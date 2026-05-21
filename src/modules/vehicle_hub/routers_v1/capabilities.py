"""
System capabilities for frontend/admin gating.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..schema_management import get_capabilities
from .auth import get_current_user
from ..models import Customer
from src.core.config import GOOGLE_MAPS_API_KEY
from src.modules.vehicle_hub.service_map.map_config import build_map_tile_config

router = APIRouter(prefix="/system", tags=["system-capabilities"])


@router.get("/maps-config")
def get_maps_config(
    current_user: Customer = Depends(get_current_user),
):
    """Mapový podklad pro servisní mapu (Leaflet/MapLibre) – klíče pouze z ENV."""
    _ = current_user
    tile_cfg = build_map_tile_config()
    return {
        **tile_cfg,
        "google_maps_js_api_key": GOOGLE_MAPS_API_KEY if GOOGLE_MAPS_API_KEY else None,
    }


@router.get("/capabilities")
def list_system_capabilities(
    current_user: Customer = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _ = current_user
    return get_capabilities(db)
