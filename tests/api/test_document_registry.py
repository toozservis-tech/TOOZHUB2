"""Public provider fixtures only. No credentials or real vehicle network calls."""
from copy import deepcopy
from types import SimpleNamespace
import json

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from src.modules.vehicle_hub.decoder import document_registry as registry
from src.modules.vehicle_hub.routers_v1 import vehicles
from src.core.rate_limiter import rate_limiter

VIN = 'TMBEFF654V7529422'
ORV = 'UAB648001'
PAYLOAD = {'Status':1, 'Data':{'VIN':VIN,'CisloOrv':ORV,'TovarniZnacka':'ŠKODA','ObchodniOznaceni':'FELICIA',
    'MotorMaxVykon':'50 / 5000','MotorZdvihObjem':1289,'PravidelnaTechnickaProhlidkaDo':'2019-11-29T00:00:00',
    'DatumPrvniRegistrace':'1997-03-21T00:00:00', 'VlastnikJmeno':'DO NOT RETURN OWNER',
    'EvidencniProhlidkaDne':'2026-10-01T00:00:00'}}

@pytest.mark.parametrize('query',[{'vin':VIN},{'orv':ORV}])
def test_only_selected_technical_data_and_exact_inspection_date(query):
    value=registry.technical_fields(PAYLOAD,registry.RegistryLookupRequest(**query))
    assert value.vin==VIN and value.engine_power_kw=='50'
    assert str(value.stk_valid_until)=='2019-11-29'
    assert value.production_year is None # First registration is not year of manufacture.
    assert 'DO NOT' not in value.model_dump_json()

@pytest.mark.parametrize('query',[{}, {'vin':VIN,'orv':ORV},{'vin':'O'*17},{'orv':'https://evil.invalid'},{'orv':'UAB648001\n'},{'vin':VIN[:-1]}])
def test_invalid_input_never_reaches_network(query):
    with pytest.raises(ValidationError): registry.RegistryLookupRequest(**query)

@pytest.mark.parametrize('change',[{'VIN':'WVWZZZ1JZXW000001'},{'CisloOrv':'UAB648002'},{'VIN':None}])
def test_unmatched_provider_vehicle_rejected(change):
    data=deepcopy(PAYLOAD);data['Data'].update(change)
    query={'orv':ORV} if 'CisloOrv' in change else {'vin':VIN}
    with pytest.raises(HTTPException) as error: registry.technical_fields(data,registry.RegistryLookupRequest(**query))
    assert error.value.status_code==502


def test_expiry_never_inferred_and_malformed_fields_ignored():
    data=deepcopy(PAYLOAD);data['Data'].update({'PravidelnaTechnickaProhlidkaDo':None,'MotorMaxVykon':{'unsafe':1},'TovarniZnacka':'x\nsecret'})
    value=registry.technical_fields(data,registry.RegistryLookupRequest(vin=VIN))
    assert value.stk_valid_until is None and value.engine_power_kw is None and value.brand is None

class Response:
    status_code=200
    def __init__(self,body):self.body=body
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def iter_content(self,chunk_size):yield self.body

@pytest.mark.parametrize('scenario',['ok','redirect','oversize','malformed','rate'])
def test_fixed_host_no_redirect_bounded_stream_and_private_errors(monkeypatch,caplog,scenario):
    calls=[]
    response=Response(json.dumps(PAYLOAD).encode())
    if scenario=='redirect':response.status_code=302
    if scenario=='rate':response.status_code=429
    if scenario=='oversize':response.body=b'x'*(registry.MAX_RESPONSE_BYTES+1)
    if scenario=='malformed':response.body=b'private-raw-body'
    class Session:
        trust_env=True
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def get(self,url,**kwargs):
            assert self.trust_env is False
            assert url==registry.REGISTRY_URL and kwargs['allow_redirects'] is False
            assert kwargs['headers']['api_key']=='private-test-key'
            assert kwargs['params']=={'vin':VIN}
            calls.append(1);return response
    monkeypatch.setattr(registry.requests,'Session',Session)
    monkeypatch.setattr(registry.config,'STK_REGISTRY_API_KEY','private-test-key')
    monkeypatch.setattr(registry.config,'DATAOVO_API_BASE_URL',registry.REGISTRY_URL)
    if scenario=='ok':assert registry.lookup_document(registry.RegistryLookupRequest(vin=VIN)).vin==VIN
    else:
        with pytest.raises(HTTPException) as error:registry.lookup_document(registry.RegistryLookupRequest(vin=VIN))
        assert 'private-' not in error.value.detail
    assert calls==[1] and 'private-test-key' not in caplog.text and VIN not in caplog.text


def test_route_requires_authenticated_user_and_limits_calls(monkeypatch):
    app=FastAPI();app.include_router(vehicles.router,prefix='/api/v1')
    calls=[]
    monkeypatch.setattr(vehicles,'lookup_document',lambda query: calls.append(query) or registry.technical_fields(PAYLOAD,query))
    rate_limiter.clear('registry-user:991232');rate_limiter.clear('registry-documents-global')
    with TestClient(app) as client:
        assert client.post('/api/v1/vehicles/registry-lookup',json={'vin':VIN}).status_code==401
        app.dependency_overrides[vehicles.get_current_user]=lambda:SimpleNamespace(id=991232)
        for _ in range(8):assert client.post('/api/v1/vehicles/registry-lookup',json={'vin':VIN}).status_code==200
        assert client.post('/api/v1/vehicles/registry-lookup',json={'vin':VIN}).status_code==429
    assert len(calls)==8
    rate_limiter.clear('registry-user:991232');rate_limiter.clear('registry-documents-global')
