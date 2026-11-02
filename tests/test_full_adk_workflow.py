"""Exercise every ADK stage without spending a Gemini request."""

import asyncio

import httpx
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.genai import types

from backend import main
from travel_core.api_schemas import PlanTripRequest
from travel_core.geo import Attraction, ResolvedLocation
from travel_core.schemas import TripRequest
from travel_planner.runner import run_adk_trip


class ItineraryModel(BaseLlm):
    calls: int = 0
    selected_ids: str = ''

    async def generate_content_async(self, llm_request, stream=False):
        self.calls += 1
        if self.calls == 1:
            yield LlmResponse(content=types.Content(role='model', parts=[
                types.Part.from_function_call(name='suggest_activities', args={
                    'selected_attraction_ids': self.selected_ids} if self.selected_ids else {})]))
        else:
            yield LlmResponse(content=types.Content(role='model', parts=[
                types.Part(text='Itinerary tool complete.')]), turn_complete=True)


class CoordinatorModel(BaseLlm):
    calls: int = 0
    hotel_id: str = 'DEMO-H002'

    async def generate_content_async(self, llm_request, stream=False):
        self.calls += 1
        yield LlmResponse(content=types.Content(role='model', parts=[
            types.Part(text='Chicago to New York City, December 15–19 for two travelers. '
                            f'Choose DEMO-F001 and {self.hotel_id}. '
                            'The plan includes five activity days.')]),
            turn_complete=True)


def test_complete_adk_workflow_uses_python_tools_and_final_coordinator(monkeypatch):
    from travel_planner.agent import itinerary_agent, travel_coordinator

    itinerary_model = ItineraryModel(model='fake-itinerary')
    coordinator_model = CoordinatorModel(model='fake-coordinator')
    monkeypatch.setattr(itinerary_agent, 'model', itinerary_model)
    monkeypatch.setattr(travel_coordinator, 'model', coordinator_model)
    request = TripRequest(
        origin='Chicago', destination='New York City',
        departure_date='2026-12-15', return_date='2026-12-19',
        travelers=2, rooms=1, budget_limit_usd=5000,
        interests='culture,food',
    )

    result = asyncio.run(run_adk_trip(request, timeout_seconds=20))

    calls = [(item['agent'], item['tool']) for item in result['trace']
             if item['event'] == 'tool_call']
    responses = [(item['agent'], item['tool']) for item in result['trace']
                 if item['event'] == 'tool_result']
    expected = [
        ('flight_agent', 'search_flights'),
        ('hotel_agent', 'search_hotels'),
        ('itinerary_agent', 'suggest_activities'),
        ('budget_agent', 'estimate_budget'),
    ]
    assert calls == expected
    assert responses == expected
    assert itinerary_model.calls == 1
    assert coordinator_model.calls == 1
    assert result['structured_plan']['budget']['status'] == 'ok'
    assert result['structured_plan']['budget']['nights'] == 4
    assert result['structured_plan']['request']['travelers'] == 2
    assert all(row['observed'] for row in result['agent_summary'])
    assert result['trace'][-1]['event'] == 'final_response'
    assert 'DEMO DATA:' in result['answer']


def _city(city_id: int, name: str, region: str, country: str, country_code: str,
          latitude: float, longitude: float) -> ResolvedLocation:
    return ResolvedLocation(id=city_id, name=name, region=region,
                            country=country, country_code=country_code,
                            latitude=latitude, longitude=longitude)


def test_http_job_invokes_real_adk_runner_and_returns_validated_trip(monkeypatch):
    """HTTP form payload -> FastAPI job -> ADK -> structured dashboard payload."""
    from travel_planner.agent import itinerary_agent, travel_coordinator

    monkeypatch.setattr(itinerary_agent, 'model', ItineraryModel(model='fake-itinerary'))
    monkeypatch.setattr(travel_coordinator, 'model',
                        CoordinatorModel(model='fake-coordinator', hotel_id='DEMO-H001'))
    monkeypatch.setattr(main, 'gemini_key_available', lambda: True)
    main._jobs.clear()
    request = PlanTripRequest(
        origin=_city(1, 'Chicago', 'Illinois', 'United States', 'US', 41.88, -87.63),
        destination=_city(2, 'New York', 'New York', 'United States', 'US', 40.71, -74),
        departure_date='2026-12-15', return_date='2026-12-19',
        travelers=2, rooms=1, total_budget_usd=2000,
        interests=['culture', 'food'])

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app), base_url='http://test') as api:
            started = await api.post('/api/trips/plan',
                                     json=request.model_dump(mode='json'))
            assert started.status_code == 202
            trip_id = started.json()['trip_id']
            status = None
            for _ in range(100):
                status = await api.get(f'/api/trips/{trip_id}/status')
                if status.json()['status'] in {'completed', 'failed'}:
                    break
                await asyncio.sleep(0.02)
            result = await api.get(f'/api/trips/{trip_id}/result')
            return status, result

    status, result = asyncio.run(run())
    assert status.json()['status'] == 'completed'
    assert [event['tool'] for event in status.json()['progress']
            if event['event'] == 'tool_result'] == [
                'search_flights', 'search_hotels', 'suggest_activities',
                'estimate_budget', 'estimate_budget']
    assert result.status_code == 200
    body = result.json()
    assert body['trip_summary']['days'] == 5
    assert body['trip_summary']['nights'] == 4
    assert body['trip_summary']['travelers'] == 2
    assert len(body['daily_itinerary']) == 5
    assert body['budget_breakdown']['initial_total']['amount_usd'] == 2270
    assert body['budget_breakdown']['optimized_total']['amount_usd'] == 1990
    assert body['budget_breakdown']['savings']['amount_usd'] == 280
    assert body['selected_flight']['group_round_trip']['source'] == 'simulated'
    assert body['selected_hotel']['bookable'] is False
    assert body['diagnostics']['trace'][-1]['event'] == 'final_response'


