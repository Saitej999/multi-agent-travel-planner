"""City disambiguation and attraction provenance without network requests."""

from travel_core import geo


def test_city_search_disambiguates_and_handles_unknown(monkeypatch):
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
