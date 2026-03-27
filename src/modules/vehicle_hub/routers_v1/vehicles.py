"""
Vehicles API v1.0 router
"""
from datetime import datetime, timedelta
import base64
import binascii
import html
import mimetypes
from pathlib import Path
import re
import secrets
import threading
import unicodedata
from urllib.parse import urljoin

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import requests
from sqlalchemy.orm import Session
from typing import Any, Dict, List, Optional

from src.core.config import DATA_DIR
from src.core.rbac import is_admin, vehicle_write_policy
from ..database import get_db
from ..models import Vehicle as VehicleModel, Customer
from ..ownership import (
    backfill_vehicle_owner_assignment,
    ensure_vehicle_owner_assignment,
    get_primary_vehicle_owner,
    user_owns_vehicle,
)
from ..schema_management import assert_module_ready
from .auth import get_current_user, can_access_vehicle
from .schemas import VehicleCreateV1, VehicleUpdateV1, VehicleOutV1

router = APIRouter(prefix="/vehicles", tags=["vehicles-v1"])

VEHICLE_PHOTOS_DIR = DATA_DIR / "vehicle_photos"
VEHICLE_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
MAX_VEHICLE_PHOTO_SIZE_BYTES = 10 * 1024 * 1024
ALLOWED_VEHICLE_PHOTO_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
    ".bmp",
    ".heic",
    ".heif",
}
MIME_TO_EXTENSION = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/bmp": ".bmp",
    "image/heic": ".heic",
    "image/heif": ".heif",
}


class VehiclePhotoUploadRequest(BaseModel):
    file_name: str = Field(..., min_length=1, max_length=255)
    file_mime_type: str = Field(default="image/jpeg", max_length=255)
    file_content_base64: str = Field(..., min_length=20, max_length=20_000_000)


TACHOMETER_BASE_URL = "https://kontrolatachometru.cz"
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


class TachometerLookupRequest(BaseModel):
    challenge_id: str = Field(..., min_length=10, max_length=255)
    vin: str = Field(..., min_length=5, max_length=32)
    captcha_code: str = Field(..., min_length=2, max_length=16)


class TachometerInspectionOut(BaseModel):
    check_date: Optional[datetime] = None
    mileage_km: int
    protocol_number: Optional[str] = None
    inspection_type: Optional[str] = None


class TachometerLookupResponse(BaseModel):
    vin: str
    latest_mileage_km: int
    latest_check_date: Optional[datetime] = None
    inspections: List[TachometerInspectionOut]
    source: str = "kontrolatachometru.cz"


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


def _parse_tachometer_inspections(search_html: str) -> List[TachometerInspectionOut]:
    rows = re.findall(
        r"<tr[^>]*data-row-id=\"[^\"]+\"[^>]*>.*?</tr>",
        search_html,
        flags=re.I | re.S,
    )
    inspections: list[TachometerInspectionOut] = []
    for row in rows:
        mileage_km = _parse_km_value(_extract_td_value(row, "data-km-staff"))
        if mileage_km is None:
            continue
        inspections.append(
            TachometerInspectionOut(
                check_date=_parse_cz_date(_extract_td_value(row, "data-finish-date")),
                mileage_km=mileage_km,
                protocol_number=_strip_html(_extract_td_value(row, "data-protocol-number")) or None,
                inspection_type=_strip_html(_extract_td_value(row, "data-inspection-type-name")) or None,
            )
        )

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


