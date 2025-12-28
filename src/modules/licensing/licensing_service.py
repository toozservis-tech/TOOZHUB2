"""
Licensing service - centralizovaná logika pro správu licencí
Source of truth je TOOZ_SERVICE_HUB, tento modul pouze enforce limity
"""
from datetime import datetime, timezone
from typing import Optional, Dict

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..vehicle_hub.models import Customer, Vehicle
from .types import LicensePlan, LicenseStatus, EffectiveEntitlement

# Maximální počet vozidel podle plánu
MAX_VEHICLES_BY_PLAN: Dict[str, Optional[int]] = {
    "FREE": 1,
    "BASIC": 5,
    "PREMIUM": None,  # None = neomezeně
}


def vehicles_count(db: Session, customer_email: str) -> int:
    """
    Spočítá počet vozidel pro daného uživatele.
    
    Args:
        db: Databázová session
        customer_email: Email uživatele
        
    Returns:
        Počet vozidel
    """
    return db.query(Vehicle).filter(Vehicle.user_email == customer_email).count()


def get_entitlement(customer: Customer) -> Dict:
    """
    Získá entitlement z cache polí v Customer modelu.
    
    Args:
        customer: Uživatel
        
    Returns:
        dict s klíči: plan, status, period_end
    """
    plan_str = getattr(customer, 'license_plan_cached', 'FREE')
    status_str = getattr(customer, 'license_status_cached', 'ACTIVE')
    period_end = getattr(customer, 'license_period_end_cached', None)
    
    return {
        "plan": plan_str,
        "status": status_str,
        "period_end": period_end,
    }


def effective_max_vehicles(entitlement: Dict) -> Optional[int]:
    """
    Vrátí efektivní maximální počet vozidel podle plánu.
    
    Args:
        entitlement: dict s plánem a statusem
        
    Returns:
        Maximální počet vozidel (None = neomezeně)
    """
    plan = entitlement.get("plan", "FREE")
    return MAX_VEHICLES_BY_PLAN.get(plan, 1)


def is_active(entitlement: Dict) -> bool:
    """
    Zkontroluje, zda je licence aktivní.
    Zatím pouze ACTIVE (bez grace period).
    
    Args:
        entitlement: dict s plánem a statusem
        
    Returns:
        True pokud je licence aktivní
    """
    status = entitlement.get("status", "EXPIRED")
    return status == "ACTIVE"


def is_over_limit(db: Session, customer_email: str, entitlement: Dict) -> bool:
    """
    Zkontroluje, zda je uživatel nad limitem vozidel.
    
    Args:
        db: Databázová session
        customer_email: Email uživatele
        entitlement: dict s plánem a statusem
        
    Returns:
        True pokud je nad limitem
    """
    max_vehicles = effective_max_vehicles(entitlement)
    if max_vehicles is None:
        return False  # Neomezeně
    
    count = vehicles_count(db, customer_email)
    return count >= max_vehicles


def enforce_vehicle_limit(db: Session, customer: Customer) -> None:
    """
    Vynutí limit vozidel - pokud je limit dosažen, vyhodí HTTPException 403.
    
    Args:
        db: Databázová session
        customer: Uživatel
        
    Raises:
        HTTPException 403: Pokud je limit dosažen nebo licence není aktivní
    """
    # Načíst entitlement z cache polí
    entitlement = get_entitlement(customer)
    
    # Pokud status není ACTIVE, chovej se jako FREE (max=1)
    if not is_active(entitlement):
        status = entitlement.get("status", "EXPIRED")
        # Pro neaktivní licence použij FREE limit (1 vozidlo)
        max_vehicles = 1
        count = vehicles_count(db, customer.email)
        
        if count >= max_vehicles:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Licence není aktivní (status: {status}). "
                    f"Pro přidání vozidel aktivujte licenci."
                )
            )
        return
    
    # Spočítat počet vozidel
    count = vehicles_count(db, customer.email)
    
    # Získat limit podle plánu
    max_vehicles = effective_max_vehicles(entitlement)
    
    # Pokud je limit None (PREMIUM), povolit neomezeně
    if max_vehicles is None:
        return
    
    # Kontrola limitu
    if count >= max_vehicles:
        plan = entitlement.get("plan", "FREE")
        raise HTTPException(
            status_code=403,
            detail=(
                f"Vehicle limit reached for your plan. "
                f"Plan: {plan}, Limit: {max_vehicles}, Current: {count}. "
                f"Upgrade to add more vehicles."
            )
        )


def get_effective_entitlement(db: Session, customer: Customer) -> EffectiveEntitlement:
    """
    Získá efektivní oprávnění uživatele z cache polí.
    
    Args:
        db: Databázová session
        customer: Uživatel
        
    Returns:
        EffectiveEntitlement s kompletními informacemi o licenci
    """
    # Načíst entitlement z cache polí
    entitlement_dict = get_entitlement(customer)
    
    # Převedení na enumy
    try:
        plan = LicensePlan(entitlement_dict["plan"])
    except ValueError:
        plan = LicensePlan.FREE
    
    try:
        status = LicenseStatus(entitlement_dict["status"])
    except ValueError:
        status = LicenseStatus.EXPIRED
    
    period_end = entitlement_dict.get("period_end")
    
    # Spočítat počet vozidel
    vehicles_count_val = vehicles_count(db, customer.email)
    
    # Získat limit
    max_vehicles = effective_max_vehicles(entitlement_dict)
    
    # Zkontrolovat, zda je nad limitem
    is_over = False
    if max_vehicles is not None:
        is_over = vehicles_count_val >= max_vehicles
    
    return EffectiveEntitlement(
        plan=plan,
        status=status,
        period_end=period_end,
        vehicles_count=vehicles_count_val,
        vehicles_limit=max_vehicles,
        is_over_limit=is_over,
    )


def require_plan_active(customer: Customer) -> None:
    """
    Dependency funkce pro kontrolu, zda je plán aktivní.
    
    Args:
        customer: Uživatel
        
    Raises:
        HTTPException 403: Pokud status není ACTIVE
    """
    entitlement = get_entitlement(customer)
    if not is_active(entitlement):
        status = entitlement.get("status", "EXPIRED")
        raise HTTPException(
            status_code=403,
            detail=f"License is not active (status: {status}). Please activate your license."
        )
