"""Mandatory searches execute through ADK even without a model key."""

import asyncio

import pytest

from travel_core.schemas import TripRequest


def test_flight_and_hotel_stages_emit_real_python_tool_events():
    pytest.importorskip('google.adk')
    from google.adk.agents import SequentialAgent
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types
    from travel_planner.retrieval_agents import FlightSearchAgent, HotelSearchAgent

    request = TripRequest(
        origin='Chicago', destination='New York City',
        departure_date='2026-12-15', return_date='2026-12-19',
        travelers=2, rooms=1, budget_limit_usd=2000,
    )

    async def run():
        sessions = InMemorySessionService()
        await sessions.create_session(
            app_name='retrieval_test', user_id='user', session_id='trip',
            state={'trip_request': request.model_dump(mode='json')})
        root = SequentialAgent(name='retrieval_test_workflow', sub_agents=[
            FlightSearchAgent(name='flight_agent'),
            HotelSearchAgent(name='hotel_agent'),
        ])
        runner = Runner(agent=root, app_name='retrieval_test', session_service=sessions)
        events = [event async for event in runner.run_async(
            user_id='user', session_id='trip',
            new_message=types.Content(role='user', parts=[
                types.Part(text=request.model_dump_json())]))]
        session = await sessions.get_session(
            app_name='retrieval_test', user_id='user', session_id='trip')
        return events, session.state

    events, state = asyncio.run(run())
    assert [(event.author, call.name) for event in events
            for call in event.get_function_calls()] == [
                ('flight_agent', 'search_flights'), ('hotel_agent', 'search_hotels')]
    assert [(event.author, response.name) for event in events
            for response in event.get_function_responses()] == [
                ('flight_agent', 'search_flights'), ('hotel_agent', 'search_hotels')]
    assert state['selected_flight']['id'] == 'DEMO-F001'
    assert state['selected_hotel']['id'] == 'DEMO-H002'
    assert state['hotel_nights'] == 4
    assert all(metric['source'] == 'deterministic_adk_agent'
               for metric in state['tool_metrics'])
