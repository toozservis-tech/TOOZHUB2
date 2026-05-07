"""
License Service - produkční licencování pro Správu vozidel
"""
import logging
from typing import Dict, List, Optional
from datetime import datetime
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException

from src.core.env_aliases import env_prefer_new

from ..vehicle_hub.models import License, LicenseSubscription, Vehicle, Tenant
from ..vehicle_hub.database import Base
from ..vehicle_hub.ownership import get_customer_by_email, get_owned_vehicle_ids

logger = logging.getLogger(__name__)

# Admin bypass – prefer SPRAVA_VOZIDEL_*, fallback TOOZHUB_* (deprecated)
_admin_tenant_raw = env_prefer_new("SPRAVA_VOZIDEL_ADMIN_TENANT_ID", "TOOZHUB_ADMIN_TENANT_ID")
ADMIN_TENANT_ID = _admin_tenant_raw
if ADMIN_TENANT_ID:
    try:
        ADMIN_TENANT_ID = int(ADMIN_TENANT_ID)
    except ValueError:
        ADMIN_TENANT_ID = None
        logger.warning(
            "[LICENSE] Invalid admin tenant id (SPRAVA_VOZIDEL_ADMIN_TENANT_ID / TOOZHUB_ADMIN_TENANT_ID): %s",
            _admin_tenant_raw,
        )

# Volitelný "legacy" režim: admin tenant je vždy premium a obchází limity.
# Výchozí je vypnuto, aby se plán dal reálně měnit (nutné např. pro platby).
_admin_force_raw = env_prefer_new("SPRAVA_VOZIDEL_ADMIN_FORCE_PREMIUM", "TOOZHUB_ADMIN_FORCE_PREMIUM") or "0"
ADMIN_FORCE_PREMIUM = _admin_force_raw.strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)


def is_admin_tenant(tenant_id: int) -> bool:
    return ADMIN_TENANT_ID is not None and tenant_id == ADMIN_TENANT_ID


class LicenseError(HTTPException):
    """Vlastní výjimka pro licence chyby"""
    def __init__(self, code: str, message: str, details: dict = None, status_code: int = 403):
        self.code = code
        self.details = details or {}
        super().__init__(status_code=status_code, detail=message)


USER_LICENSE_PLANS = ("free", "basic", "premium", "lifetime")
SERVICE_LICENSE_PLANS = ("service_free", "service_basic", "service_premium", "service_lifetime")
ALL_LICENSE_PLANS = USER_LICENSE_PLANS + SERVICE_LICENSE_PLANS

USER_PLAN_METADATA: Dict[str, Dict[str, object]] = {
    "free": {"label": "Free", "workspace_kind": "user"},
    "basic": {"label": "Basic", "workspace_kind": "user"},
    "premium": {"label": "Premium", "workspace_kind": "user"},
    "lifetime": {"label": "Lifetime", "workspace_kind": "user"},
}

SERVICE_PLAN_METADATA: Dict[str, Dict[str, object]] = {
    "service_free": {"label": "Service Free", "workspace_kind": "service"},
    "service_basic": {"label": "Service Basic", "workspace_kind": "service"},
    "service_premium": {"label": "Service Premium", "workspace_kind": "service"},
    "service_lifetime": {"label": "Service Lifetime", "workspace_kind": "service"},
}

LICENSE_PLAN_METADATA: Dict[str, Dict[str, object]] = {
    **USER_PLAN_METADATA,
    **SERVICE_PLAN_METADATA,
}


def get_license_workspace_kind_for_role(role: Optional[str]) -> str:
    normalized_role = str(role or "").strip().lower()
    return "service" if normalized_role == "service" else "user"


def get_allowed_license_plans_for_role(role: Optional[str]) -> List[str]:
    workspace_kind = get_license_workspace_kind_for_role(role)
    if workspace_kind == "service":
        return list(SERVICE_LICENSE_PLANS)
    return list(USER_LICENSE_PLANS)


