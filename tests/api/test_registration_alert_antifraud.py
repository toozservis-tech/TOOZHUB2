"""Unit coverage: admin registration alert obsahuje antifraud metadata v HTML."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.server.main_helpers import send_registration_alert_email


def test_registration_alert_email_includes_antifraud_metadata():
    fake_db = MagicMock()
    metadata = {
        "email_status": "pending",
        "phone_status": "unverified",
        "risk_flags": ["mx_lookup_timeout"],
        "fraud_score": 2,
        "registration_ip": "203.0.113.1",
        "registration_user_agent": "curl/8.0",
        "tenant_id": "t-1",
        "customer_id": 99,
        "role": "user",
    }
    with patch("src.server.main_helpers.get_registration_alert_recipients", return_value=["ops@example.com"]):
        with patch("src.modules.email_client.service.EmailService") as ES:
            inst = ES.return_value
            inst.is_configured.return_value = True
            send_registration_alert_email(
                fake_db,
                registration_type="user",
                account_email="newuser@example.com",
                account_name="Nový Uživatel",
                metadata=metadata,
            )
            inst.send_email.assert_called_once()
            msg = inst.send_email.call_args[0][0]
            html = msg.html_body or ""
            plain = msg.body or ""
            for needle in (
                "pending",
                "unverified",
                "mx_lookup_timeout",
                "203.0.113.1",
                "t-1",
                "99",
                "user",
            ):
                assert needle in html or needle in plain, f"missing {needle} in notification bodies"

