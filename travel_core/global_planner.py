"""Grounded global itinerary and partial budget helpers."""

from datetime import date, time, timedelta
from math import asin, cos, radians, sin, sqrt

from .geo import Attraction


SLOTS = ('morning', 'afternoon', 'evening')
CATEGORY_INTERESTS = {
    'museum': {'culture', 'history', 'art'}, 'gallery': {'culture', 'art'},
    'historic': {'history', 'culture', 'architecture'},
    'monument': {'history', 'culture', 'sightseeing'},
    'palace': {'history', 'culture', 'architecture'},
    'fort': {'history', 'architecture', 'sightseeing'},
    'temple': {'culture', 'history', 'architecture'},
    'church': {'culture', 'history', 'architecture'},
    'market': {'food', 'culture'},
    'park': {'outdoors', 'nature'}, 'garden': {'outdoors', 'nature'},
    'beach': {'outdoors', 'nature'},
    'viewpoint': {'sightseeing', 'outdoors'},
    'fountain': {'sightseeing', 'architecture'},
    'theatre': {'culture', 'art'},
}
DURATION_MINUTES = {'museum': 120, 'gallery': 90, 'market': 60,
                    'park': 90, 'garden': 75, 'fountain': 30,
                    'monument': 60, 'viewpoint': 45, 'temple': 60,
                    'church': 60}


def _active_periods(day: int, days: int, pace: str,
                    arrival_time: str = '', departure_time: str = '') -> set[str]:
    if day == 1:
        return set() if arrival_time and time.fromisoformat(arrival_time) >= time(13) else {'afternoon'}
    if day == days:
        return set() if departure_time and time.fromisoformat(departure_time) <= time(14) else {'morning'}
    return set(SLOTS) if pace == 'Adventurous' else {'morning', 'afternoon'}


def _same_visit(first: Attraction, second: Attraction) -> bool:
    a, b = first.name.casefold(), second.name.casefold()
    return (len(min(a, b, key=len)) >= 8 and (a in b or b in a)
            and _distance_km(first, second) <= 0.5)


def _distance_km(first: Attraction, second: Attraction) -> float:
    dlat = radians(second.latitude - first.latitude)
    dlon = radians(second.longitude - first.longitude)
    a = sin(dlat / 2) ** 2 + cos(radians(first.latitude)) * cos(
        radians(second.latitude)) * sin(dlon / 2) ** 2
    return 6371 * 2 * asin(sqrt(a))


def _coordinate_distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 6371 * 2 * asin(min(1, sqrt(a)))


