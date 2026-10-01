"""Synthetic multi-role API flows; no production database, network or customer files.

Authentication/MFA is tested separately. Here the dependency supplies an already
verified actor, while the actual vehicle policies and database queries run.
"""
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base, get_db
from src.modules.vehicle_hub.models import Customer, Tenant, Vehicle, VehicleServiceLink, ServiceRecord, RepairPhotoSession
from src.modules.vehicle_hub.ownership import ensure_vehicle_owner_assignment, release_vehicle_owner_assignment
from src.modules.vehicle_hub.routers_v1 import vehicles, service_records, repair_photos
from src.modules.vehicle_hub.routers_v1.auth import get_current_user


@pytest.fixture
def scenario(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'roles.sqlite'}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False)()
    tenants = [Tenant(name=f"Fixture {i}", license_key=f"fixture-{i}") for i in range(3)]
    db.add_all(tenants); db.flush()
    actors = {}
    for name, role, tenant in [("owner", "user", 0), ("same_tenant", "user", 0),
            ("stranger", "user", 1), ("service", "service", 1), ("other_service", "service", 2),
            ("admin", "admin", 2), ("developer", "developer_admin", 2)]:
        actor = Customer(email=f"{name}@example.invalid", role=role, tenant_id=tenants[tenant].id)
        db.add(actor); actors[name] = actor
    db.flush()
    owner = actors['owner']
    car = Vehicle(tenant_id=owner.tenant_id, user_email=owner.email, nickname="Fixture vehicle",
        vin="TMBJF73T2B9044629", plate="TEST001", stk_valid_until=date(2030, 1, 1), current_mileage_km=100,
        orv_number="PRIVATE-DOCUMENT-NUMBER", orv_front_image_path="private-front.png",
        notes="PRIVATE OWNER NOTE", insurance_provider="PRIVATE INSURANCE")
    db.add(car); db.flush()
    ensure_vehicle_owner_assignment(db, vehicle=car, owner=owner)
    link = VehicleServiceLink(tenant_id=owner.tenant_id, service_customer_id=actors['service'].id,
        owner_customer_id=owner.id, vehicle_id=car.id, status="approved", scope_vehicle_history_read=True,
        scope_create_service_record=True, owner_data_access_level="none")
    db.add(link); db.commit()
    monkeypatch.setattr(vehicles, '_ensure_vehicle_photo_column', lambda db: None)
    monkeypatch.setattr(service_records, 'assert_module_ready', lambda *args, **kwargs: None)
    # These must never be reached by any denied request.
    def unexpected(*args, **kwargs):
        raise AssertionError("Denied request reached file/network/parser processing")
    for module, names in [(vehicles, ['_build_tachometer_session', '_decode_base64_payload', '_get_vehicle_photo_file']),
                           (service_records, ['_decode_base64_payload', '_store_attachment_for_vehicle', '_extract_text_from_file'])]:
        for name in names: monkeypatch.setattr(module, name, unexpected)
    state = SimpleNamespace(db=db, car=car, link=link, actors=actors, actor=owner)
    app = FastAPI()
    for router in [vehicles.router, service_records.router, repair_photos.router]:
        app.include_router(router, prefix='/api/v1')
    app.dependency_overrides[get_current_user] = lambda: state.actor
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        state.client = client
        yield state
    db.close(); engine.dispose()


def route(s, suffix=''):
    return f'/api/v1/vehicles/{s.car.id}{suffix}'


@pytest.mark.parametrize('actor', ['owner', 'service', 'admin', 'developer'])
def test_visible_actions_match_actual_role_and_hide_owner_private_fields(scenario, actor):
    s = scenario; s.actor = s.actors[actor]
    response = s.client.get(route(s)); assert response.status_code == 200
    body = response.json(); permissions = body['permissions']
    assert permissions['can_create_service_record']
    assert permissions['can_record_mileage']
    assert permissions['can_create_repair_photos'] == (actor != 'owner')
    for key in ['can_manage_photo', 'can_edit_vehicle', 'can_import_tachometer', 'can_edit_service_records']:
        assert permissions[key] == (actor != 'service')
    if actor == 'service':
        assert body['user_email'] == 'hidden' and body['tenant_id'] is None
        for field in ['orv_number', 'orv_front_image_path', 'notes', 'insurance_provider']:
            assert body[field] is None
        assert body['vin'] == s.car.vin and body['current_mileage_km'] == 100
    else:
        assert body['orv_number'] == 'PRIVATE-DOCUMENT-NUMBER'


