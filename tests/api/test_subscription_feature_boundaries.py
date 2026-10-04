"""Actual API entitlements with synthetic data, isolated DB and provider stubs.

The stubs replace external registries/files, never billing or licensing checks.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base, get_db
from src.modules.vehicle_hub.models import Customer, Tenant, Vehicle, ServiceRecord, License, LicenseSubscription
from src.modules.vehicle_hub.ownership import ensure_vehicle_owner_assignment
from src.modules.vehicle_hub.routers_v1 import vehicles, service_records, services, analytics, vin_lookup, license_status, repair_photos
from src.modules.vehicle_hub.routers_v1.auth import get_current_user
from src.modules.vehicle_hub.decoder import router as decoder
from src.modules.vehicle_hub.decoder.document_registry import RegistryVehicle
from src.modules.licensing.service import PLAN_FEATURES, assert_feature, get_license_status, upgrade_license_plan


@pytest.fixture
def fleet(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'plans.sqlite'}", connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False)()
    actors = {}
    for name, role in [('owner','user'), ('other','user'), ('admin','admin'), ('developer','developer_admin'), ('service','service')]:
        tenant = Tenant(name=name, license_key='fixture-'+name); db.add(tenant); db.flush()
        actor = Customer(email=name+'@example.invalid', tenant_id=tenant.id, role=role); db.add(actor); db.flush()
        actors[name]=actor
    car = Vehicle(tenant_id=actors['owner'].tenant_id, user_email=actors['owner'].email,
                  nickname='Synthetic vehicle', vin='TMBJF73T2B9044629')
    db.add(car); db.flush(); ensure_vehicle_owner_assignment(db, vehicle=car, owner=actors['owner'])
    db.commit()
    monkeypatch.setattr(vehicles, '_ensure_vehicle_photo_column', lambda db: None)
    monkeypatch.setattr(service_records, 'assert_module_ready', lambda *a, **k: None)
    monkeypatch.setattr(services, '_ensure_services_schema', lambda *a: None)
    calls=[]
    monkeypatch.setattr(vehicles, 'lookup_document', lambda payload: calls.append(payload) or RegistryVehicle(vin=car.vin, brand='TEST'))
    def unexpected(*a, **k): raise AssertionError('Denied request reached external processing')
    for module, names in [(vehicles, ['create_orv_scan_record','_create_tachometer_session']),
                          (service_records, ['_store_attachment_for_vehicle','_resolve_attachment_file'])]:
        for name in names: monkeypatch.setattr(module,name,unexpected)
    app=FastAPI()
    for router in [vehicles.router,service_records.router,services.router,analytics.router,vin_lookup.router,license_status.router,repair_photos.router]:
        app.include_router(router,prefix='/api/v1')
    app.include_router(decoder.router)
    state=SimpleNamespace(db=db,actor=actors['owner'],actors=actors,car=car,calls=calls)
    app.dependency_overrides[get_db]=lambda: db
    app.dependency_overrides[get_current_user]=lambda: state.actor
    with TestClient(app) as client:
        state.client=client; yield state
    db.close(); engine.dispose()


def plan(s, value):
    upgrade_license_plan(s.db,s.actors['owner'].tenant_id,value)


@pytest.mark.parametrize('value,limit,auto,history,premium', [
    ('free',1,False,False,False),('basic',5,True,True,False),('premium',0,True,True,True)])
def test_status_and_actual_feature_routes(fleet,value,limit,auto,history,premium):
    s=fleet; plan(s,value)
    status=s.client.get('/api/v1/license/status'); assert status.status_code==200,status.text
    body=status.json(); assert body['vehicles_limit']==limit
    assert body['vin_decode_enabled']==auto
    assert body['documents_enabled']==history
    assert body['statistics_enabled']==body['costs_tracking_enabled']==body['sharing_with_service_enabled']==premium
    base=f'/api/v1/vehicles/{s.car.id}'
    assert s.client.get(base).status_code==200  # Free vehicle details stay usable.
    assert body['manual_service_records_enabled'] is True
    assert body['manual_service_records_limit']==(2 if value=='free' else None)
    assert s.client.get(base+'/records').status_code==200
    result=s.client.post('/api/v1/vehicles/registry-lookup',json={'vin':s.car.vin})
    assert result.status_code==(200 if auto else 403),result.text
    assert len(s.calls)==int(auto)
    for endpoint in ['summary','categories','monthly-costs']:
        result=s.client.get('/api/v1/analytics/'+endpoint)
        assert result.status_code==(200 if premium else 403),result.text
        if not premium: assert result.headers['X-License-Error']=='FEATURE_DISABLED'


@pytest.mark.parametrize('endpoint,payload',[
    ('/api/v1/vehicles/parse-orv',{'front_image_base64':'A'*100,'back_image_base64':'B'*100}),
    ('/api/v1/vehicles/tachometer/challenge',{}),
    ('/api/vehicles/decode-vin',{'vin':'TMBJF73T2B9044629'}),
    ('/api/vehicles/decode-plate',{'plate':'TEST001'}),
    ('/api/v1/vin/TMBJF73T2B9044629',None),
    ('/api/v1/vehicles/{id}/records/attachments/upload',{}),
    ('/api/v1/vehicles/{id}/records/document-prefill',{}),
    ('/api/v1/vehicles/{id}/records/auto-from-document',{}),
    ('/api/v1/vehicles/{id}/pdf',None),
    ('/api/v1/vehicles/{id}/records/attachments/download?key=private',None),
    ('/api/v1/repair-documentation/vehicles/{id}',None),
])
def test_free_cannot_bypass_alternative_automatic_or_document_routes(fleet,endpoint,payload):
    s=fleet; endpoint=endpoint.replace('{id}',str(s.car.id))
    result=s.client.get(endpoint) if payload is None else s.client.post(endpoint,json=payload)
    assert result.status_code==403,result.text
    assert result.headers['X-License-Error']=='FEATURE_DISABLED'
    assert s.db.query(ServiceRecord).count()==0 and not s.calls


@pytest.mark.parametrize('value,target', [('free',1),('basic',5),('premium',7)])
def test_vehicle_quota_uses_actual_create_endpoint(fleet,value,target):
    s=fleet; plan(s,value)
    for number in range(2,target+1):
        response=s.client.post('/api/v1/vehicles',json={'nickname':f'Fixture {number}'})
        assert response.status_code==200,response.text
    if value!='premium':
        response=s.client.post('/api/v1/vehicles',json={'nickname':'Over the limit'})
        assert response.status_code==403,response.text
        assert response.json()['error']['code']=='LICENSE_QUOTA_EXCEEDED'
        assert response.headers['X-License-Error']=='LICENSE_QUOTA_EXCEEDED'
    assert s.db.query(Vehicle).count()==target
    if value=='basic':
        # Existing five vehicles can still use automatic data; lookup is not an extra car.
        assert s.client.post('/api/v1/vehicles/registry-lookup',json={'vin':s.car.vin}).status_code==200


def test_upgrade_and_expiry_revoke_features_without_removing_data(fleet):
    s=fleet; plan(s,'basic');base=f'/api/v1/vehicles/{s.car.id}'
    response=s.client.post(base+'/records',json={'description':'Synthetic repair','category':'OLEJ',
        'performed_at':'2026-01-01T00:00:00','price':123})
    assert response.status_code==200,response.text
    assert s.client.get('/api/v1/analytics/summary').status_code==403
    plan(s,'premium');assert s.client.get('/api/v1/analytics/summary').json()['total_cost_czk']==123
    license=s.db.query(License).filter_by(tenant_id=s.actor.tenant_id).one()
    s.db.add(LicenseSubscription(tenant_id=s.actor.tenant_id,provider='apple',status='active',plan_current='premium'))
    license.valid_to=datetime.utcnow()-timedelta(seconds=1);s.db.commit()
    status=s.client.get('/api/v1/license/status').json()
    assert status['plan']=='free' and not status['vin_decode_enabled']
    assert s.client.get(base+'/records').json()==[]
    assert s.client.get('/api/v1/analytics/summary').status_code==403
    assert s.client.get(base).status_code==200 and s.db.query(ServiceRecord).count()==1
    s.actor=s.actors['admin'];assert s.client.get(base+'/records').status_code==200
    assert s.client.get('/api/v1/analytics/summary').status_code==200


@pytest.mark.parametrize('role',['admin','developer','service'])
def test_workspace_roles_bypass_customer_plan_but_do_not_grant_other_users_access(fleet,role):
    s=fleet;s.actor=s.actors[role]
    assert s.client.post('/api/v1/vehicles/registry-lookup',json={'vin':s.car.vin}).status_code==200
    base=f'/api/v1/vehicles/{s.car.id}'
    assert s.client.get(base+'/records').status_code==(403 if role=='service' else 200)
    s.actor=s.actors['other'];plan(s,'premium')
    assert s.client.get(base).status_code==403


def test_free_and_basic_cannot_grant_service_access(fleet):
    s=fleet
    for value in ['free','basic']:
        plan(s,value)
        result=s.client.post('/api/v1/services/vehicle-access',json={'vehicle_id':s.car.id,'service_id':s.actors['service'].id})
        assert result.status_code==403,result.text
        assert result.headers['X-License-Error']=='FEATURE_DISABLED'


def test_admin_tenant_membership_cannot_self_upgrade(fleet,monkeypatch):
    s=fleet;monkeypatch.setattr(license_status,'ADMIN_TENANT_ID',s.actor.tenant_id)
    result=s.client.post('/api/v1/license/upgrade',json={'plan':'premium'})
    assert result.status_code==403
    assert get_license_status(s.db,s.actor.tenant_id)['plan']=='free'


def test_inactive_or_missing_feature_cannot_unlock_by_plan_name(fleet):
    s=fleet;plan(s,'premium')
    license=s.db.query(License).filter_by(tenant_id=s.actor.tenant_id).one();license.status='suspended';s.db.commit()
    status=s.client.get('/api/v1/license/status').json()
    assert not any(status[key] for key in PLAN_FEATURES['premium'])
    assert status['vehicles_remaining']==0 and not status['is_unlimited']
    assert s.client.get('/api/v1/analytics/summary').status_code==403
    with pytest.raises(Exception): assert_feature(s.db,s.actor.tenant_id,'invalid')


def test_free_can_create_read_edit_two_manual_records_and_blocks_third(fleet):
    s=fleet;base=f'/api/v1/vehicles/{s.car.id}/records'
    ids=[]
    for i in range(2):
        result=s.client.post(base,json={'description':f'Manual service {i}','category':'OLEJ','performed_at':'2026-01-01T00:00:00'})
        assert result.status_code==200,result.text
        ids.append(result.json()['id'])
    denied=s.client.post(base,json={'performed_at':'2026-01-01T00:00:00','category':'OLEJ','description':'Third service'})
    assert denied.status_code==403 and denied.headers['X-License-Error']=='SERVICE_RECORD_QUOTA_EXCEEDED'
    assert len(s.client.get(base).json())==2
    assert s.client.put(base+'/'+str(ids[0]),json={'description':'Edited manual service'}).status_code==200
    assert s.client.get(base+'/'+str(ids[0])).json()['description']=='Edited manual service'
    # No forged paid attachments or import routes; another vehicle's ID is denied.
    assert s.client.put(base+'/'+str(ids[0]),json={'attachments':'[{"kind":"service_report_meta"}]'}).status_code==403
    s.actor=s.actors['other'];assert s.client.get(base).status_code==403
    s.actor=s.actors['owner'];plan(s,'basic')
    assert s.client.post(base,json={'performed_at':'2026-01-01T00:00:00','category':'OLEJ','description':'Paid third service'}).status_code==200
    assert len(s.client.get(base).json())==3
    plan(s,'free');assert len(s.client.get(base).json())==2
    assert s.client.get(base+'?include_deleted=true').status_code==403


def test_free_manual_records_do_not_unlock_paid_or_imported_history(fleet):
    s=fleet;plan(s,'basic');base=f'/api/v1/vehicles/{s.car.id}/records'
    paid=s.client.post(base,json={'performed_at':'2026-01-01T00:00:00','category':'OLEJ','description':'Paid historical record'}).json()
    plan(s,'free')
    assert s.client.get(base).json()==[]
    assert s.client.get(base+'/'+str(paid['id'])).status_code==403
    assert s.client.put(base+'/'+str(paid['id']),json={'description':'Bypass'}).status_code==403
    denied=s.client.post(base,json={'performed_at':'2026-01-01T00:00:00','category':'OLEJ','description':'Fake document','attachments':'[{"kind":"user_document"}]'})
    assert denied.status_code==403
    assert s.db.query(ServiceRecord).count()==1
