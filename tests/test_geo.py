"""City disambiguation and attraction provenance without network requests."""

import pytest

from travel_core import geo


def test_city_search_disambiguates_and_handles_unknown(monkeypatch):
    geo._search_cities_cached.cache_clear()
    monkeypatch.setattr(geo, '_read_json', lambda request, timeout: {
        'results': [
            {'id': 1, 'name': 'Paris', 'country': 'France', 'admin1': 'Île-de-France',
             'latitude': 48.86, 'longitude': 2.35},
            {'id': 2, 'name': 'Paris', 'country': 'United States', 'admin1': 'Texas',
             'latitude': 33.66, 'longitude': -95.56},
        ]})
    found = geo.search_cities('Paris')
    assert [item.label for item in found] == [
        'Paris, Île-de-France, France', 'Paris, Texas, United States']
    monkeypatch.setattr(geo, '_read_json', lambda request, timeout: {'results': []})
    assert geo.search_cities('Unknown place') == []


def test_repeated_city_search_reuses_bounded_cache(monkeypatch):
    geo._search_cities_cached.cache_clear()
    calls = []

    def provider(request, timeout):
        calls.append(request)
        return {'results': [{'id': 3169070, 'name': 'Rome', 'country': 'Italy',
                             'admin1': 'Lazio', 'country_code': 'IT',
                             'latitude': 41.9, 'longitude': 12.5}]}

    monkeypatch.setattr(geo, '_read_json', provider)
    first = geo.search_cities(' Rome ')
    second = geo.search_cities('Rome')
    assert len(calls) == 1
    assert first == second
    assert first is not second


def test_overpass_results_are_named_deduplicated_and_sourced(monkeypatch):
    city = geo.ResolvedLocation(id=1, name='Rome', region='Lazio', country='Italy',
                                latitude=41.9, longitude=12.5)
    monkeypatch.setattr(geo, '_read_json', lambda request, timeout: {
        'elements': [
            {'type': 'node', 'id': 10, 'lat': 41.91, 'lon': 12.51,
             'tags': {'name': 'Museum A', 'tourism': 'museum'}},
            {'type': 'node', 'id': 11, 'lat': 41.91, 'lon': 12.51,
             'tags': {'name': 'Museum A', 'tourism': 'museum'}},
            {'type': 'node', 'id': 12, 'lat': 41.92, 'lon': 12.52,
             'tags': {'tourism': 'museum'}},
        ]})
    found = geo.discover_attractions(city)
    assert len(found) == 1
    assert found[0].name == 'Museum A'
    assert found[0].source == 'OPENSTREETMAP_OVERPASS'


def test_wikipedia_fallback_filters_unrelated_pages_and_preserves_source(monkeypatch):
    city = geo.ResolvedLocation(id=1, name='Rome', country='Italy',
                                latitude=41.9, longitude=12.5)
    def provider(request, timeout):
        assert 'generator=geosearch' in request.full_url
        assert timeout == 12
        assert 'colimit=max' in request.full_url
        assert 'cllimit=max' in request.full_url
        return {'query': {'pages': [
            {'pageid': 10, 'title': 'Roman Museum', 'categories': [
                {'title': 'Category:Museums in Rome'}],
             'coordinates': [{'lat': 41.901, 'lon': 12.501}]},
            {'pageid': 11, 'title': 'Local politician', 'categories': [
                {'title': 'Category:Politicians from Rome'}],
             'coordinates': [{'lat': 41.901, 'lon': 12.501}]},
            {'pageid': 12, 'title': 'Distant Park', 'categories': [
                {'title': 'Category:Parks in Italy'}],
             'coordinates': [{'lat': 42.9, 'lon': 12.5}]},
        ]}}
    monkeypatch.setattr(geo, '_read_json', provider)
    found = geo.discover_wikipedia_attractions(city)
    assert [(item.name, item.source) for item in found] == [
        ('Roman Museum', 'WIKIPEDIA_GEOSEARCH')]
    assert found[0].source_url == 'https://en.wikipedia.org/?curid=10'


