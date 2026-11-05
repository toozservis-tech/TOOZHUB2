"""Recipient-confirmed transfer, with recoverable mail delivery and no public tokens."""
from datetime import datetime, timedelta
from hashlib import sha256
from hmac import compare_digest
import secrets
import json
from fastapi import HTTPException
from sqlalchemy import or_, update
from .models import Customer, Vehicle, VehicleOwnership
from .vehicle_transfer_models import VehicleTransferInvitation as Invite
from .ownership import lock_vehicle_access, get_primary_vehicle_owner_assignment, transfer_vehicle_to_new_owner
from .schema_management import assert_module_ready
from .email_verification import pending_verification
from src.core.rbac import normalize_role


def ready(db):
    assert_module_ready(db, 'vehicle_transfers', detail_prefix='Převzetí vozidla ještě není připravené')


def active_actor(db, actor):
    if getattr(actor, 'is_disabled', False) or getattr(actor, 'is_deleted', False):
        raise HTTPException(403, 'Účet není aktivní.')
    if normalize_role(actor.role) not in ('user', 'admin', 'developer_admin'):
        raise HTTPException(403, 'Vozidlo lze převzít pouze do zákaznického účtu.')
    if pending_verification(db, actor.id):
        raise HTTPException(403, 'Nejprve ověřte e-mail svého účtu.')


def create(db, *, vehicle, archive, assignment, seller, buyer_email):
    ready(db)
    row = Invite(vehicle_id=vehicle.id, archive_id=archive.id, seller_id=seller.id,
        buyer_email=buyer_email, ownership_id=assignment.id,
        ownership_started_at=assignment.owned_from or assignment.assigned_at,
        released_at=assignment.owned_until, expires_at=datetime.utcnow() + timedelta(days=14))
    db.add(row); db.flush()
    return row


def archive_period(db, archive):
    """Resolve the exact historic period, never the vehicle's legacy email."""
    from .models import VehicleOwnershipArchive
    try:
        vehicle_id, ownership_id, started = archive.period_key.split(':', 2)
        old = db.get(VehicleOwnership, int(ownership_id))
    except (ValueError, AttributeError):
        return None
    if (old is None or old.vehicle_id != archive.vehicle_id or int(vehicle_id) != archive.vehicle_id
        or old.customer_id != archive.owner_customer_id or old.is_active or old.owned_until is None
        or (old.owned_from or old.assigned_at).isoformat() != started):
        return None
    if json.loads(archive.profile_json).get('lifecycle', {}).get('action') != 'sold':
        return None
    candidate = Invite(vehicle_id=old.vehicle_id, seller_id=old.customer_id, ownership_id=old.id,
        ownership_started_at=old.owned_from or old.assigned_at, released_at=old.owned_until)
    return old if period_available(db, candidate) else None


def can_invite_archive(db, archive, actor):
    from .schema_management import module_schema_report
    return (archive.owner_customer_id == actor.id
        and module_schema_report(db, 'vehicle_transfers')['available']
        and archive_period(db, archive) is not None
        and not any(effective_status(db, row) in ('pending', 'accepted')
            for row in db.query(Invite).filter_by(archive_id=archive.id)))


def from_archive(db, archive_id, actor, buyer_email):
    from .models import VehicleOwnershipArchive
    ready(db); active_actor(db, actor)
    archive = db.get(VehicleOwnershipArchive, archive_id)
    if archive is None or archive.owner_customer_id != actor.id:
        raise HTTPException(404, 'Archiv prodeje nebyl nalezen pro tento účet.')
    lock_vehicle_access(db, archive.vehicle_id)
    if db.get_bind().dialect.name == 'sqlite':
        db.execute(update(Vehicle).where(Vehicle.id == archive.vehicle_id).values(id=Vehicle.id))
    db.expire_all(); archive = db.get(VehicleOwnershipArchive, archive_id)
    if buyer_email == actor.email.strip().lower():
        raise HTTPException(422, 'Zadejte e-mail nového majitele, nikoli svého účtu.')
    existing = db.query(Invite).filter_by(archive_id=archive_id).order_by(Invite.id.desc()).first()
    if existing:
        if existing.buyer_email == buyer_email and effective_status(db, existing) in ('pending', 'accepted'):
            return existing
        if effective_status(db, existing) in ('pending', 'accepted', 'stale'):
            raise HTTPException(409, 'K tomuto prodeji již existuje pozvánka. Pro změnu e-mailu nejprve zrušte čekající pozvánku v Převzetí vozidla.')
    period = archive_period(db, archive)
    if period is None:
        raise HTTPException(409, 'Tento prodej již nelze použít k převodu. Vlastnictví se změnilo nebo vyžaduje ověření administrátorem.')
    if existing and existing.status == 'pending':
        existing.status = 'expired'; existing.code_digest = None
    return create(db, vehicle=db.get(Vehicle, archive.vehicle_id), archive=archive,
        assignment=period, seller=actor, buyer_email=buyer_email)


