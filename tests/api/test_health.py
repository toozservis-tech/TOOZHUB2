"""
Smoke testy pro health a základní endpointy
"""
import pytest
import requests


def test_health_endpoint(api_url):
    """Test /health endpoint"""
    response = requests.get(f"{api_url}/health", timeout=5)
    assert response.status_code == 200
    data = response.json()
    assert data.get("status") == "ok"
    assert "version" in data


def test_root_endpoint(api_url):
    """Test root endpoint"""
    response = requests.get(f"{api_url}/", timeout=5)
    assert response.status_code == 200
    data = response.json()
    assert "message" in data
    assert "TooZ Hub" in data.get("message", "")


def test_version_endpoint(api_url):
    """Test /version endpoint"""
    response = requests.get(f"{api_url}/version", timeout=5)
    assert response.status_code == 200
    data = response.json()
    assert "version" in data or "project" in data