def get_license_plan_workspace_kind(plan: Optional[str]) -> str:
    normalized_plan = str(plan or "").strip().lower()
    if normalized_plan.startswith("service_"):
        return "service"
    return "user"


def get_license_plan_base(plan: Optional[str]) -> str:
    normalized_plan = str(plan or "").strip().lower()
    if normalized_plan.startswith("service_"):
        normalized_plan = normalized_plan[len("service_"):]
    if normalized_plan in {"free", "basic", "premium", "lifetime"}:
        return normalized_plan
    return "free"


def normalize_license_plan_key(plan: Optional[str], role: Optional[str] = None) -> Optional[str]:
    if plan is None:
        return None
    normalized_plan = str(plan or "").strip().lower()
    if not normalized_plan:
        return None

    workspace_kind = get_license_workspace_kind_for_role(role)
    base_plan = get_license_plan_base(normalized_plan)
    if workspace_kind == "service":
        if normalized_plan in SERVICE_LICENSE_PLANS:
            return normalized_plan
        return f"service_{base_plan}"

    if normalized_plan in USER_LICENSE_PLANS:
        return normalized_plan
    return base_plan


def get_license_plan_public_label(plan: Optional[str]) -> str:
    normalized_plan = str(plan or "").strip().lower()
    metadata = LICENSE_PLAN_METADATA.get(normalized_plan)
    if metadata and metadata.get("label"):
        return str(metadata["label"])
    return get_license_plan_base(plan).title()


# Mapování plánů na limity
PLAN_LIMITS = {
    "free": 1,
    "basic": 3,
    "premium": 0,  # 0 = unlimited
    "lifetime": 0,  # neomezeně, administrátorské přidělení
    "service_free": 10,
    "service_basic": 75,
    "service_premium": 0,
    "service_lifetime": 0,
}

FREE_SERVICE_RECORDS_LIMIT = 1
FREE_ACTIVE_MANUAL_REMINDERS_LIMIT = 1

# Mapování plánů na dostupné funkce (ARES necháváme povolený pro všechny)
PLAN_FEATURES = {
    "free": {
        "vin_decode_enabled": False,
        "ares_enabled": True,
        # Připomínky jsou základní hodnota produktu, dostupná i ve FREE plánu.
        "reminders_enabled": True,
        "reservations_enabled": False,
        "vehicle_history_enabled": False,
        "documents_enabled": False,
        "costs_tracking_enabled": False,
        "statistics_enabled": False,
        "sharing_with_service_enabled": False,
    },
    "basic": {
        "vin_decode_enabled": False,
        "ares_enabled": True,
        "reminders_enabled": True,
        "reservations_enabled": True,
        "vehicle_history_enabled": True,
        "documents_enabled": True,
        "costs_tracking_enabled": False,
        "statistics_enabled": False,
        "sharing_with_service_enabled": False,
    },
    "premium": {
        "vin_decode_enabled": True,
        "ares_enabled": True,
        "reminders_enabled": True,
        "reservations_enabled": True,
        "vehicle_history_enabled": True,
        "documents_enabled": True,
        "costs_tracking_enabled": True,
        "statistics_enabled": True,
        "sharing_with_service_enabled": True,
    },
    # Dofull Premium + doživotní platnost, pouze admin (bez Comgate)
    "lifetime": {
        "vin_decode_enabled": True,
        "ares_enabled": True,
        "reminders_enabled": True,
        "reservations_enabled": True,
        "vehicle_history_enabled": True,
        "documents_enabled": True,
        "costs_tracking_enabled": True,
        "statistics_enabled": True,
        "sharing_with_service_enabled": True,
    },
    "service_free": {
        "vin_decode_enabled": False,
        "ares_enabled": True,
        "reminders_enabled": True,
        "reservations_enabled": True,
        "vehicle_history_enabled": True,
        "documents_enabled": True,
        "costs_tracking_enabled": False,
        "statistics_enabled": False,
        "sharing_with_service_enabled": False,
    },
    "service_basic": {
        "vin_decode_enabled": True,
        "ares_enabled": True,
        "reminders_enabled": True,
        "reservations_enabled": True,
        "vehicle_history_enabled": True,
        "documents_enabled": True,
        "costs_tracking_enabled": True,
        "statistics_enabled": False,
        "sharing_with_service_enabled": False,
    },
    "service_premium": {
        "vin_decode_enabled": True,
        "ares_enabled": True,
        "reminders_enabled": True,
        "reservations_enabled": True,
        "vehicle_history_enabled": True,
        "documents_enabled": True,
        "costs_tracking_enabled": True,
        "statistics_enabled": True,
        "sharing_with_service_enabled": True,
    },
    "service_lifetime": {
        "vin_decode_enabled": True,
        "ares_enabled": True,
        "reminders_enabled": True,
        "reservations_enabled": True,
        "vehicle_history_enabled": True,
        "documents_enabled": True,
        "costs_tracking_enabled": True,
        "statistics_enabled": True,
        "sharing_with_service_enabled": True,
    },
}


