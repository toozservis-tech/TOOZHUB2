"""Authenticated owner -> selected service -> proposal -> owner confirmation.
Synthetic temporary data only; every external network attempt fails the test.
"""
from datetime import datetime, timedelta, timezone
from uuid import uuid4
import pytest
from src.core import security
from src.modules.vehicle_hub.models import Customer, Tenant, Reservation, VehicleServiceLink, VehicleOwnership
from src.modules.vehicle_hub.booking_request_models import BookingRequest, BookingRequestEvent
from src.modules.vehicle_hub.account_erasure import erase_account
from src.modules.vehicle_hub.vehicle_update_models import VehicleUpdate
from src.modules.vehicle_hub.routers_v1 import booking_requests, reservations
from test_service_http_lifecycle import http_flow


@pytest.fixture
def flow(http_flow, monkeypatch):
    # Independent server instance per test, including the real limiter budget.
    from src.core.rate_limiter import RateLimiter
    from src.server.routers import user_auth
    monkeypatch.setattr(user_auth, 'rate_limiter', RateLimiter())
    f = http_flow
    f.client.app.include_router(booking_requests.router, prefix='/api/v1')
    f.client.app.include_router(reservations.router, prefix='/api/v1')
    with f.factory() as db:
        original = db.get(Customer, f.actors['service']['id'])
        original.workshop_same_as_registered = False
        original.workshop_city = 'Svitavy'
        tenant = Tenant(name='Second synthetic service', license_key=str(uuid4()))
        db.add(tenant); db.flush()
        second = Customer(tenant_id=tenant.id, name='Jiný servis', email='second-'+uuid4().hex+'@example.com',
            role='service', password_hash=security.hash_password(f.password), session_version=0,
            workshop_same_as_registered=False, workshop_city='Opatovec')
        db.add(second); db.flush()
        f.actors['second'] = {'id':second.id, 'email':second.email, 'role':'service'}
        db.commit()
    f.headers = {}
    for name, actor in f.actors.items():
        response = f.client.post('/user/login', json={'email':actor['email'], 'password':f.password, 'expected_role':actor['role']})
        assert response.status_code == 200
        f.headers[name] = {'Authorization':'Bearer '+response.json()['access_token']}
    f.path = '/api/v1/service-booking-requests'
    return f


def create(f, **overrides):
    payload = dict(client_id=str(uuid4()), vehicle_id=f.vehicle_id, service_id=f.actors['second']['id'],
        service_type='Olej a filtry', description='Výměna oleje a kontrola brzd', preferred_datetime=None)
    payload.update(overrides)
    r = f.client.post(f.path, headers=f.headers['owner'], json=payload)
    return payload, r


def decision(f, row, actor, action, status=200, **fields):
    payload = dict(client_id=str(uuid4()), expected_version=row['version'], action=action, message='') | fields
    r = f.client.post(f.path+f"/{row['id']}/decision", headers=f.headers[actor], json=payload)
    assert r.status_code == status, r.text
    return payload, r.json()


