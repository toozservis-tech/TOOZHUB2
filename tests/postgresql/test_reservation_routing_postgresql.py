"""HTTP reservation routing on a fresh local PostgreSQL database; fake mail only."""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.modules.vehicle_hub.database import get_db
from src.modules.vehicle_hub.models import Customer, Tenant, Vehicle, Reservation, ServiceCustomerLink, VehicleServiceLink
from src.modules.vehicle_hub.ownership import ensure_vehicle_owner_assignment
from src.modules.vehicle_hub.routers_v1 import services, reservations
from src.modules.vehicle_hub.routers_v1.auth import get_current_user
from src.modules.vehicle_hub.email_notifications import send_reservation_created_email


@pytest.fixture
def scenario(pg_db, monkeypatch):
    db = pg_db.sessions()
    actors = {}
    for key, role in [('owner', 'user'), ('service', 'service'), ('admin', 'developer_admin'), ('other', 'service')]:
        tenant = Tenant(name=key, license_key='pg-booking-' + key)
        db.add(tenant); db.flush()
        row = Customer(tenant_id=tenant.id, name='Same name', email=key+'@example.com',
                       password_hash='synthetic', role=role)
        db.add(row); db.flush(); actors[key] = row
    owner = actors['owner']; service = actors['service']
    vehicle = Vehicle(tenant_id=owner.tenant_id, user_email=owner.email, plate='1AB2345')
    db.add(vehicle); db.flush(); ensure_vehicle_owner_assignment(db, vehicle=vehicle, owner=owner)
    for target in [service, actors['admin']]:
        db.add(ServiceCustomerLink(service_customer_id=target.id, service_tenant_id=target.tenant_id,
            customer_id=owner.id, customer_tenant_id=owner.tenant_id, status='active'))
    db.commit()
    sent = []
    class Mail:
        def is_configured(self): return True
        def send_email(self, message): sent.append(message); return True
    monkeypatch.setattr(reservations, 'send_reservation_created_email',
                        lambda db, row: send_reservation_created_email(db, row, Mail()))
    monkeypatch.setattr(services, '_geocode_address', lambda _: None)
    app = FastAPI(); actor = [owner]
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: actor[0]
    app.include_router(reservations.router, prefix='/api/v1')
    app.include_router(services.router, prefix='/api/v1')
    with TestClient(app) as client:
        yield SimpleNamespace(db=db, client=client, vehicle=vehicle, actor=actor, sent=sent, **actors)
    db.close()


def booking(s, target):
    return {'service_id': target.id, 'vehicle_id': s.vehicle.id, 'service_type': 'Synthetic check',
            'start_datetime': (datetime.utcnow()+timedelta(days=2)).isoformat()}


def test_postgres_rejects_admin_booking_and_preserves_exact_service_recipient(scenario):
    s = scenario
    assert s.client.post('/api/v1/reservations', json=booking(s, s.admin)).status_code == 404
    assert s.db.query(Reservation).count() == 0 and s.sent == []
    result = s.client.post('/api/v1/reservations', json=booking(s, s.service))
    assert result.status_code == 200
    assert result.json()['service_id'] == s.service.id
    assert [m.to for m in s.sent] == [[s.owner.email], [s.service.email]]
    assert s.db.query(VehicleServiceLink).count() == 0
    for role, expected_count in [(s.service, 1), (s.other, 0), (s.admin, 1)]:
        s.actor[0] = role
        assert len(s.client.get('/api/v1/reservations/service').json()) == expected_count


def test_postgres_service_cannot_bypass_owner_permission(scenario):
    s = scenario; s.actor[0] = s.service
    result = s.client.post('/api/v1/reservations', json=booking(s, s.service))
    assert result.status_code == 403
    assert s.db.query(Reservation).count() == 0 and s.sent == []


def test_postgres_catalog_filters_admin_legacy_contact_across_tenants(scenario):
    s = scenario
    for path, envelope in [('/api/v1/services', None), ('/api/v1/services/my-contacts', 'services'),
                            ('/api/v1/services/discovery', 'services')]:
        result = s.client.get(path, headers={'x-geo-lat': '49.75', 'x-geo-lon': '16.47'})
        assert result.status_code == 200
        data = result.json(); rows = data[envelope] if envelope else data
        assert {row['id'] for row in rows} == {s.service.id}
