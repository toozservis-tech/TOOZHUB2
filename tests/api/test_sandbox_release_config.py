"""Safety checks for the new, separately deployed App Review service."""
from pathlib import Path
import json
import os
import subprocess
import sys

import bcrypt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

from src.server.sandbox_config import validate_sandbox_config

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def settings(tmp_path):
    password_hash = bcrypt.hashpw(b"Synthetic-Password-42", bcrypt.gensalt(rounds=12)).decode()
    key = ec.generate_private_key(ec.SECP256R1()).private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode()
    return {
        "SV_ISOLATED_APPLE_SANDBOX": "1", "APPLE_IAP_ENVIRONMENT": "Sandbox", "APPLE_IAP_ENABLED": "1",
        "SANDBOX_DATA_ROOT": str(tmp_path), "DATABASE_URL": f"sqlite:///{tmp_path}/sv-sandbox.sqlite3",
        "DATA_DIR_PATH": str(tmp_path / "files"), "JWT_SECRET_KEY": "synthetic-signing-key-2026-this-is-not-a-real-secret",
        "PUBLIC_API_BASE_URL": "https://synthetic-sandbox.example.com",
        "SANDBOX_CUSTOMER_1_PASSWORD_HASH": password_hash, "SANDBOX_CUSTOMER_2_PASSWORD_HASH": password_hash,
        "APPLE_IAP_BUNDLE_ID": "cz.toozservis.spravavozidel.ios", "APPLE_IAP_APP_ID": "6818048361",
        "APPLE_IAP_SUBSCRIPTION_GROUP_ID": "22431514", "APPLE_IAP_KEY_ID": "SYNTHETIC1",
        "APPLE_IAP_ISSUER_ID": "00000000-0000-4000-8000-000000000001", "APPLE_IAP_PRIVATE_KEY": key,
    }


@pytest.mark.parametrize("change", [
    {"SV_ISOLATED_APPLE_SANDBOX": "0"}, {"APPLE_IAP_ENVIRONMENT": "Production"},
    {"APPLE_IAP_ENABLED": "0"}, {"DATABASE_URL": "postgresql://production.invalid/main"},
    {"VEHICLE_DB_URL": "sqlite:///legacy.db"}, {"DATABASE_SCHEMA": "public"},
    {"PUBLIC_API_BASE_URL": "https://app.toozservis.cz"}, {"PUBLIC_API_BASE_URL": "http://sandbox.example.com"},
    {"SMTP_PASSWORD": "inherited"}, {"SUPABASE_KEY": "inherited"}, {"COMGATE_SECRET": "inherited"},
    {"SPRAVA_VOZIDEL_ADMIN_FORCE_PREMIUM": "1"}, {"JWT_SECRET_KEY": "short"},
    {"SANDBOX_CUSTOMER_1_PASSWORD_HASH": "plaintext"}, {"SANDBOX_DATA_ROOT": "relative"},
])
def test_rejects_shared_or_unsafe_configuration(settings, change):
    settings.update(change)
    with pytest.raises(RuntimeError):
        validate_sandbox_config(settings, ROOT)


def test_rejects_dotenv_and_database_symlink(settings, tmp_path):
    root = tmp_path / "checkout"
    root.mkdir()
    (root / ".env").write_text("DATABASE_URL=do-not-load")
    with pytest.raises(RuntimeError):
        validate_sandbox_config(settings, root)
    (root / ".env").unlink()
    (tmp_path / "sv-sandbox.sqlite3").symlink_to(tmp_path / "other.sqlite3")
    with pytest.raises(RuntimeError):
        validate_sandbox_config(settings, root)


