"""The local HTTP API invokes ADK and returns the structured contract."""

import asyncio
import json
from pathlib import Path

import httpx

from backend import main
from travel_core.api_schemas import PlanTripRequest, plan_response
from travel_core.geo import ResolvedLocation
from travel_core.tools import search_flights, search_hotels
from travel_planner.runner import WorkflowRunError


NEW_YORK = ResolvedLocation(id=2, name='New York', region='New York',
                            country='United States', country_code='US',
                            latitude=40.71, longitude=-74.0)


def web_request():
    return PlanTripRequest(
        origin=ResolvedLocation(id=1, name='Chicago', region='Illinois',
                                country='United States', country_code='US',
                                latitude=41.88, longitude=-87.63),
        destination=NEW_YORK,
        departure_date='2026-11-15', return_date='2026-11-19',
        travelers=2, rooms=1, total_budget_usd=2000,
        interests=['food', 'culture'])


async def client():
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=main.app), base_url='http://test')


def test_health_and_missing_key_are_safe(monkeypatch):
    main._jobs.clear()
    monkeypatch.setattr(main, 'gemini_key_available', lambda: False)

    async def run():
        async with await client() as api:
            health = await api.get('/api/health')
            response = await api.post('/api/trips/plan',
                                      json=web_request().model_dump(mode='json'))
            return health, response

    health, response = asyncio.run(run())
    assert health.status_code == 200
    assert health.json()['gemini_configured'] is False
    assert response.status_code == 503
    assert response.json()['code'] == 'missing_gemini_key'
    assert not main._jobs


def test_city_lookup_and_provider_error(monkeypatch):
    monkeypatch.setattr(main, 'search_cities', lambda query: [NEW_YORK])

    async def run():
        async with await client() as api:
            return await api.get('/api/locations/search', params={'q': 'New York'})

    result = asyncio.run(run())
    assert result.status_code == 200
    assert result.json()[0]['name'] == 'New York'

    def unavailable(query):
        from travel_core.geo import GeographicDataError
        raise GeographicDataError('service timed out')

    monkeypatch.setattr(main, 'search_cities', unavailable)
    result = asyncio.run(run())
    assert result.status_code == 503
    assert result.json()['code'] == 'geographic_service'


def test_job_runs_existing_adk_function_and_renders_result(monkeypatch):
    main._jobs.clear()
    monkeypatch.setattr(main, 'gemini_key_available', lambda: True)
    saved = json.loads((Path(__file__).resolve().parents[1] /
                        'docs' / 'optimized-ai-run.json').read_text())
    saved['available_flights'] = search_flights(
        'Chicago', 'New York City', '2026-11-15', '2026-11-19', 2)['options']
    saved['available_hotels'] = search_hotels(
        'New York City', '2026-11-15', '2026-11-19', 1)['options']
    saved['model'] = 'gemini-2.5-flash'
    called = []

    async def fake_run(request, timeout_seconds, on_progress):
        called.append(request)
        on_progress({'agent': 'flight_agent', 'event': 'tool_result',
                     'tool': 'search_flights'})
        return saved

    monkeypatch.setattr(main, 'run_adk_trip', fake_run)

    async def run():
        async with await client() as api:
            started = await api.post('/api/trips/plan',
                                     json=web_request().model_dump(mode='json'))
            trip_id = started.json()['trip_id']
            await asyncio.sleep(0)
            status = await api.get(f'/api/trips/{trip_id}/status')
            result = await api.get(f'/api/trips/{trip_id}/result')
            return started, status, result

    started, status, result = asyncio.run(run())
    assert started.status_code == 202
    assert status.json()['status'] == 'completed'
    assert status.json()['progress'] == [{
        'agent': 'flight_agent', 'event': 'tool_result',
        'tool': 'search_flights', 'count': None}]
    assert result.status_code == 200
    assert result.json()['budget_breakdown']['optimized_total']['amount_usd'] == 1990
    assert result.json()['trip_summary']['days'] == 5
    assert len(called) == 1
    assert called[0].origin == 'Chicago'
    assert called[0].destination == 'New York City'
    assert called[0].travelers == 2 and called[0].rooms == 1


