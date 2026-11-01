"""Exercise Streamlit modes without making a model request."""

from datetime import date
import json
from pathlib import Path
from inspect import signature
from unittest.mock import create_autospec

from streamlit.testing.v1 import AppTest


APP = Path(__file__).resolve().parents[1] / 'app.py'


def fill_trip(app):
    app.date_input[0].set_value(date(2026, 11, 15))
    app.date_input[1].set_value(date(2026, 11, 19))
    app.form_submit_button[0].click().run()


def test_demo_mode_renders_budget_replanning_without_ollama():
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    app.radio[0].set_value('Offline Demo').run()
    fill_trip(app)
    assert not app.exception
    mode, result = app.session_state['execution']
    assert mode == 'offline'
    assert result['budget']['estimated_total_usd'] == 1990
    assert result['replanning']['triggered'] is True
    metrics = {item.label: item.value for item in app.metric}
    assert metrics['Estimated total'] == '$1,990.00'
    assert metrics['Estimated savings'] == '$280.00'
    assert not any('Developer Diagnostics' in item.label for item in app.expander)


def test_ai_mode_displays_failure_without_claiming_completion(monkeypatch):
    from travel_planner.runner import WorkflowRunError

    async def failed_run(request, timeout_seconds, on_progress=None):
        raise WorkflowRunError('Local AI run exceeded 180 seconds.',
                               [{'agent': 'flight_agent', 'event': 'tool_call',
                                 'tool': 'search_flights', 'details': '{}'}],
                               {'flight_agent': 180.0})

    monkeypatch.setattr('travel_planner.runner.run_adk_trip', failed_run)
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    fill_trip(app)
    assert not app.exception
    mode, result = app.session_state['execution']
    assert mode == 'error'
    assert result['trace'][0]['tool'] == 'search_flights'
    assert app.error
    assert 'took too long' in app.error[0].value
    assert not app.code


def test_python_error_is_only_in_diagnostics(monkeypatch):
    async def broken_runner(request, timeout_seconds, on_progress=None):
        raise TypeError("run_adk_trip() got an unexpected keyword argument 'on_progress'")

    monkeypatch.setattr('travel_planner.runner.run_adk_trip', broken_runner)
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    fill_trip(app)
    assert not app.exception
    assert app.session_state['execution'][0] == 'error'
    assert 'TypeError' not in app.error[0].value
    assert 'Restart Streamlit' in app.error[0].value
    assert not app.code
    app.toggle[0].set_value(True).run()
    assert any('TypeError' in item.value for item in app.code)


def test_ai_mode_renders_observed_plan_and_options(monkeypatch):
    from travel_core.tools import search_flights, search_hotels
    from travel_planner.runner import run_adk_trip

    saved = json.loads((APP.parent / 'docs' / 'optimized-ai-run.json').read_text())
    saved['available_flights'] = search_flights('Chicago', 'New York City',
                                                 '2026-11-15', '2026-11-19', 2)['options']
    saved['available_hotels'] = search_hotels('New York City',
                                              '2026-11-15', '2026-11-19', 1)['options']

    async def completed_run(request, timeout_seconds, on_progress=None):
        assert signature(run_adk_trip).bind(
            request, timeout_seconds=timeout_seconds, on_progress=on_progress)
        assert request.departure_date == date(2026, 11, 15)
        assert request.return_date == date(2026, 11, 19)
        assert request.origin == 'Chicago'
        assert request.destination == 'New York City'
        assert request.travelers == 2 and request.rooms == 1
        assert request.budget_limit_usd == 2000
        assert request.interests == 'culture,food'
        assert request.global_mode is False
        return saved

    strict_runner = create_autospec(run_adk_trip, side_effect=completed_run)
    monkeypatch.setattr('travel_planner.runner.run_adk_trip', strict_runner)
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    fill_trip(app)
    assert not app.exception
    assert app.session_state['execution'][0] == 'adk'
    metrics = {item.label: item.value for item in app.metric}
    assert metrics['Estimated total'] == '$1,990.00'
    assert metrics['Estimated savings'] == '$280.00'
    assert any('Compare simulated travel options' in item.label for item in app.expander)
    assert strict_runner.await_count == 1
    assert callable(strict_runner.call_args.kwargs['on_progress'])


def test_ai_mode_accepts_older_runner_without_progress_parameter(monkeypatch):
    saved = json.loads((APP.parent / 'docs' / 'optimized-ai-run.json').read_text())

    async def legacy_run(request, timeout_seconds):
        assert request.travelers == 2
        assert timeout_seconds == 180
        return saved

    monkeypatch.setattr('travel_planner.runner.run_adk_trip', legacy_run)
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    fill_trip(app)
    assert not app.exception
    assert app.session_state['execution'][0] == 'adk'


def test_progress_display_failure_does_not_discard_runner_result(monkeypatch):
    saved = json.loads((APP.parent / 'docs' / 'optimized-ai-run.json').read_text())

    async def completed_run(request, timeout_seconds, on_progress):
        on_progress({})  # A malformed cosmetic event must not change the AI result.
        return saved

    monkeypatch.setattr('travel_planner.runner.run_adk_trip', completed_run)
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    fill_trip(app)
    assert not app.exception
    kind, result = app.session_state['execution']
    assert kind == 'adk'
    assert result['progress_errors'][0].startswith('KeyError:')
    assert not app.error


def test_global_city_flow_keeps_unpriced_items_explicit(monkeypatch):
    from travel_core.geo import Attraction, ResolvedLocation
    from travel_core.global_planner import build_global_itinerary, partial_budget

    chicago = ResolvedLocation(id=1, name='Chicago', region='Illinois',
                               country='United States', latitude=41.88, longitude=-87.63)
    rome = ResolvedLocation(id=2, name='Rome', region='Lazio',
                            country='Italy', latitude=41.9, longitude=12.5)
    monkeypatch.setattr('travel_core.geo.search_cities',
                        lambda name: [rome] if name == 'Rome' else [chicago])
    place = Attraction(id='node/1', name='Museum A', category='museum',
                       latitude=41.91, longitude=12.51).model_dump()

    async def completed_run(request, timeout_seconds, on_progress=None):
        assert request.global_mode is True
        assert request.destination_location.id == 2
        itinerary = build_global_itinerary([place], ['node/1'], 5)
        budget = partial_budget(days=5, nights=4, travelers=2, rooms=1,
                                food_per_person_per_day_usd=45, transport_per_day_usd=20,
                                budget_limit_usd=2000, flight_allowance_usd=None,
                                hotel_allowance_usd=None)
        return {'structured_plan': {
            'request': request.model_dump(mode='json'), 'flight': None, 'hotel': None,
            'itinerary': itinerary['itinerary'], 'budget': budget, 'original_plan': None,
            'replanning': {'triggered': False}},
            'trace': [], 'model_metrics': [], 'tool_metrics': []}

    monkeypatch.setattr('travel_planner.runner.run_adk_trip', completed_run)
    app = AppTest.from_file(str(APP), default_timeout=20).run()
    app.text_input[1].set_value('Rome').run()
    app.button[0].click().run()
    fill_trip(app)
    assert not app.exception
    assert app.session_state['execution'][0] == 'adk'
    assert any(item.label == 'Known subtotal' for item in app.metric)
    assert any('partial USD estimate' in item.value for item in app.info)
