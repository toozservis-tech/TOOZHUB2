"""
E-mail a audit kolem žádosti servisu o přístup (SMTP volitelné — nesmí shodit HTTP).
Testy mohou přepsat ``send_service_access_request_email``.
"""
from __future__ import annotations

import logging
from typing import Callable, Optional

from sqlalchemy.orm import Session

from src.core.branding import APP_DISPLAY_NAME
from src.modules.email_client.service import EmailMessage, EmailService

from .audit_log import write_global_audit_log
from .models import Customer, Vehicle
from .service_access import masked_plate, masked_vin

logger = logging.getLogger(__name__)

send_service_access_request_email: Callable[..., bool] | None = None


def _default_send_owner_email(*, to_email: str, subject: str, plain_body: str) -> bool:
    svc = EmailService()
    if not svc.is_configured():
        raise ValueError("smtp_not_configured")
    msg = EmailMessage(to=[to_email], subject=subject, body=plain_body)
    return bool(svc.send_email(msg))


def try_email_owner_about_service_access_request(
    db: Session,
    *,
    owner: Customer,
    service: Customer,
    vehicle: Vehicle,
    request_id: int,
    tenant_id: Optional[int] = None,
) -> None:
    to_email = str(getattr(owner, "email", None) or "").strip()
    if not to_email or "@" not in to_email:
        write_global_audit_log(
            db,
            entity_type="service_access_request",
            entity_id=int(request_id),
            action="service_access_request_email_skipped",
            actor_type="system",
            actor_user_id=None,
            tenant_id=tenant_id or getattr(owner, "tenant_id", None),
            vehicle_id=int(vehicle.id),
            metadata={"reason": "owner_email_missing", "request_id": int(request_id)},
        )
        return

    service_disp = (service.name or service.email or "Servis").strip()
    plate_m = masked_plate(getattr(vehicle, "plate", None)) or "—"
    vin_m = masked_vin(getattr(vehicle, "vin", None)) or "—"
    subject = f"{APP_DISPLAY_NAME}: žádost servisu o přístup k vozidlu"
    body = (
        f"Dobrý den,\n\n"
        f"servis „{service_disp}“ žádá o přístup k vašemu vozidlu.\n"
        f"SPZ (ukázka): {plate_m}\n"
        f"VIN (ukázka): {vin_m}\n\n"
        f"Schválení nebo zamítnutí prosím proveďte po přihlášení v aplikaci {APP_DISPLAY_NAME} "
        f"(detail vozidla — záložka Servis / žádosti o přístup).\n\n"
        f"Neodpovídejte na tento e-mail — neobsahuje odkaz s oprávněním mimo aplikaci.\n"
    )

    sender = send_service_access_request_email or _default_send_owner_email
    try:
        sender(to_email=to_email, subject=subject, plain_body=body)
    except ValueError as exc:
        if str(exc) == "smtp_not_configured":
            write_global_audit_log(
                db,
                entity_type="service_access_request",
                entity_id=int(request_id),
                action="service_access_request_email_smtp_unavailable",
                actor_type="system",
                actor_user_id=None,
                tenant_id=tenant_id or getattr(owner, "tenant_id", None),
                vehicle_id=int(vehicle.id),
                metadata={
                    "request_id": int(request_id),
                    "severity": "warning",
                    "service_id": int(service.id),
                },
            )
            logger.warning("[SERVICE_ACCESS_EMAIL] SMTP není nakonfigurováno — e-mail se neodeslal.")
            return
        write_global_audit_log(
            db,
            entity_type="service_access_request",
            entity_id=int(request_id),
            action="service_access_request_email_failed",
            actor_type="system",
            actor_user_id=None,
            tenant_id=tenant_id or getattr(owner, "tenant_id", None),
            vehicle_id=int(vehicle.id),
            metadata={
                "request_id": int(request_id),
                "error": str(exc)[:500],
                "severity": "warning",
            },
        )
        logger.warning("[SERVICE_ACCESS_EMAIL] Odeslání selhalo: %s", exc)
    except Exception as exc:  # noqa: BLE001
        write_global_audit_log(
            db,
            entity_type="service_access_request",
            entity_id=int(request_id),
            action="service_access_request_email_failed",
            actor_type="system",
            actor_user_id=None,
            tenant_id=tenant_id or getattr(owner, "tenant_id", None),
            vehicle_id=int(vehicle.id),
            metadata={
                "request_id": int(request_id),
                "error": str(exc)[:500],
                "severity": "warning",
            },
        )
        logger.warning("[SERVICE_ACCESS_EMAIL] Odeslání selhalo: %s", exc)
