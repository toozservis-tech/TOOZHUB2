"""Isolated lifecycle and authorization checks; no production accounts or requests."""
from uuid import uuid4
from datetime import datetime
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import Tenant, Customer, Vehicle, VehicleOwnership, VehicleServiceLink, ServiceRecord, ServiceRecordAuditLog
from src.modules.vehicle_hub.service_job_models import ServiceJob, ServiceJobEvent
from src.modules.vehicle_hub.routers_v1.service_jobs import create_job, update_job, get_job, list_jobs, JobCreate, JobUpdate


@pytest.fixture
def ctx(tmp_path):
    engine = create_engine(f'sqlite:///{tmp_path}/jobs.sqlite')
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine)() as db:
        tenant = Tenant(name='Jobs test', license_key=str(uuid4()))
        db.add(tenant); db.flush()
        owner = Customer(tenant_id=tenant.id, email='owner@example.test', role='user', password_hash='test')
        service = Customer(tenant_id=tenant.id, email='service@example.test', role='service', password_hash='test')
        stranger = Customer(tenant_id=tenant.id, email='stranger@example.test', role='admin', password_hash='test')
        db.add_all([owner, service, stranger]); db.flush()
        vehicle = Vehicle(tenant_id=tenant.id, user_email=owner.email, vin='TMBAB7NE0F0123456', brand='Skoda', model='Octavia', plate='TEST001')
        db.add(vehicle); db.flush()
        assignment = VehicleOwnership(tenant_id=tenant.id, vehicle_id=vehicle.id, customer_id=owner.id,
            ownership_type='owner', is_primary=True, is_active=True, assigned_by_customer_id=owner.id,
            assigned_at=datetime.utcnow(), created_at=datetime.utcnow(), updated_at=datetime.utcnow())
        link = VehicleServiceLink(tenant_id=tenant.id, vehicle_id=vehicle.id, owner_customer_id=owner.id,
            service_customer_id=service.id, status='approved', scope_vehicle_history_read=True,
            scope_create_service_record=True)
        db.add_all([assignment, link]); db.commit()
        yield db, owner, service, stranger, vehicle, assignment, link
    engine.dispose()


def accept(ctx):
    db, _, service, _, vehicle, _, _ = ctx
    data = JobCreate(client_id=uuid4(), title='Výměna brzd', description='Kontrola brzd', mileage=120000)
    return create_job(vehicle.id, data, service, db), data


def test_lifecycle_creates_exactly_one_audited_record_and_retries(ctx):
    db, owner, service, _, vehicle, _, _ = ctx
    job, creation = accept(ctx)
    assert job['status'] == 'received'
    assert create_job(vehicle.id, creation, service, db)['id'] == job['id']
    start = JobUpdate(client_id=uuid4(), expected_version=1, status='in_progress', message='Práce zahájena')
    assert update_job(job['id'], start, service, db)['version'] == 2
    note = JobUpdate(client_id=uuid4(), expected_version=2, message='Nové destičky namontovány')
    assert update_job(job['id'], note, service, db)['version'] == 3
    finish = JobUpdate(client_id=uuid4(), expected_version=3, status='completed', message='Brzdy vyměněny a přezkoušeny', price=2500)
    completed = update_job(job['id'], finish, service, db)
    assert completed['status'] == 'completed' and completed['final_record_id']
    assert update_job(job['id'], finish, service, db)['final_record_id'] == completed['final_record_id']
    assert db.query(ServiceRecord).count() == 1
    record = db.query(ServiceRecord).one()
    assert record.created_by_service_customer_id == service.id and record.service_access_link_id
    assert db.query(ServiceRecordAuditLog).one().snapshot_hash == record.snapshot_hash
    assert len(get_job(job['id'], owner, db)['events']) == 4
    assert len(list_jobs(vehicle.id, owner, db)['items']) == 1
    with pytest.raises(HTTPException) as error:
        update_job(job['id'], JobUpdate(client_id=uuid4(), expected_version=4, message='Přepsat dokončení'), service, db)
    assert error.value.status_code == 409


def test_conflicting_uuid_stale_version_and_direct_completion_are_rejected(ctx):
    db, _, service, _, vehicle, _, _ = ctx
    job, creation = accept(ctx)
    with pytest.raises(HTTPException) as error:
        create_job(vehicle.id, JobCreate(client_id=creation.client_id, title='Jiná práce'), service, db)
    assert error.value.status_code == 409
    for update in [JobUpdate(client_id=uuid4(), expected_version=8, message='Zastaralý klient'),
                   JobUpdate(client_id=uuid4(), expected_version=1, status='completed', message='Přeskočit přijetí')]:
        with pytest.raises(HTTPException) as error:
            update_job(job['id'], update, service, db)
        assert error.value.status_code == 409
    assert db.query(ServiceRecord).count() == 0
    assert db.query(ServiceJobEvent).count() == 1


