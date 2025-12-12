"""
Testy pro autentizaci
"""
import pytest
import requests
from tests.api.conftest import TEST_USER_EMAIL, TEST_USER_PASSWORD


def test_register_success(api_url):
    """Test úspěšné registrace"""
    # Použít unikátní email
    import random
    unique_email = f"test_{random.randint(10000, 99999)}@example.com"
    
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
    # Použít existující email (test@example.com)
    response = requests.post(
        f"{api_url}/user/register",
        json={
            "email": TEST_USER_EMAIL,
            "password": "testpass123",
            "name": "Test User",
            "phone": "+420123456789"
        },
        timeout=5
    )
    
    # Mělo by vrátit 400
    assert response.status_code == 400


def test_login_success(api_url, auth_token):
    """Test úspěšného přihlášení"""
    assert auth_token is not None
    
    response = requests.post(
        f"{api_url}/user/login",
        json={
            "email": TEST_USER_EMAIL,
            "password": TEST_USER_PASSWORD
        },
        timeout=5
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data.get("token_type") == "bearer"


def test_login_wrong_password(api_url):
    """Test přihlášení se špatným heslem"""
    response = requests.post(
        f"{api_url}/user/login",
        json={
            "email": TEST_USER_EMAIL,
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
            "email": "nonexistent@example.com",
            "password": "password123"
        },
        timeout=5
    )
    
    assert response.status_code == 401


def test_get_current_user(api_url, authenticated_headers):
    """Test získání aktuálního uživatele"""
    if not authenticated_headers:
        pytest.skip("No auth token available")
    
    response = requests.get(
        f"{api_url}/user/me",
        headers=authenticated_headers,
        timeout=5
    )
    
    assert response.status_code == 200
    data = response.json()
    assert "email" in data
    assert data["email"] == TEST_USER_EMAIL


def test_get_current_user_unauthorized(api_url):
    """Test získání uživatele bez autentizace"""
    response = requests.get(
        f"{api_url}/user/me",
        timeout=5
    )
    
    assert response.status_code == 401 or response.status_code == 403