def _vehicle_to_response_payload(vehicle: VehicleModel, current_user: Customer, db: Session) -> dict:
    owner = get_primary_vehicle_owner(db, vehicle)
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
        "notes": getattr(vehicle, "notes", None),
        "photo_path": getattr(vehicle, "photo_path", None),
        "stk_valid_until": getattr(vehicle, "stk_valid_until", None),
        "current_mileage_km": getattr(vehicle, "current_mileage_km", None),
        "last_stk_mileage_km": getattr(vehicle, "last_stk_mileage_km", None),
        "mileage_checked_at": getattr(vehicle, "mileage_checked_at", None),
        "tyres_info": getattr(vehicle, "tyres_info", None),
        "insurance_provider": getattr(vehicle, "insurance_provider", None),
        "insurance_valid_until": getattr(vehicle, "insurance_valid_until", None),
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
        ensure_vehicle_owner_assignment(
            db,
            vehicle=vehicle,
            owner=current_user,
            assigned_by_customer_id=current_user.id,
        )
        db.commit()
        db.refresh(vehicle)
        
        logger.info(f"[VEHICLE_CREATE] ✅ Vozidlo vytvořeno: id={vehicle.id}")
        return vehicle
        
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
    current_user: Customer = Depends(get_current_user),
) -> TachometerChallengeResponse:
    """
    Načte captcha challenge z kontrolatachometru.cz.
    Uživatel opíše kód a následně zavolá /tachometer/lookup.
    """
    _ = current_user
    _cleanup_tachometer_challenge_store()
    try:
        with requests.Session() as session:
            session.headers.update(
                {
                    "User-Agent": "TooZHub/1.0 (+https://hub.toozservis.cz)",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                }
            )
            page_response = session.get(
                TACHOMETER_BASE_URL,
                timeout=_TACHOMETER_HTTP_TIMEOUT_SECONDS,
            )
            page_response.raise_for_status()
            token = _extract_hidden_token(page_response.text)
            captcha_src = _extract_captcha_src(page_response.text)
            if not token or not captcha_src:
                raise HTTPException(
                    status_code=502,
                    detail="Nepodařilo se načíst challenge z kontrolatachometru.cz.",
                )

            captcha_url = urljoin(TACHOMETER_BASE_URL, captcha_src)
            captcha_response = session.get(
                captcha_url,
                timeout=_TACHOMETER_HTTP_TIMEOUT_SECONDS,
            )
            captcha_response.raise_for_status()
            captcha_bytes = captcha_response.content
            if not captcha_bytes:
                raise HTTPException(
                    status_code=502,
                    detail="Captcha obrázek je prázdný. Zkuste to prosím znovu.",
                )

            challenge_id = secrets.token_urlsafe(24)
            challenge_data = {
                "created_at": datetime.utcnow(),
                "request_verification_token": token,
                "cookies": requests.utils.dict_from_cookiejar(session.cookies),
            }
            with _TACHOMETER_CHALLENGE_LOCK:
                _TACHOMETER_CHALLENGE_STORE[challenge_id] = challenge_data

            return TachometerChallengeResponse(
                challenge_id=challenge_id,
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


@router.post("/tachometer/lookup", response_model=TachometerLookupResponse)
def lookup_tachometer(
    payload: TachometerLookupRequest,
    current_user: Customer = Depends(get_current_user),
) -> TachometerLookupResponse:
    """
    Ověří captcha kód a vrátí poslední známý stav km ze STK/emisí.
    """
    _ = current_user
    _cleanup_tachometer_challenge_store()

    with _TACHOMETER_CHALLENGE_LOCK:
        challenge = _TACHOMETER_CHALLENGE_STORE.pop(payload.challenge_id, None)
    if not challenge:
        raise HTTPException(
            status_code=410,
            detail="Captcha challenge vypršel nebo je neplatný. Načtěte nový obrázek.",
        )

    vin = _normalize_vin(payload.vin)
    if len(vin) < 5:
        raise HTTPException(status_code=422, detail="VIN není ve validním formátu.")

    captcha_code = str(payload.captcha_code or "").strip()
    if len(captcha_code) < 2:
        raise HTTPException(status_code=422, detail="Zadejte captcha kód z obrázku.")

    try:
        with requests.Session() as session:
            session.headers.update(
                {
                    "User-Agent": "TooZHub/1.0 (+https://hub.toozservis.cz)",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Referer": TACHOMETER_BASE_URL,
                }
            )
            cookie_dict = challenge.get("cookies", {})
            if isinstance(cookie_dict, dict):
                session.cookies.update(cookie_dict)

            form_data = {
                "__RequestVerificationToken": challenge.get("request_verification_token", ""),
                "VIN": vin,
                "captcha$TB": captcha_code,
            }

            response = session.post(
                urljoin(TACHOMETER_BASE_URL, TACHOMETER_SEARCH_PATH),
                data=form_data,
                timeout=_TACHOMETER_HTTP_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            search_html = response.text

            if _contains_captcha_error(search_html):
                raise HTTPException(status_code=422, detail=_TACHOMETER_CAPTCHA_ERROR_TEXT)

            inspections = _parse_tachometer_inspections(search_html)
            if not inspections:
                raise HTTPException(
                    status_code=404,
                    detail="Pro zadané VIN nebyly nalezeny žádné údaje STK/emisí.",
                )

            latest = inspections[0]
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
            detail=f"Nepodařilo se ověřit tachometr: {exc}",
        ) from exc


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
    if len(content) > MAX_VEHICLE_PHOTO_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="Fotka je příliš velká (max 10 MB).")

    mime_type = str(payload.file_mime_type or "").lower().strip()
    if mime_type and not mime_type.startswith("image/"):
        raise HTTPException(status_code=415, detail="Podporované jsou pouze obrázky.")

    extension = Path(payload.file_name or "").suffix.lower().strip()
    if extension and extension not in ALLOWED_VEHICLE_PHOTO_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Nepodporovaný formát obrázku.")
    if not extension:
        extension = MIME_TO_EXTENSION.get(mime_type, ".jpg")

    tenant_id = int(getattr(vehicle, "tenant_id", None) or getattr(current_user, "tenant_id", None) or 0)
    target_dir = VEHICLE_PHOTOS_DIR / f"tenant_{tenant_id}" / f"vehicle_{vehicle.id}"
    target_dir.mkdir(parents=True, exist_ok=True)

    filename = f"photo_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(6)}{extension}"
    target_file = target_dir / filename
    target_file.write_bytes(content)

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
        "message": "Fotka vozidla byla úspěšně nahrána.",
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
    """Smaže vozidlo a všechny související záznamy"""
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
        # Smazat fotku vozidla ze souborového systému
        vehicle_photo_file = _get_vehicle_photo_file(getattr(vehicle, "photo_path", None))
        if vehicle_photo_file:
            try:
                vehicle_photo_file.unlink(missing_ok=True)
            except Exception:
                pass

        # Smazat související servisní záznamy
        from ..models import ServiceRecord as ServiceRecordModel
        service_records = db.query(ServiceRecordModel).filter(
            ServiceRecordModel.vehicle_id == vehicle_id
        ).all()
        for record in service_records:
            for attachment_file in _extract_service_record_attachment_files(record.attachments):
                try:
                    attachment_file.unlink(missing_ok=True)
                except Exception:
                    pass
            db.delete(record)
        
        # Smazat související připomínky
        from ..models import Reminder
        reminders = db.query(Reminder).filter(
            Reminder.vehicle_id == vehicle_id
        ).all()
        for reminder in reminders:
            db.delete(reminder)
        
        # Smazat související rezervace
        from ..models import Reservation
        reservations = db.query(Reservation).filter(
            Reservation.vehicle_id == vehicle_id
        ).all()
        for reservation in reservations:
            db.delete(reservation)
        
        # Smazat vozidlo
        db.delete(vehicle)
        db.commit()
        
        return {"message": "Vozidlo a všechny související záznamy byly smazány"}
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při mazání vozidla: {str(e)}")
