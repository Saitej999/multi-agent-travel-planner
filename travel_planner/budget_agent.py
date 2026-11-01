"""Deterministic ADK budget specialist driven by verified session state."""

import json
from time import perf_counter
from typing import AsyncGenerator

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from google.genai import types

from travel_core.replanning import choose_revised_plan
from travel_core.global_planner import partial_budget
from travel_core.schemas import TripRequest
from travel_core.tools import estimate_budget


def budget_inputs_from_state(state: dict) -> dict:
    """Build budget arguments only from validated request and prior tool outputs."""
    if state.get('workflow_error'):
        raise ValueError(f"Upstream specialist failed: {state['workflow_error']}")
    required = ('trip_request', 'flight_search', 'selected_flight', 'hotel_search',
                'selected_hotel', 'hotel_nights', 'itinerary_result', 'activities_per_person_usd')
    missing = [key for key in required if state.get(key) is None]
    if missing:
        raise ValueError('Missing upstream results: ' + ', '.join(missing))
    request = TripRequest.model_validate(state['trip_request'])
    flight = state['selected_flight']
    hotel = state['selected_hotel']
    if flight['id'] not in {option['id'] for option in state['flight_search']['options']}:
        raise ValueError('Selected flight ID was not returned by search_flights')
    if hotel['id'] not in {option['id'] for option in state['hotel_search']['options']}:
        raise ValueError('Selected hotel ID was not returned by search_hotels')
    nights = (request.return_date - request.departure_date).days
    if state['hotel_nights'] != nights:
        raise ValueError('Hotel night count does not match trip dates')
    activity_cost = state['itinerary_result']['estimated_activities_usd_per_person']
    if state['activities_per_person_usd'] != activity_cost:
        raise ValueError('Activity cost does not match itinerary tool output')
    return {
        'flight_option_id': flight['id'], 'hotel_option_id': hotel['id'],
        'nights': nights, 'travelers': request.travelers, 'rooms': request.rooms,
        'food_per_person_per_day_usd': request.food_per_person_per_day_usd,
        'transport_per_day_usd': request.transport_per_day_usd,
        'activities_per_person_usd': activity_cost,
        'budget_limit_usd': request.budget_limit_usd,
    }


def coordinator_facts(plan: dict) -> dict:
    """Give the final LLM only the facts needed for its short explanation."""
    request = plan['request']
    flight, hotel, budget = plan['flight'], plan['hotel'], plan['budget']
    original = plan['original_plan']
    replanning = plan['replanning']
    return {
        'trip': {key: request[key] for key in (
            'origin', 'destination', 'departure_date', 'return_date', 'travelers',
            'rooms', 'budget_limit_usd', 'interests', 'preferences')},
        'selected_flight': {'id': flight['id'], 'airline': flight['airline'],
                            'stops': flight['stops'],
                            'group_round_trip_usd': budget['breakdown']['round_trip_flights_usd']},
        'selected_hotel': {'id': hotel['id'], 'name': hotel['name'],
                           'nights': budget['nights'],
                           'room_total_usd': budget['breakdown']['hotel_room_total_usd']},
        'daily_activities': [
            {'day': item['day'], 'name': item['activity']['name']}
            for item in plan['itinerary']
        ],
        'costs_usd': budget['breakdown'],
        'original': {'flight_id': original['flight']['id'],
                     'hotel_id': original['hotel']['id'],
                     'total_usd': original['budget']['estimated_total_usd']},
        'final': {'total_usd': budget['estimated_total_usd'],
                  'remaining_usd': budget['remaining_usd'],
                  'within_budget': budget['within_budget']},
        'amount_saved_usd': replanning['amount_saved_usd'],
        'replanning_explanation': replanning['explanation'],
        'simulated_non_bookable': True,
    }


