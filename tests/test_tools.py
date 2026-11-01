from travel_core.tools import estimate_budget, search_flights, search_hotels, suggest_activities
from travel_core import tools


def test_itinerary_changes_with_interests_and_avoids_tagged_popular_spots():
    cultural = suggest_activities('New York City', 5, interests='culture')
    outdoors = suggest_activities('New York City', 5, interests='outdoors')
    assert cultural['status'] == outdoors['status'] == 'ok'
    assert [item['activity']['name'] for item in cultural['itinerary']] != [
        item['activity']['name'] for item in outdoors['itinerary']]
    assert all(item['activity']['interest'] == 'culture' for item in cultural['itinerary'])
    assert all(item['activity']['interest'] == 'outdoors' for item in outdoors['itinerary'])
    filtered = suggest_activities('New York City', 5, avoid_popular_spots=True)
    assert all(not item['activity'].get('popular_spot', False) for item in filtered['itinerary'])


def test_sample_flights_return_explicit_mock_metadata():
    result = search_flights("Chicago", "New York", "2026-11-15", "2026-11-19", travelers=2)
    assert result["status"] == "ok"
    assert result["live_availability_checked"] is False
    assert result["bookable"] is False
    assert result["options"][0]["total_round_trip_usd"] == 660.0


def test_flight_invalid_dates_rejected():
    assert search_flights("ORD", "JFK", "2026-12-12", "2026-12-10")["status"] == "invalid_request"


def test_unknown_route_is_not_fabricated():
    assert search_flights("LAX", "CDG", "2026-11-15", "2026-11-19")["status"] == "unsupported_route"


def test_hotels_multiply_nights_and_rooms():
    result = search_hotels("JFK", "2026-11-15", "2026-11-19", rooms=2)
    assert result["nights"] == 4
    assert result["options"][0]["total_room_cost_usd"] == 1280.0


def test_activity_cost_is_additive():
    result = suggest_activities("New York", days=3, interests="culture,food")
    assert result["status"] == "ok"
    assert len(result["itinerary"]) == 3
    assert result["estimated_activities_usd_per_person"] == 70.0


def test_budget_totals_are_deterministic():
    result = estimate_budget("DEMO-F001", "DEMO-H001", nights=4, travelers=2, rooms=1,
                             activities_per_person_usd=70, budget_limit_usd=2000)
    assert result["status"] == "ok"
    # flights 660 + hotel 640 + food 450 + transport 100 + activities 140 = 1990
    assert result["estimated_total_usd"] == 1990.0
    assert result["within_budget"] is True
    assert result["remaining_usd"] == 10.0


def test_budget_rejects_inconsistent_options():
    assert estimate_budget("DEMO-F001", "DEMO-H005", nights=2)["status"] == "invalid_selection"


def test_negative_and_excessive_inputs_rejected():
    assert estimate_budget("DEMO-F001", "DEMO-H001", nights=-1)["status"] == "invalid_request"
    assert suggest_activities("Tokyo", days=31)["status"] == "invalid_request"


def test_empty_provider_results_are_explicit(monkeypatch):
    monkeypatch.setattr(tools, 'FLIGHTS', [])
    flights = search_flights('Chicago', 'New York City', '2026-11-15', '2026-11-19', 2)
    assert flights['status'] == 'no_results'
    assert flights['options'] == []
    assert flights['source'] == 'SYNTHETIC_DEMO'

    monkeypatch.setattr(tools, 'HOTELS', [])
    hotels = search_hotels('New York City', '2026-11-15', '2026-11-19', 1)
    assert hotels['status'] == 'no_results'
    assert hotels['options'] == []
    assert hotels['bookable'] is False


def test_empty_activity_catalog_does_not_crash(monkeypatch):
    monkeypatch.setattr(tools, 'ACTIVITIES', {'New York City': []})
    result = suggest_activities('New York City', 5)
    assert result['status'] == 'no_results'
    assert result['itinerary'] == []