def build_global_itinerary(candidates: list[dict], selected_ids: list[str], days: int,
                           pace: str = 'Balanced', interests: str = '',
                           start_date: str = '', destination: str = '',
                           arrival_time: str = '', departure_time: str = '') -> dict:
    """Schedule distinct verified places; leave unsupported periods unscheduled."""
    if not 1 <= days <= 14:
        return {'status': 'invalid_request', 'message': 'Trip must span 1–14 calendar days.'}
    try:
        first_date = date.fromisoformat(start_date) if start_date else None
        if arrival_time:
            time.fromisoformat(arrival_time)
        if departure_time:
            time.fromisoformat(departure_time)
    except ValueError:
        return {'status': 'invalid_request', 'message': 'Invalid departure date or travel time.'}
    pace = pace if pace in {'Relaxed', 'Balanced', 'Adventurous'} else 'Balanced'
    places = [Attraction.model_validate(item) for item in candidates]
    by_id = {place.id: place for place in places}
    model_order = {item_id: index for index, item_id in enumerate(selected_ids)
                   if item_id in by_id}
    interest_tags = {item.strip().casefold() for item in interests.split(',') if item.strip()}
    remaining = places.copy()
    itinerary = []
    scheduled_ids = []
    unfilled_active_slots = 0
    for day in range(1, days + 1):
        # Arrival and departure times are unknown. Keep one optional place on
        # those days instead of implying a full sightseeing schedule.
        active_slots = _active_periods(day, days, pace, arrival_time, departure_time)
        slots = []
        day_anchor = None
        for slot in SLOTS:
            if slot not in active_slots:
                continue
            options = [place for place in remaining if not any(
                _same_visit(place, by_id[used]) for used in scheduled_ids)]
            if slot == 'evening':
                options = [place for place in options if place.category in {
                    'market', 'viewpoint', 'square', 'fountain', 'park', 'garden',
                    'historic', 'monument', 'fort', 'beach', 'attraction'}]
            if day_anchor is not None:
                options = [place for place in options if _distance_km(day_anchor, place) <= 8]
            if not options:
                unfilled_active_slots += 1
                continue
            used_categories = {by_id[item_id].category for item_id in scheduled_ids}
            def rank(item: Attraction) -> tuple[float, str]:
                interest_match = len(CATEGORY_INTERESTS.get(item.category, set()) & interest_tags)
                model_preference = (2.0 - model_order[item.id] / max(1, len(model_order))
                                    if item.id in model_order else 0.0)
                variety = 1.5 if item.category not in used_categories else 0.0
                proximity = (_distance_km(day_anchor, item) / 2 if day_anchor else 0.0)
                provenance = 0.5 if item.source_url else 0.0
                return (3 * interest_match + model_preference + variety + provenance - proximity,
                        item.name.casefold())
            place = max(options, key=rank)
            remaining.remove(place)
            scheduled_ids.append(place.id)
            day_anchor = day_anchor or place
            match = CATEGORY_INTERESTS.get(place.category, set()) & interest_tags
            reason = (f"Matches your {sorted(match)[0]} interest. " if match else
                      f"Adds a {place.category} stop to the trip. ")
            slots.append({'period': slot, 'title': place.name, 'category': place.category,
                          'attraction_id': place.id, 'source_url': place.source_url,
                          'latitude': place.latitude, 'longitude': place.longitude,
                          'duration_minutes': DURATION_MINUTES.get(place.category, 90),
                          'description': (('Provisional until travel timing is confirmed. '
                                           if day in {1, days} and not (arrival_time if day == 1 else departure_time)
                                           else '') + reason +
                                          'Check current access and opening hours.').strip(),
                          'source': place.source, 'verified_place': True,
                          'estimated_admission_usd': None})
        day_note = ('Arrival-day activities are provisional because arrival time is unknown.'
                    if day == 1 and not arrival_time else
                    'Departure-day activities are provisional because departure time is unknown.'
                    if day == days and not departure_time else
                    'Travel logistics leave this day unscheduled.'
                    if day in {1, days} and not active_slots else '')
        itinerary.append({'day': day, 'note': day_note,
                          'date': (first_date + timedelta(days=day - 1)).isoformat()
                          if first_date else None, 'slots': slots})
    status = ('insufficient_data' if not scheduled_ids else
              'partial' if unfilled_active_slots else 'ok')
    sources = {place.source for place in places}
    return {'status': status, 'source': (next(iter(sources)) if len(sources) == 1
                                         else 'MIXED_GEOGRAPHIC_SOURCES' if sources
                                         else 'GENERAL_SUGGESTION'),
            'destination': destination, 'pace': pace,
            'arrival_time': arrival_time, 'departure_time': departure_time,
            'itinerary': itinerary, 'selected_attraction_ids': scheduled_ids,
            'estimated_activities_usd_per_person': None,
            'note': ('Unscheduled periods are left open because verified places were unavailable. '
                     if unfilled_active_slots else '') +
                    'Durations are planning allowances. Opening hours and admission are unknown.'}


