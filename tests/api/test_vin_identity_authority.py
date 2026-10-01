"""VIN is an identifier, not proof of ownership. Synthetic DB and HTTP only."""
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, insert
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base, get_db
from src.modules.vehicle_hub.models import (
    Tenant, Customer, Vehicle, VehicleOwnership, ServiceRecord, VehicleServiceLink, ServiceCustomerInvite,
)
from src.modules.vehicle_hub.ownership import (
    ensure_vehicle_owner_assignment, release_vehicle_owner_assignment, transfer_vehicle_to_new_owner,
)
from src.modules.vehicle_hub.routers_v1 import vehicles
from src.modules.vehicle_hub.routers_v1.auth import get_current_user


@pytest.fixture
def fleet(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'identity.sqlite'}", connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False)()
    people = {}
    for name, role in [('owner','user'), ('stranger','user'), ('service','service'), ('admin','admin')]:
        tenant = Tenant(name=name, license_key=name); db.add(tenant); db.flush()
        person = Customer(tenant_id=tenant.id, email=name+'@example.invalid', role=role)
        db.add(person); db.flush(); people[name]=person
    owner = people['owner']
    car = Vehicle(tenant_id=owner.tenant_id, user_email=owner.email, nickname='Private profile',
        vin='TMBJF73T2B9044629', stk_valid_until=date(2030,1,1), notes='PRIVATE OWNER', photo_path='private-photo')
    db.add(car); db.flush(); ensure_vehicle_owner_assignment(db, vehicle=car, owner=owner)
    db.add(ServiceRecord(tenant_id=owner.tenant_id, vehicle_id=car.id, description='PRIVATE REPAIR', note='PRIVATE NOTE'))
    db.commit()
    state=SimpleNamespace(db=db, people=people, car=car, actor=owner)
    app=FastAPI(); app.include_router(vehicles.router,prefix='/api/v1')
    app.dependency_overrides[get_current_user]=lambda: state.actor
    app.dependency_overrides[get_db]=lambda: db
    monkeypatch.setattr(vehicles,'_ensure_vehicle_photo_column',lambda db:None)
    with TestClient(app) as client:
        state.client=client; yield state
    db.close(); engine.dispose()


def request(f, **extra):
    return f.client.post('/api/v1/vehicles',json={'nickname':'Attempt', 'vin':f.car.vin,
        'stk_valid_until':'2030-01-01', **extra})


@pytest.mark.parametrize('who',['stranger','service','admin'])
def test_released_vin_does_not_grant_profile_or_private_history(fleet, who):
    f=fleet; release_vehicle_owner_assignment(f.db,vehicle=f.car,owner=f.people['owner']); f.db.commit()
    f.actor=f.people[who]
    response=request(f)
    assert response.status_code==409
    for value in ['PRIVATE', 'private-photo', f.people['owner'].email]: assert value not in response.text
    assert f.db.query(VehicleOwnership).filter_by(is_active=True).count()==0
    assert f.db.query(Vehicle).count()==1
    if who!='admin':
        assert f.client.get(f'/api/v1/vehicles/{f.car.id}').status_code==403


def test_last_owner_restores_same_profile_without_duplicate_or_data_loss(fleet):
    f=fleet; release_vehicle_owner_assignment(f.db,vehicle=f.car,owner=f.actor); f.db.commit()
    response=request(f); assert response.status_code==200, response.text
    assert response.json()['id']==f.car.id and response.json()['notes']=='PRIVATE OWNER'
    assert f.db.query(Vehicle).count()==1 and f.db.query(ServiceRecord).one().note=='PRIVATE NOTE'
    assert f.db.query(VehicleOwnership).filter_by(is_active=True).count()==1
    assert request(f).status_code==409


def test_older_owner_cannot_reclaim_after_a_subsequent_owner_releases(fleet):
    f=fleet; transfer_vehicle_to_new_owner(f.db,vehicle=f.car,new_owner=f.people['stranger']); f.db.commit()
    release_vehicle_owner_assignment(f.db,vehicle=f.car,owner=f.people['stranger']); f.db.commit()
    assert request(f).status_code==409
    f.actor=f.people['stranger']; assert request(f).status_code==200


