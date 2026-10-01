"""Separate real PostgreSQL transactions, synthetic accounts only."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from threading import Barrier, Event
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from src.modules.vehicle_hub.models import (
    Customer, Tenant, Vehicle, VehicleOwnership, VehicleServiceLink, ServiceRecord, VehicleTachometerHistoryEntry, ServiceAccessRequest,
)
from src.modules.vehicle_hub.ownership import (
    ensure_vehicle_owner_assignment, release_vehicle_owner_assignment, transfer_vehicle_to_new_owner,
)
from src.modules.vehicle_hub.service_access import (
    create_or_update_vehicle_service_link, require_service_vehicle_link, service_can_read_vehicle, revoke_vehicle_service_link,
)
from src.modules.vehicle_hub.routers_v1 import vehicles, repair_photos, services, service_workspace
from src.core.session_revocation import revoke_tokens, require_active_token, RevokedAccessToken
from src.core.security import create_access_token


@pytest.fixture
def fleet(pg_db, monkeypatch):
    with pg_db.sessions() as db:
        ids = {}
        for name, role in [('owner','user'), ('buyer','user'), ('buyer2','user'), ('service','service')]:
            tenant = Tenant(name=name, license_key='fixture-'+name); db.add(tenant); db.flush()
            actor = Customer(tenant_id=tenant.id, email=f'{name}@example.invalid', role=role)
            db.add(actor); db.flush(); ids[name]=actor.id
        owner = db.get(Customer, ids['owner'])
        car = Vehicle(tenant_id=owner.tenant_id, user_email=owner.email, nickname='Synthetic car',
            vin='TMBJF73T2B9044629', stk_valid_until=date(2030,1,1), current_mileage_km=200)
        db.add(car); db.flush(); ensure_vehicle_owner_assignment(db, vehicle=car, owner=owner)
        link = create_or_update_vehicle_service_link(db, tenant_id=owner.tenant_id,
            service_customer_id=ids['service'], owner_customer_id=owner.id, vehicle_id=car.id,
            approved_by_customer_id=owner.id, source_type='direct_user_grant')
        ids.update(car=car.id, link=link.id); db.commit()
    monkeypatch.setattr(vehicles, '_ensure_vehicle_photo_column', lambda db: None)
    monkeypatch.setattr(services, '_ensure_services_schema', lambda db: None)
    monkeypatch.setattr(service_workspace, '_ensure_service_workspace_schema', lambda db: None)
    return ids


def parallel(count, operation):
    barrier = Barrier(count)
    with ThreadPoolExecutor(max_workers=count) as pool:
        return list(pool.map(lambda index: operation(index, barrier), range(count)))


@pytest.mark.parametrize('known_date', [True, False])
def test_parallel_tachometer_import_is_single_history_and_record(pg_db, fleet, known_date):
    check = datetime(2026,1,1) if known_date else None
    lookup = vehicles.TachometerLookupResponse(vin='TMBJF73T2B9044629', latest_mileage_km=150,
        latest_check_date=check, inspections=[vehicles.TachometerInspectionOut(check_date=check,
            mileage_km=150, protocol_number='FIXTURE' if known_date else None)])
    def worker(index, barrier):
        with pg_db.sessions() as db:
            car = db.get(Vehicle, fleet['car']); owner = db.get(Customer, fleet['owner'])
            pid = db.scalar(text('SELECT pg_backend_pid()'))
            barrier.wait(timeout=5)
            result, record = vehicles._store_tachometer_mileage_result(vehicle=car, lookup=lookup, current_user=owner, db=db)
            return pid, record, result['current_mileage_km']
    results = parallel(6, worker)
    assert len({row[0] for row in results}) == 6
    assert len({row[1] for row in results}) == 1
    assert {row[2] for row in results} == {200}
    with pg_db.sessions() as db:
        assert db.query(ServiceRecord).count() == db.query(VehicleTachometerHistoryEntry).count() == 1


def test_simultaneous_vin_claim_has_one_winner(pg_db, fleet):
    with pg_db.sessions() as db:
        release_vehicle_owner_assignment(db, vehicle=db.get(Vehicle, fleet['car']), owner=db.get(Customer, fleet['owner'])); db.commit()
    payload = vehicles.VehicleCreateV1(nickname='Claimed fixture', vin='TMBJF73T2B9044629', stk_valid_until=date(2030,1,1))
    def worker(index, barrier):
        with pg_db.sessions() as db:
            user = db.get(Customer, fleet[['buyer','buyer2'][index]])
            barrier.wait(timeout=5)
            result = vehicles.create_vehicle(payload, current_user=user, db=db)
            return result.status_code if hasattr(result, 'status_code') else 200
    assert sorted(parallel(2, worker)) == [200,409]
    with pg_db.sessions() as db:
        assert db.query(Vehicle).count() == 1
        assignments = db.query(VehicleOwnership).filter_by(is_active=True).all()
        assert len(assignments) == 1
        assert assignments[0].customer_id in [fleet['buyer'],fleet['buyer2']]
        assert not service_can_read_vehicle(db, db.get(Customer,fleet['service']), fleet['car'])


def test_repeated_assignment_does_not_duplicate_owner(pg_db, fleet):
    def worker(index, barrier):
        with pg_db.sessions() as db:
            car=db.get(Vehicle,fleet['car']); buyer=db.get(Customer,fleet['buyer'])
            barrier.wait(timeout=5)
            assignment=ensure_vehicle_owner_assignment(db,vehicle=car,owner=buyer)
            identity=assignment.id; db.commit(); return identity
    assert len(set(parallel(4, worker))) == 1
    with pg_db.sessions() as db:
        assert db.query(VehicleOwnership).filter_by(is_active=True).count() == 1


@pytest.mark.parametrize('operation', ['approval', 'service_write'])
def test_waiting_old_permission_is_rechecked_after_transfer(pg_db, fleet, operation):
    ready=Event(); proceed=Event()
    def waiting():
        with pg_db.sessions() as db:
            service=db.get(Customer,fleet['service']); old_owner=db.get(Customer,fleet['owner'])
            # Prime ORM with old state before the transfer commits.
            db.get(VehicleServiceLink, fleet['link']); ready.set(); proceed.wait(timeout=5)
            try:
                if operation == 'approval':
                    create_or_update_vehicle_service_link(db,tenant_id=old_owner.tenant_id,
                        service_customer_id=service.id,owner_customer_id=old_owner.id,vehicle_id=fleet['car'],
                        approved_by_customer_id=old_owner.id,source_type='direct_user_grant')
                else:
                    require_service_vehicle_link(db,current_user=service,vehicle_id=fleet['car'],require_create_record=True)
                db.commit(); return 200
            except HTTPException as error:
                db.rollback(); return error.status_code
    with ThreadPoolExecutor(max_workers=1) as pool:
        result=pool.submit(waiting); assert ready.wait(timeout=5)
        with pg_db.sessions() as db:
            transfer_vehicle_to_new_owner(db,vehicle=db.get(Vehicle,fleet['car']),new_owner=db.get(Customer,fleet['buyer']))
            proceed.set()
            # While transfer holds the vehicle lock, no old grant can commit.
            assert not result.done()
            db.commit()
        assert result.result(timeout=10) in [403,409]
    with pg_db.sessions() as db:
        assert db.query(VehicleServiceLink).filter_by(status='approved').count()==0


def test_duplicate_repair_session_is_idempotent(pg_db, fleet):
    payload=repair_photos.SessionCreate(title='Synthetic visit',client_id=uuid4())
    def worker(index,barrier):
        with pg_db.sessions() as db:
            user=db.get(Customer,fleet['service']); barrier.wait(timeout=5)
            return repair_photos.create_session(fleet['car'],payload,user=user,db=db)['id']
    assert len(set(parallel(4,worker)))==1


def test_parallel_logout_is_durable_idempotent_and_scoped(pg_db, fleet):
    token=create_access_token({'sub':'owner@example.invalid','jti':uuid4().hex})
    other=create_access_token({'sub':'owner@example.invalid','jti':uuid4().hex})
    def worker(index,barrier):
        with pg_db.sessions() as db:
            barrier.wait(timeout=5); revoke_tokens(db,[token])
    parallel(6,worker)
    with pg_db.sessions() as db:
        assert db.query(RevokedAccessToken).count()==1
        with pytest.raises(HTTPException) as error: require_active_token(db,token)
        assert error.value.status_code==401
        require_active_token(db,other)


def test_concurrent_requests_and_decisions_are_not_duplicated(pg_db, fleet):
    with pg_db.sessions() as db:
        revoke_vehicle_service_link(db,service_customer_id=fleet['service'],vehicle_id=fleet['car'],
            revoked_by_customer_id=fleet['owner'],reason='Fixture'); db.commit()
    def request(index,barrier):
        with pg_db.sessions() as db:
            user=db.get(Customer,fleet['service']); barrier.wait(timeout=5)
            return service_workspace.create_service_access_request(
                service_workspace.ServiceAccessRequestCreateV1(vehicle_id=fleet['car'],lookup_query='TMBJF73T2B9044629'),
                current_user=user,db=db)['request_id']
    ids=parallel(4,request); assert len(set(ids))==1
    def decide(index,barrier):
        with pg_db.sessions() as db:
            owner=db.get(Customer,fleet['owner']); barrier.wait(timeout=5)
            try:
                services.resolve_service_access_request(ids[0],services.ServiceAccessRequestDecisionV1(decision='approved',note='Fixture consent'),current_user=owner,db=db)
                return 200
            except HTTPException as error:
                db.rollback(); return error.status_code
    assert sorted(parallel(4,decide))==[200,409,409,409]
    with pg_db.sessions() as db:
        request=db.query(ServiceAccessRequest).one()
        assert request.status=='approved' and request.decided_by_customer_id==fleet['owner']
        assert request.decided_at and request.decision_note=='Fixture consent'
        assert db.query(VehicleServiceLink).filter_by(status='approved').count()==1