def get_or_create_license(db: Session, tenant_id: int) -> License:
    """
    Získá nebo vytvoří licenci pro tenant_id.
    Pokud licence neexistuje, vytvoří default free licenci.
    
    Args:
        db: Databázová session
        tenant_id: ID tenanta
        
    Returns:
        License objekt
    """
    admin_force_premium = ADMIN_FORCE_PREMIUM and is_admin_tenant(tenant_id)
    
    # Normální tenant - zkusit najít existující licenci
    license_obj = db.query(License).filter(License.tenant_id == tenant_id).first()
    
    # Pokud licence existuje, ujistit se, že má správné funkce podle plánu
    if license_obj:
        needs_update = False

        if admin_force_premium and license_obj.plan != "premium":
            license_obj.plan = "premium"
            needs_update = True
        if admin_force_premium and license_obj.status != "active":
            license_obj.status = "active"
            needs_update = True
        if admin_force_premium:
            if license_obj.valid_to is not None:
                license_obj.valid_to = None
                needs_update = True
            if not license_obj.valid_from:
                license_obj.valid_from = datetime.utcnow()
                needs_update = True

        current_plan_key = normalize_license_plan_key(license_obj.plan, get_license_plan_workspace_kind(license_obj.plan)) or "free"
        if current_plan_key != license_obj.plan:
            license_obj.plan = current_plan_key
            needs_update = True

        features = PLAN_FEATURES.get(license_obj.plan, PLAN_FEATURES["free"])

        # Synchronizovat feature flagy, které máme uložené v DB
        db_feature_keys = ["vin_decode_enabled", "ares_enabled", "reminders_enabled"]
        for key in db_feature_keys:
            expected = features.get(key, getattr(license_obj, key, False))
            if getattr(license_obj, key, False) != expected:
                setattr(license_obj, key, expected)
                needs_update = True

        # Aktualizovat limit podle plánu, pokud se liší
        expected_limit = 0 if admin_force_premium else PLAN_LIMITS.get(license_obj.plan, 1)
        if license_obj.vehicles_limit != expected_limit:
            license_obj.vehicles_limit = expected_limit
            needs_update = True

        if needs_update:
            license_obj.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(license_obj)
            logger.info(f"[LICENSE] Updated license features for tenant_id={tenant_id}, plan={license_obj.plan}")
    
    if not license_obj:
        # Vytvořit default free licenci
        plan = "premium" if admin_force_premium else "free"
        vehicles_limit = PLAN_LIMITS.get(plan, 1)
        features = PLAN_FEATURES.get(plan, PLAN_FEATURES["free"])
        now = datetime.utcnow()
        license_obj = License(
            tenant_id=tenant_id,
            plan=plan,
            status="active",
            vehicles_limit=vehicles_limit,
            valid_from=now,
            valid_to=None,
            vin_decode_enabled=features["vin_decode_enabled"],
            ares_enabled=features.get("ares_enabled", True),
            reminders_enabled=features["reminders_enabled"]
        )
        db.add(license_obj)
        try:
            db.commit()
            db.refresh(license_obj)
            logger.info(f"[LICENSE] Created default free license for tenant_id={tenant_id}")
        except IntegrityError:
            db.rollback()
            # Možná byla mezitím vytvořena jiným procesem
            license_obj = db.query(License).filter(License.tenant_id == tenant_id).first()
            if not license_obj:
                raise
    
    return license_obj


