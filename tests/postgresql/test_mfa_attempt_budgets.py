"""MFA rate limits must work with the actual production database driver."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from fastapi import HTTPException
import pytest

from src.core import mfa
from src.modules.vehicle_hub.models import Customer, Tenant
from src.server.routers import user_auth, user_security


def account(pg_db):
    with pg_db.sessions() as db:
        tenant = Tenant(name='Synthetic MFA', license_key=uuid4().hex)
        db.add(tenant); db.flush()
        user = Customer(tenant_id=tenant.id, email=uuid4().hex+'@example.com', role='admin')
        db.add(user); db.commit()
        return user.id


def test_first_five_attempts_allowed_sixth_denied_and_next_window_resets(pg_db, monkeypatch):
    customer_id = account(pg_db)
    monkeypatch.setattr(mfa.time, 'time', lambda: 1800000001)
    with pg_db.sessions() as db:
        for _ in range(5):
            mfa.limit_attempt(db, customer_id, 'totp-setup')
        with pytest.raises(HTTPException) as error:
            mfa.limit_attempt(db, customer_id, 'totp-setup')
        assert error.value.status_code == 429
        assert error.value.headers['Retry-After'] == '899'
        db.expire_all()
        assert db.get(mfa.MFAAttemptBudget, (customer_id, 'totp-setup')).attempts == 5
    monkeypatch.setattr(mfa.time, 'time', lambda: 1800000901)
    with pg_db.sessions() as db:
        mfa.limit_attempt(db, customer_id, 'totp-setup')
        assert db.get(mfa.MFAAttemptBudget, (customer_id, 'totp-setup')).attempts == 1


def test_parallel_requests_share_one_durable_budget(pg_db, monkeypatch):
    customer_id = account(pg_db)
    monkeypatch.setattr(mfa.time, 'time', lambda: 1800000001)
    barrier = Barrier(8)
    def attempt(_):
        with pg_db.sessions() as db:
            barrier.wait(timeout=10)
            try:
                mfa.limit_attempt(db, customer_id, 'totp-code')
                return 200
            except HTTPException as error:
                return error.status_code
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(8)))
    assert results.count(200) == 5
    assert results.count(429) == 3
    with pg_db.sessions() as db:
        assert db.get(mfa.MFAAttemptBudget, (customer_id, 'totp-code')).attempts == 5


def test_admin_enrollment_login_and_step_up_over_http_on_postgresql(pg_db, monkeypatch):
    from fastapi import FastAPI, Depends
    from fastapi.testclient import TestClient
    from src.core.auth import get_current_user_email
    from src.core.security import hash_password
    from src.modules.vehicle_hub.database import get_db
    from src.server.security_helpers import calculate_totp

    customer_id = account(pg_db)
    password = 'Synthetic-password-only-123'
    with pg_db.sessions() as db:
        user = db.get(Customer, customer_id)
        user.password_hash = hash_password(password)
        email = user.email
        db.commit()
    now = [int(mfa.time.time())]
    monkeypatch.setattr(mfa.time, 'time', lambda: now[0])
    # Only external logging side effects are substituted; auth, crypto, limits,
    # database writes and token/session validation use their real implementations.
    for module in (user_auth, user_security):
        monkeypatch.setattr(module, 'log_security_event', lambda **kw: None)
    def sessions():
        with pg_db.sessions() as db:
            yield db
    app = FastAPI()
    app.dependency_overrides[get_db] = sessions
    app.include_router(user_auth.router)
    app.include_router(user_security.router)
    @app.get('/test/protected')
    def protected(email=Depends(get_current_user_email)):
        return {'allowed': True}
    with TestClient(app) as client:
        login = client.post('/user/login', json={'email': email, 'password': password})
        assert login.status_code == 200
        old = {'Authorization': 'Bearer '+login.json()['access_token']}
        assert client.get('/test/protected', headers=old).status_code == 403
        setup = client.post('/user/security/totp/setup', headers=old, json={'current_password': password})
        assert setup.status_code == 200
        assert setup.headers['Cache-Control'] == 'no-store'
        secret = setup.json()['secret']
        enabled = client.post('/user/security/totp/enable', headers=old,
            json={'code': calculate_totp(secret, now[0])})
        assert enabled.status_code == 200
        verified = {'Authorization': 'Bearer '+enabled.json()['access_token']}
        assert client.get('/test/protected', headers=old).status_code == 401
        assert client.get('/test/protected', headers=verified).status_code == 200
        challenge = client.post('/user/login', json={'email': email, 'password': password})
        assert challenge.status_code == 200 and challenge.json()['two_factor_required']
        now[0] += 30
        payload = {'challenge_token': challenge.json()['challenge_token'], 'code': calculate_totp(secret, now[0])}
        renewed = client.post('/user/login/2fa', json=payload)
        assert renewed.status_code == 200
        assert client.post('/user/login/2fa', json=payload).status_code == 401
        now[0] += 30
        stepped = client.post('/user/security/admin-verify', headers=verified,
            json={'current_password': password, 'code': calculate_totp(secret, now[0])})
        assert stepped.status_code == 200
        result = client.get('/user/security/admin-status', headers={'Authorization': 'Bearer '+stepped.json()['access_token']})
        assert result.status_code == 200 and result.json()['verified']