class BudgetAgent(BaseAgent):
    """Calculate the initial budget and make at most one optimization pass."""

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        if (ctx.session.state.get('trip_request') or {}).get('global_mode'):
            async for event in self._run_global(ctx):
                yield event
            return
        try:
            kwargs = budget_inputs_from_state(ctx.session.state)
        except (ValueError, KeyError, TypeError) as exc:
            result = {'status': 'missing_inputs', 'message': str(exc)}
            yield Event(invocation_id=ctx.invocation_id, author=self.name,
                        content=types.Content(role='model', parts=[types.Part(text=json.dumps(result))]),
                        actions=EventActions(state_delta={'workflow_error': result['message'],
                                                          'budget_result': result}))
            return

        yield Event(invocation_id=ctx.invocation_id, author=self.name,
                    content=types.Content(role='model',
                                          parts=[types.Part.from_function_call(name='estimate_budget', args=kwargs)]))
        started = perf_counter()
        result = estimate_budget(**kwargs)
        tool_metrics = list(ctx.session.state.get('tool_metrics') or [])
        tool_metrics.append({'tool': 'estimate_budget', 'status': result['status'],
                             'duration_seconds': round(perf_counter() - started, 4),
                             'calls': 1, 'source': 'initial_budget'})
        updates = {'budget_result': result, 'initial_budget_result': result,
                   'tool_metrics': tool_metrics}
        if result['status'] != 'ok':
            updates['workflow_error'] = result.get('message', 'Budget calculation failed')
        else:
            original = {
                'flight': ctx.session.state['selected_flight'],
                'hotel': ctx.session.state['selected_hotel'],
                'itinerary': ctx.session.state['itinerary_result'],
                'budget': result,
                'budget_difference_usd': result['remaining_usd'],
            }
            updates['original_plan'] = original
            updates['replanning'] = {
                'triggered': False, 'outcome': 'initial_plan_fits',
                'evaluated_alternatives': 0, 'amount_saved_usd': 0.0,
                'final_within_budget': result['within_budget'],
                'explanation': 'The initial plan fits the requested budget.',
            }
            updates['plan_facts'] = {
                'request': ctx.session.state['trip_request'],
                'flight': original['flight'], 'hotel': original['hotel'],
                'itinerary': original['itinerary']['itinerary'],
                'budget': result, 'original_plan': original,
                'revised_plan': None, 'replanning': updates['replanning'],
                'source': 'SYNTHETIC_DEMO',
            }
            updates['coordinator_facts'] = coordinator_facts(updates['plan_facts'])
        yield Event(invocation_id=ctx.invocation_id, author=self.name,
                    content=types.Content(role='user', parts=[types.Part.from_function_response(
                        name='estimate_budget', response=result)]),
                    actions=EventActions(state_delta=updates))
        if result['status'] != 'ok' or result['within_budget']:
            return

        try:
            optimization_started = perf_counter()
            selection = choose_revised_plan(ctx.session.state, kwargs)
            optimization_seconds = round(perf_counter() - optimization_started, 4)
            revised_args = dict(kwargs, flight_option_id=selection['flight']['id'],
                                hotel_option_id=selection['hotel']['id'],
                                activities_per_person_usd=selection['itinerary']['estimated_activities_usd_per_person'])
        except (ValueError, KeyError, TypeError) as exc:
            message = f'Budget replanning failed: {exc}'
            yield Event(invocation_id=ctx.invocation_id, author=self.name,
                        content=types.Content(role='model', parts=[types.Part(text=message)]),
                        actions=EventActions(state_delta={'workflow_error': message}))
            return

        yield Event(invocation_id=ctx.invocation_id, author=self.name,
                    content=types.Content(role='model', parts=[types.Part.from_function_call(
                        name='estimate_budget', args=revised_args)]))
        started = perf_counter()
        revised_budget = estimate_budget(**revised_args)
        tool_metrics.extend([
            {'tool': 'estimate_budget', 'status': 'ok',
             'duration_seconds': optimization_seconds,
             'calls': selection['evaluated_alternatives'], 'source': 'optimization_pass'},
            {'tool': 'estimate_budget', 'status': revised_budget['status'],
             'duration_seconds': round(perf_counter() - started, 4),
             'calls': 1, 'source': 'revised_budget'},
        ])
        if revised_budget['status'] != 'ok':
            message = revised_budget.get('message', 'Revised budget calculation failed')
            yield Event(invocation_id=ctx.invocation_id, author=self.name,
                        content=types.Content(role='user', parts=[types.Part.from_function_response(
                            name='estimate_budget', response=revised_budget)]),
                        actions=EventActions(state_delta={'workflow_error': message}))
            return
        original = updates['original_plan']
        revised = {'flight': selection['flight'], 'hotel': selection['hotel'],
                   'itinerary': selection['itinerary'], 'budget': revised_budget,
                   'budget_difference_usd': revised_budget['remaining_usd']}
        saved = round(result['estimated_total_usd'] - revised_budget['estimated_total_usd'], 2)
        flight_changed = original['flight']['id'] != revised['flight']['id']
        hotel_changed = original['hotel']['id'] != revised['hotel']['id']
        activities_changed = original['itinerary']['free_only'] != revised['itinerary']['free_only']
        changes = [name for name, changed in [('flight', flight_changed), ('hotel', hotel_changed),
                                               ('activities', activities_changed)] if changed]
        explanation = ('Changed ' + ', '.join(changes) + ' using returned specialist options.'
                       if changes else 'The lowest-cost valid plan matches the initial selections.')
        if not revised_budget['within_budget']:
            explanation += f" No valid combination meets the limit; shortfall is ${-revised_budget['remaining_usd']:,.2f}."
        replanning = {'triggered': True, 'outcome': selection['outcome'],
                      'evaluated_alternatives': selection['evaluated_alternatives'],
                      'source_results': selection['source_results'],
                      'initial_total_usd': result['estimated_total_usd'],
                      'revised_total_usd': revised_budget['estimated_total_usd'],
                      'amount_saved_usd': saved,
                      'final_within_budget': revised_budget['within_budget'],
                      'explanation': explanation}
        final_updates = {'selected_flight': selection['flight'], 'selected_hotel': selection['hotel'],
                         'activities_per_person_usd': revised_args['activities_per_person_usd'],
                         'budget_result': revised_budget, 'revised_plan': revised,
                         'tool_metrics': tool_metrics,
                         'replanning': replanning,
                         'plan_facts': {'request': ctx.session.state['trip_request'],
                                        'flight': revised['flight'], 'hotel': revised['hotel'],
                                        'itinerary': revised['itinerary']['itinerary'],
                                        'budget': revised_budget, 'original_plan': original,
                                        'revised_plan': revised, 'replanning': replanning,
                                        'source': 'SYNTHETIC_DEMO'}}
        final_updates['coordinator_facts'] = coordinator_facts(final_updates['plan_facts'])
        yield Event(invocation_id=ctx.invocation_id, author=self.name,
                    content=types.Content(role='user', parts=[types.Part.from_function_response(
                        name='estimate_budget', response=revised_budget)]),
                    actions=EventActions(state_delta=final_updates))

    async def _run_global(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        """Compute only the priced portion of a global trip."""
        state = ctx.session.state
        try:
            if state.get('workflow_error'):
                raise ValueError(state['workflow_error'])
            request = TripRequest.model_validate(state['trip_request'])
            if state['flight_search']['status'] != 'unavailable' or state['hotel_search']['status'] != 'unavailable':
                raise ValueError('Global flight and hotel availability state is missing')
            itinerary = state['itinerary_result']
            days = (request.return_date - request.departure_date).days + 1
            if itinerary['status'] != 'ok' or len(itinerary['itinerary']) != days:
                raise ValueError('Verified attraction itinerary does not match trip dates')
            kwargs = {'days': days, 'nights': days - 1, 'travelers': request.travelers,
                      'rooms': request.rooms,
                      'food_per_person_per_day_usd': request.food_per_person_per_day_usd,
                      'transport_per_day_usd': request.transport_per_day_usd,
                      'budget_limit_usd': request.budget_limit_usd,
                      'flight_allowance_usd': request.flight_allowance_usd,
                      'hotel_allowance_usd': request.hotel_allowance_usd}
        except (KeyError, TypeError, ValueError) as exc:
            message = f'Global budget inputs are incomplete: {exc}'
            yield Event(invocation_id=ctx.invocation_id, author=self.name,
                        content=types.Content(role='model', parts=[types.Part(text=message)]),
                        actions=EventActions(state_delta={'workflow_error': message}))
            return
        yield Event(invocation_id=ctx.invocation_id, author=self.name,
                    content=types.Content(role='model', parts=[types.Part.from_function_call(
                        name='partial_budget', args=kwargs)]))
        started = perf_counter()
        budget = partial_budget(**kwargs)
        metrics = list(state.get('tool_metrics') or [])
        metrics.append({'tool': 'partial_budget', 'status': 'partial', 'calls': 1,
                        'duration_seconds': round(perf_counter() - started, 4)})
        plan = {'request': state['trip_request'], 'flight': None, 'hotel': None,
                'itinerary': itinerary['itinerary'], 'budget': budget,
                'original_plan': None, 'revised_plan': None,
                'replanning': {'triggered': False, 'outcome': 'no_verified_price_alternatives'},
                'source': 'OPENSTREETMAP_OVERPASS'}
        brief = {'mode': 'global', 'trip': {key: state['trip_request'][key] for key in (
            'origin', 'destination', 'departure_date', 'return_date', 'travelers',
            'rooms', 'budget_limit_usd', 'interests', 'preferences', 'travel_pace')},
                 'days': [{'day': item['day'], 'places': [slot['title'] for slot in item['slots']
                           if slot['verified_place']]} for item in itinerary['itinerary']],
                 'budget': budget, 'flight_pricing': state['flight_search']['price_status'],
                 'hotel_pricing': state['hotel_search']['price_status']}
        yield Event(invocation_id=ctx.invocation_id, author=self.name,
                    content=types.Content(role='user', parts=[types.Part.from_function_response(
                        name='partial_budget', response=budget)]),
                    actions=EventActions(state_delta={
                        'budget_result': budget, 'initial_budget_result': budget,
                        'plan_facts': plan, 'coordinator_facts': brief, 'tool_metrics': metrics}))
