import json
import asyncio
from types import SimpleNamespace

import pytest

from travel_core.schemas import TripRequest
from travel_core.tools import search_flights, search_hotels, suggest_activities
from travel_planner.coordination import (
    DEMO_DISCLAIMER, ensure_demo_disclaimer, prepare_request, save_specialist_tool_result,
    specialist_tool_args,
)


REQUEST = TripRequest(
    origin='Chicago', destination='New York City',
    departure_date='2026-11-15', return_date='2026-11-19',
    travelers=2, rooms=1, budget_limit_usd=4000,
    interests='food,culture,outdoors',
)


def context(state=None):
    return SimpleNamespace(state={} if state is None else state,
                           actions=SimpleNamespace(skip_summarization=False),
                           user_content=None)


def test_request_is_validated_and_serializable():
    ctx = context({'trip_request': REQUEST.model_dump(mode='json'),
                   'selected_flight': {'id': 'DEMO-F999'},
                   'budget_result': {'status': 'ok'}})
    assert prepare_request(ctx) is None
    assert ctx.state['budget_limit_usd'] == 4000
    assert ctx.state['selected_flight'] is None
    assert ctx.state['budget_result'] is None
    json.dumps(ctx.state)


def test_new_web_request_replaces_previous_trip_state():
    previous = REQUEST.model_dump(mode='json')
    next_request = {**previous, 'destination': 'San Francisco'}
    ctx = context({'trip_request': previous, 'selected_flight': {'id': 'DEMO-F001'}})
    ctx.user_content = SimpleNamespace(parts=[SimpleNamespace(text=json.dumps(next_request))])
    assert prepare_request(ctx) is None
    assert ctx.state['trip_request']['destination'] == 'San Francisco'
    assert ctx.state['selected_flight'] is None


def test_model_tool_arguments_are_replaced_by_validated_request():
    state = {'trip_request': REQUEST.model_dump(mode='json')}
    tool_context = context(state)
    args = {'origin': 'Los Angeles', 'destination': 'Miami', 'travelers': 99}
    specialist_tool_args(SimpleNamespace(name='search_flights'), args, tool_context)
    assert args == {'origin': 'Chicago', 'destination': 'New York City',
                    'departure_date': '2026-11-15', 'return_date': '2026-11-19',
                    'travelers': 2}

    args = {'days': 4}
    specialist_tool_args(SimpleNamespace(name='suggest_activities'), args, tool_context)
    assert args['days'] == 5
    assert args['destination'] == 'New York City'


def test_global_itinerary_proposal_is_grounded_to_five_days_and_verified_ids():
    from travel_core.geo import Attraction, ResolvedLocation

    city = ResolvedLocation(id=1, name='Rome', region='Lazio', country='Italy',
                            latitude=41.9, longitude=12.5)
    request = REQUEST.model_copy(update={'destination': city.label,
                                         'destination_location': city,
                                         'origin_location': city,
                                         'global_mode': True})
    candidates = [Attraction(id='node/42', name='Museum A', category='museum',
                             latitude=41.91, longitude=12.51).model_dump()]
    ctx = context({'trip_request': request.model_dump(mode='json'),
                   'attraction_candidates': candidates})
    proposed = {'days': 14, 'selected_attraction_ids': 'made-up,node/42'}
    specialist_tool_args(SimpleNamespace(name='suggest_activities'), proposed, ctx)
    assert proposed['days'] == 5
    assert proposed['selected_attraction_ids'] == 'node/42'
    result = suggest_activities(**proposed)
    assert result['status'] == 'ok'
    assert len(result['itinerary']) == 5


def test_itinerary_agent_can_prioritize_requested_interests_without_changing_trip_facts():
    request = REQUEST.model_copy(update={'interests': 'culture,outdoors',
                                         'preferences': 'Relaxed museums; avoid busy tourist spots'})
    ctx = context({'trip_request': request.model_dump(mode='json')})
    args = {'destination': 'Tokyo', 'days': 30, 'interests': 'outdoors,culture,entertainment',
            'avoid_popular_spots': 'true', 'free_only': True}
    specialist_tool_args(SimpleNamespace(name='suggest_activities'), args, ctx)
    assert args == {'destination': 'New York City', 'days': 5,
                    'interests': 'outdoors,culture', 'free_only': False,
                    'avoid_popular_spots': True}


def test_model_callbacks_measure_request_without_recording_prompt_text():
    from travel_planner.coordination import record_model_start, record_model_response

    ctx = SimpleNamespace(agent_name='flight_agent', state={})
    request = SimpleNamespace(contents=[SimpleNamespace(parts=[SimpleNamespace(text='trip details')])])
    record_model_start(ctx, request)
    record_model_response(ctx, None)
    metrics = ctx.state['model_metrics']
    assert metrics[0]['request_number'] == 1
    assert metrics[0]['content_text_chars'] == len('trip details')
    assert metrics[0]['status'] == 'completed'
    assert metrics[0]['duration_seconds'] >= 0
    assert 'trip details' not in str(metrics)


