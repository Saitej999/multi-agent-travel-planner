"""One-pass, catalog-grounded budget optimization for the ADK workflow."""

from itertools import product

from .tools import estimate_budget


def choose_revised_plan(state: dict, budget_args: dict) -> dict:
    """Evaluate only options returned by specialists and choose one valid plan.

    Prefer an affordable plan with fewer changes to the initial selections.
    Flight changes cost one point, hotel changes two, and a free-only itinerary
    four. Within the same score, retain the higher-cost plan. If nothing fits,
    return the cheapest valid combination and its shortfall.
    """
    flights = state['flight_search']['options']
    hotels = state['hotel_search']['options']
    itineraries = [state['itinerary_result']]
    free = state.get('free_itinerary_result')
    if free and free.get('status') == 'ok' and free.get('free_only') is True:
        itineraries.append(free)

    candidates = []
    for flight, hotel, itinerary in product(flights, hotels, itineraries):
        args = dict(budget_args, flight_option_id=flight['id'], hotel_option_id=hotel['id'],
                    activities_per_person_usd=itinerary['estimated_activities_usd_per_person'])
        budget = estimate_budget(**args)
        if budget['status'] != 'ok':
            continue
        changes = (int(flight['id'] != state['selected_flight']['id'])
                   + 2 * int(hotel['id'] != state['selected_hotel']['id'])
                   + 4 * int(itinerary.get('free_only', False)))
        candidates.append((changes, budget, flight, hotel, itinerary))
    if not candidates:
        raise ValueError('No valid flight, hotel, and itinerary combination was returned')

    affordable = [item for item in candidates if item[1]['within_budget']]
    if affordable:
        winner = min(affordable, key=lambda item: (item[0], -item[1]['estimated_total_usd'],
                                                    item[2]['id'], item[3]['id']))
        outcome = 'replanned_within_budget'
    else:
        winner = min(candidates, key=lambda item: (item[1]['estimated_total_usd'], item[0],
                                                   item[2]['id'], item[3]['id']))
        outcome = 'no_plan_within_budget'
    _, _, flight, hotel, itinerary = winner
    return {'flight': flight, 'hotel': hotel, 'itinerary': itinerary,
            'outcome': outcome, 'evaluated_alternatives': len(candidates),
            'source_results': ['flight_search', 'hotel_search', 'itinerary_result']
                              + (['free_itinerary_result'] if free else [])}
