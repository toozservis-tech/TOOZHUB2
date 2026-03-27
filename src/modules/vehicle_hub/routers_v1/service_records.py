"""
Service Records API v1.0 router
"""
from datetime import datetime
import base64
import binascii
import hashlib
import json
import mimetypes
from pathlib import Path
import re
import secrets
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Any, List, Optional
from sqlalchemy import desc, nullslast

from src.core.config import DATA_DIR
from ..database import get_db
from ..models import (
    Customer,
    ServiceRecord as ServiceRecordModel,
    ServiceRecordAuditLog,
    Vehicle as VehicleModel,
)
from ..schema_management import assert_module_ready
from .auth import get_current_user, can_access_vehicle
from .schemas import ServiceRecordCreateV1, ServiceRecordUpdateV1, ServiceRecordOutV1
from .service_workspace import (
    ALLOWED_SOURCE_TYPES,
    _build_service_record_description,
    _extract_text_from_file,
    _parse_document_payload,
)
router = APIRouter(prefix="/vehicles", tags=["service-records-v1"])

SERVICE_RECORD_ATTACHMENTS_DIR = DATA_DIR / "service_record_attachments"
SERVICE_RECORD_ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
MAX_ATTACHMENT_SIZE_BYTES = 15 * 1024 * 1024
ALLOWED_ATTACHMENT_EXTENSIONS = {
    ".pdf",
    ".txt",
    ".csv",
    ".json",
    ".xml",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
    ".gif",
}
MILEAGE_RE = re.compile(r"(?<!\d)(\d{1,3}(?:[ .]\d{3}){1,2}|\d{4,7})\s*km\b", re.IGNORECASE)
MILEAGE_KEYWORD_RE = re.compile(
    r"(?:stav\s*(?:tachometru|km)|tachometr|najeto|najazdeno|odometer)\s*[:\-]?\s*(\d{1,3}(?:[ .]\d{3}){1,2}|\d{4,7})",
    re.IGNORECASE,
)
CATEGORY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("OLEJ", ("olej", "oil", "maziv")),
    ("FILTRY", ("filtr", "filter")),
    ("BRZDY", ("brzd", "kotou", "desti")),
    ("PNEU", ("pneu", "pneum", "guma", "tire")),
    ("STK", ("stk", "emise", "emis")),
    ("DIAGNOSTIKA", ("diagnost", "diag")),
    ("KLIMATIZACE", ("klimat", "ac servis", "ac-service", "air condition")),
    ("ELEKTRIKA", ("akumul", "bateri", "alternator", "starter", "elektr")),
    ("CHLADICI", ("chladic", "chladi", "coolant")),
    ("VYFUK", ("vyfuk", "výfuk", "dpf")),
    ("KAROSERIE", ("karoser", "lakov", "plech")),
    ("OSVETLENI", ("svetl", "žárov", "zarov", "xenon", "led")),
    ("OPRAVA", ("oprava", "servis", "repair")),
]
SUSPICIOUS_SUMMARY_PATTERNS = [
    re.compile(r"\b\d{1,5}\s*/\s*\d{1,5}[A-Za-z]?\b", re.IGNORECASE),
    re.compile(r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b.*\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b", re.IGNORECASE),
    re.compile(
        r"^(celkov[aá]\s+částka|celkova\s+castka|celkem|zbýv[aá]\s+uhradit|zbyva\s+uhradit|uhrazeno)\b",
        re.IGNORECASE,
    ),
]


def _service_record_snapshot(record: ServiceRecordModel) -> dict[str, Any]:
    return {
        "id": record.id,
        "tenant_id": record.tenant_id,
        "vehicle_id": record.vehicle_id,
        "user_id": record.user_id,
        "performed_at": record.performed_at.isoformat() if record.performed_at else None,
        "mileage": record.mileage,
        "description": record.description,
        "price": record.price,
        "note": record.note,
        "category": record.category,
        "attachments": record.attachments,
        "next_service_due_date": (
            record.next_service_due_date.isoformat() if record.next_service_due_date else None
        ),
        "created_by_ai": bool(record.created_by_ai),
        "is_deleted": bool(getattr(record, "is_deleted", False)),
        "deleted_at": record.deleted_at.isoformat() if getattr(record, "deleted_at", None) else None,
        "deleted_by_user_id": getattr(record, "deleted_by_user_id", None),
        "deletion_reason": getattr(record, "deletion_reason", None),
    }


def _snapshot_json_and_hash(snapshot: dict[str, Any]) -> tuple[str, str]:
    snapshot_json = json.dumps(snapshot, ensure_ascii=False, sort_keys=True)
    snapshot_hash = hashlib.sha256(snapshot_json.encode("utf-8")).hexdigest()
    return snapshot_json, snapshot_hash


class ServiceRecordAttachmentUploadRequest(BaseModel):
    file_name: str = Field(..., min_length=1, max_length=255)
    file_mime_type: str = Field(default="application/octet-stream", max_length=255)
    file_content_base64: str = Field(..., min_length=20, max_length=25_000_000)


class ServiceRecordAutoFromDocumentRequest(BaseModel):
    source_type: str = Field(default="invoice", max_length=32)
    file_name: str = Field(..., min_length=1, max_length=255)
    file_mime_type: str = Field(default="application/octet-stream", max_length=255)
    file_content_base64: str = Field(..., min_length=20, max_length=25_000_000)
    manual_text: Optional[str] = Field(default=None, max_length=300_000)
    manual_note: Optional[str] = Field(default=None, max_length=2000)
    fallback_category: Optional[str] = Field(default=None, max_length=32)
    fallback_mileage: Optional[int] = Field(default=None, ge=0)
    fallback_performed_at: Optional[datetime] = None
    fallback_description: Optional[str] = Field(default=None, max_length=500)
    fallback_price: Optional[float] = Field(default=None, ge=0)


class ServiceRecordDocumentPrefillRequest(ServiceRecordAutoFromDocumentRequest):
    pass


def _sanitize_file_stem(filename: str) -> str:
    stem = Path(filename or "doklad").stem
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")
    return cleaned[:64] or "doklad"


def _resolve_attachment_file(relative_key: str) -> Path | None:
    raw_key = str(relative_key or "").strip().replace("\\", "/")
    if not raw_key:
        return None
    candidate = (SERVICE_RECORD_ATTACHMENTS_DIR / raw_key).resolve()
    base = SERVICE_RECORD_ATTACHMENTS_DIR.resolve()
    if not str(candidate).startswith(str(base)):
        return None
    return candidate


def _extract_attachment_file_paths(attachments_raw: str | None) -> list[Path]:
    if not attachments_raw:
        return []
    try:
        payload = json.loads(attachments_raw)
    except Exception:
        return []
    if not isinstance(payload, list):
        return []

    files: list[Path] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        key = item.get("storage_key") or item.get("path")
        if not key:
            continue
        resolved = _resolve_attachment_file(str(key))
        if resolved:
            files.append(resolved)
    return files


def _parse_attachments_payload(attachments_raw: str | None) -> list[dict[str, Any]]:
    if not attachments_raw:
        return []
    try:
        payload = json.loads(attachments_raw)
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def _parsed_summary_needs_refresh(summary: Any) -> bool:
    if not isinstance(summary, dict):
        return True
    supplier_name = str(summary.get("supplier_name") or "").strip()
    if not supplier_name or "@" in supplier_name:
        return True
    items = summary.get("items")
    if not isinstance(items, list) or not items:
        # U faktur očekáváme položky; prázdný/rozbitý summary raději přepočítat.
        return True
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        if any(pattern.search(name) for pattern in SUSPICIOUS_SUMMARY_PATTERNS):
            return True
    if summary.get("labor_total") is None and summary.get("materials_total") is None:
        return True
    return False


def _description_needs_refresh(description: Any) -> bool:
    text = str(description or "").strip()
    if not text:
        return True
    lower = text.lower()
    if "import" not in lower:
        return False
    if any(pattern.search(text) for pattern in SUSPICIOUS_SUMMARY_PATTERNS):
        return True
    return False


def _rebuild_attachment_parsed_summary(attachment: dict[str, Any]) -> tuple[Optional[dict[str, Any]], Optional[dict[str, Any]]]:
    storage_key = attachment.get("storage_key") or attachment.get("path")
    if not storage_key:
        return None, None
    attachment_file = _resolve_attachment_file(str(storage_key))
    if not attachment_file or not attachment_file.is_file():
        return None, None

    source_type = str(attachment.get("source_type") or "invoice").strip().lower() or "invoice"
    if source_type not in ALLOWED_SOURCE_TYPES:
        source_type = "invoice"

    mime_type = str(attachment.get("mime_type") or "").strip() or None
    file_name = str(attachment.get("file_name") or attachment_file.name).strip() or attachment_file.name

    raw_content = attachment_file.read_bytes()
    extracted_text, extraction_warning, extraction_engine = _extract_text_from_file(
        content=raw_content,
        file_name=file_name,
        mime_type=mime_type,
    )
    parsed_data = _parse_document_payload(
        source_type=source_type,
        extracted_text=extracted_text,
        manual_text=None,
        manual_note=None,
        extraction_engine=extraction_engine,
        extraction_warning=extraction_warning,
    )
    service_report = _build_service_report_payload(parsed_data, source_type)
    return service_report, parsed_data


def _refresh_record_attachments_summary(record: ServiceRecordModel) -> bool:
    attachments_payload = _parse_attachments_payload(record.attachments)
    if not attachments_payload:
        return False

    payload_changed = False
    first_parsed_data: Optional[dict[str, Any]] = None

    for attachment in attachments_payload:
        current_summary = attachment.get("parsed_summary")
        if not _parsed_summary_needs_refresh(current_summary):
            continue
        rebuilt_summary, parsed_data = _rebuild_attachment_parsed_summary(attachment)
        if not rebuilt_summary:
            continue
        attachment["parsed_summary"] = rebuilt_summary
        payload_changed = True
        if first_parsed_data is None and parsed_data:
            first_parsed_data = parsed_data

    if not payload_changed:
        return False

    record.attachments = json.dumps(attachments_payload, ensure_ascii=False)
    if first_parsed_data and _description_needs_refresh(record.description):
        record.description = _build_service_record_description(first_parsed_data)
    return True


def _decode_base64_payload(payload: str) -> bytes:
    raw = str(payload or "").strip()
    if not raw:
        return b""
    if raw.startswith("data:") and "," in raw:
        raw = raw.split(",", 1)[1]
    try:
        return base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Soubor není validní base64 payload: {exc}") from exc


def _store_attachment_for_vehicle(
    *,
    vehicle_id: int,
    vehicle: VehicleModel,
    current_user: Customer,
    file_name: str,
    file_mime_type: str,
    content: bytes,
) -> dict[str, Any]:
    if not content:
        raise HTTPException(status_code=422, detail="Nahraný soubor je prázdný.")
    if len(content) > MAX_ATTACHMENT_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="Soubor je příliš velký (max 15 MB).")

    filename = str(file_name or "doklad")
    extension = Path(filename).suffix.lower().strip()
    mime_type = str(file_mime_type or "").lower().strip() or "application/octet-stream"

    if extension and extension not in ALLOWED_ATTACHMENT_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Nepodporovaný typ souboru.")
    if not extension:
        if mime_type == "application/pdf":
            extension = ".pdf"
        elif mime_type.startswith("image/"):
            extension = ".jpg"
        elif mime_type.startswith("text/"):
            extension = ".txt"
        else:
            raise HTTPException(status_code=415, detail="Nepodporovaný typ souboru.")

    tenant_id = int(getattr(vehicle, "tenant_id", None) or getattr(current_user, "tenant_id", None) or 0)
    target_dir = SERVICE_RECORD_ATTACHMENTS_DIR / f"tenant_{tenant_id}" / f"vehicle_{vehicle_id}"
    target_dir.mkdir(parents=True, exist_ok=True)

    safe_stem = _sanitize_file_stem(filename)
    unique_name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{safe_stem}_{secrets.token_hex(4)}{extension}"
    target_file = target_dir / unique_name
    target_file.write_bytes(content)

    storage_key = target_file.relative_to(SERVICE_RECORD_ATTACHMENTS_DIR).as_posix()
    return {
        "file_name": filename,
        "mime_type": mime_type,
        "file_size": len(content),
        "storage_key": storage_key,
        "download_url": f"/api/v1/vehicles/{vehicle_id}/records/attachments/download?key={storage_key}",
        "absolute_path": str(target_file),
    }


