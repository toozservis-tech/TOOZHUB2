"""
Vehicles API v1.0 router
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
import base64
import binascii
import html
from io import BytesIO
import json
import mimetypes
from pathlib import Path
import re
import secrets
import threading
import unicodedata
from urllib.parse import urljoin

from fastapi import APIRouter, HTTPException, Depends, Body
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import requests
from sqlalchemy.orm import Session
from typing import Any, Dict, List, Optional

try:
    from PIL import Image, ImageOps, UnidentifiedImageError
    PILLOW_AVAILABLE = True
except Exception:
    Image = None
    ImageOps = None
    UnidentifiedImageError = Exception
    PILLOW_AVAILABLE = False

from src.core.config import DATA_DIR
from src.core.rbac import is_admin, vehicle_write_policy
from ..database import get_db
from ..models import (
    Vehicle as VehicleModel,
    Customer,
    ServiceRecord as ServiceRecordModel,
    VehicleTachometerHistoryEntry as VehicleTachometerHistoryEntryModel,
)
from ..orv_scans import apply_orv_scan_to_vehicle, create_orv_scan_record, serialize_orv_scan
from ..ownership import (
    backfill_vehicle_owner_assignment,
    ensure_vehicle_owner_assignment,
    get_current_owner_since,
    get_primary_vehicle_owner,
    get_primary_vehicle_owner_assignment,
    release_vehicle_owner_assignment,
    transfer_vehicle_to_new_owner,
    user_owns_vehicle,
)
from ..schema_management import assert_module_ready
from .auth import get_current_user, can_access_vehicle
from .schemas import (
    VehicleCreateV1,
    VehicleUpdateV1,
    VehicleOutV1,
    VehicleMileageRecordResultV1,
    VehicleMileageRecordV1,
    ORVParseRequestV1,
    ORVParseResponseV1,
)

router = APIRouter(prefix="/vehicles", tags=["vehicles-v1"])

VEHICLE_PHOTOS_DIR = DATA_DIR / "vehicle_photos"
VEHICLE_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
MAX_VEHICLE_PHOTO_RAW_SIZE_BYTES = 40 * 1024 * 1024
MAX_VEHICLE_PHOTO_OUTPUT_SIZE_BYTES = 10 * 1024 * 1024
VEHICLE_PHOTO_TARGET_SIZE = (1280, 720)
VEHICLE_PHOTO_JPEG_QUALITY = 82
VEHICLE_PHOTO_MIN_JPEG_QUALITY = 52


class VehiclePhotoUploadRequest(BaseModel):
    file_name: str = Field(..., min_length=1, max_length=255)
    file_mime_type: str = Field(default="image/jpeg", max_length=255)
    file_content_base64: str = Field(..., min_length=20, max_length=60_000_000)


TACHOMETER_BASE_URL = "https://www.kontrolatachometru.cz"
TACHOMETER_LANDING_PATH = "/"
TACHOMETER_SEARCH_PATH = "/Home/Search"
TACHOMETER_CHALLENGE_TTL_SECONDS = 10 * 60
_TACHOMETER_HTTP_TIMEOUT_SECONDS = 20
_TACHOMETER_CAPTCHA_ERROR_TEXT = "Špatně opsaný kód z obrázku"
_TACHOMETER_CHALLENGE_STORE: Dict[str, Dict[str, Any]] = {}
_TACHOMETER_CHALLENGE_LOCK = threading.Lock()


class TachometerChallengeResponse(BaseModel):
    challenge_id: str
    captcha_image_base64: str
    captcha_mime_type: str
    expires_in_seconds: int


class TachometerChallengeRequest(BaseModel):
    vin: Optional[str] = Field(default=None, min_length=5, max_length=32)


class TachometerLookupRequest(BaseModel):
    challenge_id: str = Field(..., min_length=10, max_length=255)
    vin: str = Field(..., min_length=5, max_length=32)
    captcha_code: str = Field(..., min_length=2, max_length=16)


class TachometerInspectionOut(BaseModel):
    check_date: Optional[datetime] = None
    mileage_km: int
    protocol_number: Optional[str] = None
    inspection_type: Optional[str] = None
    findings_summary: Optional[str] = None
    findings_items: List[str] = []
    detail_available: bool = False
    detail_snapshot_json: Optional[Dict[str, Any]] = None
    source_detail_reference: Optional[Dict[str, Any]] = None
    documents: List[Dict[str, Any]] = []


class TachometerLookupResponse(BaseModel):
    vin: str
    latest_mileage_km: int
    latest_check_date: Optional[datetime] = None
    inspections: List[TachometerInspectionOut]
    source: str = "kontrolatachometru.cz"


class VehicleTachometerInitResponse(BaseModel):
    session_id: str
    captcha_image_base64: str
    captcha_mime_type: str
    expires_in_seconds: int


class VehicleTachometerSubmitRequest(BaseModel):
    session_id: str = Field(..., min_length=10, max_length=255)
    captcha_code: str = Field(..., min_length=2, max_length=16)


class VehicleTachometerSubmitResponse(BaseModel):
    vehicle: VehicleOutV1
    latest_mileage_km: int
    latest_check_date: Optional[datetime] = None
    inspections: List[TachometerInspectionOut]
    created_record_id: int
    source: str = "kontrolatachometru.cz"


class VehicleTachometerHistoryEntryResponse(BaseModel):
    id: int
    check_date: Optional[datetime] = None
    mileage_km: Optional[int] = None
    protocol_number: Optional[str] = None
    inspection_type: Optional[str] = None
    source: Optional[str] = None
    status: str = "imported"
    summary: Optional[str] = None
    findings_summary: Optional[str] = None
    findings_items: List[str] = []
    detail_available: bool = False
    detail_snapshot_json: Optional[Dict[str, Any]] = None
    source_detail_reference: Optional[Dict[str, Any]] = None
    is_monotonic_valid: bool = True
    anomaly: bool = False
    anomaly_type: Optional[str] = None
    anomaly_delta_km: Optional[int] = None
    merged_duplicate_count: int = 0
    merged_entry_ids: List[int] = []
    merge_reason: Optional[str] = None
    has_documents: bool = False
    documents_count: int = 0
    documents: List[VehicleTachometerDocumentResponse] = []


class VehicleTachometerDocumentResponse(BaseModel):
    document_id: str
    title: str
    document_type: str
    available: bool
    open_mode: str
    reason: Optional[str] = None
    external_url: Optional[str] = None
    internal_proxy_url: Optional[str] = None
    source_reference: Optional[str] = None


class VehicleTachometerHistoryEntryDetailResponse(VehicleTachometerHistoryEntryResponse):
    pass


@dataclass
class _NormalizedTachometerHistoryItem:
    canonical_entry: VehicleTachometerHistoryEntryModel
    merged_entries: list[VehicleTachometerHistoryEntryModel]
    is_monotonic_valid: bool = True
    anomaly: bool = False
    anomaly_type: str | None = None
    anomaly_delta_km: int | None = None
    merge_reason: str | None = None


def _ensure_vehicle_schema_columns(db: Session) -> None:
    assert_module_ready(db, "vehicles", detail_prefix="Modul vozidel není připraven")


def _ensure_vehicle_photo_column(db: Session) -> None:
    """
    Backward-compatible alias používaný napříč routery.
    """
    _ensure_vehicle_schema_columns(db)


def _cleanup_tachometer_challenge_store() -> None:
    threshold = datetime.utcnow() - timedelta(seconds=TACHOMETER_CHALLENGE_TTL_SECONDS)
    with _TACHOMETER_CHALLENGE_LOCK:
        expired = [
            challenge_id
            for challenge_id, data in _TACHOMETER_CHALLENGE_STORE.items()
            if data.get("created_at") is None or data["created_at"] < threshold
        ]
        for challenge_id in expired:
            _TACHOMETER_CHALLENGE_STORE.pop(challenge_id, None)


def _normalize_vin(raw: str) -> str:
    value = re.sub(r"[^A-Za-z0-9]", "", str(raw or "").upper())
    return value.strip()


def _strip_html(raw: str | None) -> str:
    if not raw:
        return ""
    no_tags = re.sub(r"<[^>]+>", "", raw, flags=re.S)
    text = html.unescape(no_tags).replace("\xa0", " ")
    return " ".join(text.split())


def _extract_hidden_token(page_html: str) -> str | None:
    match = re.search(
        r'name="__RequestVerificationToken"\s+type="hidden"\s+value="([^"]+)"',
        page_html,
        flags=re.I,
    )
    if match:
        return match.group(1)
    return None


def _extract_captcha_src(page_html: str) -> str | None:
    match = re.search(r'<img[^>]+id="captcha_IMG"[^>]+src="([^"]+)"', page_html, flags=re.I)
    if match:
        return match.group(1)
    return None


def _contains_captcha_error(page_html: str) -> bool:
    decoded = html.unescape(page_html or "").lower()
    normalized_ascii = (
        unicodedata.normalize("NFKD", decoded).encode("ascii", "ignore").decode("ascii")
    )
    return (
        "špatně opsaný kód z obrázku" in decoded
        or "spatne opsany kod z obrazku" in normalized_ascii
        or "submitted code is incorrect" in decoded
    )


def _parse_km_value(raw: str | None) -> int | None:
    if not raw:
        return None
    digits = re.sub(r"[^0-9]", "", _strip_html(raw))
    if not digits:
        return None
    return int(digits)


def _parse_cz_date(raw: str | None) -> datetime | None:
    value = _strip_html(raw)
    if not value:
        return None
    for fmt in ("%d.%m.%Y", "%d.%m.%Y %H:%M", "%d.%m.%Y %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _extract_td_value(row_html: str, data_attr: str) -> str | None:
    pattern = rf"<td[^>]*{re.escape(data_attr)}[^>]*>(.*?)</td>"
    match = re.search(pattern, row_html, flags=re.I | re.S)
    if match:
        return match.group(1)
    return None


def _same_origin_external_url(raw_url: str | None) -> str | None:
    if not raw_url:
        return None
    value = html.unescape(str(raw_url)).strip()
    if not value or value.lower().startswith("javascript:"):
        return None
    absolute = urljoin(TACHOMETER_BASE_URL, value)
    if not absolute.startswith(TACHOMETER_BASE_URL):
        return None
    return absolute


def _extract_tachometer_document_links(fragment_html: str, protocol_number: str | None) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    link_index = 0
    for href, label in re.findall(r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", fragment_html or "", flags=re.I | re.S):
        external_url = _same_origin_external_url(href)
        title = _strip_html(label) or f"Dokument {link_index + 1}"
        href_lower = str(href).lower()
        title_lower = title.lower()
        if not external_url:
            continue
        if ".pdf" not in href_lower and "pdf" not in title_lower and "protokol" not in title_lower and "dokument" not in title_lower:
            continue
        link_index += 1
        documents.append(
            {
                "document_id": f"{protocol_number or 'tachometer'}:document:{link_index}",
                "title": title,
                "document_type": "protocol" if "protokol" in title_lower or ".pdf" in href_lower else "document",
                "available": True,
                "open_mode": "external_url",
                "reason": None,
                "external_url": external_url,
                "internal_proxy_url": None,
                "source_reference": href,
            }
        )
    return documents


def _extract_tachometer_detail_reference(fragment_html: str) -> dict[str, Any] | None:
    form_match = re.search(r"<form[^>]+action=[\"']([^\"']+)[\"'][^>]*>(.*?)</form>", fragment_html or "", flags=re.I | re.S)
    if form_match:
        action = _same_origin_external_url(form_match.group(1))
        if action:
            inputs = {
                str(name): str(value)
                for name, value in re.findall(
                    r"<input[^>]+name=[\"']([^\"']+)[\"'][^>]+value=[\"']([^\"']*)[\"'][^>]*>",
                    form_match.group(2),
                    flags=re.I | re.S,
                )
            }
            return {
                "kind": "form",
                "action": action,
                "method": "POST",
                "inputs": inputs,
            }

    href_match = re.search(r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>.*?Detail prohlídky.*?</a>", fragment_html or "", flags=re.I | re.S)
    if href_match:
        external_url = _same_origin_external_url(href_match.group(1))
        if external_url:
            return {
                "kind": "url",
                "url": external_url,
            }

    onclick_match = re.search(
        r"onclick=[\"'][^\"']*(?:location\.href|window\.open)\s*=\s*[\"']([^\"']+)[\"']",
        fragment_html or "",
        flags=re.I | re.S,
    )
    if onclick_match:
        external_url = _same_origin_external_url(onclick_match.group(1))
        if external_url:
            return {
                "kind": "url",
                "url": external_url,
            }

    button_fragment = re.search(r"(<button[^>]*>.*?Detail prohlídky.*?</button>)", fragment_html or "", flags=re.I | re.S)
    if button_fragment:
        button_html = button_fragment.group(1)
        data_attrs = dict(
            re.findall(r"(data-[a-z0-9_-]+)=[\"']([^\"']+)[\"']", button_html, flags=re.I)
        )
        if data_attrs:
            return {
                "kind": "button_data",
                "data": data_attrs,
            }
        return {
            "kind": "button_label",
            "label": "Detail prohlídky",
        }
    return None


def _is_openable_tachometer_detail_reference(detail_reference: dict[str, Any] | None) -> bool:
    if not isinstance(detail_reference, dict):
        return False
    return str(detail_reference.get("kind") or "") in {"url", "form", "button_data"}


def _extract_tachometer_text_blocks(fragment_html: str | None) -> list[str]:
    normalized = re.sub(r"(?i)</(?:tr|li|p|div|h\d)>", "\n", fragment_html or "")
    normalized = re.sub(r"(?i)<br\s*/?>", "\n", normalized)
    blocks = []
    for raw_line in normalized.split("\n"):
        line = _strip_html(raw_line)
        if line:
            blocks.append(line)
    return blocks


def _extract_tachometer_findings(fragment_html: str | None) -> list[str]:
    items: list[str] = []
    ignored_exact = {
        "detail prohlídky",
        "zjištěné závady",
        "zjistene zavady",
    }
    for item_html in re.findall(r"<li[^>]*>(.*?)</li>", fragment_html or "", flags=re.I | re.S):
        item_text = _strip_html(item_html)
        if item_text and item_text.lower() not in ignored_exact:
            items.append(item_text)

    blocks = _extract_tachometer_text_blocks(fragment_html)
    for index, block in enumerate(blocks):
        lowered = block.lower()
        if not any(token in lowered for token in ("závad", "zavad", "nedostat", "vada", "chyb")):
            continue
        if index + 1 < len(blocks):
            next_block = blocks[index + 1]
            next_lower = next_block.lower()
            if (
                next_block not in items
                and next_lower not in ignored_exact
                and not any(token in next_lower for token in ("detail prohlídky", "stav km", "číslo protokolu"))
            ):
                items.append(next_block)
        if block not in items and ":" not in block and lowered not in ignored_exact:
            items.append(block)

    deduped: list[str] = []
    for item in items:
        cleaned = " ".join(item.split()).strip()
        if cleaned and cleaned not in deduped:
            deduped.append(cleaned)
    return deduped


def _build_tachometer_detail_snapshot(fragment_html: str | None) -> dict[str, Any] | None:
    if not fragment_html:
        return None
    text_blocks = _extract_tachometer_text_blocks(fragment_html)
    if not text_blocks:
        return None

    field_rows = []
    for label_html, value_html in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>\s*<t[dh][^>]*>(.*?)</t[dh]>", fragment_html, flags=re.I | re.S):
        label = _strip_html(label_html)
        value = _strip_html(value_html)
        if label and value:
            field_rows.append({"label": label, "value": value})

    findings_items = _extract_tachometer_findings(fragment_html)
    if not field_rows and not findings_items:
        detail_text = " ".join(text_blocks)
        if detail_text.lower() == "detail prohlídky":
            return None
    return {
        "text_blocks": text_blocks,
        "field_rows": field_rows,
        "findings_items": findings_items,
        "raw_text": " ".join(text_blocks),
    }


def _follow_tachometer_detail_reference(
    *,
    session: requests.Session,
    detail_reference: dict[str, Any],
) -> str | None:
    try:
        kind = str(detail_reference.get("kind") or "")
        if kind == "url":
            url = str(detail_reference.get("url") or "")
            if not url.startswith(TACHOMETER_BASE_URL):
                return None
            response = session.get(url, timeout=_TACHOMETER_HTTP_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.text
        if kind == "form":
            action = str(detail_reference.get("action") or "")
            if not action.startswith(TACHOMETER_BASE_URL):
                return None
            inputs = detail_reference.get("inputs")
            if not isinstance(inputs, dict):
                inputs = {}
            response = session.post(action, data=inputs, timeout=_TACHOMETER_HTTP_TIMEOUT_SECONDS)
            response.raise_for_status()
            return response.text
    except requests.RequestException:
        return None
    return None


def _resolve_tachometer_detail_data(
    *,
    row_html: str,
    inline_detail_html: str | None,
    protocol_number: str | None,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    documents = _extract_tachometer_document_links(inline_detail_html or row_html, protocol_number)
    detail_reference = _extract_tachometer_detail_reference(inline_detail_html or row_html)
    detail_snapshot = _build_tachometer_detail_snapshot(inline_detail_html)

    if detail_snapshot is None and detail_reference and session is not None and detail_reference.get("kind") in {"url", "form"}:
        fetched_html = _follow_tachometer_detail_reference(session=session, detail_reference=detail_reference)
        if fetched_html:
            documents = _extract_tachometer_document_links(fetched_html, protocol_number) or documents
            detail_snapshot = _build_tachometer_detail_snapshot(fetched_html)

    findings_items = []
    findings_summary = None
    if isinstance(detail_snapshot, dict):
        findings_items = [
            str(item).strip()
            for item in detail_snapshot.get("findings_items", [])
            if str(item).strip()
        ]
        if findings_items:
            findings_summary = " • ".join(findings_items[:3])

    return {
        "documents": documents,
        "detail_snapshot_json": detail_snapshot,
        "source_detail_reference": detail_reference,
        "findings_items": findings_items,
        "findings_summary": findings_summary,
        "detail_available": bool(detail_snapshot or _is_openable_tachometer_detail_reference(detail_reference)),
    }


def _parse_tachometer_inspections(
    search_html: str,
    *,
    session: requests.Session | None = None,
) -> List[TachometerInspectionOut]:
    section_match = re.search(
        r"Seznam prohl[íi]dek.*?(<table[^>]*>.*?</table>)",
        search_html,
        flags=re.I | re.S,
    )
    section_html = section_match.group(1) if section_match else search_html
    rows = re.findall(r"<tr[^>]*>.*?</tr>", section_html, flags=re.I | re.S)
    inspections: list[TachometerInspectionOut] = []
    row_index = 0
    while row_index < len(rows):
        row = rows[row_index]
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, flags=re.I | re.S)
        if len(cells) < 5:
            row_index += 1
            continue
        check_date = _parse_cz_date(cells[0])
        mileage_km = _parse_km_value(cells[4])
        if mileage_km is None:
            row_index += 1
            continue
        inspection_header = " / ".join(
            part
            for part in [
                _strip_html(cells[1]) or "",
                _strip_html(cells[3]) or "",
            ]
            if part
        ) or None
        protocol_number = _strip_html(cells[2]) or None
        inline_detail_html = None
        if row_index + 1 < len(rows):
            next_row = rows[row_index + 1]
            next_cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", next_row, flags=re.I | re.S)
            next_text = _strip_html(next_row)
            next_text_lower = next_text.lower()
            if len(next_cells) <= 2 and any(token in next_text_lower for token in ("detail prohlídky", "závad", "zavad", "nedostat", "protokol", "emise")):
                inline_detail_html = next_row
                row_index += 1

        detail_data = _resolve_tachometer_detail_data(
            row_html=row,
            inline_detail_html=inline_detail_html,
            protocol_number=protocol_number,
            session=session,
        )
        inspections.append(
            TachometerInspectionOut(
                check_date=check_date,
                mileage_km=mileage_km,
                protocol_number=protocol_number,
                inspection_type=inspection_header,
                findings_summary=detail_data["findings_summary"],
                findings_items=detail_data["findings_items"],
                detail_available=bool(detail_data["detail_available"]),
                detail_snapshot_json=detail_data["detail_snapshot_json"],
                source_detail_reference=detail_data["source_detail_reference"],
                documents=detail_data["documents"],
            )
        )
        row_index += 1

    if not inspections:
        return []

    if any(item.check_date is not None for item in inspections):
        inspections.sort(
            key=lambda item: item.check_date or datetime.min,
            reverse=True,
        )
    else:
        inspections.sort(key=lambda item: item.mileage_km, reverse=True)

    return inspections


def _get_accessible_vehicle_or_404(vehicle_id: int, current_user: Customer, db: Session) -> VehicleModel:
    _ensure_vehicle_photo_column(db)
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    if not can_access_vehicle(vehicle_id, current_user, db):
        raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")
    return vehicle


def _build_tachometer_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; SpravaVozidel/1.0; +https://hub.toozservis.cz)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "cs-CZ,cs;q=0.9,en;q=0.8",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }
    )
    return session


def _create_tachometer_session(
    *,
    expected_vin: Optional[str],
    vehicle_id: Optional[int],
) -> VehicleTachometerInitResponse:
    _cleanup_tachometer_challenge_store()
    try:
        with _build_tachometer_session() as session:
            page_response = session.get(
                urljoin(TACHOMETER_BASE_URL, TACHOMETER_LANDING_PATH),
                timeout=_TACHOMETER_HTTP_TIMEOUT_SECONDS,
            )
            page_response.raise_for_status()
            token = _extract_hidden_token(page_response.text)
            captcha_src = _extract_captcha_src(page_response.text)
            if not token or not captcha_src:
                raise HTTPException(
                    status_code=502,
                    detail="Nepodařilo se načíst captcha z Kontroly tachometru.",
                )

            captcha_response = session.get(
                urljoin(TACHOMETER_BASE_URL, captcha_src),
                timeout=_TACHOMETER_HTTP_TIMEOUT_SECONDS,
            )
            captcha_response.raise_for_status()
            captcha_bytes = captcha_response.content
            if not captcha_bytes:
                raise HTTPException(
                    status_code=502,
                    detail="Captcha obrázek je prázdný. Zkuste to prosím znovu.",
                )

            session_id = secrets.token_urlsafe(24)
            with _TACHOMETER_CHALLENGE_LOCK:
                _TACHOMETER_CHALLENGE_STORE[session_id] = {
                    "created_at": datetime.utcnow(),
                    "request_verification_token": token,
                    "cookies": requests.utils.dict_from_cookiejar(session.cookies),
                    "expected_vin": expected_vin,
                    "vehicle_id": vehicle_id,
                }

            return VehicleTachometerInitResponse(
                session_id=session_id,
                captcha_image_base64=base64.b64encode(captcha_bytes).decode("ascii"),
                captcha_mime_type=(
                    captcha_response.headers.get("Content-Type", "image/png").split(";", 1)[0].strip()
                    or "image/png"
                ),
                expires_in_seconds=TACHOMETER_CHALLENGE_TTL_SECONDS,
            )
    except HTTPException:
        raise
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Nepodařilo se spojit s kontrolatachometru.cz: {exc}",
        ) from exc


def _lookup_tachometer_with_session(
    *,
    session_id: str,
    vin: str,
    captcha_code: str,
) -> TachometerLookupResponse:
    _cleanup_tachometer_challenge_store()
    with _TACHOMETER_CHALLENGE_LOCK:
        challenge = _TACHOMETER_CHALLENGE_STORE.get(session_id)
    if not challenge:
        raise HTTPException(
            status_code=410,
            detail="Captcha session vypršela nebo je neplatná. Načtěte nový obrázek.",
        )

    expected_vin = challenge.get("expected_vin")
    if expected_vin and expected_vin != vin:
        raise HTTPException(
            status_code=409,
            detail="Captcha session patří k jinému vozidlu. Načtěte nový obrázek pro aktuální VIN.",
        )

    if len(captcha_code) < 2:
        raise HTTPException(status_code=422, detail="Zadejte captcha kód z obrázku.")

    try:
        with _build_tachometer_session() as session:
            cookie_dict = challenge.get("cookies", {})
            if isinstance(cookie_dict, dict):
                session.cookies.update(cookie_dict)
            session.headers.update(
                {
                    "Referer": urljoin(TACHOMETER_BASE_URL, TACHOMETER_LANDING_PATH),
                    "Origin": TACHOMETER_BASE_URL,
                    "Content-Type": "application/x-www-form-urlencoded",
                }
            )
            response = session.post(
                urljoin(TACHOMETER_BASE_URL, TACHOMETER_SEARCH_PATH),
                data={
                    "__RequestVerificationToken": challenge.get("request_verification_token", ""),
                    "VIN": vin,
                    "captcha$TB": captcha_code,
                },
                timeout=_TACHOMETER_HTTP_TIMEOUT_SECONDS,
            )
            if not (200 <= response.status_code < 300):
                lowered = (response.text or "").lower()
                is_html = "<!doctype" in lowered or "<html" in lowered
                if response.status_code in {400, 403} or (response.status_code == 500 and is_html):
                    raise HTTPException(
                        status_code=410,
                        detail="Captcha session vypršela nebo je neplatná. Načtěte nový obrázek.",
                    )
                raise HTTPException(
                    status_code=502,
                    detail="Portál kontrolatachometru.cz momentálně nevrátil použitelnou odpověď. Zkuste to prosím znovu.",
                )

            search_html = response.text
            if _contains_captcha_error(search_html):
                raise HTTPException(status_code=422, detail=_TACHOMETER_CAPTCHA_ERROR_TEXT)

            inspections = _parse_tachometer_inspections(search_html, session=session)
            if not inspections:
                raise HTTPException(
                    status_code=404,
                    detail="Pro zadané VIN nebyly nalezeny žádné údaje STK/emisí.",
                )

            latest = inspections[0]
            with _TACHOMETER_CHALLENGE_LOCK:
                _TACHOMETER_CHALLENGE_STORE.pop(session_id, None)
            return TachometerLookupResponse(
                vin=vin,
                latest_mileage_km=latest.mileage_km,
                latest_check_date=latest.check_date,
                inspections=inspections,
            )
    except HTTPException:
        raise
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail="Portál kontrolatachometru.cz je dočasně nedostupný. Zkuste to prosím znovu později.",
        ) from exc


def _store_tachometer_mileage_result(
    *,
    vehicle: VehicleModel,
    lookup: TachometerLookupResponse,
    current_user: Customer,
    db: Session,
) -> tuple[dict, int]:
    effective_current_mileage = max(
        getattr(vehicle, "current_mileage_km", None) or lookup.latest_mileage_km,
        lookup.latest_mileage_km,
    )
    _validate_mileage_consistency(
        current_mileage_km=effective_current_mileage,
        last_stk_mileage_km=lookup.latest_mileage_km,
    )

    vehicle.current_mileage_km = effective_current_mileage
    vehicle.last_stk_mileage_km = lookup.latest_mileage_km
    vehicle.mileage_checked_at = datetime.utcnow()

    latest = lookup.inspections[0]
    performed_at = latest.check_date or datetime.utcnow()
    record_description = "Načteno z kontroly tachometru (MDČR)"
    record_note_parts = ["Zdroj: kontrolatachometru.cz"]
    if latest.protocol_number:
        record_note_parts.append(f"Protokol: {latest.protocol_number}")
    if latest.inspection_type:
        record_note_parts.append(f"Typ: {latest.inspection_type}")
    existing_record = (
        db.query(ServiceRecordModel)
        .filter(
            ServiceRecordModel.vehicle_id == vehicle.id,
            ServiceRecordModel.description == record_description,
            ServiceRecordModel.mileage == lookup.latest_mileage_km,
            ServiceRecordModel.performed_at == performed_at,
            ServiceRecordModel.is_deleted.is_(False),
        )
        .first()
    )
    if existing_record is None:
        existing_record = ServiceRecordModel(
            tenant_id=vehicle.tenant_id,
            vehicle_id=vehicle.id,
            user_id=current_user.id,
            performed_at=performed_at,
            mileage=lookup.latest_mileage_km,
            description=record_description,
            note=" | ".join(record_note_parts),
        )
        db.add(existing_record)

    _upsert_tachometer_history_entries(
        vehicle=vehicle,
        lookup=lookup,
        imported_at=datetime.utcnow(),
        db=db,
    )

    db.commit()
    db.refresh(vehicle)
    db.refresh(existing_record)
    return _vehicle_to_response_payload(vehicle, current_user, db), existing_record.id


def _upsert_tachometer_history_entries(
    *,
    vehicle: VehicleModel,
    lookup: TachometerLookupResponse,
    imported_at: datetime,
    db: Session,
) -> None:
    for inspection in lookup.inspections:
        protocol_number = (inspection.protocol_number or "").strip() or None
        source = lookup.source or "kontrolatachometru.cz"
        summary = _build_tachometer_entry_summary(
            inspection_type=inspection.inspection_type,
            protocol_number=protocol_number,
            source=source,
        )
        documents = _build_tachometer_documents(
            protocol_number=protocol_number,
            parsed_documents=list(getattr(inspection, "documents", []) or []),
            detail_available=bool(getattr(inspection, "detail_available", False)),
            source_detail_reference=getattr(inspection, "source_detail_reference", None),
        )
        raw_payload = {
            "check_date": inspection.check_date.isoformat() if inspection.check_date else None,
            "mileage_km": inspection.mileage_km,
            "protocol_number": protocol_number,
            "inspection_type": inspection.inspection_type,
            "source": source,
            "findings_summary": inspection.findings_summary,
            "findings_items": list(getattr(inspection, "findings_items", []) or []),
            "detail_available": bool(getattr(inspection, "detail_available", False)),
            "detail_snapshot_json": getattr(inspection, "detail_snapshot_json", None),
            "source_detail_reference": getattr(inspection, "source_detail_reference", None),
        }

        entry = (
            db.query(VehicleTachometerHistoryEntryModel)
            .filter(
                VehicleTachometerHistoryEntryModel.vehicle_id == vehicle.id,
                VehicleTachometerHistoryEntryModel.check_date == inspection.check_date,
                VehicleTachometerHistoryEntryModel.mileage_km == inspection.mileage_km,
                VehicleTachometerHistoryEntryModel.protocol_number == protocol_number,
            )
            .first()
        )
        if entry is None:
            entry = VehicleTachometerHistoryEntryModel(
                tenant_id=vehicle.tenant_id,
                vehicle_id=vehicle.id,
                check_date=inspection.check_date,
                mileage_km=inspection.mileage_km,
                protocol_number=protocol_number,
                inspection_type=inspection.inspection_type,
                source=source,
                status="imported",
                summary=summary,
                findings_summary=inspection.findings_summary,
                findings_items_json=json.dumps(list(getattr(inspection, "findings_items", []) or []), ensure_ascii=False),
                detail_snapshot_json=(
                    json.dumps(getattr(inspection, "detail_snapshot_json", None), ensure_ascii=False)
                    if getattr(inspection, "detail_snapshot_json", None)
                    else None
                ),
                source_detail_reference=(
                    json.dumps(getattr(inspection, "source_detail_reference", None), ensure_ascii=False)
                    if getattr(inspection, "source_detail_reference", None)
                    else None
                ),
                documents_json=json.dumps(documents, ensure_ascii=False),
                raw_payload_json=json.dumps(raw_payload, ensure_ascii=False),
                imported_at=imported_at,
                last_seen_at=imported_at,
            )
            db.add(entry)
        else:
            entry.inspection_type = inspection.inspection_type
            entry.source = source
            entry.status = "imported"
            entry.summary = summary
            entry.findings_summary = inspection.findings_summary
            entry.findings_items_json = json.dumps(list(getattr(inspection, "findings_items", []) or []), ensure_ascii=False)
            entry.detail_snapshot_json = (
                json.dumps(getattr(inspection, "detail_snapshot_json", None), ensure_ascii=False)
                if getattr(inspection, "detail_snapshot_json", None)
                else None
            )
            entry.source_detail_reference = (
                json.dumps(getattr(inspection, "source_detail_reference", None), ensure_ascii=False)
                if getattr(inspection, "source_detail_reference", None)
                else None
            )
            entry.documents_json = json.dumps(documents, ensure_ascii=False)
            entry.raw_payload_json = json.dumps(raw_payload, ensure_ascii=False)
            entry.last_seen_at = imported_at


def _backfill_tachometer_history_entries_from_service_records(
    vehicle_id: int,
    db: Session,
) -> list[VehicleTachometerHistoryEntryModel]:
    existing_entries = (
        db.query(VehicleTachometerHistoryEntryModel)
        .filter(VehicleTachometerHistoryEntryModel.vehicle_id == vehicle_id)
        .order_by(
            VehicleTachometerHistoryEntryModel.check_date.asc(),
            VehicleTachometerHistoryEntryModel.mileage_km.asc(),
            VehicleTachometerHistoryEntryModel.id.asc(),
        )
        .all()
    )
    if existing_entries:
        return existing_entries

    vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()
    if vehicle is None:
        return []

    records = (
        db.query(ServiceRecordModel)
        .filter(
            ServiceRecordModel.vehicle_id == vehicle_id,
            ServiceRecordModel.description == "Načteno z kontroly tachometru (MDČR)",
            ServiceRecordModel.is_deleted.is_(False),
        )
        .order_by(ServiceRecordModel.performed_at.asc(), ServiceRecordModel.mileage.asc(), ServiceRecordModel.id.asc())
        .all()
    )

    imported_any = False
    for record in records:
        parsed_note = _parse_tachometer_record_note(getattr(record, "note", None))
        protocol_number = parsed_note["protocol_number"]
        source = parsed_note["source"] or "kontrolatachometru.cz"
        entry = VehicleTachometerHistoryEntryModel(
            tenant_id=vehicle.tenant_id,
            vehicle_id=vehicle.id,
            check_date=getattr(record, "performed_at", None),
            mileage_km=getattr(record, "mileage", None),
            protocol_number=protocol_number,
            inspection_type=parsed_note["inspection_type"],
            source=source,
            status="imported_legacy",
            summary=_build_tachometer_entry_summary(
                inspection_type=parsed_note["inspection_type"],
                protocol_number=protocol_number,
                source=source,
            ),
            findings_summary=None,
            findings_items_json=None,
            detail_snapshot_json=None,
            source_detail_reference=None,
            documents_json=json.dumps(_build_unavailable_tachometer_documents(protocol_number), ensure_ascii=False),
            raw_payload_json=json.dumps(
                {
                    "legacy_service_record_id": record.id,
                    "check_date": getattr(record, "performed_at", None).isoformat() if getattr(record, "performed_at", None) else None,
                    "mileage_km": getattr(record, "mileage", None),
                    "protocol_number": protocol_number,
                    "inspection_type": parsed_note["inspection_type"],
                    "source": source,
                },
                ensure_ascii=False,
            ),
            imported_at=datetime.utcnow(),
            last_seen_at=datetime.utcnow(),
        )
        db.add(entry)
        imported_any = True

    if imported_any:
        db.commit()

    return (
        db.query(VehicleTachometerHistoryEntryModel)
        .filter(VehicleTachometerHistoryEntryModel.vehicle_id == vehicle_id)
        .order_by(
            VehicleTachometerHistoryEntryModel.check_date.asc(),
            VehicleTachometerHistoryEntryModel.mileage_km.asc(),
            VehicleTachometerHistoryEntryModel.id.asc(),
        )
        .all()
    )


def _tachometer_history_query(
    vehicle_id: int,
    db: Session,
) -> list[VehicleTachometerHistoryEntryModel]:
    return _backfill_tachometer_history_entries_from_service_records(vehicle_id, db)


def _build_tachometer_history_entries(vehicle_id: int, db: Session) -> list[VehicleTachometerHistoryEntryResponse]:
    items = _normalized_tachometer_history(vehicle_id, db)
    return [_tachometer_history_entry_to_summary(item) for item in items]


def _get_tachometer_history_entry_or_404(
    *,
    vehicle_id: int,
    entry_id: int,
    db: Session,
) -> VehicleTachometerHistoryEntryModel:
    _tachometer_history_query(vehicle_id, db)
    entry = (
        db.query(VehicleTachometerHistoryEntryModel)
        .filter(
            VehicleTachometerHistoryEntryModel.id == entry_id,
            VehicleTachometerHistoryEntryModel.vehicle_id == vehicle_id,
        )
        .first()
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Záznam historie STK / tachometru nebyl nalezen.")
    return entry


def _get_normalized_tachometer_history_item_or_404(
    *,
    vehicle_id: int,
    entry_id: int,
    db: Session,
) -> _NormalizedTachometerHistoryItem:
    for item in _normalized_tachometer_history(vehicle_id, db):
        if int(getattr(item.canonical_entry, "id", 0) or 0) == entry_id:
            return item
    raise HTTPException(status_code=404, detail="Záznam historie STK / tachometru nebyl nalezen.")


def _get_vehicle_photo_file(photo_path: str | None) -> Path | None:
    if not photo_path:
        return None
    base = VEHICLE_PHOTOS_DIR.resolve()
    candidate = (VEHICLE_PHOTOS_DIR / str(photo_path)).resolve()
    if not str(candidate).startswith(str(base)):
        return None
    if not candidate.is_file():
        return None
    return candidate


def _extract_service_record_attachment_files(attachments_raw: str | None) -> list[Path]:
    if not attachments_raw:
        return []
    try:
        import json
        payload = json.loads(attachments_raw)
    except Exception:
        return []
    if not isinstance(payload, list):
        return []

    base = (DATA_DIR / "service_record_attachments").resolve()
    files: list[Path] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        key = item.get("storage_key") or item.get("path")
        if not key:
            continue
        candidate = (base / str(key)).resolve()
        if str(candidate).startswith(str(base)):
            files.append(candidate)
    return files


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


def _normalize_vehicle_photo(content: bytes) -> bytes:
    if not PILLOW_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Server není připraven zpracovat fotku vozidla. Chybí knihovna Pillow.",
        )

    try:
        with Image.open(BytesIO(content)) as image:
            resampling = getattr(Image, "Resampling", Image)
            image = ImageOps.exif_transpose(image)
            if image.mode not in {"RGB", "L"}:
                rgba_image = image.convert("RGBA")
                flattened = Image.new("RGB", rgba_image.size, (255, 255, 255))
                flattened.paste(rgba_image, mask=rgba_image.getchannel("A"))
                image = flattened
            elif image.mode == "L":
                image = image.convert("RGB")
            else:
                image = image.copy()

            image = ImageOps.fit(
                image,
                VEHICLE_PHOTO_TARGET_SIZE,
                method=resampling.LANCZOS,
                centering=(0.5, 0.5),
            )

            for quality in range(
                VEHICLE_PHOTO_JPEG_QUALITY,
                VEHICLE_PHOTO_MIN_JPEG_QUALITY - 1,
                -6,
            ):
                normalized_buffer = BytesIO()
                image.save(
                    normalized_buffer,
                    format="JPEG",
                    quality=quality,
                    optimize=True,
                )
                normalized = normalized_buffer.getvalue()
                if len(normalized) <= MAX_VEHICLE_PHOTO_OUTPUT_SIZE_BYTES:
                    return normalized
    except UnidentifiedImageError as exc:
        raise HTTPException(status_code=415, detail="Soubor není podporovaný nebo je poškozený obrázek.") from exc
    except OSError as exc:
        raise HTTPException(status_code=415, detail="Soubor není podporovaný nebo je poškozený obrázek.") from exc

    raise HTTPException(
        status_code=413,
        detail="Fotku se nepodařilo zpracovat pod výsledný limit 10 MB.",
    )


def _parse_tachometer_record_note(note: str | None) -> dict[str, str | None]:
    parsed = {
        "source": None,
        "protocol_number": None,
        "inspection_type": None,
    }
    if not note:
        return parsed

    for raw_part in str(note).split("|"):
        part = raw_part.strip()
        if not part or ":" not in part:
            continue
        key, value = part.split(":", 1)
        normalized_key = key.strip().lower()
        normalized_value = value.strip() or None
        if normalized_key == "zdroj":
            parsed["source"] = normalized_value
        elif normalized_key == "protokol":
            parsed["protocol_number"] = normalized_value
        elif normalized_key == "typ":
            parsed["inspection_type"] = normalized_value
    return parsed


def _build_tachometer_entry_summary(
    *,
    inspection_type: str | None,
    protocol_number: str | None,
    source: str | None,
) -> str:
    parts = []
    if inspection_type:
        parts.append(inspection_type)
    if protocol_number:
        parts.append(f"Protokol {protocol_number}")
    if source:
        parts.append(f"Zdroj {source}")
    if not parts:
        return "Importovaný záznam z kontroly tachometru."
    return " • ".join(parts)


def _build_unavailable_tachometer_documents(protocol_number: str | None) -> list[dict[str, Any]]:
    if not protocol_number:
        return []
    return [
        {
            "document_id": f"protocol:{protocol_number}",
            "title": f"Protokol {protocol_number}",
            "document_type": "protocol",
            "available": False,
            "open_mode": "unavailable",
            "reason": "Dokument není dostupný v uložených datech.",
            "external_url": None,
            "internal_proxy_url": None,
            "source_reference": None,
        }
    ]


def _build_tachometer_documents(
    *,
    protocol_number: str | None,
    parsed_documents: list[dict[str, Any]],
    detail_available: bool,
    source_detail_reference: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    if parsed_documents:
        return parsed_documents
    if not protocol_number:
        return []
    documents = _build_unavailable_tachometer_documents(protocol_number)
    if detail_available and documents:
        documents[0]["reason"] = "Portál vrátil detail kontroly, ale nevrátil otevřitelný dokument / PDF."
    if source_detail_reference and documents:
        documents[0]["source_reference"] = json.dumps(source_detail_reference, ensure_ascii=False)
    return documents


def _deserialize_string_list(raw_payload: str | None) -> list[str]:
    if not raw_payload:
        return []
    try:
        payload = json.loads(raw_payload)
    except Exception:
        return []
    if not isinstance(payload, list):
        return []
    return [str(item).strip() for item in payload if str(item).strip()]


def _deserialize_json_object(raw_payload: str | None) -> dict[str, Any] | None:
    if not raw_payload:
        return None
    try:
        payload = json.loads(raw_payload)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _tachometer_history_sort_key(entry: VehicleTachometerHistoryEntryModel) -> tuple[datetime, int, int]:
    return (
        getattr(entry, "check_date", None) or datetime.min,
        int(getattr(entry, "mileage_km", None) or -1),
        int(getattr(entry, "id", 0) or 0),
    )


def _tachometer_entry_precision_score(entry: VehicleTachometerHistoryEntryModel) -> int:
    score = 0
    documents = _serialize_tachometer_documents(getattr(entry, "documents_json", None))
    if any(item.available for item in documents):
        score += 40
    if _deserialize_json_object(getattr(entry, "detail_snapshot_json", None)):
        score += 30
    if _deserialize_json_object(getattr(entry, "source_detail_reference", None)):
        score += 20
    if _deserialize_string_list(getattr(entry, "findings_items_json", None)):
        score += 10
    if getattr(entry, "protocol_number", None):
        score += 5
    if str(getattr(entry, "status", "") or "").lower() != "imported_legacy":
        score += 3
    return score


def _select_canonical_tachometer_entry(
    entries: list[VehicleTachometerHistoryEntryModel],
) -> VehicleTachometerHistoryEntryModel:
    return max(
        entries,
        key=lambda entry: (
            int(getattr(entry, "mileage_km", None) or -1),
            _tachometer_entry_precision_score(entry),
            1 if getattr(entry, "check_date", None) is not None else 0,
            int(getattr(entry, "id", 0) or 0),
        ),
    )


def _deduplicate_tachometer_history_entries(
    entries: list[VehicleTachometerHistoryEntryModel],
) -> list[_NormalizedTachometerHistoryItem]:
    sorted_entries = sorted(entries, key=_tachometer_history_sort_key)
    groups: list[list[VehicleTachometerHistoryEntryModel]] = []
    current_group: list[VehicleTachometerHistoryEntryModel] = []

    for entry in sorted_entries:
        if not current_group:
            current_group = [entry]
            continue

        current_date = (getattr(current_group[-1], "check_date", None) or datetime.min).date()
        entry_date = (getattr(entry, "check_date", None) or datetime.min).date()
        current_mileage = int(getattr(current_group[-1], "mileage_km", None) or -1)
        entry_mileage = int(getattr(entry, "mileage_km", None) or -1)

        if entry_date == current_date and current_mileage >= 0 and entry_mileage >= 0 and abs(entry_mileage - current_mileage) <= 5:
            current_group.append(entry)
            continue

        groups.append(current_group)
        current_group = [entry]

    if current_group:
        groups.append(current_group)

    normalized: list[_NormalizedTachometerHistoryItem] = []
    for group in groups:
        canonical_entry = _select_canonical_tachometer_entry(group)
        merged_entries = sorted(group, key=_tachometer_history_sort_key)
        merge_reason = None
        if len(merged_entries) > 1:
            merge_reason = (
                "Sloučeno jako near-duplicate: stejné datum kontroly a rozdíl km do 5 km; "
                "ponechán záznam s vyšším km nebo přesnějším zdrojem."
            )
        normalized.append(
            _NormalizedTachometerHistoryItem(
                canonical_entry=canonical_entry,
                merged_entries=merged_entries,
                merge_reason=merge_reason,
            )
        )
    return normalized


def _apply_tachometer_history_monotonicity(
    items: list[_NormalizedTachometerHistoryItem],
) -> list[_NormalizedTachometerHistoryItem]:
    previous_mileage: int | None = None
    for item in items:
        current_mileage = getattr(item.canonical_entry, "mileage_km", None)
        if current_mileage is None:
            item.is_monotonic_valid = previous_mileage is None
            continue
        if previous_mileage is not None and int(current_mileage) < int(previous_mileage):
            item.is_monotonic_valid = False
            item.anomaly = True
            item.anomaly_type = "km_decrease"
            item.anomaly_delta_km = int(current_mileage) - int(previous_mileage)
        else:
            item.is_monotonic_valid = True
            item.anomaly = False
            item.anomaly_type = None
            item.anomaly_delta_km = None
        previous_mileage = int(current_mileage)
    return items


def _normalized_tachometer_history(vehicle_id: int, db: Session) -> list[_NormalizedTachometerHistoryItem]:
    raw_entries = _tachometer_history_query(vehicle_id, db)
    deduped = _deduplicate_tachometer_history_entries(raw_entries)
    return _apply_tachometer_history_monotonicity(deduped)


def _serialize_tachometer_documents(documents_raw: str | None) -> list[VehicleTachometerDocumentResponse]:
    if not documents_raw:
        return []
    try:
        payload = json.loads(documents_raw)
    except Exception:
        return []
    if not isinstance(payload, list):
        return []

    serialized: list[VehicleTachometerDocumentResponse] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("document_id") or "Dokument").strip()
        if not title:
            title = "Dokument"
        serialized.append(
            VehicleTachometerDocumentResponse(
                document_id=str(item.get("document_id") or title),
                title=title,
                document_type=str(item.get("document_type") or "document"),
                available=bool(item.get("available")),
                open_mode=str(item.get("open_mode") or "unavailable"),
                reason=(str(item.get("reason")).strip() if item.get("reason") is not None else None),
                external_url=(str(item.get("external_url")).strip() if item.get("external_url") else None),
                internal_proxy_url=(str(item.get("internal_proxy_url")).strip() if item.get("internal_proxy_url") else None),
                source_reference=(str(item.get("source_reference")).strip() if item.get("source_reference") else None),
            )
        )
    return serialized


def _tachometer_history_entry_to_summary(
    item: _NormalizedTachometerHistoryItem,
) -> VehicleTachometerHistoryEntryResponse:
    entry = item.canonical_entry
    documents = _serialize_tachometer_documents(getattr(entry, "documents_json", None))
    available_documents = [item for item in documents if item.available]
    detail_snapshot = _deserialize_json_object(getattr(entry, "detail_snapshot_json", None))
    detail_reference = _deserialize_json_object(getattr(entry, "source_detail_reference", None))
    return VehicleTachometerHistoryEntryResponse(
        id=int(entry.id),
        check_date=getattr(entry, "check_date", None),
        mileage_km=getattr(entry, "mileage_km", None),
        protocol_number=getattr(entry, "protocol_number", None),
        inspection_type=getattr(entry, "inspection_type", None),
        source=getattr(entry, "source", None),
        status=str(getattr(entry, "status", None) or "imported"),
        summary=getattr(entry, "summary", None),
        findings_summary=getattr(entry, "findings_summary", None),
        findings_items=_deserialize_string_list(getattr(entry, "findings_items_json", None)),
        detail_available=bool(detail_snapshot or _is_openable_tachometer_detail_reference(detail_reference)),
        detail_snapshot_json=detail_snapshot,
        source_detail_reference=detail_reference,
        is_monotonic_valid=item.is_monotonic_valid,
        anomaly=item.anomaly,
        anomaly_type=item.anomaly_type,
        anomaly_delta_km=item.anomaly_delta_km,
        merged_duplicate_count=max(len(item.merged_entries) - 1, 0),
        merged_entry_ids=[int(getattr(merged_entry, "id", 0) or 0) for merged_entry in item.merged_entries],
        merge_reason=item.merge_reason,
        has_documents=bool(available_documents),
        documents_count=len(available_documents),
        documents=documents,
    )


def _tachometer_history_entry_to_detail(
    item: _NormalizedTachometerHistoryItem,
) -> VehicleTachometerHistoryEntryDetailResponse:
    entry = item.canonical_entry
    documents = _serialize_tachometer_documents(getattr(entry, "documents_json", None))
    available_documents = [item for item in documents if item.available]
    detail_snapshot = _deserialize_json_object(getattr(entry, "detail_snapshot_json", None))
    detail_reference = _deserialize_json_object(getattr(entry, "source_detail_reference", None))
    return VehicleTachometerHistoryEntryDetailResponse(
        id=int(entry.id),
        check_date=getattr(entry, "check_date", None),
        mileage_km=getattr(entry, "mileage_km", None),
        protocol_number=getattr(entry, "protocol_number", None),
        inspection_type=getattr(entry, "inspection_type", None),
        source=getattr(entry, "source", None),
        status=str(getattr(entry, "status", None) or "imported"),
        summary=getattr(entry, "summary", None),
        findings_summary=getattr(entry, "findings_summary", None),
        findings_items=_deserialize_string_list(getattr(entry, "findings_items_json", None)),
        detail_available=bool(detail_snapshot or _is_openable_tachometer_detail_reference(detail_reference)),
        detail_snapshot_json=detail_snapshot,
        source_detail_reference=detail_reference,
        is_monotonic_valid=item.is_monotonic_valid,
        anomaly=item.anomaly,
        anomaly_type=item.anomaly_type,
        anomaly_delta_km=item.anomaly_delta_km,
        merged_duplicate_count=max(len(item.merged_entries) - 1, 0),
        merged_entry_ids=[int(getattr(merged_entry, "id", 0) or 0) for merged_entry in item.merged_entries],
        merge_reason=item.merge_reason,
        has_documents=bool(available_documents),
        documents_count=len(available_documents),
        documents=documents,
    )


def _vehicle_to_response_payload(vehicle: VehicleModel, current_user: Customer, db: Session) -> dict:
    owner = get_primary_vehicle_owner(db, vehicle)
    current_owner_since = get_current_owner_since(db, vehicle)
    payload = {
        "id": vehicle.id,
        "user_email": getattr(vehicle, "user_email", None),
        "nickname": getattr(vehicle, "nickname", None),
        "brand": getattr(vehicle, "brand", None),
        "model": getattr(vehicle, "model", None),
        "year": getattr(vehicle, "year", None),
        "engine": getattr(vehicle, "engine", None),
        "vin": getattr(vehicle, "vin", None),
        "plate": getattr(vehicle, "plate", None),
        "orv_number": getattr(vehicle, "orv_number", None),
        "orv_scan_source": getattr(vehicle, "orv_scan_source", None),
        "orv_front_image_path": getattr(vehicle, "orv_front_image_path", None),
        "orv_back_image_path": getattr(vehicle, "orv_back_image_path", None),
        "orv_scanned_at": getattr(vehicle, "orv_scanned_at", None),
        "orv_confidence_json": getattr(vehicle, "orv_confidence_json", None),
        "data_trust_state": getattr(vehicle, "data_trust_state", None),
        "notes": getattr(vehicle, "notes", None),
        "photo_path": getattr(vehicle, "photo_path", None),
        "stk_valid_until": getattr(vehicle, "stk_valid_until", None),
        "current_mileage_km": getattr(vehicle, "current_mileage_km", None),
        "last_stk_mileage_km": getattr(vehicle, "last_stk_mileage_km", None),
        "mileage_checked_at": getattr(vehicle, "mileage_checked_at", None),
        "tyres_info": getattr(vehicle, "tyres_info", None),
        "insurance_provider": getattr(vehicle, "insurance_provider", None),
        "insurance_valid_until": getattr(vehicle, "insurance_valid_until", None),
        "current_owner_since": current_owner_since,
        "tenant_id": getattr(vehicle, "tenant_id", None),
        "created_at": getattr(vehicle, "created_at", None),
    }

    role_key = str(getattr(current_user, "role", "") or "").strip().lower()
    current_email = str(getattr(current_user, "email", "") or "").strip().lower()
    owner_email = str(getattr(owner, "email", None) or getattr(vehicle, "user_email", "") or "").strip().lower()
    is_owner = bool(current_email) and current_email == owner_email
    is_admin_role = is_admin(role_key)

    if not is_owner and not is_admin_role:
        payload["user_email"] = "hidden"
        payload["tenant_id"] = None

    return payload


def _validate_mileage_consistency(
    *,
    current_mileage_km: int | None,
    last_stk_mileage_km: int | None,
) -> None:
    if current_mileage_km is None or last_stk_mileage_km is None:
        return
    if current_mileage_km < last_stk_mileage_km:
        raise HTTPException(
            status_code=422,
            detail=(
                "Aktuální stav km nesmí být menší než poslední známý stav km ze STK/emisí "
                f"({last_stk_mileage_km:,} km)."
            ).replace(",", " "),
        )


def _find_duplicate_vehicle_by_vin(
    *,
    db: Session,
    tenant_id: int | None,
    vin: str | None,
    exclude_vehicle_id: int | None = None,
) -> VehicleModel | None:
    normalized_vin = _normalize_vin(vin or "")
    if not normalized_vin:
        return None

    query = db.query(VehicleModel).filter(VehicleModel.vin.isnot(None))
    if tenant_id is None:
        query = query.filter(VehicleModel.tenant_id.is_(None))
    else:
        query = query.filter(VehicleModel.tenant_id == tenant_id)

    if exclude_vehicle_id is not None:
        query = query.filter(VehicleModel.id != exclude_vehicle_id)

    for candidate in query.all():
        candidate_vin = _normalize_vin(getattr(candidate, "vin", "") or "")
        if candidate_vin == normalized_vin:
            return candidate
    return None


def _find_existing_vehicle_by_vin_globally(
    *,
    db: Session,
    vin: str | None,
    exclude_vehicle_id: int | None = None,
) -> VehicleModel | None:
    normalized_vin = _normalize_vin(vin or "")
    if not normalized_vin:
        return None
    query = db.query(VehicleModel).filter(VehicleModel.vin.isnot(None))
    if exclude_vehicle_id is not None:
        query = query.filter(VehicleModel.id != exclude_vehicle_id)
    candidates = query.order_by(VehicleModel.created_at.asc(), VehicleModel.id.asc()).all()
    for candidate in candidates:
        if _normalize_vin(getattr(candidate, "vin", "") or "") == normalized_vin:
            return candidate
    return None


def _apply_vehicle_claim_payload(vehicle: VehicleModel, vehicle_data: VehicleCreateV1) -> None:
    normalized_vin = _normalize_vin(vehicle_data.vin or "")
    if normalized_vin:
        vehicle.vin = normalized_vin
    if vehicle_data.nickname:
        vehicle.nickname = vehicle_data.nickname
    if vehicle_data.brand:
        vehicle.brand = vehicle_data.brand
    if vehicle_data.model:
        vehicle.model = vehicle_data.model
    if vehicle_data.year is not None:
        vehicle.year = vehicle_data.year
    if vehicle_data.engine:
        vehicle.engine = vehicle_data.engine
    if vehicle_data.plate:
        vehicle.plate = vehicle_data.plate
    if vehicle_data.notes:
        vehicle.notes = vehicle_data.notes
    if vehicle_data.stk_valid_until is not None:
        vehicle.stk_valid_until = vehicle_data.stk_valid_until
    if vehicle_data.current_mileage_km is not None:
        vehicle.current_mileage_km = vehicle_data.current_mileage_km
    if vehicle_data.last_stk_mileage_km is not None:
        vehicle.last_stk_mileage_km = vehicle_data.last_stk_mileage_km
        vehicle.mileage_checked_at = datetime.utcnow()
    if vehicle_data.tyres_info:
        vehicle.tyres_info = vehicle_data.tyres_info
    if vehicle_data.insurance_provider:
        vehicle.insurance_provider = vehicle_data.insurance_provider
    if vehicle_data.insurance_valid_until is not None:
        vehicle.insurance_valid_until = vehicle_data.insurance_valid_until


def _revoke_vehicle_service_links_for_owner_release(
    db: Session,
    *,
    vehicle_id: int,
    revoked_by_customer_id: int,
    reason: str,
) -> None:
    from ..models import VehicleServiceLink

    now = datetime.utcnow()
    (
        db.query(VehicleServiceLink)
        .filter(
            VehicleServiceLink.vehicle_id == int(vehicle_id),
            VehicleServiceLink.status == "approved",
        )
        .update(
            {
                VehicleServiceLink.status: "revoked",
                VehicleServiceLink.revoked_at: now,
                VehicleServiceLink.revoked_by_customer_id: int(revoked_by_customer_id),
                VehicleServiceLink.revoked_reason: reason,
                VehicleServiceLink.updated_at: now,
            },
            synchronize_session=False,
        )
    )


@router.post("/parse-orv", response_model=ORVParseResponseV1)
def parse_orv(
    payload: ORVParseRequestV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ensure_vehicle_schema_columns(db)
    scan = create_orv_scan_record(
        db=db,
        current_user=current_user,
        front_image_base64=payload.front_image_base64,
        back_image_base64=payload.back_image_base64,
        front_image_mime_type=payload.front_image_mime_type,
        back_image_mime_type=payload.back_image_mime_type,
        source=payload.source,
    )
    return serialize_orv_scan(scan)


@router.post("", response_model=VehicleOutV1)
def create_vehicle(
    vehicle_data: VehicleCreateV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Vytvoří nové vozidlo"""
    import logging
    from sqlalchemy.exc import IntegrityError
    from fastapi.responses import JSONResponse
    
    logger = logging.getLogger(__name__)

    _ensure_vehicle_photo_column(db)
    
    # Zkontrolovat tenant_id
    tenant_id = getattr(current_user, 'tenant_id', None)
    if not tenant_id:
        logger.error(f"[VEHICLE_CREATE] User {current_user.email} nemá tenant_id")
        return JSONResponse(
            status_code=403,
            content={
                "error": {
                    "code": "TENANT_MISSING",
                    "message": "Uživatel nemá přiřazený tenant. Kontaktujte administrátora.",
                    "details": {"user_email": current_user.email}
                }
            }
        )
    
    logger.info(f"[VEHICLE_CREATE] tenant_id={tenant_id} vin={vehicle_data.vin} plate={vehicle_data.plate}")
    
    try:
        # Validace povinných polí
        if not vehicle_data.nickname or len(vehicle_data.nickname.strip()) < 2:
            raise HTTPException(status_code=422, detail="Zadejte název vozidla (min. 2 znaky)")
        if not vehicle_data.stk_valid_until:
            raise HTTPException(status_code=422, detail="Zadejte platnost STK (datum)")
        _validate_mileage_consistency(
            current_mileage_km=vehicle_data.current_mileage_km,
            last_stk_mileage_km=vehicle_data.last_stk_mileage_km,
        )
        
        # KROK 1: Zkontrolovat quota
        from ...licensing.service import assert_vehicle_quota, LicenseError
        try:
            assert_vehicle_quota(db, tenant_id)
        except LicenseError as e:
            logger.warning(f"[VEHICLE_CREATE] error_code={e.code} details={e.details}")
            return JSONResponse(
                status_code=e.status_code,
                content={
                    "error": {
                        "code": e.code,
                        "message": e.detail,
                        "details": e.details
                    }
                }
            )
        
        normalized_vin = _normalize_vin(vehicle_data.vin or "")
        if vehicle_data.orv_scan_id and not normalized_vin:
            raise HTTPException(status_code=422, detail="ORV scan vyžaduje potvrzený VIN. Doplňte jej ručně před uložením.")

        existing_global_vehicle = _find_existing_vehicle_by_vin_globally(db=db, vin=normalized_vin)
        if existing_global_vehicle is not None:
            active_owner_assignment = get_primary_vehicle_owner_assignment(db, int(existing_global_vehicle.id))
            active_owner = get_primary_vehicle_owner(db, existing_global_vehicle)
            if active_owner and active_owner.id == current_user.id and active_owner_assignment and active_owner_assignment.is_active:
                logger.warning("[VEHICLE_CREATE] error_code=VEHICLE_DUPLICATE details={which_field: vin, scope: global_same_owner}")
                return JSONResponse(
                    status_code=409,
                    content={
                        "error": {
                            "code": "VEHICLE_DUPLICATE",
                            "message": "Vozidlo s tímto VIN už ve vašem profilu existuje",
                            "details": {"which_field": "vin", "value": normalized_vin},
                        }
                    },
                )
            if active_owner and active_owner.id != current_user.id and active_owner_assignment and active_owner_assignment.is_active:
                raise HTTPException(
                    status_code=409,
                    detail="Vozidlo s tímto VIN už má aktivního vlastníka. Pro převod jej nejdřív odeberte z původního profilu.",
                )

            _apply_vehicle_claim_payload(existing_global_vehicle, vehicle_data)
            apply_orv_scan_to_vehicle(
                db=db,
                vehicle=existing_global_vehicle,
                current_user=current_user,
                scan_id=vehicle_data.orv_scan_id,
                orv_number=vehicle_data.orv_number,
                use_owner_data=vehicle_data.orv_use_owner_data,
                data_trust_state=vehicle_data.data_trust_state or "verified_by_user",
                create_payload=vehicle_data.dict(),
            )
            transfer_vehicle_to_new_owner(
                db,
                vehicle=existing_global_vehicle,
                new_owner=current_user,
                assigned_by_customer_id=current_user.id,
                ownership_origin="vin_claim",
            )
            db.commit()
            db.refresh(existing_global_vehicle)
            logger.info(f"[VEHICLE_CREATE] claimed existing vehicle by VIN: id={existing_global_vehicle.id}")
            return _vehicle_to_response_payload(existing_global_vehicle, current_user, db)

        duplicate_vehicle = _find_duplicate_vehicle_by_vin(
            db=db,
            tenant_id=tenant_id,
            vin=normalized_vin,
        )
        if duplicate_vehicle is not None:
            logger.warning("[VEHICLE_CREATE] error_code=VEHICLE_DUPLICATE details={which_field: vin}")
            return JSONResponse(
                status_code=409,
                content={
                    "error": {
                        "code": "VEHICLE_DUPLICATE",
                        "message": "Vozidlo s tímto VIN již existuje",
                        "details": {"which_field": "vin", "value": normalized_vin},
                    }
                },
            )

        # KROK 2: Vytvořit vozidlo
        vehicle = VehicleModel(
            user_email=current_user.email,
            tenant_id=tenant_id,
            nickname=vehicle_data.nickname,
            brand=vehicle_data.brand,
            model=vehicle_data.model,
            year=vehicle_data.year,
            engine=vehicle_data.engine,
            vin=normalized_vin or None,
            plate=vehicle_data.plate,
            notes=vehicle_data.notes,
            stk_valid_until=vehicle_data.stk_valid_until,
            current_mileage_km=vehicle_data.current_mileage_km,
            last_stk_mileage_km=vehicle_data.last_stk_mileage_km,
            mileage_checked_at=(
                datetime.utcnow()
                if vehicle_data.last_stk_mileage_km is not None
                else None
            ),
            tyres_info=vehicle_data.tyres_info,
            insurance_provider=vehicle_data.insurance_provider,
            insurance_valid_until=vehicle_data.insurance_valid_until
        )
        
        db.add(vehicle)
        db.flush()
        apply_orv_scan_to_vehicle(
            db=db,
            vehicle=vehicle,
            current_user=current_user,
            scan_id=vehicle_data.orv_scan_id,
            orv_number=vehicle_data.orv_number,
            use_owner_data=vehicle_data.orv_use_owner_data,
            data_trust_state=vehicle_data.data_trust_state or "verified_by_user",
            create_payload=vehicle_data.dict(),
        )
        ensure_vehicle_owner_assignment(
            db,
            vehicle=vehicle,
            owner=current_user,
            assigned_by_customer_id=current_user.id,
        )
        db.commit()
        db.refresh(vehicle)
        
        logger.info(f"[VEHICLE_CREATE] ✅ Vozidlo vytvořeno: id={vehicle.id}")
        return _vehicle_to_response_payload(vehicle, current_user, db)
        
    except IntegrityError as e:
        db.rollback()
        error_str = str(e.orig) if hasattr(e, 'orig') else str(e)
        
        # Detekce duplicitního VIN nebo SPZ
        which_field = None
        if 'vin' in error_str.lower() or 'unique constraint' in error_str.lower():
            # Zkontrolovat, zda je to VIN nebo SPZ
            if vehicle_data.vin:
                existing = db.query(VehicleModel).filter(
                    VehicleModel.vin == vehicle_data.vin,
                    VehicleModel.tenant_id == tenant_id
                ).first()
                if existing:
                    which_field = "vin"
        if not which_field and vehicle_data.plate:
            existing = db.query(VehicleModel).filter(
                VehicleModel.plate == vehicle_data.plate,
                VehicleModel.tenant_id == tenant_id
            ).first()
            if existing:
                which_field = "plate"
        
        if which_field:
            logger.warning(f"[VEHICLE_CREATE] error_code=VEHICLE_DUPLICATE details={{which_field: {which_field}}}")
            return JSONResponse(
                status_code=409,
                content={
                    "error": {
                        "code": "VEHICLE_DUPLICATE",
                        "message": f"Vozidlo s tímto {which_field.upper()} již existuje",
                        "details": {"which_field": which_field, "value": getattr(vehicle_data, which_field)}
                    }
                }
            )
        else:
            # Obecná IntegrityError
            logger.error(f"[VEHICLE_CREATE] error_code=INTEGRITY_ERROR details={{error: {error_str}}}")
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": "INTEGRITY_ERROR",
                        "message": "Chyba při ukládání vozidla do databáze",
                        "details": {"error": error_str}
                    }
                }
            )
    
    except HTTPException as e:
        # LicenseError dědí z HTTPException
        if hasattr(e, 'code'):
            # LicenseError
            logger.warning(f"[VEHICLE_CREATE] error_code={e.code} details={getattr(e, 'details', {})}")
            return JSONResponse(
                status_code=e.status_code,
                content={
                    "error": {
                        "code": e.code,
                        "message": e.detail,
                        "details": getattr(e, 'details', {})
                    }
                }
            )
        else:
            # Obecná HTTPException
            logger.error(f"[VEHICLE_CREATE] error_code=HTTP_ERROR status={e.status_code}")
            return JSONResponse(
                status_code=e.status_code,
                content={
                    "error": {
                        "code": "HTTP_ERROR",
                        "message": e.detail,
                        "details": {}
                    }
                }
            )
    
    except Exception as e:
        db.rollback()
        import traceback
        error_traceback = "".join(traceback.format_exception(type(e), e, e.__traceback__))
        logger.error(f"[VEHICLE_CREATE] error_code=UNKNOWN_ERROR details={{error: {str(e)}}}")
        logger.error(f"[VEHICLE_CREATE] Traceback:\n{error_traceback}")
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "UNKNOWN_ERROR",
                    "message": f"Neočekávaná chyba: {str(e)}",
                    "details": {"error_type": type(e).__name__}
                }
            }
        )


