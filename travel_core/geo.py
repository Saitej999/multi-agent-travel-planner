"""Small, bounded clients for public city and attraction data."""

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from math import asin, cos, radians, sin, sqrt
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from pydantic import BaseModel, Field, ValidationError


GEOCODING_URL = 'https://geocoding-api.open-meteo.com/v1/search'
OVERPASS_URL = 'https://overpass-api.de/api/interpreter'
WIKIPEDIA_URL = 'https://en.wikipedia.org/w/api.php'
USER_AGENT = 'MultiAgentTravelPlanner-learning-project/1.0'
WIKIPEDIA_USER_AGENT = 'MultiAgentTravelPlanner/1.0 (educational project; https://github.com/Saitej999)'


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
    source_url: str = ''


@dataclass(frozen=True)
class AttractionDiscovery:
    attractions: list[Attraction]
    status: str
    sources: list[str]
    warnings: list[str]
    diagnostics: list[dict] | None = None


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
    return list(_search_cities_cached(query))


@lru_cache(maxsize=128)
def _search_cities_cached(query: str) -> tuple[ResolvedLocation, ...]:
    """Avoid repeated public geocoding requests in this single-process app."""
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
    return tuple(locations)


@lru_cache(maxsize=64)
def _overpass_payload(latitude: float, longitude: float) -> dict:
    """Cache only successful bounded provider responses in this local process."""
    around = f'(around:3000,{latitude:.5f},{longitude:.5f})'
    query = ('[out:json][timeout:8];('
             f'nwr["tourism"~"^(museum|gallery|attraction|viewpoint)$"]{around};'
             f'nwr["historic"~"^(monument|memorial|archaeological_site|castle|ruins)$"]{around};'
             f'nwr["leisure"~"^(park|garden)$"]{around};'
             f'nwr["amenity"="marketplace"]{around};'
             ');out center 40;')
    request = Request(OVERPASS_URL, data=urlencode({'data': query}).encode(),
                      headers={'User-Agent': USER_AGENT,
                               'Content-Type': 'application/x-www-form-urlencoded'})
    data = _read_json(request, timeout=11)
    if data.get('remark'):
        raise GeographicDataError('OpenStreetMap attraction search could not complete.')
    return data


def discover_attractions(location: ResolvedLocation) -> list[Attraction]:
    """Fetch at most 40 named OSM places near a verified city center."""
    data = _overpass_payload(location.latitude, location.longitude)
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
                    'garden' if tags.get('leisure') == 'garden' else
                    'market' if tags.get('amenity') == 'marketplace' else
                    'historic' if 'historic' in tags else
                    'viewpoint' if tags.get('tourism') == 'viewpoint' else 'attraction')
        try:
            place = Attraction(id=f"osm:{item['type']}/{item['id']}", name=name,
                               category=category, latitude=position['lat'],
                               longitude=position['lon'],
                               description=(tags.get('description:en') or tags.get('description') or '')[:180],
                               source_url=f"https://www.openstreetmap.org/{item['type']}/{item['id']}")
        except (KeyError, ValidationError):
            continue
        seen.add(key)
        places.append(place)
        if len(places) == 40:
            break
    return places


_WIKI_CATEGORY_TYPES = (
    ('museum', r'\bmuseums?\b'),
    ('gallery', r'\bart galleries\b'),
    ('park', r'\bparks?\b|\bzoos?\b'),
    ('garden', r'\bgardens?\b'),
    ('market', r'\bmarkets?\b|\bmarketplaces?\b'),
    ('temple', r'\btemples?\b|\bshrines?\b'),
    ('church', r'\bchurches\b|\bchurch buildings\b|\bcathedrals?\b|\bbasilicas?\b'),
    ('palace', r'\bpalaces?\b'),
    ('fort', r'\bforts?\b|\bfortifications?\b'),
    ('fountain', r'\bfountains?\b'),
    ('beach', r'\bbeaches\b'),
    ('historic', r'\bhistoric sites\b|\bheritage sites\b|\bworld heritage sites\b|\barchaeological sites\b'),
    ('monument', r'\bmonuments? and memorials? in\b'),
    ('attraction', r'\btourist attractions? in\b'),
    ('theatre', r'\btheat(?:res|ers)\b'),
)
_WIKI_EXCLUDED = re.compile(
    r'\b(airports?|schools?|colleges?|universities|hospitals?|prisons?|'
    r'constituencies|politicians|companies|disasters|bombings?|stations?|'
    r'stock exchanges?)\b', re.IGNORECASE)
