"""Operational reservation -> consent -> job -> photo -> final history -> handover.

Synthetic actors and local temporary file paths only. No external service traffic.
"""
import base64
from datetime import datetime, timedelta
from io import BytesIO
from uuid import uuid4

from PIL import Image
from test_service_http_lifecycle import http_flow
from src.modules.vehicle_hub.models import Customer, Reservation, ServiceRecord, VehicleServiceLink
from src.modules.vehicle_hub.routers_v1 import reservations
from src.modules.vehicle_hub.service_job_models import ServiceJobPhoto


def test_booking_service_workflow_requires_owner_consent_and_is_idempotent(http_flow, monkeypatch, tmp_path):
    from src.modules.vehicle_hub.routers_v1 import service_records
    from src.modules.vehicle_hub.routers_v1 import service_jobs
    from src.modules.vehicle_hub import vehicle_privacy
    f = http_flow
    f.client.app.include_router(reservations.router, prefix="/api/v1")
    # Durable storage is isolated from production and the user's actual documents.
    from src.core import file_storage
    monkeypatch.setattr(service_records, "SERVICE_RECORD_ATTACHMENTS_DIR", tmp_path / "record_photos")
    monkeypatch.setattr(file_storage, "DATA_DIR", tmp_path)
    for name in ["owner", "service", "stranger"]:
        a = f.actors[name]
        login = f.client.post("/user/login", json={
            "email": a["email"], "password": f.password, "expected_role": a["role"]})
        assert login.status_code == 200
        f.headers = getattr(f, "headers", {})
        f.headers[name] = {"Authorization": "Bearer " + login.json()["access_token"]}
    with f.factory() as db:
        service = db.get(Customer, f.actors["service"]["id"])
        service.workshop_same_as_registered = False
        service.workshop_city = "Test town"
        owner = db.get(Customer, f.actors["owner"]["id"])
        booking = Reservation(
            tenant_id=owner.tenant_id,
            customer_id=owner.id,
            service_id=service.id,
            vehicle_id=f.vehicle_id,
            service_type="Brzdy",
            note="Kontrola a výměna destiček",
            start_datetime=datetime.utcnow() + timedelta(days=2),
            status="CONFIRMED",
        )
        db.add(booking)
        db.commit()
        booking_id = booking.id
    url = f"/api/v1/reservations/{booking_id}"
    client, h = f.client, f.headers
    assert client.get(url + "/workspace", headers=h["owner"]).status_code == 403
    assert client.get(url + "/workspace", headers=h["stranger"]).status_code == 403
    ctx = client.get(url + "/workspace", headers=h["service"])
    assert ctx.status_code == 200, ctx.text
    body = ctx.json()
    assert body["vehicle_id"] == f.vehicle_id and body["customer_name"]
    assert body["access_approved"] is False and body["job"] is None
    assert client.post(url + "/start-job", headers=h["service"]).status_code == 403
    requested = client.post(url + "/request-access", headers=h["service"])
    assert requested.status_code == 200, requested.text
    approval_id = requested.json()["request_id"]
    assert client.post(url + "/request-access", headers=h["service"]).json()["request_id"] == approval_id
    assert client.put(
        f"/api/v1/services/access-requests/{approval_id}",
        headers=h["owner"], json={"decision": "approved"}
    ).status_code == 200
    job = client.post(url + "/start-job", headers=h["service"])
    assert job.status_code == 200, job.text
    job_data = job.json()
    assert client.post(url + "/start-job", headers=h["service"]).json()["id"] == job_data["id"]
    job_id = job_data["id"]
    started = client.post(f"/api/v1/service-jobs/{job_id}/updates", headers=h["service"], json={
        "client_id":str(uuid4()), "expected_version": job_data["version"],
        "status":"in_progress", "message":"Práce zahájena", "mileage": 102345,
    })
    assert started.status_code == 200, started.text
    img = BytesIO()
    Image.new("RGB", (120, 120), (225, 225, 225)).save(img, format="JPEG")
    encoded = base64.b64encode(img.getvalue()).decode("ascii")
    photo_idempotency = str(uuid4())
    photo_payload = {"client_id": photo_idempotency, "caption": "Brzdy před opravou", "content_base64": encoded}
    uploaded = client.post(f"/api/v1/service-jobs/{job_id}/photos", headers=h["service"], json=photo_payload)
    assert uploaded.status_code == 200, uploaded.text
    assert len(uploaded.json()["job"]["photos"]) == 1
    again = client.post(f"/api/v1/service-jobs/{job_id}/photos", headers=h["service"], json=photo_payload)
    assert again.status_code == 200 and again.json()["photo"]["id"] == uploaded.json()["photo"]["id"]
    same_image = client.post(f"/api/v1/service-jobs/{job_id}/photos", headers=h["service"],
                             json={**photo_payload, "client_id":str(uuid4())})
    assert same_image.status_code == 200 and same_image.json()["photo"]["id"] == uploaded.json()["photo"]["id"]
    assert same_image.json()["job"]["version"] == uploaded.json()["job"]["version"]
    assert client.get(f"/api/v1/service-jobs/{job_id}/photos/{uploaded.json()['photo']['id']}",
                      headers=h["stranger"]).status_code in (403,404)
    stored = client.get(f"/api/v1/service-jobs/{job_id}/photos/{uploaded.json()['photo']['id']}", headers=h["service"])
    assert stored.status_code == 200 and stored.headers["content-type"].startswith("image/jpeg")
    finished = client.post(f"/api/v1/service-jobs/{job_id}/updates", headers=h["service"], json={
        "client_id":str(uuid4()), "expected_version": uploaded.json()["job"]["version"],
        "status":"completed", "message":"Brzdy hotové, zkušební jízda OK", "price": 1800,
    })
    assert finished.status_code == 200, finished.text
    assert finished.json()["final_record_id"]
    with f.factory() as db:
        record = db.get(ServiceRecord, finished.json()["final_record_id"])
        assert "storage_key" in record.attachments and "Brzdy před opravou" in record.attachments
        assert db.query(ServiceJobPhoto).count() == 1
    handed = client.post(f"/api/v1/service-jobs/{job_id}/handover", headers=h["service"], json={
        "client_id": str(uuid4()), "expected_version": finished.json()["version"]})
    assert handed.status_code == 200, handed.text
    assert handed.json()["status"] == "handed_over"
    other = BytesIO()
    Image.new("RGB", (120, 120), (22, 33, 44)).save(other, format="JPEG")
    assert client.post(f"/api/v1/service-jobs/{job_id}/photos", headers=h["service"],
                       json={**photo_payload, "client_id":str(uuid4()),
                             "content_base64":base64.b64encode(other.getvalue()).decode("ascii")}).status_code == 409
