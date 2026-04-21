from __future__ import annotations

import hashlib
import json
import re
import secrets
import zipfile
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.config import DATA_DIR, FRONTEND_BASE_URL
from src.core.rbac import normalize_role

from ..audit_log import write_global_audit_log
from ..database import get_db
from ..models import (
    Customer,
    ServiceAccessRequest,
    ServiceRecord,
    Vehicle,
    VehicleRemovalEvent,
    VehicleReportDocument,
    VehicleServiceLink,
    VehicleTransferToken,
)
from ..ownership import (
    get_owned_vehicle,
    release_vehicle_owner_assignment,
    transfer_vehicle_to_new_owner,
    user_owns_vehicle,
)
from ..reports.vehicle_report_access import resolve_report_mode
from ..reports.vehicle_report_builder import build_vehicle_service_report_payload
from ..reports.vehicle_report_pdf import render_vehicle_service_report_pdf
from ..reports.vehicle_report_verification import finalize_vehicle_report_document
from ..schema_management import assert_module_ready
from ..service_access import create_or_update_vehicle_service_link, revoke_vehicle_service_link, vehicle_label
from ..vehicle_public_history import render_vehicle_qr_svg
from .auth import get_current_user

"""
PRODUCTION CRITICAL LOGIC:
- service access enforcement
- lifecycle remove/transfer
- audit log
Jakákoliv změna musí projít production auditem.
"""

router = APIRouter(prefix="/vehicles", tags=["vehicle-lifecycle-v1"])

ARCHIVE_ROOT = DATA_DIR / "vehicle_archives"
REPORT_ROOT = DATA_DIR / "vehicle_reports"
ARCHIVE_ROOT.mkdir(parents=True, exist_ok=True)
REPORT_ROOT.mkdir(parents=True, exist_ok=True)

REMOVAL_FOLLOWUP_FIELDS = {
    "sale": "buyer_contact_hint",
    "scrap": "scrap_document_reference",
    "export": "export_country",
    "temporary_hide": "hide_until_or_reason",
    "duplicate": "duplicate_vehicle_reference",
    "other": "note",
}


class ServiceAccessLinkRequest(BaseModel):
    service_id: int = Field(gt=0)
    request_reason: Optional[str] = Field(default=None, max_length=500)
    access_scope: list[str] = Field(default_factory=lambda: [
        "read_summary",
        "create_service_record",
        "manage_work_order",
        "manage_invoice",
        "manage_photos",
    ])


class ServiceAccessDecisionRequest(BaseModel):
    note: Optional[str] = Field(default=None, max_length=500)


class VehicleLookupBySpzRequest(BaseModel):
    spz: str = Field(..., min_length=2, max_length=32)


class AttachExistingVehicleRequest(BaseModel):
    spz: str = Field(..., min_length=2, max_length=32)
    vin: str = Field(..., min_length=5, max_length=32)
    confirm_vehicle_id: int = Field(gt=0)
    acquisition_reason: str = Field(default="existing_vehicle_claim", max_length=64)


class RemovalInitRequest(BaseModel):
    reason_code: str = Field(..., min_length=3, max_length=64)


class RemovalConfirmRequest(BaseModel):
    reason_code: str = Field(..., min_length=3, max_length=64)
    followup_answer: dict[str, Any] = Field(default_factory=dict)


class TransferTokenRequest(BaseModel):
    transfer_reason: str = Field(default="sale", min_length=3, max_length=64)
    expires_in_days: int = Field(default=30, ge=1, le=180)


class ClaimByTransferRequest(BaseModel):
    token: str = Field(..., min_length=20, max_length=512)
    spz: str = Field(..., min_length=2, max_length=32)
    vin: str = Field(..., min_length=5, max_length=32)


def _normalize_spz(value: str | None) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _normalize_vin(value: str | None) -> str:
    return re.sub(r"[^A-HJ-NPR-Z0-9]", "", str(value or "").upper())


def _token_hash(token: str) -> str:
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def _transfer_url(raw_token: str) -> str:
    base = str(FRONTEND_BASE_URL or "").strip().rstrip("/") or "http://127.0.0.1:8000"
    if base.endswith("/web/index.html"):
        return f"{base.rsplit('/', 1)[0]}/vehicle-transfer.html?token={raw_token}"
    if base.endswith("/web"):
        return f"{base}/vehicle-transfer.html?token={raw_token}"
    return f"{base}/web/vehicle-transfer.html?token={raw_token}"


