import asyncio
from types import SimpleNamespace

import pytest

from travel_core.schemas import TripRequest
from travel_planner.coordination import DEMO_DISCLAIMER
from travel_planner.runner import (WorkflowRunError, agent_execution_summary,
                                   missing_specialist_calls, missing_workflow_tools, run_adk_trip)


def test_complete_plan_requires_actual_specialist_calls():
    trace = [
        {'agent': 'travel_coordinator', 'event': 'tool_call', 'tool': 'flight_agent'},
        {'agent': 'travel_coordinator', 'event': 'tool_result', 'tool': 'flight_agent'},
        {'agent': 'travel_coordinator', 'event': 'tool_call', 'tool': 'hotel_agent'},
        {'agent': 'travel_coordinator', 'event': 'tool_call', 'tool': 'itinerary_agent'},
        {'agent': 'travel_coordinator', 'event': 'tool_call', 'tool': 'budget_agent'},
    ]
    assert missing_specialist_calls(trace) == set()
    assert missing_specialist_calls(trace[:-1]) == {'budget_agent'}
    assert missing_specialist_calls([]) == {
        'flight_agent', 'hotel_agent', 'itinerary_agent', 'budget_agent'
    }


def test_workflow_tool_check_uses_events_not_final_text():
    assert missing_workflow_tools([]) == {
        'search_flights', 'search_hotels', 'suggest_activities', 'estimate_budget'
    }


def test_agent_summary_distinguishes_observed_calls_from_final_text():
    trace = [{'agent': 'flight_agent', 'event': 'tool_call', 'tool': 'search_flights'},
             {'agent': 'flight_agent', 'event': 'tool_result', 'tool': 'search_flights'},
             {'agent': 'travel_coordinator', 'event': 'final_response', 'tool': '—'}]
    summary = agent_execution_summary(trace, {'flight_agent': 1.2, 'travel_coordinator': 0.8})
    assert summary[0]['observed'] is True
    assert summary[0]['elapsed_seconds'] == 1.2
    assert summary[1]['observed'] is False
    assert summary[-1]['observed'] is True


def test_runner_timeout_preserves_partial_tool_trace(monkeypatch):
    pytest.importorskip('google.adk')
    from google.adk import runners, sessions

    class FakeSessions:
        async def create_session(self, **kwargs):
            pass

    class FakeEvent:
        author = 'flight_agent'

        def get_function_calls(self):
            return [SimpleNamespace(name='search_flights', args={})]

        def get_function_responses(self):
            return []

        def is_final_response(self):
            return False

    class SlowRunner:
        def __init__(self, **kwargs):
            pass

        async def run_async(self, **kwargs):
            yield FakeEvent()
            await asyncio.sleep(0.2)

    monkeypatch.setattr(runners, 'Runner', SlowRunner)
    monkeypatch.setattr(sessions, 'InMemorySessionService', FakeSessions)
    request = TripRequest(origin='Chicago', destination='New York City',
                          departure_date='2026-11-15', return_date='2026-11-19',
                          travelers=2, rooms=1, budget_limit_usd=2000)
    with pytest.raises(WorkflowRunError, match='exceeded') as caught:
        asyncio.run(run_adk_trip(request, timeout_seconds=0.01))
    assert caught.value.trace[0]['tool'] == 'search_flights'
    assert caught.value.timings['flight_agent'] >= 0


def test_progress_callback_failure_preserves_observed_trace(monkeypatch):
    pytest.importorskip('google.adk')
    from google.adk import runners, sessions

    class FakeSessions:
        async def create_session(self, **kwargs):
            pass

    class ToolResultEvent:
        author = 'flight_agent'

        def get_function_calls(self):
            return []

        def get_function_responses(self):
            return [SimpleNamespace(name='search_flights', response={'status': 'ok'})]

        def is_final_response(self):
            return False

    class FakeRunner:
        def __init__(self, **kwargs):
            pass

        async def run_async(self, **kwargs):
            yield ToolResultEvent()

    monkeypatch.setattr(runners, 'Runner', FakeRunner)
    monkeypatch.setattr(sessions, 'InMemorySessionService', FakeSessions)
    request = TripRequest(origin='Chicago', destination='New York City',
                          departure_date='2026-12-15', return_date='2026-12-19',
                          travelers=2, rooms=1, budget_limit_usd=2000)

    def failing_callback(event):
        assert event == {'agent': 'flight_agent', 'event': 'tool_result',
                         'tool': 'search_flights'}
        raise RuntimeError('progress view failed')

    with pytest.raises(WorkflowRunError, match='progress view failed') as caught:
        asyncio.run(run_adk_trip(request, on_progress=failing_callback))
    assert caught.value.trace[0]['tool'] == 'search_flights'
    assert isinstance(caught.value.__cause__, RuntimeError)


def test_runner_collects_ordered_events_and_final_state(monkeypatch):
    pytest.importorskip('google.adk')
    from google.adk import runners, sessions
    from google.genai import types

    class FakeSessions:
        async def create_session(self, *, state, **kwargs):
            self.state = state

        async def get_session(self, **kwargs):
            return SimpleNamespace(state=self.state)

    class FakeEvent:
        def __init__(self, author, tool=None, result=False, final=False):
            self.author, self.tool, self.result, self.final = author, tool, result, final
            self.content = (types.Content(role='model', parts=[types.Part(
                text='Final demo plan DEMO-F001 DEMO-H002. ' + DEMO_DISCLAIMER)])
                            if final else None)

        def get_function_calls(self):
            return [] if self.result or not self.tool else [SimpleNamespace(name=self.tool, args={})]

        def get_function_responses(self):
            return [SimpleNamespace(name=self.tool, response={'status': 'ok'})] if self.result else []

        def is_final_response(self):
            return self.final

    class FakeRunner:
        def __init__(self, *, session_service, **kwargs):
            self.sessions = session_service

        async def run_async(self, **kwargs):
            for author, tool in [('flight_agent', 'search_flights'),
                                 ('hotel_agent', 'search_hotels'),
                                 ('itinerary_agent', 'suggest_activities'),
                                 ('budget_agent', 'estimate_budget')]:
                yield FakeEvent(author, tool)
                yield FakeEvent(author, tool, result=True)
            self.sessions.state.update(budget_result={'status': 'ok'},
                                       plan_facts={'source': 'SYNTHETIC_DEMO'},
                                       selected_flight={'id': 'DEMO-F001'},
                                       selected_hotel={'id': 'DEMO-H002'},
                                       final_plan_text='Final demo plan DEMO-F001 DEMO-H002. ' + DEMO_DISCLAIMER)
            yield FakeEvent('travel_coordinator', final=True)

    monkeypatch.setattr(runners, 'Runner', FakeRunner)
    monkeypatch.setattr(sessions, 'InMemorySessionService', FakeSessions)
    request = TripRequest(origin='Chicago', destination='New York City',
                          departure_date='2026-11-15', return_date='2026-11-19',
                          travelers=2, rooms=1, budget_limit_usd=4000)
    result = asyncio.run(run_adk_trip(request))
    assert result['answer'].startswith('Final demo plan')
    assert [item['tool'] for item in result['trace'] if item['event'] == 'tool_call'] == [
        'search_flights', 'search_hotels', 'suggest_activities', 'estimate_budget'
    ]
    assert result['structured_plan']['source'] == 'SYNTHETIC_DEMO'