def test_quota_error_is_friendly_and_job_fails(monkeypatch):
    main._jobs.clear()
    monkeypatch.setattr(main, 'gemini_key_available', lambda: True)

    async def fake_run(request, timeout_seconds, on_progress):
        raise WorkflowRunError('429 RESOURCE_EXHAUSTED', [
            {'agent': 'flight_agent', 'event': 'tool_result', 'tool': 'search_flights'}
        ], {'flight_agent': 0.1})

    monkeypatch.setattr(main, 'run_adk_trip', fake_run)

    async def run():
        async with await client() as api:
            started = await api.post('/api/trips/plan',
                                     json=web_request().model_dump(mode='json'))
            trip_id = started.json()['trip_id']
            await asyncio.sleep(0)
            return await api.get(f'/api/trips/{trip_id}/result')

    result = asyncio.run(run())
    assert result.status_code == 409
    assert result.json()['code'] == 'gemini_quota'
    assert result.json()['diagnostics']['trace'][0]['tool'] == 'search_flights'
    assert 'RESOURCE_EXHAUSTED' not in result.json()['message']


def test_model_availability_errors_are_actionable():
    assert main._error_for(RuntimeError('503 UNAVAILABLE: high demand')).code == 'gemini_unavailable'
    assert main._error_for(RuntimeError('404 NOT_FOUND: model no longer available')).code == 'gemini_model_unavailable'


def test_invalid_dates_rejected_before_any_job(monkeypatch):
    main._jobs.clear()
    monkeypatch.setattr(main, 'gemini_key_available', lambda: True)
    payload = web_request().model_dump(mode='json')
    payload['return_date'] = '2026-11-14'

    async def run():
        async with await client() as api:
            return await api.post('/api/trips/plan', json=payload)

    response = asyncio.run(run())
    assert response.status_code == 422
    assert not main._jobs


def test_budget_endpoint_recalculates_without_adk(monkeypatch):
    from travel_core.global_planner import build_global_itinerary, partial_budget
    rome = ResolvedLocation(id=3, name='Rome', region='Lazio', country='Italy',
                            country_code='IT', latitude=41.9, longitude=12.5)
    request = web_request().model_copy(update={'destination': rome, 'rooms': 2})
    itinerary = build_global_itinerary([], [], 5, start_date='2026-11-15',
                                       destination=rome.label)
    budget = partial_budget(days=5, nights=4, travelers=2, rooms=2,
                            food_per_person_per_day_usd=45,
                            transport_per_day_usd=20, budget_limit_usd=2000,
                            flight_allowance_usd=None, hotel_allowance_usd=None)
    result = {'structured_plan': {'request': {'global_mode': True},
                                  'itinerary': itinerary['itinerary'], 'budget': budget,
                                  'attraction_status': 'insufficient_data',
                                  'replanning': {'triggered': False, 'outcome': 'none'}},
              'model': 'test-model', 'execution_mode': 'TEST'}
    main._jobs.clear()
    main._jobs['budget-test'] = main.LocalJob(
        trip_id='budget-test', status='completed', result=plan_response(request, result))
    async def unexpected_adk(*args, **kwargs):
        raise AssertionError('Budget update must not call ADK')
    monkeypatch.setattr(main, 'run_adk_trip', unexpected_adk)

    async def run():
        async with await client() as api:
            revised = await api.post('/api/trips/budget-test/budget', json={
                'flights_usd': 900, 'hotel_nightly_rate_usd': 120})
            stored = await api.get('/api/trips/budget-test/result')
            invalid = await api.post('/api/trips/budget-test/budget', json={
                'hotel_nightly_rate_usd': 120, 'hotel_whole_stay_usd': 960})
            return revised, stored, invalid

    revised, stored, invalid = asyncio.run(run())
    assert revised.status_code == stored.status_code == 200
    assert revised.json()['budget_breakdown']['estimate_based_total']['amount_usd'] == 2410
    assert revised.json()['budget_breakdown']['estimate_difference_usd'] == -410
    assert revised.json()['budget_breakdown']['within_budget'] is None
    assert revised.json()['budget_breakdown']['items'][1]['price']['source'] == 'user_estimate'
    assert stored.json()['budget_breakdown'] == revised.json()['budget_breakdown']
    assert invalid.status_code == 422
