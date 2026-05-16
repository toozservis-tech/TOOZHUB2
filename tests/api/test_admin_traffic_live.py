"""Admin traffic live snapshot — RBAC a parsování logu."""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.server.admin_traffic_live as live_module
from src.core.auth import get_current_user_email
from src.modules.vehicle_hub.database import Base, get_db as vehicle_hub_get_db
from src.modules.vehicle_hub.models import Customer, SecurityAccessLog, Tenant
from src.server.admin_traffic_live import router as traffic_live_router


@pytest.fixture()
def live_client(tmp_path, monkeypatch):
    db_path = tmp_path / "live.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    tenant = Tenant(name="L", license_key="lic-live", workspace_slug="lv", workspace_route_kind="user")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    admin = Customer(
        tenant_id=tenant.id,
        email="live.admin@example.com",
        password_hash="x",
        name="Admin",
        role="admin",
    )
    user = Customer(
        tenant_id=tenant.id,
        email="live.user@example.com",
        password_hash="x",
        name="U",
        role="user",
    )
    db.add_all([admin, user])
    db.commit()
    db.refresh(admin)

    db.add(
        SecurityAccessLog(
            tenant_id=tenant.id,
            customer_id=admin.id,
            user_email=str(admin.email).lower(),
            event_type="api_activity",
            endpoint="/api/v1/me",
            ip_address="203.0.113.10",
            country="Czechia",
            city="Praha",
            region="Praha",
            source="ipwho.is",
        )
    )
    db.commit()

    log_file = tmp_path / "access.log"
    log_file.write_text(
        '1.2.3.4 - - [15/May/2026:12:00:00 +0000] "GET /web_admin/ HTTP/1.1" 200 99 "-" "Mozilla/5.0 Chrome/120"\n'
        "not a combined line\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(live_module, "GEOIP_CITY_DATABASE_PATH", None)

    app = FastAPI()
    app.include_router(traffic_live_router, prefix="/admin-api")

    def override_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[vehicle_hub_get_db] = override_db

    def client_for(email: str):
        app.dependency_overrides[get_current_user_email] = lambda e=email: e  # noqa: B008
        return TestClient(app)

    try:
        yield SimpleNamespace(
            log_file=log_file,
            as_admin=lambda: client_for(admin.email),
            as_user=lambda: client_for(user.email),
            app=app,
        )
    finally:
        app.dependency_overrides.clear()
        db.close()
        engine.dispose()


def test_app_visits_user_forbidden(live_client):
    r = live_client.as_user().get("/admin-api/traffic/app-visits")
    assert r.status_code == 403


def test_live_user_forbidden(live_client, monkeypatch):
    monkeypatch.setattr(live_module, "_resolve_access_log_path", lambda: live_client.log_file.resolve())
    r = live_client.as_user().get("/admin-api/traffic/live/snapshot")
    assert r.status_code == 403


def test_app_visits_admin_lists_security_log(live_client):
    r = live_client.as_admin().get("/admin-api/traffic/app-visits?limit=10")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert len(data["items"]) >= 1
    row = data["items"][0]
    assert row["event_type"] == "api_activity"
    assert "admin" in (row.get("who_email") or "")
    assert row.get("endpoint") == "/api/v1/me"


def test_live_admin_snapshot(live_client, monkeypatch):
    def _resolve_ok():
        return live_client.log_file.resolve()

    monkeypatch.setattr(live_module, "_resolve_access_log_path", _resolve_ok)
    r = live_client.as_admin().get("/admin-api/traffic/live/snapshot?limit=10")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["source_log"] == str(live_client.log_file.resolve())
    assert data["visit_filter"] == "interesting"
    assert len(data["items"]) == 1
    row = data["items"][0]
    assert row["ip"] == "1.2.3.4"
    assert row["method"] == "GET"
    assert row["path"] == "/web_admin/"
    assert row["status"] == 200
    assert row["browser"]["family"] == "Chrome"
    assert row["summary"]["who"].startswith("Chrome")
    assert "15.05.2026" in row["summary"]["when_prague"]
    assert row["summary"]["from_link"] == "přímo / bez odkazu"


def test_interesting_skips_health(live_client, monkeypatch):
    log_file = live_client.log_file
    log_file.write_text(
        '9.9.9.9 - - [15/May/2026:12:00:00 +0000] "GET /api/health HTTP/1.1" 200 1 "-" "Mozilla/5.0 Chrome/120"\n',
        encoding="utf-8",
    )

    def _resolve_ok():
        return log_file.resolve()

    monkeypatch.setattr(live_module, "_resolve_access_log_path", _resolve_ok)
    r = live_client.as_admin().get("/admin-api/traffic/live/snapshot?limit=10&interesting_only=true")
    assert r.status_code == 200
    assert r.json()["items"] == []

    r2 = live_client.as_admin().get("/admin-api/traffic/live/snapshot?limit=10&interesting_only=false")
    assert r2.status_code == 200
    assert len(r2.json()["items"]) == 1


def test_live_no_log_503(live_client, monkeypatch):
    monkeypatch.setattr(live_module, "_resolve_access_log_path", lambda: None)
    r = live_client.as_admin().get("/admin-api/traffic/live/snapshot")
    assert r.status_code == 503
