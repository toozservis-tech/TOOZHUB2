import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from src.modules.vehicle_hub.database import Base, get_db

pytestmark = pytest.mark.skip(reason="FakturyWeb workspace router není v produkční aplikaci montovaný; integrační testy jsou zastaralé.")

from src.server.main import app
from src.modules.vehicle_hub.models import *
from src.modules.service_workspace.fakturyweb_client import FakturyWebError
from src.modules.vehicle_hub.routers_v1.auth import get_current_user

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

@pytest.fixture
def mock_fakturyweb_client():
    with patch("src.modules.service_workspace.fakturyweb_router.FakturyWebTestClient") as mock:
        yield mock

def test_user_role_no_access(db_session):
    tenant = Tenant(name="Test Tenant", license_key="test1", workspace_route_kind="c", workspace_slug="test1")
    db_session.add(tenant)
    db_session.commit()
    
    user = Customer(tenant_id=tenant.id, email="user1@test.com", role="user")
    db_session.add(user)
    db_session.commit()
    
    with patch("src.modules.vehicle_hub.routers_v1.auth.get_current_user", return_value=user):
        app.dependency_overrides[get_current_user] = lambda: user
        response = client.get("/api/v1/services/workspace/fakturyweb/settings")
        app.dependency_overrides.pop(get_current_user, None)
        assert response.status_code == 403
        assert "pouze servisní účet" in response.json()["detail"]

def test_service_role_access_and_settings_masking(db_session):
    tenant = Tenant(name="Test Tenant", license_key="test2", workspace_route_kind="c", workspace_slug="test2")
    db_session.add(tenant)
    db_session.commit()
    
    service = Customer(tenant_id=tenant.id, email="service2@test.com", role="service")
    db_session.add(service)
    db_session.commit()
    
    with patch("src.modules.vehicle_hub.routers_v1.auth.get_current_user", return_value=service):
        app.dependency_overrides[get_current_user] = lambda: service
        payload = {
            "fakturyweb_email": "test@fakturyweb.cz",
            "fakturyweb_api_key": "mysecretapikey123456",
            "supplier_mode": "manual",
            "default_due_days": 14,
            "default_payment": "prevod",
            "default_currency": "Kč",
            "default_style": "styl_7",
            "default_qr": 1
        }
        response = client.post("/api/v1/services/workspace/fakturyweb/settings", json=payload)
        assert response.status_code == 200, response.json()
        
        settings = db_session.query(ServiceFakturywebSettings).filter_by(tenant_id=tenant.id).first()
        assert settings.email == "test@fakturyweb.cz"
        assert settings.api_key_mask == "myse****3456"
        assert "mysecretapikey123456" not in settings.encrypted_api_key
        
        response = client.get("/api/v1/services/workspace/fakturyweb/settings")
        assert response.status_code == 200, response.json()
        data = response.json()
        assert "api_key" not in data
        assert "encrypted_api_key" not in data
        assert data["email"] == "test@fakturyweb.cz"
        
        audit = db_session.query(ServiceFakturywebAuditLog).filter_by(action="settings_saved").first()
        assert "mysecretapikey123456" not in audit.request_hash
        app.dependency_overrides.pop(get_current_user, None)

def test_test_connection_calls_init(db_session, mock_fakturyweb_client):
    tenant = Tenant(name="Test Tenant", license_key="test3", workspace_route_kind="c", workspace_slug="test3")
    db_session.add(tenant)
    db_session.commit()
    
    service = Customer(tenant_id=tenant.id, email="service3@test.com", role="service")
    db_session.add(service)
    db_session.commit()
    
    settings = ServiceFakturywebSettings(
        tenant_id=tenant.id,
        service_workspace_id=service.id,
        email="test@fakturyweb.cz",
        encrypted_api_key="bXlzZWNyZXRhcGlrZXkxMjM0NTY=",
        supplier_mode="manual",
        default_due_days=7, default_payment="prevod", default_currency="Kč", default_style="styl_7", default_qr=1, test_mode_default=True
    )
    db_session.add(settings)
    db_session.commit()
    
    mock_instance = MagicMock()
    mock_fakturyweb_client.return_value.__enter__.return_value = mock_instance
    
    with patch("src.modules.vehicle_hub.routers_v1.auth.get_current_user", return_value=service):
        app.dependency_overrides[get_current_user] = lambda: service
        response = client.post("/api/v1/services/workspace/fakturyweb/test-connection")
        app.dependency_overrides.pop(get_current_user, None)
        assert response.status_code == 200, response.json()
        
        mock_instance.call_fakturyweb.assert_called_once_with(
            "api/init", {"key": "mysecretapikey123456", "email": "test@fakturyweb.cz"}
        )

