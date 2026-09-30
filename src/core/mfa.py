"""Transactional TOTP verification and short-lived, hashed login challenges."""
import base64
import hashlib
import hmac
import re
import secrets
import time
from datetime import datetime, timedelta

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from src.core.config import JWT_SECRET_KEY
from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import CustomerSecuritySettings
from src.modules.vehicle_hub.account_state import customer_session_version


class MFAState(Base):
    __tablename__ = 'mfa_security_state'
    customer_id = Column(Integer, ForeignKey('customers.id', ondelete='CASCADE'), primary_key=True)
    pending_expires_at = Column(DateTime, nullable=True)
    last_step = Column(Integer, nullable=False, default=-1)


class MFALoginChallenge(Base):
    __tablename__ = 'mfa_login_challenges'
    digest = Column(String(64), primary_key=True)
    customer_id = Column(Integer, ForeignKey('customers.id', ondelete='CASCADE'), nullable=False, index=True)
    session_version = Column(Integer, nullable=False)
    expected_role = Column(String, nullable=False, default='')
    attempts = Column(Integer, nullable=False, default=0)
    expires_at = Column(DateTime, nullable=False, index=True)


class MFAAttemptBudget(Base):
    __tablename__ = 'mfa_attempt_budgets'
    customer_id = Column(Integer, ForeignKey('customers.id', ondelete='CASCADE'), primary_key=True)
    action = Column(String(32), primary_key=True)
    window = Column(Integer, nullable=False)
    attempts = Column(Integer, nullable=False)


def limit_attempt(db, customer_id, action, *, limit=5):
    """Atomic per-account budget persists across process restarts and workers.

    Call before taking verification locks or changing account state: this commits
    the attempt even when later password/OTP validation raises an HTTP error.
    """
    from sqlalchemy import case, or_
    dialect = db.get_bind().dialect.name
    if dialect == 'postgresql':
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == 'sqlite':
        from sqlalchemy.dialects.sqlite import insert
    else:
        raise HTTPException(503, 'Ověření nyní není dostupné.')
    window = int(time.time()) // 900
    table = MFAAttemptBudget
    statement = insert(table).values(customer_id=customer_id, action=action, window=window, attempts=1)
    statement = statement.on_conflict_do_update(
        index_elements=['customer_id', 'action'],
        set_={'window': window, 'attempts': case((table.window != window, 1), else_=table.attempts + 1)},
        where=or_(table.window != window, table.attempts < limit),
    )
    changed = db.execute(statement).rowcount
    db.commit()
    if changed != 1:
        raise HTTPException(429, 'Příliš mnoho pokusů. Vyčkejte a zkuste to později.',
                            headers={'Retry-After': str(900 - int(time.time()) % 900)})


def encrypt_legacy_seeds(db):
    """Upgrade valid legacy seeds without changing the user's authenticator."""
    count = 0
    for settings in db.query(CustomerSecuritySettings).filter(CustomerSecuritySettings.totp_secret.isnot(None)).with_for_update():
        stored = settings.totp_secret
        if re.fullmatch('[A-Z2-7]{32}', stored):
            settings.totp_secret = protect_secret(stored)
            count += 1
    db.commit()
    return count


def _cipher():
    # Purpose-separated key. Database backups contain ciphertext, not TOTP seeds.
    # JWT root rotation MUST re-encrypt stored seeds before retiring the old key.
    key=hmac.new(JWT_SECRET_KEY.encode(), b'SpravaVozidel/TOTP/storage/v1', hashlib.sha256).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def protect_secret(secret: str) -> str:
    return 'enc:v1:' + _cipher().encrypt(secret.encode('ascii')).decode('ascii')


def read_secret(stored: str | None) -> str:
    value=stored or ''
    if value.startswith('enc:v1:'):
        try: value=_cipher().decrypt(value[7:].encode('ascii')).decode('ascii')
        except (InvalidToken, UnicodeError, ValueError):
            raise HTTPException(503, 'Ověření účtu není nyní dostupné. Kontaktujte podporu.') from None
    # Read old enrolled factors without forcing users to disable their protection.
    if not re.fullmatch('[A-Z2-7]{32}', value):
        raise HTTPException(503, 'Ověření účtu není nyní dostupné. Kontaktujte podporu.')
    return value