def _extract_mileage_from_text(raw_text: str) -> Optional[int]:
    text = str(raw_text or "")
    if not text:
        return None

    found: list[int] = []
    for match in MILEAGE_RE.finditer(text):
        token = str(match.group(1) or "").replace(" ", "").replace(".", "")
        try:
            value = int(token)
        except Exception:
            continue
        if 500 <= value <= 2_000_000:
            found.append(value)

    for match in MILEAGE_KEYWORD_RE.finditer(text):
        token = str(match.group(1) or "").replace(" ", "").replace(".", "")
        try:
            value = int(token)
        except Exception:
            continue
        if 500 <= value <= 2_000_000:
            found.append(value)
    if not found:
        return None
    return max(found)


def _to_iso_date(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            return None
    return None


def _format_money_for_note(amount: Any, currency: str = "CZK") -> str:
    try:
        parsed = float(amount)
    except Exception:
        return "Neuvedeno"
    symbol = "Kč" if str(currency or "").upper() == "CZK" else str(currency or "").upper()
    return f"{parsed:,.2f}".replace(",", " ").replace(".", ",") + f" {symbol}"


def _normalize_parsed_items(parsed_data: dict[str, Any]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in parsed_data.get("items") or []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        quantity = item.get("quantity")
        unit = str(item.get("unit") or "").strip() or None
        total_price = item.get("total_price")
        unit_price = item.get("unit_price")
        currency = str(item.get("currency") or parsed_data.get("currency") or "CZK").upper()
        normalized.append(
            {
                "name": name,
                "quantity": quantity,
                "unit": unit,
                "unit_price": unit_price,
                "total_price": total_price,
                "currency": currency,
            }
        )
        if len(normalized) >= 30:
            break
    return normalized


def _parse_optional_float(raw_value: Any) -> Optional[float]:
    if raw_value is None:
        return None
    try:
        normalized = str(raw_value).replace("\xa0", " ").replace(" ", "").replace(",", ".")
        if not normalized:
            return None
        value = float(normalized)
        if not (value == value):  # NaN guard
            return None
        return value
    except Exception:
        return None


def _is_labor_item_name_or_unit(name: Any, unit: Any) -> bool:
    unit_value = str(unit or "").strip().lower()
    if unit_value in {"h", "hod", "hod.", "hodina", "hodiny", "hr", "nh"}:
        return True

    lower_name = str(name or "").strip().lower()
    if not lower_name:
        return False

    labor_keywords = (
        "práce",
        "prace",
        "servisní práce",
        "servisni prace",
        "hodinová sazba",
        "hodinova sazba",
        "diagnost",
        "montáž",
        "montaz",
        "demontáž",
        "demontaz",
        "oprava",
        "seřízení",
        "serizeni",
    )
    return any(keyword in lower_name for keyword in labor_keywords)


def _infer_labor_material_breakdown(items: list[dict[str, Any]]) -> tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
    labor_total = 0.0
    materials_total = 0.0
    labor_hours = 0.0
    labor_hour_rate: Optional[float] = None
    labor_found = False
    material_found = False

    for item in items:
        if not isinstance(item, dict):
            continue
        total_price = _parse_optional_float(item.get("total_price"))
        if total_price is None or total_price <= 0:
            continue

        name = item.get("name")
        unit = item.get("unit")
        quantity = _parse_optional_float(item.get("quantity"))
        unit_price = _parse_optional_float(item.get("unit_price"))
        is_labor = _is_labor_item_name_or_unit(name, unit)

        if is_labor:
            labor_found = True
            labor_total += float(total_price)
            unit_value = str(unit or "").strip().lower()
            if quantity is not None and quantity > 0 and unit_value in {"h", "hod", "hod.", "hodina", "hodiny", "hr", "nh"}:
                labor_hours += float(quantity)
                if labor_hour_rate is None and unit_price is not None and unit_price > 0:
                    labor_hour_rate = float(unit_price)
                elif labor_hour_rate is None:
                    labor_hour_rate = float(total_price) / float(quantity)
            elif labor_hour_rate is None and unit_price is not None and unit_price > 0:
                labor_hour_rate = float(unit_price)
        else:
            material_found = True
            materials_total += float(total_price)

    return (
        round(labor_total, 2) if labor_found else None,
        round(materials_total, 2) if material_found else None,
        round(labor_hours, 2) if labor_hours > 0 else None,
        round(float(labor_hour_rate), 2) if labor_hour_rate is not None and labor_hour_rate > 0 else None,
    )


def _suggest_category_from_parsed_data(parsed_data: dict[str, Any], source_type: str) -> str:
    text_parts: list[str] = []
    for item in parsed_data.get("items") or []:
        if isinstance(item, dict):
            text_parts.append(str(item.get("name") or ""))
    text_parts.extend(
        [
            str(parsed_data.get("supplier_name") or ""),
            str(parsed_data.get("service_summary") or ""),
            str(parsed_data.get("document_number") or ""),
            str(source_type or ""),
        ]
    )
    haystack = " ".join(text_parts).lower()
    for category, keywords in CATEGORY_KEYWORDS:
        if any(keyword in haystack for keyword in keywords):
            return category
    return "JINE"


def _build_service_report_payload(parsed_data: dict[str, Any], source_type: str) -> dict[str, Any]:
    supplier_email = parsed_data.get("supplier_email")
    supplier_website = parsed_data.get("supplier_website")
    service_link = parsed_data.get("service_link") or supplier_website or (f"mailto:{supplier_email}" if supplier_email else None)
    currency = str(parsed_data.get("currency") or "CZK").upper()
    items = _normalize_parsed_items(parsed_data)
    inferred_labor_total, inferred_materials_total, inferred_labor_hours, inferred_labor_hour_rate = _infer_labor_material_breakdown(items)

    labor_total = _parse_optional_float(parsed_data.get("labor_total"))
    materials_total = _parse_optional_float(parsed_data.get("materials_total"))
    labor_hours = _parse_optional_float(parsed_data.get("labor_hours"))
    labor_hour_rate = _parse_optional_float(parsed_data.get("labor_hour_rate"))

    if labor_total is None:
        labor_total = inferred_labor_total
    if materials_total is None:
        materials_total = inferred_materials_total
    if labor_hours is None:
        labor_hours = inferred_labor_hours
    if labor_hour_rate is None:
        labor_hour_rate = inferred_labor_hour_rate

    return {
        "source_type": source_type,
        "document_number": parsed_data.get("document_number"),
        "supplier_name": parsed_data.get("supplier_name"),
        "supplier_email": supplier_email,
        "supplier_website": supplier_website,
        "service_link": service_link,
        "customer_name": parsed_data.get("customer_name"),
        "service_summary": parsed_data.get("service_summary"),
        "technician_name": parsed_data.get("technician_name"),
        "technician_initials": parsed_data.get("technician_initials"),
        "issue_date": _to_iso_date(parsed_data.get("issue_date")),
        "due_date": _to_iso_date(parsed_data.get("due_date")),
        "currency": currency,
        "labor_hours": labor_hours,
        "labor_hour_rate": labor_hour_rate,
        "subtotal_without_vat": parsed_data.get("subtotal_without_vat"),
        "vat_amount": parsed_data.get("vat_amount"),
        "total_with_vat": parsed_data.get("total_with_vat"),
        "labor_total": labor_total,
        "materials_total": materials_total,
        "items": items,
    }


def _build_service_report_note(
    *,
    source_type: str,
    parsed_data: dict[str, Any],
    manual_note: Optional[str] = None,
) -> str:
    source_label_map = {
        "invoice": "Faktura",
        "delivery_note": "Dodací list",
        "work_order": "Zakázkový list",
        "receipt": "Účtenka",
        "manual": "Ruční zápis",
    }
    source_label = source_label_map.get(str(source_type or "").lower(), "Doklad")
    currency = str(parsed_data.get("currency") or "CZK").upper()

    lines: list[str] = [f"Servisní zpráva ({source_label})"]
    if parsed_data.get("supplier_name"):
        lines.append(f"Dodavatel: {parsed_data.get('supplier_name')}")
    if parsed_data.get("supplier_email"):
        lines.append(f"Kontakt servisu: {parsed_data.get('supplier_email')}")
    if parsed_data.get("service_link"):
        lines.append(f"Odkaz na servis: {parsed_data.get('service_link')}")
    if parsed_data.get("customer_name"):
        lines.append(f"Odběratel: {parsed_data.get('customer_name')}")
    if parsed_data.get("service_summary"):
        lines.append(f"Rozsah prací: {parsed_data.get('service_summary')}")
    if parsed_data.get("technician_name"):
        technician_line = f"Technik: {parsed_data.get('technician_name')}"
        if parsed_data.get("technician_initials"):
            technician_line += f" ({parsed_data.get('technician_initials')})"
        lines.append(technician_line)
    if parsed_data.get("document_number"):
        lines.append(f"Číslo dokladu: {parsed_data.get('document_number')}")
    if parsed_data.get("issue_date"):
        lines.append(f"Datum dokladu: {_to_iso_date(parsed_data.get('issue_date'))}")
    if parsed_data.get("due_date"):
        lines.append(f"Splatnost: {_to_iso_date(parsed_data.get('due_date'))}")
    if parsed_data.get("total_with_vat") is not None:
        lines.append(f"Celkem: {_format_money_for_note(parsed_data.get('total_with_vat'), currency)}")

    items = _normalize_parsed_items(parsed_data)
    if items:
        lines.append("Položky:")
        for item in items[:8]:
            item_line = f"- {item.get('name')}"
            qty = item.get("quantity")
            if qty is not None:
                try:
                    qty_value = float(qty)
                    qty_text = f"{qty_value:g}"
                except Exception:
                    qty_text = str(qty)
                unit = str(item.get("unit") or "").strip()
                item_line += f" ({qty_text}{(' ' + unit) if unit else ''})"
            if item.get("total_price") is not None:
                item_currency = str(item.get("currency") or currency).upper()
                item_line += f" – {_format_money_for_note(item.get('total_price'), item_currency)}"
            lines.append(item_line)
        if len(items) > 8:
            lines.append(f"... a dalších {len(items) - 8} položek")

    cleaned_manual_note = str(manual_note or "").strip()
    if cleaned_manual_note:
        lines.append(f"Poznámka: {cleaned_manual_note}")
    return "\n".join(lines).strip()


def _build_document_prefill_data(
    *,
    source_type: str,
    parsed_data: dict[str, Any],
    extracted_text: str,
    manual_text: Optional[str],
    manual_note: Optional[str],
    fallback_category: Optional[str],
    fallback_mileage: Optional[int],
    fallback_performed_at: Optional[datetime],
    fallback_description: Optional[str],
    fallback_price: Optional[float],
) -> dict[str, Any]:
    issue_date = parsed_data.get("issue_date")
    fallback_dt = fallback_performed_at
    if fallback_dt is not None and fallback_dt.tzinfo is not None:
        fallback_dt = fallback_dt.astimezone().replace(tzinfo=None)
    performed_at = fallback_dt
    if performed_at is None and issue_date is not None:
        try:
            performed_at = datetime.combine(issue_date, datetime.min.time())
        except Exception:
            performed_at = None
    if performed_at is None:
        performed_at = datetime.utcnow()

    parsed_total = parsed_data.get("total_with_vat")
    if parsed_total is None:
        subtotal = parsed_data.get("subtotal_without_vat")
        vat_amount = parsed_data.get("vat_amount")
        if subtotal is not None and vat_amount is not None:
            parsed_total = round(float(subtotal) + float(vat_amount), 2)
    total_price_value = float(fallback_price) if fallback_price is not None else (
        float(parsed_total) if parsed_total is not None else None
    )

    combined_text_for_mileage = "\n".join(
        part for part in [(extracted_text or "").strip(), str(manual_text or "").strip()] if part
    )
    auto_mileage = _extract_mileage_from_text(combined_text_for_mileage)
    mileage_value = fallback_mileage if fallback_mileage is not None else auto_mileage

    description_text = str(fallback_description or "").strip() or _build_service_record_description(parsed_data)
    if not description_text:
        description_text = "Import dokladu"

    category_value = str(fallback_category or "").strip().upper() or _suggest_category_from_parsed_data(
        parsed_data, source_type
    )
    if not category_value:
        category_value = "JINE"

    service_report = _build_service_report_payload(parsed_data, source_type)
    note_text = _build_service_report_note(
        source_type=source_type,
        parsed_data=parsed_data,
        manual_note=manual_note,
    )
    return {
        "performed_at": performed_at,
        "mileage": mileage_value,
        "description": description_text,
        "price": total_price_value,
        "note": note_text or None,
        "category": category_value,
        "service_report": service_report,
    }


@router.post("/{vehicle_id}/records", response_model=ServiceRecordOutV1)
def create_service_record(
    vehicle_id: int,
    record_data: ServiceRecordCreateV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Vytvoří nový servisní záznam"""
    try:
        assert_module_ready(db, "service_records", detail_prefix="Servisní historie není připravena")
        # Kontrola přístupu k vozidlu
        if not can_access_vehicle(vehicle_id, current_user, db):
            raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")
        
        # Načíst vozidlo kvůli tenant kontextu
        vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()
        if not vehicle:
            raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")

        # Tenant kontext je povinný - primárně z vozidla, fallback z uživatele (legacy) a nakonec tenant 1
        tenant_id = vehicle.tenant_id or getattr(current_user, "tenant_id", None) or 1

        # Vytvořit záznam
        user_id = current_user.id
        record = ServiceRecordModel(
            tenant_id=tenant_id,
            vehicle_id=vehicle_id,
            user_id=user_id,
            performed_at=record_data.performed_at,
            mileage=record_data.mileage,
            description=record_data.description,
            price=record_data.price,
            note=record_data.note,
            category=record_data.category,
            attachments=record_data.attachments,
            next_service_due_date=record_data.next_service_due_date
        )
        
        db.add(record)
        db.flush()
        snapshot = _service_record_snapshot(record)
        _, snapshot_hash = _snapshot_json_and_hash(snapshot)
        record.snapshot_hash = snapshot_hash
        db.commit()
        db.refresh(record)
        
        return record
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"[SERVICE_RECORDS] Error creating record for vehicle {vehicle_id}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při vytváření servisního záznamu: {str(e)}")


@router.post("/{vehicle_id}/records/attachments/upload")
def upload_service_record_attachment(
    vehicle_id: int,
    payload: ServiceRecordAttachmentUploadRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Nahraje doklad (PDF/fotka/text) a vrátí metadata pro uložení do attachments záznamu."""
    if not can_access_vehicle(vehicle_id, current_user, db):
        raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")

    vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")

    content = _decode_base64_payload(payload.file_content_base64)
    attachment_meta = _store_attachment_for_vehicle(
        vehicle_id=vehicle_id,
        vehicle=vehicle,
        current_user=current_user,
        file_name=payload.file_name,
        file_mime_type=payload.file_mime_type,
        content=content,
    )
    return {
        "file_name": attachment_meta["file_name"],
        "mime_type": attachment_meta["mime_type"],
        "file_size": attachment_meta["file_size"],
        "storage_key": attachment_meta["storage_key"],
        "download_url": attachment_meta["download_url"],
    }


@router.post("/{vehicle_id}/records/auto-from-document")
def create_service_record_from_document(
    vehicle_id: int,
    payload: ServiceRecordAutoFromDocumentRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Automaticky vytvoří servisní záznam z nahraného dokladu (PDF/fotka/text).
    Používá stejný parser jako servisní workspace, aby se neduplikovala logika.
    """
    if not can_access_vehicle(vehicle_id, current_user, db):
        raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")

    vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")

    source_type = str(payload.source_type or "invoice").strip().lower()
    if source_type not in ALLOWED_SOURCE_TYPES:
        raise HTTPException(status_code=422, detail="Neplatný typ dokladu.")

    raw_content = _decode_base64_payload(payload.file_content_base64)
    attachment_meta = _store_attachment_for_vehicle(
        vehicle_id=vehicle_id,
        vehicle=vehicle,
        current_user=current_user,
        file_name=payload.file_name,
        file_mime_type=payload.file_mime_type,
        content=raw_content,
    )

    extracted_text, extraction_warning, extraction_engine = _extract_text_from_file(
        content=raw_content,
        file_name=payload.file_name,
        mime_type=payload.file_mime_type,
    )

    parsed_data = _parse_document_payload(
        source_type=source_type,
        extracted_text=extracted_text,
        manual_text=payload.manual_text,
        manual_note=payload.manual_note,
        extraction_engine=extraction_engine,
        extraction_warning=extraction_warning,
    )

    parse_confidence = float(parsed_data.get("confidence") or 0.0)
    processing_status = "processed"
    if not ((extracted_text or "").strip() or str(payload.manual_text or "").strip()):
        processing_status = "failed"
    elif parse_confidence < 0.35:
        processing_status = "needs_review"

    prefill = _build_document_prefill_data(
        source_type=source_type,
        parsed_data=parsed_data,
        extracted_text=extracted_text,
        manual_text=payload.manual_text,
        manual_note=payload.manual_note,
        fallback_category=payload.fallback_category,
        fallback_mileage=payload.fallback_mileage,
        fallback_performed_at=payload.fallback_performed_at,
        fallback_description=payload.fallback_description,
        fallback_price=payload.fallback_price,
    )

    attachments_payload = json.dumps(
        [
            {
                "kind": "user_document",
                "file_name": attachment_meta["file_name"],
                "mime_type": attachment_meta["mime_type"],
                "file_size": attachment_meta["file_size"],
                "storage_key": attachment_meta["storage_key"],
                "download_url": attachment_meta["download_url"],
                "source_type": source_type,
                "parsed_summary": prefill["service_report"],
            }
        ],
        ensure_ascii=False,
    )

    tenant_id = vehicle.tenant_id or getattr(current_user, "tenant_id", None) or 1
    record = ServiceRecordModel(
        tenant_id=tenant_id,
        vehicle_id=vehicle_id,
        user_id=current_user.id,
        performed_at=prefill["performed_at"],
        mileage=prefill["mileage"],
        description=prefill["description"],
        price=prefill["price"],
        note=prefill["note"],
        category=prefill["category"],
        attachments=attachments_payload,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return {
        "record": record,
        "processing_status": processing_status,
        "parse_confidence": parse_confidence,
        "parsed_data": parsed_data,
        "prefill": prefill,
        "extraction_engine": extraction_engine,
        "extraction_warning": extraction_warning,
    }


@router.post("/{vehicle_id}/records/document-prefill")
def preview_service_record_from_document(
    vehicle_id: int,
    payload: ServiceRecordDocumentPrefillRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Vytěží data z dokladu a vrátí předvyplnění formuláře servisního záznamu.
    Záznam se v této fázi NEukládá.
    """
    if not can_access_vehicle(vehicle_id, current_user, db):
        raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")

    vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")

    source_type = str(payload.source_type or "invoice").strip().lower()
    if source_type not in ALLOWED_SOURCE_TYPES:
        raise HTTPException(status_code=422, detail="Neplatný typ dokladu.")

    raw_content = _decode_base64_payload(payload.file_content_base64)
    extracted_text, extraction_warning, extraction_engine = _extract_text_from_file(
        content=raw_content,
        file_name=payload.file_name,
        mime_type=payload.file_mime_type,
    )
    parsed_data = _parse_document_payload(
        source_type=source_type,
        extracted_text=extracted_text,
        manual_text=payload.manual_text,
        manual_note=payload.manual_note,
        extraction_engine=extraction_engine,
        extraction_warning=extraction_warning,
    )

    parse_confidence = float(parsed_data.get("confidence") or 0.0)
    processing_status = "processed"
    if not ((extracted_text or "").strip() or str(payload.manual_text or "").strip()):
        processing_status = "failed"
    elif parse_confidence < 0.35:
        processing_status = "needs_review"

    prefill = _build_document_prefill_data(
        source_type=source_type,
        parsed_data=parsed_data,
        extracted_text=extracted_text,
        manual_text=payload.manual_text,
        manual_note=payload.manual_note,
        fallback_category=payload.fallback_category,
        fallback_mileage=payload.fallback_mileage,
        fallback_performed_at=payload.fallback_performed_at,
        fallback_description=payload.fallback_description,
        fallback_price=payload.fallback_price,
    )

    return {
        "processing_status": processing_status,
        "parse_confidence": parse_confidence,
        "parsed_data": parsed_data,
        "prefill": prefill,
        "extraction_engine": extraction_engine,
        "extraction_warning": extraction_warning,
    }


@router.get("/{vehicle_id}/records/attachments/download")
def download_service_record_attachment(
    vehicle_id: int,
    key: str = Query(..., min_length=3, max_length=500),
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Bezpečné stažení přílohy servisního záznamu."""
    if not can_access_vehicle(vehicle_id, current_user, db):
        raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")

    vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")

    expected_segment = f"/vehicle_{vehicle_id}/"
    normalized_key = str(key or "").replace("\\", "/")
    if expected_segment not in f"/{normalized_key}":
        raise HTTPException(status_code=403, detail="Příloha nepatří k tomuto vozidlu.")

    attachment_file = _resolve_attachment_file(normalized_key)
    if not attachment_file or not attachment_file.is_file():
        raise HTTPException(status_code=404, detail="Příloha nebyla nalezena.")

    media_type = mimetypes.guess_type(str(attachment_file.name))[0] or "application/octet-stream"
    safe_filename_ascii = attachment_file.name.encode("ascii", "ignore").decode("ascii") or "doklad"
    safe_filename_utf8 = quote(attachment_file.name, safe="")
    content_disposition = f'inline; filename="{safe_filename_ascii}"; filename*=UTF-8\'\'{safe_filename_utf8}'
    return FileResponse(
        path=str(attachment_file),
        media_type=media_type,
        headers={"Content-Disposition": content_disposition},
    )


@router.get("/{vehicle_id}/pdf", name="generate_pdf")
def generate_service_records_pdf(
    vehicle_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Vygeneruje PDF s historií servisních záznamů pro vozidlo.
    
    PDF obsahuje:
    - Hlavičku s informacemi o vozidle (název, VIN, SPZ, atd.)
    - Seznam všech servisních záznamů
    - Pod každým záznamem poznámku menším písmem
    """
    try:
        from fastapi.responses import FileResponse
        from pathlib import Path
        from datetime import datetime, date
        
        # Kontrola přístupu k vozidlu
        if not can_access_vehicle(vehicle_id, current_user, db):
            raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")
        
        # Načíst vozidlo
        vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()
        if not vehicle:
            raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
        
        # Načíst všechny záznamy - řadit podle data (nejstarší první pro PDF)
        records = db.query(ServiceRecordModel).filter(
            ServiceRecordModel.vehicle_id == vehicle_id
        ).order_by(nullslast(ServiceRecordModel.performed_at.asc())).all()
        
        # Zkontrolovat, zda je dostupný ReportLab
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.pdfgen import canvas
            from reportlab.lib.units import mm
            from reportlab.lib import colors
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
            from reportlab.lib.enums import TA_LEFT, TA_CENTER
            REPORTLAB_AVAILABLE = True
        except ImportError:
            REPORTLAB_AVAILABLE = False
            raise HTTPException(
                status_code=500,
                detail="Generování PDF není dostupné. ReportLab není nainstalován."
            )
        
        # Vytvořit PDF
        from src.core.config import PDF_DIR
        PDF_DIR.mkdir(parents=True, exist_ok=True)
        
        # Název souboru - zajistit ASCII kompatibilitu
        vehicle_name = vehicle.nickname or vehicle.plate or f"vozidlo_{vehicle_id}"
        # Odstranit diakritiku a speciální znaky pro název souboru
        import unicodedata
        safe_name = unicodedata.normalize('NFKD', str(vehicle_name))
        safe_name = ''.join(c for c in safe_name if not unicodedata.combining(c))
        # Převést na ASCII - odstranit všechny ne-ASCII znaky
        safe_name = safe_name.encode('ascii', 'ignore').decode('ascii')
        safe_name = "".join(c for c in safe_name if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_name = safe_name.replace(' ', '_')[:50]  # Omezit délku
        if not safe_name:  # Pokud by bylo prázdné, použít výchozí
            safe_name = f"vozidlo_{vehicle_id}"
        filename = f"servisni_zaznamy_{safe_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        pdf_path = PDF_DIR / filename
        
        # Pomocná funkce pro escape HTML a UTF-8
        def escape_html(text):
            """Escape HTML znaků a zajistí UTF-8 kompatibilitu"""
            if text is None:
                return ""
            text = str(text)
            # Escape HTML znaků - důležité pro ReportLab Paragraph
            text = text.replace('&', '&amp;')
            text = text.replace('<', '&lt;')
            text = text.replace('>', '&gt;')
            text = text.replace('"', '&quot;')
            text = text.replace("'", '&#39;')
            # Odstranit LaTeX matematické symboly, které ReportLab může interpretovat špatně
            text = text.replace('$', '')
            text = text.replace('\\', '')
            return text
        
        # Pomocná funkce pro formátování čísel bez LaTeX
        def format_number(num):
            """Formátuje číslo bez LaTeX matematických symbolů"""
            if num is None:
                return ""
            try:
                # Použít jednoduché formátování s mezerou jako oddělovač tisíců
                return f"{num:,.0f}".replace(',', ' ')
            except (ValueError, TypeError):
                return str(num)
        
        # Vytvořit PDF dokument s footerem
        def add_footer(canvas_obj, doc):
            """Přidá footer s datem a číslem stránky"""
            canvas_obj.saveState()
            canvas_obj.setFont('Helvetica', 8)
            canvas_obj.setFillColor(colors.HexColor('#64748b'))
            
            # Datum generování - bez českých znaků pro drawString
            gen_date = datetime.now().strftime('%d.%m.%Y %H:%M')
            footer_text = f"Vygenerovano: {gen_date}"
            canvas_obj.drawString(20*mm, 15*mm, footer_text)
            
            # Číslo stránky
            page_num = canvas_obj.getPageNumber()
            canvas_obj.drawRightString(190*mm, 15*mm, f"Stranka {page_num}")
            
            canvas_obj.restoreState()
        
        # Zajistit, že cesta k PDF je ASCII-safe (pro Windows kompatibilitu)
        pdf_path_str = str(pdf_path)
        try:
            # Zkusit vytvořit PDF s UTF-8 cestou
            doc = SimpleDocTemplate(
                pdf_path_str, 
                pagesize=A4,
                rightMargin=20*mm,
                leftMargin=20*mm,
                topMargin=30*mm,
                bottomMargin=25*mm
            )
        except (UnicodeEncodeError, OSError) as e:
            # Pokud selže, použít ASCII-safe cestu
            import tempfile
            temp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix='.pdf', dir=str(PDF_DIR))
            temp_pdf.close()
            pdf_path = Path(temp_pdf.name)
            doc = SimpleDocTemplate(
                str(pdf_path), 
                pagesize=A4,
                rightMargin=20*mm,
                leftMargin=20*mm,
                topMargin=30*mm,
                bottomMargin=25*mm
            )
        story = []
        styles = getSampleStyleSheet()
        
        # Profesionální barvy
        primary_color = colors.HexColor('#0f172a')  # Tmavě modrá
        secondary_color = colors.HexColor('#1e40af')  # Modrá
        accent_color = colors.HexColor('#3b82f6')  # Světle modrá
        text_color = colors.HexColor('#1e293b')  # Tmavě šedá
        light_gray = colors.HexColor('#f8fafc')  # Velmi světle šedá
        border_color = colors.HexColor('#e2e8f0')  # Světle šedá
        muted_text = colors.HexColor('#64748b')  # Šedá
        
        # Vlastní styly
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=primary_color,
            spaceAfter=8,
            spaceBefore=0,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        )
        
        subtitle_style = ParagraphStyle(
            'CustomSubtitle',
            parent=styles['Normal'],
            fontSize=10,
            textColor=muted_text,
            spaceAfter=20,
            alignment=TA_CENTER,
            fontName='Helvetica'
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontSize=16,
            textColor=primary_color,
            spaceAfter=12,
            spaceBefore=20,
            fontName='Helvetica-Bold',
            borderWidth=0,
            borderPadding=0
        )
        
        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontSize=10,
            textColor=text_color,
            spaceAfter=8,
            leading=14,
            fontName='Helvetica'
        )
        
        note_style = ParagraphStyle(
            'CustomNote',
            parent=styles['Normal'],
            fontSize=9,
            textColor=muted_text,
            spaceAfter=10,
            leftIndent=15,
            leading=12,
            fontName='Helvetica-Oblique'
        )
        
        record_title_style = ParagraphStyle(
            'RecordTitle',
            parent=styles['Normal'],
            fontSize=11,
            textColor=primary_color,
            spaceAfter=4,
            fontName='Helvetica-Bold',
            leading=14
        )
        
        # Hlavička s dekorativním pruhem
        header_table_data = [
            [Paragraph("<b>HISTORIE SERVISNÍCH ZÁZNAMŮ</b>", title_style)]
        ]
        header_table = Table(header_table_data, colWidths=[170*mm])
        header_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), secondary_color),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTSIZE', (0, 0), (-1, -1), 24),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 15),
            ('TOPPADDING', (0, 0), (-1, -1), 15),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ]))
        story.append(header_table)
        story.append(Spacer(1, 15))
        
        # Tabulka s informacemi o vozidle - profesionální design
        vehicle_data = []
        if vehicle.nickname:
            vehicle_data.append(["Název vozidla", escape_html(vehicle.nickname)])
        if vehicle.brand:
            vehicle_data.append(["Značka", escape_html(vehicle.brand)])
        if vehicle.model:
            vehicle_data.append(["Model", escape_html(vehicle.model)])
        if vehicle.year:
            vehicle_data.append(["Rok výroby", str(vehicle.year)])
        if vehicle.vin:
            vehicle_data.append(["VIN", escape_html(vehicle.vin)])
        if vehicle.plate:
            vehicle_data.append(["SPZ", escape_html(vehicle.plate)])
        if vehicle.engine:
            vehicle_data.append(["Motor", escape_html(vehicle.engine)])
        
        if vehicle_data:
            # Přidat prázdný řádek pro lepší vzhled
            vehicle_table = Table(vehicle_data, colWidths=[60*mm, 110*mm])
            vehicle_table.setStyle(TableStyle([
                # Hlavička (první řádek)
                ('BACKGROUND', (0, 0), (0, -1), light_gray),
                ('TEXTCOLOR', (0, 0), (0, -1), primary_color),
                ('TEXTCOLOR', (1, 0), (1, -1), text_color),
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                ('ALIGN', (1, 0), (1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
                ('TOPPADDING', (0, 0), (-1, -1), 10),
                ('LEFTPADDING', (0, 0), (-1, -1), 12),
                ('RIGHTPADDING', (0, 0), (-1, -1), 12),
                ('GRID', (0, 0), (-1, -1), 1, border_color),
                ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, light_gray]),
            ]))
            story.append(vehicle_table)
            story.append(Spacer(1, 25))
        
        # Souhrn (pokud jsou záznamy)
        if records:
            total_price = sum(r.price or 0 for r in records)
            total_records = len(records)
            # Formátovat cenu bez LaTeX matematických symbolů
            if total_price > 0:
                price_str = format_number(total_price)
                price_display = f"{price_str} Kč"
            else:
                price_display = "Nezadáno"
            summary_data = [
                ["Celkový počet záznamů", str(total_records)],
                ["Celková cena servisů", price_display]
            ]
            summary_table = Table(summary_data, colWidths=[100*mm, 70*mm])
            summary_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, -1), accent_color),
                ('TEXTCOLOR', (0, 0), (-1, -1), colors.white),
                ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 11),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
                ('TOPPADDING', (0, 0), (-1, -1), 10),
                ('LEFTPADDING', (0, 0), (-1, -1), 12),
                ('RIGHTPADDING', (0, 0), (-1, -1), 12),
            ]))
            story.append(summary_table)
            story.append(Spacer(1, 20))
        
        # Seznam záznamů
        story.append(Paragraph("SERVISNÍ ZÁZNAMY", heading_style))
        
        if not records:
            empty_style = ParagraphStyle(
                'EmptyStyle',
                parent=styles['Normal'],
                fontSize=11,
                textColor=muted_text,
                spaceAfter=20,
                alignment=TA_CENTER,
                fontName='Helvetica-Oblique'
            )
            story.append(Paragraph("Zatím nebyly přidány žádné servisní záznamy.", empty_style))
        else:
            # Kategorie mapování (bez emoji pro lepší kompatibilitu)
            category_map = {
                'OLEJ': 'Olej',
                'BRZDY': 'Brzdy',
                'PNEU': 'Pneumatiky',
                'STK': 'STK',
                'DIAGNOSTIKA': 'Diagnostika',
                'FILTRY': 'Filtry',
                'CHLADICI': 'Chladicí systém',
                'VYFUK': 'Výfuk',
                'OSVETLENI': 'Osvětlení',
                'KAROSERIE': 'Karoserie',
                'INTERIER': 'Interiér',
                'ELEKTRIKA': 'Elektrika',
                'KLIMATIZACE': 'Klimatizace',
                'PREVENTIVNI': 'Preventivní',
                'OPRAVA': 'Oprava',
                'JINE': 'Jiné'
            }
            
            for i, record in enumerate(records, 1):
                # Datum
                if record.performed_at:
                    try:
                        if isinstance(record.performed_at, datetime):
                            date_str = record.performed_at.strftime('%d.%m.%Y %H:%M')
                        elif isinstance(record.performed_at, date):
                            date_str = record.performed_at.strftime('%d.%m.%Y')
                        else:
                            date_str = str(record.performed_at)
                    except (AttributeError, TypeError):
                        date_str = 'Nezadáno'
                else:
                    date_str = 'Nezadáno'
                
                # Kategorie
                category_display = category_map.get(record.category, record.category or 'Jiné')
                
                # Popis - escape HTML pro UTF-8
                description = escape_html(record.description or 'Bez popisu')
                
                # Hlavní řádek záznamu
                record_title = f"<b>{i}. {escape_html(category_display)}</b>"
                story.append(Paragraph(record_title, record_title_style))
                
                # Popis
                story.append(Paragraph(description, normal_style))
                
                # Detaily v tabulce
                details_data = []
                if record.mileage:
                    mileage_str = format_number(record.mileage)
                    details_data.append(["Nájezd", f"{mileage_str} km"])
                if record.price:
                    price_str = format_number(record.price)
                    details_data.append(["Cena", f"{price_str} Kč"])
                details_data.append(["Datum", escape_html(date_str)])
                
                if details_data:
                    details_table = Table(details_data, colWidths=[40*mm, 130*mm])
                    details_table.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (0, -1), light_gray),
                        ('TEXTCOLOR', (0, 0), (0, -1), muted_text),
                        ('TEXTCOLOR', (1, 0), (1, -1), text_color),
                        ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
                        ('FONTNAME', (0, 0), (0, -1), 'Helvetica'),
                        ('FONTNAME', (1, 0), (1, -1), 'Helvetica'),
                        ('FONTSIZE', (0, 0), (-1, -1), 9),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                        ('TOPPADDING', (0, 0), (-1, -1), 6),
                        ('LEFTPADDING', (0, 0), (-1, -1), 8),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
                        ('GRID', (0, 0), (-1, -1), 0.5, border_color),
                    ]))
                    story.append(details_table)
                
                # Poznámka (pokud existuje) - escape HTML
                if record.note:
                    note_text = escape_html(record.note)
                    story.append(Paragraph(f"Poznámka: {note_text}", note_style))
                
                # Oddělovač (kromě posledního)
                if i < len(records):
                    story.append(Spacer(1, 12))
        
        # Vytvořit PDF s footerem
        doc.build(story, onFirstPage=add_footer, onLaterPages=add_footer)
        
        # Vrátit soubor s Content-Disposition headerem
        from fastapi.responses import Response
        from urllib.parse import quote
        
        with open(pdf_path, 'rb') as f:
            pdf_content = f.read()
        
        # Kódovat název souboru pro Content-Disposition header (RFC 5987)
        # Použít ASCII-safe název a UTF-8 encoded verzi
        safe_filename_ascii = filename.encode('ascii', 'ignore').decode('ascii')
        safe_filename_utf8 = quote(filename, safe='')
        
        # Content-Disposition s podporou UTF-8 (RFC 5987)
        content_disposition = f'attachment; filename="{safe_filename_ascii}"; filename*=UTF-8\'\'{safe_filename_utf8}'
        
        return Response(
            content=pdf_content,
            media_type='application/pdf',
            headers={
                'Content-Disposition': content_disposition
            }
        )
    except HTTPException:
        raise
    except UnicodeEncodeError as e:
        print(f"[SERVICE_RECORDS] Unicode encoding error generating PDF for vehicle {vehicle_id}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500, 
            detail=f"Chyba při generování PDF: Problém s kódováním znaků. Zkuste použít název vozidla bez diakritiky."
        )
    except Exception as e:
        print(f"[SERVICE_RECORDS] Error generating PDF for vehicle {vehicle_id}: {e}")
        import traceback
        traceback.print_exc()
        # Zkusit získat více informací o chybě
        error_msg = str(e)
        if 'latin-1' in error_msg or 'codec' in error_msg.lower():
            error_msg = "Chyba kódování: Text obsahuje znaky, které nelze zakódovat. Zkuste použít název vozidla bez diakritiky."
        raise HTTPException(status_code=500, detail=f"Chyba při generování PDF: {error_msg}")


