from travel_core.planner import plan_trip
from travel_core.schemas import TripRequest
from travel_core.tools import suggest_activities


SAMPLE = {
    'origin': 'Chicago', 'destination': 'New York',
    'departure_date': '2026-11-15', 'return_date': '2026-11-19',
    'travelers': 2, 'rooms': 1,
    'interests': 'culture,food', 'budget_limit_usd': 2_000,
}


def test_schema_accepts_complete_trip():
    assert TripRequest(**SAMPLE).travelers == 2


def test_missing_essentials_are_rejected():
    for field in ('departure_date', 'return_date', 'destination'):
        result = plan_trip({key: value for key, value in SAMPLE.items() if key != field})
        assert result['status'] == 'invalid_request'


def test_successful_budget_revision_changes_options_not_arithmetic():
    result = plan_trip(SAMPLE)
    assert result['status'] == 'ok'
    assert result['execution_mode'] == 'OFFLINE_PYTHON_NOT_AI_AGENTS'
    assert result['replanning']['triggered'] is True
    assert result['replanning']['outcome'] == 'replanned_within_budget'
    assert result['initial_budget']['estimated_total_usd'] > 2_000
    assert result['budget']['within_budget'] is True
    assert result['budget']['estimated_total_usd'] <= 2_000
    assert result['budget']['flight_option_id'] == result['flight']['id']
    assert result['budget']['hotel_option_id'] == result['hotel']['id']


def test_generous_budget_keeps_initial_plan():
    result = plan_trip(dict(SAMPLE, budget_limit_usd=5_000))
    assert result['replanning']['triggered'] is False
    assert result['budget']['estimated_total_usd'] == result['initial_budget']['estimated_total_usd']


def test_unachievable_budget_is_reported_and_does_not_claim_success():
    result = plan_trip(dict(SAMPLE, budget_limit_usd=300))
    assert result['status'] == 'ok'
    assert result['replanning']['outcome'] == 'no_plan_within_budget'
    assert result['budget']['within_budget'] is False
    assert result['budget']['remaining_usd'] < 0


def test_synthetic_free_itinerary_only_selects_zero_cost_activities():
    itinerary = suggest_activities('New York', 5, 'culture,food', free_only=True)
    assert itinerary['status'] == 'ok'
    assert itinerary['estimated_activities_usd_per_person'] == 0
    assert all(a['activity']['estimated_usd_per_person'] == 0 for a in itinerary['itinerary'])


def test_invalid_long_trip_is_rejected():
    result = plan_trip(dict(SAMPLE, return_date='2026-12-30'))
    assert result['status'] == 'invalid_request'


def test_unsupported_city_does_not_generate_fictional_offers():
    result = plan_trip(dict(SAMPLE, destination='Paris'))
    assert result['status'] == 'unsupported_request'


def test_map_points_available_for_all_sample_activity_days():
    result = plan_trip(SAMPLE)
    for day in result['itinerary']['itinerary']:
        assert -90 <= day['activity']['latitude'] <= 90
        assert -180 <= day['activity']['longitude'] <= 180


def test_selected_options_match_original_provider_ids():
    result = plan_trip(dict(SAMPLE, budget_limit_usd=1750))
    assert result['flight']['id'] in [f['id'] for f in result['flights']['options']]
    assert result['hotel']['id'] in [h['id'] for h in result['hotels']['options']]
    assert result['budget']['estimated_total_usd'] == sum(result['budget']['breakdown'].values())