def locked_settings(db, customer):
    settings=(db.query(CustomerSecuritySettings).filter(CustomerSecuritySettings.customer_id==customer.id)
              .with_for_update().populate_existing().first())
    if settings is None:
        settings=CustomerSecuritySettings(tenant_id=customer.tenant_id,customer_id=customer.id,
            two_factor_enabled=False,biometric_enabled=False,biometric_preferred=False)
        db.add(settings); db.flush()
    return settings


def state_for(db, customer_id):
    state=db.get(MFAState,customer_id)
    if state is None:
        state=MFAState(customer_id=customer_id,last_step=-1)
        db.add(state); db.flush()
    return state


def consume_code(db, settings, code: str, *, now=None) -> bool:
    from src.server.security_helpers import calculate_totp, TOTP_PERIOD_SECONDS
    if not re.fullmatch('[0-9]{6}', code or ''):
        return False
    secret=read_secret(settings.totp_secret)
    now=int(time.time() if now is None else now)
    matched=None
    for offset in (-1,0,1):
        step=now//TOTP_PERIOD_SECONDS+offset
        if hmac.compare_digest(calculate_totp(secret,step*TOTP_PERIOD_SECONDS),code): matched=step
    if matched is None: return False
    state_for(db,settings.customer_id)
    # Conditional UPDATE protects even backends where row locks are unavailable.
    changed=(db.query(MFAState).filter(MFAState.customer_id==settings.customer_id,MFAState.last_step<matched)
             .update({MFAState.last_step:matched},synchronize_session='fetch'))
    if changed != 1: return False
    if not settings.totp_secret.startswith('enc:v1:'):
        settings.totp_secret=protect_secret(secret)
    return True


def create_login_challenge(db, customer, expected_role=None):
    now=datetime.utcnow()
    db.query(MFALoginChallenge).filter(MFALoginChallenge.expires_at<=now).delete(synchronize_session=False)
    token=secrets.token_urlsafe(32)
    db.add(MFALoginChallenge(digest=hashlib.sha256(token.encode()).hexdigest(),customer_id=customer.id,
        session_version=customer_session_version(customer),expected_role=expected_role or '',
        expires_at=now+timedelta(minutes=5),attempts=0))
    db.commit()
    return token,300


def verified_claims(customer):
    return {'sub':customer.email,'sv':customer_session_version(customer),
            'amr':['pwd','otp'],'mfa_at':int(time.time())}


ADMIN_VERIFICATION_SECONDS = 15 * 60
ADMIN_BOOTSTRAP_ROUTES = frozenset({
    ('GET', '/user/me'), ('GET', '/user/email-verification'),
    ('POST', '/user/email-verification/resend'),
    ('GET', '/user/security/settings'), ('GET', '/user/security/admin-status'),
    ('POST', '/user/security/admin-verify'), ('POST', '/user/security/totp/setup'),
    ('POST', '/user/security/totp/enable'), ('PUT', '/user/change-password'),
})


def admin_assurance_status(db, customer, claims):
    required = (customer.role or '').strip().lower() in {'admin', 'developer_admin'}
    settings = db.query(CustomerSecuritySettings).filter_by(customer_id=customer.id).first() if required else None
    enrolled = bool(settings and settings.two_factor_enabled)
    if enrolled:
        read_secret(settings.totp_secret)  # Fail closed on missing/corrupt configured factors.
    checked_at = claims.get('mfa_at')
    valid_timestamp = isinstance(checked_at, (int, float)) and not isinstance(checked_at, bool)
    fresh = valid_timestamp and 0 <= time.time() - checked_at < ADMIN_VERIFICATION_SECONDS
    verified = not required or bool(enrolled and fresh and claims.get('amr') == ['pwd', 'otp'])
    return {'required': required, 'enrolled': enrolled, 'verified': verified,
            'valid_until': int(checked_at + ADMIN_VERIFICATION_SECONDS) if required and verified else None}


def require_admin_assurance(db, customer, claims):
    if not admin_assurance_status(db, customer, claims)['verified']:
        raise HTTPException(403, 'Pro přístup administrátora potvrďte heslo a nový kód z autentikátoru.',
                            headers={'X-Admin-Verification': 'required'})