def test_real_login_routes_quotas_and_persistent_fixture(settings):
    # A new process isolates application singleton configuration and creates only
    # this test's database. No real Apple key or production connection is used.
    env = {name: os.environ[name] for name in ("PATH", "HOME") if name in os.environ}
    env.update(settings)
    code = '''
import json
from fastapi.testclient import TestClient
from sqlalchemy import text
from src.server.sandbox_review import app, initialize_fixture
from src.modules.vehicle_hub.database import SessionLocal
from src.modules.vehicle_hub.models import Customer, Vehicle, License
from src.core.security import create_access_token
from src.modules.email_client.service import EmailService
assert not EmailService().is_configured()
with TestClient(app) as client:
    assert client.get('/health').json()['environment'] == 'Sandbox'
    assert client.post('/user/register', json={}).status_code == 404
    assert client.post('/user/register/service-request', json={}).status_code == 404
    assert client.post('/user/email-verification/resend', json={}).status_code == 404
    assert client.get('/admin-api/users').status_code == 404
    assert client.get('/api/v1/vehicles').status_code in (401, 403)
    for number in (1, 2):
        login = client.post('/user/login', json={'email':f'sandbox-{number}@example.com', 'password':'Synthetic-Password-42'})
        assert login.status_code == 200, (login.status_code, login.text)
        headers={'Authorization':'Bearer '+login.json()['access_token']}
        for path in ['/user/me','/user/security/settings','/api/v1/vehicles','/api/v1/reminders',
                     '/api/v1/reminders/settings','/api/v1/reservations/my','/api/v1/services/discovery',
                     '/api/v1/license/status','/api/v1/system/capabilities']:
            response = client.get(path, headers=headers)
            assert response.status_code == 200, (path, response.status_code, response.text)
        license = client.get('/api/v1/license/status', headers=headers).json()
        assert license['plan'] == 'free' and license['vehicles_limit'] == 1, license
        catalog = client.get('/api/v1/license/apple/catalog', headers=headers)
        assert catalog.status_code == 200 and catalog.json().get('environment') == 'Sandbox', catalog.text
        assert catalog.json()['enabled'] is True, catalog.text
        assert client.post('/api/v1/license/apple/sync',headers=headers,
                           json={'signed_transaction':'invalid.signed.transaction'}).status_code == 400
    # A valid-looking token from a differently signed server cannot cross over.
    import jwt
    forged=jwt.encode({'sub':'sandbox-1@example.com'},'another-server-secret-with-at-least-32-bytes',algorithm='HS256')
    assert client.get('/user/me',headers={'Authorization':'Bearer '+forged}).status_code == 401
    # Exercise real erasure, then restart. The fixture must not recreate a
    # deleted identity or its vehicle, and the other account must survive.
    erased = client.request('DELETE', '/user/me', headers=headers,
        json={'current_password':'Synthetic-Password-42','confirmation_text':'SMAZAT UCET'})
    assert erased.status_code == 200, erased.text
    assert erased.json()['deleted'] is True
    assert client.get('/api/v1/vehicles', headers=headers).status_code == 401
    with SessionLocal() as db:
        before=db.query(Vehicle).count()
        assert before == 1
        assert db.get(Customer,2) is None
    initialize_fixture()
    with SessionLocal() as db:
        assert db.query(Vehicle).count() == before
        assert db.get(Customer,2) is None
        assert db.query(License).filter(License.plan != 'free').count() == 0
print('SANDBOX_SURFACE_OK')
'''
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, env=env,
                            text=True, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "SANDBOX_SURFACE_OK" in result.stdout


def role_settings(settings):
    from src.server.sandbox_config import ROLE_ACCOUNT_SPECS
    settings['SANDBOX_ROLE_ACCOUNTS_ENABLED'] = '1'
    for number, _, _, _, key in ROLE_ACCOUNT_SPECS:
        settings[key] = bcrypt.hashpw(f'Synthetic-Role-{number}-42'.encode(), bcrypt.gensalt(rounds=12)).decode()
    return settings


def test_role_credentials_are_explicit_and_distinct(settings):
    settings['SANDBOX_ROLE_ACCOUNTS_ENABLED'] = '1'
    with pytest.raises(RuntimeError):
        validate_sandbox_config(settings, ROOT)
    role_settings(settings)
    assert validate_sandbox_config(settings, ROOT)
    settings['SANDBOX_ADMIN_PASSWORD_HASH'] = settings['SANDBOX_CUSTOMER_1_PASSWORD_HASH']
    with pytest.raises(RuntimeError):
        validate_sandbox_config(settings, ROOT)


