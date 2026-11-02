"""Mock travel provider tools for Google ADK agents.

These functions NEVER check live availability or issue bookings.
All catalog prices are synthetic test fixtures.
"""
from datetime import date
import json

from pydantic import ValidationError

from .catalog import ACTIVITIES, AIRPORT_ALIASES, CITY_BY_AIRPORT, FLIGHTS, HOTELS
from .schemas import ActivityQuery, BudgetQuery, FlightQuery, HotelQuery


def _airport(value: str) -> str | None:
    return AIRPORT_ALIASES.get(value.strip().lower())


def _city(value: str) -> str | None:
    code = _airport(value)
    return CITY_BY_AIRPORT.get(code) if code else None


def _error(exc: ValidationError) -> dict:
    return {"status": "invalid_request", "errors": [e["msg"] for e in exc.errors()]}


def search_flights(origin: str, destination: str, departure_date: str, return_date: str,
                   travelers: int = 1, global_mode: bool = False,
                   flight_allowance_usd: float | None = None) -> dict:
    """Search synthetic round-trip airfare examples (not live flights).

    Args:
        origin: Origin city name or airport code, e.g. Chicago or ORD.
        destination: Destination city name or airport code, e.g. New York or JFK.
        departure_date: Outbound date YYYY-MM-DD.
        return_date: Return date YYYY-MM-DD.
        travelers: Number of travelers between 1 and 8.
        global_mode: True when no synthetic flight catalog applies.
        flight_allowance_usd: Optional user-entered group airfare allowance, not a quote.
    """
    try:
        q = FlightQuery(origin=origin, destination=destination, departure_date=departure_date,
                        return_date=return_date, travelers=travelers)
    except ValidationError as exc:
        return _error(exc)
    if global_mode:
        return {'status': 'unavailable', 'source': 'NO_LIVE_PROVIDER', 'bookable': False,
                'origin': q.origin, 'destination': q.destination,
                'departure_date': q.departure_date.isoformat(),
                'return_date': q.return_date.isoformat(), 'travelers': q.travelers,
                'options': [], 'flight_allowance_usd': flight_allowance_usd,
                'price_status': 'user_estimate' if flight_allowance_usd is not None else 'unknown',
                'note': 'No live flight provider is connected; no flight offer or airline is claimed.'}
    src, dst = _airport(q.origin), _airport(q.destination)
    if src is None or dst is None:
        return {"status": "unsupported_route", "message": "Demo routes begin in Chicago (ORD) and end in NYC, SFO, or Tokyo; live flight APIs are not connected."}
    if src == dst:
        return {"status": "invalid_request", "message": "Origin and destination must differ."}
    options = [dict(f, total_round_trip_usd=round(f["round_trip_usd_per_person"] * q.travelers, 2))
               for f in FLIGHTS if f["origin"] == src and f["destination"] == dst]
    return {"status": "ok" if options else "no_results", "source": "SYNTHETIC_DEMO",
            "live_availability_checked": False, "bookable": False,
            "departure_date": q.departure_date.isoformat(), "return_date": q.return_date.isoformat(),
            "travelers": q.travelers, "options": options,
            "note": "These are fictional examples, NOT current flights, prices, or inventory."
                    if options else "No synthetic flight options are available for this route."}


