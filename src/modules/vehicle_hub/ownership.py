"""
Ownership helpers for explicit vehicle <-> owner binding.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from .models import Customer, Vehicle, VehicleOwnership


def _normalize_email(email: Optional[str]) -> str:
    return str(email or "").strip().lower()


def get_customer_by_email(db: Session, email: Optional[str]) -> Optional[Customer]:
    normalized = _normalize_email(email)
    if not normalized:
        return None
    return db.query(Customer).filter(func.lower(Customer.email) == normalized).first()


def get_primary_vehicle_owner_assignment(db: Session, vehicle_id: int) -> Optional[VehicleOwnership]:
    return (
        db.query(VehicleOwnership)
        .filter(
            VehicleOwnership.vehicle_id == vehicle_id,
            VehicleOwnership.is_active.is_(True),
            VehicleOwnership.is_primary.is_(True),
        )
        .order_by(VehicleOwnership.id.asc())
        .first()
    )


def get_primary_vehicle_owner(db: Session, vehicle: Vehicle) -> Optional[Customer]:
    assignment = get_primary_vehicle_owner_assignment(db, int(vehicle.id))
    if assignment:
        return db.query(Customer).filter(Customer.id == assignment.customer_id).first()
    return get_customer_by_email(db, getattr(vehicle, "user_email", None))


def user_owns_vehicle(db: Session, customer: Customer, vehicle: Vehicle) -> bool:
    assignment = (
        db.query(VehicleOwnership.id)
        .filter(
            VehicleOwnership.vehicle_id == vehicle.id,
            VehicleOwnership.customer_id == customer.id,
            VehicleOwnership.is_active.is_(True),
        )
        .first()
    )
    if assignment is not None:
        return True
    return _normalize_email(getattr(vehicle, "user_email", None)) == _normalize_email(customer.email)


def ensure_vehicle_owner_assignment(
    db: Session,
    *,
    vehicle: Vehicle,
    owner: Customer,
    assigned_by_customer_id: Optional[int] = None,
) -> VehicleOwnership:
    existing = (
        db.query(VehicleOwnership)
        .filter(
            VehicleOwnership.vehicle_id == vehicle.id,
            VehicleOwnership.customer_id == owner.id,
            VehicleOwnership.ownership_type == "owner",
        )
        .first()
    )
    if existing:
        existing.is_active = True
        existing.is_primary = True
        existing.revoked_at = None
        existing.tenant_id = owner.tenant_id
        existing.updated_at = datetime.utcnow()
        db.flush()
        return existing

    ownership = VehicleOwnership(
        tenant_id=owner.tenant_id,
        vehicle_id=vehicle.id,
        customer_id=owner.id,
        ownership_type="owner",
        is_primary=True,
        is_active=True,
        assigned_by_customer_id=assigned_by_customer_id,
        assigned_at=datetime.utcnow(),
    )
    db.add(ownership)
    db.flush()
    return ownership


def backfill_vehicle_owner_assignment(db: Session, vehicle: Vehicle) -> Optional[VehicleOwnership]:
    owner = get_customer_by_email(db, getattr(vehicle, "user_email", None))
    if not owner:
        return None
    return ensure_vehicle_owner_assignment(db, vehicle=vehicle, owner=owner, assigned_by_customer_id=owner.id)
