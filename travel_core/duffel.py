"""Read-only flight search using Duffel developer test mode only."""

import json
import os
from decimal import Decimal, InvalidOperation
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field, ValidationError

from .geo import ResolvedLocation, _distance_km
from .catalog import AIRPORT_ALIASES


BASE = 'https://api.duffel.com'


class DuffelError(Exception):
    def __init__(self, reason: str):
        self.reason = reason


class Place(BaseModel):
    type: str
    iata_code: str = Field(pattern=r'^[A-Z]{3}$')
    iata_country_code: str
    name: str
    city_name: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class Carrier(BaseModel):
    name: str = Field(min_length=2)


class Segment(BaseModel):
    operating_carrier: Carrier


class Slice(BaseModel):
    segments: list[Segment] = Field(min_length=1)


class TestOffer(BaseModel):
    id: str
    live_mode: bool
    total_amount: Decimal
    total_currency: str
    slices: list[Slice] = Field(min_length=2)


def test_token_available() -> bool:
    return os.getenv('DUFFEL_TEST_TOKEN', '').startswith('duffel_test_')


def _request(path: str, token: str, *, body: dict | None = None) -> dict:
    headers = {'Authorization': f'Bearer {token}', 'Duffel-Version': 'v2',
               'Accept': 'application/json'}
    payload = None
    if body is not None:
        headers['Content-Type'] = 'application/json'
        payload = json.dumps({'data': body}).encode('utf-8')
    request = Request(BASE + path, data=payload, headers=headers,
                      method='POST' if body is not None else 'GET')
    try:
        with urlopen(request, timeout=18 if body is not None else 7) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise DuffelError('invalid_response')
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise DuffelError('invalid_response')
        return parsed
    except HTTPError as exc:
        raise DuffelError('authentication_error' if exc.code in {401, 403}
                          else 'rate_limited' if exc.code == 429 else 'provider_unavailable') from exc
    except (TimeoutError, URLError) as exc:
        raise DuffelError('timeout' if isinstance(exc, TimeoutError) or
                          isinstance(getattr(exc, 'reason', None), TimeoutError)
                          else 'provider_unavailable') from exc
    except (ValueError, UnicodeDecodeError) as exc:
        raise DuffelError('invalid_response') from exc


def resolve_airport(location: ResolvedLocation, token: str) -> str | None:
    """Use Duffel Places and the selected city/country, never a guessed IATA code."""
    if not location.country_code:
        return None
    payload = _request('/places/suggestions?' + urlencode({'query': location.name}), token)
    valid = []
    for raw in payload.get('data') or []:
        if not isinstance(raw, dict):
            continue
        try:
            place = Place.model_validate(raw)
        except ValidationError:
            continue
        if place.type != 'airport' or place.iata_country_code.upper() != location.country_code.upper():
            continue
        city = raw.get('city') if isinstance(raw.get('city'), dict) else {}
        city_name = (place.city_name or city.get('name') or '').casefold()
        if location.name.casefold() not in city_name and city_name not in location.name.casefold():
            continue
        if place.latitude is None or place.longitude is None:
            continue
        distance = _distance_km(location.latitude, location.longitude,
                                place.latitude, place.longitude)
        if distance <= 100:
            valid.append((distance, place.iata_code))
    preferred = AIRPORT_ALIASES.get(location.name.casefold())
    if preferred and any(code == preferred for _, code in valid):
        return preferred
    return min(valid)[1] if valid else None


def search_test_offers(origin: ResolvedLocation, destination: ResolvedLocation,
                       departure_date: str, return_date: str, travelers: int) -> dict:
    """Return a few USD round-trip test offers; never create orders or bookings."""
    token = os.getenv('DUFFEL_TEST_TOKEN', '').strip()
    if not token:
        return {'status': 'unavailable', 'reason': 'missing_credentials', 'options': []}
    if not token.startswith('duffel_test_'):
        return {'status': 'unavailable', 'reason': 'test_token_required', 'options': []}
    try:
        src = resolve_airport(origin, token)
        dst = resolve_airport(destination, token)
        if not src or not dst or src == dst:
            return {'status': 'unavailable', 'reason': 'airport_unresolved', 'options': []}
        query = urlencode({'return_offers': 'true', 'supplier_timeout': 10000})
        payload = _request('/air/offer_requests?' + query, token, body={
            'slices': [{'origin': src, 'destination': dst, 'departure_date': departure_date},
                       {'origin': dst, 'destination': src, 'departure_date': return_date}],
            'passengers': [{'type': 'adult'} for _ in range(travelers)],
            'cabin_class': 'economy'})
        data = payload.get('data') or {}
        if not isinstance(data, dict):
            return {'status': 'unavailable', 'reason': 'invalid_response', 'options': []}
        if data.get('live_mode') is not False:
            return {'status': 'unavailable', 'reason': 'live_response_rejected', 'options': []}
        options = []
        for raw in data.get('offers') or []:
            try:
                offer = TestOffer.model_validate(raw)
                if offer.live_mode or offer.total_currency != 'USD' or len(offer.slices) != 2:
                    continue
                total = float(offer.total_amount)
                if not 0 <= total <= 1_000_000:
                    continue
                carriers = list(dict.fromkeys(
                    segment.operating_carrier.name for slice_ in offer.slices
                    for segment in slice_.segments))
                options.append({'id': offer.id, 'origin': src, 'destination': dst,
                                'airline': ', '.join(carriers),
                                'stops': sum(len(slice_.segments) - 1 for slice_ in offer.slices),
                                'total_round_trip_usd': round(total, 2),
                                'round_trip_usd_per_person': round(total / travelers, 2),
                                'departure_date': departure_date, 'return_date': return_date,
                                'source': 'DUFFEL_TEST'})
            except (ValidationError, ValueError, InvalidOperation, ZeroDivisionError):
                continue
        options.sort(key=lambda item: item['total_round_trip_usd'])
        return {'status': 'ok' if options else 'unavailable',
                'reason': None if options else 'no_test_offers', 'options': options[:5]}
    except DuffelError as exc:
        return {'status': 'unavailable', 'reason': exc.reason, 'options': []}
