"""
Autentizační modul pro TooZ Hub 2
- JWT token validace
- Získání aktuálního uživatele
"""
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional

from .security import decode_access_token

# HTTPBearer pro získání tokenu z Authorization headeru
security = HTTPBearer()


def get_current_user_email(
    credentials: HTTPAuthorizationCredentials = Depends(security)
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
    email = decode_access_token(token)
    
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Neplatný nebo expirovaný token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return email