@router.get("", response_model=List[VehicleOutV1])
def get_vehicles(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Vrací všechna vozidla uživatele"""
    import logging
    import traceback
    logger = logging.getLogger(__name__)
    _ensure_vehicle_photo_column(db)
    
    try:
        logger.info(f"[VEHICLES] ========================================")
        logger.info(f"[VEHICLES] GET /api/v1/vehicles - Načítání vozidel")
        logger.info(f"[VEHICLES] User: {current_user.email}")
        logger.info(f"[VEHICLES] Tenant ID: {getattr(current_user, 'tenant_id', 'N/A')}")
        print(f"[VEHICLES] Načítání vozidel pro uživatele: {current_user.email}")
        print(f"[VEHICLES] Tenant ID uživatele: {getattr(current_user, 'tenant_id', 'N/A')}")
        
        tenant_id = getattr(current_user, "tenant_id", None)
        if tenant_id is None:
            logger.error("[VEHICLES] User bez tenant_id - fail safe 403")
            raise HTTPException(status_code=403, detail="Uživatel nemá přiřazený tenant")

        print(f"[VEHICLES] Filtrování podle tenant_id: {tenant_id}")
        owned_vehicle_ids = set()
        from ..models import VehicleOwnership
        current_user_id = getattr(current_user, "id", None)

        if current_user_id is not None:
            ownership_rows = (
                db.query(VehicleOwnership.vehicle_id)
                .filter(
                    VehicleOwnership.customer_id == current_user_id,
                    VehicleOwnership.tenant_id == tenant_id,
                    VehicleOwnership.is_active.is_(True),
                )
                .all()
            )
            for (vehicle_id,) in ownership_rows:
                if vehicle_id:
                    owned_vehicle_ids.add(int(vehicle_id))

        if not owned_vehicle_ids:
            legacy_vehicles = (
                db.query(VehicleModel)
                .filter(
                    VehicleModel.user_email == current_user.email,
                    VehicleModel.tenant_id == tenant_id,
                )
                .all()
            )
            for vehicle in legacy_vehicles:
                backfill_vehicle_owner_assignment(db, vehicle)
                owned_vehicle_ids.add(int(vehicle.id))
            if legacy_vehicles:
                db.commit()

        vehicles = []
        if owned_vehicle_ids:
            vehicles = (
                db.query(VehicleModel)
                .filter(
                    VehicleModel.id.in_(owned_vehicle_ids),
                    VehicleModel.tenant_id == tenant_id,
                )
                .all()
            )

        print(f"[VEHICLES] Nalezeno {len(vehicles)} vozidel")
        
        # Zkusit explicitně serializovat každé vozidlo, abychom zachytili případné chyby
        result = []
        for idx, vehicle in enumerate(vehicles):
            try:
                # Zkontrolovat, zda vozidlo má všechny potřebné atributy
                if not hasattr(vehicle, 'id'):
                    logger.warning(f"[VEHICLES] WARNING: Vozidlo #{idx} nemá ID, přeskočeno")
                    print(f"[VEHICLES] WARNING: Vozidlo nemá ID, přeskočeno")
                    continue
                
                logger.debug(f"[VEHICLES] Serializuji vozidlo ID {vehicle.id}")
                
                # Zkusit vytvořit VehicleOutV1 pro validaci
                vehicle_dict = {
                    'id': vehicle.id,
                    'user_email': getattr(vehicle, 'user_email', None),
                    'nickname': getattr(vehicle, 'nickname', None),
                    'brand': getattr(vehicle, 'brand', None),
                    'model': getattr(vehicle, 'model', None),
                    'year': getattr(vehicle, 'year', None),
                    'engine': getattr(vehicle, 'engine', None),
                    'vin': getattr(vehicle, 'vin', None),
                    'plate': getattr(vehicle, 'plate', None),
                    'notes': getattr(vehicle, 'notes', None),
                    'photo_path': getattr(vehicle, 'photo_path', None),
                    'stk_valid_until': getattr(vehicle, 'stk_valid_until', None),
                    'current_mileage_km': getattr(vehicle, 'current_mileage_km', None),
                    'last_stk_mileage_km': getattr(vehicle, 'last_stk_mileage_km', None),
                    'mileage_checked_at': getattr(vehicle, 'mileage_checked_at', None),
                    'tyres_info': getattr(vehicle, 'tyres_info', None),
                    'insurance_provider': getattr(vehicle, 'insurance_provider', None),
                    'insurance_valid_until': getattr(vehicle, 'insurance_valid_until', None),
                    'tenant_id': getattr(vehicle, 'tenant_id', None),
                    'created_at': getattr(vehicle, 'created_at', None)
                }
                
                # Validovat pomocí schématu
                VehicleOutV1(**vehicle_dict)
                result.append(vehicle)
            except Exception as veh_error:
                import traceback
                vehicle_id = getattr(vehicle, 'id', 'unknown')
                error_traceback = "".join(traceback.format_exception(type(veh_error), veh_error, veh_error.__traceback__))
                logger.error(f"[VEHICLES] ERROR: Chyba při validaci vozidla ID {vehicle_id}: {veh_error}")
                logger.error(f"[VEHICLES] Traceback:\n{error_traceback}")
                print(f"[VEHICLES] ERROR: Chyba při validaci vozidla ID {vehicle_id}: {veh_error}")
                traceback.print_exc()
                # Pokračovat s dalšími vozidly místo selhání celého dotazu
        
        logger.info(f"[VEHICLES] ✅ Úspěšně načteno {len(result)} vozidel")
        print(f"[VEHICLES] Vracím {len(result)} validních vozidel")
        return result
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        error_traceback = "".join(traceback.format_exception(type(e), e, e.__traceback__))
        error_msg = str(e) if str(e) else "Neznámá chyba"
        logger.error(f"[VEHICLES] ❌ FATAL ERROR: {error_msg}")
        logger.error(f"[VEHICLES] Traceback:\n{error_traceback}")
        print(f"[VEHICLES] FATAL ERROR: {error_msg}")
        traceback.print_exc()
        error_type = type(e).__name__
        print(f"[ERROR] Chyba při načítání vozidel: {error_type}: {error_msg}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání vozidel: {error_type}: {error_msg}")


@router.post("/tachometer/challenge", response_model=TachometerChallengeResponse)
def create_tachometer_challenge(
    payload: Optional[TachometerChallengeRequest] = Body(default=None),
    current_user: Customer = Depends(get_current_user),
) -> TachometerChallengeResponse:
    """
    Načte captcha challenge z kontrolatachometru.cz.
    Uživatel opíše kód a následně zavolá /tachometer/lookup.
    """
    _ = current_user
    expected_vin = None
    if payload and payload.vin:
        normalized_vin = _normalize_vin(payload.vin)
        expected_vin = normalized_vin if len(normalized_vin) == 17 else None
    challenge = _create_tachometer_session(expected_vin=expected_vin, vehicle_id=None)
    return TachometerChallengeResponse(
        challenge_id=challenge.session_id,
        captcha_image_base64=challenge.captcha_image_base64,
        captcha_mime_type=challenge.captcha_mime_type,
        expires_in_seconds=challenge.expires_in_seconds,
    )


@router.post("/tachometer/lookup", response_model=TachometerLookupResponse)
def lookup_tachometer(
    payload: TachometerLookupRequest,
    current_user: Customer = Depends(get_current_user),
) -> TachometerLookupResponse:
    """
    Ověří captcha kód a vrátí poslední známý stav km ze STK/emisí.
    """
    _ = current_user
    vin = _normalize_vin(payload.vin)
    if len(vin) < 5:
        raise HTTPException(status_code=422, detail="VIN není ve validním formátu.")
    return _lookup_tachometer_with_session(
        session_id=payload.challenge_id,
        vin=vin,
        captcha_code=str(payload.captcha_code or "").strip(),
    )


@router.post("/{vehicle_id}/tachometer/init", response_model=VehicleTachometerInitResponse)
def init_vehicle_tachometer(
    vehicle_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VehicleTachometerInitResponse:
    vehicle = _get_accessible_vehicle_or_404(vehicle_id, current_user, db)
    vin = _normalize_vin(getattr(vehicle, "vin", "") or "")
    if len(vin) != 17:
        raise HTTPException(
            status_code=422,
            detail="Pro kontrolu tachometru musí mít vozidlo uložené validní VIN (17 znaků).",
        )
    return _create_tachometer_session(expected_vin=vin, vehicle_id=vehicle.id)


@router.post("/{vehicle_id}/tachometer/submit", response_model=VehicleTachometerSubmitResponse)
def submit_vehicle_tachometer(
    vehicle_id: int,
    payload: VehicleTachometerSubmitRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VehicleTachometerSubmitResponse:
    vehicle = _get_accessible_vehicle_or_404(vehicle_id, current_user, db)
    vin = _normalize_vin(getattr(vehicle, "vin", "") or "")
    if len(vin) != 17:
        raise HTTPException(
            status_code=422,
            detail="Pro kontrolu tachometru musí mít vozidlo uložené validní VIN (17 znaků).",
        )

    with _TACHOMETER_CHALLENGE_LOCK:
        stored_session = _TACHOMETER_CHALLENGE_STORE.get(payload.session_id)
    if not stored_session:
        raise HTTPException(
            status_code=410,
            detail="Captcha session vypršela nebo je neplatná. Načtěte nový obrázek.",
        )
    if stored_session.get("vehicle_id") not in {None, vehicle.id}:
        raise HTTPException(
            status_code=409,
            detail="Captcha session patří k jinému vozidlu. Načtěte nový obrázek pro aktuální VIN.",
        )

    lookup = _lookup_tachometer_with_session(
        session_id=payload.session_id,
        vin=vin,
        captcha_code=str(payload.captcha_code or "").strip(),
    )
    vehicle_payload, created_record_id = _store_tachometer_mileage_result(
        vehicle=vehicle,
        lookup=lookup,
        current_user=current_user,
        db=db,
    )
    return VehicleTachometerSubmitResponse(
        vehicle=vehicle_payload,
        latest_mileage_km=lookup.latest_mileage_km,
        latest_check_date=lookup.latest_check_date,
        inspections=lookup.inspections,
        created_record_id=created_record_id,
    )


@router.get("/{vehicle_id}/tachometer/history", response_model=List[VehicleTachometerHistoryEntryResponse])
def get_vehicle_tachometer_history(
    vehicle_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[VehicleTachometerHistoryEntryResponse]:
    _ = _get_accessible_vehicle_or_404(vehicle_id, current_user, db)
    return _build_tachometer_history_entries(vehicle_id, db)


@router.get(
    "/{vehicle_id}/tachometer/history/{entry_id}",
    response_model=VehicleTachometerHistoryEntryDetailResponse,
)
def get_vehicle_tachometer_history_entry_detail(
    vehicle_id: int,
    entry_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VehicleTachometerHistoryEntryDetailResponse:
    _ = _get_accessible_vehicle_or_404(vehicle_id, current_user, db)
    item = _get_normalized_tachometer_history_item_or_404(vehicle_id=vehicle_id, entry_id=entry_id, db=db)
    return _tachometer_history_entry_to_detail(item)


@router.get(
    "/{vehicle_id}/tachometer/history/{entry_id}/documents",
    response_model=List[VehicleTachometerDocumentResponse],
)
def get_vehicle_tachometer_history_entry_documents(
    vehicle_id: int,
    entry_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> List[VehicleTachometerDocumentResponse]:
    _ = _get_accessible_vehicle_or_404(vehicle_id, current_user, db)
    item = _get_normalized_tachometer_history_item_or_404(vehicle_id=vehicle_id, entry_id=entry_id, db=db)
    entry = item.canonical_entry
    return _serialize_tachometer_documents(getattr(entry, "documents_json", None))


@router.get("/{vehicle_id}", response_model=VehicleOutV1)
def get_vehicle(
    vehicle_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Vrací konkrétní vozidlo podle ID"""
    _ensure_vehicle_photo_column(db)
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()
    
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    
    # Kontrola přístupu
    if not can_access_vehicle(vehicle_id, current_user, db):
        raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")

    return _vehicle_to_response_payload(vehicle, current_user, db)


@router.post("/{vehicle_id}/mileage", response_model=VehicleMileageRecordResultV1)
def record_vehicle_mileage(
    vehicle_id: int,
    payload: VehicleMileageRecordV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Zapíše aktuální stav tachometru a uloží auditní záznam do servisní historie."""
    _ensure_vehicle_photo_column(db)
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()

    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")

    if not can_access_vehicle(vehicle_id, current_user, db):
        raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")

    current_mileage = getattr(vehicle, "current_mileage_km", None)
    if (
        current_mileage is not None
        and payload.mileage_km < current_mileage
        and not payload.confirm_lower_than_current
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "Nový stav km je nižší než poslední evidovaný stav. "
                    "Pokud jde o opravu nebo zpřesnění údajů, potvrďte zápis znovu."
                ),
                "current_mileage_km": current_mileage,
            },
        )

    _validate_mileage_consistency(
        current_mileage_km=payload.mileage_km,
        last_stk_mileage_km=getattr(vehicle, "last_stk_mileage_km", None),
    )

    vehicle.current_mileage_km = payload.mileage_km

    mileage_record = ServiceRecordModel(
        tenant_id=vehicle.tenant_id,
        vehicle_id=vehicle.id,
        user_id=getattr(current_user, "id", None),
        performed_at=datetime.utcnow(),
        mileage=payload.mileage_km,
        description="Zápis aktuálního stavu tachometru",
        note=(payload.note.strip() if payload.note else None),
        category="JINE",
        created_by_ai=False,
    )
    db.add(mileage_record)
    db.flush()
    db.commit()
    db.refresh(vehicle)
    db.refresh(mileage_record)

    return VehicleMileageRecordResultV1(
        vehicle=_vehicle_to_response_payload(vehicle, current_user, db),
        created_record_id=mileage_record.id,
    )


@router.put("/{vehicle_id}", response_model=VehicleOutV1)
def update_vehicle(
    vehicle_id: int,
    vehicle_data: VehicleUpdateV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Aktualizuje vozidlo"""
    _ensure_vehicle_photo_column(db)
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()
    
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    
    # Kontrola přístupu
    if not can_access_vehicle(vehicle_id, current_user, db):
        raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")

    effective_current_mileage = (
        vehicle_data.current_mileage_km
        if vehicle_data.current_mileage_km is not None
        else getattr(vehicle, "current_mileage_km", None)
    )
    effective_last_stk_mileage = (
        vehicle_data.last_stk_mileage_km
        if vehicle_data.last_stk_mileage_km is not None
        else getattr(vehicle, "last_stk_mileage_km", None)
    )
    _validate_mileage_consistency(
        current_mileage_km=effective_current_mileage,
        last_stk_mileage_km=effective_last_stk_mileage,
    )

    if vehicle_data.vin is not None:
        normalized_vin = _normalize_vin(vehicle_data.vin)
        if vehicle_data.orv_scan_id and not normalized_vin:
            raise HTTPException(status_code=422, detail="ORV scan vyžaduje potvrzený VIN. Doplňte jej ručně před uložením.")
        if normalized_vin:
            duplicate_vehicle = _find_duplicate_vehicle_by_vin(
                db=db,
                tenant_id=getattr(vehicle, "tenant_id", None),
                vin=normalized_vin,
                exclude_vehicle_id=vehicle.id,
            )
            if duplicate_vehicle is not None:
                raise HTTPException(status_code=409, detail="Vozidlo s tímto VIN již existuje")
            vehicle.vin = normalized_vin
        else:
            vehicle.vin = None
    
    # Aktualizace polí
    if vehicle_data.nickname is not None:
        vehicle.nickname = vehicle_data.nickname
    if vehicle_data.brand is not None:
        vehicle.brand = vehicle_data.brand
    if vehicle_data.model is not None:
        vehicle.model = vehicle_data.model
    if vehicle_data.year is not None:
        vehicle.year = vehicle_data.year
    if vehicle_data.engine is not None:
        vehicle.engine = vehicle_data.engine
    if vehicle_data.plate is not None:
        vehicle.plate = vehicle_data.plate
    if vehicle_data.notes is not None:
        vehicle.notes = vehicle_data.notes
    if vehicle_data.stk_valid_until is not None:
        vehicle.stk_valid_until = vehicle_data.stk_valid_until
    if vehicle_data.current_mileage_km is not None:
        vehicle.current_mileage_km = vehicle_data.current_mileage_km
    if vehicle_data.last_stk_mileage_km is not None:
        vehicle.last_stk_mileage_km = vehicle_data.last_stk_mileage_km
        vehicle.mileage_checked_at = datetime.utcnow()
    if vehicle_data.tyres_info is not None:
        vehicle.tyres_info = vehicle_data.tyres_info
    if vehicle_data.insurance_provider is not None:
        vehicle.insurance_provider = vehicle_data.insurance_provider
    if vehicle_data.insurance_valid_until is not None:
        vehicle.insurance_valid_until = vehicle_data.insurance_valid_until
    if vehicle_data.data_trust_state is not None:
        vehicle.data_trust_state = vehicle_data.data_trust_state
    if vehicle_data.orv_number is not None:
        vehicle.orv_number = str(vehicle_data.orv_number or "").strip() or None
    apply_orv_scan_to_vehicle(
        db=db,
        vehicle=vehicle,
        current_user=current_user,
        scan_id=vehicle_data.orv_scan_id,
        orv_number=vehicle_data.orv_number,
        use_owner_data=bool(vehicle_data.orv_use_owner_data),
        data_trust_state=vehicle_data.data_trust_state or getattr(vehicle, "data_trust_state", None) or "verified_by_user",
        create_payload=vehicle_data.dict(exclude_unset=False),
    )
    
    # DOČASNĚ ZAKÁZÁNO: Aktualizace assigned_service_id - dokud se neprovede migrace databáze
    # if vehicle_data.assigned_service_id is not None:
    #     if vehicle_data.assigned_service_id == 0 or vehicle_data.assigned_service_id == -1:
    #         vehicle.assigned_service_id = None
    #     else:
    #         service = db.query(Customer).filter(
    #             Customer.id == vehicle_data.assigned_service_id,
    #             Customer.role == "service"
    #         ).first()
    #         if not service:
    #             raise HTTPException(status_code=400, detail="Zadaný servis neexistuje nebo není servisem")
    #         vehicle.assigned_service_id = service.id
    # elif hasattr(vehicle_data, 'assigned_service_id') and vehicle_data.assigned_service_id is None:
    #     vehicle.assigned_service_id = None
    
    db.commit()
    db.refresh(vehicle)
    
    return _vehicle_to_response_payload(vehicle, current_user, db)


@router.get("/{vehicle_id}/photo")
def get_vehicle_photo(
    vehicle_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Vrátí fotku vozidla (pokud je nahraná)."""
    _ensure_vehicle_photo_column(db)
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")

    if not can_access_vehicle(vehicle_id, current_user, db):
        raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")

    photo_file = _get_vehicle_photo_file(getattr(vehicle, "photo_path", None))
    if not photo_file:
        raise HTTPException(status_code=404, detail="Fotka vozidla nebyla nalezena")

    media_type = mimetypes.guess_type(str(photo_file))[0] or "application/octet-stream"
    return FileResponse(path=str(photo_file), media_type=media_type, filename=photo_file.name)


@router.post("/{vehicle_id}/photo")
def upload_vehicle_photo(
    vehicle_id: int,
    payload: VehiclePhotoUploadRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Nahraje/aktualizuje fotku vozidla (pro uživatele i servis)."""
    _ensure_vehicle_photo_column(db)
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")

    if not can_access_vehicle(vehicle_id, current_user, db):
        raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")

    content = _decode_base64_payload(payload.file_content_base64)
    if not content:
        raise HTTPException(status_code=422, detail="Nahraný soubor je prázdný.")
    if len(content) > MAX_VEHICLE_PHOTO_RAW_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="Fotka je příliš velká pro zpracování (max 40 MB vstupních dat).")

    mime_type = str(payload.file_mime_type or "").lower().strip()
    if mime_type and not mime_type.startswith("image/"):
        raise HTTPException(status_code=415, detail="Podporované jsou pouze obrázky.")

    normalized_content = _normalize_vehicle_photo(content)

    tenant_id = int(getattr(vehicle, "tenant_id", None) or getattr(current_user, "tenant_id", None) or 0)
    target_dir = VEHICLE_PHOTOS_DIR / f"tenant_{tenant_id}" / f"vehicle_{vehicle.id}"
    target_dir.mkdir(parents=True, exist_ok=True)

    filename = f"photo_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(6)}.jpg"
    target_file = target_dir / filename
    target_file.write_bytes(normalized_content)

    previous_file = _get_vehicle_photo_file(getattr(vehicle, "photo_path", None))
    vehicle.photo_path = target_file.relative_to(VEHICLE_PHOTOS_DIR).as_posix()
    db.commit()
    db.refresh(vehicle)

    if previous_file and previous_file != target_file:
        try:
            previous_file.unlink(missing_ok=True)
        except Exception:
            pass

    return {
        "message": "Fotka vozidla byla úspěšně nahrána a serverově normalizována na 1280x720 JPEG.",
        "photo_path": vehicle.photo_path,
        "photo_url": f"/api/v1/vehicles/{vehicle.id}/photo?v={int(datetime.utcnow().timestamp())}",
    }


@router.delete("/{vehicle_id}/photo")
def delete_vehicle_photo(
    vehicle_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Smaže fotku vozidla."""
    _ensure_vehicle_photo_column(db)
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")

    if not can_access_vehicle(vehicle_id, current_user, db):
        raise HTTPException(status_code=403, detail="Nemáte přístup k tomuto vozidlu")

    photo_file = _get_vehicle_photo_file(getattr(vehicle, "photo_path", None))
    vehicle.photo_path = None
    db.commit()

    if photo_file:
        try:
            photo_file.unlink(missing_ok=True)
        except Exception:
            pass

    return {"message": "Fotka vozidla byla smazána."}


@router.delete("/{vehicle_id}")
def delete_vehicle(
    vehicle_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Odebere vozidlo z profilu aktuálního vlastníka, ale zachová jeho historii v databázi."""
    _ensure_vehicle_photo_column(db)
    vehicle = db.query(VehicleModel).filter(VehicleModel.id == vehicle_id).first()
    
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
    
    # Kontrola přístupu - pouze vlastník může smazat
    owner_decision = vehicle_write_policy(
        role=current_user.role,
        is_owner=user_owns_vehicle(db, current_user, vehicle),
    )
    if not owner_decision.allowed:
        raise HTTPException(status_code=403, detail="Nemáte oprávnění smazat toto vozidlo")
    
    try:
        released = release_vehicle_owner_assignment(db, vehicle=vehicle, owner=current_user)
        if not released:
            raise HTTPException(status_code=409, detail="Aktuální vlastnická vazba vozidla už není aktivní.")

        _revoke_vehicle_service_links_for_owner_release(
            db,
            vehicle_id=vehicle_id,
            revoked_by_customer_id=current_user.id,
            reason="Vozidlo bylo odebráno z profilu vlastníka.",
        )

        db.commit()

        return {
            "message": (
                "Vozidlo bylo odebráno z vašeho profilu. Historie a servisní záznamy zůstaly "
                "bezpečně uložené pro případný budoucí převod na nového vlastníka."
            )
        }
    except Exception as e:
        db.rollback()
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=500, detail=f"Chyba při odebrání vozidla z profilu: {str(e)}")
