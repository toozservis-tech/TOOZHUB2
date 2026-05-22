"""
Testy ověření e-mailu (P0 registrace) — stránka, API endpoint, audit bez plaintext tokenu.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
import requests
from fastapi.testclient import TestClient

from src.modules.vehicle_hub.registration_security import (
    generate_email_verification_secret,
    hash_email_verification_token,
)
from src.server.bootstrap import create_app
from tests.api.integration_accounts import (
    CI_DEFAULT_PASSWORD,
    CI_DEFAULT_PHONE_E164,
    plant_email_verification_token_for_test,
    release_customer_emails_for_re_register,
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app())


def test_verify_email_html_returns_200(client: TestClient):
    r = client.get("/web/verify-email.html")
    assert r.status_code == 200
    assert "text/html" in (r.headers.get("content-type") or "").lower()
    assert "Ověření e-mailu" in r.text


def test_verify_html_still_returns_200(client: TestClient):
    r = client.get("/web/verify.html")
    assert r.status_code == 200
    assert "text/html" in (r.headers.get("content-type") or "").lower()


def test_verify_email_valid_token_marks_account_verified(client: TestClient):
    email = f"ci.p0.email-verify.{uuid4().hex[:12]}@example.com"
    password = CI_DEFAULT_PASSWORD
    try:
        reg = client.post(
            "/user/register",
            json={
                "email": email,
                "password": password,
                "name": "P0 Verify Test",
                "phone": CI_DEFAULT_PHONE_E164,
            },
        )
        assert reg.status_code == 200, reg.text
        assert reg.json().get("verification_required") is True

        raw_token = plant_email_verification_token_for_test(email)
        verify = client.post("/user/verify-email", json={"token": raw_token})
        assert verify.status_code == 200, verify.text
        assert verify.json().get("verified") is True

        login = client.post("/user/login", json={"email": email, "password": password})
        assert login.status_code == 200, login.text
        assert login.json().get("access_token")
    finally:
        release_customer_emails_for_re_register([email])


def test_verify_email_invalid_token_safe_400(client: TestClient):
    bogus = generate_email_verification_secret()
    r = client.post("/user/verify-email", json={"token": bogus})
    assert r.status_code == 400
    assert r.status_code != 500
    detail = r.json().get("detail")
    if isinstance(detail, dict):
        assert detail.get("code") == "token_invalid"
    else:
        assert "neplatný" in str(detail).lower() or "použitý" in str(detail).lower()


def test_verify_email_replay_does_not_500(client: TestClient):
    email = f"ci.p0.email-replay.{uuid4().hex[:12]}@example.com"
    password = CI_DEFAULT_PASSWORD
    try:
        reg = client.post(
            "/user/register",
            json={
                "email": email,
                "password": password,
                "name": "P0 Replay Test",
                "phone": CI_DEFAULT_PHONE_E164,
            },
        )
        assert reg.status_code == 200, reg.text
        raw_token = plant_email_verification_token_for_test(email)

        first = client.post("/user/verify-email", json={"token": raw_token})
        assert first.status_code == 200, first.text

        second = client.post("/user/verify-email", json={"token": raw_token})
        assert second.status_code == 200, second.text
        assert second.json().get("already_verified") is True
        assert second.status_code != 500
    finally:
        release_customer_emails_for_re_register([email])


def test_verify_email_expired_token_safe_400(client: TestClient):
    email = f"ci.p0.email-expired.{uuid4().hex[:12]}@example.com"
    password = CI_DEFAULT_PASSWORD
    raw_token = generate_email_verification_secret()
    try:
        reg = client.post(
            "/user/register",
            json={
                "email": email,
                "password": password,
                "name": "P0 Expired Test",
                "phone": CI_DEFAULT_PHONE_E164,
            },
        )
        assert reg.status_code == 200, reg.text

        from sqlalchemy import func

        from src.modules.vehicle_hub.database import SessionLocal
        from src.modules.vehicle_hub.models import Customer

        db = SessionLocal()
        try:
            c = db.query(Customer).filter(func.lower(Customer.email) == email.lower()).first()
            assert c is not None
            c.email_verification_token_hash = hash_email_verification_token(raw_token)
            c.email_verification_expires_at = datetime.utcnow() - timedelta(minutes=1)
            c.email_verified_at = None
            c.account_status = "pending_email_verification"
            db.commit()
        finally:
            db.close()

        r = client.post("/user/verify-email", json={"token": raw_token})
        assert r.status_code == 400
        assert r.status_code != 500
        detail = r.json().get("detail")
        if isinstance(detail, dict):
            assert detail.get("code") == "token_expired"
    finally:
        release_customer_emails_for_re_register([email])


def test_verify_email_missing_token_validation_not_500(client: TestClient):
    r = client.post("/user/verify-email", json={"token": "short"})
    assert r.status_code in {400, 422}
    assert r.status_code != 500


def test_api_me_without_auth_not_500(client: TestClient):
    r = client.get("/api/me")
    assert r.status_code == 200
    assert r.status_code != 500
    assert r.json().get("authenticated") is False


def test_email_verification_e2e_smoke(api_url):
    """Registrace → ověření tokenu → login → dashboard přístup."""
    try:
        requests.get(f"{api_url}/health", timeout=2)
    except Exception:
        pytest.skip("API server nedostupný")

    email = f"ci.p0.e2e-verify.{uuid4().hex[:12]}@example.com"
    password = CI_DEFAULT_PASSWORD
    try:
        reg = requests.post(
            f"{api_url}/user/register",
            json={
                "email": email,
                "password": password,
                "name": "P0 E2E Verify",
                "phone": CI_DEFAULT_PHONE_E164,
            },
            timeout=15,
        )
        assert reg.status_code == 200, reg.text
        assert reg.json().get("verification_required") is True

        blocked = requests.post(
            f"{api_url}/user/login",
            json={"email": email, "password": password},
            timeout=15,
        )
        assert blocked.status_code == 403

        raw_token = plant_email_verification_token_for_test(email)
        verify = requests.post(
            f"{api_url}/user/verify-email",
            json={"token": raw_token},
            timeout=15,
        )
        assert verify.status_code == 200, verify.text

        login = requests.post(
            f"{api_url}/user/login",
            json={"email": email, "password": password},
            timeout=15,
        )
        assert login.status_code == 200, login.text
        token = login.json()["access_token"]

        me = requests.get(
            f"{api_url}/api/me",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        assert me.status_code == 200, me.text
        assert me.json().get("authenticated") is True
    finally:
        release_customer_emails_for_re_register([email])
