"""
Services API v1.0 router
Endpointy pro správu servisů
"""
import json
import math
import time
from datetime import datetime
from typing import Any, Dict, Optional
from urllib.parse import quote
from urllib.request import Request as UrlRequest, urlopen

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from src.core.branding import APP_SERVER_PRODUCT_TOKEN
from src.core.rbac import is_admin
from ..database import get_db
from ..models import Customer, ServiceAccessRequest, ServiceCustomerLink, ServiceVehicleAccess, Vehicle, VehicleServiceLink
from ..ownership import get_owned_vehicle, get_owned_vehicle_ids
from ..schema_management import assert_module_ready
from ..service_access import create_or_update_vehicle_service_link, revoke_vehicle_service_link, vehicle_label
from .auth import get_current_user
from .schemas import (
    ServiceAccessRequestCreateV1,
    ServiceAccessRequestDecisionV1,
    ServiceAccessRequestListOutV1,
    ServiceApprovedVehicleListOutV1,
    ServiceVehicleLookupRequestV1,
    ServiceVehicleLookupResponseV1,
    VehicleServiceLinkListOutV1,
)

router = APIRouter(prefix="/services", tags=["services-v1"])

_SERVICE_GEO_CACHE: Dict[str, Dict[str, Any]] = {}
_SERVICE_GEO_CACHE_TTL_SEC = 7 * 24 * 60 * 60  # 7 dní
_SERVICE_GEO_CACHE_MAX_ITEMS = 3000
_SERVICE_GEOLOOKUP_URL = (
    "https://nominatim.openstreetmap.org/search?format=jsonv2&accept-language=cs&limit=1&q={query}"
)
_SERVICE_GEOLOOKUP_TIMEOUT_SEC = 1.8
_SERVICE_GEOLOOKUP_MAX_NEW_LOOKUPS_PER_REQUEST = 25


class VehicleAccessGrantRequest(BaseModel):
    vehicle_id: int = Field(gt=0)
    service_id: int = Field(gt=0)
    note: Optional[str] = Field(default=None, max_length=500)
    conflict_strategy: Optional[str] = Field(default="keep", max_length=32)  # ask | keep | replace


def _normalize_email(value: Optional[str]) -> str:
    return str(value or "").strip().lower()


def _is_admin_role(role: Optional[str]) -> bool:
    return is_admin(role)


def _ensure_services_schema(db: Session) -> None:
    assert_module_ready(db, "service_workspace", detail_prefix="Servisní propojení není připravené")


def _access_scope_summary() -> str:
    return "Čtení historie vozidla a možnost vytvářet nové servisní záznamy bez úprav starších cizích záznamů."


def _upsert_service_customer_link(
    db: Session,
    *,
    service_customer_id: int,
    service_tenant_id: Optional[int],
    target_customer: Customer,
    note: Optional[str] = None,
) -> tuple[ServiceCustomerLink, bool]:
    existing = (
        db.query(ServiceCustomerLink)
        .filter(
            ServiceCustomerLink.service_customer_id == service_customer_id,
            ServiceCustomerLink.customer_id == target_customer.id,
        )
        .first()
    )
    if existing:
        existing.status = "active"
        existing.service_tenant_id = service_tenant_id
        existing.customer_tenant_id = target_customer.tenant_id
        if note is not None:
            existing.note = note
        existing.updated_at = datetime.utcnow()
        db.flush()
        return existing, False

    link = ServiceCustomerLink(
        service_tenant_id=service_tenant_id,
        service_customer_id=service_customer_id,
        customer_tenant_id=target_customer.tenant_id,
        customer_id=target_customer.id,
        status="active",
        note=note,
    )
    db.add(link)
    db.flush()
    return link, True