def test_python_tool_results_are_shared_and_selected_from_actual_options():
    ctx = context({'trip_request': REQUEST.model_dump(mode='json')})
    prepare_request(ctx)
    responses = [
        ('search_flights', search_flights('Chicago', 'New York City', '2026-11-15', '2026-11-19', 2)),
        ('search_hotels', search_hotels('New York City', '2026-11-15', '2026-11-19', 1)),
        ('suggest_activities', suggest_activities('New York City', 5, 'food,culture,outdoors')),
    ]
    for name, result in responses:
        save_specialist_tool_result(SimpleNamespace(name=name), {}, ctx, result)
    assert ctx.actions.skip_summarization is True
    assert ctx.state['selected_flight']['id'] in {x['id'] for x in ctx.state['flight_search']['options']}
    assert ctx.state['selected_hotel']['id'] in {x['id'] for x in ctx.state['hotel_search']['options']}
    assert ctx.state['selected_flight']['id'] == 'DEMO-F001'
    assert ctx.state['selected_hotel']['id'] == 'DEMO-H002'
    assert ctx.state['hotel_nights'] == 4
    assert ctx.state['activities_per_person_usd'] == 70
    json.dumps(ctx.state)


def test_unsupported_route_stops_downstream_work():
    ctx = context({'trip_request': REQUEST.model_dump(mode='json')})
    result = search_flights('Chicago', 'Miami', '2026-11-15', '2026-11-19', 2)
    save_specialist_tool_result(SimpleNamespace(name='search_flights'), {}, ctx, result)
    assert 'workflow_error' in ctx.state
    assert 'selected_flight' not in ctx.state


def test_budget_depends_on_verified_tool_results():
    pytest.importorskip('google.adk')
    from travel_planner.budget_agent import budget_inputs_from_state

    ctx = context({'trip_request': REQUEST.model_dump(mode='json')})
    with pytest.raises(ValueError, match='Missing upstream results'):
        budget_inputs_from_state(ctx.state)
    for name, result in [
        ('search_flights', search_flights('Chicago', 'New York City', '2026-11-15', '2026-11-19', 2)),
        ('search_hotels', search_hotels('New York City', '2026-11-15', '2026-11-19', 1)),
        ('suggest_activities', suggest_activities('New York City', 5, 'food,culture,outdoors')),
    ]:
        save_specialist_tool_result(SimpleNamespace(name=name), {}, ctx, result)
    kwargs = budget_inputs_from_state(ctx.state)
    assert (kwargs['flight_option_id'], kwargs['hotel_option_id']) == ('DEMO-F001', 'DEMO-H002')
    assert (kwargs['nights'], kwargs['travelers'], kwargs['rooms']) == (4, 2, 1)
    assert kwargs['activities_per_person_usd'] == 70

    ctx.state['selected_flight'] = {'id': 'DEMO-F999'}
    with pytest.raises(ValueError, match='not returned'):
        budget_inputs_from_state(ctx.state)


def test_project_root_is_the_required_sequential_order():
    pytest.importorskip('google.adk')
    from google.adk.agents import SequentialAgent
    from travel_planner.agent import root_agent

    assert isinstance(root_agent, SequentialAgent)
    assert [agent.name for agent in root_agent.sub_agents] == [
        'flight_agent', 'hotel_agent', 'itinerary_agent', 'budget_agent', 'travel_coordinator'
    ]


def test_budget_agent_emits_python_call_result_and_state_delta():
    pytest.importorskip('google.adk')
    from travel_planner.budget_agent import BudgetAgent

    ctx = context({'trip_request': REQUEST.model_dump(mode='json')})
    for name, result in [
        ('search_flights', search_flights('Chicago', 'New York City', '2026-11-15', '2026-11-19', 2)),
        ('search_hotels', search_hotels('New York City', '2026-11-15', '2026-11-19', 1)),
        ('suggest_activities', suggest_activities('New York City', 5, 'food,culture,outdoors')),
    ]:
        save_specialist_tool_result(SimpleNamespace(name=name), {}, ctx, result)
    invocation = SimpleNamespace(session=SimpleNamespace(state=ctx.state), invocation_id='unit-test')

    async def collect():
        return [event async for event in BudgetAgent(name='budget_agent')._run_async_impl(invocation)]

    events = asyncio.run(collect())
    assert [call.name for call in events[0].get_function_calls()] == ['estimate_budget']
    assert [response.name for response in events[1].get_function_responses()] == ['estimate_budget']
    budget = events[1].actions.state_delta['budget_result']
    assert budget['estimated_total_usd'] == 2270
    assert budget['remaining_usd'] == 1730
    assert events[1].actions.state_delta['plan_facts']['flight']['id'] == 'DEMO-F001'


def test_budget_agent_reports_missing_upstream_results_without_calculating():
    pytest.importorskip('google.adk')
    from travel_planner.budget_agent import BudgetAgent

    invocation = SimpleNamespace(session=SimpleNamespace(state={
        'trip_request': REQUEST.model_dump(mode='json')}), invocation_id='unit-test')

    async def collect():
        return [event async for event in BudgetAgent(name='budget_agent')._run_async_impl(invocation)]

    events = asyncio.run(collect())
    assert len(events) == 1
    assert events[0].get_function_calls() == []
    assert events[0].actions.state_delta['budget_result']['status'] == 'missing_inputs'


def test_final_model_response_keeps_simulated_disclaimer():
    pytest.importorskip('google.adk')
    from google.adk.models.llm_response import LlmResponse
    from google.genai import types

    response = LlmResponse(content=types.Content(role='model', parts=[types.Part(text='Plan total: $2,270')]))
    callback_context = SimpleNamespace(state={'plan_facts': {'budget': {'nights': 4}}})
    amended = ensure_demo_disclaimer(callback_context, response)
    assert DEMO_DISCLAIMER in ''.join(part.text or '' for part in amended.content.parts)
    assert '4 nights' in ''.join(part.text or '' for part in amended.content.parts)
    assert ensure_demo_disclaimer(callback_context, amended) is None
