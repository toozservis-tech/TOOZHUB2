"""Browser/mobile shared service workflow over isolated storage and real authorization."""
import base64
import io
from uuid import uuid4
from datetime import datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.modules.vehicle_hub.database import Base, get_db
from src.modules.vehicle_hub.models import Customer, Tenant, Vehicle
from src.modules.vehicle_hub.ownership import ensure_vehicle_owner_assignment
from src.modules.vehicle_hub.routers_v1 import service_workspace, services, repair_photos, service_records, vehicles
from src.modules.vehicle_hub.routers_v1.auth import get_current_user
from src.modules.licensing.service import upgrade_license_plan

@pytest.fixture
def flow(tmp_path, monkeypatch):
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db=sessionmaker(bind=engine)()
    actors=[]
    for name,role in [('owner','user'),('garage','service'),('other-garage','service')]:
        tenant=Tenant(name=name,license_key=str(uuid4()));db.add(tenant);db.flush()
        user=Customer(tenant_id=tenant.id,email=name+'@example.invalid',name=name,role=role,is_disabled=False,is_deleted=False)
        db.add(user);db.flush();upgrade_license_plan(db,tenant.id,'premium');actors.append(user)
    owner=actors[0]
    vehicle=Vehicle(tenant_id=owner.tenant_id,user_email=owner.email,nickname='Web QA',plate='TEST123',vin='WVWZZZ1KZAW000001')
    db.add(vehicle);db.flush();ensure_vehicle_owner_assignment(db,vehicle=vehicle,owner=owner);db.commit()
    state={'actor':actors[1]}
    app=FastAPI()
    app.dependency_overrides[get_current_user]=lambda:state['actor']
    app.dependency_overrides[get_db]=lambda:db
    for router in [service_workspace.router,services.router,repair_photos.router,service_records.router,vehicles.router]:app.include_router(router,prefix='/api/v1')
    monkeypatch.setattr(repair_photos,'PHOTO_ROOT',tmp_path/'photos')
    def persist(path,content):path.write_bytes(content)
    monkeypatch.setattr(repair_photos,'persist_file',persist)
    monkeypatch.setattr(repair_photos,'cached_file',lambda path:path)
    with TestClient(app) as client:yield client,state,actors,vehicle
    db.close();engine.dispose()

def test_lookup_consent_history_and_photo_are_scoped_to_approved_service(flow):
    client,state,actors,vehicle=flow
    owner,garage,other=actors
    assert client.get('/api/v1/services/workspace/approved-vehicles').json()['items']==[]
    lookup=client.post('/api/v1/services/workspace/vehicle-lookup',json={'query':vehicle.plate})
    assert lookup.status_code==200,lookup.text
    candidate=lookup.json()['candidates'][0]
    assert 'owner_email' not in candidate
    assert client.get(f'/api/v1/vehicles/{vehicle.id}').status_code in (403,404)
    request=client.post('/api/v1/services/workspace/access-requests',json={'vehicle_id':vehicle.id,'lookup_query':vehicle.plate,'note':'Test opravy'})
    assert request.status_code==200,request.text
    request_id=request.json()['request_id']
    denied=client.put(f'/api/v1/services/access-requests/{request_id}',json={'decision':'approved'})
    assert denied.status_code==403
    state['actor']=owner
    assert client.get('/api/v1/services/access-requests').json()['requests'][0]['id']==request_id
    approved=client.put(f'/api/v1/services/access-requests/{request_id}',json={'decision':'approved'})
    assert approved.status_code==200,approved.text
    state['actor']=garage
    assert client.get('/api/v1/services/workspace/approved-vehicles').json()['items'][0]['id']==vehicle.id
    detail=client.get(f'/api/v1/vehicles/{vehicle.id}').json()
    assert detail['permissions']['can_create_repair_photos'] is True
    assert detail['permissions']['can_edit_vehicle'] is False
    record=client.post(f'/api/v1/vehicles/{vehicle.id}/records',json={'performed_at':datetime.now().isoformat(),'description':'Test servisního úkonu','category':'OLEJ','mileage':123456,'price':500})
    assert record.status_code in (200,201),record.text
    repair=client.post(f'/api/v1/repair-documentation/vehicles/{vehicle.id}',json={'title':'Test opravy','client_id':str(uuid4())})
    assert repair.status_code==200,repair.text
    repair_id=repair.json()['id']
    image=io.BytesIO();Image.new('RGB',(80,60),'orange').save(image,format='JPEG')
    payload={'phase':'before','note':'Před opravou','source':'library','client_id':str(uuid4()),'file_content_base64':base64.b64encode(image.getvalue()).decode()}
    photo=client.post(f'/api/v1/repair-documentation/sessions/{repair_id}/photos',json=payload)
    assert photo.status_code==200,photo.text
    photo_id=photo.json()['id']
    assert client.post(f'/api/v1/repair-documentation/sessions/{repair_id}/photos',json=payload).json()['id']==photo_id
    state['actor']=other
    assert client.get('/api/v1/services/workspace/approved-vehicles').json()['items']==[]
    assert client.get(f'/api/v1/repair-documentation/sessions/{repair_id}/photos').status_code==403
    assert client.get(f'/api/v1/repair-documentation/photos/{photo_id}/file').status_code==403
    state['actor']=owner
    assert client.get(f'/api/v1/repair-documentation/sessions/{repair_id}/photos').json()[0]['id']==photo_id
    assert client.get(f'/api/v1/vehicles/{vehicle.id}/records').json()[0]['id']==record.json()['id']
