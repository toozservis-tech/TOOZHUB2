"""Admin API pro servisní mapu."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.modules.vehicle_hub.audit_log import write_global_audit_log
from src.modules.vehicle_hub.database import get_db
from src.modules.vehicle_hub.models import ServiceLocation, ServiceLocationClaim, ServiceLocationSource
from src.modules.vehicle_hub.schema_management import assert_module_ready
from src.modules.vehicle_hub.service_map.claim_service import (
    approve_service_location_claim,
    reject_service_location_claim,
)
from src.modules.vehicle_hub.service_map.constants import VERIFICATION_DUPLICATE
from src.modules.vehicle_hub.service_map.mdcr_stk_sme_importer import import_mdcr_stk_sme
from src.modules.vehicle_hub.service_map.osm_importer import import_osm_overpass_json
from src.modules.vehicle_hub.service_map.search_service import ADMIN_SEARCH_MAX_LIMIT, search_service_locations, serialize_location
from src.server.admin_api import require_developer_admin

router = APIRouter(prefix="/service-map", tags=["admin-service-map"])


class OsmImportBody(BaseModel):
    payload: dict[str, Any]
    import_batch_id: Optional[str] = Field(default=None, max_length=64)


class MdcrImportBody(BaseModel):
    payload: Any = None
    csv_text: Optional[str] = None
    import_batch_id: Optional[str] = Field(default=None, max_length=64)


class AdminLocationPatch(BaseModel):
    category: Optional[str] = Field(default=None, max_length=32)
    verification_status: Optional[str] = Field(default=None, max_length=32)
    is_active: Optional[bool] = None
    name: Optional[str] = Field(default=None, max_length=255)


@router.post("/import/osm")
def admin_import_osm(
    body: OsmImportBody,
    admin=Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    assert_module_ready(db, "service_map", detail_prefix="Servisní mapa není připravená")
    write_global_audit_log(
        db,
        entity_type="service_map_import",
        entity_id=None,
        action="import_started",
        actor_user_id=int(getattr(admin, "id", 0) or 0) or None,
        metadata={"kind": "osm", "import_batch_id": body.import_batch_id},
    )
    db.commit()
    result = import_osm_overpass_json(db, body.payload, import_batch_id=body.import_batch_id)
    write_global_audit_log(
        db,
        entity_type="service_map_import",
        entity_id=None,
        action="import_finished",
        actor_user_id=int(getattr(admin, "id", 0) or 0) or None,
        metadata=result,
    )
    db.commit()
    return result


@router.post("/import/mdcr-stk-sme")
def admin_import_mdcr(
    body: MdcrImportBody,
    admin=Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    assert_module_ready(db, "service_map", detail_prefix="Servisní mapa není připravená")
    if body.csv_text:
        result = import_mdcr_stk_sme(db, body.csv_text, import_batch_id=body.import_batch_id, file_format="csv")
    elif body.payload is not None:
        result = import_mdcr_stk_sme(db, body.payload, import_batch_id=body.import_batch_id, file_format="json")
    else:
        raise HTTPException(status_code=400, detail="Chybí payload nebo csv_text.")
    write_global_audit_log(
        db,
        entity_type="service_map_import",
        entity_id=None,
        action="mdcr_import",
        actor_user_id=int(getattr(admin, "id", 0) or 0) or None,
        metadata=result,
    )
    db.commit()
    return result


@router.get("/locations")
def admin_list_locations(
    q: Optional[str] = Query(default=None, max_length=128),
    category: Optional[str] = Query(default=None, max_length=32),
    verification_status: Optional[str] = Query(default=None, max_length=32),
    is_active: Optional[bool] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    admin=Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    assert_module_ready(db, "service_map", detail_prefix="Servisní mapa není připravená")
    query = db.query(ServiceLocation)
    if q:
        needle = f"%{q.strip()}%"
        query = query.filter(
            (ServiceLocation.name.ilike(needle))
            | (ServiceLocation.city.ilike(needle))
            | (ServiceLocation.source_external_id.ilike(needle))
        )
    if category:
        query = query.filter(ServiceLocation.category == category)
    if verification_status:
        query = query.filter(ServiceLocation.verification_status == verification_status)
    if is_active is not None:
        query = query.filter(ServiceLocation.is_active.is_(bool(is_active)))
    total = query.count()
    rows = query.order_by(ServiceLocation.id.desc()).offset(offset).limit(limit).all()
    return {"items": [serialize_location(row) for row in rows], "total": total}


@router.patch("/locations/{location_id}")
def admin_patch_location(
    location_id: int,
    body: AdminLocationPatch,
    admin=Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    assert_module_ready(db, "service_map", detail_prefix="Servisní mapa není připravená")
    row = db.query(ServiceLocation).filter(ServiceLocation.id == location_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Servisní místo nenalezeno.")

    before = serialize_location(row)
    if body.category is not None:
        row.category = body.category
    if body.verification_status is not None:
        row.verification_status = body.verification_status
    if body.is_active is not None:
        row.is_active = bool(body.is_active)
    if body.name is not None:
        row.name = body.name.strip()
    row.updated_at = datetime.utcnow()

    write_global_audit_log(
        db,
        entity_type="service_location",
        entity_id=int(row.id),
        action="admin_patch",
        actor_user_id=int(getattr(admin, "id", 0) or 0) or None,
        before_json=before,
        after_json=serialize_location(row),
    )
    db.commit()
    return serialize_location(row)


@router.post("/claims/{claim_id}/approve")
def admin_approve_claim(
    claim_id: int,
    admin=Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    assert_module_ready(db, "service_map", detail_prefix="Servisní mapa není připravená")
    claim = approve_service_location_claim(db, claim_id=claim_id, admin_user_id=int(admin.id))
    return {"id": int(claim.id), "claim_status": claim.claim_status}


@router.post("/claims/{claim_id}/reject")
def admin_reject_claim(
    claim_id: int,
    admin=Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    assert_module_ready(db, "service_map", detail_prefix="Servisní mapa není připravená")
    claim = reject_service_location_claim(db, claim_id=claim_id, admin_user_id=int(admin.id))
    return {"id": int(claim.id), "claim_status": claim.claim_status}


@router.get("/overview")
def admin_service_map_overview(
    admin=Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    assert_module_ready(db, "service_map", detail_prefix="Servisní mapa není připravená")
    total = db.query(ServiceLocation).count()
    active = db.query(ServiceLocation).filter(ServiceLocation.is_active.is_(True)).count()
    pending_claims = db.query(ServiceLocationClaim).filter(ServiceLocationClaim.claim_status == "pending").count()
    duplicates = db.query(ServiceLocation).filter(ServiceLocation.verification_status == VERIFICATION_DUPLICATE).count()
    return {
        "locations_total": total,
        "locations_active": active,
        "claims_pending": pending_claims,
        "duplicates_flagged": duplicates,
    }


@router.get("/claims")
def admin_list_claims(
    claim_status: Optional[str] = Query(default="pending", max_length=32),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    admin=Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    assert_module_ready(db, "service_map", detail_prefix="Servisní mapa není připravená")
    query = db.query(ServiceLocationClaim)
    if claim_status:
        query = query.filter(ServiceLocationClaim.claim_status == claim_status)
    total = query.count()
    rows = query.order_by(ServiceLocationClaim.id.desc()).offset(offset).limit(limit).all()
    items = []
    for claim in rows:
        location = db.query(ServiceLocation).filter(ServiceLocation.id == claim.service_location_id).first()
        items.append(
            {
                "id": int(claim.id),
                "claim_status": claim.claim_status,
                "service_location_id": int(claim.service_location_id),
                "service_tenant_id": int(claim.service_tenant_id),
                "business_name": claim.business_name,
                "ico": claim.ico,
                "submitted_at": claim.submitted_at.isoformat() if claim.submitted_at else None,
                "location": serialize_location(location) if location else None,
            }
        )
    return {"items": items, "total": total}


@router.get("/duplicates")
def admin_list_duplicates(
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    admin=Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    assert_module_ready(db, "service_map", detail_prefix="Servisní mapa není připravená")
    query = db.query(ServiceLocation).filter(ServiceLocation.verification_status == VERIFICATION_DUPLICATE)
    total = query.count()
    rows = query.order_by(ServiceLocation.id.desc()).offset(offset).limit(limit).all()
    return {"items": [serialize_location(row) for row in rows], "total": total}


@router.get("/import-batches")
def admin_list_import_batches(
    limit: int = Query(default=20, ge=1, le=100),
    admin=Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    assert_module_ready(db, "service_map", detail_prefix="Servisní mapa není připravená")
    rows = (
        db.query(ServiceLocationSource.import_batch_id, ServiceLocationSource.source_type)
        .filter(ServiceLocationSource.import_batch_id.isnot(None))
        .distinct()
        .order_by(ServiceLocationSource.import_batch_id.desc())
        .limit(limit)
        .all()
    )
    batches = []
    for batch_id, source_type in rows:
        count = (
            db.query(ServiceLocationSource)
            .filter(ServiceLocationSource.import_batch_id == batch_id)
            .count()
        )
        batches.append({"import_batch_id": batch_id, "source_type": source_type, "source_rows": count})
    return {"items": batches}


@router.get("/search")
def admin_service_map_search(
    lat: Optional[float] = Query(default=None, ge=-90, le=90),
    lng: Optional[float] = Query(default=None, ge=-180, le=180),
    radius_km: float = Query(default=50.0, ge=1, le=200),
    north: Optional[float] = Query(default=None, ge=-90, le=90),
    south: Optional[float] = Query(default=None, ge=-90, le=90),
    east: Optional[float] = Query(default=None, ge=-180, le=180),
    west: Optional[float] = Query(default=None, ge=-180, le=180),
    category: Optional[str] = Query(default=None, max_length=32),
    q: Optional[str] = Query(default=None, max_length=128),
    verified_only: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=ADMIN_SEARCH_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
    admin=Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    assert_module_ready(db, "service_map", detail_prefix="Servisní mapa není připravená")
    items, total, meta = search_service_locations(
        db,
        lat=lat,
        lng=lng,
        radius_km=radius_km,
        north=north,
        south=south,
        east=east,
        west=west,
        category=category,
        q=q,
        verified_only=verified_only,
        limit=limit,
        offset=offset,
        admin_mode=True,
    )
    return {"items": items, "total": total, **meta}
