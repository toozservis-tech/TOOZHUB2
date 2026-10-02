"""Reservation recipients and permissions, with real relationships and fake mail."""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import (
    Customer, Tenant, Vehicle, Reservation, ServiceCustomerLink,
    ServiceCustomerInvite, ServiceVehicleAccess, VehicleServiceLink, EmailNotificationLog,
)
from src.modules.vehicle_hub.ownership import ensure_vehicle_owner_assignment
from src.modules.vehicle_hub.service_access import create_or_update_vehicle_service_link
from src.modules.vehicle_hub.routers_v1 import services, reservations
from src.modules.vehicle_hub.routers_v1 import service_workspace as workspace
from src.modules.vehicle_hub.routers_v1.schemas import ReservationCreateV1, ReservationUpdateV1
from src.modules.vehicle_hub.email_notifications import send_reservation_created_email


class Mailbox:
    def __init__(self):
        self.messages = []

    def is_configured(self):
        return True

    def send_email(self, message):
        self.messages.append(message)
        return True


def request():
    return Request({'type': 'http', 'method': 'POST', 'path': '/api/v1/reservations',
                    'headers': [(b'x-geo-lat', b'49.75'), (b'x-geo-lon', b'16.47')],
                    'query_string': b''})


@pytest.fixture
def state(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'routing.sqlite'}")
    @event.listens_for(engine, 'connect')
    def foreign_keys(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False)()
    actors = {}
    for name, role in [('owner', 'user'), ('stranger', 'user'), ('service', 'service'),
                       ('other_service', 'service'), ('admin', 'developer_admin'),
                       ('disabled', 'service'), ('deleted', 'service')]:
        tenant = Tenant(name=name, license_key='routing-' + name)
        db.add(tenant); db.flush()
        actor = Customer(tenant_id=tenant.id, email=name+'@example.com',
                         name='Same display name', role=role, password_hash='synthetic',
                         is_disabled=name == 'disabled', is_deleted=name == 'deleted')
        db.add(actor); db.flush(); actors[name] = actor
    owner = actors['owner']
    car = Vehicle(tenant_id=owner.tenant_id, user_email=owner.email, nickname='Owner car', plate='1AB2345')
    db.add(car); db.flush(); ensure_vehicle_owner_assignment(db, vehicle=car, owner=owner)
    for name in ['service', 'admin', 'disabled', 'deleted']:
        target = actors[name]
        db.add(ServiceCustomerLink(service_customer_id=target.id, service_tenant_id=target.tenant_id,
               customer_id=owner.id, customer_tenant_id=owner.tenant_id, status='active'))
    db.commit()
    mailbox = Mailbox()
    monkeypatch.setattr(services, '_geocode_address', lambda _: None)
    monkeypatch.setattr(reservations, 'send_reservation_created_email',
                        lambda db, row, **kwargs: send_reservation_created_email(db, row, mailbox, **kwargs))
    yield SimpleNamespace(db=db, car=car, mailbox=mailbox, **actors)
    db.close(); engine.dispose()


def create(s, actor=None, target=None):
    return reservations.create_reservation(ReservationCreateV1(
        service_id=(target or s.service).id, vehicle_id=s.car.id,
        start_datetime=datetime.utcnow()+timedelta(days=2), service_type='Test reservation'),
        request=request(), current_user=actor or s.owner, db=s.db)


def test_catalogs_exclude_admin_disabled_and_deleted_legacy_links(state):
    s = state
    assert {row['id'] for row in services.get_services(current_user=s.owner, db=s.db)} == {s.service.id}
    assert {row['id'] for row in services.get_my_service_contacts(current_user=s.owner, db=s.db)['services']} == {s.service.id}
    assert {row['id'] for row in services.get_services_discovery(request(), current_user=s.owner, db=s.db)['services']} == {s.service.id}
    # Unlinked foreign tenants stay hidden; admins retain their global service view.
    assert {row['id'] for row in services.get_services(current_user=s.admin, db=s.db)} == {s.service.id, s.other_service.id}


@pytest.mark.parametrize('target', ['admin', 'owner', 'disabled', 'deleted'])
def test_invalid_service_target_rejected_before_writes_and_mail(state, target):
    s = state
    with pytest.raises(HTTPException) as error:
        create(s, target=getattr(s, target))
    assert error.value.status_code == 404
    assert s.db.query(Reservation).count() == 0
    assert s.db.query(ServiceCustomerInvite).count() == 0
    assert s.db.query(ServiceVehicleAccess).count() == 0
    assert s.mailbox.messages == []


def test_selected_service_id_controls_mail_even_with_identical_names(state):
    s = state
    row = create(s)
    assert row.service_id == s.service.id and row.customer_id == s.owner.id
    assert [m.to for m in s.mailbox.messages] == [[s.owner.email], [s.service.email]]
    service_mail = s.mailbox.messages[1]
    assert '/web/reservations.html' in service_mail.html_body
    assert '/web_admin/' not in service_mail.html_body
    assert 'administračním panelu' not in service_mail.body
    assert {(log.customer_id, log.email) for log in s.db.query(EmailNotificationLog)} == {
        (s.owner.id, s.owner.email), (s.service.id, s.service.email)}
    assert s.db.query(VehicleServiceLink).count() == 0
    assert s.db.query(ServiceVehicleAccess).count() == 0
    assert s.db.query(ServiceCustomerInvite).count() == 0


