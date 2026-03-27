"""
Testy pro servisní workspace API.
"""
from __future__ import annotations

from datetime import date, timedelta
from uuid import uuid4

import requests
from sqlalchemy import func

from src.modules.vehicle_hub.database import SessionLocal
from src.modules.vehicle_hub.models import Customer


def _unique_email(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:10]}@example.com"


def _register_user(api_url: str, *, email: str, password: str = "testpass123", name: str = "Test User") -> tuple[str, int]:
    response = requests.post(
        f"{api_url}/user/register",
        json={
            "email": email,
            "password": password,
            "name": name,
            "phone": "+420123456789",
        },
        timeout=8,
    )
    assert response.status_code == 200
    payload = response.json()
    return payload["access_token"], int(payload["user"]["id"])


def _promote_user_to_service(email: str) -> None:
    db = SessionLocal()
    try:
        customer = (
            db.query(Customer)
            .filter(func.lower(Customer.email) == str(email).lower())
            .first()
        )
        assert customer is not None
        customer.role = "service"
        db.commit()
    finally:
        db.close()


def _create_vehicle(api_url: str, user_token: str, nickname: str = "Test Vehicle") -> int:
    response = requests.post(
        f"{api_url}/api/v1/vehicles",
        headers={"Authorization": f"Bearer {user_token}"},
        json={
            "nickname": nickname,
            "brand": "Skoda",
            "model": "Octavia",
            "year": 2021,
            "plate": f"TEST{uuid4().hex[:4].upper()}",
            "stk_valid_until": (date.today() + timedelta(days=365)).isoformat(),
        },
        timeout=8,
    )
    assert response.status_code == 200, response.text
    return int(response.json()["id"])


def test_service_workspace_link_existing_and_ingest(api_url):
    service_email = _unique_email("service")
    customer_email = _unique_email("customer")

    service_token, _ = _register_user(api_url, email=service_email, name="Service účet")
    _promote_user_to_service(service_email)

    customer_token, customer_id = _register_user(api_url, email=customer_email, name="Koncový zákazník")
    vehicle_id = _create_vehicle(api_url, customer_token, nickname="Fleet test")

    service_headers = {"Authorization": f"Bearer {service_token}"}

    link_response = requests.post(
        f"{api_url}/api/v1/services/workspace/customers/link-existing",
        headers=service_headers,
        json={"customer_email": customer_email, "note": "API test link"},
        timeout=8,
    )
    assert link_response.status_code == 200, link_response.text
    link_payload = link_response.json()
    assert link_payload["linked"] is True

    customers_response = requests.get(
        f"{api_url}/api/v1/services/workspace/customers",
        headers=service_headers,
        timeout=8,
    )
    assert customers_response.status_code == 200, customers_response.text
    customers = customers_response.json()
    assert any(str(item.get("email", "")).lower() == customer_email.lower() for item in customers)

    vehicles_response = requests.get(
        f"{api_url}/api/v1/services/workspace/customers/{customer_id}/vehicles",
        headers=service_headers,
        timeout=8,
    )
    assert vehicles_response.status_code == 200, vehicles_response.text
    vehicles = vehicles_response.json()
    assert any(int(item["id"]) == vehicle_id for item in vehicles)

    ingest_response = requests.post(
        f"{api_url}/api/v1/services/workspace/documents/ingest",
        headers=service_headers,
        json={
            "customer_id": customer_id,
            "vehicle_id": vehicle_id,
            "source_type": "invoice",
            "manual_note": "Import test faktury",
            "manual_text": (
                "Faktura č.: FV-2026-001\n"
                "Dodavatel: Test Servis s.r.o.\n"
                "Datum vystavení: 01.03.2026\n"
                "Práce diagnostika 1 ks 800 Kč\n"
                "Náhradní díl filtr 1 ks 500 Kč\n"
                "DPH 21% 273 Kč\n"
                "Celkem k úhradě 1573 Kč\n"
            ),
            "auto_create_service_record": True,
        },
        timeout=10,
    )
    assert ingest_response.status_code == 200, ingest_response.text
    ingest_payload = ingest_response.json()
    assert ingest_payload.get("processing_status") in {"processed", "needs_review"}
    assert ingest_payload.get("auto_created_service_record_id") is not None
    assert (ingest_payload.get("parse_confidence") or 0) > 0
    parsed_data = ingest_payload.get("parsed_data") or {}
    assert parsed_data.get("document_number")


def test_service_workspace_invitation_accept_flow(api_url):
    service_email = _unique_email("service_invite")
    invited_email = _unique_email("invited")

    service_token, _ = _register_user(api_url, email=service_email, name="Service Invite")
    _promote_user_to_service(service_email)
    service_headers = {"Authorization": f"Bearer {service_token}"}

    send_response = requests.post(
        f"{api_url}/api/v1/services/workspace/invitations/send",
        headers=service_headers,
        json={
            "invite_email": invited_email,
            "invite_name": "Pozvaný klient",
            "invite_message": "Prosím zaregistrujte se pro přístup k servisní historii.",
        },
        timeout=8,
    )
    assert send_response.status_code == 200, send_response.text
    send_payload = send_response.json()
    assert send_payload.get("registration_url")

    invites_response = requests.get(
        f"{api_url}/api/v1/services/workspace/invitations",
        headers=service_headers,
        timeout=8,
    )
    assert invites_response.status_code == 200, invites_response.text
    invites = invites_response.json()
    matching_invite = next(
        (item for item in invites if str(item.get("invite_email", "")).lower() == invited_email.lower()),
        None,
    )
    assert matching_invite is not None

    db = SessionLocal()
    try:
        invite_token = None
        customer_invite = (
            db.query(Customer.id, Customer.email)
            .filter(func.lower(Customer.email) == invited_email.lower())
            .first()
        )
        if customer_invite:
            # Email může být už existující. Pak je tok přímého propojení bez tokenu.
            invite_token = None
        else:
            from src.modules.vehicle_hub.models import ServiceCustomerInvite

            invite = (
                db.query(ServiceCustomerInvite)
                .filter(
                    func.lower(ServiceCustomerInvite.invite_email) == invited_email.lower(),
                    ServiceCustomerInvite.status == "pending",
                )
                .order_by(ServiceCustomerInvite.created_at.desc())
                .first()
            )
            assert invite is not None
            invite_token = invite.token
    finally:
        db.close()

    invited_token, _ = _register_user(api_url, email=invited_email, name="Invited User")
    invited_headers = {"Authorization": f"Bearer {invited_token}"}

    if invite_token:
        accept_response = requests.post(
            f"{api_url}/api/v1/services/workspace/invitations/accept",
            headers=invited_headers,
            json={"token": invite_token},
            timeout=8,
        )
        assert accept_response.status_code == 200, accept_response.text
        accept_payload = accept_response.json()
        assert accept_payload.get("accepted") is True

    customers_response = requests.get(
        f"{api_url}/api/v1/services/workspace/customers",
        headers=service_headers,
        timeout=8,
    )
    assert customers_response.status_code == 200, customers_response.text
    customers = customers_response.json()
    assert any(str(item.get("email", "")).lower() == invited_email.lower() for item in customers)
