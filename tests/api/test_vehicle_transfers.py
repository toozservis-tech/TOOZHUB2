"""No real mail or vehicle. Exercise consent, stale periods, quota and private archives."""
from datetime import datetime, timedelta
from hashlib import sha256
import re
import pytest
from fastapi import HTTPException, FastAPI
from fastapi.testclient import TestClient
from test_vehicle_lifecycle import ctx, payload, apply
from src.modules.vehicle_hub import vehicle_transfers as domain
from src.modules.vehicle_hub.vehicle_transfer_models import VehicleTransferInvitation as Invite
from src.modules.vehicle_hub.models import Tenant, Customer, Vehicle, VehicleOwnership, VehicleOwnershipArchive, License
from src.modules.vehicle_hub.email_verification import EmailVerification
from src.modules.vehicle_hub.routers_v1 import vehicle_transfers as routes, vehicle_archives
from src.modules.vehicle_hub.ownership import transfer_vehicle_to_new_owner, release_vehicle_owner_assignment
from src.modules.vehicle_hub.database import get_db
from src.modules.vehicle_hub.routers_v1.auth import get_current_user

@pytest.fixture
def sale(ctx, monkeypatch):
    db, seller, service, buyer, vehicle, assignment, link = ctx
    seller.email = 'seller@example.com'; buyer.email = 'buyer@example.com'
    tenant = Tenant(name='Buyer', license_key='buyer-test'); db.add(tenant); db.flush()
    buyer.tenant_id = tenant.id
    db.commit()
    mail = []
    def capture(self, *args, **kwargs): mail.append(args); return True
    monkeypatch.setattr('src.modules.email_client.service.EmailService.send_simple_email', capture)
    request = payload(ctx, 'sold', sale={'mode': 'new_owner', 'buyer_email': buyer.email})
    result = apply(ctx, request)
    row = db.get(Invite, result['transfer_invitation_id'])
    code = re.search(r'Jednorázový kód: ([0-9a-f]+)', mail[0][2]).group(1)
    return ctx, row, code, mail, request


def test_sale_sends_one_email_but_never_grants_until_confirmed(sale):
    ctx, row, code, mail, request = sale
    db, seller, service, buyer, vehicle, assignment, link = ctx
    assert not assignment.is_active and link.status == 'revoked'
    assert row.status == 'pending' and row.delivery_status == 'sent'
    assert row.code_digest == sha256(code.encode()).hexdigest()
    assert code not in str(domain.list_for(db, buyer))
    assert not db.query(VehicleOwnership).filter_by(customer_id=buyer.id, is_active=True).first()
    apply(ctx, request)
    assert len(mail) == 1 and db.query(Invite).count() == 1
    accepted = routes.decide_transfer(row.id, routes.Decision(accept=True, code=code), buyer, db)
    assert accepted['status'] == 'accepted'
    assert vehicle.user_email == buyer.email and vehicle.tenant_id == buyer.tenant_id
    assert db.query(VehicleOwnership).filter_by(customer_id=buyer.id, is_active=True).count() == 1
    assert routes.decide_transfer(row.id, routes.Decision(accept=True), buyer, db)['status'] == 'accepted'
    assert db.query(VehicleOwnership).filter_by(customer_id=buyer.id, is_active=True).count() == 1
    assert vehicle_archives.list_archives(buyer, db) == []
    with pytest.raises(HTTPException) as error: vehicle_archives.archive_detail(row.archive_id, buyer, db)
    assert error.value.status_code == 404
    assert vehicle_archives.archive_detail(row.archive_id, seller, db)['profile']['lifecycle']['sale']['buyer_email'] == buyer.email


def test_code_and_account_are_both_required_and_unverified_denied(sale):
    ctx, row, code, _, _ = sale
    db, seller, service, buyer, *_ = ctx
    for who, value, status in [(seller, code, 404), (service, code, 403), (buyer, None, 422), (buyer, 'wrong', 422)]:
        with pytest.raises(HTTPException) as error: routes.decide_transfer(row.id, routes.Decision(accept=True, code=value), who, db)
        assert error.value.status_code == status
        assert db.get(Invite, row.id).status == 'pending'
    db.add(EmailVerification(customer_id=buyer.id)); db.commit()
    with pytest.raises(HTTPException) as error: routes.decide_transfer(row.id, routes.Decision(accept=True, code=code), buyer, db)
    assert error.value.status_code == 403


