"""Backend-to-frontend contracts use structured, provenance-aware values."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from travel_core.api_schemas import (BudgetEstimateRequest, PlanTripRequest, Price,
                                     plan_response, recalculate_trip_estimates)
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


def test_global_estimates_use_python_and_keep_admission_unknown():
    from travel_core.global_planner import build_global_itinerary, partial_budget
    request = web_request(ROME).model_copy(update={'rooms': 2})
    itinerary = build_global_itinerary([], [], 5, start_date='2026-11-15',
                                       destination=ROME.label)
    budget = partial_budget(days=5, nights=4, travelers=2, rooms=2,
                            food_per_person_per_day_usd=45,
                            transport_per_day_usd=20, budget_limit_usd=2000,
                            flight_allowance_usd=None, hotel_allowance_usd=None)
    result = {'structured_plan': {'request': {'global_mode': True},
                                  'itinerary': itinerary['itinerary'], 'budget': budget,
                                  'attraction_status': 'insufficient_data',
                                  'replanning': {'triggered': False, 'outcome': 'none'}},
              'model': 'test-model', 'execution_mode': 'TEST'}
    plan = plan_response(request, result)
    revised = recalculate_trip_estimates(plan, BudgetEstimateRequest(
        flights_usd=900, hotel_nightly_rate_usd=120))
    assert revised.budget_breakdown.items[1].price.amount_usd == 960
    assert revised.budget_breakdown.known_subtotal.amount_usd == 2410
    assert revised.budget_breakdown.estimate_based_total.amount_usd == 2410
    assert revised.budget_breakdown.estimate_difference_usd == -410
    assert revised.budget_breakdown.within_budget is None
    assert revised.budget_breakdown.comparison_status == 'partial'
    assert revised.budget_breakdown.items[0].price.source == 'user_estimate'
    complete = recalculate_trip_estimates(plan, BudgetEstimateRequest(
        flights_usd=900, hotel_whole_stay_usd=960, admission_usd=100))
    assert complete.budget_breakdown.estimate_based_total.amount_usd == 2510
    assert complete.budget_breakdown.comparison_status == 'estimate_complete'
    assert complete.budget_breakdown.within_budget is False
    with pytest.raises(ValidationError):
        BudgetEstimateRequest(hotel_nightly_rate_usd=120, hotel_whole_stay_usd=960)
