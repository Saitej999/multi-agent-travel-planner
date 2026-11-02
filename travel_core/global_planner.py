"""Grounded global itinerary and partial budget helpers."""

from datetime import date, timedelta
from math import asin, cos, radians, sin, sqrt

from .geo import Attraction


SLOTS = ('morning', 'afternoon', 'evening')


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
                           start_date: str = '', destination: str = '') -> dict:
    """Schedule distinct verified places; leave unsupported periods unscheduled."""
    if not 1 <= days <= 14:
        return {'status': 'invalid_request', 'message': 'Trip must span 1–14 calendar days.'}
    try:
        first_date = date.fromisoformat(start_date) if start_date else None
    except ValueError:
        return {'status': 'invalid_request', 'message': 'Invalid departure date.'}
    pace = pace if pace in {'Relaxed', 'Balanced', 'Adventurous'} else 'Balanced'
    places = [Attraction.model_validate(item) for item in candidates]
    by_id = {place.id: place for place in places}
    chosen = []
    for item_id in selected_ids:
        if item_id in by_id and item_id not in chosen:
            chosen.append(item_id)
    interest_tags = {item.strip().casefold() for item in interests.split(',')}
    preferred_categories = set()
    if interest_tags & {'culture', 'history', 'architecture', 'art'}:
        preferred_categories.update({'museum', 'gallery', 'historic', 'monument',
                                     'palace', 'fort', 'temple', 'church', 'attraction'})
    if 'food' in interest_tags:
        preferred_categories.add('market')
    if interest_tags & {'outdoors', 'nature', 'sightseeing'}:
        preferred_categories.update({'park', 'garden', 'beach', 'viewpoint', 'fountain'})
    unselected = [place for place in places if place.id not in chosen]
    unselected.sort(key=lambda place: place.category not in preferred_categories)
    chosen += [place.id for place in unselected]
    remaining = [by_id[item_id] for item_id in chosen]
    itinerary = []
    scheduled_ids = []
    unfilled_active_slots = 0
    for day in range(1, days + 1):
        # Arrival and departure times are unknown. Keep one optional place on
        # those days instead of implying a full sightseeing schedule.
        active_slots = ({'afternoon'} if day == 1 else {'morning'} if day == days else
                        set(SLOTS) if pace == 'Adventurous' else {'morning', 'afternoon'})
        slots = []
        day_anchor = None
        for slot in SLOTS:
            if slot not in active_slots:
                continue
            options = remaining
            if slot == 'evening':
                options = [place for place in options if place.category in {
                    'market', 'viewpoint', 'square', 'fountain', 'park', 'garden',
                    'historic', 'monument', 'fort', 'beach', 'attraction'}]
            if day_anchor is not None:
                options = [place for place in options if _distance_km(day_anchor, place) <= 8]
            if not options:
                unfilled_active_slots += 1
                continue
            place = (min(options, key=lambda item: _distance_km(day_anchor, item))
                     if day_anchor else options[0])
            remaining.remove(place)
            scheduled_ids.append(place.id)
            day_anchor = day_anchor or place
            slots.append({'period': slot, 'title': place.name, 'category': place.category,
                          'attraction_id': place.id, 'source_url': place.source_url,
                          'latitude': place.latitude, 'longitude': place.longitude,
                          'duration_minutes': 90 if slot != 'evening' else 60,
                          'description': (('Optional if travel timing allows. ' if day in {1, days}
                                           else 'Check opening hours before visiting. ') +
                                          place.description).strip(),
                          'source': place.source, 'verified_place': True,
                          'estimated_admission_usd': None})
        itinerary.append({'day': day,
                          'date': (first_date + timedelta(days=day - 1)).isoformat()
                          if first_date else None, 'slots': slots})
    status = ('insufficient_data' if not scheduled_ids else
              'partial' if unfilled_active_slots else 'ok')
    sources = {place.source for place in places}
    return {'status': status, 'source': (next(iter(sources)) if len(sources) == 1
                                         else 'MIXED_GEOGRAPHIC_SOURCES' if sources
                                         else 'GENERAL_SUGGESTION'),
            'destination': destination, 'pace': pace,
            'itinerary': itinerary, 'selected_attraction_ids': scheduled_ids,
            'estimated_activities_usd_per_person': None,
            'note': ('Unscheduled periods are left open because verified places were unavailable. '
                     if unfilled_active_slots else '') +
                    'Durations are planning allowances. Opening hours and admission are unknown.'}


def validate_global_itinerary(result: dict, *, candidates: list[dict],
                              destination: str, departure_date: date,
                              days: int, destination_latitude: float,
                              destination_longitude: float) -> dict:
    """Check the model-grounded tool result without another LLM call."""
    issues = []
    itinerary = result.get('itinerary') or []
    if result.get('destination') != destination:
        issues.append('destination_mismatch')
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
        for slot in day.get('slots') or []:
            period = slot.get('period')
            if period not in SLOTS or period in periods:
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
                if (slot.get('source') != place.source or
                    slot.get('latitude') != place.latitude or
                    slot.get('longitude') != place.longitude or
                    slot.get('source_url') != place.source_url or
                    _coordinate_distance_km(place.latitude, place.longitude,
                                            destination_latitude, destination_longitude) > 25):
                    issues.append('invalid_attraction_provenance')
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
    expected_active = 2 + max(0, days - 2) * (3 if result.get('pace') == 'Adventurous' else 2)
    if verified_count < expected_active:
        return {'status': 'partial', 'issues': ['limited_attraction_coverage'],
                'verified_count': verified_count}
    return {'status': 'ok', 'issues': [], 'verified_count': verified_count}


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