def _safe_qr_svg(public_url: str) -> str | None:
    try:
        return render_vehicle_qr_svg(public_url)
    except HTTPException:
        return None


def _require_owned_vehicle(db: Session, current_user: Customer, vehicle_id: int) -> Vehicle:
    vehicle = get_owned_vehicle(db, current_user, int(vehicle_id), tenant_id=getattr(current_user, "tenant_id", None))
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nebylo nalezeno nebo k němu nemáte vlastnickou vazbu.")
    return vehicle


def _vehicle_public_summary(vehicle: Vehicle) -> dict[str, Any]:
    vin = str(vehicle.vin or "")
    return {
        "vehicle_id": int(vehicle.id),
        "label": vehicle_label(vehicle),
        "brand": vehicle.brand,
        "model": vehicle.model,
        "year": vehicle.year,
        "spz_current": vehicle.plate,
        "vin_masked": f"{vin[:3]}***{vin[-4:]}" if vin else None,
        "status": getattr(vehicle, "status", "active"),
    }


def _create_transfer_token(
    db: Session,
    *,
    vehicle: Vehicle,
    current_user: Customer,
    transfer_reason: str,
    expires_in_days: int,
) -> tuple[VehicleTransferToken, str, str]:
    raw_token = secrets.token_urlsafe(32)
    public_url = _transfer_url(raw_token)
    row = VehicleTransferToken(
        vehicle_id=int(vehicle.id),
        issued_by_user_id=int(current_user.id),
        transfer_reason=transfer_reason,
        token_hash=_token_hash(raw_token),
        qr_payload=public_url,
        expires_at=datetime.utcnow() + timedelta(days=int(expires_in_days)),
        status="active",
    )
    db.add(row)
    db.flush()
    write_global_audit_log(
        db,
        entity_type="vehicle_transfer_token",
        entity_id=int(row.id),
        action="transfer_token_issued",
        actor_type="user",
        actor_user_id=int(current_user.id),
        actor_role=getattr(current_user, "role", None),
        tenant_id=getattr(current_user, "tenant_id", None),
        vehicle_id=int(vehicle.id),
        metadata={"transfer_reason": transfer_reason, "expires_at": row.expires_at.isoformat()},
    )
    return row, raw_token, public_url


def _generate_vehicle_report(
    db: Session,
    *,
    vehicle: Vehicle,
    current_user: Customer,
) -> tuple[VehicleReportDocument, bytes]:
    resolved_mode = resolve_report_mode(db=db, vehicle=vehicle, current_user=current_user, requested_mode="owner")
    payload = build_vehicle_service_report_payload(db=db, vehicle=vehicle, current_user=current_user, mode=resolved_mode)
    payload, document_row = finalize_vehicle_report_document(db=db, vehicle=vehicle, current_user=current_user, payload=payload)
    pdf_content = render_vehicle_service_report_pdf(payload)
    report_path = REPORT_ROOT / f"vehicle-{int(vehicle.id)}-report-{document_row.document_id}.pdf"
    report_path.write_bytes(pdf_content)
    write_global_audit_log(
        db,
        entity_type="vehicle_report_document",
        entity_id=int(document_row.id),
        action="digital_report_generated",
        actor_type="user",
        actor_user_id=int(current_user.id),
        actor_role=getattr(current_user, "role", None),
        tenant_id=int(vehicle.tenant_id),
        vehicle_id=int(vehicle.id),
        metadata={"document_id": document_row.document_id, "path": str(report_path)},
    )
    return document_row, pdf_content


