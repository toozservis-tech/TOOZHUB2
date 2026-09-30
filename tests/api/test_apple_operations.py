"""Administration/maintenance checks with synthetic accounts and mocked Apple."""
from types import SimpleNamespace
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from appstoreserverlibrary.signed_data_verifier import VerificationException, VerificationStatus

from test_apple_billing import setup, signed_state
from src.modules.licensing import apple_store as store, apple_reconciliation as worker
from src.modules.vehicle_hub.routers_v1 import apple_billing
from src.modules.vehicle_hub.database import get_db
from src.server import admin_api, bootstrap


def test_unconfigured_apple_job_is_not_reported_running(setup, monkeypatch):
    monkeypatch.setattr(admin_api, "get_job_pause_metadata", lambda _: {})
    def unavailable(): raise HTTPException(503, "Čeká na aktivaci")
    monkeypatch.setattr(store, "config", unavailable)
    monkeypatch.setenv("APPLE_IAP_ENABLED", "1")
    jobs = admin_api.get_control_center_jobs(email="fixture@example.invalid", db=setup[0])["jobs"]
    job = next(item for item in jobs if item["name"] == worker.JOB_NAME)
    assert job["available"] is False and job["effective_enabled"] is False
    assert job["state"] == "disabled" and job["unavailable_reason"] == "Čeká na aktivaci"


def test_manual_apple_job_never_dispatches_payment_worker(setup, monkeypatch):
    from src.modules.vehicle_hub.routers_v1 import license_status
    monkeypatch.setattr(admin_api, "is_job_paused", lambda _: False)
    monkeypatch.setattr(admin_api, "log_developer_action", lambda *a, **k: None)
    monkeypatch.setattr(license_status, "process_license_subscription_jobs", lambda **kw: pytest.fail("Apple job invoked a Comgate charge"))
    monkeypatch.setattr(worker, "reconcile_subscriptions", lambda **kw: {"checked": 2, "errors": 0})
    result = admin_api.run_control_center_job({"job_name": worker.JOB_NAME}, None, "fixture@example.invalid", setup[0])
    assert result["result"]["checked"] == 2


def test_paused_apple_job_does_not_run(setup, monkeypatch):
    monkeypatch.setattr(admin_api, "is_job_paused", lambda _: True)
    monkeypatch.setattr(worker, "reconcile_subscriptions", lambda **kw: pytest.fail("Paused worker ran"))
    with pytest.raises(HTTPException) as exc:
        admin_api.run_control_center_job({"job_name": worker.JOB_NAME}, None, "fixture@example.invalid", setup[0])
    assert exc.value.status_code == 409


def test_disabled_worker_cannot_be_reported_resumed(setup, monkeypatch):
    monkeypatch.setenv("APPLE_IAP_ENABLED", "0")
    monkeypatch.setattr(admin_api, "set_job_paused", lambda *a, **k: pytest.fail("Disabled worker resumed"))
    with pytest.raises(HTTPException) as exc:
        admin_api.resume_control_center_job(admin_api.JobStateRequest(job_name=worker.JOB_NAME, reason="fixture"), None, "fixture@example.invalid", setup[0])
    assert exc.value.status_code == 409


def test_maintenance_accepts_signed_notification_but_not_other_purchase_routes(setup, monkeypatch):
    signed_state(setup, monkeypatch)
    verifier, _ = store.apple_services(setup[3])
    verifier.verify_and_decode_notification = lambda _: SimpleNamespace(notificationType="TEST")
    monkeypatch.setattr(bootstrap, "get_runtime_setting_bool", lambda *a: True)
    app = FastAPI()
    bootstrap._register_middlewares(app)
    app.include_router(apple_billing.router, prefix="/api/v1/license")
    app.dependency_overrides[get_db] = lambda: setup[0]
    with TestClient(app) as client:
        path = "/api/v1/license/apple/notifications"
        response = client.post(path, json={"signedPayload": "signed-fixture"})
        assert response.status_code == 200 and response.json() == {"received": True}
        def invalid(_): raise VerificationException(VerificationStatus.VERIFICATION_FAILURE)
        verifier.verify_and_decode_notification = invalid
        assert client.post(path, json={"signedPayload": "forged-fixture"}).status_code == 400
        assert client.post("/api/v1/license/apple/session").status_code == 503
        assert client.post(path + "/unexpected").status_code == 503
