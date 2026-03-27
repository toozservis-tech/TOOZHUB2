"""
SEC-HIGH-004: Services discovery must be tenant-isolated.
"""
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import Customer, Tenant
from src.modules.vehicle_hub.routers_v1 import services as services_router


def _request_with_coordinates() -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/services/discovery",
        "headers": [
            (b"x-geo-lat", b"50.0755"),
            (b"x-geo-lon", b"14.4378"),
        ],
        "query_string": b"",
    }
    return Request(scope)


@pytest.fixture()
def db_context(tmp_path: Path):
    db_path = tmp_path / "services_discovery_sec_high_004.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = TestingSessionLocal()
    try:
        tenant_a = Tenant(name="Tenant A", license_key="tenant-a-key")
        tenant_b = Tenant(name="Tenant B", license_key="tenant-b-key")
        db.add_all([tenant_a, tenant_b])
        db.commit()
        db.refresh(tenant_a)
        db.refresh(tenant_b)

        user_a = Customer(
            tenant_id=tenant_a.id,
            email="sec-high-004-user-a@example.com",
            password_hash="hash-user-a",
            role="user",
            name="User A",
            city="Praha",
        )
        service_a = Customer(
            tenant_id=tenant_a.id,
            email="sec-high-004-service-a@example.com",
            password_hash="hash-service-a",
            role="service",
            name="Service A",
            city="Praha",
        )
        service_b = Customer(
            tenant_id=tenant_b.id,
            email="sec-high-004-service-b@example.com",
            password_hash="hash-service-b",
            role="service",
            name="Service B",
            city="Brno",
        )
        developer_admin = Customer(
            tenant_id=tenant_a.id,
            email="sec-high-004-admin@example.com",
            password_hash="hash-admin",
            role="developer_admin",
            name="Admin",
            city="Praha",
        )
        db.add_all([user_a, service_a, service_b, developer_admin])
        db.commit()
        db.refresh(user_a)
        db.refresh(service_a)
        db.refresh(service_b)
        db.refresh(developer_admin)

        yield {
            "db": db,
            "user_a": user_a,
            "service_a": service_a,
            "service_b": service_b,
            "developer_admin": developer_admin,
        }
    finally:
        db.close()
        engine.dispose()


def test_discovery_for_regular_user_is_tenant_isolated(monkeypatch: pytest.MonkeyPatch, db_context) -> None:
    monkeypatch.setattr(services_router, "_geocode_address", lambda _: None)

    payload = services_router.get_services_discovery(
        request=_request_with_coordinates(),
        current_user=db_context["user_a"],
        db=db_context["db"],
    )

    discovered_emails = {item["email"] for item in payload["services"]}

    assert db_context["service_a"].email in discovered_emails
    assert db_context["service_b"].email not in discovered_emails


def test_discovery_for_developer_admin_keeps_global_visibility(monkeypatch: pytest.MonkeyPatch, db_context) -> None:
    monkeypatch.setattr(services_router, "_geocode_address", lambda _: None)

    payload = services_router.get_services_discovery(
        request=_request_with_coordinates(),
        current_user=db_context["developer_admin"],
        db=db_context["db"],
    )

    discovered_emails = {item["email"] for item in payload["services"]}

    assert db_context["service_a"].email in discovered_emails
    assert db_context["service_b"].email in discovered_emails