def _archive_vehicle_bundle(db: Session, *, vehicle: Vehicle, document_row: VehicleReportDocument) -> str:
    records = (
        db.query(ServiceRecord)
        .filter(ServiceRecord.vehicle_id == int(vehicle.id), ServiceRecord.is_deleted.is_(False))
        .order_by(ServiceRecord.performed_at.asc(), ServiceRecord.id.asc())
        .all()
    )
    archive_path = ARCHIVE_ROOT / f"vehicle-{int(vehicle.id)}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.zip"
    manifest = {
        "vehicle": {
            "id": int(vehicle.id),
            "vin": vehicle.vin,
            "spz_current": vehicle.plate,
            "make": vehicle.brand,
            "model": vehicle.model,
            "year": vehicle.year,
            "status": getattr(vehicle, "status", "active"),
        },
        "digital_report_document_id": int(document_row.id),
        "records": [
            {
                "id": int(row.id),
                "performed_at": row.performed_at.isoformat() if row.performed_at else None,
                "origin": getattr(row, "origin", None),
                "category": row.category,
                "description": row.description,
                "mileage": row.mileage,
            }
            for row in records
        ],
        "archived_at": datetime.utcnow().isoformat(),
    }
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, default=str, indent=2))
        report_path = REPORT_ROOT / f"vehicle-{int(vehicle.id)}-report-{document_row.document_id}.pdf"
        if report_path.exists():
            zf.write(report_path, "digital-report.pdf")
    return str(archive_path)