@pytest.mark.parametrize('target', ['admin', 'disabled', 'deleted'])
def test_historical_invalid_service_does_not_receive_mail(state, target):
    s = state
    row = Reservation(tenant_id=s.owner.tenant_id, customer_id=s.owner.id,
        vehicle_id=s.car.id, service_id=getattr(s, target).id,
        start_datetime=datetime.utcnow(), status='PENDING')
    s.db.add(row); s.db.commit()
    assert send_reservation_created_email(s.db, row, s.mailbox) == (False, False)
    assert s.mailbox.messages == []


def test_foreign_customer_cannot_book_owner_vehicle(state):
    s = state
    with pytest.raises(HTTPException) as error:
        create(s, actor=s.stranger)
    assert error.value.status_code == 403
    assert s.db.query(Reservation).count() == 0


def test_service_booking_requires_current_vehicle_permission(state):
    s = state
    with pytest.raises(HTTPException) as error:
        create(s, actor=s.service)
    assert error.value.status_code == 403
    grant = create_or_update_vehicle_service_link(s.db, tenant_id=s.owner.tenant_id,
        service_customer_id=s.service.id, owner_customer_id=s.owner.id,
        vehicle_id=s.car.id, approved_by_customer_id=s.owner.id, source_type='direct_user_grant')
    s.db.commit()
    row = create(s, actor=s.service)
    assert row.customer_id == s.owner.id
    grant.status = 'revoked'; s.db.commit()
    with pytest.raises(HTTPException) as error:
        create(s, actor=s.service)
    assert error.value.status_code == 403


def test_service_cannot_book_as_other_service(state):
    s = state
    with pytest.raises(HTTPException) as error:
        create(s, actor=s.other_service)
    assert error.value.status_code == 403
    assert s.db.query(Reservation).count() == 0


def test_visibility_for_customer_selected_service_and_global_admin(state):
    s = state
    row = create(s)
    assert [r.id for r in reservations.get_my_reservations(current_user=s.owner, db=s.db)] == [row.id]
    assert reservations.get_my_reservations(current_user=s.stranger, db=s.db) == []
    assert [r.id for r in reservations.get_service_reservations(current_user=s.service, db=s.db)] == [row.id]
    assert reservations.get_service_reservations(current_user=s.other_service, db=s.db) == []
    assert [r.id for r in reservations.get_service_reservations(current_user=s.admin, db=s.db)] == [row.id]
    for actor in [s.stranger, s.other_service]:
        for operation in [
            lambda: reservations.get_reservation(row.id, current_user=actor, db=s.db),
            lambda: reservations.update_reservation(row.id, ReservationUpdateV1(status='CANCELLED'), request(), current_user=actor, db=s.db),
            lambda: reservations.delete_reservation(row.id, request(), current_user=actor, db=s.db),
        ]:
            with pytest.raises(HTTPException) as error:
                operation()
            assert error.value.status_code == 403


@pytest.mark.parametrize('role', [' User ', 'unexpected'])
def test_nonstandard_user_role_cannot_replan_or_act_as_a_service(state, role):
    s = state
    s.owner.role = role; s.db.commit()
    row = create(s)
    with pytest.raises(HTTPException) as error:
        reservations.update_reservation(row.id, ReservationUpdateV1(note='unauthorized change'),
            request(), current_user=s.owner, db=s.db)
    assert error.value.status_code == 403
    assert row.note is None


def test_admin_cannot_be_granted_service_vehicle_access(state):
    s = state
    with pytest.raises(HTTPException) as error:
        services.grant_vehicle_access_to_service(services.VehicleAccessGrantRequest(
            vehicle_id=s.car.id, service_id=s.admin.id), current_user=s.owner, db=s.db)
    assert error.value.status_code == 404
    assert s.db.query(VehicleServiceLink).count() == 0


def test_legacy_admin_invitation_cannot_restore_wrong_service_contact(state, monkeypatch):
    s = state
    # Authentication is verified separately; this test exercises the role of
    # the invitation sender against real persisted invitation relationships.
    monkeypatch.setattr(workspace, '_require_invitation_recipient', lambda *_: None)
    invitation = ServiceCustomerInvite(service_customer_id=s.admin.id,
        service_tenant_id=s.admin.tenant_id, invite_email=s.owner.email,
        token='synthetic_invitation_token_only', status='pending',
        expires_at=datetime.utcnow()+timedelta(days=1))
    s.db.add(invitation); s.db.commit()
    assert workspace.list_incoming_service_invitations(current_user=s.owner, db=s.db)['items'] == []
    with pytest.raises(HTTPException) as error:
        workspace.accept_service_invitation(workspace.AcceptServiceInviteRequest(
            invitation_id=invitation.id, decision='accept'), current_user=s.owner, db=s.db)
    assert error.value.status_code == 409
    assert invitation.status == 'pending'
