"""Admin traffic report (GoAccess) — RBAC a bezpečné chování."""
from __future__ import annotations

import json
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.server.admin_traffic_report as traffic_module
from src.core.auth import get_current_user_email
from src.modules.vehicle_hub.database import Base, get_db as vehicle_hub_get_db
from src.modules.vehicle_hub.models import Customer, Tenant

# admin router kromě traffic — import celého admin_api je zbytečně těžký; použijeme jen traffic router.
from src.server.admin_traffic_report import router as traffic_router


@pytest.fixture()
def traffic_rb_client(tmp_path, monkeypatch):
    db_path = tmp_path / "traffic.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    tenant = Tenant(name="T", license_key="lic-traf", workspace_slug="tr", workspace_route_kind="user")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    admin = Customer(
        tenant_id=tenant.id,
        email="traffic.admin@example.com",
        password_hash="x",
        name="Admin",
        role="admin",
    )
    user = Customer(
        tenant_id=tenant.id,
        email="traffic.user@example.com",
        password_hash="x",
        name="U",
        role="user",
    )
    service = Customer(
        tenant_id=tenant.id,
        email="traffic.svc@example.com",
        password_hash="x",
        name="S",
        role="service",
    )
    db.add_all([admin, user, service])
    db.commit()

    report_html = tmp_path / "goaccess-admin.html"
    report_meta = tmp_path / "goaccess-admin.meta.json"
    monkeypatch.setattr(traffic_module, "GOACCESS_REPORT_HTML_PATH", report_html)
    monkeypatch.setattr(traffic_module, "GOACCESS_REPORT_META_PATH", report_meta)

    stub_script = tmp_path / "admin_generate_traffic_report.sh"
    stub_script.write_text(
        "#!/bin/bash\n"
        f'echo \'{{"ok":true,"generated_at":"2099-01-01T00:00:00Z","source_log":"/tmp/access.log","report_path":"{report_html}","error":null}}\' > "{report_meta}"\n'
        f'echo "<html><body>ok</body></html>" > "{report_html}"\n',
        encoding="utf-8",
    )
    stub_script.chmod(0o755)
    monkeypatch.setattr(traffic_module, "_REPORT_SCRIPT", stub_script)

    app = FastAPI()
    app.include_router(traffic_router)

    def override_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[vehicle_hub_get_db] = override_db

    from types import SimpleNamespace

    def client_for(email: str):
        app.dependency_overrides[get_current_user_email] = lambda e=email: e
        return TestClient(app)

    try:
        yield SimpleNamespace(
            db=db,
            as_admin=lambda: client_for(admin.email),
            as_user=lambda: client_for(user.email),
            as_service=lambda: client_for(service.email),
            report_html=report_html,
            report_meta=report_meta,
            app=app,
        )
    finally:
        app.dependency_overrides.clear()
        db.close()
        engine.dispose()


def test_regular_user_forbidden(traffic_rb_client):
    c = traffic_rb_client.as_user()
    assert c.get("/admin-api/traffic/report").status_code == 403
    assert c.get("/admin-api/traffic/report/status").status_code == 403
    assert c.post("/admin-api/traffic/report/regenerate").status_code == 403


def test_service_account_forbidden(traffic_rb_client):
    c = traffic_rb_client.as_service()
    assert c.get("/admin-api/traffic/report").status_code == 403
    assert c.post("/admin-api/traffic/report/regenerate").status_code == 403


def test_admin_get_report_html(traffic_rb_client):
    traffic_rb_client.report_html.write_text("<html><body>x</body></html>", encoding="utf-8")
    traffic_rb_client.report_meta.write_text(
        json.dumps(
            {
                "ok": True,
                "generated_at": "2099-01-01T00:00:00Z",
                "source_log": "/var/log/nginx/access.log",
                "report_path": str(traffic_rb_client.report_html),
                "error": None,
            }
        ),
        encoding="utf-8",
    )
    c = traffic_rb_client.as_admin()
    r = c.get("/admin-api/traffic/report")
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("text/html")
    body = r.text
    assert "<html>" in body
    assert "/var/log/nginx" not in body  # nesmí unikat raw log cesta v HTML odpovědi obsahu reportu
    assert "127.0.0.1" not in body


def test_missing_report_safe_error(traffic_rb_client):
    c = traffic_rb_client.as_admin()
    r = c.get("/admin-api/traffic/report")
    assert r.status_code == 404
    assert "Přehled" in r.text or "přehled" in r.text.lower()
    assert "GET / HTTP" not in r.text
    assert "127.0.0.1" not in r.text


def test_regenerate_runs_fixed_script_only(traffic_rb_client, monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append({"argv": list(cmd), "shell": kwargs.get("shell")})
        traffic_rb_client.report_meta.write_text(
            json.dumps(
                {
                    "ok": True,
                    "generated_at": "2099-01-01T12:00:00Z",
                    "source_log": "/var/log/nginx/access.log",
                    "report_path": str(traffic_rb_client.report_html),
                    "error": None,
                }
            ),
            encoding="utf-8",
        )
        traffic_rb_client.report_html.write_text("<html><body>y</body></html>", encoding="utf-8")

        class _R:
            returncode = 0

        return _R()

    monkeypatch.setattr(traffic_module.subprocess, "run", fake_run)
    c = traffic_rb_client.as_admin()
    r = c.post("/admin-api/traffic/report/regenerate?inject=ignored")
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    assert len(calls) == 1
    assert calls[0]["shell"] is False
    argv = calls[0]["argv"]
    assert argv[:2] == ["/bin/bash", str(traffic_module._REPORT_SCRIPT)]
    assert "inject" not in " ".join(argv)
