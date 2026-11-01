"""Grounded global itinerary and partial budget helpers."""

from math import asin, cos, radians, sin, sqrt

from .geo import Attraction


SLOTS = ('morning', 'afternoon', 'evening')


def _distance_km(first: Attraction, second: Attraction) -> float:
    dlat = radians(second.latitude - first.latitude)
    dlon = radians(second.longitude - first.longitude)
    a = sin(dlat / 2) ** 2 + cos(radians(first.latitude)) * cos(
        radians(second.latitude)) * sin(dlon / 2) ** 2
    return 6371 * 2 * asin(sqrt(a))


def build_global_itinerary(candidates: list[dict], selected_ids: list[str], days: int,
                           pace: str = 'Balanced') -> dict:
    """Place model-selected verified IDs on days, filling remaining slots safely."""
    if not 1 <= days <= 14:
        return {'status': 'invalid_request', 'message': 'Trip must span 1–14 calendar days.'}
    pace = pace if pace in {'Relaxed', 'Balanced', 'Adventurous'} else 'Balanced'
    places = [Attraction.model_validate(item) for item in candidates]
    if not places:
        return {'status': 'no_results', 'message': 'No verified attractions were returned for this city.'}
    by_id = {place.id: place for place in places}
    chosen = []
    for item_id in selected_ids:
        if item_id in by_id and item_id not in chosen:
            chosen.append(item_id)
    chosen += [place.id for place in places if place.id not in chosen]
    remaining = [by_id[item_id] for item_id in chosen]
    itinerary = []
    scheduled_ids = []
    previous = None
    for day in range(1, days + 1):
        edge = day in {1, days}
        density = (1 if edge else 2) if pace == 'Relaxed' else (2 if edge else 3)
        slots = []
        for index, slot in enumerate(SLOTS):
            if index < density and remaining:
                # The model supplies preference order; short local jumps break ties.
                window = remaining[:min(6, len(remaining))]
                place = (min(window, key=lambda item: _distance_km(previous, item))
                         if previous else window[0])
                remaining.remove(place)
                scheduled_ids.append(place.id)
                previous = place
                slots.append({'period': slot, 'title': place.name, 'category': place.category,
                              'latitude': place.latitude, 'longitude': place.longitude,
                              'duration_minutes': 90 if slot != 'evening' else 60,
                              'description': place.description,
                              'source': place.source, 'verified_place': True,
                              'estimated_admission_usd': None})
            else:
                slots.append({'period': slot, 'title': 'Flexible time or a nearby meal',
                              'category': 'general_suggestion', 'latitude': None,
                              'longitude': None, 'duration_minutes': 60,
                              'description': 'Choose a place locally; no venue or price is verified.',
                              'source': 'GENERAL_SUGGESTION', 'verified_place': False,
                              'estimated_admission_usd': None})
        itinerary.append({'day': day, 'slots': slots})
    return {'status': 'ok', 'source': 'OPENSTREETMAP_OVERPASS', 'pace': pace,
            'itinerary': itinerary, 'selected_attraction_ids': scheduled_ids,
            'estimated_activities_usd_per_person': None,
            'note': 'Durations are planning allowances. Opening hours, admission, and crowds are unknown.'}


def partial_budget(*, days: int, nights: int, travelers: int, rooms: int,
                   food_per_person_per_day_usd: float,
                   transport_per_day_usd: float, budget_limit_usd: float,
                   flight_allowance_usd: float | None, hotel_allowance_usd: float | None) -> dict:
    """Never treat missing travel or admission prices as zero."""
    food = round(days * travelers * food_per_person_per_day_usd, 2)
    transport = round(days * transport_per_day_usd, 2)
    breakdown = {'food_usd': food, 'ground_transport_usd': transport,
                 'flights_usd': flight_allowance_usd, 'hotel_usd': hotel_allowance_usd,
                 'admission_usd': None}
    subtotal = round(sum(value for value in breakdown.values() if value is not None), 2)
    missing = [name for name, value in breakdown.items() if value is None]
    return {'status': 'partial', 'currency': 'USD', 'days': days, 'nights': nights,
            'travelers': travelers, 'rooms': rooms, 'breakdown': breakdown,
            'known_subtotal_usd': subtotal, 'estimated_total_usd': None,
            'budget_limit_usd': budget_limit_usd, 'remaining_usd': None,
            'within_budget': None, 'missing_costs': missing,
            'note': 'User allowances are estimates; unknown admission costs prevent a complete total.'}