def search_hotels(destination: str, check_in: str, check_out: str, rooms: int = 1,
                  global_mode: bool = False, hotel_allowance_usd: float | None = None) -> dict:
    """Search synthetic hotel examples; no current room inventory is checked.

    Args:
        destination: City name or airport code.
        check_in: Check-in date YYYY-MM-DD (confirm arrival date separately).
        check_out: Check-out date YYYY-MM-DD.
        rooms: Number of rooms between 1 and 8.
        global_mode: True when no synthetic hotel catalog applies.
        hotel_allowance_usd: Optional user-entered stay allowance, not a room offer.
    """
    try:
        q = HotelQuery(destination=destination, check_in=check_in, check_out=check_out, rooms=rooms)
    except ValidationError as exc:
        return _error(exc)
    if global_mode:
        nights = (q.check_out - q.check_in).days
        return {'status': 'unavailable', 'source': 'NO_LIVE_PROVIDER', 'bookable': False,
                'destination': q.destination, 'check_in': q.check_in.isoformat(),
                'check_out': q.check_out.isoformat(), 'nights': nights, 'rooms': q.rooms,
                'options': [], 'hotel_allowance_usd': hotel_allowance_usd,
                'price_status': 'user_estimate' if hotel_allowance_usd is not None else 'unknown',
                'note': 'No live hotel provider is connected; no property or room price is claimed.'}
    city = _city(q.destination)
    if not city:
        return {"status": "unsupported_destination", "message": "Demo hotels only cover New York City, San Francisco, and Tokyo."}
    nights = (q.check_out - q.check_in).days
    options = [dict(h, total_room_cost_usd=round(h["nightly_usd_per_room"] * nights * q.rooms, 2))
               for h in HOTELS if h["city"] == city]
    return {"status": "ok" if options else "no_results", "source": "SYNTHETIC_DEMO", "live_availability_checked": False,
            "bookable": False, "city": city, "check_in": q.check_in.isoformat(),
            "check_out": q.check_out.isoformat(), "nights": nights, "rooms": q.rooms,
            "options": options, "note": "Fictional lodging options. Taxes, fees, and availability not included."
                    if options else "No synthetic hotel options are available for this destination."}


def suggest_activities(destination: str, days: int, interests: str = "", free_only: bool = False,
                       avoid_popular_spots: bool = False, candidate_data_json: str = '',
                       selected_attraction_ids: str = '', pace: str = 'Balanced',
                       start_date: str = '') -> dict:
    """Construct a simple day-wise itinerary using example activity ideas.

    Args:
        destination: Destination city or airport code.
        days: Number of activity days between 1 and 14.
        interests: Comma-separated interests: culture, outdoors, food, entertainment.
        free_only: If True, use only zero-cost demo activities (may repeat landmarks).
        avoid_popular_spots: If True, omit catalog items tagged as popular spots; not a live crowd forecast.
        candidate_data_json: Verified OSM candidates supplied by the application for global trips.
        selected_attraction_ids: Comma-separated candidate IDs chosen in preference order.
        pace: Relaxed, Balanced, or Adventurous.
        start_date: ISO departure date for a verified global itinerary.
    """
    try:
        q = ActivityQuery(destination=destination, days=days, interests=interests)
    except ValidationError as exc:
        return _error(exc)
    if candidate_data_json:
        from .global_planner import build_global_itinerary

        try:
            candidates = json.loads(candidate_data_json)
            if not isinstance(candidates, list):
                raise ValueError('Attraction candidates must be a list')
            return build_global_itinerary(candidates,
                                          [item.strip() for item in selected_attraction_ids.split(',')],
                                          q.days, pace=pace, interests=q.interests,
                                          start_date=start_date, destination=q.destination)
        except (ValueError, TypeError) as exc:
            return {'status': 'invalid_request', 'message': f'Invalid attraction data: {exc}'}
    city = _city(q.destination)
    if city not in ACTIVITIES:
        return {"status": "unsupported_destination", "message": "Demo activities only cover New York City, San Francisco, and Tokyo."}
    options = ACTIVITIES[city]
    eligible = [a for a in options if (not free_only or a["estimated_usd_per_person"] == 0)
                and (not avoid_popular_spots or not a.get('popular_spot', False))]
    if not eligible:
        return {"status": "no_results", "source": "SYNTHETIC_DEMO", "destination": city,
                "free_only": free_only, "itinerary": [], "estimated_activities_usd_per_person": 0.0,
                "note": "No synthetic activities match this request."}
    requested_order = [tag.strip().lower() for tag in q.interests.split(',') if tag.strip()]
    preferred = [a for tag in requested_order for a in eligible if a['interest'] == tag]
    if len(requested_order) == 1 and preferred:
        ordered = preferred
    else:
        ordered = preferred + [a for a in eligible if a not in preferred]
    # Cycle through attractions: useful for a toy starter; replacing with real geospatial planner is a future milestone.
    itinerary = [{"day": i + 1, "activity": ordered[i % len(ordered)]} for i in range(q.days)]
    activity_cost = round(sum(item["activity"]["estimated_usd_per_person"] for item in itinerary), 2)
    return {"status": "ok", "source": "SYNTHETIC_DEMO", "destination": city, "free_only": free_only,
            "interests_used": q.interests, "avoid_popular_spots": avoid_popular_spots,
            "itinerary": itinerary, "estimated_activities_usd_per_person": activity_cost,
            "note": "Check real-world opening hours, ticket prices, transit times, and accessibility before traveling."}