def _serialize_access_request_row(request_row: ServiceAccessRequest, service: Customer, vehicle: Vehicle) -> dict[str, Any]:
    return {
        "id": int(request_row.id),
        "vehicle_id": int(request_row.vehicle_id),
        "service_id": int(request_row.service_customer_id),
        "service_name": service.name or service.email,
        "service_email": service.email,
        "vehicle_name": vehicle_label(vehicle),
        "vehicle_plate": vehicle.plate,
        "requested_at": request_row.requested_at.isoformat() if request_row.requested_at else None,
        "status": str(request_row.status or "pending"),
        "note": request_row.request_message,
        "scope_summary": _access_scope_summary(),
    }


def _safe_float(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_client_coordinates(request: Request) -> Optional[tuple[float, float]]:
    lat = _safe_float(request.headers.get("x-geo-lat"))
    lon = _safe_float(request.headers.get("x-geo-lon"))
    if lat is None or lon is None:
        return None
    if lat < -90 or lat > 90 or lon < -180 or lon > 180:
        return None
    return round(lat, 6), round(lon, 6)


def _cache_get(key: str) -> Optional[Dict[str, Any]]:
    cached = _SERVICE_GEO_CACHE.get(key)
    if not cached:
        return None
    if cached.get("expires_at", 0) < time.time():
        _SERVICE_GEO_CACHE.pop(key, None)
        return None
    return cached.get("payload")


def _cache_set(key: str, payload: Dict[str, Any]) -> None:
    if len(_SERVICE_GEO_CACHE) >= _SERVICE_GEO_CACHE_MAX_ITEMS:
        oldest_key = next(iter(_SERVICE_GEO_CACHE.keys()), None)
        if oldest_key is not None:
            _SERVICE_GEO_CACHE.pop(oldest_key, None)
    _SERVICE_GEO_CACHE[key] = {
        "expires_at": time.time() + _SERVICE_GEO_CACHE_TTL_SEC,
        "payload": payload,
    }


def _build_service_address(service: Customer) -> str:
    parts = []
    street = (service.street or "").strip()
    street_number = (service.street_number or "").strip()
    if street and street_number:
        parts.append(f"{street} {street_number}")
    elif street:
        parts.append(street)
    city = (service.city or "").strip()
    if city:
        parts.append(city)
    zip_code = (service.zip or "").strip()
    if zip_code:
        parts.append(zip_code)
    parts.append("Česká republika")
    return ", ".join(part for part in parts if part)


def _compose_service_address(service: Customer) -> str:
    street = (service.street or "").strip()
    street_number = (service.street_number or "").strip()
    line_one = f"{street} {street_number}".strip() if (street or street_number) else ""
    line_two = " ".join(part for part in [(service.zip or "").strip(), (service.city or "").strip()] if part).strip()
    return ", ".join(part for part in [line_one, line_two] if part)


def _geocode_address(address: str) -> Optional[Dict[str, Any]]:
    key = address.strip().lower()
    if not key:
        return None

    cached = _cache_get(key)
    if cached is not None:
        return cached

    try:
        request_url = _SERVICE_GEOLOOKUP_URL.format(query=quote(address, safe=""))
        req = UrlRequest(
            request_url,
            headers={
                "Accept": "application/json",
                "User-Agent": f"{APP_SERVER_PRODUCT_TOKEN}-ServicesDirectory/1.0",
            },
        )
        with urlopen(req, timeout=_SERVICE_GEOLOOKUP_TIMEOUT_SEC) as response:
            body = response.read().decode("utf-8", errors="ignore")
        data = json.loads(body)
        if not isinstance(data, list) or not data:
            _cache_set(key, {})
            return None

        first = data[0] if isinstance(data[0], dict) else {}
        lat = _safe_float(first.get("lat"))
        lon = _safe_float(first.get("lon"))
        if lat is None or lon is None:
            _cache_set(key, {})
            return None
        if lat < -90 or lat > 90 or lon < -180 or lon > 180:
            _cache_set(key, {})
            return None

        payload = {
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "display_name": first.get("display_name"),
        }
        _cache_set(key, payload)
        return payload
    except Exception:
        return None


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lam = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lam / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(max(1 - a, 0)))
    return round(r * c, 1)


