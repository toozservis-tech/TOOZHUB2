"""Unregistered clients can have multiple cars without losing invitations/work."""
from datetime import date
from uuid import uuid4

import pytest
from fastapi import HTTPException

from test_service_invitation_consent import fixture
from src.modules.vehicle_hub.models import ServiceCustomerInvite, Vehicle, VehicleOwnership, ServiceRecord
from src.modules.vehicle_hub.routers_v1 import service_workspace as workspace, service_jobs as jobs


def add_car(s, suffix=1):
    return workspace.create_pending_vehicle_registration(
        workspace.PendingVehicleRegistrationRequest(invite_email='new-client@example.com',
            invite_name='Testovací Klient', vehicle=workspace.ServiceWorkspaceVehicleCreateRequest(
                nickname=f'Ukázka {suffix}', vin=f'TMBTEST00000000{suffix:02}',
                stk_valid_until=date(2030, 1, 1))), current_user=s.service, db=s.db)


def test_second_car_preserves_first_invitation(fixture):
    s = fixture
    first = add_car(s)
    invite = s.db.query(ServiceCustomerInvite).one()
    token = invite.token
    second = add_car(s, 2)
    s.db.refresh(invite)
    assert first['vehicle_id'] != second['vehicle_id']
    assert invite.status == 'pending' and invite.token == token
    assert s.db.query(ServiceCustomerInvite).filter_by(status='pending').count() == 1
    assert s.db.query(ServiceCustomerInvite).count() == 1


def test_prepared_car_is_not_presented_as_owner_consent(fixture):
    from src.modules.vehicle_hub.routers_v1.schemas import ServiceApprovedVehicleListOutV1
    s = fixture
    first = add_car(s)
    data = workspace.list_approved_service_vehicles(s.service, s.db)
    # The response model must preserve the explicit state, not discard it.
    response = ServiceApprovedVehicleListOutV1.model_validate(data)
    car = next(item for item in response.items if item.id == first['vehicle_id'])
    assert car.access_status == 'awaiting_registration'
    assert car.source_type == 'pending_owner_registration'
    assert car.customer_id is None and car.last_shared_at is None
    with pytest.raises(HTTPException) as denied:
        workspace.list_approved_service_vehicles(s.stranger, s.db)
    assert denied.value.status_code == 403


def test_private_job_before_registration_has_no_fake_owner(fixture):
    s = fixture
    car = add_car(s)
    created = jobs.create_job(car['vehicle_id'], jobs.JobCreate(client_id=uuid4(), title='Kontrola brzd'), s.service, s.db)
    assert created['shared_with_owner'] is False
    assert created['consent_status'] == 'awaiting_registration'
    assert not s.db.query(VehicleOwnership).filter_by(vehicle_id=car['vehicle_id']).count()
    assert jobs.list_jobs(car['vehicle_id'], s.service, s.db)['items'][0]['id'] == created['id']
    with pytest.raises(HTTPException):
        jobs.get_job(created['id'], s.stranger, s.db)
    started = jobs.update_job(created['id'], jobs.JobUpdate(client_id=uuid4(), expected_version=created['version'],
        status='in_progress', message='Kontrola brzd'), s.service, s.db)
    completed = jobs.update_job(created['id'], jobs.JobUpdate(client_id=uuid4(), expected_version=started['version'],
        status='completed', message='Brzdy zkontrolované', price=1500), s.service, s.db)
    assert completed['final_record_id'] is None
    assert s.db.query(ServiceRecord).count() == 0
    assert jobs.get_job(created['id'], s.service, s.db)['status'] == 'completed'