def test_selected_service_no_date_proposal_confirm_idempotence_and_owner_visibility(flow):
    f = flow
    assert f.client.get(f.path).status_code == 401
    body, response = create(f)
    assert response.status_code == 200, response.text
    row = response.json()
    assert row['service_name'] == 'Jiný servis' and row['preferred_datetime'] is None
    retry = f.client.post(f.path, headers=f.headers['owner'], json=body)
    assert retry.json()['id'] == row['id']
    assert f.client.post(f.path, headers=f.headers['owner'], json=body | {'description':'Changed retry'}).status_code == 409
    assert f.client.get(f.path, headers=f.headers['service']).json()['items'] == []
    assert f.client.get(f.path, headers=f.headers['stranger']).json()['items'] == []
    assert f.client.get(f.path, headers=f.headers['second']).json()['items'][0]['id'] == row['id']
    decision(f,row,'service','propose',404)
    decision(f,row,'owner','accept',403)
    decision(f,row,'second','accept',422)
    proposed = (datetime.now(timezone.utc)+timedelta(days=3)).replace(microsecond=0).isoformat()
    proposal, updated = decision(f,row,'second','propose',proposed_datetime=proposed,message='Můžeme ve středu dopoledne.')
    assert updated['status'] == 'proposed' and updated['version'] == 2
    with f.factory() as db:
        assert db.query(Reservation).count() == 0
        assert db.query(VehicleServiceLink).count() == 0
        assert db.query(VehicleUpdate).filter_by(recipient_id=f.actors['owner']['id']).count() == 1
    assert f.client.get(f.path, headers=f.headers['owner']).json()['items'][0]['service_reply'] == 'Můžeme ve středu dopoledne.'
    decision(f,row,'owner','accept_proposal',409)
    decision(f,updated,'second','accept',409)
    accepted_body, confirmed = decision(f,updated,'owner','accept_proposal')
    assert confirmed['status'] == 'confirmed' and confirmed['reservation_id']
    again = f.client.post(f.path+f"/{row['id']}/decision", headers=f.headers['owner'], json=accepted_body)
    assert again.status_code == 200 and again.json()['reservation_id'] == confirmed['reservation_id']
    owner_bookings = f.client.get('/api/v1/reservations/my', headers=f.headers['owner'])
    service_bookings = f.client.get('/api/v1/reservations/service', headers=f.headers['second'])
    assert owner_bookings.status_code == service_bookings.status_code == 200
    assert owner_bookings.json()[0]['id'] == service_bookings.json()[0]['id'] == confirmed['reservation_id']
    assert owner_bookings.json()[0]['status'] == 'CONFIRMED'
    with f.factory() as db:
        assert db.query(BookingRequest).count() == db.query(Reservation).count() == 1
        assert db.query(Reservation).one().source_platform == 'mobile_quick_booking'
        assert db.query(BookingRequestEvent).count() == 3
    assert f.external_attempts == []


def test_rejection_reason_history_and_terminal_state(flow):
    f=flow
    _,response=create(f); row=response.json()
    decision(f,row,'second','reject',422)
    _, rejected=decision(f,row,'second','reject',message='Tento typ opravy neprovádíme.')
    assert rejected['status']=='rejected'
    owner=f.client.get(f.path,headers=f.headers['owner']).json()['items'][0]
    assert owner['service_reply']=='Tento typ opravy neprovádíme.' and len(owner['events'])==2
    decision(f,rejected,'second','propose',409)
    with f.factory() as db: assert db.query(Reservation).count()==0


def test_future_requested_time_accept_and_slot_collision(flow):
    f=flow
    time=(datetime.now(timezone.utc)+timedelta(days=4)).replace(microsecond=0).isoformat()
    _,response=create(f,preferred_datetime=time); row=response.json()
    _,confirmed=decision(f,row,'second','accept')
    assert confirmed['status']=='confirmed'
    _,response2=create(f,preferred_datetime=time)
    decision(f,response2.json(),'second','accept',409)
    _,cancelled=decision(f,response2.json(),'owner','cancel')
    assert cancelled['status']=='cancelled'
    with f.factory() as db: assert db.query(Reservation).count()==1


def test_ownership_and_input_boundaries(flow):
    f=flow
    body,response=create(f,description='   '); assert response.status_code==422
    body,response=create(f,preferred_datetime='2020-01-01T00:00:00Z'); assert response.status_code==422
    body,response=create(f,service_id=f.actors['stranger']['id']); assert response.status_code==404
    body,response=create(f); row=response.json()
    assert f.client.post(f.path,headers=f.headers['stranger'],json=body | {'client_id':str(uuid4())}).status_code==403
    with f.factory() as db:
        assignment=db.query(VehicleOwnership).filter_by(vehicle_id=f.vehicle_id,is_active=True).one()
        assignment.owned_from=datetime.utcnow()+timedelta(seconds=1); db.commit()
    decision(f,row,'second','reject',409,message='Cannot modify an old ownership period')