@router.get("")
def get_services(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Vrátí seznam dostupných servisů.

    - admin: všechny servisy
    - user/service: pouze servisy ve stejném tenantovi
    """
    _ensure_services_schema(db)
    query = db.query(Customer).filter(Customer.role.in_(["service", "developer_admin"]))

    if current_user.role not in ["admin", "developer_admin"]:
        tenant_id = getattr(current_user, "tenant_id", None)
        if not tenant_id:
            raise HTTPException(status_code=403, detail="Uživatel nemá přiřazený tenant")
        query = query.filter(Customer.tenant_id == tenant_id)

    services = query.order_by(Customer.name.asc(), Customer.email.asc()).all()
    
    return [
        {
            "id": s.id,
            "email": s.email,
            "name": s.name,
            "role": s.role,
            "city": s.city,
            "phone": s.phone,
            "tenant_id": getattr(s, "tenant_id", None),
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "vehicles_count": 0
        }
        for s in services
    ]


@router.get("/my-contacts")
def get_my_service_contacts(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Kontakty na servisy, které mají aktivní propojení s aktuálním zákaznickým účtem.
    """
    _ensure_services_schema(db)
    role_key = str(getattr(current_user, "role", "") or "").strip().lower()
    if role_key == "service":
        return {"services": [], "meta": {"total": 0}}

    rows = (
        db.query(ServiceCustomerLink, Customer)
        .join(Customer, ServiceCustomerLink.service_customer_id == Customer.id)
        .filter(
            ServiceCustomerLink.customer_id == current_user.id,
            ServiceCustomerLink.status == "active",
            Customer.role.in_(["service", "developer_admin"]),
        )
        .order_by(Customer.name.asc(), Customer.email.asc())
        .all()
    )

    services = []
    seen_ids = set()
    for _, service in rows:
        if not service or service.id in seen_ids:
            continue
        seen_ids.add(service.id)
        services.append(
            {
                "id": service.id,
                "name": service.name or service.email,
                "email": service.email,
                "phone": service.phone,
                "ico": service.ico,
                "city": service.city,
                "address": _compose_service_address(service),
            }
        )

    return {
        "services": services,
        "meta": {
            "total": len(services),
        },
    }


@router.get("/access-requests", response_model=ServiceAccessRequestListOutV1)
def get_service_access_requests(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Vrátí čekající žádosti servisů o přístup k vozidlům aktuálního uživatele.
    """
    _ensure_services_schema(db)
    role_key = str(getattr(current_user, "role", "") or "").strip().lower()
    if role_key in {"service"}:
        raise HTTPException(status_code=403, detail="Endpoint je dostupný pouze v uživatelském režimu.")

    owned_vehicle_ids = sorted(get_owned_vehicle_ids(db, current_user, tenant_id=getattr(current_user, "tenant_id", None)))
    if not owned_vehicle_ids:
        return {"requests": []}

    rows = (
        db.query(ServiceAccessRequest, Customer, Vehicle)
        .join(Customer, ServiceAccessRequest.service_customer_id == Customer.id)
        .join(Vehicle, ServiceAccessRequest.vehicle_id == Vehicle.id)
        .filter(
            ServiceAccessRequest.owner_customer_id == current_user.id,
            ServiceAccessRequest.vehicle_id.in_(owned_vehicle_ids),
            ServiceAccessRequest.status == "pending",
        )
        .order_by(ServiceAccessRequest.requested_at.desc(), ServiceAccessRequest.id.desc())
        .all()
    )
    return {"requests": [_serialize_access_request_row(request_row, service, vehicle) for request_row, service, vehicle in rows]}


@router.put("/access-requests/{request_id}")
def resolve_service_access_request(
    request_id: int,
    payload: ServiceAccessRequestDecisionV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Uživatel schválí nebo zamítne pending žádost servisu o přístup k vozidlu.
    """
    _ensure_services_schema(db)
    role_key = str(getattr(current_user, "role", "") or "").strip().lower()
    if role_key in {"service"}:
        raise HTTPException(status_code=403, detail="Servisní účet nemůže rozhodovat o zákaznických žádostech.")

    request_row = (
        db.query(ServiceAccessRequest)
        .filter(
            ServiceAccessRequest.id == request_id,
            ServiceAccessRequest.owner_customer_id == current_user.id,
        )
        .first()
    )
    if not request_row:
        raise HTTPException(status_code=404, detail="Žádost o přístup nebyla nalezena.")
    if str(request_row.status or "") != "pending":
        raise HTTPException(status_code=409, detail="Žádost už byla vyřízena.")

    vehicle = get_owned_vehicle(db, current_user, int(request_row.vehicle_id), tenant_id=getattr(current_user, "tenant_id", None))
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo už není dostupné pro rozhodnutí o přístupu.")

    service = (
        db.query(Customer)
        .filter(
            Customer.id == request_row.service_customer_id,
            Customer.role.in_(["service", "developer_admin"]),
        )
        .first()
    )
    if not service:
        raise HTTPException(status_code=404, detail="Servis spojený se žádostí nebyl nalezen.")

    decision = str(payload.decision or "").strip().lower()
    if decision not in {"approved", "rejected"}:
        raise HTTPException(status_code=422, detail="Rozhodnutí musí být approved nebo rejected.")

    try:
        request_row.decided_at = datetime.utcnow()
        request_row.decided_by_customer_id = current_user.id
        request_row.decision_note = (payload.note or "").strip() or None

        if decision == "approved":
            link = create_or_update_vehicle_service_link(
                db,
                tenant_id=vehicle.tenant_id or current_user.tenant_id or service.tenant_id,
                service_customer_id=service.id,
                owner_customer_id=current_user.id,
                vehicle_id=vehicle.id,
                approved_by_customer_id=current_user.id,
                source_type="request_approved",
                source_request_id=request_row.id,
                note=(request_row.request_message or "").strip() or None,
            )
            request_row.status = "approved"
            request_row.approved_link_id = link.id
            _upsert_service_customer_link(
                db,
                service_customer_id=service.id,
                service_tenant_id=service.tenant_id,
                target_customer=current_user,
                note="Propojeno přes schválenou žádost o přístup k vozidlu",
            )
        else:
            request_row.status = "rejected"

        request_row.updated_at = datetime.utcnow()
        db.commit()
        return {
            "resolved": True,
            "request_id": int(request_row.id),
            "decision": decision,
            "vehicle_id": int(request_row.vehicle_id),
            "service_id": int(request_row.service_customer_id),
        }
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Nepodařilo se uložit rozhodnutí o žádosti: {exc}") from exc


@router.get("/vehicle-access", response_model=VehicleServiceLinkListOutV1)
def get_vehicle_access_grants(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Vrátí explicitní povolení vozidel pro konkrétní servisy.
    """
    _ensure_services_schema(db)
    role_key = str(getattr(current_user, "role", "") or "").strip().lower()
    if role_key in {"service"}:
        raise HTTPException(status_code=403, detail="Endpoint je dostupný pouze v uživatelském režimu.")

    owned_vehicle_ids = sorted(get_owned_vehicle_ids(db, current_user, tenant_id=getattr(current_user, "tenant_id", None)))
    if not owned_vehicle_ids:
        return {"grants": [], "meta": {"total": 0}}

    rows = (
        db.query(VehicleServiceLink, Customer, Vehicle)
        .join(Customer, VehicleServiceLink.service_customer_id == Customer.id)
        .join(Vehicle, VehicleServiceLink.vehicle_id == Vehicle.id)
        .filter(
            VehicleServiceLink.owner_customer_id == current_user.id,
            VehicleServiceLink.vehicle_id.in_(owned_vehicle_ids),
            VehicleServiceLink.status == "approved",
            Customer.role.in_(["service", "developer_admin"]),
        )
        .order_by(VehicleServiceLink.updated_at.desc())
        .all()
    )

    grants = []
    for access_row, service, vehicle in rows:
        grants.append(
            {
                "service_id": int(access_row.service_customer_id),
                "vehicle_id": int(access_row.vehicle_id),
                "customer_id": int(access_row.owner_customer_id),
                "service_name": service.name or service.email,
                "service_email": service.email,
                "vehicle_name": vehicle_label(vehicle),
                "vehicle_plate": vehicle.plate,
                "status": access_row.status,
                "updated_at": access_row.updated_at.isoformat() if access_row.updated_at else None,
            }
        )

    return {
        "grants": grants,
        "meta": {
            "total": len(grants),
        },
    }


@router.post("/vehicle-access")
def grant_vehicle_access_to_service(
    payload: VehicleAccessGrantRequest,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Uživatel explicitně povolí servisu správu konkrétního vozidla.
    """
    _ensure_services_schema(db)
    role_key = str(getattr(current_user, "role", "") or "").strip().lower()
    if role_key in {"service"}:
        raise HTTPException(status_code=403, detail="Servisní účet nemůže měnit oprávnění zákaznického vozidla.")

    vehicle = get_owned_vehicle(db, current_user, int(payload.vehicle_id), tenant_id=getattr(current_user, "tenant_id", None))
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nebylo nalezeno nebo vám nepatří.")

    service = (
        db.query(Customer)
        .filter(
            Customer.id == payload.service_id,
            Customer.role.in_(["service", "developer_admin"]),
        )
        .first()
    )
    if not service:
        raise HTTPException(status_code=404, detail="Servis nebyl nalezen.")

    conflict_rows = (
        db.query(ServiceVehicleAccess, Customer)
        .join(Customer, ServiceVehicleAccess.service_customer_id == Customer.id)
        .filter(
            ServiceVehicleAccess.customer_id == current_user.id,
            ServiceVehicleAccess.vehicle_id == vehicle.id,
            ServiceVehicleAccess.status == "active",
            ServiceVehicleAccess.service_customer_id != service.id,
            Customer.role.in_(["service", "developer_admin"]),
        )
        .order_by(ServiceVehicleAccess.updated_at.desc())
        .all()
    )
    conflict_services = [
        {
            "service_id": int(conflict_access.service_customer_id),
            "service_name": conflict_service.name or conflict_service.email,
            "service_email": conflict_service.email,
            "updated_at": conflict_access.updated_at.isoformat() if conflict_access.updated_at else None,
        }
        for conflict_access, conflict_service in conflict_rows
    ]
    conflict_strategy = str(payload.conflict_strategy or "keep").strip().lower()
    if conflict_strategy not in {"ask", "keep", "replace"}:
        conflict_strategy = "keep"

    if conflict_services and conflict_strategy == "ask":
        conflict_names = ", ".join(
            str(item.get("service_name") or item.get("service_email") or f"#{item.get('service_id')}")
            for item in conflict_services[:6]
        )
        return {
            "granted": False,
            "requires_confirmation": True,
            "conflict": True,
            "service_id": int(service.id),
            "vehicle_id": int(vehicle.id),
            "conflict_services": conflict_services,
            "message": (
                "Vozidlo je už přiřazené k jinému servisu"
                + (f": {conflict_names}." if conflict_names else ".")
                + " Zvolte, zda původní přiřazení zachovat, nebo nahradit."
            ),
        }

    try:
        revoked_conflict_service_ids: list[int] = []
        if conflict_services and conflict_strategy == "replace":
            now = datetime.utcnow()
            for conflict_access, _conflict_service in conflict_rows:
                conflict_access.status = "revoked"
                conflict_access.revoked_at = now
                conflict_access.updated_at = now
                revoked_conflict_service_ids.append(int(conflict_access.service_customer_id))

        _upsert_service_customer_link(
            db,
            service_customer_id=service.id,
            service_tenant_id=service.tenant_id,
            target_customer=current_user,
            note="Propojeno přes explicitní povolení vozidla",
        )
        create_or_update_vehicle_service_link(
            db,
            tenant_id=vehicle.tenant_id or current_user.tenant_id or service.tenant_id,
            service_customer_id=service.id,
            owner_customer_id=current_user.id,
            vehicle_id=vehicle.id,
            approved_by_customer_id=current_user.id,
            source_type="direct_user_grant",
            note=(payload.note or "").strip() or None,
        )

        db.commit()
        return {
            "granted": True,
            "service_id": int(service.id),
            "vehicle_id": int(vehicle.id),
            "conflict": bool(conflict_services),
            "conflict_strategy": conflict_strategy,
            "conflict_services": conflict_services,
            "revoked_conflict_service_ids": sorted(set(revoked_conflict_service_ids)),
            "message": (
                "Servisu byl povolen přístup k vybranému vozidlu."
                if not revoked_conflict_service_ids
                else "Servisu byl povolen přístup a původní servisní přiřazení bylo odebráno."
            ),
        }
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Nepodařilo se uložit oprávnění: {exc}") from exc


@router.delete("/vehicle-access/{service_id}/{vehicle_id}")
def revoke_vehicle_access_for_service(
    service_id: int,
    vehicle_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Uživatel odebere servisu explicitní oprávnění ke konkrétnímu vozidlu.
    """
    _ensure_services_schema(db)
    role_key = str(getattr(current_user, "role", "") or "").strip().lower()
    if role_key in {"service"}:
        raise HTTPException(status_code=403, detail="Servisní účet nemůže měnit oprávnění zákaznického vozidla.")

    vehicle = get_owned_vehicle(db, current_user, int(vehicle_id), tenant_id=getattr(current_user, "tenant_id", None))
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vozidlo nebylo nalezeno nebo vám nepatří.")

    link_row = (
        db.query(VehicleServiceLink)
        .filter(
            VehicleServiceLink.service_customer_id == service_id,
            VehicleServiceLink.owner_customer_id == current_user.id,
            VehicleServiceLink.vehicle_id == vehicle_id,
            VehicleServiceLink.status == "approved",
        )
        .first()
    )
    if not link_row:
        return {
            "revoked": False,
            "service_id": int(service_id),
            "vehicle_id": int(vehicle_id),
            "message": "Pro danou kombinaci servis/vozidlo nebylo aktivní oprávnění.",
        }

    try:
        revoke_vehicle_service_link(
            db,
            service_customer_id=service_id,
            vehicle_id=vehicle_id,
            revoked_by_customer_id=current_user.id,
            reason="user_revoke",
        )
        db.commit()
        return {
            "revoked": True,
            "service_id": int(service_id),
            "vehicle_id": int(vehicle_id),
            "message": "Přístup servisu k vozidlu byl odebrán.",
        }
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Nepodařilo se odebrat oprávnění: {exc}") from exc


@router.delete("/my-contacts/{service_id}")
def disconnect_my_service_contact(
    service_id: int,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Uživatel odpojí servisní kontakt:
    - zneaktivní vazbu ServiceCustomerLink
    - odebere všechna aktivní oprávnění ServiceVehicleAccess vůči tomuto servisu
    """
    _ensure_services_schema(db)
    role_key = str(getattr(current_user, "role", "") or "").strip().lower()
    if role_key in {"service"}:
        raise HTTPException(status_code=403, detail="Servisní účet nemůže odpojovat zákaznické servisní kontakty.")

    service = (
        db.query(Customer)
        .filter(
            Customer.id == service_id,
            Customer.role.in_(["service", "developer_admin"]),
        )
        .first()
    )
    if not service:
        raise HTTPException(status_code=404, detail="Servis nebyl nalezen.")

    link_row = (
        db.query(ServiceCustomerLink)
        .filter(
            ServiceCustomerLink.service_customer_id == service_id,
            ServiceCustomerLink.customer_id == current_user.id,
            ServiceCustomerLink.status == "active",
        )
        .first()
    )
    access_rows = (
        db.query(ServiceVehicleAccess)
        .filter(
            ServiceVehicleAccess.service_customer_id == service_id,
            ServiceVehicleAccess.customer_id == current_user.id,
            ServiceVehicleAccess.status == "active",
        )
        .all()
    )

    if not link_row and not access_rows:
        return {
            "disconnected": False,
            "service_id": int(service_id),
            "service_name": service.name or service.email,
            "revoked_vehicles_count": 0,
            "message": "Servis už není aktivně propojen s vaším účtem.",
        }

    try:
        now = datetime.utcnow()
        revoked_vehicle_ids: list[int] = []
        if link_row:
            link_row.status = "archived"
            link_row.updated_at = now
        for access in access_rows:
            access.status = "revoked"
            access.revoked_at = now
            access.updated_at = now
            if access.vehicle_id is not None:
                revoked_vehicle_ids.append(int(access.vehicle_id))
        db.commit()
        return {
            "disconnected": True,
            "service_id": int(service_id),
            "service_name": service.name or service.email,
            "revoked_vehicles_count": len(revoked_vehicle_ids),
            "revoked_vehicle_ids": sorted(set(revoked_vehicle_ids)),
            "message": "Servis byl odpojen a jeho přístup k vašim vozidlům byl odebrán.",
        }
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Nepodařilo se servis odpojit: {exc}") from exc


@router.get("/discovery")
def get_services_discovery(
    request: Request,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Katalog aktivních servisů pro uživatele.

    - Vrací servisní účty (role=service/developer_admin).
    - Pokud má uživatel aktivní propojení se servisem, je tento servis zahrnut i mimo standardní filtr.
    - Pokud je dostupná poloha uživatele (X-Geo-Lat/Lon), seřadí podle vzdálenosti.
    - Fallback: pokud uživatel nemá GPS hlavičky, zkusí se geokódovat jeho profilová adresa.
    """
    _ensure_services_schema(db)

    linked_service_ids: set[int] = set()
    role_key = str(getattr(current_user, "role", "") or "").strip().lower()
    if role_key not in {"service"}:
        linked_rows = (
            db.query(ServiceCustomerLink.service_customer_id)
            .filter(
                ServiceCustomerLink.customer_id == current_user.id,
                ServiceCustomerLink.status == "active",
            )
            .all()
        )
        linked_service_ids = {int(service_id) for (service_id,) in linked_rows if service_id is not None}

    query = db.query(Customer).filter(Customer.role.in_(["service", "developer_admin"]))

    if not _is_admin_role(current_user.role):
        tenant_id = getattr(current_user, "tenant_id", None)
        if not tenant_id:
            raise HTTPException(status_code=403, detail="Uživatel nemá přiřazený tenant")
        if linked_service_ids:
            query = query.filter(or_(Customer.tenant_id == tenant_id, Customer.id.in_(list(linked_service_ids))))
        else:
            query = query.filter(Customer.tenant_id == tenant_id)

    if linked_service_ids:
        query = query.filter(or_(Customer.password_hash.isnot(None), Customer.id.in_(list(linked_service_ids))))
    else:
        query = query.filter(Customer.password_hash.isnot(None))

    services = query.order_by(Customer.name.asc(), Customer.email.asc()).all()

    active_access_counts: dict[int, int] = {}
    if role_key not in {"service"} and services:
        rows = (
            db.query(
                ServiceVehicleAccess.service_customer_id,
                func.count(ServiceVehicleAccess.id),
            )
            .filter(
                ServiceVehicleAccess.customer_id == current_user.id,
                ServiceVehicleAccess.status == "active",
            )
            .group_by(ServiceVehicleAccess.service_customer_id)
            .all()
        )
        active_access_counts = {
            int(service_id): int(count or 0)
            for service_id, count in rows
            if service_id is not None
        }

    reference_coords = _extract_client_coordinates(request)
    reference_source = "browser"

    if reference_coords is None:
        profile_address = _build_service_address(current_user)
        if profile_address:
            geocoded_user = _geocode_address(profile_address)
            if geocoded_user and geocoded_user.get("lat") is not None and geocoded_user.get("lon") is not None:
                reference_coords = (float(geocoded_user["lat"]), float(geocoded_user["lon"]))
                reference_source = "profile_address"

    ref_lat = reference_coords[0] if reference_coords else None
    ref_lon = reference_coords[1] if reference_coords else None

    rows = []
    used_new_lookups = 0
    for service in services:
        address = _build_service_address(service)
        cache_key = address.strip().lower()
        cached = _cache_get(cache_key) if cache_key else None

        geocoded = cached
        if geocoded is None and address:
            if used_new_lookups < _SERVICE_GEOLOOKUP_MAX_NEW_LOOKUPS_PER_REQUEST:
                geocoded = _geocode_address(address)
                used_new_lookups += 1
            else:
                geocoded = None

        lat = _safe_float((geocoded or {}).get("lat"))
        lon = _safe_float((geocoded or {}).get("lon"))
        distance_km = None
        if ref_lat is not None and ref_lon is not None and lat is not None and lon is not None:
            distance_km = _haversine_km(ref_lat, ref_lon, lat, lon)

        rows.append(
            {
                "id": service.id,
                "name": service.name or "Neznámý servis",
                "email": service.email,
                "phone": service.phone,
                "city": service.city,
                "street": service.street,
                "street_number": service.street_number,
                "zip": service.zip,
                "ico": service.ico,
                "distance_km": distance_km,
                "has_precise_distance": distance_km is not None,
                "coordinates": {"lat": lat, "lon": lon} if lat is not None and lon is not None else None,
                "is_linked": service.id in linked_service_ids,
                "shared_vehicles_count": int(active_access_counts.get(int(service.id), 0)),
                "created_at": service.created_at.isoformat() if service.created_at else None,
            }
        )

    rows.sort(key=lambda item: (item["distance_km"] is None, item["distance_km"] or 10**9, (item.get("name") or "").lower()))

    return {
        "meta": {
            "total": len(rows),
            "linked_total": sum(1 for item in rows if bool(item.get("is_linked"))),
            "reference_source": reference_source if reference_coords else "none",
            "reference_coordinates": {"lat": ref_lat, "lon": ref_lon} if reference_coords else None,
            "distance_sorted": bool(reference_coords),
        },
        "services": rows,
    }


# -----------------------------------------------------------------------------
# Propojení servis–vozidlo: kanonické cesty (stejná logika jako /services/workspace/*)
# -----------------------------------------------------------------------------


@router.post("/vehicle-lookup", response_model=ServiceVehicleLookupResponseV1)
def vehicle_lookup_for_service_product_path(
    payload: ServiceVehicleLookupRequestV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """SPZ/VIN lookup bez historie + audit; viz ``service_workspace.lookup_vehicle_for_service``."""
    from . import service_workspace as _service_workspace

    return _service_workspace.lookup_vehicle_for_service(payload, current_user, db)


@router.post("/access-requests")
def create_service_access_request_product_path(
    payload: ServiceAccessRequestCreateV1,
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Servis odešle žádost o přístup; viz ``service_workspace.create_service_access_request``."""
    from . import service_workspace as _service_workspace

    return _service_workspace.create_service_access_request(payload, current_user, db)


@router.get("/approved-vehicles", response_model=ServiceApprovedVehicleListOutV1)
def list_approved_service_vehicles_product_path(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Schválená vozidla servisu; viz ``service_workspace.list_approved_service_vehicles``."""
    from . import service_workspace as _service_workspace

    return _service_workspace.list_approved_service_vehicles(current_user, db)