def require_admin(db, actor):
    active_actor(db, actor)
    if normalize_role(actor.role) not in ('admin', 'developer_admin'):
        raise HTTPException(403, 'Ověření převodu je dostupné pouze administrátorovi.')


def admin_review(db, vehicle_id, actor):
    from .models import VehicleOwnershipArchive
    from .vehicle_lifecycle import ownership_token, current_state
    ready(db); require_admin(db, actor)
    vehicle = db.get(Vehicle, vehicle_id)
    if vehicle is None: raise HTTPException(404, 'Vozidlo nebylo nalezeno.')
    period = get_primary_vehicle_owner_assignment(db, vehicle_id)
    archive = db.query(VehicleOwnershipArchive).filter_by(vehicle_id=vehicle_id).order_by(
        VehicleOwnershipArchive.created_at.desc(), VehicleOwnershipArchive.id.desc()).first()
    if period:
        state, version = current_state(db, period)
        identity = f'active:{ownership_token(vehicle_id, period)}:{state}:{version}'
        seller = db.get(Customer, period.customer_id)
        allowed = seller is not None and not seller.is_deleted and not seller.is_disabled
    else:
        identity = f'archive:{archive.id if archive else 0}:{archive.period_key if archive else ""}'
        seller = db.get(Customer, archive.owner_customer_id) if archive and archive.owner_customer_id else None
        allowed = bool(seller and not seller.is_deleted and not seller.is_disabled and archive_period(db, archive))
    return dict(vehicle_id=vehicle_id, title=' '.join(v for v in [vehicle.brand, vehicle.model] if v) or 'Vozidlo',
        vin=vehicle.vin, plate=vehicle.plate, owner_email=seller.email if seller else None,
        review_token=sha256(identity.encode()).hexdigest(), can_invite=allowed,
        reason=('Po ověření podkladů odešlete pozvánku. Současné vlastnictví se ukončí a soukromé podklady zůstanou v archivu. Nový majitel musí převzetí potvrdit.' if allowed else
            'Chybí ověřitelné vlastnické období. Neprovádějte převod pouze podle VIN; nejprve dořešte podklady.'),
        archive_id=None if period else (archive.id if archive else None))


def admin_invite(db, vehicle_id, actor, payload):
    from .models import DeveloperActionAuditLog, VehicleOwnershipArchive
    from .vehicle_lifecycle_models import VehicleLifecycleEvent
    from . import vehicle_lifecycle as lifecycle
    from .routers_v1.vehicle_lifecycle import VehicleLifecycleAction, VehicleSaleDetails
    ready(db); require_admin(db, actor)
    lock_vehicle_access(db, vehicle_id)
    if db.get_bind().dialect.name == 'sqlite':
        db.execute(update(Vehicle).where(Vehicle.id == vehicle_id).values(id=Vehicle.id))
    db.expire_all()
    previous = db.query(VehicleLifecycleEvent).filter_by(actor_id=actor.id, client_id=str(payload.request_id)).first()
    if previous:
        previous_result = json.loads(previous.response_json)
        row = db.get(Invite, previous_result.get('transfer_invitation_id'))
        if previous.vehicle_id != vehicle_id or previous.note != payload.reason or row is None or row.buyer_email != payload.buyer_email:
            raise HTTPException(409, 'Toto potvrzení již patří jinému převodu.')
        return row
    review = admin_review(db, vehicle_id, actor)
    if not review['can_invite'] or not compare_digest(review['review_token'], payload.review_token):
        raise HTTPException(409, 'Stav vlastnictví se změnil nebo převod není dostupný. Načtěte náhled znovu.')
    period = get_primary_vehicle_owner_assignment(db, vehicle_id)
    if period:
        seller = db.get(Customer, period.customer_id)
        if payload.buyer_email == seller.email.strip().lower():
            raise HTTPException(422, 'Nový majitel nemůže být současný vlastník.')
        _, version = lifecycle.current_state(db, period)
        result = lifecycle.apply_action(db, vehicle_id=vehicle_id, actor=actor,
            payload=VehicleLifecycleAction(client_id=payload.request_id, ownership_id=period.id,
                ownership_token=lifecycle.ownership_token(vehicle_id, period), expected_version=version,
                action='sold', note=payload.reason, sale=VehicleSaleDetails(mode='new_owner', buyer_email=payload.buyer_email)),
            legacy_assignment=period)
        row = db.get(Invite, result['transfer_invitation_id'])
    else:
        archive = db.get(VehicleOwnershipArchive, review['archive_id'])
        seller = db.get(Customer, archive.owner_customer_id)
        row = from_archive(db, archive.id, seller, payload.buyer_email)
    db.add(DeveloperActionAuditLog(developer_id=actor.id, developer_email=actor.email,
        action_type='vehicle.transfer.verified_invitation', target_resource=f'vehicle:{vehicle_id}',
        parameters_json=json.dumps({'invitation_id': row.id, 'reason': payload.reason,
            'request_id': str(payload.request_id), 'seller_id': row.seller_id}, ensure_ascii=False),
        result='success', status_code=200))
    return row


