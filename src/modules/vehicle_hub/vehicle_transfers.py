"""Recipient-confirmed transfer, with recoverable mail delivery and no public tokens."""
from datetime import datetime, timedelta
from hashlib import sha256
from hmac import compare_digest
import secrets
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
