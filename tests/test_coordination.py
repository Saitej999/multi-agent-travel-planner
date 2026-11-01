from types import SimpleNamespace

from travel_planner.coordination import guard_budget_call, record_specialist_result, report_tool_error


def test_budget_waits_for_specialists_and_concrete_ids():
    context = SimpleNamespace(state={})
    budget = SimpleNamespace(name='budget_agent')
    placeholder = guard_budget_call(budget, {'request': 'flight_id and hotel_id'}, context)
    assert placeholder['status'] == 'missing_inputs'
    assert placeholder['missing_specialists'] == [
        'flight_agent', 'hotel_agent', 'itinerary_agent'
    ]

    for name in ('flight_agent', 'hotel_agent', 'itinerary_agent'):
        record_specialist_result(SimpleNamespace(name=name), {}, context, {'result': 'ok'})
    assert guard_budget_call(budget, {'request': 'flight_id and hotel_id'}, context)['status'] == 'missing_inputs'
    assert guard_budget_call(budget, {'request': 'DEMO-F001 DEMO-H001, 4 nights, 2 travelers, 1 room'}, context) is None


def test_non_budget_calls_are_not_blocked():
    context = SimpleNamespace(state={})
    assert guard_budget_call(SimpleNamespace(name='flight_agent'), {}, context) is None


def test_failed_specialist_is_not_counted_as_complete():
    context = SimpleNamespace(state={})
    flight = SimpleNamespace(name='flight_agent')
    failure = report_tool_error(flight, {}, context, RuntimeError('provider failed'))
    assert failure['status'] == 'tool_error'
    assert failure['error_type'] == 'RuntimeError'
    record_specialist_result(flight, {}, context, failure)
    assert context.state == {}
