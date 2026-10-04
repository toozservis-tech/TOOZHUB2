"""Real PostgreSQL routes and synthetic mail transport; no customer mail/data."""
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text

from src.core.auth import get_current_user_email
from src.modules.vehicle_hub.database import get_db
from src.modules.vehicle_hub import models as m
from src.modules.vehicle_hub.ownership import ensure_vehicle_owner_assignment
from src.modules.vehicle_hub.routers_v1 import service_workspace, vehicles
from src.modules.vehicle_hub.routers_v1.auth import get_current_user
from src.modules.email_client import service as mail
from src.server.routers import user_security


@pytest.fixture
def scenario(pg_db, monkeypatch):
    db = pg_db.sessions()
    tenants = [m.Tenant(name='Synthetic '+uuid4().hex, license_key=uuid4().hex) for _ in range(2)]
    db.add_all(tenants); db.flush()
    owner = m.Customer(email=uuid4().hex+'@example.com', name='PRIVATE OWNER', phone='PRIVATE PHONE',
                       tenant_id=tenants[0].id, role='user')
    service = m.Customer(email=uuid4().hex+'@example.com', tenant_id=tenants[1].id, role='service')
    db.add_all([owner, service]); db.flush()
    car = m.Vehicle(tenant_id=owner.tenant_id, user_email=owner.email, plate='1ab 2345',
                    vin='WVWZZZ1JZXW000001', nickname='Synthetic vehicle', notes='PRIVATE NOTE')
    db.add(car); db.flush(); ensure_vehicle_owner_assignment(db, vehicle=car, owner=owner); db.commit()
    sent = []
    class FakeMail:
        from_email = 'Evidence Vozidel <support@example.com>'
        def is_configured(self): return True
        def send_simple_email(self, **kwargs): sent.append(kwargs); return True
    monkeypatch.setattr(mail, 'EmailService', FakeMail)
    monkeypatch.setattr(user_security, 'log_security_event', lambda **kwargs: None)
    for key in ('SUPPORT_EMAIL', 'SMTP_FROM', 'SMTP_USER'): monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('EMAIL_FROM', FakeMail.from_email)
    app = FastAPI()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: service
    app.dependency_overrides[get_current_user_email] = lambda: service.email
    app.include_router(service_workspace.router, prefix='/api/v1')
    app.include_router(vehicles.router, prefix='/api/v1')
    app.include_router(user_security.router)
    with TestClient(app) as client:
        yield SimpleNamespace(client=client, db=db, car=car, owner=owner, service=service, sent=sent, mail=FakeMail)
    db.close()


@pytest.mark.parametrize('query', ['1AB2345', '1ab 2345', '1AB\u00a02345', '1AB-2345', ' 1ab\t2345 '])
def test_service_finds_formatted_plate_without_gaining_history_access(scenario, query):
    s = scenario
    response = s.client.post('/api/v1/services/workspace/vehicle-lookup', json={'query': query})
    assert response.status_code == 200
    candidates = response.json()['candidates']
    assert len(candidates) == 1 and candidates[0]['vehicle_id'] == s.car.id
    assert candidates[0]['can_request_access'] and candidates[0]['owner_label'] is None
    for private in (s.owner.email, s.owner.phone, s.owner.name, s.car.notes): assert private not in response.text
    assert s.client.get(f'/api/v1/vehicles/{s.car.id}').status_code == 403


def test_stored_unicode_spacing_and_case_are_normalized_too(scenario):
    s = scenario; s.car.plate = '1ab\u202f2345'; s.db.commit()
    response = s.client.post('/api/v1/services/workspace/vehicle-lookup', json={'query': '1AB2345'})
    assert response.status_code == 200 and response.json()['candidates'][0]['vehicle_id'] == s.car.id


def test_duplicate_plate_requires_vin_instead_of_silently_selecting_another_car(scenario):
    s = scenario
    other = m.Vehicle(tenant_id=s.owner.tenant_id, user_email=s.owner.email, plate='1AB2345', vin='WVWZZZ1JZXW000002')
    s.db.add(other); s.db.flush(); ensure_vehicle_owner_assignment(s.db, vehicle=other, owner=s.owner); s.db.commit()
    result = s.client.post('/api/v1/services/workspace/vehicle-lookup', json={'query':'1AB2345'})
    assert result.status_code == 409 and 'VIN' in result.json()['detail']
    by_vin = s.client.post('/api/v1/services/workspace/vehicle-lookup', json={'query': s.car.vin.lower()})
    assert by_vin.status_code == 200 and by_vin.json()['candidates'][0]['vehicle_id'] == s.car.id


def test_partial_plate_does_not_enumerate_vehicles(scenario):
    result = scenario.client.post('/api/v1/services/workspace/vehicle-lookup', json={'query': '1AB'})
    assert result.status_code == 200 and result.json()['candidates'] == []


def support_payload(**changes):
    return dict(category='obecne', subject='Synthetic question', message='Synthetic support message only.', **changes)


def test_resend_only_configuration_can_receive_support_and_reply_to_authenticated_sender(scenario):
    s = scenario
    result = s.client.post('/user/support', json=support_payload())
    assert result.status_code == 200 and result.json()['sent'] is True
    assert len(s.sent) == 1 and s.sent[0]['to'] == 'support@example.com'
    assert s.sent[0]['reply_to'] == s.service.email
    assert 'IP:' not in s.sent[0]['body'], 'Diagnostics require a visible opt-in'


def test_explicit_support_address_takes_precedence(scenario, monkeypatch):
    monkeypatch.setenv('SUPPORT_EMAIL', 'Help <help@example.com>')
    assert scenario.client.post('/user/support', json=support_payload()).status_code == 200
    assert scenario.sent[0]['to'] == 'help@example.com'


def test_invalid_recipient_fails_without_sending_or_exposing_configuration(scenario, monkeypatch):
    monkeypatch.setenv('SUPPORT_EMAIL', 'bad@example.com, other@example.com')
    result = scenario.client.post('/user/support', json=support_payload())
    assert result.status_code == 503 and not scenario.sent
    assert 'example.com' not in result.text and 'konfigurace' not in result.text


@pytest.mark.parametrize('failure', [False, RuntimeError('PRIVATE PROVIDER KEY and message')])
def test_mail_rejection_is_not_reported_as_sent_or_exposed(scenario, monkeypatch, capsys, failure):
    def send(self, **kwargs):
        if isinstance(failure, Exception): raise failure
        return failure
    monkeypatch.setattr(scenario.mail, 'send_simple_email', send)
    result = scenario.client.post('/user/support', json=support_payload())
    assert result.status_code == 503 and 'PRIVATE' not in result.text
    assert 'PRIVATE' not in capsys.readouterr().out


def test_audit_failure_after_accepted_mail_does_not_invite_duplicate_send(scenario, monkeypatch):
    def broken_log(**kwargs): raise RuntimeError('PRIVATE AUDIT')
    monkeypatch.setattr(user_security, 'log_security_event', broken_log)
    result = scenario.client.post('/user/support', json=support_payload(include_diagnostics=True))
    assert result.status_code == 200 and result.json()['sent'] and len(scenario.sent) == 1
    assert 'IP:' in scenario.sent[0]['body']
