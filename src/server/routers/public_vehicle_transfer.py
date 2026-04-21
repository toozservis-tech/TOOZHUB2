from __future__ import annotations

import hashlib
import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.modules.vehicle_hub.audit_log import write_global_audit_log
from src.modules.vehicle_hub.database import get_db
from src.modules.vehicle_hub.models import Vehicle, VehicleTransferToken
from src.modules.vehicle_hub.routers_v1.vehicle_lifecycle import ClaimByTransferRequest, claim_vehicle_by_transfer
from src.modules.vehicle_hub.routers_v1.auth import get_current_user

router = APIRouter(prefix="/api/public/vehicle-transfer", tags=["public-vehicle-transfer"])


def _token_hash(token: str) -> str:
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def _masked_vin(vin: str | None) -> str | None:
    text = str(vin or "").strip().upper()
    if not text:
        return None
    return f"{text[:3]}***{text[-4:]}"


@router.get("/{token}")
def get_vehicle_transfer_token(token: str, request: Request, db: Session = Depends(get_db)):
    token_row = db.query(VehicleTransferToken).filter(VehicleTransferToken.token_hash == _token_hash(token)).first()
    if not token_row:
        raise HTTPException(status_code=404, detail="Předávací token nebyl nalezen.")
    if token_row.status == "active" and token_row.expires_at < datetime.utcnow():
        token_row.status = "expired"
        db.flush()
    vehicle = db.query(Vehicle).filter(Vehicle.id == int(token_row.vehicle_id)).first()
    write_global_audit_log(
        db,
        entity_type="vehicle_transfer_token",
        entity_id=int(token_row.id),
        action="transfer_token_opened",
        actor_type="public",
        tenant_id=getattr(vehicle, "tenant_id", None) if vehicle else None,
        vehicle_id=int(token_row.vehicle_id),
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={"status": token_row.status},
    )
    db.commit()
    return {
        "status": token_row.status,
        "expires_at": token_row.expires_at.isoformat() if token_row.expires_at else None,
        "vehicle": {
            "vehicle_id": int(vehicle.id),
            "brand": vehicle.brand,
            "model": vehicle.model,
            "year": vehicle.year,
            "spz_current": vehicle.plate,
            "vin_masked": _masked_vin(vehicle.vin),
        } if vehicle else None,
        "requires_confirmation": ["vin", "spz"],
    }


@router.post("/{token}/claim")
def claim_public_vehicle_transfer(
    token: str,
    payload: ClaimByTransferRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.token != token:
        raise HTTPException(status_code=409, detail="Token v URL a těle požadavku se neshoduje.")
    return claim_vehicle_by_transfer(payload=payload, current_user=current_user, db=db)
