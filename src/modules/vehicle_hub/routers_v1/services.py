"""
Services API v1.0 router
Endpointy pro správu servisů
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from typing import List

from ..database import get_db
from ..models import Customer
from .auth import get_current_user, require_role

router = APIRouter(prefix="/services", tags=["services-v1"])


@router.get("")
def get_services(
    current_user: Customer = Depends(require_role("admin")),
    db: Session = Depends(get_db)
):
    """Vrátí seznam všech servisů (customers s role='service')"""
    services = db.query(Customer).filter(Customer.role == "service").all()
    
    return [
        {
            "id": s.id,
            "email": s.email,
            "name": s.name,
            "role": s.role,
            "city": s.city,
            "phone": s.phone,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "vehicles_count": 0
        }
        for s in services
    ]