@pytest.mark.parametrize('state', ['expired', 'cancelled', 'rejected'])
def test_final_and_expired_invites_cannot_be_accepted(sale, state):
    ctx, row, code, _, _ = sale
    db, seller, _, buyer, *_ = ctx
    if state == 'expired': row.expires_at = datetime.utcnow() - timedelta(seconds=1); db.commit()
    elif state == 'cancelled': routes.cancel_transfer(row.id, seller, db)
    else: routes.decide_transfer(row.id, routes.Decision(accept=False), buyer, db)
    with pytest.raises(HTTPException) as error: routes.decide_transfer(row.id, routes.Decision(accept=True, code=code), buyer, db)
    assert error.value.status_code == 409
    assert not db.query(VehicleOwnership).filter_by(customer_id=buyer.id, is_active=True).first()


def test_later_owner_even_released_again_invalidates_old_invite(sale):
    ctx, row, code, _, _ = sale
    db, seller, service, buyer, vehicle, *_ = ctx
    transfer_vehicle_to_new_owner(db, vehicle=vehicle, new_owner=service)
    release_vehicle_owner_assignment(db, vehicle=vehicle, owner=service, revoked_by_customer_id=service.id)
    db.commit()
    assert domain.output(db, row, seller)['status'] == 'stale'
    with pytest.raises(HTTPException) as error: routes.decide_transfer(row.id, routes.Decision(accept=True, code=code), buyer, db)
    assert error.value.status_code == 409


def test_recipient_limit_does_not_consume_invitation(sale):
    ctx, row, code, _, _ = sale
    db, _, _, buyer, *_ = ctx
    db.add(Vehicle(tenant_id=buyer.tenant_id, user_email=buyer.email, vin='TMBAB7NE0F0999999'))
    db.commit()
    with pytest.raises(HTTPException) as error: routes.decide_transfer(row.id, routes.Decision(accept=True, code=code), buyer, db)
    assert error.value.status_code == 403 and db.get(Invite, row.id).status == 'pending'
    # Grant a valid local license as test data, then retry the identical consent.
    db.add(License(tenant_id=buyer.tenant_id, plan='premium', status='active', vehicles_limit=0))
    db.commit()
    assert routes.decide_transfer(row.id, routes.Decision(accept=True, code=code), buyer, db)['status'] == 'accepted'


def test_resend_rotates_code_and_failure_is_visible(sale, monkeypatch):
    ctx, row, old_code, mail, _ = sale
    db, seller, _, buyer, *_ = ctx
    with pytest.raises(HTTPException) as error: routes.resend_transfer(row.id, seller, db)
    assert error.value.status_code == 429
    row.delivery_attempted_at -= timedelta(minutes=2); db.commit()
    monkeypatch.setattr('src.modules.email_client.service.EmailService.send_simple_email', lambda *a, **k: False)
    assert routes.resend_transfer(row.id, seller, db)['delivery_status'] == 'failed'
    with pytest.raises(HTTPException): routes.decide_transfer(row.id, routes.Decision(accept=True, code=old_code), buyer, db)
    assert db.get(Invite, row.id).status == 'pending'


def test_mail_failure_does_not_undo_sale(ctx, monkeypatch):
    monkeypatch.setattr('src.modules.email_client.service.EmailService.send_simple_email', lambda *a, **k: False)
    result = apply(ctx, payload(ctx, 'sold'))
    assert not ctx[5].is_active
    assert ctx[0].get(Invite, result['transfer_invitation_id']).delivery_status == 'failed'


def test_admin_privileged_archive_policy_explicit(sale):
    ctx, row, *_ = sale
    db, _, service, buyer, *_ = ctx
    for role in ('admin', 'developer_admin'):
        service.role = role; db.commit()
        # Existing privileged archive policy is unchanged; not granted by being buyer.
        assert vehicle_archives.archive_detail(row.archive_id, service, db)['profile']['lifecycle']['sale']['buyer_email'] == buyer.email
    service.role = 'service'; db.commit()
    with pytest.raises(HTTPException): vehicle_archives.archive_detail(row.archive_id, service, db)