def test_create_invoice_forces_apitest_and_saves_local(db_session, mock_fakturyweb_client):
    tenant = Tenant(name="Test Tenant", license_key="test4", workspace_route_kind="c", workspace_slug="test4")
    db_session.add(tenant)
    db_session.commit()
    
    service = Customer(tenant_id=tenant.id, email="service4@test.com", role="service")
    db_session.add(service)
    db_session.commit()
    
    settings = ServiceFakturywebSettings(
        tenant_id=tenant.id,
        service_workspace_id=service.id,
        email="test@fakturyweb.cz",
        encrypted_api_key="bXlzZWNyZXRhcGlrZXkxMjM0NTY=",
        supplier_mode="manual",
        default_due_days=7, default_payment="prevod", default_currency="Kč", default_style="styl_7", default_qr=1, test_mode_default=True
    )
    db_session.add(settings)
    db_session.commit()
    
    mock_instance = MagicMock()
    mock_instance.call_fakturyweb.return_value = {"status": 1, "code": "FW123", "number": "20260001"}
    mock_fakturyweb_client.return_value.__enter__.return_value = mock_instance
    
    payload = {
        "customer": {"name": "Test Customer", "email": "cust@test.com"},
        "invoice": {"issue_date": "2026-05-06", "delivery_date": "2026-05-06", "due_date": "2026-05-13", "payment": "prevod", "currency": "Kč", "qr": 1, "style": "styl_7"},
        "items": [{"text": "Oprava", "quantity": 1, "unit": "ks", "price": 1000}]
    }
    
    with patch("src.modules.vehicle_hub.routers_v1.auth.get_current_user", return_value=service):
        app.dependency_overrides[get_current_user] = lambda: service
        response = client.post("/api/v1/services/workspace/fakturyweb/invoices/test-create", json=payload)
        app.dependency_overrides.pop(get_current_user, None)
        assert response.status_code == 200, response.json()
        
        call_args = mock_instance.call_fakturyweb.call_args[0]
        assert call_args[0] == "api/nf"
        assert call_args[1]["apitest"] == 1
        
        inv = db_session.query(ServiceFakturywebInvoice).filter_by(tenant_id=tenant.id).first()
        assert inv is not None
        assert inv.fakturyweb_code == "FW123"
        assert inv.fakturyweb_number == "20260001"
        assert inv.test_mode is True
        assert inv.amount_estimated == 1000

def test_tenant_isolation(db_session):
    tenant1 = Tenant(name="Tenant 1", license_key="t1", workspace_route_kind="c", workspace_slug="t1")
    tenant2 = Tenant(name="Tenant 2", license_key="t2", workspace_route_kind="c", workspace_slug="t2")
    db_session.add_all([tenant1, tenant2])
    db_session.commit()
    
    service1 = Customer(tenant_id=tenant1.id, email="s1@test.com", role="service")
    service2 = Customer(tenant_id=tenant2.id, email="s2@test.com", role="service")
    db_session.add_all([service1, service2])
    db_session.commit()
    
    inv1 = ServiceFakturywebInvoice(tenant_id=tenant1.id, service_workspace_id=service1.id, fakturyweb_code="FW1", local_status="created", test_mode=True)
    inv2 = ServiceFakturywebInvoice(tenant_id=tenant2.id, service_workspace_id=service2.id, fakturyweb_code="FW2", local_status="created", test_mode=True)
    db_session.add_all([inv1, inv2])
    db_session.commit()
    
    with patch("src.modules.vehicle_hub.routers_v1.auth.get_current_user", return_value=service1):
        app.dependency_overrides[get_current_user] = lambda: service1
        response = client.get("/api/v1/services/workspace/fakturyweb/invoices")
        app.dependency_overrides.pop(get_current_user, None)
        assert response.status_code == 200, response.json()
        data = response.json()
        assert len(data) == 1
        assert data[0]["fakturyweb_code"] == "FW1"
