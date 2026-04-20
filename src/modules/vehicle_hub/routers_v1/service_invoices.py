"""
Servisní faktury (Fáze 1): draft / issued / cancelled, číslování při vystavení, PDF, audit.
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
from ..models import (
    Customer,
    ServiceCustomerLink,
    ServiceInvoice,
    ServiceInvoiceCounter,
    ServiceInvoiceLine,
    Vehicle as VehicleModel,
)
from ..reports.service_invoice_pdf import render_service_invoice_pdf
from ..schema_management import assert_module_ready
from .auth import get_current_user
from .service_dashboard import _resolve_owner_and_vehicle

router = APIRouter(prefix="/api/service", tags=["service-invoices"])


def _require_service_invoice_role(current_user: Customer) -> None:
    role = str(getattr(current_user, "role", "") or "").lower()
    if role != "service":
        raise HTTPException(status_code=403, detail="Faktury může spravovat pouze servisní účet.")


def _ensure_service_invoices_schema(db: Session) -> None:
    assert_module_ready(db, "service_invoices", detail_prefix="Servisní faktury nejsou připraveny")
    assert_module_ready(db, "service_workspace", detail_prefix="Servisní propojení není připravené")


def _ensure_invoice_customer(db: Session, *, current_user: Customer, customer_id: int) -> Customer:
    owner = db.query(Customer).filter(Customer.id == int(customer_id)).first()
    if not owner:
        raise HTTPException(status_code=404, detail="Zákazník nebyl nalezen.")
    link = (
        db.query(ServiceCustomerLink.id)
        .filter(
            ServiceCustomerLink.service_customer_id == current_user.id,
            ServiceCustomerLink.customer_id == owner.id,
            ServiceCustomerLink.status == "active",
        )
        .first()
    )
    if not link:
        raise HTTPException(status_code=403, detail="Servis nemá vazbu na tohoto zákazníka.")
    return owner


def _ensure_invoice_party(
    db: Session,
    *,
    current_user: Customer,
    customer_id: int,
    vehicle_id: Optional[int],
) -> tuple[Customer, Optional[VehicleModel]]:
    owner = _ensure_invoice_customer(db, current_user=current_user, customer_id=customer_id)
    if vehicle_id is None:
        return owner, None
    o2, vehicle = _resolve_owner_and_vehicle(
        db,
        current_user=current_user,
        owner_id=int(owner.id),
        vehicle_id=int(vehicle_id),
    )
    return o2, vehicle


def _compute_line_amounts(*, quantity: float, unit_price: float, tax_rate: float) -> tuple[float, float, float]:
    net = round(float(quantity) * float(unit_price), 2)
    tax = round(net * (float(tax_rate) / 100.0), 2)
    gross = round(net + tax, 2)
    return net, tax, gross


def _build_lines_from_payload(
    db: Session,
    *,
    tenant_id: int,
    invoice_id: int,
    items: list["ServiceInvoiceLineIn"],
) -> tuple[list[ServiceInvoiceLine], float, float, float]:
    subtotal = 0.0
    tax_total = 0.0
    total = 0.0
    rows: list[ServiceInvoiceLine] = []
    for idx, item in enumerate(items):
        net, tax, gross = _compute_line_amounts(
            quantity=item.quantity,
            unit_price=item.unit_price,
            tax_rate=item.tax_rate,
        )
        subtotal += net
        tax_total += tax
        total += gross
        rows.append(
            ServiceInvoiceLine(
                tenant_id=int(tenant_id),
                invoice_id=int(invoice_id),
                description=str(item.description or "").strip() or "Položka",
                quantity=float(item.quantity),
                unit=str(item.unit or "ks").strip()[:32] or "ks",
                unit_price=float(item.unit_price),
                tax_rate=float(item.tax_rate),
                line_total=gross,
                sort_order=idx,
            )
        )
    subtotal = round(subtotal, 2)
    tax_total = round(tax_total, 2)
    total = round(total, 2)
    return rows, subtotal, tax_total, total


def _allocate_invoice_number(db: Session, *, tenant_id: int) -> str:
    row = db.query(ServiceInvoiceCounter).filter(ServiceInvoiceCounter.tenant_id == int(tenant_id)).first()
    if row is None:
        row = ServiceInvoiceCounter(tenant_id=int(tenant_id), next_seq=1)
        db.add(row)
        db.flush()
    seq = int(row.next_seq)
    row.next_seq = seq + 1
    db.flush()
    year = datetime.utcnow().year
    return f"FV-{year}-{seq:06d}"


def _get_invoice_for_service(
    db: Session,
    *,
    current_user: Customer,
    invoice_id: int,
) -> ServiceInvoice:
    inv = (
        db.query(ServiceInvoice)
        .filter(
            ServiceInvoice.id == int(invoice_id),
            ServiceInvoice.service_id == int(current_user.id),
            ServiceInvoice.tenant_id == int(current_user.tenant_id),
        )
        .first()
    )
    if not inv:
        raise HTTPException(status_code=404, detail="Faktura nebyla nalezena.")
    return inv


def _serialize_line(line: ServiceInvoiceLine) -> dict[str, Any]:
    return {
        "id": int(line.id),
        "description": line.description,
        "quantity": line.quantity,
        "unit": line.unit,
        "unit_price": line.unit_price,
        "tax_rate": line.tax_rate,
        "line_total": line.line_total,
        "sort_order": line.sort_order,
    }


def _serialize_invoice(
    inv: ServiceInvoice,
    lines: list[ServiceInvoiceLine],
    *,
    include_lines: bool = True,
    customer_label: Optional[str] = None,
    vehicle_label: Optional[str] = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "id": int(inv.id),
        "tenant_id": int(inv.tenant_id),
        "service_id": int(inv.service_id),
        "customer_id": int(inv.customer_id),
        "vehicle_id": int(inv.vehicle_id) if inv.vehicle_id is not None else None,
        "invoice_number": inv.invoice_number,
        "status": inv.status,
        "status_label": _status_label(str(inv.status or "")),
        "subtotal": inv.subtotal,
        "tax_total": inv.tax_total,
        "total": inv.total,
        "currency": inv.currency,
        "issued_at": inv.issued_at.isoformat() if inv.issued_at else None,
        "due_at": inv.due_at.isoformat() if inv.due_at else None,
        "cancelled_at": inv.cancelled_at.isoformat() if inv.cancelled_at else None,
        "notes": inv.notes,
        "created_at": inv.created_at.isoformat() if inv.created_at else None,
        "updated_at": inv.updated_at.isoformat() if inv.updated_at else None,
        "customer_label": customer_label,
        "vehicle_label": vehicle_label,
    }
    if include_lines:
        body["lines"] = [_serialize_line(ln) for ln in sorted(lines, key=lambda x: (x.sort_order, x.id))]
    return body


def _resolve_invoice_labels(db: Session, *, inv: ServiceInvoice) -> tuple[Optional[str], Optional[str]]:
    customer = db.query(Customer).filter(Customer.id == int(inv.customer_id)).first()
    vehicle = (
        db.query(VehicleModel).filter(VehicleModel.id == int(inv.vehicle_id)).first()
        if inv.vehicle_id is not None
        else None
    )
    customer_label = (customer.name or customer.email) if customer else None
    vehicle_label = None
    if vehicle:
        vehicle_label = " ".join(
            part for part in [getattr(vehicle, "brand", None), getattr(vehicle, "model", None)] if part
        ).strip() or getattr(vehicle, "nickname", None) or getattr(vehicle, "plate", None) or getattr(vehicle, "vin", None)
    return customer_label, vehicle_label


def _audit(
    db: Session,
    *,
    invoice: ServiceInvoice,
    action: str,
    actor: Customer,
    metadata: Optional[dict[str, Any]] = None,
) -> None:
    write_global_audit_log(
        db,
        entity_type="service_invoice",
        entity_id=int(invoice.id),
        action=action,
        actor_user_id=int(actor.id),
        actor_role=str(getattr(actor, "role", None) or ""),
        tenant_id=int(invoice.tenant_id),
        metadata=metadata or {},
    )


class ServiceInvoiceLineIn(BaseModel):
    description: str = Field(..., min_length=1, max_length=512)
    quantity: float = Field(default=1, gt=0)
    unit: str = Field(default="ks", max_length=32)
    unit_price: float = Field(default=0, ge=0)
    tax_rate: float = Field(default=0, ge=0, le=100)


class ServiceInvoiceCreateRequest(BaseModel):
    customer_id: int = Field(gt=0)
    vehicle_id: Optional[int] = Field(default=None, gt=0)
    currency: str = Field(default="CZK", max_length=8)
    due_at: Optional[datetime] = None
    notes: Optional[str] = Field(default=None, max_length=8000)
    lines: list[ServiceInvoiceLineIn] = Field(default_factory=list)


class ServiceInvoiceUpdateRequest(BaseModel):
    customer_id: Optional[int] = Field(default=None, gt=0)
    vehicle_id: Optional[int] = None
    currency: Optional[str] = Field(default=None, max_length=8)
    due_at: Optional[datetime] = None
    notes: Optional[str] = Field(default=None, max_length=8000)
    lines: Optional[list[ServiceInvoiceLineIn]] = None


def _status_label(status: str) -> str:
    return {"draft": "Koncept", "issued": "Vystaveno", "cancelled": "Zrušeno"}.get(
        str(status or "").lower(),
        str(status or ""),
    )


def _pdf_payload(
    db: Session,
    *,
    invoice: ServiceInvoice,
    lines: list[ServiceInvoiceLine],
    service_customer: Customer,
) -> dict[str, Any]:
    customer = db.query(Customer).filter(Customer.id == int(invoice.customer_id)).first()
    vehicle = (
        db.query(VehicleModel).filter(VehicleModel.id == int(invoice.vehicle_id)).first()
        if invoice.vehicle_id
        else None
    )
    vehicle_label = None
    if vehicle:
        vehicle_label = " ".join(
            p for p in [getattr(vehicle, "brand", None), getattr(vehicle, "model", None)] if p
        ).strip() or getattr(vehicle, "nickname", None) or getattr(vehicle, "plate", None)

    doc_status = "KONCEPT — nečíslovaný náhled" if str(invoice.status) == "draft" else "Vystavený doklad"
    if str(invoice.status) == "cancelled":
        doc_status = "Zrušený doklad"

    return {
        "id": int(invoice.id),
        "invoice_number": invoice.invoice_number,
        "status": invoice.status,
        "status_label": _status_label(str(invoice.status or "")),
        "document_status_label": doc_status,
        "service_name": service_customer.name or service_customer.email,
        "service_ico": getattr(service_customer, "ico", None),
        "issued_at_label": invoice.issued_at.strftime("%d.%m.%Y %H:%M") if invoice.issued_at else "-",
        "due_at_label": invoice.due_at.strftime("%d.%m.%Y %H:%M") if invoice.due_at else "-",
        "customer_label": (customer.name or customer.email) if customer else "-",
        "vehicle_label": vehicle_label,
        "currency": invoice.currency or "CZK",
        "subtotal": invoice.subtotal,
        "tax_total": invoice.tax_total,
        "total": invoice.total,
        "notes": invoice.notes,
        "lines": [_serialize_line(ln) for ln in sorted(lines, key=lambda x: (x.sort_order, x.id))],
    }


@router.get("/invoices")
def list_service_invoices(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_invoice_role(current_user)
    _ensure_service_invoices_schema(db)

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
        customer_label, vehicle_label = _resolve_invoice_labels(db, inv=inv)
        items.append(
            _serialize_invoice(
                inv,
                [],
                include_lines=False,
                customer_label=customer_label,
                vehicle_label=vehicle_label,
            )
        )
    return {"items": items}


@router.post("/invoices", status_code=201)
def create_service_invoice(
    payload: ServiceInvoiceCreateRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_invoice_role(current_user)
    _ensure_service_invoices_schema(db)

    _ensure_invoice_party(
        db,
        current_user=current_user,
        customer_id=int(payload.customer_id),
        vehicle_id=payload.vehicle_id,
    )

    inv = ServiceInvoice(
        tenant_id=int(current_user.tenant_id),
        service_id=int(current_user.id),
        customer_id=int(payload.customer_id),
        vehicle_id=int(payload.vehicle_id) if payload.vehicle_id else None,
        status="draft",
        subtotal=0,
        tax_total=0,
        total=0,
        currency=str(payload.currency or "CZK").strip()[:8] or "CZK",
        due_at=payload.due_at,
        notes=(str(payload.notes).strip() if payload.notes else None),
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

    _audit(db, invoice=inv, action="invoice_created", actor=current_user, metadata={"customer_id": inv.customer_id})
    db.commit()
    db.refresh(inv)
    lines = (
        db.query(ServiceInvoiceLine)
        .filter(ServiceInvoiceLine.invoice_id == int(inv.id))
        .order_by(ServiceInvoiceLine.sort_order, ServiceInvoiceLine.id)
        .all()
    )
    customer_label, vehicle_label = _resolve_invoice_labels(db, inv=inv)
    return _serialize_invoice(inv, lines, customer_label=customer_label, vehicle_label=vehicle_label)


@router.get("/invoices/{invoice_id}")
def get_service_invoice(
    invoice_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_invoice_role(current_user)
    _ensure_service_invoices_schema(db)

    inv = _get_invoice_for_service(db, current_user=current_user, invoice_id=invoice_id)
    lines = (
        db.query(ServiceInvoiceLine)
        .filter(ServiceInvoiceLine.invoice_id == int(inv.id))
        .order_by(ServiceInvoiceLine.sort_order, ServiceInvoiceLine.id)
        .all()
    )
    customer_label, vehicle_label = _resolve_invoice_labels(db, inv=inv)
    return _serialize_invoice(inv, lines, customer_label=customer_label, vehicle_label=vehicle_label)


@router.put("/invoices/{invoice_id}")
def update_service_invoice(
    invoice_id: int,
    payload: ServiceInvoiceUpdateRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_invoice_role(current_user)
    _ensure_service_invoices_schema(db)

    inv = _get_invoice_for_service(db, current_user=current_user, invoice_id=invoice_id)
    if str(inv.status) != "draft":
        raise HTTPException(status_code=409, detail="Upravit lze pouze fakturu ve stavu koncept.")

    fields_set = set(getattr(payload, "model_fields_set", set()) or set())

    if "customer_id" in fields_set:
        if payload.customer_id is None:
            raise HTTPException(status_code=422, detail="customer_id je povinný.")
        cust_id = int(payload.customer_id)
    else:
        cust_id = int(inv.customer_id)

    if "vehicle_id" in fields_set:
        veh_id = payload.vehicle_id
    else:
        veh_id = int(inv.vehicle_id) if inv.vehicle_id is not None else None

    _ensure_invoice_party(db, current_user=current_user, customer_id=cust_id, vehicle_id=veh_id)

    if "customer_id" in fields_set:
        inv.customer_id = cust_id
    if "vehicle_id" in fields_set:
        inv.vehicle_id = int(payload.vehicle_id) if payload.vehicle_id else None
    if "currency" in fields_set and payload.currency is not None:
        inv.currency = str(payload.currency).strip()[:8] or "CZK"
    if "due_at" in fields_set:
        inv.due_at = payload.due_at
    if "notes" in fields_set:
        inv.notes = str(payload.notes).strip() if payload.notes else None

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
    _audit(db, invoice=inv, action="invoice_updated", actor=current_user)
    db.commit()
    db.refresh(inv)
    lines = (
        db.query(ServiceInvoiceLine)
        .filter(ServiceInvoiceLine.invoice_id == int(inv.id))
        .order_by(ServiceInvoiceLine.sort_order, ServiceInvoiceLine.id)
        .all()
    )
    customer_label, vehicle_label = _resolve_invoice_labels(db, inv=inv)
    return _serialize_invoice(inv, lines, customer_label=customer_label, vehicle_label=vehicle_label)


@router.post("/invoices/{invoice_id}/issue")
def issue_service_invoice(
    invoice_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_invoice_role(current_user)
    _ensure_service_invoices_schema(db)

    inv = _get_invoice_for_service(db, current_user=current_user, invoice_id=invoice_id)
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

    inv.invoice_number = _allocate_invoice_number(db, tenant_id=int(inv.tenant_id))
    inv.status = "issued"
    inv.issued_at = datetime.utcnow()
    db.flush()
    _audit(
        db,
        invoice=inv,
        action="invoice_issued",
        actor=current_user,
        metadata={"invoice_number": inv.invoice_number},
    )
    db.commit()
    db.refresh(inv)
    customer_label, vehicle_label = _resolve_invoice_labels(db, inv=inv)
    return _serialize_invoice(inv, lines, customer_label=customer_label, vehicle_label=vehicle_label)


@router.post("/invoices/{invoice_id}/cancel")
def cancel_service_invoice(
    invoice_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_invoice_role(current_user)
    _ensure_service_invoices_schema(db)

    inv = _get_invoice_for_service(db, current_user=current_user, invoice_id=invoice_id)
    if str(inv.status) == "cancelled":
        raise HTTPException(status_code=409, detail="Faktura je již zrušena.")

    inv.status = "cancelled"
    inv.cancelled_at = datetime.utcnow()
    db.flush()
    _audit(db, invoice=inv, action="invoice_cancelled", actor=current_user)
    db.commit()
    db.refresh(inv)
    lines = (
        db.query(ServiceInvoiceLine)
        .filter(ServiceInvoiceLine.invoice_id == int(inv.id))
        .order_by(ServiceInvoiceLine.sort_order, ServiceInvoiceLine.id)
        .all()
    )
    customer_label, vehicle_label = _resolve_invoice_labels(db, inv=inv)
    return _serialize_invoice(inv, lines, customer_label=customer_label, vehicle_label=vehicle_label)


@router.get("/invoices/{invoice_id}/pdf")
def get_service_invoice_pdf(
    invoice_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_invoice_role(current_user)
    _ensure_service_invoices_schema(db)

    inv = _get_invoice_for_service(db, current_user=current_user, invoice_id=invoice_id)
    lines = (
        db.query(ServiceInvoiceLine)
        .filter(ServiceInvoiceLine.invoice_id == int(inv.id))
        .order_by(ServiceInvoiceLine.sort_order, ServiceInvoiceLine.id)
        .all()
    )
    pdf_bytes = render_service_invoice_pdf(_pdf_payload(db, invoice=inv, lines=lines, service_customer=current_user))
    _audit(
        db,
        invoice=inv,
        action="invoice_pdf_exported",
        actor=current_user,
        metadata={"invoice_number": inv.invoice_number, "status": inv.status},
    )
    db.commit()
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="service-invoice-{int(inv.id)}.pdf"'},
    )