def test_additive_role_migration_real_auth_mfa_and_service_isolation(settings):
    env = {name: os.environ[name] for name in ('PATH', 'HOME') if name in os.environ}
    env.update(settings)
    # Start the previous two-account configuration and retain a changed license.
    first = subprocess.run([sys.executable, '-c', '''
from src.server.sandbox_review import initialize_fixture
from src.modules.vehicle_hub.database import SessionLocal
from src.modules.vehicle_hub.models import License
with SessionLocal() as db:
    license = db.query(License).filter_by(tenant_id=2).one()
    license.plan='premium'; license.vehicles_limit=0
    db.commit()
'''], cwd=ROOT, env=env, text=True, capture_output=True, timeout=60)
    assert first.returncode == 0, first.stdout + first.stderr
    env.update(role_settings(settings))
    code = '''
from fastapi.testclient import TestClient
from src.server.sandbox_review import app, initialize_fixture
from src.modules.vehicle_hub.database import SessionLocal
from src.modules.vehicle_hub.models import Customer, License, Vehicle, VehicleServiceLink
from src.modules.vehicle_hub.service_access import create_or_update_vehicle_service_link
from src.server.security_helpers import calculate_totp
import time
with SessionLocal() as db:
    assert db.query(Customer).count()==5
    assert db.query(License).filter_by(tenant_id=2).one().plan=='premium'
    passwords={c.id:c.password_hash for c in db.query(Customer).all()}
    vehicles=db.query(Vehicle).count()
    for service, owner in [(4,1),(5,2)]:
        vehicle=db.query(Vehicle).filter_by(tenant_id=owner).one()
        create_or_update_vehicle_service_link(db, tenant_id=owner, service_customer_id=service,
            owner_customer_id=owner, vehicle_id=vehicle.id, approved_by_customer_id=owner,
            source_type='owner_grant')
    db.commit()
initialize_fixture()
with SessionLocal() as db:
    assert {c.id:c.password_hash for c in db.query(Customer).all()}==passwords
    assert db.query(Vehicle).count()==vehicles
with TestClient(app) as client:
    tokens={}
    identities=[(1,'sandbox-1@example.com','user','Synthetic-Password-42'),
                (2,'sandbox-2@example.com','user','Synthetic-Password-42'),
                (3,'sandbox-admin@example.com','admin','Synthetic-Role-3-42'),
                (4,'sandbox-service-1@example.com','service','Synthetic-Role-4-42'),
                (5,'sandbox-service-2@example.com','service','Synthetic-Role-5-42')]
    for number,email,role,password in identities:
        r=client.post('/user/login',json={'email':email,'password':password})
        assert r.status_code==200,(number,r.status_code,r.text)
        tokens[number]={'Authorization':'Bearer '+r.json()['access_token']}
        me=client.get('/user/me',headers=tokens[number])
        assert me.status_code==200,me.text
        assert me.json()['role']==role,me.text
    assert client.get('/admin-api/users',headers=tokens[3]).status_code==403
    for number in (1,2,4,5):
        assert client.get('/admin-api/users',headers=tokens[number]).status_code==403
    for service,owner in [(4,1),(5,2)]:
        r=client.get('/api/v1/services/workspace/approved-vehicles',headers=tokens[service])
        assert r.status_code==200,r.text
        assert [v['customer_id'] for v in r.json()['items']]==[owner],r.text
        assert client.get('/api/v1/vehicles/'+str(3-owner),headers=tokens[service]).status_code in (403,404)
    for number in (1,2):
        assert client.get('/api/v1/services/workspace/approved-vehicles',headers=tokens[number]).status_code==403
    discovery=client.get('/api/v1/services/discovery',headers=tokens[1])
    assert discovery.status_code==200,discovery.text
    assert 'Testovací servis 1' in discovery.text and 'Testovací servis 2' in discovery.text
    assert 'sandbox-admin@' not in discovery.text
    setup=client.post('/user/security/totp/setup',headers=tokens[3],json={'current_password':'Synthetic-Role-3-42'})
    assert setup.status_code==200,setup.text
    enable=client.post('/user/security/totp/enable',headers=tokens[3],json={'code':calculate_totp(setup.json()['secret'], int(time.time()))})
    assert enable.status_code==200,enable.text
    admin={'Authorization':'Bearer '+enable.json()['access_token']}
    users=client.get('/admin-api/users',headers=admin)
    assert users.status_code==200,users.text
    assert len(users.json())==5
    for path in ['/admin-api/overview','/admin-api/vehicles','/admin-api/services','/admin-api/records']:
        response=client.get(path,headers=admin)
        assert response.status_code==200,(path,response.status_code,response.text)
    assert client.post('/admin-api/users',headers=admin,json={'email':'not-synthetic@real.example.org'}).status_code==422
    # A newly provisioned test identity is valid on restart; real addresses are not.
    with SessionLocal() as db:
        db.get(Customer,4).email='changed-service@example.invalid'
        db.commit()
    initialize_fixture()
    # Erased role fixtures must not be recreated by a restart.
    erased=client.request('DELETE','/user/me',headers=tokens[5],json={'current_password':'Synthetic-Role-5-42','confirmation_text':'SMAZAT UCET'})
    assert erased.status_code==200,erased.text
    initialize_fixture()
    with SessionLocal() as db:
        assert db.get(Customer,5) is None
        assert db.query(License).filter_by(tenant_id=2).one().plan=='premium'
print('SANDBOX_ROLES_OK')
'''
    result = subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=env,
                            text=True, capture_output=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'SANDBOX_ROLES_OK' in result.stdout
