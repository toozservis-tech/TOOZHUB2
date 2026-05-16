"""
Antifraud registrace: ověření e-mailu, telefon E.164, token hash v DB.
Vyžaduje běžící API (TEST_API_URL) a sdílenou DB s backendem.

Každý scénář používá jedno pevné e‑mailové místo; před zápisem se uvolní řádek v DB (release),
aby opakovaný běh pytestů neplnil customers novými adresami.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
import requests
from sqlalchemy import func

from src.modules.vehicle_hub.database import SessionLocal
from src.modules.vehicle_hub.models import Customer
from src.modules.vehicle_hub.registration_security import (
    generate_email_verification_secret,
    hash_email_verification_token,
)
from tests.api.integration_accounts import (
    CI_AF_EXPIRED,
    CI_AF_PHONE_BAD,
    CI_AF_PLAIN_VERIFY_TOKEN,
    CI_AF_RESEND,
    CI_AF_TOKENSECRET,
    CI_AF_VERIFY_FLOW,
    CI_DEFAULT_PASSWORD,
    _verify_customer_email_in_db,
    release_customer_emails_for_re_register,
)


def _api_skip_if_down(api_url: str) -> None:
    try:
        requests.get(f"{api_url}/health", timeout=2)
    except Exception:
        pytest.skip("API server nedostupný")


def test_register_fake_cz_phone_rejected(api_url):
    _api_skip_if_down(api_url)
    email = CI_AF_PHONE_BAD
    release_customer_emails_for_re_register([email])
    r = requests.post(
        f"{api_url}/user/register",
        json={
            "email": email,
            "password": CI_DEFAULT_PASSWORD,
            "name": "Bad Phone",
            "phone": "+420111111111",
        },
        timeout=10,
    )
    assert r.status_code == 422


def test_register_invalid_email_rejected(api_url):
    _api_skip_if_down(api_url)
    r = requests.post(
        f"{api_url}/user/register",
        json={
            "email": "not-an-email",
            "password": CI_DEFAULT_PASSWORD,
            "name": "X",
            "phone": "+420737262711",
        },
        timeout=10,
    )
    assert r.status_code in (400, 422)


def test_register_pending_then_login_blocked_then_verify(api_url):
    _api_skip_if_down(api_url)
    email = CI_AF_VERIFY_FLOW
    release_customer_emails_for_re_register([email])
    reg = requests.post(
        f"{api_url}/user/register",
        json={
            "email": email,
            "password": CI_DEFAULT_PASSWORD,
            "name": "Verify Flow",
            "phone": "+420737262711",
        },
        timeout=15,
    )
    assert reg.status_code == 200, reg.text
    body = reg.json()
    assert body.get("verification_required") is True
    assert not body.get("access_token")

    bad_login = requests.post(
        f"{api_url}/user/login",
        json={"email": email, "password": CI_DEFAULT_PASSWORD},
        timeout=10,
    )
    assert bad_login.status_code == 403

    plain_token = CI_AF_PLAIN_VERIFY_TOKEN
    th = hash_email_verification_token(plain_token)
    db = SessionLocal()
    try:
        cust = db.query(Customer).filter(func.lower(Customer.email) == email.lower()).first()
        assert cust is not None
        assert cust.email_verification_token_hash != plain_token
        cust.email_verification_token_hash = th
        cust.email_verification_expires_at = datetime.utcnow() + timedelta(minutes=30)
        db.commit()
    finally:
        db.close()

    vr = requests.post(f"{api_url}/user/verify-email", json={"token": plain_token}, timeout=10)
    assert vr.status_code == 200, vr.text

    db = SessionLocal()
    try:
        cust = db.query(Customer).filter(func.lower(Customer.email) == email.lower()).first()
        assert cust.email_verified_at is not None
        assert cust.account_status == "active"
        assert cust.email_verification_token_hash is None
    finally:
        db.close()

    ok = requests.post(
        f"{api_url}/user/login",
        json={"email": email, "password": CI_DEFAULT_PASSWORD},
        timeout=10,
    )
    assert ok.status_code == 200, ok.text

    vr2 = requests.post(f"{api_url}/user/verify-email", json={"token": plain_token}, timeout=10)
    assert vr2.status_code == 400


def test_verify_fails_when_expired(api_url):
    _api_skip_if_down(api_url)
    email = CI_AF_EXPIRED
    release_customer_emails_for_re_register([email])
    reg = requests.post(
        f"{api_url}/user/register",
        json={
            "email": email,
            "password": CI_DEFAULT_PASSWORD,
            "name": "Expired",
            "phone": "+420608901234",
        },
        timeout=15,
    )
    assert reg.status_code == 200, reg.text
    plain = generate_email_verification_secret()
    th = hash_email_verification_token(plain)
    db = SessionLocal()
    try:
        cust = db.query(Customer).filter(func.lower(Customer.email) == email.lower()).first()
        cust.email_verification_token_hash = th
        cust.email_verification_expires_at = datetime.utcnow() - timedelta(minutes=5)
        db.commit()
    finally:
        db.close()
    r = requests.post(f"{api_url}/user/verify-email", json={"token": plain}, timeout=10)
    assert r.status_code == 400


def test_resend_never_confirms_account_existence(api_url):
    _api_skip_if_down(api_url)
    msg1 = requests.post(
        f"{api_url}/user/resend-verification-email",
        json={"email": "zzz.nonexistent-mailbox-12345@example.com"},
        timeout=10,
    )
    assert msg1.status_code == 200
    t1 = msg1.json().get("message")
    email = CI_AF_RESEND
    release_customer_emails_for_re_register([email])
    requests.post(
        f"{api_url}/user/register",
        json={
            "email": email,
            "password": CI_DEFAULT_PASSWORD,
            "name": "Resend",
            "phone": "+420608901235",
        },
        timeout=15,
    )
    msg2 = requests.post(
        f"{api_url}/user/resend-verification-email",
        json={"email": email},
        timeout=10,
    )
    assert msg2.status_code == 200
    assert msg2.json().get("message") == t1


def test_no_plaintext_verification_token_in_db(api_url):
    _api_skip_if_down(api_url)
    email = CI_AF_TOKENSECRET
    release_customer_emails_for_re_register([email])
    reg = requests.post(
        f"{api_url}/user/register",
        json={
            "email": email,
            "password": CI_DEFAULT_PASSWORD,
            "name": "Tok",
            "phone": "+420608901236",
        },
        timeout=15,
    )
    assert reg.status_code == 200
    db = SessionLocal()
    try:
        c = db.query(Customer).filter(func.lower(Customer.email) == email.lower()).first()
        assert c.email_verification_token_hash
        assert len(c.email_verification_token_hash) == 64
    finally:
        db.close()
    _verify_customer_email_in_db(email)
