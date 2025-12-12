"""
Pytest konfigurace pro API testy
"""
import os
import pytest
import requests
from pathlib import Path
import sys

# Přidat root projektu do path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Testovací konfigurace
TEST_API_URL = os.getenv("TEST_API_URL", "http://127.0.0.1:8000")
TEST_DB_URL = os.getenv("TEST_DATABASE_URL", "sqlite:///./test_vehicles.db")
TEST_ENV = "test"

# Testovací uživatel
TEST_USER_EMAIL = "test@example.com"
TEST_USER_PASSWORD = "testpass123"


@pytest.fixture(scope="session")
def api_url():
    """Base URL pro API"""
    return TEST_API_URL


@pytest.fixture(scope="session")
def test_db_url():
    """Testovací databáze URL"""
    return TEST_DB_URL


@pytest.fixture(scope="function")
def auth_token(api_url):
    """
    Získat auth token pro testy.
    Vytvoří testovacího uživatele pokud neexistuje.
    """
    # Zkusit přihlásit existujícího uživatele
    try:
        response = requests.post(
            f"{api_url}/user/login",
            json={
                "email": TEST_USER_EMAIL,
                "password": TEST_USER_PASSWORD
            },
            timeout=5
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("access_token")
    except Exception:
        pass
    
    # Pokud přihlášení selhalo, zkusit registraci
    try:
        response = requests.post(
            f"{api_url}/user/register",
            json={
                "email": TEST_USER_EMAIL,
                "password": TEST_USER_PASSWORD,
                "name": "Test User",
                "phone": "+420123456789"
            },
            timeout=5
        )
        if response.status_code == 200:
            data = response.json()
            return data.get("access_token")
    except Exception:
        pass
    
    return None


@pytest.fixture(scope="function")
def authenticated_headers(auth_token):
    """Headers s autentizací"""
    if auth_token:
        return {"Authorization": f"Bearer {auth_token}"}
    return {}


@pytest.fixture(scope="function")
def cleanup_test_data(api_url, authenticated_headers):
    """
    Cleanup fixture - smaže testovací data po testu
    """
    yield
    
    # Cleanup: smazat testovací vozidla
    try:
        response = requests.get(
            f"{api_url}/api/v1/vehicles",
            headers=authenticated_headers,
            timeout=5
        )
        if response.status_code == 200:
            vehicles = response.json()
            for vehicle in vehicles:
                if "test" in vehicle.get("nickname", "").lower():
                    requests.delete(
                        f"{api_url}/api/v1/vehicles/{vehicle['id']}",
                        headers=authenticated_headers,
                        timeout=5
                    )
    except Exception:
        pass

