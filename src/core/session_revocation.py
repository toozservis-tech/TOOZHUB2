"""Durable, per-token logout. Only non-reversible token digests are stored.

A signed unexpired token is enough to revoke itself; logout intentionally does
not require a still-active account, verified email or current admin assurance.
"""
import hashlib
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import Column, DateTime, String, delete, select
from sqlalchemy.exc import SQLAlchemyError

from src.core.private_errors import report_exception
from src.core.security import decode_access_token_payload, decode_logout_ticket
from src.modules.vehicle_hub.database import Base


class RevokedAccessToken(Base):
    __tablename__ = 'revoked_access_tokens'
    digest = Column(String(64), primary_key=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    revoked_at = Column(DateTime, nullable=False, default=datetime.utcnow)


def token_digest(token: str, claims=None) -> str:
    claims = claims or decode_access_token_payload(token) or {}
    # Legacy tokens without jti remain individually revocable by full-token hash.
    source = 'session:' + claims['jti'] if isinstance(claims.get('jti'), str) else token
    return hashlib.sha256(source.encode('utf-8')).hexdigest()


def require_active_token(db, token: str) -> None:
    try:
        # Query each time, including within a reused session; do not trust an
        # identity-map/cache hit when another worker may have committed logout.
        revoked = db.execute(select(RevokedAccessToken.digest).where(
            RevokedAccessToken.digest == token_digest(token)
        )).first()
    except SQLAlchemyError as exc:
        report_exception(exc)
        raise HTTPException(503, 'Ověření přihlášení nyní není dostupné. Zkuste to později.') from None
    if revoked:
        raise HTTPException(401, 'Přihlášení bylo ukončeno. Přihlaste se znovu.',
                            headers={'WWW-Authenticate': 'Bearer'})


def revoke_tokens(db, tokens=(), *, tickets=()) -> None:
    """Commit idempotently; never store or log a bearer credential or identity."""
    rows = {}
    for token in tokens:
        if not token:
            continue
        payload = decode_access_token_payload(token)
        if not payload:
            continue  # Invalid/expired credentials are already unusable.
        expiry = datetime.fromtimestamp(float(payload['exp']), timezone.utc).replace(tzinfo=None)
        digest = token_digest(token, payload)
        rows[digest] = {'digest': digest, 'expires_at': expiry, 'revoked_at': datetime.utcnow()}
    for ticket in tickets:
        payload = decode_logout_ticket(ticket)
        if payload:
            expiry = datetime.fromtimestamp(float(payload['exp']), timezone.utc).replace(tzinfo=None)
            rows[payload['sid']] = {'digest': payload['sid'], 'expires_at': expiry, 'revoked_at': datetime.utcnow()}
    if not rows:
        return
    try:
        dialect = db.get_bind().dialect.name
        if dialect == 'postgresql':
            from sqlalchemy.dialects.postgresql import insert
        elif dialect == 'sqlite':
            from sqlalchemy.dialects.sqlite import insert
        else:
            raise HTTPException(503, 'Odhlášení na serveru nyní není dostupné.')
        # Cleanup cannot restore a usable token: its signed exp is already past.
        db.execute(delete(RevokedAccessToken).where(RevokedAccessToken.expires_at <= datetime.utcnow()))
        for row in rows.values():
            db.execute(insert(RevokedAccessToken).values(**row).on_conflict_do_nothing(index_elements=['digest']))
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        report_exception(exc)
        raise HTTPException(503, 'Odhlášení na serveru se nepotvrdilo. Zkuste to znovu.') from None
