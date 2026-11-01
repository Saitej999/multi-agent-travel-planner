"""Small, bounded clients for public city and attraction data."""

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field, ValidationError


GEOCODING_URL = 'https://geocoding-api.open-meteo.com/v1/search'
OVERPASS_URL = 'https://overpass-api.de/api/interpreter'
USER_AGENT = 'MultiAgentTravelPlanner-learning-project/1.0'


class GeographicDataError(ValueError):
    """A location could not be verified from the external source."""


class ResolvedLocation(BaseModel):
    id: int
    name: str = Field(min_length=2)
    country: str = Field(min_length=2)
    region: str = ''
    country_code: str = ''
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    timezone: str = ''
    source: str = 'OPEN_METEO_GEOCODING'

    @property
    def label(self) -> str:
        parts = [self.name, self.region, self.country]
        return ', '.join(part for part in parts if part)


class Attraction(BaseModel):
    id: str
    name: str = Field(min_length=2)
    category: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    description: str = ''
    source: str = 'OPENSTREETMAP_OVERPASS'


def _read_json(request: Request, timeout: int) -> dict:
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(1_000_001)
        if len(raw) > 1_000_000:
            raise GeographicDataError('The map service returned too much data. Try again later.')
        return json.loads(raw)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise GeographicDataError(f'Location service is unavailable: {type(exc).__name__}') from exc


def search_cities(query: str) -> list[ResolvedLocation]:
    """Return up to five named, disambiguated city candidates."""
    query = query.strip()
    if len(query) < 2:
        return []
    url = GEOCODING_URL + '?' + urlencode({'name': query, 'count': 5, 'language': 'en', 'format': 'json'})
    data = _read_json(Request(url, headers={'User-Agent': USER_AGENT}), timeout=7)
    locations = []
    for item in data.get('results') or []:
        try:
            locations.append(ResolvedLocation(
                id=item['id'], name=item['name'], country=item['country'],
                region=item.get('admin1') or '', country_code=item.get('country_code') or '',
                latitude=item['latitude'], longitude=item['longitude'],
                timezone=item.get('timezone') or '',
            ))
        except (KeyError, ValidationError):
            continue
    return locations


def discover_attractions(location: ResolvedLocation) -> list[Attraction]:
    """Fetch at most 60 named OSM places near a verified city center."""
    around = f'(around:4500,{location.latitude:.5f},{location.longitude:.5f})'
    query = ('[out:json][timeout:12];('
             f'nwr["tourism"~"^(museum|gallery|attraction|viewpoint)$"]{around};'
             f'nwr["historic"]{around};'
             f'nwr["leisure"="park"]{around};'
             ');out center 60;')
    request = Request(OVERPASS_URL, data=urlencode({'data': query}).encode(),
                      headers={'User-Agent': USER_AGENT,
                               'Content-Type': 'application/x-www-form-urlencoded'})
    data = _read_json(request, timeout=16)
    places = []
    seen = set()
    for item in data.get('elements') or []:
        tags = item.get('tags') or {}
        name = (tags.get('name:en') or tags.get('name') or '').strip()
        position = item.get('center') or item
        if not name or 'lat' not in position or 'lon' not in position:
            continue
        key = name.casefold()
        if key in seen:
            continue
        category = ('museum' if tags.get('tourism') == 'museum' else
                    'gallery' if tags.get('tourism') == 'gallery' else
                    'park' if tags.get('leisure') == 'park' else
                    'historic' if 'historic' in tags else
                    'viewpoint' if tags.get('tourism') == 'viewpoint' else 'attraction')
        try:
            place = Attraction(id=f"osm:{item['type']}/{item['id']}", name=name,
                               category=category, latitude=position['lat'],
                               longitude=position['lon'],
                               description=(tags.get('description:en') or tags.get('description') or '')[:180])
        except (KeyError, ValidationError):
            continue
        seen.add(key)
        places.append(place)
        if len(places) == 60:
            break
    return places