@pytest.mark.parametrize('actor', ['same_tenant', 'stranger', 'other_service'])
def test_unrelated_accounts_cannot_read_vehicle_or_history(scenario, actor):
    s = scenario; s.actor = s.actors[actor]
    for suffix in ['', '/records', '/tachometer/history', '/photo']:
        assert s.client.get(route(s, suffix)).status_code == 403


@pytest.mark.parametrize('actor', ['service', 'same_tenant', 'stranger', 'other_service'])
@pytest.mark.parametrize('action', ['metadata', 'photo', 'delete_photo', 'tachometer'])
def test_read_permission_never_grants_vehicle_management(scenario, actor, action):
    s = scenario; s.actor = s.actors[actor]
    if action == 'metadata': response = s.client.put(route(s), json={'nickname': 'Not allowed'})
    elif action == 'photo': response = s.client.post(route(s, '/photo'), json={'file_name': 'fixture.jpg', 'file_content_base64': 'A'*24})
    elif action == 'delete_photo': response = s.client.delete(route(s, '/photo'))
    else: response = s.client.post(route(s, '/tachometer/init'))
    assert response.status_code == 403, response.text
    s.db.refresh(s.car)
    assert s.car.nickname == 'Fixture vehicle' and s.car.photo_path is None
    assert s.db.query(ServiceRecord).count() == 0


@pytest.mark.parametrize('actor', ['owner', 'admin', 'developer'])
def test_owner_and_admin_can_update_profile(scenario, actor):
    s = scenario; s.actor = s.actors[actor]
    response = s.client.put(route(s), json={'nickname': 'Changed by authorized actor'})
    assert response.status_code == 200, response.text
    assert response.json()['permissions']['can_edit_vehicle']
    s.db.refresh(s.car); assert s.car.nickname == 'Changed by authorized actor'


def test_read_only_link_does_not_allow_records_documents_mileage_or_repairs(scenario):
    s = scenario; s.actor = s.actors['service']; s.link.scope_create_service_record = False; s.db.commit()
    body = s.client.get(route(s)).json()
    assert all(not enabled for enabled in body['permissions'].values())
    assert s.client.get(route(s, '/records')).status_code == 200
    body = {'performed_at': '2026-10-01T09:00:00', 'description': 'Fixture record', 'category': 'JINE'}
    assert s.client.post(route(s, '/records'), json=body).status_code == 403
    document = {'file_name': 'fixture.txt', 'file_mime_type': 'text/plain', 'file_content_base64': 'A'*24}
    for suffix in ['/records/attachments/upload', '/records/auto-from-document', '/records/document-prefill']:
        assert s.client.post(route(s, suffix), json=document).status_code == 403
    assert s.client.post(route(s, '/mileage'), json={'mileage_km': 101}).status_code == 403
    assert s.client.post(f'/api/v1/repair-documentation/vehicles/{s.car.id}', json={'title':'Fixture', 'client_id':str(uuid4())}).status_code == 403
    assert s.db.query(ServiceRecord).count() == 0 and s.db.query(RepairPhotoSession).count() == 0
    assert s.car.current_mileage_km == 100


@pytest.mark.parametrize('revocation', ['read_scope', 'status'])
def test_access_revocation_closes_history_and_writes_but_keeps_own_repair_evidence(scenario, revocation):
    s = scenario; s.actor = s.actors['service']
    response = s.client.post(route(s, '/records'), json={'performed_at': '2026-10-01T09:00:00', 'description': 'Fixture repair', 'category': 'JINE'})
    assert response.status_code == 200, response.text
    record = s.db.get(ServiceRecord, response.json()['id'])
    assert record.created_by_service_customer_id == s.actor.id and record.service_access_link_id == s.link.id
    session = s.client.post(f'/api/v1/repair-documentation/vehicles/{s.car.id}', json={'title':'Fixture visit', 'client_id':str(uuid4())})
    assert session.status_code == 200
    visit_id = session.json()['id']
    if revocation == 'read_scope': s.link.scope_vehicle_history_read = False
    else: s.link.status = 'revoked'
    s.db.commit()
    for suffix in ['', '/records', '/tachometer/history']:
        assert s.client.get(route(s, suffix)).status_code == 403
    assert s.client.post(route(s, '/mileage'), json={'mileage_km': 110}).status_code == 403
    assert s.client.get(f'/api/v1/repair-documentation/sessions/{visit_id}/photos').status_code == 200
    assert s.client.post(f'/api/v1/repair-documentation/sessions/{visit_id}/photos', json={
        'client_id': str(uuid4()), 'phase':'after', 'source':'library', 'file_content_base64':'A'*24}).status_code == 403
    s.actor = s.actors['other_service']
    assert s.client.get(f'/api/v1/repair-documentation/sessions/{visit_id}/photos').status_code == 403
    s.actor = s.actors['owner']
    assert s.client.get(f'/api/v1/repair-documentation/sessions/{visit_id}/photos').status_code == 200
    assert len(s.client.get(route(s, '/records')).json()) == 1


