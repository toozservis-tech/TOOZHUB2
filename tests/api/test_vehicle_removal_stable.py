"""
Integrační kontrola odebrání vozidla vs. legacy user_email / backfill.
Vyžaduje běžící API (TEST_API_URL / výchozí 127.0.0.1:8000) a nově nasazený kód lifecycle.

Spuštění: RUN_LIFECYCLE_INTEGRATION=1 pytest tests/api/test_vehicle_removal_stable.py
"""
from __future__ import annotations

import os

from uuid import uuid4

import pytest
import requests

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIFECYCLE_INTEGRATION") != "1",
    reason="Nastavte RUN_LIFECYCLE_INTEGRATION=1 a restartovaný backend s novým lifecycle kódem.",
)

from tests.api.integration_accounts import CI_API_BUYER, CI_API_SELLER
from tests.api.test_vehicle_lifecycle_canonical import _create_vehicle, _register_user, _vin


def test_vehicle_removal_sale_hides_vehicle_and_stable_on_repeat(api_url):
    seller_token, _ = _register_user(api_url, email=CI_API_SELLER, name="Seller RM")
    buyer_email = CI_API_BUYER
    plate = f"RM{uuid4().hex[:5].upper()}"[:7]
    vin = _vin()
    vehicle_id = _create_vehicle(api_url, seller_token, plate=plate, vin=vin)

    init = requests.post(
        f"{api_url}/api/v1/vehicles/{vehicle_id}/remove/init",
        headers={"Authorization": f"Bearer {seller_token}"},
        json={"reason_code": "sale"},
        timeout=8,
    )
    assert init.status_code == 200, init.text

    removal = requests.post(
        f"{api_url}/api/v1/vehicles/{vehicle_id}/remove/confirm",
        headers={"Authorization": f"Bearer {seller_token}"},
        json={
            "reason_code": "sale",
            "followup_answer": {"buyer_email": buyer_email, "buyer_phone": "+420987654321"},
        },
        timeout=15,
    )
    assert removal.status_code == 200, removal.text
    body = removal.json()
    assert body.get("removed") is True
    assert body.get("digital_report_document_uid")

    def ids_for(tok: str) -> set[int]:
        r = requests.get(f"{api_url}/api/v1/vehicles", headers={"Authorization": f"Bearer {tok}"}, timeout=8)
        assert r.status_code == 200, r.text
        return {int(x["id"]) for x in r.json()}

    assert vehicle_id not in ids_for(seller_token)
    assert vehicle_id not in ids_for(seller_token)


def test_transfer_claim_alias_then_claim_by_transfer_second_call_same(api_url):
    seller_token, _ = _register_user(api_url, email=CI_API_SELLER, name="Seller Alias")
    buyer_token, _ = _register_user(api_url, email=CI_API_BUYER, name="Buyer Alias")
    plate = f"AL{uuid4().hex[:5].upper()}"[:7]
    vin = _vin()
    vehicle_id = _create_vehicle(api_url, seller_token, plate=plate, vin=vin)

    tok_resp = requests.post(
        f"{api_url}/api/v1/vehicles/{vehicle_id}/transfer-token",
        headers={"Authorization": f"Bearer {seller_token}"},
        json={"transfer_reason": "sale", "expires_in_days": 14},
        timeout=8,
    )
    assert tok_resp.status_code == 200, tok_resp.text
    raw_token = tok_resp.json()["token"]

    alias = requests.post(
        f"{api_url}/api/v1/vehicles/transfer-claim",
        headers={"Authorization": f"Bearer {buyer_token}"},
        json={"token": raw_token, "spz": plate, "vin": vin},
        timeout=8,
    )
    assert alias.status_code == 200, alias.text

    dup_alias = requests.post(
        f"{api_url}/api/v1/vehicles/transfer-claim",
        headers={"Authorization": f"Bearer {buyer_token}"},
        json={"token": raw_token, "spz": plate, "vin": vin},
        timeout=8,
    )
    dup_canon = requests.post(
        f"{api_url}/api/v1/vehicles/claim-by-transfer",
        headers={"Authorization": f"Bearer {buyer_token}"},
        json={"token": raw_token, "spz": plate, "vin": vin},
        timeout=8,
    )
    assert dup_alias.status_code == 409
    assert dup_canon.status_code == 409


def test_public_transfer_vehicle_payload_has_no_plain_spz(api_url):
    seller_token, _ = _register_user(api_url, email=CI_API_SELLER, name="Seller Pub")
    plate = f"PB{uuid4().hex[:5].upper()}"[:7]
    vin = _vin()
    vehicle_id = _create_vehicle(api_url, seller_token, plate=plate, vin=vin)

    tok_resp = requests.post(
        f"{api_url}/api/v1/vehicles/{vehicle_id}/transfer-token",
        headers={"Authorization": f"Bearer {seller_token}"},
        json={"transfer_reason": "sale", "expires_in_days": 14},
        timeout=8,
    )
    assert tok_resp.status_code == 200, tok_resp.text
    raw_token = tok_resp.json()["token"]

    pub = requests.get(f"{api_url}/api/public/vehicle-transfer/{raw_token}", timeout=8)
    assert pub.status_code == 200, pub.text
    js = pub.json()
    v = js.get("vehicle") or {}
    assert "spz_current" not in v
    assert "vehicle_id" not in v
    assert v.get("spz_masked") is not None


def test_direct_vehicle_delete_returns_409(api_url):
    seller_token, _ = _register_user(api_url, email=CI_API_SELLER, name="Seller Del")
    plate = f"DL{uuid4().hex[:5].upper()}"[:7]
    vin = _vin()
    vehicle_id = _create_vehicle(api_url, seller_token, plate=plate, vin=vin)
    r = requests.delete(
        f"{api_url}/api/v1/vehicles/{vehicle_id}",
        headers={"Authorization": f"Bearer {seller_token}"},
        timeout=8,
    )
    assert r.status_code == 409