def validate_global_itinerary(result: dict, *, candidates: list[dict],
                              destination: str, departure_date: date,
                              days: int, destination_latitude: float,
                              destination_longitude: float,
                              arrival_time: str = '', departure_time: str = '') -> dict:
    """Check the model-grounded tool result without another LLM call."""
    issues = []
    itinerary = result.get('itinerary') or []
    if result.get('destination') != destination:
        issues.append('destination_mismatch')
    if result.get('arrival_time', '') != arrival_time or result.get('departure_time', '') != departure_time:
        issues.append('travel_time_mismatch')
    if len(itinerary) != days or [item.get('day') for item in itinerary] != list(range(1, days + 1)):
        issues.append('invalid_day_sequence')
    by_id = {item['id']: Attraction.model_validate(item) for item in candidates}
    scheduled = set()
    verified_count = 0
    for day in itinerary:
        expected_date = departure_date + timedelta(days=day.get('day', 1) - 1)
        if day.get('date') != expected_date.isoformat():
            issues.append('date_mismatch')
        periods = set()
        allowed = _active_periods(day.get('day', 1), days, result.get('pace', 'Balanced'),
                                  arrival_time, departure_time)
        day_places = []
        for slot in day.get('slots') or []:
            period = slot.get('period')
            if period not in allowed or period in periods:
                issues.append('invalid_period_structure')
            periods.add(period)
            if slot.get('verified_place'):
                verified_count += 1
                item_id = slot.get('attraction_id')
                place = by_id.get(item_id)
                if place is None or item_id in scheduled:
                    issues.append('unverified_or_duplicate_attraction')
                    continue
                scheduled.add(item_id)
                if any(_same_visit(place, by_id[used]) for used in scheduled if used != item_id):
                    issues.append('excessive_attraction_repetition')
                if day_places and _distance_km(day_places[0], place) > 8:
                    issues.append('poor_geographic_grouping')
                day_places.append(place)
                if (slot.get('source') != place.source or
                    slot.get('latitude') != place.latitude or
                    slot.get('longitude') != place.longitude or
                    slot.get('source_url') != place.source_url or
                    _coordinate_distance_km(place.latitude, place.longitude,
                                            destination_latitude, destination_longitude) > 25):
                    issues.append('invalid_attraction_provenance')
                if slot.get('estimated_admission_usd') is not None:
                    issues.append('invented_admission_price')
            else:
                issues.append('unsupported_activity_slot')
                if slot.get('latitude') is not None or slot.get('longitude') is not None:
                    issues.append('unverified_coordinates')
    if issues:
        return {'status': 'invalid_result', 'issues': sorted(set(issues)),
                'verified_count': verified_count}
    if not verified_count:
        return {'status': 'insufficient_data', 'issues': ['no_verified_attractions'],
                'verified_count': 0}
    expected_active = sum(len(_active_periods(day, days, result.get('pace', 'Balanced'),
                                               arrival_time, departure_time))
                          for day in range(1, days + 1))
    if verified_count < expected_active:
        return {'status': 'partial', 'issues': ['limited_attraction_coverage'],
                'verified_count': verified_count}
    return {'status': 'ok', 'issues': [], 'verified_count': verified_count}


def partial_budget(*, days: int, nights: int, travelers: int, rooms: int,
                   food_per_person_per_day_usd: float,
                   transport_per_day_usd: float, budget_limit_usd: float,
                   flight_allowance_usd: float | None, hotel_allowance_usd: float | None,
                   admission_allowance_usd: float | None = None) -> dict:
    """Never treat missing travel or admission prices as zero."""
    food = round(days * travelers * food_per_person_per_day_usd, 2)
    transport = round(days * transport_per_day_usd, 2)
    breakdown = {'food_usd': food, 'ground_transport_usd': transport,
                 'flights_usd': flight_allowance_usd, 'hotel_usd': hotel_allowance_usd,
                 'admission_usd': admission_allowance_usd}
    subtotal = round(sum(value for value in breakdown.values() if value is not None), 2)
    missing = [name for name, value in breakdown.items() if value is None]
    travel_estimated = flight_allowance_usd is not None and hotel_allowance_usd is not None
    complete_estimate = not missing
    difference = round(budget_limit_usd - subtotal, 2)
    return {'status': 'estimate_complete' if complete_estimate else 'partial',
            'currency': 'USD', 'days': days, 'nights': nights,
            'travelers': travelers, 'rooms': rooms, 'breakdown': breakdown,
            'known_subtotal_usd': subtotal,
            'estimate_based_total_usd': subtotal if travel_estimated else None,
            'estimate_difference_usd': difference if travel_estimated else None,
            'estimated_total_usd': subtotal if complete_estimate else None,
            'budget_limit_usd': budget_limit_usd,
            'remaining_usd': difference if complete_estimate else None,
            'within_budget': difference >= 0 if complete_estimate else None,
            'missing_costs': missing,
            'note': ('All travel and admission amounts are user estimates or planning allowances.'
                     if complete_estimate else
                     'Unknown costs remain excluded from the displayed subtotal and comparison.')}
