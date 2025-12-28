"""
Licensing module - centralizovaná správa licencí a limitů
Source of truth je TOOZ_SERVICE_HUB, tento modul pouze enforce limity
"""

from .types import LicensePlan, LicenseStatus, EffectiveEntitlement
from .licensing_service import (
    get_effective_entitlement,
    enforce_vehicle_limit,
    vehicles_count,
    get_entitlement,
    effective_max_vehicles,
    is_active,
    is_over_limit,
    require_plan_active,
)
from .dependencies import require_plan_active_dependency, require_feature

__all__ = [
    "LicensePlan",
    "LicenseStatus",
    "EffectiveEntitlement",
    "get_effective_entitlement",
    "enforce_vehicle_limit",
    "vehicles_count",
    "get_entitlement",
    "effective_max_vehicles",
    "is_active",
    "is_over_limit",
    "require_plan_active",
    "require_plan_active_dependency",
    "require_feature",
]











