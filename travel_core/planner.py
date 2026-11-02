"""Deterministic, runnable offline travel workflow.

IMPORTANT: These steps imitate the *roles* of specialist agents for teaching
purposes. They are NOT calls to LLM agents. Actual Google ADK AgentTool
orchestration lives in travel_planner/agent.py (requires a configured Gemini key).
"""

from itertools import product

from pydantic import ValidationError

from .schemas import TripRequest
from .tools import estimate_budget, search_flights, search_hotels, suggest_activities


def plan_trip(trip: TripRequest | dict) -> dict:
    """Plan a trip from synthetic fixtures, revising the options if over budget."""
    try:
        request = trip if isinstance(trip, TripRequest) else TripRequest.model_validate(trip)
    except ValidationError as exc:
        return {'status': 'invalid_request', 'errors': [error['msg'] for error in exc.errors()]}

    nights = (request.return_date - request.departure_date).days
    days = nights + 1
    start = request.departure_date.isoformat()
    end = request.return_date.isoformat()
    trace = []

    flights = search_flights(request.origin, request.destination, start, end, request.travelers)
    trace.append({'stage': 'Flight search', 'action': 'Called search_flights', 'status': flights['status']})
    hotels = search_hotels(request.destination, start, end, request.rooms)
    trace.append({'stage': 'Hotel search', 'action': 'Called search_hotels', 'status': hotels['status']})
    activities = suggest_activities(request.destination, days=days, interests=request.interests)
    trace.append({'stage': 'Itinerary planning', 'action': 'Called suggest_activities', 'status': activities['status']})

    results = (flights, hotels, activities)
    if any(result['status'] != 'ok' for result in results):
        return {
            'status': 'unsupported_request',
            'message': 'The offline demo only supports Chicago → New York City / San Francisco / Tokyo.',
            'details': [r for r in results if r['status'] != 'ok'],
            'trace': trace,
            'source': 'SYNTHETIC_DEMO',
            'execution_mode': 'OFFLINE_PYTHON_NOT_AI_AGENTS',
        }

    flight_options = flights['options']
    hotel_options = hotels['options']
    # Begin with convenience (fewest stops) and a midrange hotel where available.
    baseline_flight = min(flight_options, key=lambda f: (f['stops'], f['round_trip_usd_per_person']))
    baseline_hotel = next((h for h in hotel_options if h['category'] == 'midrange'), hotel_options[0])
    food = request.food_per_person_per_day_usd
    transport = request.transport_per_day_usd

    def budget_for(flight: dict, hotel: dict, itinerary: dict) -> dict:
        return estimate_budget(
            flight_option_id=flight['id'],
            hotel_option_id=hotel['id'],
            nights=nights, travelers=request.travelers, rooms=request.rooms,
            food_per_person_per_day_usd=food,
            transport_per_day_usd=transport,
            activities_per_person_usd=itinerary['estimated_activities_usd_per_person'],
            budget_limit_usd=request.budget_limit_usd,
        )

    initial_budget = budget_for(baseline_flight, baseline_hotel, activities)
    trace.append({'stage': 'Budget evaluation', 'action': 'Calculated initial plan with estimate_budget',
                  'status': 'within_budget' if initial_budget['within_budget'] else 'over_budget',
                  'estimated_total_usd': initial_budget['estimated_total_usd']})
    selected_flight, selected_hotel, selected_activities = baseline_flight, baseline_hotel, activities
    budget = initial_budget
    replanning = {'triggered': False, 'outcome': 'initial_plan_fits', 'evaluated_alternatives': 0}

    if not initial_budget['within_budget']:
        # The fallback itinerary has zero *synthetic* activity fees; real transit,
        # entry charges, meals etc. still require independent verification.
        free_activities = suggest_activities(request.destination, days=days,
                                            interests=request.interests, free_only=True)
        alternatives = []
        for flight, hotel, itinerary in product(flight_options, hotel_options, [activities, free_activities]):
            candidate_budget = budget_for(flight, hotel, itinerary)
            changes = (int(flight['id'] != baseline_flight['id']) +
                       2 * int(hotel['id'] != baseline_hotel['id']) +
                       4 * int(itinerary['free_only']))
            alternatives.append((changes, candidate_budget, flight, hotel, itinerary))

        affordable = [item for item in alternatives if item[1]['within_budget']]
        if affordable:
            # Prefer fewer changes; among equal-change choices, maximize available comfort budget.
            winner = min(affordable, key=lambda item: (item[0], -item[1]['estimated_total_usd']))
            outcome = 'replanned_within_budget'
        else:
            # Don't falsely claim success: return the cheapest illustration and the shortfall.
            winner = min(alternatives, key=lambda item: item[1]['estimated_total_usd'])
            outcome = 'no_plan_within_budget'
        _, budget, selected_flight, selected_hotel, selected_activities = winner
        replanning = {
            'triggered': True,
            'outcome': outcome,
            'evaluated_alternatives': len(alternatives),
            'initial_total_usd': initial_budget['estimated_total_usd'],
            'revised_total_usd': budget['estimated_total_usd'],
            'changed_flight': selected_flight['id'] != baseline_flight['id'],
            'changed_hotel': selected_hotel['id'] != baseline_hotel['id'],
            'used_free_activities': selected_activities['free_only'],
        }
        trace.append({'stage': 'Budget-aware replanning',
                      'action': f'Evaluated {len(alternatives)} deterministic combinations',
                      'status': outcome, 'estimated_total_usd': budget['estimated_total_usd']})

    return {
        'status': 'ok',
        'execution_mode': 'OFFLINE_PYTHON_NOT_AI_AGENTS',
        'source': 'SYNTHETIC_DEMO',
        'bookable': False,
        'request': request.model_dump(mode='json'),
        'flights': flights,
        'hotels': hotels,
        'flight': selected_flight,
        'hotel': selected_hotel,
        'itinerary': selected_activities,
        'initial_budget': initial_budget,
        'budget': budget,
        'replanning': replanning,
        'trace': trace,
        'limitations': [
            'Fictional flights, hotels and prices; no live inventory or bookings.',
            'Landmark locations are approximate static reference points.',
            'Admission prices, weather, opening hours and transport routes are not verified.',
            'The offline pipeline is Python orchestration, NOT Google ADK agent delegation.',
        ],
    }
