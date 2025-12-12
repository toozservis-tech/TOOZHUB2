"""
Testy pro vehicles API
"""
import pytest
import requests


def test_create_vehicle(api_url, authenticated_headers, cleanup_test_data):
    """Test vytvoření vozidla"""
    if not authenticated_headers:
        pytest.skip("No auth token available")
    
    vehicle_data = {
        "nickname": "Test Vehicle",
        "plate": "TEST123",
        "brand": "Test Brand",
        "model": "Test Model",
        "year": 2020
    }
    
    response = requests.post(
        f"{api_url}/api/v1/vehicles",
        json=vehicle_data,
        headers=authenticated_headers,
        timeout=5
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["nickname"] == vehicle_data["nickname"]
    assert data["plate"] == vehicle_data["plate"]
    assert "id" in data
    
    return data["id"]


def test_get_vehicles(api_url, authenticated_headers):
    """Test získání seznamu vozidel"""
    if not authenticated_headers:
        pytest.skip("No auth token available")
    
    response = requests.get(
        f"{api_url}/api/v1/vehicles",
        headers=authenticated_headers,
        timeout=5
    )
    
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_get_vehicle_detail(api_url, authenticated_headers, cleanup_test_data):
    """Test získání detailu vozidla"""
    if not authenticated_headers:
        pytest.skip("No auth token available")
    
    # Vytvořit vozidlo
    vehicle_data = {
        "nickname": "Test Vehicle Detail",
        "plate": "TEST456",
        "brand": "Test Brand",
        "model": "Test Model",
        "year": 2020
    }
    
    create_response = requests.post(
        f"{api_url}/api/v1/vehicles",
        json=vehicle_data,
        headers=authenticated_headers,
        timeout=5
    )
    assert create_response.status_code == 200
    vehicle_id = create_response.json()["id"]
    
    # Získat detail
    response = requests.get(
        f"{api_url}/api/v1/vehicles/{vehicle_id}",
        headers=authenticated_headers,
        timeout=5
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == vehicle_id
    assert data["nickname"] == vehicle_data["nickname"]


def test_update_vehicle(api_url, authenticated_headers, cleanup_test_data):
    """Test aktualizace vozidla"""
    if not authenticated_headers:
        pytest.skip("No auth token available")
    
    # Vytvořit vozidlo
    vehicle_data = {
        "nickname": "Test Vehicle Update",
        "plate": "TEST789",
        "brand": "Test Brand",
        "model": "Test Model",
        "year": 2020
    }
    
    create_response = requests.post(
        f"{api_url}/api/v1/vehicles",
        json=vehicle_data,
        headers=authenticated_headers,
        timeout=5
    )
    assert create_response.status_code == 200
    vehicle_id = create_response.json()["id"]
    
    # Aktualizovat
    update_data = {
        "nickname": "Updated Vehicle",
        "year": 2021
    }
    
    response = requests.put(
        f"{api_url}/api/v1/vehicles/{vehicle_id}",
        json=update_data,
        headers=authenticated_headers,
        timeout=5
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["nickname"] == update_data["nickname"]
    assert data["year"] == update_data["year"]


def test_delete_vehicle(api_url, authenticated_headers):
    """Test smazání vozidla"""
    if not authenticated_headers:
        pytest.skip("No auth token available")
    
    # Vytvořit vozidlo
    vehicle_data = {
        "nickname": "Test Vehicle Delete",
        "plate": "TEST999",
        "brand": "Test Brand",
        "model": "Test Model",
        "year": 2020
    }
    
    create_response = requests.post(
        f"{api_url}/api/v1/vehicles",
        json=vehicle_data,
        headers=authenticated_headers,
        timeout=5
    )
    assert create_response.status_code == 200
    vehicle_id = create_response.json()["id"]
    
    # Smazat
    response = requests.delete(
        f"{api_url}/api/v1/vehicles/{vehicle_id}",
        headers=authenticated_headers,
        timeout=5
    )
    
    assert response.status_code == 200 or response.status_code == 204
    
    # Ověřit, že bylo smazáno
    get_response = requests.get(
        f"{api_url}/api/v1/vehicles/{vehicle_id}",
        headers=authenticated_headers,
        timeout=5
    )
    assert get_response.status_code == 404