def test_email_alias_alone_never_proves_ownership(fleet):
    f=fleet; f.db.query(VehicleOwnership).delete(); f.car.user_email=f.people['stranger'].email; f.db.commit()
    f.actor=f.people['stranger']; assert request(f).status_code==409


def test_preregistered_car_requires_the_invited_verified_account_and_active_invite(fleet):
    from src.modules.vehicle_hub.email_verification import EmailVerification
    f=fleet; f.db.query(VehicleOwnership).delete(); f.car.user_email=f.actor.email
    f.car.tenant_id=f.people['service'].tenant_id
    f.db.add(VehicleServiceLink(tenant_id=f.car.tenant_id,service_customer_id=f.people['service'].id,
        owner_customer_id=f.people['service'].id, vehicle_id=f.car.id,status='approved',source_type='pending_owner_registration'))
    invite=ServiceCustomerInvite(service_tenant_id=f.car.tenant_id,service_customer_id=f.people['service'].id,
        invite_email=f.actor.email,token='synthetic-not-a-real-secret',status='pending',expires_at=datetime.utcnow()+timedelta(days=1))
    verification=EmailVerification(customer_id=f.actor.id)
    f.db.add_all([invite,verification]); f.db.commit()
    assert request(f).status_code==409
    verification.verified_at=datetime.utcnow(); f.db.commit()
    invite.status='cancelled'; f.db.commit(); assert request(f).status_code==409
    invite.status='pending'; invite.expires_at=datetime.utcnow()-timedelta(days=1)
    f.db.commit(); assert request(f).status_code==409
    invite.expires_at=datetime.utcnow()+timedelta(days=1); f.db.commit()
    assert request(f).status_code==200
    assert f.db.query(VehicleServiceLink).one().status=='revoked'


@pytest.mark.parametrize('operation',['create','edit','batch'])
def test_all_orm_writers_reject_normalized_vin_duplicates_across_tenants(fleet,operation):
    f=fleet; other=f.people['stranger']
    car=Vehicle(tenant_id=other.tenant_id,user_email=other.email,nickname='Other',vin=None)
    f.db.add(car)
    if operation=='edit': f.db.commit()
    car.vin='tmb jf73t2b9-044629'
    if operation=='batch':
        # Two new rows also conflict before either has an assigned database ID.
        car.vin='WVWZZZ1JZXW000001'
        f.db.add(Vehicle(tenant_id=other.tenant_id,user_email=other.email,vin=car.vin))
    with pytest.raises(HTTPException) as denied: f.db.flush()
    assert denied.value.status_code==409
    f.db.rollback(); assert f.db.query(Vehicle).filter(Vehicle.vin.is_not(None)).count()==1


def test_vinless_vehicles_can_be_added_and_unrelated_legacy_rows_are_preserved(fleet):
    f=fleet
    for name in ['First','Second']:
        f.db.add(Vehicle(tenant_id=f.actor.tenant_id,user_email=f.actor.email,nickname=name))
    f.db.commit(); assert f.db.query(Vehicle).count()==3
    # Simulate a legacy import outside ORM protection. Ordinary metadata edits
    # must not delete/merge existing ambiguous identities during rollout.
    f.db.execute(insert(Vehicle).values(tenant_id=f.actor.tenant_id,user_email=f.actor.email,vin=f.car.vin))
    f.db.commit(); f.car.notes='Changed by original owner'; f.db.commit()
    assert f.db.query(Vehicle).count()==4
    assert request(f).status_code==409  # Never pick an arbitrary duplicate.


def test_restore_does_not_bypass_inactive_license(fleet):
    from src.modules.vehicle_hub.models import License
    f=fleet; release_vehicle_owner_assignment(f.db,vehicle=f.car,owner=f.actor)
    f.db.add(License(tenant_id=f.actor.tenant_id,plan='free',status='disabled',vehicles_limit=1))
    f.db.commit()
    response=request(f); assert response.status_code==403
    assert response.json()['error']['code']=='LICENSE_INACTIVE'
    assert f.db.query(VehicleOwnership).filter_by(is_active=True).count()==0
