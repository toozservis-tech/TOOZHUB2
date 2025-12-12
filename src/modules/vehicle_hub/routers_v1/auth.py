"""
Helper funkce pro autorizaci v1.0
"""
from fastapi import HTTPException, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from typing import Optional

from ..database import get_db
from ..models import Customer
from src.core.auth import get_current_user_email


def get_current_user(
    user_email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db)
) -> Customer:
    """
    Získá aktuálního uživatele z databáze podle emailu.
    
    Raises:
        HTTPException: Pokud uživatel neexistuje
    """
    user = db.query(Customer).filter(Customer.email == user_email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")
    return user


def get_current_user_optional(
    db: Session = Depends(get_db),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False))
) -> Optional[Customer]:
    """
    Získá aktuálního uživatele z databáze podle emailu, pokud je přihlášen.
    Vrátí None, pokud uživatel není přihlášen nebo neexistuje.
    
    Returns:
        Customer nebo None
    """
    if not credentials:
        return None
    
    try:
        from src.core.security import decode_access_token
        token = credentials.credentials
        user_email = decode_access_token(token)
        
        if not user_email:
            return None
        
        user = db.query(Customer).filter(Customer.email == user_email).first()
        return user
    except Exception:
        return None


def require_role(required_role: str):
    """
    Dependency pro kontrolu role uživatele.
    
    Args:
        required_role: Požadovaná role ("user", "service", "admin")
    
    Returns:
        Depends funkce, která kontroluje roli
    """
    def role_checker(
        current_user: Customer = Depends(get_current_user)
    ) -> Customer:
        if current_user.role != required_role and current_user.role != "admin":
            raise HTTPException(
                status_code=403,
                detail=f"Přístup zamítnut. Požadována role: {required_role}"
            )
        return current_user
    
    return role_checker


def get_current_user_id(
    user_email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db)
) -> int:
    """
    Získá ID aktuálního uživatele.
    
    Returns:
        User ID
    """
    user = db.query(Customer).filter(Customer.email == user_email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")
    return user.id


def can_access_vehicle(
    vehicle_id: int,
    current_user: Customer,
    db: Session
) -> bool:
    """
    Kontroluje, zda má uživatel přístup k vozidlu.
    
    Rules:
    - role "user": pouze vlastní vozidla
    - role "service": vlastní vozidla + vozidla zákazníků s intake/rezervací
    - role "admin": všechna vozidla
    
    Returns:
        True pokud má přístup
    """
    from ..models import Vehicle, ServiceIntake, Reservation
    
    # Admin má přístup ke všemu
    if current_user.role == "admin":
        return True
    
    # Najít vozidlo
    vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
    if not vehicle:
        return False
    
    # Vlastník vozidla má vždy přístup
    if vehicle.user_email == current_user.email:
        return True
    
    # Service role - může přistupovat k vozidlům zákazníků s intake/rezervací
    if current_user.role == "service":
        # Kontrola přes ServiceIntake
        intake_exists = db.query(ServiceIntake).filter(
            ServiceIntake.vehicle_id == vehicle_id,
            ServiceIntake.service_id == current_user.id
        ).first()
        if intake_exists:
            return True
        
        # Kontrola přes Reservation
        reservation_exists = db.query(Reservation).filter(
            Reservation.vehicle_id == vehicle_id,
            Reservation.service_id == current_user.id
        ).first()
        if reservation_exists:
            return True
    
    return False
