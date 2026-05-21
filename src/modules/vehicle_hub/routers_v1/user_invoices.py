"""
Uživatelské faktury — podnikatelé s IČO vystavují faktury z uživatelského rozhraní.
Používá stejnou tabulku service_invoices; vystavitel = service_id, příjemce v extra_json.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..audit_log import write_global_audit_log
from ..database import get_db
from ..models import Customer, ServiceInvoice, ServiceInvoiceLine, Vehicle as VehicleModel
from ..schema_management import assert_module_ready
from .auth import get_current_user
from .service_invoices import (
    ServiceInvoiceLineIn,
    _allocate_invoice_number,
    _audit,
    _build_lines_from_payload,
    _get_invoice_for_service,
    _invoice_extra_json,
    _parse_invoice_datetime,
    _parse_invoice_extra,
    _resolve_invoice_labels,
    _serialize_invoice,
    render_internal_service_invoice_pdf,
)
from .vehicles import _require_user_account, _user_owned_vehicle_ids

router = APIRouter(prefix="/user/invoices", tags=["user-invoices"])

USER_ISSUED_FLAG = "user_issued_invoice"


def _ensure_user_invoices_schema(db: Session) -> None:
    assert_module_ready(db, "service_invoices", detail_prefix="Fakturace není připravená")


def _require_user_invoice_eligible(current_user: Customer) -> None:
    _require_user_account(current_user)
    ico = str(getattr(current_user, "ico", None) or "").strip()
    name = str(getattr(current_user, "name", None) or "").strip()
    if not ico:
        raise HTTPException(
            status_code=403,
            detail="Vystavovat faktury mohou uživatelé s vyplněným IČO v profilu účtu.",
        )
    if not name:
        raise HTTPException(
            status_code=403,
            detail="Doplňte název firmy nebo jméno v profilu účtu před vystavením faktury.",
        )


def _is_user_issued_invoice(inv: ServiceInvoice) -> bool:
    extra = _parse_invoice_extra(inv.extra_json)
    return bool(extra.get(USER_ISSUED_FLAG))


def _get_user_issued_invoice(
    db: Session,
    *,
    current_user: Customer,
    invoice_id: int,
) -> ServiceInvoice:
    inv = _get_invoice_for_service(db, current_user=current_user, invoice_id=invoice_id)
    if not _is_user_issued_invoice(inv):
        raise HTTPException(status_code=404, detail="Faktura nebyla nalezena.")
    return inv


def _recipient_label(inv: ServiceInvoice) -> Optional[str]:
    extra = _parse_invoice_extra(inv.extra_json)
    label = str(extra.get("customer_name") or "").strip()
    return label or None


def _serialize_user_issued_invoice(
    db: Session,
    inv: ServiceInvoice,
    lines: list[ServiceInvoiceLine],
    *,
    include_lines: bool = True,
) -> dict[str, Any]:
    customer_label, vehicle_label = _resolve_invoice_labels(db, inv=inv)
    recipient = _recipient_label(inv)
    if recipient:
        customer_label = recipient
    body = _serialize_invoice(
        inv,
        lines,
        include_lines=include_lines,
        customer_label=customer_label,
        vehicle_label=vehicle_label,
    )
    body["direction"] = "issued"
    body["user_issued"] = True
    return body


def _default_supplier_extra(user: Customer) -> dict[str, Any]:
    street = " ".join(
        part for part in [getattr(user, "street", None), getattr(user, "street_number", None)] if part
    ).strip()
    return {
        "supplier_name": user.name or user.email or "",
        "supplier_ico": str(user.ico or "").strip(),
        "supplier_dic": str(user.dic or "").strip(),
        "supplier_street": street,
        "supplier_city": str(getattr(user, "city", None) or "").strip(),
        "supplier_zip": str(getattr(user, "zip", None) or "").strip(),
        "supplier_email": str(user.email or "").strip(),
        "supplier_phone": str(getattr(user, "phone", None) or "").strip(),
        "supplier_state": "Česká republika",
    }


def _merge_supplier_defaults(extra: dict[str, Any], user: Customer) -> dict[str, Any]:
    merged = dict(extra or {})
    defaults = _default_supplier_extra(user)
    for key, value in defaults.items():
        if not str(merged.get(key) or "").strip() and value:
            merged[key] = value
    return merged


def _validate_user_vehicle(
    db: Session,
    *,
    current_user: Customer,
    vehicle_id: Optional[int],
) -> None:
    if vehicle_id is None:
        return
    owned = _user_owned_vehicle_ids(db, current_user=current_user)
    if int(vehicle_id) not in owned:
        raise HTTPException(status_code=403, detail="Fakturu lze vázat pouze na vaše vozidlo.")


def _assert_recipient_extra(extra: dict[str, Any]) -> None:
    if not str(extra.get("customer_name") or "").strip():
        raise HTTPException(status_code=422, detail="Vyplňte název odběratele faktury.")


class UserInvoiceCreateRequest(BaseModel):
    vehicle_id: Optional[int] = Field(default=None, gt=0)
    non_vehicle_invoice: bool = Field(default=True)
    currency: str = Field(default="CZK", max_length=8)
    due_at: Optional[datetime] = None
    notes: Optional[str] = Field(default=None, max_length=8000)
    extra: dict[str, Any] = Field(default_factory=dict)
    lines: list[ServiceInvoiceLineIn] = Field(default_factory=list)


class UserInvoiceUpdateRequest(BaseModel):
    vehicle_id: Optional[int] = None
    currency: Optional[str] = Field(default=None, max_length=8)
    due_at: Optional[datetime] = None
    notes: Optional[str] = Field(default=None, max_length=8000)
    extra: Optional[dict[str, Any]] = None
    lines: Optional[list[ServiceInvoiceLineIn]] = None


@router.get("/eligibility")
def user_invoice_eligibility(
    current_user: Customer = Depends(get_current_user),
):
    _require_user_account(current_user)
    ico = str(getattr(current_user, "ico", None) or "").strip()
    name = str(getattr(current_user, "name", None) or "").strip()
    return {
        "eligible": bool(ico and name),
        "has_ico": bool(ico),
        "has_name": bool(name),
        "ico": ico or None,
        "message": (
            None
            if ico and name
            else "Pro vystavování faktur doplňte IČO a název firmy v nastavení profilu."
        ),
    }


@router.get("")
def list_user_issued_invoices(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_user_account(current_user)
    _ensure_user_invoices_schema(db)

    rows = (
        db.query(ServiceInvoice)
        .filter(
            ServiceInvoice.service_id == int(current_user.id),
            ServiceInvoice.tenant_id == int(current_user.tenant_id),
        )
        .order_by(ServiceInvoice.created_at.desc(), ServiceInvoice.id.desc())
        .limit(250)
        .all()
    )
    items: list[dict[str, Any]] = []
    for inv in rows:
        if not _is_user_issued_invoice(inv):
            continue
        items.append(_serialize_user_issued_invoice(db, inv, [], include_lines=False))
    return {"items": items}


@router.post("", status_code=201)
def create_user_invoice(
    payload: UserInvoiceCreateRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_user_invoice_eligible(current_user)
    _ensure_user_invoices_schema(db)

    if payload.non_vehicle_invoice:
        if payload.vehicle_id is not None:
            raise HTTPException(status_code=422, detail="U faktury bez vozidla ponechte vehicle_id prázdné.")
        vehicle_id_val = None
    else:
        if not payload.vehicle_id:
            raise HTTPException(status_code=422, detail="Vyberte vozidlo nebo zvolte fakturu bez vozidla.")
        _validate_user_vehicle(db, current_user=current_user, vehicle_id=int(payload.vehicle_id))
        vehicle_id_val = int(payload.vehicle_id)

    extra_in = _merge_supplier_defaults(dict(payload.extra or {}), current_user)
    extra_in[USER_ISSUED_FLAG] = True
    if payload.non_vehicle_invoice:
        extra_in["manual_non_vehicle_invoice"] = True
    _assert_recipient_extra(extra_in)

    inv = ServiceInvoice(
        tenant_id=int(current_user.tenant_id),
        service_id=int(current_user.id),
        customer_id=int(current_user.id),
        vehicle_id=vehicle_id_val,
        service_record_id=None,
        work_order_id=None,
        status="draft",
        subtotal=0,
        tax_total=0,
        total=0,
        currency=str(payload.currency or "CZK").strip()[:8] or "CZK",
        due_at=payload.due_at,
        notes=(str(payload.notes).strip() if payload.notes else None),
        extra_json=_invoice_extra_json(extra_in),
    )
    db.add(inv)
    db.flush()

    line_rows, sub, tax, tot = _build_lines_from_payload(
        db,
        tenant_id=int(current_user.tenant_id),
        invoice_id=int(inv.id),
        items=payload.lines,
    )
    for lr in line_rows:
        db.add(lr)
    inv.subtotal = sub
    inv.tax_total = tax
    inv.total = tot
    db.flush()

    _audit(
        db,
        invoice=inv,
        action="user_invoice_created",
        actor=current_user,
        metadata={"vehicle_id": vehicle_id_val, "non_vehicle": bool(payload.non_vehicle_invoice)},
    )
    db.commit()
    db.refresh(inv)
    lines = (
        db.query(ServiceInvoiceLine)
        .filter(ServiceInvoiceLine.invoice_id == int(inv.id))
        .order_by(ServiceInvoiceLine.sort_order, ServiceInvoiceLine.id)
        .all()
    )
    return _serialize_user_issued_invoice(db, inv, lines)


@router.get("/{invoice_id}")
def get_user_invoice(
    invoice_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_user_account(current_user)
    _ensure_user_invoices_schema(db)
    inv = _get_user_issued_invoice(db, current_user=current_user, invoice_id=invoice_id)
    lines = (
        db.query(ServiceInvoiceLine)
        .filter(ServiceInvoiceLine.invoice_id == int(inv.id))
        .order_by(ServiceInvoiceLine.sort_order, ServiceInvoiceLine.id)
        .all()
    )
    return _serialize_user_issued_invoice(db, inv, lines)


@router.put("/{invoice_id}")
def update_user_invoice(
    invoice_id: int,
    payload: UserInvoiceUpdateRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_user_invoice_eligible(current_user)
    _ensure_user_invoices_schema(db)

    inv = _get_user_issued_invoice(db, current_user=current_user, invoice_id=invoice_id)
    if str(inv.status) != "draft":
        raise HTTPException(status_code=409, detail="Upravit lze pouze fakturu ve stavu koncept.")

    fields_set = set(getattr(payload, "model_fields_set", set()) or set())

    if "vehicle_id" in fields_set:
        veh_id = payload.vehicle_id
        if veh_id is not None:
            _validate_user_vehicle(db, current_user=current_user, vehicle_id=int(veh_id))
            inv.vehicle_id = int(veh_id)
            merged = _parse_invoice_extra(inv.extra_json)
            merged.pop("manual_non_vehicle_invoice", None)
            merged[USER_ISSUED_FLAG] = True
            inv.extra_json = _invoice_extra_json(merged)
        else:
            inv.vehicle_id = None
            merged = _parse_invoice_extra(inv.extra_json)
            merged["manual_non_vehicle_invoice"] = True
            merged[USER_ISSUED_FLAG] = True
            inv.extra_json = _invoice_extra_json(merged)

    if "currency" in fields_set and payload.currency is not None:
        inv.currency = str(payload.currency).strip()[:8] or "CZK"
    if "due_at" in fields_set:
        inv.due_at = payload.due_at
    if "notes" in fields_set:
        inv.notes = str(payload.notes).strip() if payload.notes else None
    if "extra" in fields_set:
        merged = _merge_supplier_defaults(dict(payload.extra or {}), current_user)
        merged[USER_ISSUED_FLAG] = True
        _assert_recipient_extra(merged)
        inv.extra_json = _invoice_extra_json(merged)

    if "lines" in fields_set and payload.lines is not None:
        db.query(ServiceInvoiceLine).filter(ServiceInvoiceLine.invoice_id == int(inv.id)).delete(
            synchronize_session=False
        )
        line_rows, sub, tax, tot = _build_lines_from_payload(
            db,
            tenant_id=int(inv.tenant_id),
            invoice_id=int(inv.id),
            items=payload.lines,
        )
        for lr in line_rows:
            db.add(lr)
        inv.subtotal = sub
        inv.tax_total = tax
        inv.total = tot

    db.flush()
    _audit(db, invoice=inv, action="user_invoice_updated", actor=current_user)
    db.commit()
    db.refresh(inv)
    lines = (
        db.query(ServiceInvoiceLine)
        .filter(ServiceInvoiceLine.invoice_id == int(inv.id))
        .order_by(ServiceInvoiceLine.sort_order, ServiceInvoiceLine.id)
        .all()
    )
    return _serialize_user_issued_invoice(db, inv, lines)


@router.post("/{invoice_id}/issue")
def issue_user_invoice(
    invoice_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_user_invoice_eligible(current_user)
    _ensure_user_invoices_schema(db)

    inv = _get_user_issued_invoice(db, current_user=current_user, invoice_id=invoice_id)
    if str(inv.status) != "draft":
        raise HTTPException(status_code=409, detail="Vystavit lze pouze koncept faktury.")

    lines = (
        db.query(ServiceInvoiceLine)
        .filter(ServiceInvoiceLine.invoice_id == int(inv.id))
        .order_by(ServiceInvoiceLine.sort_order, ServiceInvoiceLine.id)
        .all()
    )
    if not lines:
        raise HTTPException(status_code=422, detail="Faktura musí obsahovat alespoň jednu položku.")

    extra = _merge_supplier_defaults(_parse_invoice_extra(inv.extra_json), current_user)
    if not str(extra.get("supplier_ico") or "").strip():
        raise HTTPException(status_code=422, detail="Dodavatel musí mít vyplněné IČO.")
    _assert_recipient_extra(extra)
    inv.extra_json = _invoice_extra_json(extra)

    inv.invoice_number = _allocate_invoice_number(db, tenant_id=int(inv.tenant_id))
    inv.status = "issued"
    if not str(extra.get("variable_symbol") or "").strip() and inv.invoice_number:
        digits = "".join(ch for ch in str(inv.invoice_number) if ch.isdigit())
        if digits:
            extra["variable_symbol"] = digits[-10:]
            inv.extra_json = _invoice_extra_json(extra)
    inv.issued_at = _parse_invoice_datetime(extra.get("issue_date"))
    db.flush()
    _audit(
        db,
        invoice=inv,
        action="user_invoice_issued",
        actor=current_user,
        metadata={"invoice_number": inv.invoice_number},
    )
    db.commit()
    db.refresh(inv)
    return _serialize_user_issued_invoice(db, inv, lines)


@router.post("/{invoice_id}/cancel")
def cancel_user_invoice(
    invoice_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_user_account(current_user)
    _ensure_user_invoices_schema(db)

    inv = _get_user_issued_invoice(db, current_user=current_user, invoice_id=invoice_id)
    if str(inv.status) == "cancelled":
        raise HTTPException(status_code=409, detail="Faktura je již zrušena.")

    inv.status = "cancelled"
    inv.cancelled_at = datetime.utcnow()
    db.flush()
    _audit(db, invoice=inv, action="user_invoice_cancelled", actor=current_user)
    db.commit()
    db.refresh(inv)
    lines = (
        db.query(ServiceInvoiceLine)
        .filter(ServiceInvoiceLine.invoice_id == int(inv.id))
        .order_by(ServiceInvoiceLine.sort_order, ServiceInvoiceLine.id)
        .all()
    )
    return _serialize_user_issued_invoice(db, inv, lines)


@router.get("/{invoice_id}/pdf")
def get_user_invoice_pdf(
    invoice_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_user_account(current_user)
    _ensure_user_invoices_schema(db)

    inv = _get_user_issued_invoice(db, current_user=current_user, invoice_id=invoice_id)
    pdf_bytes = render_internal_service_invoice_pdf(db, invoice=inv)
    write_global_audit_log(
        db,
        entity_type="service_invoice",
        entity_id=int(inv.id),
        action="user_invoice_pdf_exported",
        actor_user_id=int(current_user.id),
        actor_role=str(getattr(current_user, "role", None) or ""),
        tenant_id=int(inv.tenant_id),
        metadata={"invoice_number": inv.invoice_number, "status": inv.status},
    )
    db.commit()
    filename = f"faktura-{inv.invoice_number or inv.id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )
