"""One-use email verification for newly created accounts; legacy accounts unchanged."""
import hashlib
import secrets
from datetime import datetime, timedelta
from fastapi import HTTPException
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from .database import Base
from src.core.config import PUBLIC_API_BASE_URL
from src.core.branding import APP_DISPLAY_NAME
from src.modules.email_client.service import EmailService
from src.modules.email_client.templates import render_email_layout


class EmailVerification(Base):
    __tablename__ = 'email_verifications'
    customer_id = Column(Integer, ForeignKey('customers.id', ondelete='CASCADE'), primary_key=True)
    token_digest = Column(String, nullable=True, unique=True)
    expires_at = Column(DateTime, nullable=True)
    verified_at = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, nullable=True)


def prepare_verification(db, customer):
    """Persist a pending gate in the same transaction as a newly created account."""
    row = EmailVerification(customer_id=customer.id)
    db.add(row)
    db.flush()
    return row


def pending_verification(db, customer_id):
    row = db.get(EmailVerification, customer_id)
    return bool(row and not row.verified_at)


def issue_verification(db, customer):
    row = db.query(EmailVerification).filter_by(customer_id=customer.id).with_for_update().first()
    # Do not turn an old, usable account into a pending account on a resend.
    if row is None or row.verified_at:
        return True
    now = datetime.utcnow()
    if row.sent_at and row.sent_at > now - timedelta(seconds=60):
        raise HTTPException(
            429, 'Další e-mail můžete odeslat za minutu.', headers={'Retry-After': '60'}
        )
    token = secrets.token_urlsafe(32)
    digest = hashlib.sha256(token.encode()).hexdigest()
    row.token_digest = digest
    row.expires_at = now + timedelta(hours=24)
    row.sent_at = now
    db.commit()
    url = PUBLIC_API_BASE_URL.rstrip('/') + '/web/verify-email.html#token=' + token
    try:
        sent = EmailService().send_simple_email(
            customer.email,
            f'{APP_DISPLAY_NAME} – ověření e-mailu',
            'Potvrďte svou e-mailovou adresu: ' + url + '\nOdkaz platí 24 hodin.',
            render_email_layout(
                title='Potvrďte svůj e-mail', subtitle='Poslední krok k aktivaci účtu.',
                intro='Dobrý den,',
                paragraphs=['Ověřte, že tato e-mailová adresa patří vám. Odkaz je jednorázový a platí 24 hodin.'],
                cta_label='Ověřit e-mail', cta_url=url,
                footer_note='Pokud jste si účet nezakládali, odkaz neotevírejte.',
            ),
        )
        if not sent:
            raise RuntimeError('Email delivery was not confirmed')
    except Exception:
        # Revoke only this delivery attempt. A later resend or confirmation may
        # have completed while the mail provider was responding.
        db.query(EmailVerification).filter(
            EmailVerification.customer_id == customer.id,
            EmailVerification.token_digest == digest,
            EmailVerification.verified_at.is_(None),
        ).update({EmailVerification.token_digest: None, EmailVerification.expires_at: None}, synchronize_session=False)
        db.commit()
        return False
    return True
