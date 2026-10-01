from datetime import date
import json

import pytest
import requests
from src.modules.vehicle_hub.decoder import inspection_validity as target

VIN = 'TMBJF73T2B9044629'


def payload(value='2028-02-29T00:00:00'):
    return {'Status': 1, 'Data': {'VIN': VIN, 'PravidelnaTechnickaProhlidkaDo': value}}


@pytest.mark.parametrize('value,expected', [('2028-02-29T00:00:00', date(2028, 2, 29)), ('2024-04-22', date(2024, 4, 22)), ('2028-02-29T00:00:00+02:00', date(2028, 2, 29))])
def test_explicit_registry_date_including_expired_is_preserved(value, expected):
    result = target.parse_registry_expiry(payload(value), VIN)
    assert result.status == 'verified'
    assert result.valid_until == expected


@pytest.mark.parametrize('value', [None, '', '2027-02-29', '2028-04-31', '0001-01-01', '2028', 2028, True, {}, '2028-02-29 ignored', '2028-02-29T99:00:00'])
def test_missing_malformed_or_sentinel_never_becomes_a_date(value):
    assert target.parse_registry_expiry(payload(value), VIN).valid_until is None


def test_identification_inspection_or_last_inspection_date_cannot_be_expiry():
    p = payload(None)
    p['Data'].update(InspectionDate='2030-01-01', EvidencniProhlidkaDne='2031-01-01', PlatnostEmisiDo='2032-01-01')
    assert target.parse_registry_expiry(p, VIN).valid_until is None


@pytest.mark.parametrize('mutate', [lambda p: p.update(Status=0), lambda p: p.update(Status=True), lambda p: p['Data'].update(VIN='TMBJF73T2B9044628'), lambda p: p['Data'].pop('VIN'), lambda p: p.update(Data=[])])
def test_requires_success_and_matching_vehicle(mutate):
    p = payload()
    mutate(p)
    assert target.parse_registry_expiry(p, VIN).valid_until is None


class Response:
    status_code = 200
    body = json.dumps(payload()).encode()
    closed = False
    def __enter__(self): return self
    def __exit__(self, *args): self.closed = True
    def iter_content(self, **kwargs): yield self.body


class Session:
    trust_env = True
    response = Response()
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def get(self, url, **kwargs):
        assert url == target.REGISTRY_URL
        assert self.trust_env is False
        assert kwargs['allow_redirects'] is False
        assert kwargs['stream'] is True
        assert kwargs['params'] == {'vin': VIN}
        assert kwargs['headers']['api_key'] == 'fixture-key'
        return self.response


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setattr(target.config, 'STK_REGISTRY_API_KEY', '')
    monkeypatch.setattr(target.config, 'DATAOVO_API_KEY', 'fixture-key')
    monkeypatch.setattr(target.config, 'DATAOVO_API_BASE_URL', target.REGISTRY_URL)
    monkeypatch.setattr(target.requests, 'Session', Session)
    monkeypatch.setattr(Session, 'response', Response())


def test_bounded_official_transport(configured):
    assert target.fetch_inspection_validity(VIN).status == 'verified'
    assert Session.response.closed


@pytest.mark.parametrize('status', [301, 302, 403, 429, 500])
def test_redirects_errors_limits_do_not_fail_mileage_import(configured, status):
    Session.response.status_code = status
    assert target.fetch_inspection_validity(VIN).status == 'unavailable'
    assert Session.response.closed


@pytest.mark.parametrize('body', [b'not-json', b'[]', b'x' * (target.MAX_RESPONSE_BYTES + 1)])
def test_unusable_body_is_ignored(configured, body):
    Session.response.body = body
    assert target.fetch_inspection_validity(VIN).valid_until is None


def test_timeout_remains_partial_success(configured, monkeypatch):
    def timeout(*args, **kwargs): raise requests.Timeout('do not log this')
    monkeypatch.setattr(Session, 'get', timeout)
    assert target.fetch_inspection_validity(VIN).status == 'unavailable'


@pytest.mark.parametrize('key,url', [('', target.REGISTRY_URL), ('fixture-key', 'http://api.dataovozidlech.cz/api/vehicletechnicaldata/v2'), ('fixture-key', 'https://elsewhere.invalid')])
def test_no_key_or_wrong_destination_never_sends_request(configured, monkeypatch, key, url):
    monkeypatch.setattr(target.config, 'DATAOVO_API_KEY', key)
    monkeypatch.setattr(target.config, 'DATAOVO_API_BASE_URL', url)
    def forbidden(): pytest.fail('Must not contact unconfigured registry')
    monkeypatch.setattr(target.requests, 'Session', forbidden)
    assert target.fetch_inspection_validity(VIN).status == 'not_configured'


def test_stk_specific_key_does_not_require_activating_legacy_decoder(configured, monkeypatch):
    monkeypatch.setattr(target.config, 'STK_REGISTRY_API_KEY', 'fixture-key')
    monkeypatch.setattr(target.config, 'DATAOVO_API_KEY', '')
    assert target.fetch_inspection_validity(VIN).status == 'verified'