def period_available(db, row):
    old = db.get(VehicleOwnership, row.ownership_id)
    if not old or old.is_active or old.customer_id != row.seller_id:
        return False
    if (old.owned_from or old.assigned_at) != row.ownership_started_at or old.owned_until != row.released_at:
        return False
    if get_primary_vehicle_owner_assignment(db, row.vehicle_id):
        return False
    # Reject a stale invitation even if a later owner has already sold again.
    later = db.query(VehicleOwnership.id).filter(VehicleOwnership.vehicle_id == row.vehicle_id,
        or_(VehicleOwnership.owned_from >= row.released_at,
            VehicleOwnership.assigned_at >= row.released_at)).first()
    return later is None


def effective_status(db, row):
    if row.status != 'pending': return row.status
    if row.expires_at <= datetime.utcnow(): return 'expired'
    if not period_available(db, row): return 'stale'
    return 'pending'


def output(db, row, actor):
    vehicle = db.get(Vehicle, row.vehicle_id)
    sender = row.seller_id == actor.id
    return dict(id=row.id, vehicle_id=row.vehicle_id, archive_id=row.archive_id if sender else None,
        direction='sent' if sender else 'received', buyer_email=row.buyer_email,
        title=' '.join(v for v in [vehicle.brand, vehicle.model] if v) or 'Vozidlo',
        plate=vehicle.plate, vin=vehicle.vin, status=effective_status(db, row),
        delivery_status=row.delivery_status if sender else None,
        created_at=row.created_at, expires_at=row.expires_at, decided_at=row.decided_at)


def list_for(db, actor):
    ready(db); active_actor(db, actor)
    rows = db.query(Invite).filter(or_(Invite.seller_id == actor.id,
        Invite.buyer_email == actor.email.strip().lower())).order_by(Invite.id.desc()).limit(200).all()
    return {'items': [output(db, row, actor) for row in rows]}


def locked(db, invite_id, actor, *, sender=False):
    ready(db); active_actor(db, actor)
    row = db.get(Invite, invite_id)
    authorized = row and (row.seller_id == actor.id if sender else
        row.buyer_email == actor.email.strip().lower() and row.seller_id != actor.id)
    if not authorized: raise HTTPException(404, 'Pozvánka nebyla nalezena pro tento účet.')
    lock_vehicle_access(db, row.vehicle_id)
    if db.get_bind().dialect.name == 'sqlite':
        # SQLite ignores FOR UPDATE. Obtain its writer lock before refreshing
        # status, period and quota, so competing accept/cancel/resend serialize.
        db.execute(update(Invite).where(Invite.id == invite_id).values(status=Invite.status),
            execution_options={'synchronize_session': False})
    return db.query(Invite).filter_by(id=invite_id).with_for_update().populate_existing().one()


