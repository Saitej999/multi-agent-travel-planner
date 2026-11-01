"""Fast, local checks of the deterministic Phase 2 decision path."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from travel_core.replanning import choose_revised_plan
from travel_core.schemas import TripRequest
from travel_core.tools import search_flights, search_hotels, suggest_activities
from travel_planner.coordination import save_specialist_tool_result
from travel_planner.coordination import DEMO_DISCLAIMER, ensure_demo_disclaimer


def prepared_state(limit=2000, interests='food,culture,outdoors'):
    request = TripRequest(origin='Chicago', destination='New York City',
                          departure_date='2026-11-15', return_date='2026-11-19',
                          travelers=2, rooms=1, budget_limit_usd=limit,
                          interests=interests)
    state = {'trip_request': request.model_dump(mode='json')}
    ctx = SimpleNamespace(state=state, actions=SimpleNamespace(skip_summarization=False))
    responses = [
        ('search_flights', search_flights('Chicago', 'New York City', '2026-11-15', '2026-11-19', 2)),
        ('search_hotels', search_hotels('New York City', '2026-11-15', '2026-11-19', 1)),
        ('suggest_activities', suggest_activities('New York City', 5, request.interests)),
    ]
    for name, response in responses:
        save_specialist_tool_result(SimpleNamespace(name=name), {}, ctx, response)
    return state


def run_budget(state):
    pytest.importorskip('google.adk')
    from travel_planner.budget_agent import BudgetAgent

    invocation = SimpleNamespace(session=SimpleNamespace(state=state), invocation_id='test')

    async def collect():
        events = []
        async for event in BudgetAgent(name='budget_agent')._run_async_impl(invocation):
            events.append(event)
            state.update(event.actions.state_delta or {})
        return events

    return asyncio.run(collect())


def test_within_budget_keeps_original_and_skips_optimization(monkeypatch):
    state = prepared_state(4000)
    def unexpected(*args):
        raise AssertionError('replanning should not run')
    monkeypatch.setattr('travel_planner.budget_agent.choose_revised_plan', unexpected)
    events = run_budget(state)
    assert len(events) == 2
    assert state['budget_result']['estimated_total_usd'] == 2270
    assert state['replanning']['triggered'] is False
    assert state.get('revised_plan') is None


def test_over_budget_selects_returned_hotel_and_recalculates():
    state = prepared_state()
    events = run_budget(state)
    assert [call.name for event in events for call in event.get_function_calls()] == [
        'estimate_budget', 'estimate_budget']
    assert state['original_plan']['flight']['id'] == 'DEMO-F001'
    assert state['original_plan']['hotel']['id'] == 'DEMO-H002'
    assert state['original_plan']['itinerary']['estimated_activities_usd_per_person'] == 70
    assert state['initial_budget_result']['estimated_total_usd'] == 2270
    assert state['initial_budget_result']['remaining_usd'] == -270
    assert state['revised_plan']['hotel']['id'] == 'DEMO-H001'
    assert state['budget_result']['estimated_total_usd'] == 1990
    assert state['budget_result']['remaining_usd'] == 10
    assert state['replanning']['amount_saved_usd'] == 280
    assert state['replanning']['outcome'] == 'replanned_within_budget'
    assert state['replanning']['source_results'] == [
        'flight_search', 'hotel_search', 'itinerary_result', 'free_itinerary_result']
    assert state['plan_facts']['request']['departure_date'] == '2026-11-15'
    assert state['plan_facts']['request']['return_date'] == '2026-11-19'
    assert (state['budget_result']['nights'], state['budget_result']['travelers'],
            state['budget_result']['rooms']) == (4, 2, 1)
    assert sum(state['budget_result']['breakdown'].values()) == 1990
    brief = state['coordinator_facts']
    assert brief['selected_hotel']['id'] == 'DEMO-H001'
    assert brief['original']['total_usd'] == 2270
    assert brief['final']['total_usd'] == 1990
    assert len(brief['daily_activities']) == 5
    assert len(json.dumps(brief)) < len(json.dumps(state['plan_facts']))


def test_no_affordable_combination_reports_cheapest_shortfall():
    state = prepared_state(100)
    run_budget(state)
    assert state['replanning']['outcome'] == 'no_plan_within_budget'
    assert state['replanning']['final_within_budget'] is False
    assert state['revised_plan']['flight']['id'] == 'DEMO-F002'
    assert state['revised_plan']['hotel']['id'] == 'DEMO-H001'
    assert state['revised_plan']['itinerary']['free_only'] is True
    assert state['budget_result']['estimated_total_usd'] == 1720
    assert state['budget_result']['remaining_usd'] == -1620
    assert 'shortfall' in state['replanning']['explanation']


def test_requested_interests_change_the_itinerary_and_revision():
    state = prepared_state(2000, 'food,museums,sightseeing')
    run_budget(state)
    assert state['initial_budget_result']['estimated_total_usd'] == 2460
    assert state['replanning']['final_within_budget'] is True
    assert state['budget_result']['estimated_total_usd'] == 2000
    assert state['revised_plan']['flight']['id'] == 'DEMO-F002'
    assert state['revised_plan']['itinerary']['free_only'] is True


@pytest.mark.parametrize('missing', ['flight_search', 'hotel_search'])
def test_missing_search_result_stops_budget(missing):
    state = prepared_state()
    state.pop(missing)
    events = run_budget(state)
    assert len(events) == 1
    assert state['budget_result']['status'] == 'missing_inputs'


@pytest.mark.parametrize('selected', ['selected_flight', 'selected_hotel'])
def test_unreturned_selection_is_rejected(selected):
    state = prepared_state()
    state[selected] = {'id': 'DEMO-INVALID'}
    run_budget(state)
    assert state['budget_result']['status'] == 'missing_inputs'
    assert 'not returned' in state['workflow_error']


def test_optimizer_uses_only_verified_options():
    state = prepared_state()
    args = {'flight_option_id': 'DEMO-F001', 'hotel_option_id': 'DEMO-H002',
            'nights': 4, 'travelers': 2, 'rooms': 1,
            'food_per_person_per_day_usd': 45, 'transport_per_day_usd': 20,
            'activities_per_person_usd': 70, 'budget_limit_usd': 2000}
    selection = choose_revised_plan(state, args)
    assert selection['flight'] in state['flight_search']['options']
    assert selection['hotel'] in state['hotel_search']['options']
    assert selection['itinerary'] in [state['itinerary_result'], state['free_itinerary_result']]
    assert selection['evaluated_alternatives'] == 8


def test_final_response_includes_verified_budget_comparison():
    pytest.importorskip('google.adk')
    from google.adk.models.llm_response import LlmResponse
    from google.genai import types

    state = prepared_state()
    run_budget(state)
    response = LlmResponse(content=types.Content(role='model', parts=[types.Part(text='Trip plan')]))
    amended = ensure_demo_disclaimer(SimpleNamespace(state=state), response)
    text = ''.join(part.text or '' for part in amended.content.parts)
    assert 'original DEMO-F001 / DEMO-H002 $2,270.00' in text
    assert 'revised DEMO-F001 / DEMO-H001 $1,990.00' in text
    assert 'saved $280.00' in text
    assert DEMO_DISCLAIMER in text
