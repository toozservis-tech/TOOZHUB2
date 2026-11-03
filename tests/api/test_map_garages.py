"""Provider contracts and home preferences must never create service access."""
import pytest
from fastapi import HTTPException
from test_service_invitation_consent import fixture
from src.modules.vehicle_hub import apple_garages as maps
from src.modules.vehicle_hub.routers_v1 import services
from src.modules.vehicle_hub.models import ServiceCustomerLink, ServiceAccessRequest

PLACE={'id':'MAP-123','name':'Ukázkový servis','formattedAddressLines':['Testovací 1','Opatovec'],
    'coordinate':{'latitude':49.8,'longitude':16.5}}

def test_search_provider_contract_deduplicates_and_sorts(monkeypatch):
    calls=[]
    def provider(path,params):
        calls.append((path,params))
        if len(calls)==1:return {'results':[PLACE]}
        return {'results':[{**PLACE,'id':'far','coordinate':{'latitude':49.85,'longitude':16.5}},PLACE,PLACE,{'name':'broken'}]}
    monkeypatch.setattr(maps,'_get',provider)
    result=maps.search('Opatovec')
    assert [r['id'] for r in result['items']]==['MAP-123','far']
    assert result['items'][0]['distance_km']==0
    assert calls[1][1]['includePoiCategories']=='AutomotiveRepair'
    north,east,south,west=map(float,calls[1][1]['searchRegion'].split(','))
    assert south<49.8<north and west<16.5<east
    assert all(not r['registered'] for r in result['items'])

def test_provider_failure_not_false_empty_directory(monkeypatch):
    for key in ('APPLE_MAPS_TEAM_ID','APPLE_MAPS_KEY_ID','APPLE_MAPS_PRIVATE_KEY'):monkeypatch.delenv(key,raising=False)
    with pytest.raises(HTTPException) as error:maps.search('Opatovec')
    assert error.value.status_code==503 and 'zatím není připojený' in error.value.detail

def test_detail_uses_places_response_results(monkeypatch):
    monkeypatch.setattr(maps,'_get',lambda path,params:{'results':[PLACE]})
    assert maps.detail('MAP-123')['id']=='MAP-123'


def test_home_garage_is_private_preference_not_consent(fixture,monkeypatch):
    s=fixture
    monkeypatch.setattr(maps,'detail',lambda place_id:maps.place_row({**PLACE,'id':place_id}))
    response=services.save_home_garage(services.HomeGarageSelection(apple_place_id='MAP-123'),s.owner,s.db)
    assert response['place']['id']=='MAP-123'
    assert services.read_home_garage(s.stranger,s.db)['place'] is None
    s.db.expire_all()
    assert services.read_home_garage(s.owner,s.db)['place']['id']=='MAP-123'
    services.save_home_garage(services.HomeGarageSelection(apple_place_id=None),s.owner,s.db)
    assert services.read_home_garage(s.owner,s.db)['place'] is None
    assert s.db.query(ServiceCustomerLink).count()==0
    assert s.db.query(ServiceAccessRequest).count()==0


def test_missing_provider_does_not_delete_existing_favorite(fixture,monkeypatch):
    s=fixture
    s.db.add(maps.HomeGarage(customer_id=s.owner.id,apple_place_id='MAP-123'));s.db.commit()
    def unavailable(_):raise HTTPException(503,'Mapy nejsou dostupné')
    monkeypatch.setattr(maps,'detail',unavailable)
    with pytest.raises(HTTPException):services.save_home_garage(services.HomeGarageSelection(apple_place_id='MAP-456'),s.owner,s.db)
    assert s.db.get(maps.HomeGarage,s.owner.id).apple_place_id=='MAP-123'
    # Removing a favorite remains possible during a provider outage.
    assert services.save_home_garage(services.HomeGarageSelection(),s.owner,s.db)['place'] is None


def test_native_mapkit_bookmark_does_not_need_server_key_or_grant_access(fixture,monkeypatch):
    s=fixture
    def no_server_lookup(_):raise AssertionError('Native MapKit resolves its public place on the device')
    monkeypatch.setattr(maps,'detail',no_server_lookup)
    response=services.save_home_garage(services.HomeGarageSelection(apple_place_id='MAP-123',resolve_place=False),s.owner,s.db)
    assert response=={'apple_place_id':'MAP-123','place':None}
    assert services.read_home_garage(s.owner,s.db,False)==response
    assert services.read_home_garage(s.stranger,s.db,False)['apple_place_id'] is None
    assert s.db.query(ServiceCustomerLink).count()==0
    assert s.db.query(ServiceAccessRequest).count()==0
    services.save_home_garage(services.HomeGarageSelection(resolve_place=False),s.owner,s.db)
    assert services.read_home_garage(s.owner,s.db,False)['apple_place_id'] is None