def get_vehicle_count(db: Session, tenant_id: int) -> int:
    """
    Spočítá počet vozidel pro tenant_id.
    
    Args:
        db: Databázová session
        tenant_id: ID tenanta
        
    Returns:
        Počet vozidel
    """
    return db.query(Vehicle).filter(Vehicle.tenant_id == tenant_id, Vehicle.status != "archived").count()


def get_vehicle_count_for_user(db: Session, tenant_id: int, user_email: Optional[str]) -> int:
    """
    Spočítá počet vozidel konkrétního uživatele v rámci tenantu.

    Pokud user_email není dostupný, vrací tenant-wide počet.
    """
    normalized_email = str(user_email or "").strip().lower()
    if not normalized_email:
        return get_vehicle_count(db, tenant_id)

    customer = get_customer_by_email(db, normalized_email)
    if customer is None:
        # Deprecated compat fallback for users/customers that ještě nemají
        # explicitní ownership/customer vazbu. Nesmí být hlavní autoritou.
        return db.query(Vehicle).filter(
            Vehicle.tenant_id == tenant_id,
            func.lower(Vehicle.user_email) == normalized_email,
            Vehicle.status != "archived",
        ).count()

    return len(get_owned_vehicle_ids(db, customer, tenant_id=tenant_id))


def is_unlimited(license_obj: License) -> bool:
    """
    Zkontroluje, zda je licence unlimited (vehicles_limit == 0).
    
    Args:
        license_obj: License objekt
        
    Returns:
        True pokud je unlimited
    """
    return license_obj.vehicles_limit == 0


def assert_vehicle_quota(db: Session, tenant_id: int) -> None:
    """
    Zkontroluje, zda tenant může přidat další vozidlo.
    Pokud ne, vyhodí LicenseError.
    
    Args:
        db: Databázová session
        tenant_id: ID tenanta
        
    Raises:
        LicenseError: Pokud je quota překročena
    """
    license_obj = get_or_create_license(db, tenant_id)
    
    # Legacy admin bypass - aktivní jen při explicitním zapnutí.
    if ADMIN_FORCE_PREMIUM and is_admin_tenant(tenant_id):
        return
    
    # Zkontrolovat status
    if license_obj.status != "active":
        raise LicenseError(
            code="LICENSE_INACTIVE",
            message=f"Licence není aktivní (status: {license_obj.status})",
            details={"status": license_obj.status, "tenant_id": tenant_id}
        )
    
    # Zkontrolovat valid_to (admin bypass valid_to)
    if license_obj.valid_to and not (ADMIN_FORCE_PREMIUM and is_admin_tenant(tenant_id)):
        if datetime.utcnow() > license_obj.valid_to:
            raise LicenseError(
                code="LICENSE_EXPIRED",
                message=f"Licence vypršela (valid_to: {license_obj.valid_to})",
                details={"valid_to": license_obj.valid_to.isoformat(), "tenant_id": tenant_id}
            )
    
    # Zkontrolovat quota
    if is_unlimited(license_obj):
        return  # Unlimited - OK
    
    current = get_vehicle_count(db, tenant_id)
    if current >= license_obj.vehicles_limit:
        raise LicenseError(
            code="LICENSE_QUOTA_EXCEEDED",
            message=f"Limit vozidel překročen ({current}/{license_obj.vehicles_limit})",
            details={
                "plan": license_obj.plan,
                "limit": license_obj.vehicles_limit,
                "current": current
            },
            status_code=403
        )


