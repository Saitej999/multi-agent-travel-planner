"""Bounded OpenStreetMap discovery of named accommodation properties."""

from functools import lru_cache
from urllib.parse import urlencode
from urllib.request import Request

from pydantic import BaseModel, Field, ValidationError

from .geo import (GeographicDataError, OVERPASS_URL, ResolvedLocation,
                  USER_AGENT, _distance_km, _read_json)

OVERPASS_FALLBACK_URL = 'https://overpass.private.coffee/api/interpreter'


class HotelProperty(BaseModel):
    id: str
    name: str = Field(min_length=2)
    city: str
    category: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    source: str = 'OPENSTREETMAP_OVERPASS'
    source_url: str


@lru_cache(maxsize=64)
def _hotel_payload(latitude: float, longitude: float) -> dict:
    around = f'(around:10000,{latitude:.5f},{longitude:.5f})'
    query = ('[out:json][timeout:8];('
             f'nwr["tourism"~"^(hotel|motel|guest_house|hostel)$"]["name"]{around};'
             ');out center 40;')
    for endpoint in (OVERPASS_URL, OVERPASS_FALLBACK_URL):
        request = Request(endpoint, data=urlencode({'data': query}).encode(),
                          headers={'User-Agent': USER_AGENT,
                                   'Content-Type': 'application/x-www-form-urlencoded'})
        try:
            payload = _read_json(request, timeout=11)
            if not isinstance(payload, dict):
                raise GeographicDataError('OpenStreetMap hotel response was invalid.')
            if payload.get('remark'):
                raise GeographicDataError('OpenStreetMap hotel search could not complete.')
            return payload
        except GeographicDataError:
            continue
    raise GeographicDataError('Both public OpenStreetMap hotel searches were unavailable.')


def discover_hotels(location: ResolvedLocation) -> list[HotelProperty]:
    places = []
    seen = set()
    for item in _hotel_payload(location.latitude, location.longitude).get('elements') or []:
        if not isinstance(item, dict) or item.get('type') not in {'node', 'way', 'relation'}:
            continue
        tags = item.get('tags') or {}
        name = (tags.get('name:en') or tags.get('name') or '').strip()
        position = item.get('center') or item
        category = tags.get('tourism')
        if not name or category not in {'hotel', 'motel', 'guest_house', 'hostel'}:
            continue
        try:
            place = HotelProperty(id=f"osm:{item['type']}/{item['id']}", name=name,
                                  city=location.name, category=category,
                                  latitude=position['lat'], longitude=position['lon'],
                                  source_url=f"https://www.openstreetmap.org/{item['type']}/{item['id']}")
        except (KeyError, ValidationError, TypeError):
            continue
        if _distance_km(location.latitude, location.longitude,
                        place.latitude, place.longitude) > 15:
            continue
        key = (place.name.casefold(), round(place.latitude, 3), round(place.longitude, 3))
        if key in seen:
            continue
        seen.add(key)
        places.append(place)
        if len(places) >= 30:
            break
    return places