def test_wikipedia_rejects_unrelated_pages_with_place_categories():
    city = geo.ResolvedLocation(id=1, name='Paris', country='France',
                                latitude=48.85, longitude=2.35)
    assert geo._wikipedia_category({'title': '1995 France bombings', 'categories': [
        {'title': 'Category:Markets in Paris'}]}, city) is None
    assert geo._wikipedia_category({'title': '18th Avenue station', 'categories': [
        {'title': 'Category:Parks in Paris'}]}, city) is None
    assert geo._wikipedia_category({'title': 'Old Theatre', 'categories': [
        {'title': 'Category:Theatres in Paris'},
        {'title': 'Category:Demolished theatres in Paris'}]}, city) is None


def test_attraction_discovery_falls_back_and_never_invents_places(monkeypatch):
    city = geo.ResolvedLocation(id=1, name='Rome', country='Italy',
                                latitude=41.9, longitude=12.5)
    def unavailable(location):
        raise geo.GeographicDataError('Location service is unavailable: TimeoutError')
    museum = geo.Attraction(id='wikipedia:10', name='Roman Museum', category='museum',
                            latitude=41.9, longitude=12.5, source='WIKIPEDIA_GEOSEARCH')
    monkeypatch.setattr(geo, 'discover_attractions', unavailable)
    monkeypatch.setattr(geo, 'discover_wikipedia_attractions', lambda location: [museum])
    partial = geo.find_attractions(city)
    assert partial.status == 'partial'
    assert partial.attractions == [museum]
    assert partial.sources == ['WIKIPEDIA_GEOSEARCH']
    assert any('OpenStreetMap' in warning for warning in partial.warnings)

    monkeypatch.setattr(geo, 'discover_wikipedia_attractions', unavailable)
    empty = geo.find_attractions(city)
    assert empty.status == 'partial'
    assert empty.attractions == []
    assert empty.sources == []
    assert any('No verified attractions' in warning for warning in empty.warnings)


def test_overpass_timeout_and_error_remark_are_recoverable(monkeypatch):
    city = geo.ResolvedLocation(id=1, name='Rome', country='Italy',
                                latitude=41.9, longitude=12.5)
    geo._overpass_payload.cache_clear()
    def timeout(request, timeout):
        raise geo.GeographicDataError('Location service is unavailable: TimeoutError')
    monkeypatch.setattr(geo, '_read_json', timeout)
    with pytest.raises(geo.GeographicDataError, match='TimeoutError'):
        geo.discover_attractions(city)
    monkeypatch.setattr(geo, '_read_json', lambda request, timeout: {
        'remark': 'runtime error: Query timed out', 'elements': []})
    with pytest.raises(geo.GeographicDataError, match='could not complete'):
        geo.discover_attractions(city)


def test_partial_discovery_can_retry_both_providers(monkeypatch):
    city = geo.ResolvedLocation(id=1, name='Rome', country='Italy',
                                latitude=41.899, longitude=12.499)
    geo._overpass_payload.cache_clear()
    geo._wikipedia_payload.cache_clear()
    calls = []
    def provider(request, timeout):
        calls.append(request.full_url)
        if 'wikipedia.org' in request.full_url:
            return {'query': {'pages': []}}
        return {'elements': []}
    monkeypatch.setattr(geo, '_read_json', provider)
    assert geo.find_attractions(city, min_places=2).status == 'partial'
    assert geo.find_attractions(city, min_places=2).status == 'partial'
    assert len(calls) == 6


@pytest.mark.parametrize('name,country,code,latitude,longitude', [
    ('Rome', 'Italy', 'IT', 41.9, 12.5),
    ('Paris', 'France', 'FR', 48.86, 2.35),
    ('Tokyo', 'Japan', 'JP', 35.68, 139.69),
    ('New York', 'United States', 'US', 40.71, -74.0),
])
def test_international_city_coordinates_survive_geocoding(monkeypatch, name, country, code,
                                                           latitude, longitude):
    geo._search_cities_cached.cache_clear()
    monkeypatch.setattr(geo, '_read_json', lambda request, timeout: {'results': [{
        'id': 42, 'name': name, 'country': country, 'country_code': code,
        'latitude': latitude, 'longitude': longitude}]})
    found = geo.search_cities(name)[0]
    assert (found.name, found.country_code, found.latitude, found.longitude) == (
        name, code, latitude, longitude)
