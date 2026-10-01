"""Unknown STK stays null through real HTTP forms, storage and reminders.

Uses synthetic identities and a disposable database, never real accounts or mail.
"""
from datetime import date, datetime
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base, get_db
from src.modules.vehicle_hub.models import Customer, Tenant, Vehicle, ServiceCustomerLink
from src.modules.vehicle_hub.ownership import release_vehicle_owner_assignment
from src.modules.vehicle_hub.routers_v1 import vehicles, service_workspace, reminders
from src.modules.vehicle_hub.routers_v1.auth import get_current_user
from src.modules.licensing import service as licensing


@pytest.fixture
def scenario(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path/'inspection.sqlite'}", connect_args={'check_same_thread':False})
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine,autoflush=False)()
    tenant = Tenant(name='Inspection fixture',license_key='inspection-fixture'); db.add(tenant); db.flush()
    owner = Customer(tenant_id=tenant.id,email='owner@example.com',role='user')
    service = Customer(tenant_id=tenant.id,email='service@example.com',role='service')
    other = Customer(tenant_id=tenant.id,email='other@example.com',role='user')
    db.add_all([owner,service,other]); db.flush()
    db.add(ServiceCustomerLink(service_tenant_id=tenant.id,service_customer_id=service.id,
        customer_tenant_id=tenant.id,customer_id=owner.id,status='active',
        consented_at=datetime.utcnow(),consented_by_customer_id=owner.id)); db.commit()
    monkeypatch.setattr(licensing,'assert_vehicle_quota',lambda *a,**kw:None)
    monkeypatch.setattr(licensing,'assert_feature',lambda *a,**kw:None)
    monkeypatch.setattr(vehicles,'_ensure_vehicle_photo_column',lambda db:None)
    monkeypatch.setattr(service_workspace,'_ensure_service_workspace_schema',lambda db:None)
    def reject_email(*args, **kwargs):
        pytest.fail('The existing-customer fixture must not send an invitation')
    monkeypatch.setattr(service_workspace,'_send_invitation_email',reject_email)
    monkeypatch.setattr(reminders,'_ensure_reminders_schema',lambda db:None)
    state = SimpleNamespace(db=db,owner=owner,service=service,other=other,actor=owner)
    app=FastAPI()
    for router in [vehicles.router,service_workspace.router,reminders.router]: app.include_router(router,prefix='/api/v1')
    app.dependency_overrides[get_current_user]=lambda:state.actor
    app.dependency_overrides[get_db]=lambda:db
    with TestClient(app) as client:
        state.client=client
        yield state
    db.close(); engine.dispose()


def create(s, **fields):
    response=s.client.post('/api/v1/vehicles',json={'nickname':'Synthetic car',**fields})
    assert response.status_code==200,response.text
    return response.json()


@pytest.mark.parametrize('fields', [{},{'stk_valid_until':None},{'stk_valid_until':'2028-02-29'},{'stk_valid_until':'2001-01-01'}])
def test_customer_create_and_read_preserve_unknown_or_explicit_date(scenario,fields):
    s=scenario; data=create(s,**fields)
    expected=fields.get('stk_valid_until')
    assert data['stk_valid_until']==expected
    assert s.client.get(f"/api/v1/vehicles/{data['id']}").json()['stk_valid_until']==expected
    row=s.db.get(Vehicle,data['id'])
    assert row.stk_valid_until==(date.fromisoformat(expected) if expected else None)


@pytest.mark.parametrize('value',['','2027-02-29','tomorrow',123,True])
def test_invalid_date_is_rejected_without_creating_a_vehicle(scenario,value):
    s=scenario
    response=s.client.post('/api/v1/vehicles',json={'nickname':'Invalid date','stk_valid_until':value})
    assert response.status_code==422,response.text
    assert s.db.query(Vehicle).count()==0


def test_partial_edit_preserves_expiry_but_explicit_null_clears_it(scenario):
    s=scenario; data=create(s,stk_valid_until='2030-05-06'); url=f"/api/v1/vehicles/{data['id']}"
    response=s.client.put(url,json={'nickname':'Renamed'}); assert response.status_code==200,response.text
    assert response.json()['stk_valid_until']=='2030-05-06'
    response=s.client.put(url,json={'stk_valid_until':None}); assert response.status_code==200,response.text
    assert response.json()['stk_valid_until'] is None
    response=s.client.put(url,json={'nickname':'Renamed again'})
    assert response.json()['stk_valid_until'] is None
    assert s.db.get(Vehicle,data['id']).stk_valid_until is None


@pytest.mark.parametrize('date_value',[None,'2030-05-06'])
@pytest.mark.parametrize('pending',[False,True])
def test_service_customer_and_pending_registration_keep_optional_date(scenario,date_value,pending):
    s=scenario; s.actor=s.service
    payload={'nickname':'Service fixture','stk_valid_until':date_value}
    if pending:
        payload['vin']='TMBJF73T2B9044629'
        response=s.client.post('/api/v1/services/workspace/pending-vehicles',json={'invite_email':s.owner.email,'vehicle':payload})
    else:
        response=s.client.post(f'/api/v1/services/workspace/customers/{s.owner.id}/vehicles',json=payload)
    assert response.status_code==200,response.text
    body=response.json(); vehicle_id=body['vehicle_id'] if pending else body['id']
    s.actor=s.owner
    assert s.client.get(f'/api/v1/vehicles/{vehicle_id}').json()['stk_valid_until']==date_value


def test_unknown_dates_do_not_create_expiry_reminders(scenario):
    s=scenario; data=create(s); url=f"/api/v1/vehicles/{data['id']}"
    def stk_reminders():
        response=s.client.get('/api/v1/reminders'); assert response.status_code==200,response.text
        return [item for item in response.json() if item['type']=='STK']
    assert stk_reminders()==[]
    response=s.client.put(url,json={'stk_valid_until':date.today().isoformat()}); assert response.status_code==200
    assert len(stk_reminders())==1
    response=s.client.put(url,json={'stk_valid_until':None}); assert response.status_code==200
    assert stk_reminders()==[]


def test_other_account_cannot_clear_a_known_inspection(scenario):
    s=scenario; data=create(s,stk_valid_until='2030-05-06'); s.actor=s.other
    response=s.client.put(f"/api/v1/vehicles/{data['id']}",json={'stk_valid_until':None})
    assert response.status_code==403
    assert s.db.get(Vehicle,data['id']).stk_valid_until==date(2030,5,6)


def test_restoring_previous_ownership_without_date_preserves_known_evidence(scenario):
    s=scenario; data=create(s,vin='TMBJF73T2B9044629',stk_valid_until='2030-05-06')
    car=s.db.get(Vehicle,data['id'])
    release_vehicle_owner_assignment(s.db,vehicle=car,owner=s.owner); s.db.commit()
    restored=create(s,vin=car.vin,stk_valid_until=None)
    assert restored['id']==car.id and restored['stk_valid_until']=='2030-05-06'