def test_calendar_deletion_preserves_negotiation_without_foreign_key_failure(flow):
    f=flow
    time=(datetime.now(timezone.utc)+timedelta(days=4)).replace(microsecond=0).isoformat()
    _,response=create(f,preferred_datetime=time)
    _,confirmed=decision(f,response.json(),'second','accept')
    result=f.client.delete('/api/v1/reservations/'+str(confirmed['reservation_id']),headers=f.headers['owner'])
    assert result.status_code==200,result.text
    rows=f.client.get(f.path,headers=f.headers['owner']).json()['items']
    assert rows[0]['status']=='cancelled' and rows[0]['reservation_id'] is None
    assert len(rows[0]['events'])==2


def test_migration_is_additive_and_repeatable(flow):
    from scripts.migrate_booking_requests import migrate
    f=flow
    engine=f.factory.kw['bind']
    # Empty new tables represent the pre-release schema. Existing accounts/car remain.
    BookingRequestEvent.__table__.drop(engine)
    BookingRequest.__table__.drop(engine)
    migrate(engine)
    _,response=create(f); assert response.status_code==200,response.text
    migrate(engine)
    with f.factory() as db:
        assert db.query(BookingRequest).count()==1
        assert db.query(BookingRequestEvent).count()==1
        assert db.query(Customer).count()==4


@pytest.mark.parametrize('identity',['owner','second'])
def test_account_erasure_removes_only_affected_booking_graph(flow,identity):
    f=flow
    time=(datetime.now(timezone.utc)+timedelta(days=4)).replace(microsecond=0).isoformat()
    _,response=create(f,preferred_datetime=time)
    decision(f,response.json(),'second','accept')
    with f.factory() as db:
        erase_account(db,db.get(Customer,f.actors[identity]['id']))
        db.commit()
        assert db.query(BookingRequest).count()==db.query(BookingRequestEvent).count()==0
        assert db.get(Customer,f.actors['stranger']['id']) is not None


def test_reviewed_vehicle_deletion_includes_booking_history(flow):
    from src.modules.vehicle_hub.vehicle_deletion import deletion_preview, delete_reviewed_vehicle
    from src.modules.vehicle_hub.models import Vehicle
    f=flow
    time=(datetime.now(timezone.utc)+timedelta(days=4)).replace(microsecond=0).isoformat()
    _,response=create(f,preferred_datetime=time)
    decision(f,response.json(),'second','accept')
    with f.factory() as db:
        preview=deletion_preview(db,f.vehicle_id)
        assert any(i['key']=='service_booking_requests' for i in preview['items'])
        delete_reviewed_vehicle(db,f.vehicle_id,preview_token=preview['preview_token'],delete_related=True,
            actor=db.get(Customer,f.actors['owner']['id']),reason='Synthetic reviewed deletion')
        db.commit()
        assert db.get(Vehicle,f.vehicle_id) is None
        assert db.query(BookingRequest).count()==db.query(BookingRequestEvent).count()==0
        assert db.get(Customer,f.actors['second']['id']) is not None


def test_pending_request_must_be_resolved_before_archiving_vehicle(flow):
    from fastapi import HTTPException
    from src.modules.vehicle_hub.vehicle_lifecycle import ensure_no_open_work
    f=flow
    _,response=create(f)
    with f.factory() as db:
        assignment=db.query(VehicleOwnership).filter_by(vehicle_id=f.vehicle_id,is_active=True).one()
        with pytest.raises(HTTPException) as error:
            ensure_no_open_work(db,f.vehicle_id,assignment)
        assert error.value.status_code==409
    decision(f,response.json(),'owner','cancel')
    with f.factory() as db:
        assignment=db.query(VehicleOwnership).filter_by(vehicle_id=f.vehicle_id,is_active=True).one()
        ensure_no_open_work(db,f.vehicle_id,assignment)


def test_accounts_without_display_name_still_return_decodable_request(flow):
    f=flow
    with f.factory() as db:
        db.get(Customer,f.actors['second']['id']).name=None
        db.get(Customer,f.actors['owner']['id']).name=None
        db.commit()
    _,response=create(f)
    assert response.status_code==200
    row=response.json()
    assert row['service_name']==f.actors['second']['email']
    assert row['customer_name']=='Zákazník'