def test_http_inbox_is_read_only_and_buyer_get_has_no_private_archive_id(sale):
    ctx, row, code, _, _ = sale
    db, seller, _, buyer, *_ = ctx
    app = FastAPI(); app.include_router(routes.router, prefix='/api/v1')
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: buyer
    with TestClient(app) as client:
        item = client.get('/api/v1/vehicle-transfers').json()['items'][0]
        assert item['direction'] == 'received' and item['archive_id'] is None
        assert row.status == 'pending'
        assert client.get(f'/api/v1/vehicle-transfers/{row.id}/decision').status_code == 405
        assert client.post(f'/api/v1/vehicle-transfers/{row.id}/cancel').status_code == 404
        assert client.post(f'/api/v1/vehicle-transfers/{row.id}/decision', json={'accept': True, 'code': code}).json()['status'] == 'accepted'


def test_migration_is_additive_and_repeatable(ctx):
    from scripts.migrate_vehicle_transfers import migrate
    db = ctx[0]
    db.commit()
    migrate(db.get_bind()); migrate(db.get_bind())
    assert ctx[5].is_active


def test_parallel_confirmation_is_one_transfer_and_one_receipt(sale):
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy.orm import Session
    ctx, row, code, _, _ = sale
    db, _, _, buyer, *_ = ctx
    invite_id, buyer_id, engine = row.id, buyer.id, db.get_bind()
    db.commit()
    def accept_once(_):
        with Session(engine) as concurrent_db:
            return routes.decide_transfer(invite_id, routes.Decision(accept=True, code=code),
                concurrent_db.get(Customer, buyer_id), concurrent_db)['status']
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(accept_once, range(2))) == ['accepted', 'accepted']
    db.expire_all()
    assert db.query(VehicleOwnership).filter_by(customer_id=buyer_id, is_active=True).count() == 1


def test_erasure_covers_transfer_contact_and_foreign_keys(sale):
    from src.modules.vehicle_hub.account_erasure import erase_account
    ctx, row, code, _, _ = sale
    db, seller, _, buyer, *_ = ctx
    routes.decide_transfer(row.id, routes.Decision(accept=True, code=code), buyer, db)
    erase_account(db, seller); db.commit()
    assert db.query(Invite).count() == 0
    assert db.query(VehicleOwnership).filter_by(customer_id=buyer.id,is_active=True).count() == 1


def test_new_recipient_can_register_later_then_accept(ctx, monkeypatch):
    db, seller, _, _, vehicle, *_ = ctx
    recipient = 'future-owner@example.com'
    assert not db.query(Customer).filter_by(email=recipient).first()
    mail = []
    def capture(self, *args, **kwargs): mail.append(args); return True
    monkeypatch.setattr('src.modules.email_client.service.EmailService.send_simple_email', capture)
    result = apply(ctx, payload(ctx, 'sold', sale={'mode': 'new_owner', 'buyer_email': recipient}))
    invite = db.get(Invite, result['transfer_invitation_id'])
    assert invite.status == 'pending' and len(mail) == 1
    # Registration creates an account; the normal email-verification guard still applies.
    tenant = Tenant(name='Future owner', license_key='future-owner-qa'); db.add(tenant); db.flush()
    user = Customer(tenant_id=tenant.id, email=recipient, name='Future owner', role='user', password_hash='qa-unused')
    db.add(user); db.flush(); verification = EmailVerification(customer_id=user.id); db.add(verification); db.commit()
    code = re.search(r'Jednorázový kód: ([0-9a-f]+)', mail[0][2]).group(1)
    with pytest.raises(HTTPException) as error:
        routes.decide_transfer(invite.id, routes.Decision(accept=True, code=code), user, db)
    assert error.value.status_code == 403
    verification.verified_at = datetime.utcnow(); db.commit()
    assert domain.list_for(db, user)['items'][0]['status'] == 'pending'
    assert routes.decide_transfer(invite.id, routes.Decision(accept=True, code=code), user, db)['status'] == 'accepted'
    assert vehicle.user_email == recipient


def test_repeated_acceptance_after_resale_is_receipt_only(sale):
    ctx, row, code, _, _ = sale
    db, seller, _, buyer, vehicle, *_ = ctx
    routes.decide_transfer(row.id, routes.Decision(accept=True, code=code), buyer, db)
    transfer_vehicle_to_new_owner(db, vehicle=vehicle, new_owner=seller); db.commit()
    assert routes.decide_transfer(row.id, routes.Decision(accept=True, code=code), buyer, db)['status'] == 'accepted'
    assert db.query(VehicleOwnership).filter_by(vehicle_id=vehicle.id, customer_id=seller.id, is_active=True).count() == 1
    assert db.query(VehicleOwnership).filter_by(vehicle_id=vehicle.id, customer_id=buyer.id, is_active=True).count() == 0