@router.post("/lookup-by-spz")
def lookup_vehicle_by_spz(
    payload: VehicleLookupBySpzRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    assert_module_ready(db, "vehicles", detail_prefix="Modul vozidel není připraven")
    spz = _normalize_spz(payload.spz)
    if not spz:
        raise HTTPException(status_code=422, detail="Zadejte platnou SPZ.")
    vehicle = db.query(Vehicle).filter(Vehicle.plate == spz).order_by(Vehicle.created_at.asc(), Vehicle.id.asc()).first()
    write_global_audit_log(
        db,
        entity_type="vehicle",
        entity_id=int(vehicle.id) if vehicle else None,
        action="vehicle_lookup_by_spz",
        actor_type=normalize_role(getattr(current_user, "role", None)),
        actor_user_id=getattr(current_user, "id", None),
        actor_role=getattr(current_user, "role", None),
        tenant_id=getattr(current_user, "tenant_id", None),
        vehicle_id=int(vehicle.id) if vehicle else None,
        metadata={"spz_hash": hashlib.sha256(spz.encode("utf-8")).hexdigest(), "found": bool(vehicle)},
    )
    db.commit()
    return {
        "exists": bool(vehicle),
        "vehicle": _vehicle_public_summary(vehicle) if vehicle else None,
        "requires_vin_confirmation": bool(vehicle),
    }


@router.post("/attach-existing")
def attach_existing_vehicle(
    payload: AttachExistingVehicleRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    vehicle = db.query(Vehicle).filter(Vehicle.id == int(payload.confirm_vehicle_id)).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nebylo nalezeno.")
    if _normalize_spz(payload.spz) != _normalize_spz(vehicle.plate):
        raise HTTPException(status_code=409, detail="SPZ nesouhlasí s nalezeným vozidlem.")
    if _normalize_vin(payload.vin) != _normalize_vin(vehicle.vin):
        raise HTTPException(status_code=409, detail="VIN nesouhlasí s nalezeným vozidlem.")
    transfer_vehicle_to_new_owner(
        db,
        vehicle=vehicle,
        new_owner=current_user,
        assigned_by_customer_id=int(current_user.id),
        ownership_origin=str(payload.acquisition_reason or "existing_vehicle_claim"),
    )
    vehicle.status = "active"
    write_global_audit_log(
        db,
        entity_type="vehicle",
        entity_id=int(vehicle.id),
        action="existing_vehicle_attached",
        actor_type="user",
        actor_user_id=int(current_user.id),
        actor_role=getattr(current_user, "role", None),
        tenant_id=int(current_user.tenant_id),
        vehicle_id=int(vehicle.id),
        metadata={"acquisition_reason": payload.acquisition_reason},
    )
    db.commit()
    return {"attached": True, "vehicle_id": int(vehicle.id), "history_preserved": True}


@router.get("/{vehicle_id}/service-access")
def list_vehicle_service_access(
    vehicle_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    vehicle = _require_owned_vehicle(db, current_user, vehicle_id)
    rows = (
        db.query(VehicleServiceLink, Customer)
        .join(Customer, VehicleServiceLink.service_customer_id == Customer.id)
        .filter(VehicleServiceLink.vehicle_id == int(vehicle.id))
        .order_by(VehicleServiceLink.updated_at.desc(), VehicleServiceLink.id.desc())
        .all()
    )
    requests = (
        db.query(ServiceAccessRequest, Customer)
        .join(Customer, ServiceAccessRequest.service_customer_id == Customer.id)
        .filter(
            ServiceAccessRequest.vehicle_id == int(vehicle.id),
            ServiceAccessRequest.owner_customer_id == int(current_user.id),
        )
        .order_by(ServiceAccessRequest.requested_at.desc(), ServiceAccessRequest.id.desc())
        .all()
    )
    return {
        "vehicle_id": int(vehicle.id),
        "access": [
            {
                "id": int(link.id),
                "service_tenant_id": getattr(service, "tenant_id", None),
                "service_id": int(service.id),
                "service_name": service.name or service.email,
                "status": link.status,
                "access_scope": {
                    "read_summary": bool(link.scope_vehicle_history_read),
                    "create_service_record": bool(link.scope_create_service_record),
                    "manage_work_order": True,
                    "manage_invoice": True,
                    "manage_photos": True,
                },
                "approved_at": link.approved_at.isoformat() if link.approved_at else None,
                "revoked_at": link.revoked_at.isoformat() if link.revoked_at else None,
                "updated_at": link.updated_at.isoformat() if link.updated_at else None,
            }
            for link, service in rows
        ],
        "requests": [
            {
                "id": int(req.id),
                "service_id": int(service.id),
                "service_name": service.name or service.email,
                "status": req.status,
                "message": req.request_message,
                "requested_at": req.requested_at.isoformat() if req.requested_at else None,
            }
            for req, service in requests
        ],
    }


@router.post("/{vehicle_id}/service-access/request-or-link")
def request_or_link_service_access(
    vehicle_id: int,
    payload: ServiceAccessLinkRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    vehicle = _require_owned_vehicle(db, current_user, vehicle_id)
    service = db.query(Customer).filter(Customer.id == int(payload.service_id), Customer.role.in_(["service", "developer_admin"])).first()
    if not service:
        raise HTTPException(status_code=404, detail="Servis nebyl nalezen.")
    link = create_or_update_vehicle_service_link(
        db,
        tenant_id=int(vehicle.tenant_id),
        service_customer_id=int(service.id),
        owner_customer_id=int(current_user.id),
        vehicle_id=int(vehicle.id),
        approved_by_customer_id=int(current_user.id),
        source_type="direct_user_grant",
        note=(payload.request_reason or "").strip() or None,
    )
    write_global_audit_log(
        db,
        entity_type="vehicle_service_access",
        entity_id=int(link.id),
        action="service_access_direct_approved",
        actor_type="user",
        actor_user_id=int(current_user.id),
        actor_role=getattr(current_user, "role", None),
        tenant_id=int(vehicle.tenant_id),
        vehicle_id=int(vehicle.id),
        metadata={"service_id": int(service.id), "access_scope": payload.access_scope},
    )
    db.commit()
    return {"linked": True, "access_id": int(link.id), "status": "approved", "vehicle_id": int(vehicle.id), "service_id": int(service.id)}


@router.post("/{vehicle_id}/service-access/{access_id}/approve")
def approve_service_access(
    vehicle_id: int,
    access_id: int,
    payload: ServiceAccessDecisionRequest | None = None,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    vehicle = _require_owned_vehicle(db, current_user, vehicle_id)
    request_row = db.query(ServiceAccessRequest).filter(
        ServiceAccessRequest.id == int(access_id),
        ServiceAccessRequest.vehicle_id == int(vehicle.id),
    ).first()
    if not request_row:
        raise HTTPException(status_code=404, detail="Žádost o přístup nebyla nalezena.")
    if request_row.status != "pending":
        raise HTTPException(status_code=409, detail="Žádost už byla vyřízena.")
    link = create_or_update_vehicle_service_link(
        db,
        tenant_id=int(vehicle.tenant_id),
        service_customer_id=int(request_row.service_customer_id),
        owner_customer_id=int(current_user.id),
        vehicle_id=int(vehicle.id),
        approved_by_customer_id=int(current_user.id),
        source_type="request_approved",
        source_request_id=int(request_row.id),
        note=(payload.note if payload else None) or request_row.request_message,
    )
    request_row.status = "approved"
    request_row.decided_at = datetime.utcnow()
    request_row.decided_by_customer_id = int(current_user.id)
    request_row.decision_note = payload.note if payload else None
    request_row.approved_link_id = int(link.id)
    write_global_audit_log(
        db,
        entity_type="vehicle_service_access",
        entity_id=int(link.id),
        action="service_access_approved",
        actor_type="user",
        actor_user_id=int(current_user.id),
        actor_role=getattr(current_user, "role", None),
        tenant_id=int(vehicle.tenant_id),
        vehicle_id=int(vehicle.id),
        metadata={"request_id": int(request_row.id)},
    )
    db.commit()
    return {"approved": True, "access_id": int(link.id), "request_id": int(request_row.id)}


@router.post("/{vehicle_id}/service-access/{access_id}/reject")
def reject_service_access(
    vehicle_id: int,
    access_id: int,
    payload: ServiceAccessDecisionRequest | None = None,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    vehicle = _require_owned_vehicle(db, current_user, vehicle_id)
    request_row = db.query(ServiceAccessRequest).filter(
        ServiceAccessRequest.id == int(access_id),
        ServiceAccessRequest.vehicle_id == int(vehicle.id),
    ).first()
    if not request_row:
        raise HTTPException(status_code=404, detail="Žádost o přístup nebyla nalezena.")
    if request_row.status != "pending":
        raise HTTPException(status_code=409, detail="Žádost už byla vyřízena.")
    request_row.status = "rejected"
    request_row.decided_at = datetime.utcnow()
    request_row.decided_by_customer_id = int(current_user.id)
    request_row.decision_note = payload.note if payload else None
    write_global_audit_log(
        db,
        entity_type="vehicle_service_request",
        entity_id=int(request_row.id),
        action="service_access_rejected",
        actor_type="user",
        actor_user_id=int(current_user.id),
        actor_role=getattr(current_user, "role", None),
        tenant_id=int(vehicle.tenant_id),
        vehicle_id=int(vehicle.id),
        metadata={"note": payload.note if payload else None},
    )
    db.commit()
    return {"rejected": True, "request_id": int(request_row.id)}


@router.post("/{vehicle_id}/service-access/{access_id}/revoke")
def revoke_service_access(
    vehicle_id: int,
    access_id: int,
    payload: ServiceAccessDecisionRequest | None = None,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    vehicle = _require_owned_vehicle(db, current_user, vehicle_id)
    link = db.query(VehicleServiceLink).filter(
        VehicleServiceLink.id == int(access_id),
        VehicleServiceLink.vehicle_id == int(vehicle.id),
        VehicleServiceLink.owner_customer_id == int(current_user.id),
    ).first()
    if not link:
        raise HTTPException(status_code=404, detail="Servisní přístup nebyl nalezen.")
    revoke_vehicle_service_link(
        db,
        service_customer_id=int(link.service_customer_id),
        vehicle_id=int(vehicle.id),
        revoked_by_customer_id=int(current_user.id),
        reason=(payload.note if payload else None) or "user_revoke",
    )
    write_global_audit_log(
        db,
        entity_type="vehicle_service_access",
        entity_id=int(link.id),
        action="service_access_revoked",
        actor_type="user",
        actor_user_id=int(current_user.id),
        actor_role=getattr(current_user, "role", None),
        tenant_id=int(vehicle.tenant_id),
        vehicle_id=int(vehicle.id),
        metadata={"reason": payload.note if payload else None},
    )
    db.commit()
    return {"revoked": True, "access_id": int(link.id)}


@router.post("/{vehicle_id}/remove/init")
def init_vehicle_removal(
    vehicle_id: int,
    payload: RemovalInitRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ = _require_owned_vehicle(db, current_user, vehicle_id)
    reason = str(payload.reason_code or "").strip().lower()
    if reason not in REMOVAL_FOLLOWUP_FIELDS:
        raise HTTPException(status_code=422, detail="Neplatný důvod odstranění vozidla z evidence.")
    return {
        "vehicle_id": int(vehicle_id),
        "reason_code": reason,
        "required_followup_field": REMOVAL_FOLLOWUP_FIELDS[reason],
        "requires_transfer_token": reason == "sale",
        "will_generate_digital_report": True,
        "will_archive_without_loss": True,
    }


@router.post("/{vehicle_id}/transfer-token")
def create_transfer_token(
    vehicle_id: int,
    payload: TransferTokenRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    vehicle = _require_owned_vehicle(db, current_user, vehicle_id)
    token_row, raw_token, public_url = _create_transfer_token(
        db,
        vehicle=vehicle,
        current_user=current_user,
        transfer_reason=payload.transfer_reason,
        expires_in_days=payload.expires_in_days,
    )
    db.commit()
    return {
        "id": int(token_row.id),
        "vehicle_id": int(vehicle.id),
        "token": raw_token,
        "status": token_row.status,
        "expires_at": token_row.expires_at.isoformat(),
        "qr_payload": public_url,
        "qr_svg": _safe_qr_svg(public_url),
        "share": {"email": public_url, "sms": public_url, "whatsapp": public_url},
    }


@router.post("/{vehicle_id}/remove/confirm")
def confirm_vehicle_removal(
    vehicle_id: int,
    payload: RemovalConfirmRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    vehicle = _require_owned_vehicle(db, current_user, vehicle_id)
    reason = str(payload.reason_code or "").strip().lower()
    required_field = REMOVAL_FOLLOWUP_FIELDS.get(reason)
    if not required_field:
        raise HTTPException(status_code=422, detail="Neplatný důvod odstranění vozidla z evidence.")
    if not str((payload.followup_answer or {}).get(required_field) or "").strip():
        raise HTTPException(status_code=422, detail=f"Pro důvod {reason} je povinné pole {required_field}.")
    document_row, _pdf_content = _generate_vehicle_report(db, vehicle=vehicle, current_user=current_user)
    transfer_row = None
    transfer_payload = None
    if reason == "sale":
        transfer_row, raw_token, public_url = _create_transfer_token(
            db,
            vehicle=vehicle,
            current_user=current_user,
            transfer_reason="sale",
            expires_in_days=30,
        )
        transfer_payload = {
            "token": raw_token,
            "qr_payload": public_url,
            "qr_svg": _safe_qr_svg(public_url),
            "share": {"email": public_url, "sms": public_url, "whatsapp": public_url},
        }
    archive_path = _archive_vehicle_bundle(db, vehicle=vehicle, document_row=document_row)
    released = release_vehicle_owner_assignment(db, vehicle=vehicle, owner=current_user)
    if not released:
        raise HTTPException(status_code=409, detail="Aktivní vlastnická vazba už byla ukončena.")
    vehicle.status = "archived"
    event = VehicleRemovalEvent(
        vehicle_id=int(vehicle.id),
        initiated_by_user_id=int(current_user.id),
        reason_code=reason,
        required_followup_answer_json=json.dumps(payload.followup_answer, ensure_ascii=False, default=str),
        digital_report_document_id=int(document_row.id),
        archive_bundle_path=archive_path,
        transfer_token_id=int(transfer_row.id) if transfer_row else None,
    )
    db.add(event)
    db.flush()
    write_global_audit_log(
        db,
        entity_type="vehicle_removal_event",
        entity_id=int(event.id),
        action="vehicle_removed_archived",
        actor_type="user",
        actor_user_id=int(current_user.id),
        actor_role=getattr(current_user, "role", None),
        tenant_id=int(vehicle.tenant_id),
        vehicle_id=int(vehicle.id),
        metadata={
            "reason_code": reason,
            "archive_bundle_path": archive_path,
            "digital_report_document_id": int(document_row.id),
            "transfer_token_id": int(transfer_row.id) if transfer_row else None,
        },
    )
    db.commit()
    return {
        "removed": True,
        "vehicle_id": int(vehicle.id),
        "reason_code": reason,
        "digital_report_document_id": int(document_row.id),
        "digital_report_document_uid": document_row.document_id,
        "digital_report_url": f"/api/v1/vehicles/{int(vehicle.id)}/digital-report?document_id={document_row.document_id}",
        "archive_bundle_path": archive_path,
        "transfer": transfer_payload,
        "history_preserved": True,
    }


@router.get("/{vehicle_id}/digital-report")
def get_vehicle_digital_report(
    vehicle_id: int,
    document_id: Optional[str] = None,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    vehicle = db.query(Vehicle).filter(Vehicle.id == int(vehicle_id)).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nebylo nalezeno.")
    can_access_report = user_owns_vehicle(db, current_user, vehicle)
    existing_document = None
    if document_id:
        existing_document = (
            db.query(VehicleReportDocument)
            .filter(
                VehicleReportDocument.vehicle_id == int(vehicle.id),
                VehicleReportDocument.document_id == str(document_id),
            )
            .first()
        )
        if not existing_document:
            raise HTTPException(status_code=404, detail="Digitální výpis nebyl nalezen.")
        removal_event = (
            db.query(VehicleRemovalEvent.id)
            .filter(
                VehicleRemovalEvent.vehicle_id == int(vehicle.id),
                VehicleRemovalEvent.digital_report_document_id == int(existing_document.id),
                VehicleRemovalEvent.initiated_by_user_id == int(current_user.id),
            )
            .first()
        )
        if removal_event is not None:
            can_access_report = True
    if not can_access_report:
        raise HTTPException(status_code=403, detail="Digitální výpis může stáhnout aktuální vlastník/správce vozidla.")
    if existing_document is not None:
        report_path = REPORT_ROOT / f"vehicle-{int(vehicle.id)}-report-{existing_document.document_id}.pdf"
        if not report_path.exists():
            raise HTTPException(status_code=404, detail="PDF digitálního výpisu nebylo nalezeno v úložišti.")
        pdf_content = report_path.read_bytes()
        filename = f"vypis-vozidla-{int(vehicle.id)}-{existing_document.document_id}.pdf"
        return Response(content=pdf_content, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{filename}"'})
    document_row, pdf_content = _generate_vehicle_report(db, vehicle=vehicle, current_user=current_user)
    db.commit()
    filename = f"vypis-vozidla-{int(vehicle.id)}-{document_row.document_id}.pdf"
    return Response(content=pdf_content, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{filename}"'})


@router.post("/claim-by-transfer")
def claim_vehicle_by_transfer(
    payload: ClaimByTransferRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    token_row = db.query(VehicleTransferToken).filter(VehicleTransferToken.token_hash == _token_hash(payload.token)).first()
    if not token_row:
        raise HTTPException(status_code=404, detail="Předávací token nebyl nalezen.")
    if token_row.status != "active" or token_row.expires_at < datetime.utcnow():
        if token_row.status == "active":
            token_row.status = "expired"
            db.commit()
        raise HTTPException(status_code=409, detail="Předávací token už není aktivní.")
    vehicle = db.query(Vehicle).filter(Vehicle.id == int(token_row.vehicle_id)).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo k tokenu nebylo nalezeno.")
    if _normalize_spz(payload.spz) != _normalize_spz(vehicle.plate) or _normalize_vin(payload.vin) != _normalize_vin(vehicle.vin):
        write_global_audit_log(
            db,
            entity_type="vehicle_transfer_token",
            entity_id=int(token_row.id),
            action="transfer_token_claim_rejected",
            actor_type="user",
            actor_user_id=int(current_user.id),
            actor_role=getattr(current_user, "role", None),
            tenant_id=getattr(current_user, "tenant_id", None),
            vehicle_id=int(vehicle.id),
            metadata={"reason": "vin_or_spz_mismatch"},
        )
        db.commit()
        raise HTTPException(status_code=409, detail="VIN nebo SPZ nesouhlasí s předávaným vozidlem.")
    transfer_vehicle_to_new_owner(
        db,
        vehicle=vehicle,
        new_owner=current_user,
        assigned_by_customer_id=int(token_row.issued_by_user_id),
        ownership_origin="transfer_token_claim",
    )
    token_row.status = "claimed"
    token_row.claimed_by_user_id = int(current_user.id)
    token_row.claimed_at = datetime.utcnow()
    vehicle.status = "active"
    write_global_audit_log(
        db,
        entity_type="vehicle_transfer_token",
        entity_id=int(token_row.id),
        action="transfer_token_claimed",
        actor_type="user",
        actor_user_id=int(current_user.id),
        actor_role=getattr(current_user, "role", None),
        tenant_id=getattr(current_user, "tenant_id", None),
        vehicle_id=int(vehicle.id),
        metadata={"issued_by_user_id": int(token_row.issued_by_user_id)},
    )
    db.commit()
    return {"claimed": True, "vehicle_id": int(vehicle.id), "history_preserved": True}