def estimate_budget(
    flight_option_id: str,
    hotel_option_id: str,
    nights: int,
    travelers: int = 1,
    rooms: int = 1,
    food_per_person_per_day_usd: float = 45.0,
    transport_per_day_usd: float = 20.0,
    activities_per_person_usd: float = 0.0,
    budget_limit_usd: float = 0.0,
) -> dict:
    """Calculate a deterministic sample budget from synthetic flight/hotel IDs.

    Args:
        flight_option_id: ID returned by search_flights, e.g. DEMO-F001.
        hotel_option_id: ID returned by search_hotels, e.g. DEMO-H001.
        nights: Lodging nights.
        travelers: Total people traveling.
        rooms: Total rooms booked.
        food_per_person_per_day_usd: Estimated per-person food spend per day.
        transport_per_day_usd: Estimated total ground transport spend per day for group.
        activities_per_person_usd: Total expected activity costs per person over trip.
        budget_limit_usd: Optional overall trip budget, or 0 if unspecified.
    """
    try:
        q = BudgetQuery(flight_option_id=flight_option_id, hotel_option_id=hotel_option_id,
                        nights=nights, travelers=travelers, rooms=rooms,
                        food_per_person_per_day_usd=food_per_person_per_day_usd,
                        transport_per_day_usd=transport_per_day_usd,
                        activities_per_person_usd=activities_per_person_usd,
                        budget_limit_usd=budget_limit_usd)
    except ValidationError as exc:
        return _error(exc)
    flight = next((f for f in FLIGHTS if f["id"] == q.flight_option_id), None)
    hotel = next((h for h in HOTELS if h["id"] == q.hotel_option_id), None)
    if flight is None or hotel is None:
        return {"status": "invalid_selection", "message": "Only IDs actually returned by the synthetic provider can be budgeted."}
    if CITY_BY_AIRPORT[flight["destination"]] != hotel["city"]:
        return {"status": "invalid_selection", "message": "Flight destination and hotel location do not match."}
    days = q.nights + 1
    breakdown = {
        "round_trip_flights_usd": round(flight["round_trip_usd_per_person"] * q.travelers, 2),
        "hotel_room_total_usd": round(hotel["nightly_usd_per_room"] * q.rooms * q.nights, 2),
        "food_usd": round(q.food_per_person_per_day_usd * q.travelers * days, 2),
        "ground_transport_usd": round(q.transport_per_day_usd * days, 2),
        "activities_usd": round(q.activities_per_person_usd * q.travelers, 2),
    }
    total = round(sum(breakdown.values()), 2)
    return {"status": "ok", "source": "SYNTHETIC_DEMO", "currency": "USD",
            "flight_option_id": q.flight_option_id, "hotel_option_id": q.hotel_option_id,
            "nights": q.nights, "days": days, "travelers": q.travelers, "rooms": q.rooms,
            "breakdown": breakdown, "estimated_total_usd": total,
            "budget_limit_usd": q.budget_limit_usd if q.budget_limit_usd else None,
            "remaining_usd": round(q.budget_limit_usd - total, 2) if q.budget_limit_usd else None,
            "within_budget": total <= q.budget_limit_usd if q.budget_limit_usd else None,
            "excluded": ["Taxes and resort fees", "Baggage and seat selection", "Travel insurance", "Visa costs", "Price volatility"],
            "note": "This is sample planning arithmetic, not a quote or booking offer."}
