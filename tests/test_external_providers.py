"""Provider contracts use mocked responses; no external account or network needed."""

from travel_core import duffel, geo, hotels
from travel_core.tools import search_flights, search_hotels


CHICAGO = geo.ResolvedLocation(id=1, name='Chicago', country='United States',
                               country_code='US', latitude=41.88, longitude=-87.63)
MUMBAI = geo.ResolvedLocation(id=2, name='Mumbai', country='India',
                              country_code='IN', latitude=19.07, longitude=72.88)


def _place(code, city, country, latitude, longitude):
    return {'type': 'airport', 'iata_code': code, 'iata_country_code': country,
            'name': code, 'city_name': city, 'latitude': latitude,
            'longitude': longitude}


def _offer(*, live=False, currency='USD'):
    return {'id': 'off_test_1', 'live_mode': live, 'total_amount': '1234.50',
            'total_currency': currency, 'slices': [
                {'segments': [{'operating_carrier': {'name': 'Test Airways'}},
                              {'operating_carrier': {'name': 'Test Airways'}}]},
                {'segments': [{'operating_carrier': {'name': 'Test Airways'}}]}]}


def test_duffel_resolves_airports_and_parses_round_trip_test_offers(monkeypatch):
    monkeypatch.setenv('DUFFEL_TEST_TOKEN', 'duffel_test_example')
    calls = []
    def request(path, token, *, body=None):
        calls.append((path, body))
        if 'places/suggestions' in path:
            if 'Chicago' in path:
                return {'data': [_place('YYZ', 'Chicago', 'CA', 41.9, -87.6),
                                 _place('MDW', 'Chicago', 'US', 41.79, -87.75),
                                 _place('ORD', 'Chicago', 'US', 41.98, -87.9)]}
            return {'data': [_place('BOM', 'Mumbai', 'IN', 19.09, 72.87)]}
        return {'data': {'live_mode': False, 'offers': [_offer()]}}
    monkeypatch.setattr(duffel, '_request', request)
    result = search_flights(CHICAGO.label, MUMBAI.label, '2026-12-06', '2026-12-10',
                            2, global_mode=True,
                            origin_location=CHICAGO.model_dump(),
                            destination_location=MUMBAI.model_dump())
    assert result['status'] == 'ok'
    assert result['bookable'] is False and result['live_availability_checked'] is False
    assert result['options'][0]['origin'] == 'ORD'
    assert result['options'][0]['destination'] == 'BOM'
    assert result['options'][0]['airline'] == 'Test Airways'
    assert result['options'][0]['stops'] == 1
    assert result['options'][0]['total_round_trip_usd'] == 1234.50
    assert calls[-1][1]['passengers'] == [{'type': 'adult'}, {'type': 'adult'}]
    assert [slice_['departure_date'] for slice_ in calls[-1][1]['slices']] == [
        '2026-12-06', '2026-12-10']


def test_duffel_requires_test_credentials_and_rejects_live_or_non_usd(monkeypatch):
    monkeypatch.delenv('DUFFEL_TEST_TOKEN', raising=False)
    missing = duffel.search_test_offers(CHICAGO, MUMBAI, '2026-12-06', '2026-12-10', 2)
    assert missing == {'status': 'unavailable', 'reason': 'missing_credentials', 'options': []}
    monkeypatch.setenv('DUFFEL_TEST_TOKEN', 'duffel_live_example')
    assert duffel.search_test_offers(CHICAGO, MUMBAI, '2026-12-06', '2026-12-10', 2)['reason'] == 'test_token_required'
    monkeypatch.setenv('DUFFEL_TEST_TOKEN', 'duffel_test_example')
    monkeypatch.setattr(duffel, 'resolve_airport', lambda location, token: 'ORD' if location == CHICAGO else 'BOM')
    monkeypatch.setattr(duffel, '_request', lambda *args, **kwargs: {
        'data': {'live_mode': True, 'offers': [_offer(live=True)]}})
    assert duffel.search_test_offers(CHICAGO, MUMBAI, '2026-12-06', '2026-12-10', 2)['reason'] == 'live_response_rejected'
    monkeypatch.setattr(duffel, '_request', lambda *args, **kwargs: {
        'data': {'live_mode': False, 'offers': [_offer(currency='GBP')]}})
    assert duffel.search_test_offers(CHICAGO, MUMBAI, '2026-12-06', '2026-12-10', 2)['reason'] == 'no_test_offers'


def test_duffel_timeout_and_authentication_are_nonfatal(monkeypatch):
    monkeypatch.setenv('DUFFEL_TEST_TOKEN', 'duffel_test_example')
    for reason in ('timeout', 'authentication_error'):
        def failed(*args, **kwargs):
            raise duffel.DuffelError(reason)
        monkeypatch.setattr(duffel, '_request', failed)
        assert duffel.search_test_offers(CHICAGO, MUMBAI, '2026-12-06', '2026-12-10', 2)['reason'] == reason


def test_osm_hotel_discovery_preserves_names_coordinates_and_unknown_prices(monkeypatch):
    hotels._hotel_payload.cache_clear()
    monkeypatch.setattr(hotels, '_read_json', lambda request, timeout: {'elements': [
        {'type': 'node', 'id': 1, 'lat': 19.071, 'lon': 72.881,
         'tags': {'name': 'Named Mumbai Hotel', 'tourism': 'hotel'}},
        {'type': 'node', 'id': 2, 'lat': 19.072, 'lon': 72.882,
         'tags': {'tourism': 'hotel'}},
        {'type': 'node', 'id': 3, 'lat': 20.0, 'lon': 72.88,
         'tags': {'name': 'Distant Hotel', 'tourism': 'hotel'}}]})
    result = search_hotels(MUMBAI.label, '2026-12-06', '2026-12-10', 1,
                           global_mode=True, destination_location=MUMBAI.model_dump())
    assert result['status'] == 'ok' and result['nights'] == 4
    assert len(result['options']) == 1
    property_ = result['options'][0]
    assert property_['name'] == 'Named Mumbai Hotel'
    assert property_['source_url'] == 'https://www.openstreetmap.org/node/1'
    assert property_['latitude'] == 19.071
    assert property_['total_room_cost_usd'] is None
    assert result['bookable'] is False


def test_osm_hotel_timeout_is_honest_unavailable_state(monkeypatch):
    hotels._hotel_payload.cache_clear()
    def unavailable(request, timeout):
        raise geo.GeographicDataError('Location service is unavailable: TimeoutError')
    monkeypatch.setattr(hotels, '_read_json', unavailable)
    result = search_hotels(MUMBAI.label, '2026-12-06', '2026-12-10', 1,
                           global_mode=True, destination_location=MUMBAI.model_dump())
    assert result['status'] == 'unavailable'
    assert result['reason'] == 'provider_unavailable'
    assert result['options'] == []


def test_osm_hotel_search_uses_second_public_overpass_instance(monkeypatch):
    hotels._hotel_payload.cache_clear()
    calls = []
    def provider(request, timeout):
        calls.append(request.full_url)
        if len(calls) == 1:
            raise geo.GeographicDataError('Primary unavailable')
        return {'elements': [{'type': 'node', 'id': 5, 'lat': 19.071,
                              'lon': 72.881, 'tags': {'name': 'Hotel Five', 'tourism': 'hotel'}}]}
    monkeypatch.setattr(hotels, '_read_json', provider)
    found = hotels.discover_hotels(MUMBAI)
    assert len(found) == 1 and found[0].name == 'Hotel Five'
    assert calls == [geo.OVERPASS_URL, hotels.OVERPASS_FALLBACK_URL]