def test_service_mileage_is_attributed_and_does_not_grant_history_edits(scenario):
    s = scenario; s.actor = s.actors['service']
    response = s.client.post(route(s, '/mileage'), json={'mileage_km': 150})
    assert response.status_code == 200, response.text
    record_id = response.json()['created_record_id']
    record = s.db.get(ServiceRecord, record_id)
    assert record.created_by_service_customer_id == s.actor.id and record.service_access_link_id == s.link.id
    assert response.json()['vehicle']['current_mileage_km'] == 150
    assert s.client.post(route(s, '/mileage'), json={'mileage_km': 120, 'confirm_lower_than_current':True}).status_code == 403
    for method in ['put','delete']:
        assert s.client.request(method, route(s, f'/records/{record_id}'), json={'description':'Attempted change'}).status_code == 403
    s.db.refresh(s.car); assert s.car.current_mileage_km == 150
    s.actor = s.actors['owner']
    assert s.client.post(route(s, '/mileage'), json={'mileage_km': 120}).status_code == 409
    assert s.client.post(route(s, '/mileage'), json={'mileage_km': 120, 'confirm_lower_than_current':True}).status_code == 200


def test_mixed_migrated_and_legacy_vehicles_are_listed_without_reviving_released_ones(scenario):
    s = scenario; owner=s.actors['owner']
    def add(label, tenant_id=owner.tenant_id):
        car=Vehicle(tenant_id=tenant_id, user_email=owner.email, nickname=label, stk_valid_until=date(2030,1,1))
        s.db.add(car); s.db.flush(); return car
    legacy = add('Legacy')
    released = add('Released'); ensure_vehicle_owner_assignment(s.db, vehicle=released, owner=owner)
    assert release_vehicle_owner_assignment(s.db, vehicle=released, owner=owner)
    add('Different tenant', s.actors['stranger'].tenant_id)
    s.db.commit()
    response = s.client.get('/api/v1/vehicles')
    assert response.status_code == 200, response.text
    assert {row['id'] for row in response.json()} == {s.car.id, legacy.id}
    assert all(row['permissions']['can_manage_photo'] for row in response.json())
    assert len(s.client.get('/api/v1/vehicles').json()) == 2


@pytest.mark.parametrize('operation', ['create', 'list', 'get', 'update', 'delete', 'pdf'])
def test_service_history_errors_never_log_or_return_private_exception(scenario, monkeypatch, capsys, caplog, operation):
    s = scenario
    marker = 'PRIVATE_DATABASE_DOCUMENT_OR_PASSWORD'
    def fail(*args, **kwargs): raise RuntimeError(marker)
    monkeypatch.setattr(service_records, 'assert_module_ready', fail)
    monkeypatch.setattr(service_records, 'can_access_vehicle', fail)
    if operation == 'create': response = s.client.post(route(s, '/records'), json={'performed_at': '2026-10-01T09:00:00', 'description': 'Fixture repair', 'category':'JINE'})
    elif operation == 'list': response = s.client.get(route(s, '/records'))
    elif operation == 'get': response = s.client.get(route(s, '/records/1'))
    elif operation == 'update': response = s.client.put(route(s, '/records/1'), json={'description':'Fixture edit'})
    elif operation == 'delete': response = s.client.delete(route(s, '/records/1'))
    else: response = s.client.get(route(s, '/pdf'))
    assert response.status_code == 500, response.text
    assert marker not in response.text
    assert len(response.json()['detail'].split()[-1]) == 32
    output = capsys.readouterr()
    assert marker not in output.out + output.err + caplog.text