@router.get("/{vehicle_id}/records", response_model=List[ServiceRecordOutV1])
def get_service_records(
    vehicle_id: int,
    include_deleted: bool = Query(default=False),
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Vrací všechny servisní záznamy pro vozidlo"""
    try:
        assert_module_ready(db, "service_records", detail_prefix="Servisní historie není připravena")
        # Kontrola přístupu k vozidlu
        if not can_access_vehicle(vehicle_id, current_user, db):
            raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")
        
        # Načíst záznamy - řadit podle performed_at (nejnovější první)
        query = db.query(ServiceRecordModel).filter(
            ServiceRecordModel.vehicle_id == vehicle_id
        )
        if not include_deleted:
            query = query.filter(ServiceRecordModel.is_deleted.is_(False))
        records = query.order_by(nullslast(desc(ServiceRecordModel.performed_at))).all()
        
        return records
    except HTTPException:
        raise
    except Exception as e:
        print(f"[SERVICE_RECORDS] Error getting records for vehicle {vehicle_id}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání servisních záznamů: {str(e)}")


@router.get("/{vehicle_id}/records/{record_id}", response_model=ServiceRecordOutV1)
def get_service_record(
    vehicle_id: int,
    record_id: int,
    include_deleted: bool = Query(default=False),
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Vrací konkrétní servisní záznam"""
    try:
        assert_module_ready(db, "service_records", detail_prefix="Servisní historie není připravena")
        # Kontrola přístupu k vozidlu
        if not can_access_vehicle(vehicle_id, current_user, db):
            raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")
        
        record = db.query(ServiceRecordModel).filter(
            ServiceRecordModel.id == record_id,
            ServiceRecordModel.vehicle_id == vehicle_id
        ).first()
        
        if not record:
            raise HTTPException(status_code=404, detail="Servisní záznam nenalezen")
        if bool(getattr(record, "is_deleted", False)) and not include_deleted:
            raise HTTPException(status_code=404, detail="Servisní záznam byl archivován")

        refreshed = _refresh_record_attachments_summary(record)
        if refreshed:
            db.add(record)
            db.commit()
            db.refresh(record)

        return record
    except HTTPException:
        raise
    except Exception as e:
        print(f"[SERVICE_RECORDS] Error getting record {record_id} for vehicle {vehicle_id}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání servisního záznamu: {str(e)}")


@router.put("/{vehicle_id}/records/{record_id}", response_model=ServiceRecordOutV1)
def update_service_record(
    vehicle_id: int,
    record_id: int,
    record_data: ServiceRecordUpdateV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Aktualizuje servisní záznam.
    POZOR: Záznamy vytvořené AI asistentem (created_by_ai=True) nelze smazat, pouze upravit.
    """
    try:
        assert_module_ready(db, "service_records", detail_prefix="Servisní historie není připravena")
        # Kontrola přístupu k vozidlu
        if not can_access_vehicle(vehicle_id, current_user, db):
            raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")
        
        record = db.query(ServiceRecordModel).filter(
            ServiceRecordModel.id == record_id,
            ServiceRecordModel.vehicle_id == vehicle_id
        ).first()
        
        if not record:
            raise HTTPException(status_code=404, detail="Servisní záznam nenalezen")
        if bool(getattr(record, "is_deleted", False)):
            raise HTTPException(status_code=409, detail="Archivovaný servisní záznam nelze upravovat")

        previous_snapshot = _service_record_snapshot(record)
        
        # Aktualizace polí
        if record_data.performed_at is not None:
            record.performed_at = record_data.performed_at
        if record_data.mileage is not None:
            record.mileage = record_data.mileage
        if record_data.description is not None:
            record.description = record_data.description
        if record_data.price is not None:
            record.price = record_data.price
        if record_data.note is not None:
            record.note = record_data.note
        if record_data.category is not None:
            record.category = record_data.category
        if record_data.attachments is not None:
            record.attachments = record_data.attachments
        if record_data.next_service_due_date is not None:
            record.next_service_due_date = record_data.next_service_due_date

        new_snapshot = _service_record_snapshot(record)
        previous_snapshot_json, _ = _snapshot_json_and_hash(previous_snapshot)
        new_snapshot_json, snapshot_hash = _snapshot_json_and_hash(new_snapshot)
        record.snapshot_hash = snapshot_hash
        db.add(
            ServiceRecordAuditLog(
                tenant_id=record.tenant_id,
                service_record_id=record.id,
                vehicle_id=record.vehicle_id,
                changed_by_user_id=getattr(current_user, "id", None),
                action="update",
                previous_snapshot_json=previous_snapshot_json,
                new_snapshot_json=new_snapshot_json,
                snapshot_hash=snapshot_hash,
                change_reason=None,
            )
        )
        
        db.commit()
        db.refresh(record)
        
        return record
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"[SERVICE_RECORDS] Error updating record {record_id} for vehicle {vehicle_id}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při aktualizaci servisního záznamu: {str(e)}")


@router.delete("/{vehicle_id}/records/{record_id}")
def delete_service_record(
    vehicle_id: int,
    record_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Archivuje servisní záznam bez fyzického smazání.
    POZOR: Záznamy vytvořené AI asistentem (created_by_ai=True) nelze archivovat.
    """
    try:
        assert_module_ready(db, "service_records", detail_prefix="Servisní historie není připravena")
        # Kontrola přístupu k vozidlu
        if not can_access_vehicle(vehicle_id, current_user, db):
            raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")

        record = db.query(ServiceRecordModel).filter(
            ServiceRecordModel.id == record_id,
            ServiceRecordModel.vehicle_id == vehicle_id
        ).first()

        if not record:
            raise HTTPException(status_code=404, detail="Servisní záznam nenalezen")
        if bool(getattr(record, "is_deleted", False)):
            return {"message": "Servisní záznam je již archivovaný"}
        
        # Zakázat mazání záznamů vytvořených AI asistentem
        if record.created_by_ai:
            raise HTTPException(
                status_code=403,
                detail="Záznam vytvořený AI asistentem nelze smazat. Můžete ho pouze upravit."
            )

        previous_snapshot = _service_record_snapshot(record)
        record.is_deleted = True
        record.deleted_at = datetime.utcnow()
        record.deleted_by_user_id = getattr(current_user, "id", None)
        record.deletion_reason = "user_delete"
        new_snapshot = _service_record_snapshot(record)
        previous_snapshot_json, _ = _snapshot_json_and_hash(previous_snapshot)
        new_snapshot_json, snapshot_hash = _snapshot_json_and_hash(new_snapshot)
        record.snapshot_hash = snapshot_hash
        db.add(
            ServiceRecordAuditLog(
                tenant_id=record.tenant_id,
                service_record_id=record.id,
                vehicle_id=record.vehicle_id,
                changed_by_user_id=getattr(current_user, "id", None),
                action="delete",
                previous_snapshot_json=previous_snapshot_json,
                new_snapshot_json=new_snapshot_json,
                snapshot_hash=snapshot_hash,
                change_reason="user_delete",
            )
        )
        db.commit()
        
        return {"message": "Servisní záznam byl archivován"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"[SERVICE_RECORDS] Error deleting record {record_id} for vehicle {vehicle_id}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při mazání servisního záznamu: {str(e)}")