def assert_feature(db: Session, tenant_id: int, feature_name: str) -> None:
    """
    Zkontroluje, zda je feature povoleno pro tenant_id.
    Pokud ne, vyhodí LicenseError.
    
    Args:
        db: Databázová session
        tenant_id: ID tenanta
        feature_name: Název feature ("vin_decode", "ares", "reminders", "documents", "reservations")
        
    Raises:
        LicenseError: Pokud je feature zakázáno
    """
    license_obj = get_or_create_license(db, tenant_id)
    
    # Legacy admin bypass - aktivní jen při explicitním zapnutí.
    if ADMIN_FORCE_PREMIUM and is_admin_tenant(tenant_id):
        return

    if feature_name == "documents":
        features = PLAN_FEATURES.get(license_obj.plan, PLAN_FEATURES["free"])
        if not bool(features.get("documents_enabled", False)):
            raise LicenseError(
                code="FEATURE_DISABLED",
                message=(
                    "Export dokumentů a PDF není ve vašem tarifu povolen. "
                    "Upgradujte na BASIC nebo PREMIUM."
                ),
                details={
                    "feature_name": "documents",
                    "plan": license_obj.plan,
                    "tenant_id": tenant_id,
                },
                status_code=403,
            )
        return

    if feature_name == "reservations":
        features = PLAN_FEATURES.get(license_obj.plan, PLAN_FEATURES["free"])
        if not bool(features.get("reservations_enabled", False)):
            raise LicenseError(
                code="FEATURE_DISABLED",
                message=(
                    "Objednání servisu není ve vašem tarifu povoleno. "
                    "Upgradujte na BASIC nebo PREMIUM."
                ),
                details={
                    "feature_name": "reservations",
                    "plan": license_obj.plan,
                    "tenant_id": tenant_id,
                },
                status_code=403,
            )
        return
    
    # Mapování feature name na sloupec
    feature_map = {
        "vin_decode": "vin_decode_enabled",
        "ares": "ares_enabled",
        "reminders": "reminders_enabled",
        "reservations": "reservations_enabled",
    }
    
    if feature_name not in feature_map:
        raise LicenseError(
            code="INVALID_FEATURE",
            message=f"Neplatný feature: {feature_name}",
            details={"feature_name": feature_name}
        )
    
    column_name = feature_map[feature_name]
    is_enabled = getattr(license_obj, column_name, False)
    
    if not is_enabled:
        raise LicenseError(
            code="FEATURE_DISABLED",
            message=f"Feature '{feature_name}' není povoleno pro váš plán ({license_obj.plan})",
            details={
                "feature_name": feature_name,
                "plan": license_obj.plan,
                "tenant_id": tenant_id
            },
            status_code=403
        )