def test_no_admin_shortcut_and_revocation_blocks_service_but_not_owner(ctx):
    db, owner, service, stranger, _, _, link = ctx
    job, _ = accept(ctx)
    with pytest.raises(HTTPException):
        get_job(job['id'], stranger, db)
    with pytest.raises(HTTPException):
        update_job(job['id'], JobUpdate(client_id=uuid4(), expected_version=1, message='Změna majitelem'), owner, db)
    link.status = 'revoked'; db.commit()
    with pytest.raises(HTTPException):
        get_job(job['id'], service, db)
    with pytest.raises(HTTPException):
        update_job(job['id'], JobUpdate(client_id=uuid4(), expected_version=1, message='Po odebrání'), service, db)
    assert get_job(job['id'], owner, db)['id'] == job['id']


def test_transfer_hides_old_private_timeline_from_both_owners_and_service(ctx):
    db, owner, service, stranger, vehicle, assignment, _ = ctx
    job, _ = accept(ctx)
    assignment.customer_id = stranger.id; db.commit()
    for actor in (owner, stranger, service):
        with pytest.raises(HTTPException) as error:
            get_job(job['id'], actor, db)
        assert error.value.status_code == 404
    assert list_jobs(vehicle.id, stranger, db)['items'] == []
    with pytest.raises(HTTPException):
        update_job(job['id'], JobUpdate(client_id=uuid4(), expected_version=1, message='Po převodu'), service, db)
    assert db.query(ServiceJob).one().version == 1


def test_cancelled_job_is_immutable_and_has_no_final_record(ctx):
    db, _, service, _, _, _, _ = ctx
    job, _ = accept(ctx)
    cancel = JobUpdate(client_id=uuid4(), expected_version=1, status='cancelled', message='Majitel zakázku zrušil')
    result = update_job(job['id'], cancel, service, db)
    assert result['status'] == 'cancelled' and result['final_record_id'] is None
    assert update_job(job['id'], cancel, service, db)['version'] == 2
    with pytest.raises(HTTPException):
        update_job(job['id'], JobUpdate(client_id=uuid4(), expected_version=2, status='in_progress', message='Obnovení'), service, db)
    assert db.query(ServiceRecord).count() == 0


def test_existing_intake_creates_one_job_and_owner_alert_atomically(ctx):
    from src.modules.vehicle_hub.routers_v1.service_intake import create_service_intake
    from src.modules.vehicle_hub.routers_v1.schemas import ServiceIntakeCreateV1
    from src.modules.vehicle_hub.routers_v1.service_jobs import create_job_from_intake
    from src.modules.vehicle_hub.vehicle_update_models import VehicleUpdate
    db, owner, service, _, vehicle, _, _ = ctx
    intake = create_service_intake(ServiceIntakeCreateV1(vehicle_id=vehicle.id, customer_id=owner.id,
        odometer_km=121000, work_description='Kontrola poškozeného ložiska'), service, db)
    job = db.query(ServiceJob).one()
    assert job.intake_id == intake.id and job.status == 'received'
    assert job.mileage == 121000 and job.owner_id == owner.id
    assert create_job_from_intake(db, intake=intake, current_user=service).id == job.id
    assert db.query(ServiceJobEvent).count() == 1
    event = db.query(VehicleUpdate).one()
    assert event.event_type == 'job.received' and event.service_job_id == job.id


def test_completion_transaction_rolls_back_job_record_audit_and_alert(ctx, monkeypatch):
    from src.modules.vehicle_hub.routers_v1 import service_jobs
    from src.modules.vehicle_hub.vehicle_update_models import VehicleUpdate
    db, _, service, _, _, _, _ = ctx
    job, _ = accept(ctx)
    update_job(job['id'], JobUpdate(client_id=uuid4(), expected_version=1, status='in_progress', message='Zahájeno'), service, db)
    notices_before = db.query(VehicleUpdate).count()
    def fail(*args, **kwargs):
        raise RuntimeError('isolated publication failure')
    monkeypatch.setattr(service_jobs, 'publish_vehicle_update', fail)
    with pytest.raises(RuntimeError):
        update_job(job['id'], JobUpdate(client_id=uuid4(), expected_version=2, status='completed', message='Dokončeno'), service, db)
    db.rollback()
    assert db.get(ServiceJob, job['id']).status == 'in_progress'
    assert db.query(ServiceRecord).count() == 0
    assert db.query(ServiceRecordAuditLog).count() == 0
    assert db.query(VehicleUpdate).count() == notices_before
    assert db.query(ServiceJobEvent).count() == 2


def test_sell_and_repurchase_does_not_restore_private_timeline(ctx):
    db, owner, service, _, vehicle, assignment, _ = ctx
    job, _ = accept(ctx)
    # Existing owner rows are reused on return (unique owner/vehicle/type).
    from datetime import timedelta
    assignment.owned_from = assignment.owned_from + timedelta(days=1)
    db.commit()
    for actor in (owner, service):
        with pytest.raises(HTTPException) as error:
            get_job(job['id'], actor, db)
        assert error.value.status_code == 404
    assert list_jobs(vehicle.id, owner, db)['items'] == []
