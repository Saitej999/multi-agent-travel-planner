"""Grounding and arithmetic for the optional global planning path."""

from travel_core.geo import Attraction, ResolvedLocation
from datetime import date

from travel_core.global_planner import build_global_itinerary, partial_budget, validate_global_itinerary
from travel_core.tools import search_flights, search_hotels


def test_global_itinerary_uses_verified_places_once_and_actual_days():
    places = [Attraction(id=f'node/{i}', name=f'Place {i}', category='museum',
                         latitude=41.9 + i * .001, longitude=12.5).model_dump()
              for i in range(10)]
    result = build_global_itinerary(places, ['node/3', 'invented'], 5, 'Relaxed',
                                    start_date='2026-12-06', destination='Rome')
    assert result['status'] == 'ok'
    assert len(result['itinerary']) == 5
    assert [len(day['slots']) for day in result['itinerary']] == [1, 2, 2, 2, 1]
    assert [day['date'] for day in result['itinerary']] == [
        f'2026-12-{day:02d}' for day in range(6, 11)]
    assert [slot['period'] for slot in result['itinerary'][0]['slots']
            if slot['verified_place']] == ['afternoon']
    assert [slot['period'] for slot in result['itinerary'][-1]['slots']
            if slot['verified_place']] == ['morning']
    assert result['selected_attraction_ids'][0] == 'node/3'
    assert len(set(result['selected_attraction_ids'])) == len(result['selected_attraction_ids'])
    assert all(slot['verified_place'] and slot['attraction_id'] and slot['source']
               for day in result['itinerary'] for slot in day['slots'])
    assert validate_global_itinerary(result, candidates=places, destination='Rome',
                                     departure_date=date(2026, 12, 6), days=5,
                                     destination_latitude=41.9,
                                     destination_longitude=12.5)['status'] == 'ok'


def test_global_itinerary_without_verified_places_is_explicitly_partial():
    result = build_global_itinerary([], [], 8, 'Relaxed')
    assert result['status'] == 'insufficient_data'
    assert len(result['itinerary']) == 8
    assert result['selected_attraction_ids'] == []
    assert all(not day['slots'] for day in result['itinerary'])


def test_global_itinerary_rejects_unverified_venue_or_wrong_date():
    places = [Attraction(id='osm:node/1', name='Museum', category='museum',
                         latitude=41.9, longitude=12.5).model_dump()]
    result = build_global_itinerary(places, [], 2, start_date='2026-12-06', destination='Rome')
    result['itinerary'][0]['slots'][0]['latitude'] = 0
    result['itinerary'][0]['date'] = '2026-12-07'
    quality = validate_global_itinerary(result, candidates=places, destination='Rome',
                                         departure_date=date(2026, 12, 6), days=2,
                                         destination_latitude=41.9, destination_longitude=12.5)
    assert quality['status'] == 'invalid_result'
    assert {'date_mismatch', 'invalid_attraction_provenance'} <= set(quality['issues'])


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