def decide(db, invite_id, actor, *, accept, code=None):
    row = locked(db, invite_id, actor)
    if row.status == 'accepted' and accept and row.accepted_by == actor.id:
        return output(db, row, actor)  # Receipt only; never re-grant after a later sale.
    if row.status == 'rejected' and not accept:
        return output(db, row, actor)
    if effective_status(db, row) != 'pending':
        raise HTTPException(409, 'Pozvánka již není platná. Vozidlo nebylo převedeno.')
    if accept:
        normalized = (code or '').strip().lower().replace(' ', '')
        if not row.code_digest or not compare_digest(row.code_digest, sha256(normalized.encode()).hexdigest()):
            raise HTTPException(422, 'Kód z pozvánky není platný. Použijte poslední odeslaný e-mail.')
        # The email code also proves control of legacy email accounts which
        # predate mandatory email verification. An authenticated email alone is insufficient.
        from src.modules.licensing.service import assert_vehicle_quota
        assert_vehicle_quota(db, actor.tenant_id, restoring_vehicle_id=row.vehicle_id, customer=actor)
        vehicle = db.get(Vehicle, row.vehicle_id)
        transfer_vehicle_to_new_owner(db, vehicle=vehicle, new_owner=actor,
            assigned_by_customer_id=actor.id, ownership_origin='confirmed_sale_invitation')
        row.status = 'accepted'; row.accepted_by = actor.id
    else:
        row.status = 'rejected'
    row.decided_at = datetime.utcnow(); row.code_digest = None
    db.flush()
    return output(db, row, actor)


def cancel(db, invite_id, actor):
    row = locked(db, invite_id, actor, sender=True)
    if row.status == 'cancelled': return output(db, row, actor)
    if row.status != 'pending': raise HTTPException(409, 'Vyřízenou pozvánku nelze zrušit.')
    row.status = 'cancelled'; row.decided_at = datetime.utcnow(); row.code_digest = None
    db.flush()
    return output(db, row, actor)


def mail_contents(row, code):
    from src.core.config import PUBLIC_API_BASE_URL
    from src.core.branding import APP_DISPLAY_NAME
    from src.modules.email_client.templates import render_email_layout
    # A plain landing URL: no address, VIN, credential or bearer token in logs.
    url = PUBLIC_API_BASE_URL.rstrip('/') + '/web/vehicle-transfer.html'
    paragraphs = [
        'Původní majitel vám nabízí převzetí vozidla do aplikace Evidence Vozidel.',
        'Přihlaste se nebo se zaregistrujte se stejným e-mailem, na který přišla tato pozvánka. '
        'Ve Vozidlech otevřete Převzetí vozidla, zkontrolujte SPZ a VIN a zadejte níže uvedený kód.',
        f'Jednorázový kód: {code}',
        'Pozvánka platí 14 dní od vytvoření. Samotné otevření e-mailu nic nepřevádí. '
        'Ceny, faktury a soukromé poznámky původního majitele zůstávají v jeho archivu.',
        'Pokud vozidlo nekupujete, pozvánku odmítněte nebo ji ignorujte.',
    ]
    return (f'{APP_DISPLAY_NAME} – pozvánka k převzetí vozidla', '\n\n'.join(paragraphs),
        render_email_layout(title='Převzetí vozidla', subtitle='Nejdříve zkontrolujte vozidlo, potom potvrďte převzetí.',
            intro='Dobrý den,', paragraphs=paragraphs, cta_label='Otevřít převzetí vozidla', cta_url=url))


def send_invitation(db, invite_id, actor, *, resend=False):
    """After the sale commit. Mail failure must never roll back or repeat a sale.

    Store a delivery attempt before contacting the provider. A process interruption
    is visible as unconfirmed sending; explicit resend rotates the code after 60 s.
    """
    row = locked(db, invite_id, actor, sender=True)
    if effective_status(db, row) != 'pending':
        raise HTTPException(409, 'Pozvánka již není platná; e-mail nebyl odeslán.')
    if not resend and row.delivery_status != 'pending':
        return output(db, row, actor)
    now = datetime.utcnow()
    if row.delivery_attempted_at and now - row.delivery_attempted_at < timedelta(seconds=60):
        raise HTTPException(429, 'Další pozvánku můžete odeslat za minutu.', headers={'Retry-After': '60'})
    code = secrets.token_hex(16)
    digest = sha256(code.encode()).hexdigest()
    row.code_digest = digest; row.delivery_status = 'sending'; row.delivery_attempted_at = now
    db.commit()
    subject, body, html = mail_contents(row, code)
    try:
        from src.modules.email_client.service import EmailService
        sent = bool(EmailService().send_simple_email(row.buyer_email, subject, body, html))
    except Exception:
        sent = False  # Never print code, destination or provider response.
    # Do not revive a cancelled/accepted invite or overwrite a newer resend.
    db.query(Invite).filter(Invite.id == invite_id, Invite.code_digest == digest,
        Invite.status == 'pending').update({'delivery_status': 'sent' if sent else 'failed',
            'sent_at': now if sent else None}, synchronize_session=False)
    db.commit(); db.expire_all()
    return output(db, db.get(Invite, invite_id), actor)
