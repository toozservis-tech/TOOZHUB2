"""
Testy pro autentizaci
"""
import base64
import hashlib
import hmac
import io
import struct
import time
import zipfile
import requests
from uuid import uuid4


def _unique_email(prefix: str = "test") -> str:
    return f"{prefix}_{uuid4().hex[:10]}@example.com"


def _register_user(api_url: str, email: str | None = None, password: str = "testpass123"):
    """Vytvoří testovacího uživatele a vrátí normalizovaný email + token."""
    register_email = email or _unique_email("user")
    response = requests.post(
        f"{api_url}/user/register",
        json={
            "email": register_email,
            "password": password,
            "name": "Test User",
            "phone": "+420123456789",
        },
        timeout=5,
    )
    assert response.status_code == 200
    data = response.json()
    return register_email.lower(), password, data["access_token"], data


def _calculate_totp(secret: str, unix_time: int | None = None) -> str:
    normalized = secret.strip().replace(" ", "").upper()
    padding = "=" * ((8 - len(normalized) % 8) % 8)
    key = base64.b32decode(normalized + padding, casefold=True)
    counter = int((unix_time or int(time.time())) // 30)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{binary % 1000000:06d}"


def test_register_success(api_url):
    """Test úspěšné registrace"""
    unique_email = _unique_email("register")
    
    response = requests.post(
        f"{api_url}/user/register",
        json={
            "email": unique_email,
            "password": "testpass123",
            "name": "Test User",
            "phone": "+420123456789"
        },
        timeout=5
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data.get("token_type") == "bearer"
    assert "user" in data


def test_register_duplicate_email(api_url):
    """Test registrace s duplicitním emailem"""
    duplicate_email = _unique_email("duplicate")

    first_response = requests.post(
        f"{api_url}/user/register",
        json={
            "email": duplicate_email,
            "password": "testpass123",
            "name": "Test User",
            "phone": "+420123456789"
        },
        timeout=5
    )
    assert first_response.status_code == 200

    # Druhá registrace stejného emailu (jiná velikost písmen) musí selhat
    response = requests.post(
        f"{api_url}/user/register",
        json={
            "email": duplicate_email.upper(),
            "password": "testpass123",
            "name": "Test User Duplicate",
            "phone": "+420123456789",
        },
        timeout=5,
    )
    
    assert response.status_code == 400


def test_login_success(api_url):
    """Test úspěšného přihlášení"""
    email, password, _, _ = _register_user(api_url)
    
    response = requests.post(
        f"{api_url}/user/login",
        json={
            "email": email,
            "password": password
        },
        timeout=5
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data.get("token_type") == "bearer"


def test_login_wrong_password(api_url):
    """Test přihlášení se špatným heslem"""
    email, _, _, _ = _register_user(api_url)

    response = requests.post(
        f"{api_url}/user/login",
        json={
            "email": email,
            "password": "wrongpassword"
        },
        timeout=5
    )
    
    assert response.status_code == 401


def test_login_nonexistent_user(api_url):
    """Test přihlášení neexistujícího uživatele"""
    response = requests.post(
        f"{api_url}/user/login",
        json={
            "email": _unique_email("nonexistent"),
            "password": "password123"
        },
        timeout=5
    )
    
    assert response.status_code == 401


def test_login_case_insensitive_email(api_url):
    """Přihlášení by mělo ignorovat velikost písmen v emailu"""
    mixed_case_email = f"CaseUser{uuid4().hex[:6]}@Example.com"
    _, password, _, _ = _register_user(api_url, email=mixed_case_email)
    
    response = requests.post(
        f"{api_url}/user/login",
        json={
            "email": mixed_case_email.upper(),
            "password": password
        },
        timeout=5
    )
    
    assert response.status_code == 200


def test_register_stores_normalized_email(api_url):
    """Registrace musí uložit normalizovaný email a blokovat duplicitu"""
    mixed_case_email = f"CaseUser{uuid4().hex[:6]}@Example.com"
    normalized_email = mixed_case_email.lower()
    password = "testpass123"
    
    # Registrace s mixem velkých písmen
    register_response = requests.post(
        f"{api_url}/user/register",
        json={
            "email": mixed_case_email,
            "password": password,
            "name": "Case User"
        },
        timeout=5
    )
    assert register_response.status_code == 200
    register_data = register_response.json()
    assert register_data["user"]["email"] == normalized_email
    
    # Druhá registrace se stejným emailem v lowercase musí selhat
    duplicate_response = requests.post(
        f"{api_url}/user/register",
        json={
            "email": normalized_email,
            "password": password,
            "name": "Case User Duplicate"
        },
        timeout=5
    )
    assert duplicate_response.status_code == 400


def test_get_current_user(api_url):
    """Test získání aktuálního uživatele"""
    email, _, token, _ = _register_user(api_url)
    headers = {"Authorization": f"Bearer {token}"}
    
    response = requests.get(
        f"{api_url}/user/me",
        headers=headers,
        timeout=5
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "email" in data
    assert data["email"] == email


def test_get_current_user_unauthorized(api_url):
    """Test získání uživatele bez autentizace"""
    response = requests.get(
        f"{api_url}/user/me",
        timeout=5
    )
    
    assert response.status_code == 401 or response.status_code == 403


def test_account_export_and_delete_flow(api_url):
    """Uživatel musí umět stáhnout export a následně trvale smazat účet."""
    email, password, token, _ = _register_user(api_url, password="DeleteMe123")
    headers = {"Authorization": f"Bearer {token}"}

    # Přidat minimálně jedno vozidlo, aby export obsahoval i PDF report.
    create_vehicle_response = requests.post(
        f"{api_url}/api/v1/vehicles",
        json={
            "nickname": "Delete Flow Car",
            "plate": f"DEL{uuid4().hex[:4].upper()}",
            "brand": "Skoda",
            "model": "Octavia",
            "year": 2020,
            "stk_valid_until": "2030-12-31",
        },
        headers=headers,
        timeout=10,
    )
    assert create_vehicle_response.status_code == 200

    export_response = requests.get(
        f"{api_url}/user/me/export",
        headers=headers,
        timeout=30,
    )
    assert export_response.status_code == 200
    assert "application/zip" in (export_response.headers.get("content-type", "")).lower()

    zip_buffer = io.BytesIO(export_response.content)
    with zipfile.ZipFile(zip_buffer, "r") as archive:
        names = set(archive.namelist())
        assert "data/kompletni_export.json" in names
        assert "data/ucet_prehled.json" in names
        assert any(name.startswith("vozidla_pdf/") and name.endswith(".pdf") for name in names)

    # Bez potvrzení exportu musí mazání selhat.
    no_export_confirmation_response = requests.delete(
        f"{api_url}/user/me",
        json={
            "current_password": password,
            "confirmation_text": "SMAZAT UCET",
            "export_downloaded": False,
        },
        headers=headers,
        timeout=10,
    )
    assert no_export_confirmation_response.status_code == 400

    # Správné potvrzení + heslo => účet se smaže.
    delete_response = requests.delete(
        f"{api_url}/user/me",
        json={
            "current_password": password,
            "confirmation_text": "SMAZAT UCET",
            "export_downloaded": True,
        },
        headers=headers,
        timeout=20,
    )
    assert delete_response.status_code == 200
    delete_payload = delete_response.json()
    assert delete_payload.get("deleted") is True

    # Po smazání už se nelze přihlásit.
    login_response = requests.post(
        f"{api_url}/user/login",
        json={"email": email, "password": password},
        timeout=10,
    )
    assert login_response.status_code == 401


def test_forgot_password_endpoint_returns_200(api_url):
    """Forgot password endpoint musí vracet 200 i pro neexistující email."""
    response = requests.post(
        f"{api_url}/user/forgot-password",
        json={"email": _unique_email("forgot")},
        timeout=5,
    )
    assert response.status_code == 200
    data = response.json()
    assert "message" in data


def test_request_password_reset_legacy_alias_returns_200(api_url):
    """Legacy alias endpoint musí fungovat kvůli zpětné kompatibilitě klientů."""
    response = requests.post(
        f"{api_url}/user/request-password-reset",
        json={"email": _unique_email("forgot_alias")},
        timeout=5,
    )
    assert response.status_code == 200
    data = response.json()
    assert "message" in data


def test_login_role_mismatch_returns_403(api_url):
    """Přihlášení uživatele v režimu service musí vrátit 403."""
    email, password, _, _ = _register_user(api_url)

    response = requests.post(
        f"{api_url}/user/login",
        json={
            "email": email,
            "password": password,
            "expected_role": "service",
        },
        timeout=5,
    )

    assert response.status_code == 403


def test_login_with_two_factor_flow(api_url):
    """Kompletní 2FA flow: setup -> enable -> login challenge -> verify."""
    email, password, token, _ = _register_user(api_url)
    headers = {"Authorization": f"Bearer {token}"}

    setup_response = requests.post(
        f"{api_url}/user/security/totp/setup",
        headers=headers,
        timeout=5,
    )
    assert setup_response.status_code == 200
    setup_data = setup_response.json()
    secret = setup_data.get("secret")
    assert secret

    enable_code = _calculate_totp(secret)
    enable_response = requests.post(
        f"{api_url}/user/security/totp/enable",
        headers=headers,
        json={"code": enable_code},
        timeout=5,
    )
    assert enable_response.status_code == 200
    assert enable_response.json().get("two_factor_enabled") is True

    login_response = requests.post(
        f"{api_url}/user/login",
        json={"email": email, "password": password},
        timeout=5,
    )
    assert login_response.status_code == 200
    login_data = login_response.json()
    assert login_data.get("two_factor_required") is True
    challenge_token = login_data.get("challenge_token")
    assert challenge_token

    verify_response = requests.post(
        f"{api_url}/user/login/2fa",
        json={
            "challenge_token": challenge_token,
            "code": _calculate_totp(secret),
        },
        timeout=5,
    )
    assert verify_response.status_code == 200
    verify_data = verify_response.json()
    assert verify_data.get("access_token")
    assert verify_data.get("user", {}).get("email") == email


def test_service_registration_request_creates_pending_account(api_url):
    """Servisní registrace vytvoří pending žádost a účet není ihned aktivní."""
    email = _unique_email("service_request")
    password = "testpass123"
    unique_ico = str(10000000 + int(uuid4().hex[:6], 16) % 89999999)

    response = requests.post(
        f"{api_url}/user/register/service-request",
        json={
            "email": email,
            "password": password,
            "ico": unique_ico,
            "service_name": "Demo Servis s.r.o.",
            "responsible_person": "Jan Novak",
            "phone": "+420123456789",
            "street": "Servisni 1",
            "street_number": "12",
            "city": "Praha",
            "zip": "11000",
            "dic": "CZ12345678",
            "registration_purpose": "Chceme spravovat servisni objednavky klientu.",
        },
        timeout=5,
    )
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "pending"
    assert data.get("request_id")

    login_response = requests.post(
        f"{api_url}/user/login",
        json={"email": email, "password": password, "expected_role": "service"},
        timeout=5,
    )
    assert login_response.status_code == 401


def test_service_registration_request_duplicate_pending_blocked(api_url):
    """Opakované podání pending servisní žádosti se stejným emailem musí být blokováno."""
    email = _unique_email("service_request_dup")
    unique_ico = str(10000000 + int(uuid4().hex[:6], 16) % 89999999)
    payload = {
        "email": email,
        "password": "testpass123",
        "ico": unique_ico,
        "service_name": "Servis Duplicate",
        "responsible_person": "Petr Svoboda",
        "phone": "+420777555444",
        "street": "Dilenska 5",
        "street_number": "5",
        "city": "Brno",
        "zip": "60200",
        "dic": None,
        "registration_purpose": "Registrace servisniho uctu pro praci s rezervacemi.",
    }

    first = requests.post(
        f"{api_url}/user/register/service-request",
        json=payload,
        timeout=5,
    )
    assert first.status_code == 200

    second = requests.post(
        f"{api_url}/user/register/service-request",
        json=payload,
        timeout=5,
    )
    assert second.status_code == 400


def test_service_registration_duplicate_ico_blocked(api_url):
    """Jedno IČO nesmí být použito pro více servisních registrací."""
    ico_digits = str(10000000 + int(uuid4().hex[:6], 16) % 89999999)
    payload_base = {
        "password": "testpass123",
        "ico": ico_digits,
        "service_name": "Servis Test",
        "responsible_person": "Jan Test",
        "phone": "+420777123456",
        "street": "Servisni 1",
        "street_number": "12",
        "city": "Praha",
        "zip": "11000",
        "dic": "CZ12345678",
        "registration_purpose": "Test registrace servisniho uctu pro API.",
    }

    first_response = requests.post(
        f"{api_url}/user/register/service-request",
        json={**payload_base, "email": _unique_email("service_ico_a")},
        timeout=5,
    )
    assert first_response.status_code == 200, first_response.text

    second_response = requests.post(
        f"{api_url}/user/register/service-request",
        json={**payload_base, "email": _unique_email("service_ico_b")},
        timeout=5,
    )
    assert second_response.status_code == 400, second_response.text
    detail = second_response.json().get("detail", "")
    assert "IČO" in detail or "ICO" in detail or "Ico" in detail