def get_license_status(db: Session, tenant_id: int, user_email: Optional[str] = None) -> dict:
    """
    Získá status licence pro tenant_id.
    
    Args:
        db: Databázová session
        tenant_id: ID tenanta
        
    Returns:
        dict s informacemi o licenci včetně feature flags
    """
    license_obj = get_or_create_license(db, tenant_id)
    tenant_vehicle_count = get_vehicle_count(db, tenant_id)
    user_vehicle_count = get_vehicle_count_for_user(db, tenant_id, user_email)
    is_unl = is_unlimited(license_obj)
    
    vehicles_remaining = None if is_unl else max(0, license_obj.vehicles_limit - tenant_vehicle_count)
    
    features = PLAN_FEATURES.get(license_obj.plan, PLAN_FEATURES["free"])
    normalized_plan = normalize_license_plan_key(license_obj.plan, get_license_plan_workspace_kind(license_obj.plan)) or "free"

    over_limit = (not is_unl) and tenant_vehicle_count > int(license_obj.vehicles_limit or 0)
    status = {
        "tenant_id": str(tenant_id),
        "plan": normalized_plan,
        "plan_base": get_license_plan_base(normalized_plan),
        "plan_workspace_kind": get_license_plan_workspace_kind(normalized_plan),
        "plan_public_label": get_license_plan_public_label(normalized_plan),
        "status": license_obj.status,
        "vehicles_limit": license_obj.vehicles_limit,
        # Tenant-wide počet (používá se pro licenční limity)
        "vehicles_current": tenant_vehicle_count,
        # Uživatelský počet (pro UI kontext "moje vozidla")
        "vehicles_current_user": user_vehicle_count,
        "vehicles_remaining": vehicles_remaining,
        "is_unlimited": is_unl,
        # Aliasy pro klientské UI (dashboard)
        "vehicles_count": tenant_vehicle_count,
        "license_limit": None if is_unl else int(license_obj.vehicles_limit or 0),
        "is_over_limit": bool(over_limit),
        "vin_decode_enabled": license_obj.vin_decode_enabled,
        "ares_enabled": license_obj.ares_enabled,
        "reminders_enabled": license_obj.reminders_enabled,
    }

    # Doplnit ostatní feature flagy podle plánu (nejsou uložené v DB)
    status.update({
        "reservations_enabled": bool(features.get("reservations_enabled", False)),
        "vehicle_history_enabled": bool(features.get("vehicle_history_enabled", False)),
        "documents_enabled": bool(features.get("documents_enabled", False)),
        "costs_tracking_enabled": bool(features.get("costs_tracking_enabled", False)),
        "statistics_enabled": bool(features.get("statistics_enabled", False)),
        "sharing_with_service_enabled": bool(features.get("sharing_with_service_enabled", False)),
        "is_lifetime": get_license_plan_base(normalized_plan) == "lifetime",
    })

    return status


def upgrade_license_plan(db: Session, tenant_id: int, plan: str) -> dict:
    """
    Nastaví licenci na požadovaný plán a vrátí aktuální stav.
    
    Args:
        db: databázová session
        tenant_id: cílový tenant
        plan: "free" | "basic" | "premium" | "lifetime"
    
    Returns:
        dict ve formátu get_license_status
    """
    plan_key = str(plan or "").strip().lower()
    if plan_key not in PLAN_FEATURES:
        raise HTTPException(
            status_code=400,
            detail=(
                "Neplatný plán. Povolené hodnoty: free, basic, premium, lifetime, "
                "service_free, service_basic, service_premium, service_lifetime."
            ),
        )
    
    license_obj = get_or_create_license(db, tenant_id)
    features = PLAN_FEATURES[plan_key]
    vehicles_limit = PLAN_LIMITS.get(plan_key, 1)
    
    license_obj.plan = plan_key
    license_obj.status = "active"
    license_obj.vehicles_limit = vehicles_limit
    license_obj.vin_decode_enabled = features["vin_decode_enabled"]
    license_obj.ares_enabled = features.get("ares_enabled", True)
    license_obj.reminders_enabled = features["reminders_enabled"]
    license_obj.updated_at = datetime.utcnow()

    if get_license_plan_base(plan_key) == "lifetime":
        license_obj.valid_to = None
        sub = (
            db.query(LicenseSubscription)
            .filter(LicenseSubscription.tenant_id == tenant_id)
            .first()
        )
        if sub is not None:
            sub.status = "legacy_manual"
            sub.auto_renew_enabled = False
            sub.next_charge_at = None
            sub.current_period_end = None
            sub.grace_until = None
            sub.pending_plan_change = None
            sub.plan_current = plan_key
            sub.billing_period = None
            sub.updated_at = datetime.utcnow()
            db.add(sub)
    
    db.add(license_obj)
    db.commit()
    db.refresh(license_obj)
    
    return get_license_status(db, tenant_id)
