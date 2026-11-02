"""Backend-to-frontend contracts use structured, provenance-aware values."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from travel_core.api_schemas import PlanTripRequest, Price, plan_response
from travel_core.geo import ResolvedLocation
from travel_core.tools import search_flights, search_hotels


def city(id, name, region, country, code, latitude, longitude):
    return ResolvedLocation(id=id, name=name, region=region, country=country,
                            country_code=code, latitude=latitude, longitude=longitude)


CHICAGO = city(1, 'Chicago', 'Illinois', 'United States', 'US', 41.88, -87.63)
NEW_YORK = city(2, 'New York', 'New York', 'United States', 'US', 40.71, -74.0)
ROME = city(3, 'Rome', 'Lazio', 'Italy', 'IT', 41.9, 12.5)


def web_request(destination=NEW_YORK):
    return PlanTripRequest(
        origin=CHICAGO, destination=destination,
        departure_date='2026-11-15', return_date='2026-11-19',
        travelers=2, rooms=1, total_budget_usd=2000,
        interests=['food', 'culture'], travel_pace='Balanced')


def test_web_request_preserves_validated_dates_and_sample_route():
    trip = web_request().to_trip_request()
    assert trip.global_mode is False
    assert trip.destination == 'New York City'
    assert (trip.return_date - trip.departure_date).days == 4
    assert web_request(ROME).to_trip_request().global_mode is True


def test_invalid_dates_and_unknown_price_are_rejected():
    with pytest.raises(ValidationError):
        PlanTripRequest(origin=CHICAGO, destination=ROME,
                        departure_date='2026-11-19', return_date='2026-11-15',
                        travelers=2, rooms=1, total_budget_usd=2000)
    with pytest.raises(ValidationError):
        Price(amount_usd=0, kind='unknown', source='unknown')
    assert Price(amount_usd=42, kind='known', source='verified').amount_usd == 42
    with pytest.raises(ValidationError):
        Price(amount_usd=42, kind='known', source='simulated')


def test_saved_adk_result_maps_to_structured_budget_without_markdown():
    saved = json.loads((Path(__file__).resolve().parents[1] /
                        'docs' / 'optimized-ai-run.json').read_text())
    saved['available_flights'] = search_flights(
        'Chicago', 'New York City', '2026-11-15', '2026-11-19', 2)['options']
    saved['available_hotels'] = search_hotels(
        'New York City', '2026-11-15', '2026-11-19', 1)['options']
    plan = plan_response(web_request(), saved)
    assert plan.trip_summary.days == 5
    assert plan.trip_summary.nights == 4
    assert len(plan.daily_itinerary) == 5
    assert plan.selected_flight.id == 'DEMO-F001'
    assert plan.selected_hotel.id == 'DEMO-H001'
    assert plan.budget_breakdown.initial_total.amount_usd == 2270
    assert plan.budget_breakdown.optimized_total.amount_usd == 1990
    assert plan.budget_breakdown.savings.amount_usd == 280
    assert plan.budget_breakdown.comparison_status == 'complete'
    assert plan.flight_options[0].group_round_trip.source == 'simulated'
    assert 'answer' not in plan.model_dump()
