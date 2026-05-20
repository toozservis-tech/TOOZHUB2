"""Service workspace work-order item endpoints.

Small backend slice for service-case -> work-order conversion and server-side
labor/material/other item totals. It extends the existing ServiceWorkOrder model
instead of introducing a parallel service system.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import unicodedata
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
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
    ServiceWorkOrderCsvImport,
    ServiceWorkOrderItem,
    Vehicle,
)
from ..schema_management import assert_module_ready
from ..service_access import require_approved_service_vehicle_access
from .auth import get_current_user
from .service_workspace import _require_service_workspace_role


router = APIRouter(prefix="/services/workspace", tags=["service-workspace-work-orders"])

ITEM_TYPES = frozenset({"labor", "material", "other"})
ITEM_SOURCES = frozenset({"manual", "csv"})
CSV_IMPORT_MAX_BYTES = 2 * 1024 * 1024
CSV_IMPORT_FIELDS = {
    "name",
    "code",
    "quantity",
    "unit",
    "vat_rate",
    "purchase_price_without_vat",
    "sale_price_without_vat",
    "discount_percent",
    "note",
}
CSV_REQUIRED_FIELDS = {"name", "quantity", "sale_price_without_vat"}
ALLOWED_VAT_RATES = {0.0, 12.0, 21.0}


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
    note: Optional[str] = Field(default=None, max_length=2000)
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
    note: Optional[str] = Field(default=None, max_length=2000)
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


def _strip_accents(value: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", str(value or ""))
        if not unicodedata.combining(ch)
    )


def _norm_key(value: Any) -> str:
    return _strip_accents(str(value or "").strip().lower())


def _safe_csv_text(value: Any) -> str:
    text = str(value or "").strip()
    if text and text[0] in ("=", "+", "-", "@"):
        return "'" + text
    return text


def _parse_decimal(value: Any) -> Optional[float]:
    text = str(value or "").strip()
    if text == "":
        return None
    text = (
        text.replace("\u00a0", "")
        .replace(" ", "")
        .replace("Kč", "")
        .replace("CZK", "")
        .replace("%", "")
        .strip()
    )
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    elif "," in text:
        text = text.replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _csv_duplicate_key(code: Any, name: Any, quantity: Any, sale_price_without_vat: Any) -> tuple[str, str, float, float]:
    return (
        _norm_key(code),
        _norm_key(name),
        round(float(quantity or 0), 4),
        round(float(sale_price_without_vat or 0), 2),
    )


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
        "note": item.note,
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


def _get_csv_import_work_order(db: Session, *, current_user: Customer, work_order_id: int) -> ServiceWorkOrder:
    order = db.query(ServiceWorkOrder).filter(ServiceWorkOrder.id == int(work_order_id)).first()
    if not order:
        raise HTTPException(status_code=404, detail="Zakázka nebyla nalezena.")
    if int(order.service_customer_id) != int(current_user.id):
        raise HTTPException(status_code=403, detail="Servis nemá oprávnění k této zakázce/vozidlu.")
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


def _extract_multipart_name(disposition: str) -> str:
    marker = 'name="'
    if marker not in disposition:
        return ""
    rest = disposition.split(marker, 1)[1]
    return rest.split('"', 1)[0]


def _extract_multipart_filename(disposition: str) -> str:
    marker = 'filename="'
    if marker not in disposition:
        return ""
    rest = disposition.split(marker, 1)[1]
    return rest.split('"', 1)[0]


async def _read_csv_multipart_request(request: Request) -> tuple[bytes, str, dict[str, str], str]:
    content_type_header = str(request.headers.get("content-type") or "")
    if "multipart/form-data" not in content_type_header.lower() or "boundary=" not in content_type_header:
        raise HTTPException(status_code=415, detail="Nahrajte CSV jako multipart/form-data.")
    boundary = content_type_header.split("boundary=", 1)[1].strip().strip('"')
    body = await request.body()
    marker = ("--" + boundary).encode("utf-8")
    fields: dict[str, str] = {}
    file_data = b""
    filename = "import.csv"
    file_content_type = "text/csv"
    for part in body.split(marker):
        part = part.strip(b"\r\n")
        if not part or part == b"--":
            continue
        if part.endswith(b"--"):
            part = part[:-2].strip(b"\r\n")
        header_blob, sep, content = part.partition(b"\r\n\r\n")
        if not sep:
            continue
        headers = header_blob.decode("utf-8", errors="ignore").split("\r\n")
        disposition = next((h for h in headers if h.lower().startswith("content-disposition:")), "")
        content_type_line = next((h for h in headers if h.lower().startswith("content-type:")), "")
        name = _extract_multipart_name(disposition)
        part_filename = _extract_multipart_filename(disposition)
        content = content.rstrip(b"\r\n")
        if part_filename:
            filename = part_filename
            if ":" in content_type_line:
                file_content_type = content_type_line.split(":", 1)[1].strip()
            file_data = content
        elif name:
            fields[name] = content.decode("utf-8", errors="replace")
    return _validate_csv_upload(file_data, filename, file_content_type), filename, fields, file_content_type


def _validate_csv_upload(data: bytes, filename: str, content_type: str) -> bytes:
    filename = str(filename or "import.csv")
    content_type = str(content_type or "").lower()
    if not (filename.lower().endswith(".csv") or content_type in {"text/csv", "application/csv", "text/plain", "application/vnd.ms-excel"}):
        raise HTTPException(status_code=415, detail="Nahrajte soubor CSV.")
    if len(data) > CSV_IMPORT_MAX_BYTES:
        raise HTTPException(status_code=413, detail="CSV soubor je příliš velký. Maximum je 2 MB.")
    if not data:
        raise HTTPException(status_code=422, detail="CSV soubor je prázdný.")
    return data


def _decode_csv_bytes(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1250", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise HTTPException(status_code=422, detail="CSV soubor se nepodařilo přečíst.")


def _detect_delimiter(text: str) -> str:
    candidates = [";", ",", "\t"]
    lines = [line for line in text.splitlines()[:10] if line.strip()]
    scores = {delimiter: 0 for delimiter in candidates}
    for line in lines:
        for delimiter in candidates:
            scores[delimiter] += line.count(delimiter)
    best = max(candidates, key=lambda delimiter: scores[delimiter])
    return best if scores[best] > 0 else ";"


def _parse_csv(data: bytes) -> tuple[str, list[str], list[dict[str, Any]]]:
    text = _decode_csv_bytes(data)
    delimiter = _detect_delimiter(text)
    try:
        reader = csv.reader(io.StringIO(text), delimiter=delimiter)
        rows = list(reader)
    except csv.Error as exc:
        raise HTTPException(status_code=422, detail=f"CSV soubor není validní: {exc}") from exc
    rows = [row for row in rows if any(str(cell or "").strip() for cell in row)]
    if not rows:
        raise HTTPException(status_code=422, detail="CSV neobsahuje žádná data.")
    columns = [str(cell or "").strip().lstrip("\ufeff") for cell in rows[0]]
    if not any(columns):
        raise HTTPException(status_code=422, detail="CSV nemá hlavičku sloupců.")
    data_rows = [
        {
            "row_number": index,
            "raw": {columns[i] or f"column_{i + 1}": (row[i] if i < len(row) else "") for i in range(len(columns))},
        }
        for index, row in enumerate(rows[1:], start=2)
    ]
    return delimiter, columns, data_rows


def _detect_mapping(columns: list[str]) -> dict[str, str]:
    synonyms = {
        "name": {"name", "nazev", "nazev dilu", "dil", "polozka", "produkt", "popis"},
        "code": {"code", "kod", "kod dilu", "sku", "objednaci cislo", "cislo"},
        "quantity": {"quantity", "mnozstvi", "mnoz.", "pocet", "qty"},
        "unit": {"unit", "jednotka", "mj"},
        "vat_rate": {"vat_rate", "dph", "sazba dph", "vat"},
        "purchase_price_without_vat": {"purchase_price_without_vat", "nakup bez dph", "nc bez dph", "nakupni cena bez dph"},
        "sale_price_without_vat": {"sale_price_without_vat", "prodej bez dph", "pc bez dph", "prodejni cena bez dph", "cena bez dph", "cena"},
        "discount_percent": {"discount_percent", "sleva", "sleva %", "discount"},
        "note": {"note", "poznamka", "pozn.", "comment"},
    }
    result: dict[str, str] = {}
    normalized = {column: _norm_key(column) for column in columns}
    for field, names in synonyms.items():
        for column, norm in normalized.items():
            if norm in names:
                result[field] = column
                break
    return result


def _normalize_mapping(mapping: dict[str, Any], columns: list[str]) -> dict[str, str]:
    allowed_columns = set(columns)
    normalized: dict[str, str] = {}
    for field, column in (mapping or {}).items():
        f = str(field or "").strip()
        c = str(column or "").strip()
        if f in CSV_IMPORT_FIELDS and c in allowed_columns:
            normalized[f] = c
    return normalized


def _existing_csv_duplicate_keys(db: Session, order: ServiceWorkOrder) -> set[tuple[str, str, float, float]]:
    items = (
        db.query(ServiceWorkOrderItem)
        .filter(
            ServiceWorkOrderItem.work_order_id == int(order.id),
            ServiceWorkOrderItem.source == "csv",
            ServiceWorkOrderItem.deleted_at.is_(None),
        )
        .all()
    )
    return {
        _csv_duplicate_key(item.code, item.name, item.quantity, item.sale_price_without_vat)
        for item in items
    }


def _validate_csv_rows(
    *,
    rows: list[dict[str, Any]],
    mapping: dict[str, str],
    existing_duplicate_keys: set[tuple[str, str, float, float]],
) -> dict[str, Any]:
    missing = sorted(CSV_REQUIRED_FIELDS - set(mapping.keys()))
    if missing:
        return {
            "rows_count": len(rows),
            "importable_count": 0,
            "skipped_count": len(rows),
            "duplicate_count": 0,
            "errors_count": len(rows),
            "rows": [],
            "mapping_errors": [f"Chybí mapování pole {field}." for field in missing],
        }

    seen: set[tuple[str, str, float, float]] = set()
    preview_rows = []
    importable_count = 0
    skipped_count = 0
    duplicate_count = 0
    errors_count = 0

    for row in rows:
        raw = row.get("raw") or {}
        if not any(str(value or "").strip() for value in raw.values()):
            skipped_count += 1
            continue
        values = {field: raw.get(column, "") for field, column in mapping.items()}
        errors: list[str] = []
        warnings: list[str] = []
        name = _safe_csv_text(values.get("name"))
        code = _safe_csv_text(values.get("code"))
        unit = _safe_csv_text(values.get("unit")) or "ks"
        note = _safe_csv_text(values.get("note"))
        quantity = _parse_decimal(values.get("quantity"))
        vat_rate = _parse_decimal(values.get("vat_rate"))
        purchase_price = _parse_decimal(values.get("purchase_price_without_vat"))
        sale_price = _parse_decimal(values.get("sale_price_without_vat"))
        discount = _parse_decimal(values.get("discount_percent"))

        if not name:
            errors.append("Chybí název dílu.")
        if quantity is None or quantity <= 0:
            errors.append("Množství musí být větší než 0.")
        if sale_price is None or sale_price < 0:
            errors.append("Prodejní cena bez DPH nesmí být záporná a musí být číslo.")
        if purchase_price is not None and purchase_price < 0:
            errors.append("Nákupní cena bez DPH nesmí být záporná.")
        vat = 21.0 if vat_rate is None else float(vat_rate)
        if vat not in ALLOWED_VAT_RATES:
            errors.append("DPH musí být 0, 12 nebo 21.")
        disc = 0.0 if discount is None else float(discount)
        if disc < 0 or disc > 100:
            errors.append("Sleva musí být mezi 0 a 100 %.")

        duplicate = False
        if not errors:
            key = _csv_duplicate_key(code, name, quantity, sale_price)
            duplicate = key in existing_duplicate_keys or key in seen
            if duplicate:
                duplicate_count += 1
                warnings.append("Možná duplicita z CSV importu.")
            seen.add(key)

        importable = not errors
        if importable:
            importable_count += 1
        else:
            errors_count += 1
            skipped_count += 1

        preview_rows.append({
            "row_number": int(row["row_number"]),
            "values": {
                "name": name,
                "code": code or None,
                "quantity": quantity,
                "unit": unit,
                "vat_rate": vat,
                "purchase_price_without_vat": purchase_price,
                "sale_price_without_vat": sale_price,
                "discount_percent": disc,
                "note": note or None,
            },
            "errors": errors,
            "warnings": warnings,
            "duplicate": duplicate,
            "importable": importable,
        })

    return {
        "rows_count": len(rows),
        "importable_count": importable_count,
        "skipped_count": skipped_count,
        "duplicate_count": duplicate_count,
        "errors_count": errors_count,
        "rows": preview_rows,
        "mapping_errors": [],
    }


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
        note=(str(payload.note).strip() if payload.note else None),
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
    if "note" in fields_set:
        item.note = (str(payload.note).strip() if payload.note else None)
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


@router.post("/work-orders/{work_order_id}/csv/preview")
async def preview_work_order_csv_import(
    work_order_id: int,
    request: Request,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_schema(db)
    order = _get_csv_import_work_order(db, current_user=current_user, work_order_id=work_order_id)
    data, filename, fields, _content_type = await _read_csv_multipart_request(request)
    delimiter, columns, rows = _parse_csv(data)
    detected_mapping = _detect_mapping(columns)
    active_mapping = detected_mapping
    if fields.get("mapping_json"):
        try:
            active_mapping = _normalize_mapping(json.loads(fields["mapping_json"]), columns)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=422, detail="Mapování sloupců není validní JSON.") from exc
    validation = _validate_csv_rows(
        rows=rows,
        mapping=_normalize_mapping(active_mapping, columns),
        existing_duplicate_keys=_existing_csv_duplicate_keys(db, order),
    )
    return {
        "filename": filename,
        "file_sha256": hashlib.sha256(data).hexdigest(),
        "delimiter": delimiter,
        "columns": columns,
        "sample_rows": [row["raw"] for row in rows[:5]],
        "detected_mapping": detected_mapping,
        "mapping": active_mapping,
        "validation": validation,
    }


@router.post("/work-orders/{work_order_id}/csv/import")
async def import_work_order_csv_items(
    work_order_id: int,
    request: Request,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_service_workspace_role(current_user)
    _ensure_schema(db)
    order = _get_csv_import_work_order(db, current_user=current_user, work_order_id=work_order_id)
    data, filename, fields, _content_type = await _read_csv_multipart_request(request)
    mapping_json = fields.get("mapping_json") or "{}"
    skip_duplicates = str(fields.get("skip_duplicates", "true")).strip().lower() not in {"0", "false", "ne", "no"}
    try:
        mapping_raw = json.loads(mapping_json or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="Mapování sloupců není validní JSON.") from exc

    delimiter, columns, rows = _parse_csv(data)
    mapping = _normalize_mapping(mapping_raw, columns)
    validation = _validate_csv_rows(
        rows=rows,
        mapping=mapping,
        existing_duplicate_keys=_existing_csv_duplicate_keys(db, order),
    )
    if validation.get("mapping_errors"):
        raise HTTPException(status_code=422, detail={"mapping_errors": validation["mapping_errors"]})

    imported_count = 0
    skipped_count = 0
    duplicate_count = 0
    error_rows: list[dict[str, Any]] = []
    created_items: list[dict[str, Any]] = []

    for row in validation["rows"]:
        if row["errors"]:
            skipped_count += 1
            error_rows.append({
                "row_number": row["row_number"],
                "errors": row["errors"],
                "values": row["values"],
            })
            continue
        if row["duplicate"]:
            duplicate_count += 1
            if skip_duplicates:
                skipped_count += 1
                continue
        values = row["values"]
        item = ServiceWorkOrderItem(
            tenant_id=int(order.tenant_id),
            work_order_id=int(order.id),
            service_customer_id=int(order.service_customer_id),
            vehicle_id=int(order.vehicle_id) if order.vehicle_id else None,
            item_type="material",
            name=str(values["name"]).strip(),
            code=(str(values["code"]).strip() if values.get("code") else None),
            quantity=float(values["quantity"]),
            unit=str(values.get("unit") or "ks").strip(),
            vat_rate=float(values.get("vat_rate") if values.get("vat_rate") is not None else 21),
            purchase_price_without_vat=values.get("purchase_price_without_vat"),
            sale_price_without_vat=float(values["sale_price_without_vat"]),
            discount_percent=float(values.get("discount_percent") or 0),
            note=(str(values["note"]).strip() if values.get("note") else None),
            source="csv",
            created_by=int(current_user.id),
        )
        db.add(item)
        db.flush()
        after = _item_snapshot(item)
        _write_item_audit(db, action="SERVICE_WORK_ORDER_ITEM_CREATED_FROM_CSV", item=item, actor=current_user, after=after)
        created_items.append(after)
        imported_count += 1

    import_record = ServiceWorkOrderCsvImport(
        tenant_id=int(order.tenant_id),
        service_id=int(current_user.id),
        work_order_id=int(order.id),
        vehicle_id=int(order.vehicle_id) if order.vehicle_id else None,
        filename=filename[:255],
        delimiter=delimiter,
        rows_count=int(validation["rows_count"]),
        imported_count=imported_count,
        skipped_count=skipped_count,
        duplicate_count=duplicate_count,
        error_rows_json=json.dumps(error_rows, ensure_ascii=False, default=str),
        mapping_json=json.dumps(mapping, ensure_ascii=False, default=str),
        file_sha256=hashlib.sha256(data).hexdigest(),
        created_by=int(current_user.id),
    )
    db.add(import_record)
    db.flush()
    write_global_audit_log(
        db,
        entity_type="service_work_order_csv_import",
        entity_id=int(import_record.id),
        action="SERVICE_WORK_ORDER_CSV_IMPORTED",
        actor_user_id=int(current_user.id),
        actor_role=getattr(current_user, "role", None),
        tenant_id=int(order.tenant_id),
        vehicle_id=int(order.vehicle_id) if order.vehicle_id else None,
        metadata={
            "work_order_id": int(order.id),
            "filename": filename,
            "rows_count": int(validation["rows_count"]),
            "imported_count": imported_count,
            "skipped_count": skipped_count,
            "duplicate_count": duplicate_count,
            "file_sha256": import_record.file_sha256,
        },
    )
    db.commit()
    db.refresh(import_record)
    return {
        "import_result": {
            "id": int(import_record.id),
            "filename": filename,
            "delimiter": delimiter,
            "rows_count": int(validation["rows_count"]),
            "imported_count": imported_count,
            "skipped_count": skipped_count,
            "duplicate_count": duplicate_count,
            "error_rows": error_rows,
            "created_items": created_items,
        },
        "summary": _summary_for_order(db, order),
    }


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
