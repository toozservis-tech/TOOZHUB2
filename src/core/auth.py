"""
Autentizační modul pro Správu vozidel
- JWT token validace
- Získání aktuálního uživatele
"""
from fastapi import HTTPException, Depends, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from src.modules.vehicle_hub.email_verification import pending_verification
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional

from .security import decode_access_token_payload
from .session_revocation import require_active_token
from src.modules.vehicle_hub.database import get_db
from src.modules.vehicle_hub.models import Customer
from src.modules.vehicle_hub.account_state import (
    ensure_customer_account_state_schema,
    customer_is_deleted,
    customer_is_disabled,
    customer_session_version,
)

# HTTPBearer pro získání tokenu z Authorization headeru
security = HTTPBearer()


def get_current_user_email(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> str:
    """
    Získá email aktuálně přihlášeného uživatele z JWT tokenu.
    
    Args:
        credentials: HTTPAuthorizationCredentials z HTTPBearer
        
    Returns:
        Email uživatele
        
    Raises:
        HTTPException: Pokud je token neplatný nebo chybí
    """
    token = credentials.credentials
    payload = decode_access_token_payload(token)
    email = (payload or {}).get("sub")

    if email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Neplatný nebo expirovaný token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    require_active_token(db, token)
    ensure_customer_account_state_schema(db)

    normalized_email = str(email).strip().lower()
    customer = db.query(Customer).filter(func.lower(Customer.email) == normalized_email).first()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Neplatný nebo expirovaný token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if customer_is_deleted(customer) or customer_is_disabled(customer):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Účet je neaktivní",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_session_version = payload.get("sv")
    try:
        token_session_version_int = int(token_session_version if token_session_version is not None else 0)
    except (TypeError, ValueError):
        token_session_version_int = 0

    if token_session_version_int != customer_session_version(customer):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session byla ukončena, přihlaste se znovu",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if pending_verification(db, customer.id) and (request.method, request.url.path) not in {
        ("GET", "/user/me"), ("DELETE", "/user/me"), ("GET", "/user/me/export"),
        ("PUT", "/user/change-password"),
        ("GET", "/user/email-verification"), ("POST", "/user/email-verification/resend"),
    }:
        raise HTTPException(403, "Nejprve ověřte svou e-mailovou adresu odkazem v e-mailu.")
    from src.core.mfa import ADMIN_BOOTSTRAP_ROUTES, require_admin_assurance
    if (request.method, request.url.path) not in ADMIN_BOOTSTRAP_ROUTES:
        require_admin_assurance(db, customer, payload)
    return email