_WIKI_NOT_VISITABLE = re.compile(
    r'\b(demolished|destroyed|disestablishments|former theatres|former theaters)\b',
    re.IGNORECASE)


def _wikipedia_category(page: dict, location: ResolvedLocation) -> str | None:
    """Require a place-type category and destination evidence, not a name guess."""
    title = str(page.get('title') or '')
    categories = [str(item.get('title') or '').removeprefix('Category:').casefold()
                  for item in page.get('categories') or []]
    if _WIKI_EXCLUDED.search(title):
        return None
    if any(_WIKI_NOT_VISITABLE.search(category) for category in categories):
        return None
    locality = (location.name, location.region, location.country)
    if not any(part and part.casefold() in category
               for part in locality for category in categories):
        return None
    for category_name, pattern in _WIKI_CATEGORY_TYPES:
        if any(re.search(pattern, category) for category in categories):
            return category_name
    return None


def _distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    a = sin(radians(lat2 - lat1) / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * (
        sin(radians(lon2 - lon1) / 2) ** 2)
    return 6371 * 2 * asin(min(1, sqrt(a)))


@lru_cache(maxsize=64)
def _wikipedia_payload(latitude: float, longitude: float) -> dict:
    """Cache successful geosearch responses without caching provider failures."""
    params = {'action': 'query', 'generator': 'geosearch',
              'ggscoord': f'{latitude:.5f}|{longitude:.5f}',
              'ggsradius': 10000, 'ggslimit': 100, 'ggsnamespace': 0,
              'prop': 'coordinates|categories', 'colimit': 'max',
              'cllimit': 'max', 'clshow': '!hidden',
              'format': 'json', 'formatversion': 2}
    request = Request(WIKIPEDIA_URL + '?' + urlencode(params),
                      headers={'User-Agent': WIKIPEDIA_USER_AGENT})
    data = _read_json(request, timeout=12)
    if data.get('error'):
        raise GeographicDataError('Wikipedia attraction search returned an API error.')
    return data


def discover_wikipedia_attractions(location: ResolvedLocation) -> list[Attraction]:
    """Use one bounded geosearch request; only include nearby, categorized places."""
    data = _wikipedia_payload(location.latitude, location.longitude)
    places = []
    for page in (data.get('query') or {}).get('pages') or []:
        category = _wikipedia_category(page, location)
        if category is None:
            continue
        coordinates = page.get('coordinates') or []
        if not coordinates:
            continue
        point = coordinates[0]
        try:
            lat, lon = float(point['lat']), float(point['lon'])
            if _distance_km(location.latitude, location.longitude, lat, lon) > 10:
                continue
            title = str(page['title']).strip()
            places.append(Attraction(id=f"wikipedia:{page['pageid']}", name=title,
                                     category=category, latitude=lat, longitude=lon,
                                     source='WIKIPEDIA_GEOSEARCH',
                                     source_url=f"https://en.wikipedia.org/?curid={page['pageid']}"))
        except (KeyError, TypeError, ValueError, ValidationError):
            continue
    return places


_ORIGINAL_OSM_DISCOVERY = discover_attractions
_ORIGINAL_WIKI_DISCOVERY = discover_wikipedia_attractions


def _secondary_center(location: ResolvedLocation, places: list[Attraction]) -> ResolvedLocation:
    """Cover a second north-south city area without inventing venue coordinates."""
    latitude = max(-89.9, min(89.9, location.latitude - 12 / 111))
    mean_east_km = (sum((place.longitude - location.longitude) * 111 *
                        max(.1, cos(radians(location.latitude))) for place in places) / len(places)
                    if places else 0.0)
    east_km = -3.0 if mean_east_km < 0 else 3.0 if mean_east_km > 0 else 0.0
    longitude = location.longitude + east_km / (
        111 * max(.1, cos(radians(location.latitude))))
    longitude = ((longitude + 180) % 360) - 180
    return location.model_copy(update={'latitude': latitude, 'longitude': longitude})


def _provider_error(exc: GeographicDataError) -> tuple[str, int | None]:
    cause = exc.__cause__
    if isinstance(cause, HTTPError):
        return 'http_error', cause.code
    if isinstance(cause, TimeoutError):
        return 'timeout', None
    if isinstance(cause, (URLError,)):
        return 'unavailable', None
    return 'provider_response_error', None


def find_attractions(location: ResolvedLocation, min_places: int = 6) -> AttractionDiscovery:
    """Use one OSM area and at most two bounded Wikipedia areas when needed."""
    places: list[Attraction] = []
    sources: list[str] = []
    warnings: list[str] = []
    diagnostics: list[dict] = []
    try:
        places = discover_attractions(location)
        raw_count = (len((_overpass_payload(location.latitude, location.longitude).get('elements') or []))
                     if discover_attractions is _ORIGINAL_OSM_DISCOVERY else None)
        diagnostics.append({'provider': 'OPENSTREETMAP_OVERPASS', 'status': 'ok',
                            'center': [location.latitude, location.longitude],
                            'radius_m': 3000, 'raw_count': raw_count,
                            'accepted_count': len(places)})
        if places:
            sources.append('OPENSTREETMAP_OVERPASS')
    except GeographicDataError as exc:
        kind, http_status = _provider_error(exc)
        diagnostics.append({'provider': 'OPENSTREETMAP_OVERPASS', 'status': kind,
                            'http_status': http_status, 'raw_count': None,
                            'accepted_count': 0, 'center': [location.latitude, location.longitude],
                            'radius_m': 3000})
        warnings.append('OpenStreetMap attraction search ' +
                        ('timed out.' if kind == 'timeout' else 'is temporarily unavailable.'))

    def add_wikipedia(search_location: ResolvedLocation) -> bool:
        try:
            found = discover_wikipedia_attractions(search_location)
            raw_count = (len((_wikipedia_payload(search_location.latitude,
                                                 search_location.longitude).get('query') or {}).get('pages') or [])
                         if discover_wikipedia_attractions is _ORIGINAL_WIKI_DISCOVERY else None)
            accepted = 0
            seen = {place.name.casefold() for place in places}
            for place in found:
                if (place.name.casefold() not in seen and
                    _distance_km(location.latitude, location.longitude,
                                 place.latitude, place.longitude) <= 25):
                    places.append(place)
                    seen.add(place.name.casefold())
                    accepted += 1
            if accepted and 'WIKIPEDIA_GEOSEARCH' not in sources:
                sources.append('WIKIPEDIA_GEOSEARCH')
            diagnostics.append({'provider': 'WIKIPEDIA_GEOSEARCH', 'status': 'ok',
                                'center': [round(search_location.latitude, 5),
                                           round(search_location.longitude, 5)],
                                'radius_m': 10000, 'raw_count': raw_count,
                                'parsed_count': len(found), 'accepted_count': accepted})
            return True
        except GeographicDataError as exc:
            kind, http_status = _provider_error(exc)
            diagnostics.append({'provider': 'WIKIPEDIA_GEOSEARCH', 'status': kind,
                                'http_status': http_status, 'raw_count': None,
                                'accepted_count': 0,
                                'center': [round(search_location.latitude, 5),
                                           round(search_location.longitude, 5)],
                                'radius_m': 10000})
            warnings.append('Wikipedia attraction search ' +
                            ('timed out.' if kind == 'timeout' else 'is temporarily unavailable.'))
            return False

    if len(places) < min_places:
        wiki_available = add_wikipedia(location)
        if wiki_available and len(places) < min_places:
            add_wikipedia(_secondary_center(location, [place for place in places
                                                       if place.source == 'WIKIPEDIA_GEOSEARCH']))
    if not places:
        warnings.append('No verified attractions are available; the itinerary is incomplete.')
    elif len(places) < min_places:
        warnings.append('Only a few verified attractions are available; unscheduled periods remain open.')
    status = 'complete' if len(places) >= min_places else 'partial'
    if status == 'partial':
        # Let the user retry incomplete discovery; only complete results stay cached.
        _overpass_payload.cache_clear()
        _wikipedia_payload.cache_clear()
    return AttractionDiscovery(places, status, sources, warnings, diagnostics)