def test_global_adk_uses_model_selected_verified_places_and_partial_budget(monkeypatch):
    from travel_core import geo
    from travel_planner.agent import itinerary_agent, travel_coordinator

    chicago = _city(1, 'Chicago', 'Illinois', 'United States', 'US', 41.88, -87.63)
    rome = _city(3169070, 'Rome', 'Lazio', 'Italy', 'IT', 41.9, 12.5)
    attractions = [Attraction(
        id=f'osm:node/{index}', name=f'{"Museum" if index < 6 else "Park"} {index}',
        category='museum' if index < 6 else 'park',
        latitude=41.9 + index * 0.001, longitude=12.5)
        for index in range(12)]
    monkeypatch.setattr(geo, 'discover_attractions', lambda location: attractions)
    request = TripRequest(
        origin=chicago.label, destination=rome.label,
        origin_location=chicago, destination_location=rome, global_mode=True,
        departure_date='2026-12-15', return_date='2026-12-20',
        travelers=2, rooms=1, budget_limit_usd=2500,
        flight_allowance_usd=800, hotel_allowance_usd=600,
        interests='history,culture,food', travel_pace='Relaxed')

    async def run_with(selected_id: str):
        monkeypatch.setattr(itinerary_agent, 'model', ItineraryModel(
            model='fake-itinerary', selected_ids=selected_id))
        monkeypatch.setattr(travel_coordinator, 'model',
                            CoordinatorModel(model='fake-coordinator'))
        return await run_adk_trip(request, timeout_seconds=20)

    museum = asyncio.run(run_with('osm:node/1'))
    outdoors = asyncio.run(run_with('osm:node/8'))
    for result in (museum, outdoors):
        calls = [item['tool'] for item in result['trace'] if item['event'] == 'tool_call']
        assert calls == ['search_flights', 'search_hotels',
                         'suggest_activities', 'partial_budget']
        assert result['structured_plan']['flight'] is None
        assert result['structured_plan']['hotel'] is None
        assert result['structured_plan']['budget']['status'] == 'partial'
        assert result['structured_plan']['budget']['within_budget'] is None
        assert len(result['structured_plan']['itinerary']) == 6
        assert result['structured_plan']['budget']['nights'] == 5
        assert result['trace'][-1]['event'] == 'final_response'
    first_museum = museum['structured_plan']['itinerary'][0]['slots'][0]
    first_outdoor = outdoors['structured_plan']['itinerary'][0]['slots'][0]
    assert first_museum['category'] == 'museum'
    assert first_outdoor['category'] == 'park'
    assert first_museum['title'] != first_outdoor['title']
    response = __import__('travel_core.api_schemas', fromlist=['plan_response']).plan_response(
        PlanTripRequest(origin=chicago, destination=rome,
                        departure_date='2026-12-15', return_date='2026-12-20',
                        travelers=2, rooms=1, total_budget_usd=2500,
                        interests=['history', 'culture', 'food']), museum)
    assert response.attraction_data.status == 'complete'
    assert response.daily_itinerary[0].slots[0].attraction_id == 'osm:node/1'


def test_global_adk_completes_with_no_attraction_provider(monkeypatch):
    from travel_core import geo
    from travel_planner.agent import itinerary_agent, travel_coordinator

    chicago = _city(1, 'Chicago', 'Illinois', 'United States', 'US', 41.88, -87.63)
    rome = _city(3169070, 'Rome', 'Lazio', 'Italy', 'IT', 41.9, 12.5)
    def unavailable(location):
        raise geo.GeographicDataError('Location service is unavailable: TimeoutError')
    monkeypatch.setattr(geo, 'discover_attractions', unavailable)
    monkeypatch.setattr(geo, 'discover_wikipedia_attractions', unavailable)
    monkeypatch.setattr(itinerary_agent, 'model', ItineraryModel(model='fake-itinerary'))
    monkeypatch.setattr(travel_coordinator, 'model', CoordinatorModel(model='fake-coordinator'))
    request = TripRequest(
        origin=chicago.label, destination=rome.label,
        origin_location=chicago, destination_location=rome, global_mode=True,
        departure_date='2026-12-14', return_date='2026-12-21',
        travelers=2, rooms=1, budget_limit_usd=2000, interests='culture,food',
        travel_pace='Relaxed')
    result = asyncio.run(run_adk_trip(request, timeout_seconds=20))
    calls = [item['tool'] for item in result['trace'] if item['event'] == 'tool_call']
    assert calls == ['search_flights', 'search_hotels', 'suggest_activities', 'partial_budget']
    assert result['structured_plan']['attraction_status'] == 'insufficient_data'
    assert result['structured_plan']['budget']['known_subtotal_usd'] == 880
    assert result['structured_plan']['budget']['nights'] == 7
    assert result['structured_plan']['budget']['within_budget'] is None
    assert len(result['structured_plan']['itinerary']) == 8
    assert result['attractions'] == []
    response = __import__('travel_core.api_schemas', fromlist=['plan_response']).plan_response(
        PlanTripRequest(origin=chicago, destination=rome,
                        departure_date='2026-12-14', return_date='2026-12-21',
                        travelers=2, rooms=1, total_budget_usd=2000,
                        interests=['culture', 'food']), result)
    assert response.data_sources == ['OPEN_METEO_GEOCODING']
    assert response.attraction_data.status == 'insufficient_data'
    assert response.attraction_data.verified_count == 0
    assert any('No verified attractions' in warning for warning in response.warnings)
    assert all(not slot.verified_place for day in response.daily_itinerary for slot in day.slots)
