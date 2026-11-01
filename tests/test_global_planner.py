"""Grounding and arithmetic for the optional global planning path."""

from travel_core.geo import Attraction, ResolvedLocation
from travel_core.global_planner import build_global_itinerary, partial_budget
from travel_core.tools import search_flights, search_hotels


def test_global_itinerary_uses_verified_places_once_and_actual_days():
    places = [Attraction(id=f'node/{i}', name=f'Place {i}', category='museum',
                         latitude=41.9 + i * .001, longitude=12.5).model_dump()
              for i in range(7)]
    result = build_global_itinerary(places, ['node/3', 'invented'], 5, 'Relaxed')
    assert result['status'] == 'ok'
    assert len(result['itinerary']) == 5
    assert all(len(day['slots']) == 3 for day in result['itinerary'])
    assert result['selected_attraction_ids'][0] == 'node/3'
    assert len(set(result['selected_attraction_ids'])) == len(result['selected_attraction_ids'])
    assert all(slot['source'] == 'GENERAL_SUGGESTION' for day in result['itinerary']
               for slot in day['slots'] if not slot['verified_place'])


def test_global_budget_keeps_unknown_costs_unknown():
    result = partial_budget(days=5, nights=4, travelers=2, rooms=1,
                            food_per_person_per_day_usd=45,
                            transport_per_day_usd=20, budget_limit_usd=2000,
                            flight_allowance_usd=800, hotel_allowance_usd=600)
    assert result['known_subtotal_usd'] == 1950
    assert result['estimated_total_usd'] is None
    assert result['within_budget'] is None
    assert result['missing_costs'] == ['admission_usd']
    assert result['nights'] == 4


def test_global_search_does_not_fabricate_offers():
    flights = search_flights('Chicago, Illinois, United States', 'Rome, Lazio, Italy',
                             '2026-11-15', '2026-11-19', 2, global_mode=True)
    hotels = search_hotels('Rome, Lazio, Italy', '2026-11-15',
                           '2026-11-19', 1, global_mode=True)
    assert flights['status'] == hotels['status'] == 'unavailable'
    assert flights['options'] == hotels['options'] == []
    assert hotels['nights'] == 4
    assert flights['bookable'] is hotels['bookable'] is False
