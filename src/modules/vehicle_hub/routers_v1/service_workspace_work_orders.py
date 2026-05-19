"""Service workspace work-order item endpoints.

Small backend slice for service-case -> work-order conversion and server-side
labor/material/other item totals. It extends the existing ServiceWorkOrder model
instead of introducing a parallel service system.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..audit_log import write_global_audit_log
from ..database import get_db
from ..models import (
    Customer,
    ServiceCustomerLink,
    ServiceIntake,
    ServiceWorkOrder,
    ServiceWorkOrderAuditLog,
    ServiceWorkOrderItem,
    Vehicle,
)
from ..schema_management import assert_module_ready
from ..service_access import require_approved_service_vehicle_access
from .auth import get_current_user
from .service_workspace import _require_service_workspace_role


router = APIRouter(prefix="/services/workspace", tags=["service-workspace-work-orders"])

ITEM_TYPES = frozenset({"labor", "material", "other"})
ITEM_SOURCES = frozenset({"manual"})


class WorkOrderItemCreateV1(BaseModel):
    type: str = Field(..., min_length=3, max_length=32)
    name: str = Field(..., min_length=1, max_length=512)
    code: Optional[str] = Field(default=None, max_length=128)
    quantity: float = Field(default=1, gt=0)
    unit: str = Field(default="ks", min_length=1, max_length=32)
    vat_rate: float = Field(default=21, ge=0, le=100)
    purchase_price_without_vat: Optional[float] = Field(default=None, ge=0)
    sale_price_without_vat: float = Field(default=0, ge=0)
    discount_percent: float = Field(default=0, ge=0, le=100)
    mechanic_id: Optional[int] = Field(default=None, gt=0)
    source: str = Field(default="manual", min_length=3, max_length=32)


class WorkOrderItemPatchV1(BaseModel):
    type: Optional[str] = Field(default=None, min_length=3, max_length=32)
    name: Optional[str] = Field(default=None, min_length=1, max_length=512)
    code: Optional[str] = Field(default=None, max_length=128)
    quantity: Optional[float] = Field(default=None, gt=0)
    unit: Optional[str] = Field(default=None, min_length=1, max_length=32)
    vat_rate: Optional[float] = Field(default=None, ge=0, le=100)
    purchase_price_without_vat: Optional[float] = Field(default=None, ge=0)
    sale_price_without_vat: Optional[float] = Field(default=None, ge=0)
    discount_percent: Optional[float] = Field(default=None, ge=0, le=100)
    mechanic_id: Optional[int] = Field(default=None, gt=0)


class CreateWorkOrderFromIntakeV1(BaseModel):
    title: Optional[str] = Field(default=None, min_length=3, max_length=255)
    description: Optional[str] = Field(default=None, max_length=4000)
    technician_id: Optional[int] = Field(default=None, gt=0)


def _ensure_schema(db: Session) -> None:
    assert_module_ready(db, "service_workspace", detail_prefix="Servisní workspace není připraven")
    assert_module_ready(db, "service_dashboard", detail_prefix="Servisní zakázky nejsou připraveny")


def _normalize_item_type(raw: str | None) -> str:
    value = str(raw or "").strip().lower()
    if value not in ITEM_TYPES:
        raise HTTPException(status_code=422, detail="Neplatný typ položky zakázky.")
    return value


def _normalize_source(raw: str | None) -> str:
    value = str(raw or "manual").strip().lower()
    if value not in ITEM_SOURCES:
        raise HTTPException(status_code=422, detail="Neplatný zdroj položky zakázky.")
    return value


def _round_money(value: float) -> float:
    return round(float(value or 0), 2)


def _line_totals(item: ServiceWorkOrderItem) -> dict[str, float]:
    quantity = float(item.quantity or 0)
    unit_price = float(item.sale_price_without_vat or 0)
    discount = max(0.0, min(100.0, float(item.discount_percent or 0)))
    net = _round_money(quantity * unit_price * (1 - discount / 100))
    vat = _round_money(net * float(item.vat_rate or 0) / 100)
    gross = _round_money(net + vat)
    return {
        "line_total_without_vat": net,
        "vat_amount": vat,
        "line_total_with_vat": gross,
    }


def _item_snapshot(item: ServiceWorkOrderItem) -> dict[str, Any]:
    totals = _line_totals(item)
    return {
        "id": int(item.id),
        "work_order_id": int(item.work_order_id),
        "type": item.item_type,
        "name": item.name,
        "code": item.code,
        "quantity": float(item.quantity or 0),
        "unit": item.unit,
        "vat_rate": float(item.vat_rate or 0),
        "purchase_price_without_vat": item.purchase_price_without_vat,
        "sale_price_without_vat": float(item.sale_price_without_vat or 0),
        "discount_percent": float(item.discount_percent or 0),
        "mechanic_id": item.mechanic_id,
        "source": item.source,
        "created_by": item.created_by,
        "deleted_at": item.deleted_at.isoformat() if item.deleted_at else None,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
        **totals,
    }


def _work_order_snapshot(order: ServiceWorkOrder) -> dict[str, Any]:
    return {
        "id": int(order.id),
        "tenant_id": order.tenant_id,
        "service_customer_id": order.service_customer_id,
        "owner_customer_id": order.owner_customer_id,
        "vehicle_id": order.vehicle_id,
        "technician_id": order.technician_id,
        "source_type": order.source_type,
        "source_intake_id": order.source_intake_id,
        "title": order.title,
        "description": order.description,
        "status": order.status,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "updated_at": order.updated_at.isoformat() if order.updated_at else None,
    }


def _write_work_order_audit(
    db: Session,
    *,
    work_order: ServiceWorkOrder,
    action: str,
    actor: Customer,
    previous_snapshot: dict[str, Any],
    new_snapshot: Optional[dict[str, Any]],
) -> None:
    db.add(
        ServiceWorkOrderAuditLog(
            tenant_id=work_order.tenant_id,
            work_order_id=work_order.id,
            vehicle_id=work_order.vehicle_id,
            changed_by_user_id=getattr(actor, "id", None),
            action=action,
            previous_snapshot_json=json.dumps(previous_snapshot, ensure_ascii=False, default=str),
            new_snapshot_json=(
                json.dumps(new_snapshot, ensure_ascii=False, default=str)
                if new_snapshot is not None
                else None
            ),
        )
    )


def _write_item_audit(
    db: Session,
    *,
    action: str,
    item: ServiceWorkOrderItem,
    actor: Customer,
    before: Optional[dict[str, Any]] = None,
    after: Optional[dict[str, Any]] = None,
) -> None:
    write_global_audit_log(
        db,
        entity_type="service_work_order_item",
        entity_id=int(item.id),
        action=action,
        actor_user_id=getattr(actor, "id", None),
        actor_role=getattr(actor, "role", None),
        tenant_id=item.tenant_id,
        vehicle_id=item.vehicle_id,
        before_json=before,
        after_json=after,
        metadata={
            "work_order_id": int(item.work_order_id),
            "item_type": item.item_type,
            "source": item.source,
        },
    )


def _get_owned_work_order(db: Session, *, current_user: Customer, work_order_id: int) -> ServiceWorkOrder:
    order = (
        db.query(ServiceWorkOrder)
        .filter(
            ServiceWorkOrder.id == int(work_order_id),
            ServiceWorkOrder.service_customer_id == int(current_user.id),
        )
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="Zakázka nebyla nalezena.")
    if order.vehicle_id:
        require_approved_service_vehicle_access(
            db,
            current_user=current_user,
            vehicle_id=int(order.vehicle_id),
        )
    return order


def _get_owned_item(
    db: Session,
    *,
    current_user: Customer,
    work_order: ServiceWorkOrder,
    item_id: int,
) -> ServiceWorkOrderItem:
    item = (
        db.query(ServiceWorkOrderItem)
        .filter(
            ServiceWorkOrderItem.id == int(item_id),
            ServiceWorkOrderItem.work_order_id == int(work_order.id),
            ServiceWorkOrderItem.service_customer_id == int(current_user.id),
            ServiceWorkOrderItem.deleted_at.is_(None),
        )
        .first()
    )
    if not item:
        raise HTTPException(status_code=404, detail="Položka zakázky nebyla nalezena.")
    return item


def _require_active_customer_link(db: Session, *, service: Customer, owner: Customer) -> ServiceCustomerLink:
    link = (
        db.query(ServiceCustomerLink)
        .filter(
            ServiceCustomerLink.service_customer_id == int(service.id),
            ServiceCustomerLink.customer_id == int(owner.id),
            ServiceCustomerLink.status == "active",
        )
        .first()
    )
    if not link:
        raise HTTPException(status_code=403, detail="Servis nemá aktivní vazbu na tohoto zákazníka.")
    return link


def _summary_for_order(db: Session, order: ServiceWorkOrder) -> dict[str, Any]:
    items = (
        db.query(ServiceWorkOrderItem)
        .filter(
            ServiceWorkOrderItem.work_order_id == int(order.id),
            ServiceWorkOrderItem.deleted_at.is_(None),
        )
        .order_by(ServiceWorkOrderItem.created_at.asc(), ServiceWorkOrderItem.id.asc())
        .all()
    )
    groups: dict[str, dict[str, float]] = {
        key: {"total_without_vat": 0.0, "vat_total": 0.0, "total_with_vat": 0.0}
        for key in sorted(ITEM_TYPES)
    }
    serialized = []
    for item in items:
        snap = _item_snapshot(item)
        serialized.append(snap)
        group = groups.setdefault(
            item.item_type,
            {"total_without_vat": 0.0, "vat_total": 0.0, "total_with_vat": 0.0},
        )
        group["total_without_vat"] += float(snap["line_total_without_vat"])
        group["vat_total"] += float(snap["vat_amount"])
        group["total_with_vat"] += float(snap["line_total_with_vat"])

    for values in groups.values():
        for key, value in list(values.items()):
            values[key] = _round_money(value)

    total_without_vat = _round_money(sum(v["total_without_vat"] for v in groups.values()))
    vat_total = _round_money(sum(v["vat_total"] for v in groups.values()))
    total_with_vat = _round_money(sum(v["total_with_vat"] for v in groups.values()))
    return {
        "work_order_id": int(order.id),
        "items": serialized,
        "groups": groups,
        "total_without_vat": total_without_vat,
        "vat_total": vat_total,
        "total_with_vat": total_with_vat,
    }


@router.post("/work-orders/{work_order_id}/items", status_code=201)
def create_work_order_item(
    work_order_id: int,
    payload: WorkOrderItemCreateV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_schema(db)
    order = _get_owned_work_order(db, current_user=current_user, work_order_id=work_order_id)

    item = ServiceWorkOrderItem(
        tenant_id=int(order.tenant_id),
        work_order_id=int(order.id),
        service_customer_id=int(order.service_customer_id),
        vehicle_id=int(order.vehicle_id) if order.vehicle_id else None,
        item_type=_normalize_item_type(payload.type),
        name=str(payload.name).strip(),
        code=(str(payload.code).strip() if payload.code else None),
        quantity=float(payload.quantity),
        unit=str(payload.unit or "ks").strip(),
        vat_rate=float(payload.vat_rate),
        purchase_price_without_vat=payload.purchase_price_without_vat,
        sale_price_without_vat=float(payload.sale_price_without_vat),
        discount_percent=float(payload.discount_percent or 0),
        mechanic_id=payload.mechanic_id,
        source=_normalize_source(payload.source),
        created_by=int(current_user.id),
    )
    db.add(item)
    db.flush()
    after = _item_snapshot(item)
    _write_item_audit(db, action="SERVICE_WORK_ORDER_ITEM_CREATED", item=item, actor=current_user, after=after)
    db.commit()
    db.refresh(item)
    return {"item": _item_snapshot(item), "summary": _summary_for_order(db, order)}


@router.patch("/work-orders/{work_order_id}/items/{item_id}")
def update_work_order_item(
    work_order_id: int,
    item_id: int,
    payload: WorkOrderItemPatchV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_schema(db)
    order = _get_owned_work_order(db, current_user=current_user, work_order_id=work_order_id)
    item = _get_owned_item(db, current_user=current_user, work_order=order, item_id=item_id)
    before = _item_snapshot(item)
    fields_set = set(getattr(payload, "model_fields_set", set()) or set())

    if "type" in fields_set and payload.type is not None:
        item.item_type = _normalize_item_type(payload.type)
    if "name" in fields_set and payload.name is not None:
        item.name = str(payload.name).strip()
    if "code" in fields_set:
        item.code = (str(payload.code).strip() if payload.code else None)
    if "quantity" in fields_set and payload.quantity is not None:
        item.quantity = float(payload.quantity)
    if "unit" in fields_set and payload.unit is not None:
        item.unit = str(payload.unit).strip()
    if "vat_rate" in fields_set and payload.vat_rate is not None:
        item.vat_rate = float(payload.vat_rate)
    if "purchase_price_without_vat" in fields_set:
        item.purchase_price_without_vat = payload.purchase_price_without_vat
    if "sale_price_without_vat" in fields_set and payload.sale_price_without_vat is not None:
        item.sale_price_without_vat = float(payload.sale_price_without_vat)
    if "discount_percent" in fields_set and payload.discount_percent is not None:
        item.discount_percent = float(payload.discount_percent)
    if "mechanic_id" in fields_set:
        item.mechanic_id = payload.mechanic_id
    item.updated_at = datetime.utcnow()

    db.flush()
    after = _item_snapshot(item)
    _write_item_audit(db, action="SERVICE_WORK_ORDER_ITEM_UPDATED", item=item, actor=current_user, before=before, after=after)
    db.commit()
    db.refresh(item)
    return {"item": _item_snapshot(item), "summary": _summary_for_order(db, order)}


@router.delete("/work-orders/{work_order_id}/items/{item_id}")
def delete_work_order_item(
    work_order_id: int,
    item_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_schema(db)
    order = _get_owned_work_order(db, current_user=current_user, work_order_id=work_order_id)
    item = _get_owned_item(db, current_user=current_user, work_order=order, item_id=item_id)
    before = _item_snapshot(item)
    item.deleted_at = datetime.utcnow()
    item.deleted_by = int(current_user.id)
    item.updated_at = datetime.utcnow()
    db.flush()
    after = _item_snapshot(item)
    _write_item_audit(db, action="SERVICE_WORK_ORDER_ITEM_DELETED", item=item, actor=current_user, before=before, after=after)
    db.commit()
    return {"ok": True, "summary": _summary_for_order(db, order)}


@router.get("/work-orders/{work_order_id}/summary")
def get_work_order_summary(
    work_order_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_schema(db)
    order = _get_owned_work_order(db, current_user=current_user, work_order_id=work_order_id)
    return _summary_for_order(db, order)


@router.post("/vehicle-intakes/{intake_id}/create-work-order", status_code=201)
def create_work_order_from_intake(
    intake_id: int,
    payload: CreateWorkOrderFromIntakeV1 | None = None,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_schema(db)
    payload = payload or CreateWorkOrderFromIntakeV1()

    intake = (
        db.query(ServiceIntake)
        .filter(
            ServiceIntake.id == int(intake_id),
            ServiceIntake.service_id == int(current_user.id),
        )
        .first()
    )
    if not intake:
        raise HTTPException(status_code=404, detail="Příjem vozidla nebyl nalezen.")
    if not intake.vehicle_id:
        raise HTTPException(status_code=422, detail="Příjem zatím není navázaný na vozidlo.")
    vehicle, owner, link = require_approved_service_vehicle_access(
        db,
        current_user=current_user,
        vehicle_id=int(intake.vehicle_id),
    )
    if intake.customer_id and int(intake.customer_id) != int(owner.id):
        raise HTTPException(status_code=403, detail="Příjem neodpovídá vlastníkovi vozidla.")
    customer_link = _require_active_customer_link(db, service=current_user, owner=owner)

    duplicate = (
        db.query(ServiceWorkOrder)
        .filter(
            ServiceWorkOrder.service_customer_id == int(current_user.id),
            ServiceWorkOrder.source_intake_id == int(intake.id),
        )
        .first()
    )
    if duplicate:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "intake_work_order_exists",
                "existing_work_order_id": int(duplicate.id),
            },
        )

    vehicle_label = " ".join(
        part for part in [getattr(vehicle, "brand", None), getattr(vehicle, "model", None), getattr(vehicle, "plate", None)] if part
    ).strip() or f"Vozidlo #{int(vehicle.id)}"
    title = (payload.title or "").strip() or f"Zakázka z příjmu: {vehicle_label}"
    description = (payload.description or "").strip() or "\n".join(
        part
        for part in [
            intake.customer_request,
            intake.intake_note,
            intake.damage_description,
            intake.work_description,
        ]
        if part
    ) or None

    technician_id = int(payload.technician_id or current_user.id)
    technician = (
        db.query(Customer)
        .filter(Customer.id == technician_id, Customer.tenant_id == current_user.tenant_id)
        .first()
    )
    if not technician:
        raise HTTPException(status_code=404, detail="Technik nebyl nalezen.")

    order = ServiceWorkOrder(
        tenant_id=int(getattr(current_user, "tenant_id", None) or getattr(vehicle, "tenant_id", None) or 1),
        service_customer_id=int(current_user.id),
        owner_customer_id=int(owner.id),
        vehicle_id=int(vehicle.id),
        technician_id=int(technician.id),
        source_type="intake",
        source_intake_id=int(intake.id),
        title=title,
        description=description,
        status="awaiting_client_approval",
    )
    db.add(order)
    db.flush()
    snapshot = _work_order_snapshot(order)
    _write_work_order_audit(
        db,
        work_order=order,
        action="create_from_intake",
        actor=current_user,
        previous_snapshot={},
        new_snapshot=snapshot,
    )
    write_global_audit_log(
        db,
        entity_type="service_work_order",
        entity_id=int(order.id),
        action="SERVICE_WORK_ORDER_CREATED_FROM_INTAKE",
        actor_user_id=int(current_user.id),
        actor_role=getattr(current_user, "role", None),
        tenant_id=int(order.tenant_id),
        vehicle_id=int(order.vehicle_id),
        metadata={
            "intake_id": int(intake.id),
            "vehicle_service_link_id": int(link.id),
            "service_customer_link_id": int(customer_link.id),
            "owner_customer_id": int(owner.id),
        },
    )
    db.commit()
    db.refresh(order)

    return {
        "work_order": _work_order_snapshot(order),
        "vehicle": {
            "id": int(vehicle.id),
            "plate": vehicle.plate,
            "vin": vehicle.vin,
            "brand": vehicle.brand,
            "model": vehicle.model,
        },
        "owner_customer_id": int(owner.id),
    }