@pytest.mark.parametrize('decision', ['approved', 'rejected'])
def test_verified_claim_then_explicit_consent_preserves_completed_work(fixture, monkeypatch, tmp_path, decision):
    import base64
    from io import BytesIO
    from PIL import Image
    from src.modules.vehicle_hub.routers_v1 import vehicles, services
    from src.modules.vehicle_hub.routers_v1.schemas import ServiceAccessRequestDecisionV1
    from src.modules.vehicle_hub.models import ServiceAccessRequest, VehicleAttachmentPrivacy
    from src.modules.vehicle_hub.routers_v1 import service_records
    from src.modules.vehicle_hub.vehicle_privacy import require_attachment_private
    import src.modules.licensing.service as licensing
    s = fixture
    car = add_car(s)
    created = jobs.create_job(car['vehicle_id'], jobs.JobCreate(client_id=uuid4(), title='Výměna oleje'), s.service, s.db)
    monkeypatch.setattr(service_records, 'SERVICE_RECORD_ATTACHMENTS_DIR', tmp_path/'attachments')
    monkeypatch.setattr(service_records, 'persist_file', lambda path, data: path.write_bytes(data))
    monkeypatch.setattr(service_records, 'cached_file', lambda path: path if path.exists() else None)
    raw=BytesIO(); Image.new('RGB',(600,400),'orange').save(raw,'JPEG')
    uploaded=jobs.upload_service_job_photo(created['id'], jobs.JobPhotoUpload(client_id=uuid4(),caption='Nový filtr',
        content_base64=base64.b64encode(raw.getvalue()).decode()),s.service,s.db)
    photo_id=uploaded['photo']['id']
    assert jobs.view_job_photo(created['id'],photo_id,s.service,s.db,thumbnail=True).body
    with pytest.raises(HTTPException): jobs.view_job_photo(created['id'],photo_id,s.stranger,s.db)
    started = jobs.update_job(created['id'], jobs.JobUpdate(client_id=uuid4(), expected_version=uploaded['job']['version'],
        status='in_progress', message='Výměna oleje'), s.service, s.db)
    completed = jobs.update_job(created['id'], jobs.JobUpdate(client_id=uuid4(), expected_version=started['version'],
        status='completed', message='Nový olej a filtr', price=2100), s.service, s.db)
    s.stranger.email = 'new-client@example.com'
    s.db.commit()
    monkeypatch.setattr(licensing, 'assert_vehicle_quota', lambda *a, **kw: None)
    monkeypatch.setattr(services, 'assert_customer_feature', lambda *a, **kw: None)
    v = s.db.get(Vehicle, car['vehicle_id'])
    result = vehicles.create_vehicle(vehicles.VehicleCreateV1(nickname=v.nickname, vin=v.vin), s.stranger, s.db)
    assert result['id'] == v.id
    request = s.db.query(ServiceAccessRequest).filter_by(vehicle_id=v.id).one()
    assert request.status == 'pending'
    assert jobs.list_jobs(v.id, s.stranger, s.db)['items'] == []
    assert jobs.get_job(created['id'], s.service, s.db)['consent_status'] == 'pending'
    with pytest.raises(HTTPException): jobs.view_job_photo(created['id'],photo_id,s.stranger,s.db,thumbnail=True)
    attachment=s.db.query(VehicleAttachmentPrivacy).one()
    with pytest.raises(HTTPException): require_attachment_private(s.db,vehicle_id=v.id,key=attachment.storage_key,actor=s.stranger)
    services.resolve_service_access_request(request.id, ServiceAccessRequestDecisionV1(decision=decision), s.stranger, s.db)
    if decision == 'approved':
        record = s.db.query(ServiceRecord).one()
        assert record.price == 2100 and record.description == 'Nový olej a filtr'
        assert record.performed_at == completed['completed_at']
        assert record.tenant_id == s.stranger.tenant_id
        assert jobs.get_job(created['id'], s.stranger, s.db)['shared_with_owner']
        assert jobs.view_job_photo(created['id'],photo_id,s.stranger,s.db,thumbnail=True).body
        require_attachment_private(s.db,vehicle_id=v.id,key=attachment.storage_key,actor=s.stranger)
    else:
        assert s.db.query(ServiceRecord).count() == 0
        assert jobs.list_jobs(v.id, s.stranger, s.db)['items'] == []
        assert jobs.get_job(created['id'], s.service, s.db)['consent_status'] == 'rejected'
        with pytest.raises(HTTPException): jobs.view_job_photo(created['id'],photo_id,s.stranger,s.db)
        assert jobs.view_job_photo(created['id'],photo_id,s.service,s.db).body


@pytest.mark.parametrize('runner', ['script', 'alembic'])
def test_preregistration_migration_preserves_rows_and_child_references(tmp_path, runner):
    from sqlalchemy import create_engine, inspect, text, event
    from scripts.migrate_service_job_preregistration import migrate
    engine = create_engine(f'sqlite:///{tmp_path}/migration.sqlite')
    @event.listens_for(engine, 'connect')
    def foreign_keys(conn, _):
        conn.execute('PRAGMA foreign_keys=ON')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE service_jobs (id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL, ownership_id INTEGER NOT NULL, ownership_started_at TIMESTAMP NOT NULL, title TEXT)'))
        conn.execute(text("INSERT INTO service_jobs VALUES (1, 10, 20, '2026-01-01', 'Původní zakázka')"))
        conn.execute(text('CREATE TABLE evidence (id INTEGER PRIMARY KEY, job_id INTEGER REFERENCES service_jobs(id))'))
        conn.execute(text('INSERT INTO evidence VALUES (1, 1)'))
    if runner == 'script':
        migrate(engine); migrate(engine)
    else:
        import importlib.util
        from pathlib import Path
        from alembic.migration import MigrationContext
        from alembic.operations import Operations
        path=Path(__file__).resolve().parents[2]/'alembic/versions/20261103_0022_service_job_preregistration.py'
        spec=importlib.util.spec_from_file_location('prereg_migration_test',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        for _ in range(2):
            with engine.connect() as conn:
                context=MigrationContext.configure(conn)
                with context.begin_transaction(), Operations.context(context):
                    module.upgrade()
    with engine.begin() as conn:
        assert conn.execute(text('SELECT title,owner_id,ownership_id FROM service_jobs')).one() == ('Původní zakázka', 10, 20)
        assert conn.execute(text('SELECT job_id FROM evidence')).scalar() == 1
        assert conn.exec_driver_sql('PRAGMA foreign_keys').scalar() == 1
        assert not conn.exec_driver_sql('PRAGMA foreign_key_check').all()
        conn.execute(text("INSERT INTO service_jobs (id,title) VALUES (2,'Soukromá příprava')"))
        assert all(c['nullable'] for c in inspect(conn).get_columns('service_jobs') if c['name'] in ('owner_id','ownership_id','ownership_started_at'))
