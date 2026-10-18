"""Synthetic HTTP flow with real password/JWT/role/consent/entitlement checks.

Only persistence factories point at temporary SQLite. No auth or feature gates
are overridden; no production network, database, files or credentials are used.
"""
from types import SimpleNamespace
from uuid import uuid4

import pytest
import json
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from src.core import security
from src.modules.vehicle_hub.database import Base, get_db
from src.modules.vehicle_hub.models import Customer, Tenant, License, Vehicle, ServiceRecord, ServiceRecordAuditLog, VehicleServiceLink
from src.modules.vehicle_hub.ownership import ensure_vehicle_owner_assignment
from src.modules.vehicle_hub.vehicle_update_models import VehicleUpdate, VehicleUpdateReceipt
from src.modules.vehicle_hub.service_job_models import ServiceJob
from src.modules.vehicle_hub.routers_v1 import service_workspace, services, service_jobs, vehicle_updates, service_records, vehicle_lifecycle, vehicle_archives, vehicles
from src.server.routers import user_auth
from src.server import security_tracking


@pytest.fixture
def http_flow(tmp_path, monkeypatch):
    engine = create_engine(f'sqlite:///{tmp_path}/http-lifecycle.sqlite', connect_args={'check_same_thread': False})
    @event.listens_for(engine, 'connect')
    def enable_foreign_keys(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setattr(security, 'JWT_SECRET_KEY', 'isolated-http-lifecycle-test-signing-key-only')
    monkeypatch.setattr(security_tracking, 'SessionLocal', factory)
    monkeypatch.setattr(security_tracking, '_GEOLOOKUP_ENABLED', False, raising=False)
    monkeypatch.setattr(security_tracking, '_REVERSE_GEO_ENABLED', False)
    import requests
    external_attempts = []
    def no_external_network(*args, **kwargs):
        external_attempts.append("blocked")
        raise AssertionError('External network is forbidden in the isolated HTTP flow')
    monkeypatch.setattr(requests.Session, 'request', no_external_network)
    monkeypatch.setattr(security_tracking, 'urlopen', no_external_network)
    password = 'Synthetic-Flow-Only-4729'
    actors = {}
    with factory() as db:
        for name, role in [('owner', 'user'), ('service', 'service'), ('stranger', 'user')]:
            tenant = Tenant(name=f'HTTP {name}', license_key=str(uuid4()))
            db.add(tenant); db.flush()
            actor = Customer(tenant_id=tenant.id, name=f'HTTP {name}', email=f'{name}-{uuid4().hex}@example.com',
                role=role, password_hash=security.hash_password(password), session_version=0)
            db.add(actor); db.flush()
            db.add(License(tenant_id=tenant.id, plan='premium' if name == 'owner' else 'free',
                status='active', vehicles_limit=10))
            actors[name] = {'id': actor.id, 'email': actor.email, 'role': role}
        owner = db.get(Customer, actors['owner']['id'])
        vehicle = Vehicle(tenant_id=owner.tenant_id, user_email=owner.email, nickname='Synthetic HTTP vehicle',
            vin='WVWZZZ1JZXW000001', plate='HTTP001', brand='Synthetic')
        db.add(vehicle); db.flush()
        ensure_vehicle_owner_assignment(db, vehicle=vehicle, owner=owner)
        vehicle_id = vehicle.id
        db.commit()
    app = FastAPI()
    app.include_router(user_auth.router)
    for router in (service_workspace.router, services.router, service_jobs.router, vehicle_updates.router, service_records.router, vehicle_lifecycle.router, vehicle_archives.router, vehicles.router):
        app.include_router(router, prefix='/api/v1')
    def isolated_db():
        with factory() as db:
            yield db
    app.dependency_overrides[get_db] = isolated_db
    try:
        with TestClient(app) as client:
            yield SimpleNamespace(client=client, factory=factory, actors=actors, password=password, vehicle_id=vehicle_id, external_attempts=external_attempts)
    finally:
        engine.dispose()


def test_authenticated_request_to_completed_record_and_owner_alerts_over_http(http_flow):
    flow = http_flow
    client, vehicle_id = flow.client, flow.vehicle_id
    trace = []
    def expect(response, status):
        trace.append((response.request.method, response.request.url.path, response.status_code))
        assert response.status_code == status, f'{response.request.method} {response.request.url.path}: expected {status}, got {response.status_code}'
        return response.json()
    owner_path = '/api/v1/vehicle-updates'
    expect(client.get(owner_path), 401)
    owner_data = flow.actors['owner']
    expect(client.post('/user/login', json={'email': owner_data['email'], 'password': 'wrong-password'}), 401)
    headers = {}
    for name, actor in flow.actors.items():
        login = expect(client.post('/user/login', json={'email': actor['email'], 'password': flow.password, 'expected_role': actor['role']}), 200)
        assert login['user']['id'] == actor['id'] and login['user']['role'] == actor['role']
        headers[name] = {'Authorization': 'Bearer ' + login['access_token']}
    owner, service, stranger = (headers[name] for name in ('owner', 'service', 'stranger'))
    jobs_path = f'/api/v1/vehicles/{vehicle_id}/service-jobs'
    record_path = f'/api/v1/vehicles/{vehicle_id}/records'
    creation = {'client_id': str(uuid4()), 'title': 'HTTP brake repair', 'description': 'Acceptance details', 'mileage': 120000}
    expect(client.post(jobs_path, headers=service, json=creation), 403)
    expect(client.get(record_path, headers=service), 403)
    lookup = expect(client.post('/api/v1/services/workspace/vehicle-lookup', headers=service, json={'query': 'HTTP001'}), 200)
    assert lookup['candidates'][0]['vehicle_id'] == vehicle_id
    assert lookup['candidates'][0]['vin_masked'] != 'WVWZZZ1JZXW000001'
    request_path = '/api/v1/services/workspace/access-requests'
    request_body = {'vehicle_id': vehicle_id, 'lookup_query': 'HTTP001', 'note': 'Synthetic access request'}
    pending = expect(client.post(request_path, headers=service, json=request_body), 200)
    retry = expect(client.post(request_path, headers=service, json=request_body), 200)
    assert retry['request_id'] == pending['request_id'] and not retry['created']
    decision_path = f"/api/v1/services/access-requests/{pending['request_id']}"
    inbox = expect(client.get(owner_path, headers=owner), 200)
    assert inbox['unread_count'] == 1 and inbox['items'][0]['event_type'] == 'access_request.created'
    request_alert_id = inbox['items'][0]['id']
    expect(client.post(f'{owner_path}/{request_alert_id}/read', headers=owner), 200)
    # Reading a notice never authorizes service access.
    expect(client.post(jobs_path, headers=service, json=creation), 403)
    expect(client.put(decision_path, headers=stranger, json={'decision': 'approved'}), 404)
    expect(client.put(decision_path, headers=service, json={'decision': 'approved'}), 403)
    requests = expect(client.get('/api/v1/services/access-requests', headers=owner), 200)
    assert any(row['id'] == pending['request_id'] for row in requests['requests'])
    expect(client.put(decision_path, headers=owner, json={'decision': 'approved'}), 200)
    job = expect(client.post(jobs_path, headers=service, json=creation), 200)
    same_job = expect(client.post(jobs_path, headers=service, json=creation), 200)
    assert job['status'] == 'received' and same_job['id'] == job['id']
    job_path = f"/api/v1/service-jobs/{job['id']}"
    expect(client.get(job_path, headers=stranger), 403)
    expect(client.get(job_path, headers=owner), 200)
    update_path = job_path + '/updates'
    start = {'client_id': str(uuid4()), 'expected_version': 1, 'status': 'in_progress', 'message': 'Started inspection'}
    started = expect(client.post(update_path, headers=service, json=start), 200)
    assert started['version'] == 2
    progress = {'client_id': str(uuid4()), 'expected_version': 2, 'message': 'Brake pads installed'}
    progressed = expect(client.post(update_path, headers=service, json=progress), 200)
    assert progressed['version'] == 3
    stale = {'client_id': str(uuid4()), 'expected_version': 1, 'message': 'Stale work submission'}
    expect(client.post(update_path, headers=service, json=stale), 409)
    finish = {'client_id': str(uuid4()), 'expected_version': 3, 'status': 'completed', 'message': 'Brakes tested and completed', 'price': 2500}
    completed = expect(client.post(update_path, headers=service, json=finish), 200)
    retried = expect(client.post(update_path, headers=service, json=finish), 200)
    assert completed['status'] == 'completed' and completed['final_record_id'] == retried['final_record_id']
    assert len(completed['events']) == 4
    expect(client.post(update_path, headers=service, json={**finish, 'message': 'Changed retry payload'}), 409)
    expect(client.post(update_path, headers=service, json={'client_id': str(uuid4()), 'expected_version': 4, 'message': 'Rewrite completed job'}), 409)
    final_record_path = f"{record_path}/{completed['final_record_id']}"
    expect(client.put(final_record_path, headers=service, json={'description': 'Rewrite immutable history'}), 403)
    expect(client.delete(final_record_path, headers=service), 403)
    owner_records = expect(client.get(record_path, headers=owner), 200)
    assert len(owner_records) == 1 and owner_records[0]['id'] == completed['final_record_id']
    assert owner_records[0]['description'] == finish['message'] and 'Brake pads installed' in owner_records[0]['note']
    expect(client.get(record_path, headers=stranger), 403)
    alerts = expect(client.get(owner_path, headers=owner), 200)
    assert len(alerts['items']) == 5 and alerts['unread_count'] == 4
    assert [row['event_type'] for row in alerts['items']].count('job.completed') == 1
    assert all(row['vehicle_id'] == vehicle_id for row in alerts['items'])
    assert expect(client.get(owner_path, headers=stranger), 200)['items'] == []
    assert expect(client.get(owner_path, headers=service), 200)['items'] == []
    complete_alert = next(row for row in alerts['items'] if row['event_type'] == 'job.completed')
    expect(client.post(f"{owner_path}/{complete_alert['id']}/read", headers=stranger), 404)
    for row in alerts['items']:
        expect(client.post(f"{owner_path}/{row['id']}/read", headers=owner), 200)
        expect(client.post(f"{owner_path}/{row['id']}/read", headers=owner), 200)
    assert expect(client.get(owner_path, headers=owner), 200)['unread_count'] == 0
    with flow.factory() as db:
        assert db.query(ServiceJob).count() == 1
        assert db.query(ServiceRecord).count() == 1
        assert db.query(ServiceRecordAuditLog).count() == 1
        assert db.query(VehicleUpdate).count() == 5
        assert db.query(VehicleUpdateReceipt).count() == 5
        link = db.query(VehicleServiceLink).one()
        assert link.status == 'approved' and not link.scope_edit_existing_records and not link.scope_delete_existing_records
    assert flow.external_attempts == []
    print('HTTP_FLOW_RESULT ' + json.dumps({'http_requests': len(trace), 'password_logins': 3,
        'final_records': 1, 'creation_audits': 1, 'owner_alerts': 5, 'read_receipts': 5,
        'auth_or_entitlement_overrides': False, 'external_network_attempts': len(flow.external_attempts)}, sort_keys=True))



def test_owner_http_archive_and_restore_preserve_private_period_and_reject_stale_client(http_flow):
    flow = http_flow
    client = flow.client
    trace = []
    def expect(response, status):
        trace.append((response.request.method, response.request.url.path, response.status_code))
        assert response.status_code == status, f'{response.request.method} {response.request.url.path}: expected {status}, got {response.status_code}'
        return response.json()
    headers = {}
    for name, actor in flow.actors.items():
        login = expect(client.post('/user/login', json={'email': actor['email'], 'password': flow.password,
            'expected_role': actor['role']}), 200)
        headers[name] = {'Authorization': 'Bearer ' + login['access_token']}
    owner, service, stranger = (headers[name] for name in ('owner', 'service', 'stranger'))
    private = 'PRIVATE_SYNTHETIC_ENDING_PERIOD'
    vin = 'WVWZZZ1JZXW000002'
    nickname = 'Separate lifecycle fixture'
    with flow.factory() as db:
        owner_row = db.get(Customer, flow.actors['owner']['id'])
        car = Vehicle(tenant_id=owner_row.tenant_id, user_email=owner_row.email, nickname=nickname,
            vin=vin, plate='HTTP002', notes=private, year=2014)
        db.add(car); db.flush()
        assignment = ensure_vehicle_owner_assignment(db, vehicle=car, owner=owner_row)
        record = ServiceRecord(tenant_id=owner_row.tenant_id, vehicle_id=car.id, user_id=owner_row.id,
            description=private, note=private, price=1234)
        db.add(record)
        db.add(VehicleServiceLink(tenant_id=owner_row.tenant_id, vehicle_id=car.id,
            service_customer_id=flow.actors['service']['id'], owner_customer_id=owner_row.id,
            status='approved', scope_vehicle_history_read=True, scope_create_service_record=True))
        db.commit()
        car_id, record_id, assignment_id = car.id, record.id, assignment.id
    lifecycle_path = f'/api/v1/vehicles/{car_id}/lifecycle'
    expect(client.get(lifecycle_path, headers=service), 403)
    expect(client.get(lifecycle_path, headers=stranger), 403)
    initial = expect(client.get(lifecycle_path, headers=owner), 200)
    assert initial['state'] == 'active' and initial['version'] == 0
    assert set(initial['actions']) == {'sold', 'removed', 'scrapped', 'deposited'}
    def action_body(action, state, **extra):
        return {'client_id': str(uuid4()), 'ownership_id': state['ownership_id'],
            'ownership_token': state['ownership_token'], 'expected_version': state['version'],
            'action': action, **extra}
    # A real client may retain a request that was never sent. Its version alone
    # will match again after restore; the ownership token must still fence it.
    never_sent = action_body('deposited', initial)
    deposit = action_body('deposited', initial)
    assert expect(client.post(lifecycle_path, headers=owner, json=deposit), 200)['state'] == 'deposited'
    deposited = expect(client.get(lifecycle_path, headers=owner), 200)
    assert deposited['version'] == 1 and 'reactivated' in deposited['actions']
    reactivate = action_body('reactivated', deposited)
    assert expect(client.post(lifecycle_path, headers=owner, json=reactivate), 200)['state'] == 'active'
    active = expect(client.get(lifecycle_path, headers=owner), 200)
    removal = action_body('removed', active, note='Synthetic removal')
    archived = expect(client.post(lifecycle_path, headers=owner, json=removal), 200)
    assert archived['state'] == 'archived' and archived['version'] == 3 and archived['archive_id']
    expect(client.get(lifecycle_path, headers=owner), 403)
    archive_path = f"/api/v1/vehicle-archives/{archived['archive_id']}"
    archive = expect(client.get(archive_path, headers=owner), 200)
    assert archive['vehicle_id'] == car_id and archive['profile']['notes'] == private
    assert archive['lifecycle']['action'] == 'removed'
    assert len(archive['records']) == 1 and archive['records'][0]['id'] == record_id
    assert archive['records'][0]['note'] == private and archive['records'][0]['price'] == 1234
    own_archives = expect(client.get('/api/v1/vehicle-archives', headers=owner), 200)
    assert any(row['id'] == archived['archive_id'] for row in own_archives)
    for foreign in (service, stranger):
        expect(client.get(archive_path, headers=foreign), 404)
        assert expect(client.get('/api/v1/vehicle-archives', headers=foreign), 200) == []
    restored = expect(client.post('/api/v1/vehicles', headers=owner,
        json={'vin': vin, 'nickname': nickname}), 200)
    assert restored['id'] == car_id and restored['year'] == 2014
    fresh = expect(client.get(lifecycle_path, headers=owner), 200)
    assert fresh['ownership_id'] == assignment_id and fresh['version'] == 0 and fresh['state'] == 'active'
    assert fresh['ownership_token'] != initial['ownership_token']
    expect(client.post(lifecycle_path, headers=owner, json=never_sent), 409)
    # The exact old completed request is a receipt lookup, never a second removal.
    assert expect(client.post(lifecycle_path, headers=owner, json=removal), 200) == archived
    assert expect(client.get(lifecycle_path, headers=owner), 200)['state'] == 'active'
    assert expect(client.get(archive_path, headers=owner), 200)['profile']['notes'] == private
    expect(client.get(f'/api/v1/vehicles/{car_id}/records', headers=service), 403)
    with flow.factory() as db:
        assert db.query(Vehicle).filter(Vehicle.vin == vin).count() == 1
        assert db.get(ServiceRecord, record_id).note == private
        assert db.query(VehicleServiceLink).filter_by(vehicle_id=car_id).one().status == 'revoked'
    assert flow.external_attempts == []
    print('HTTP_ARCHIVE_RESTORE_RESULT ' + json.dumps({'http_requests': len(trace), 'password_logins': 3,
        'same_vehicle_identity': True, 'private_archive_retained': True, 'foreign_archive_denied': True,
        'stale_ownership_request_rejected': True, 'grant_revived': False,
        'external_network_attempts': len(flow.external_attempts)}, sort_keys=True))
