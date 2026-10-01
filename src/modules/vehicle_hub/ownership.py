"""
Ownership helpers for explicit vehicle <-> owner binding.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from .models import Customer, Vehicle, VehicleOwnership, VehicleServiceLink, ServiceVehicleAccess, ServiceAccessRequest


def lock_vehicle_access(db: Session, vehicle_id: int) -> None:
    """Common first lock for ownership, sharing decisions and service writes.

    Lock only the identity: callers may have deliberately edited vehicle fields.
    Ownership/grant queries must be refreshed after this transaction-level lock.
    """
    if db.query(Vehicle.id).filter(Vehicle.id == vehicle_id).with_for_update().first() is None:
        raise HTTPException(404, "Vozidlo nebylo nalezeno.")


def revoke_vehicle_sharing_for_owner_change(
    db: Session, *, vehicle_id: int, actor_id: int, reason: str,
) -> None:
    """Revoke both permission models and outstanding decisions, retain evidence."""
    lock_vehicle_access(db, vehicle_id)
    now = datetime.utcnow()
    db.query(VehicleServiceLink).filter(
        VehicleServiceLink.vehicle_id == vehicle_id, VehicleServiceLink.status == "approved",
    ).update({VehicleServiceLink.status: "revoked", VehicleServiceLink.revoked_at: now,
        VehicleServiceLink.revoked_by_customer_id: actor_id, VehicleServiceLink.revoked_reason: reason,
        VehicleServiceLink.updated_at: now}, synchronize_session="fetch")
    db.query(ServiceVehicleAccess).filter(
        ServiceVehicleAccess.vehicle_id == vehicle_id, ServiceVehicleAccess.status == "active",
    ).update({ServiceVehicleAccess.status: "revoked", ServiceVehicleAccess.revoked_at: now,
        ServiceVehicleAccess.updated_at: now}, synchronize_session="fetch")
    db.query(ServiceAccessRequest).filter(
        ServiceAccessRequest.vehicle_id == vehicle_id, ServiceAccessRequest.status.in_(["pending", "approved"]),
    ).update({ServiceAccessRequest.status: "revoked", ServiceAccessRequest.decided_at: now,
        ServiceAccessRequest.decided_by_customer_id: actor_id, ServiceAccessRequest.decision_note: reason,
        ServiceAccessRequest.updated_at: now}, synchronize_session="fetch")


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
        .populate_existing()
        .first()
    )


def get_primary_vehicle_owner(db: Session, vehicle: Vehicle) -> Optional[Customer]:
    assignment = get_primary_vehicle_owner_assignment(db, int(vehicle.id))
    if assignment:
        return db.query(Customer).filter(Customer.id == assignment.customer_id).first()
    backfilled = backfill_vehicle_owner_assignment(db, vehicle)
    if backfilled:
        return db.query(Customer).filter(Customer.id == backfilled.customer_id).first()
    return None


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
    backfilled = backfill_vehicle_owner_assignment(db, vehicle)
    if backfilled is None:
        return False
    return int(backfilled.customer_id) == int(customer.id)


def ensure_vehicle_owner_assignment(
    db: Session,
    *,
    vehicle: Vehicle,
    owner: Customer,
    assigned_by_customer_id: Optional[int] = None,
    ownership_origin: str = "manual",
) -> VehicleOwnership:
    lock_vehicle_access(db, int(vehicle.id))
    previous = get_primary_vehicle_owner_assignment(db, int(vehicle.id))
    has_previous_period = previous is None and db.query(VehicleOwnership.id).filter_by(vehicle_id=vehicle.id).first() is not None
    if (previous and previous.customer_id != owner.id) or has_previous_period:
        revoke_vehicle_sharing_for_owner_change(db, vehicle_id=int(vehicle.id),
            actor_id=assigned_by_customer_id or owner.id, reason="Změnil se vlastník vozidla. Nový vlastník musí přístup schválit znovu.")
    now = datetime.utcnow()
    (
        db.query(VehicleOwnership)
        .filter(
            VehicleOwnership.vehicle_id == vehicle.id,
            VehicleOwnership.customer_id != owner.id,
            VehicleOwnership.is_active.is_(True),
        )
        .update(
            {
                VehicleOwnership.is_active: False,
                VehicleOwnership.is_primary: False,
                VehicleOwnership.owned_until: now,
                VehicleOwnership.revoked_at: now,
                VehicleOwnership.updated_at: now,
            },
            synchronize_session="fetch",
        )
    )

    existing = (
        db.query(VehicleOwnership)
        .filter(
            VehicleOwnership.vehicle_id == vehicle.id,
            VehicleOwnership.customer_id == owner.id,
            VehicleOwnership.ownership_type == "owner",
        )
        .populate_existing()
        .first()
    )
    if existing:
        if not existing.is_active:
            existing.owned_from = now
        existing.is_active = True
        existing.is_primary = True
        existing.ownership_origin = ownership_origin or existing.ownership_origin or "manual"
        existing.owned_from = existing.owned_from or existing.assigned_at or now
        existing.owned_until = None
        existing.revoked_at = None
        existing.tenant_id = owner.tenant_id
        existing.updated_at = now
        db.flush()
        return existing

    ownership = VehicleOwnership(
        tenant_id=owner.tenant_id,
        vehicle_id=vehicle.id,
        customer_id=owner.id,
        ownership_type="owner",
        ownership_origin=ownership_origin or "manual",
        is_primary=True,
        is_active=True,
        assigned_by_customer_id=assigned_by_customer_id,
        owned_from=now,
        assigned_at=now,
    )
    db.add(ownership)
    db.flush()
    return ownership


def backfill_vehicle_owner_assignment(db: Session, vehicle: Vehicle) -> Optional[VehicleOwnership]:
    # Legacy email is only a migration hint for a vehicle with no ownership
    # history. Never let a read/access check transfer a vehicle or revive a grant.
    # Serialize concurrent backfills before checking whether history exists.
    locked_vehicle = (
        db.query(Vehicle).filter(Vehicle.id == vehicle.id)
        .with_for_update().populate_existing().first()
    )
    if locked_vehicle is None:
        return None
    vehicle = locked_vehicle
    assignments = db.query(VehicleOwnership).filter(VehicleOwnership.vehicle_id == vehicle.id).all()
    if assignments:
        return next((row for row in assignments if row.is_active and row.is_primary), None)
    owner = get_customer_by_email(db, getattr(vehicle, "user_email", None))
    if (not owner or owner.tenant_id != vehicle.tenant_id
            or owner.is_deleted or owner.is_disabled):
        return None
    return ensure_vehicle_owner_assignment(
        db,
        vehicle=vehicle,
        owner=owner,
        assigned_by_customer_id=owner.id,
        ownership_origin="legacy_backfill",
    )


def release_vehicle_owner_assignment(
    db: Session,
    *,
    vehicle: Vehicle,
    owner: Customer,
    revoked_by_customer_id: Optional[int] = None,
) -> bool:
    lock_vehicle_access(db, int(vehicle.id))
    now = datetime.utcnow()
    updated = (
        db.query(VehicleOwnership)
        .filter(
            VehicleOwnership.vehicle_id == vehicle.id,
            VehicleOwnership.customer_id == owner.id,
            VehicleOwnership.is_active.is_(True),
        )
        .update(
            {
                VehicleOwnership.is_active: False,
                VehicleOwnership.is_primary: False,
                VehicleOwnership.owned_until: now,
                VehicleOwnership.revoked_at: now,
                VehicleOwnership.updated_at: now,
            },
            synchronize_session="fetch",
        )
    )
    if updated:
        revoke_vehicle_sharing_for_owner_change(db, vehicle_id=int(vehicle.id),
            actor_id=revoked_by_customer_id or owner.id, reason="Vozidlo bylo odebráno z profilu vlastníka.")
    db.flush()
    return bool(updated)


def may_restore_vehicle_profile(db: Session, *, vehicle: Vehicle, customer: Customer) -> bool:
    """VIN identifies a car, never authority to take someone else's profile.

    Self-recovery is limited to the last recorded owner. A service pre-registration
    with no ownership history can be claimed only by its verified invited account.
    The caller holds the vehicle lock and authenticates email verification first.
    """
    history = (db.query(VehicleOwnership).filter_by(vehicle_id=vehicle.id, ownership_type="owner")
               .order_by(VehicleOwnership.owned_from.desc(), VehicleOwnership.id.desc())
               .populate_existing().all())
    if history:
        if any(row.is_active for row in history):
            return False
        latest = history[0]
        # Ambiguous legacy periods must be resolved by an administrator.
        newest = latest.owned_from or latest.assigned_at
        contenders = {row.customer_id for row in history if (row.owned_from or row.assigned_at) == newest}
        return latest.customer_id == customer.id and contenders == {customer.id}

    if _normalize_email(vehicle.user_email) != _normalize_email(customer.email):
        return False
    from .models import ServiceCustomerInvite
    from .email_verification import pending_verification
    if pending_verification(db, customer.id):
        return False
    pending_link = db.query(VehicleServiceLink).filter_by(
        vehicle_id=vehicle.id, source_type="pending_owner_registration", status="approved",
    ).first()
    if pending_link is None:
        return False
    return db.query(ServiceCustomerInvite.id).filter(
        ServiceCustomerInvite.service_customer_id == pending_link.service_customer_id,
        func.lower(ServiceCustomerInvite.invite_email) == _normalize_email(customer.email),
        or_(
            and_(ServiceCustomerInvite.status == "pending", ServiceCustomerInvite.expires_at > datetime.utcnow()),
            and_(ServiceCustomerInvite.status == "accepted", ServiceCustomerInvite.linked_customer_id == customer.id),
        ),
    ).first() is not None


def transfer_vehicle_to_new_owner(
    db: Session,
    *,
    vehicle: Vehicle,
    new_owner: Customer,
    assigned_by_customer_id: Optional[int] = None,
    ownership_origin: str = "vin_claim",
) -> VehicleOwnership:
    lock_vehicle_access(db, int(vehicle.id))
    previous = get_primary_vehicle_owner_assignment(db, int(vehicle.id))
    if previous is None or previous.customer_id != new_owner.id:
        revoke_vehicle_sharing_for_owner_change(db, vehicle_id=int(vehicle.id),
            actor_id=assigned_by_customer_id or new_owner.id, reason="Převod vozidla. Nový vlastník musí přístup servisu schválit znovu.")
    vehicle.tenant_id = new_owner.tenant_id
    vehicle.user_email = new_owner.email
    db.flush()
    return ensure_vehicle_owner_assignment(
        db,
        vehicle=vehicle,
        owner=new_owner,
        assigned_by_customer_id=assigned_by_customer_id or new_owner.id,
        ownership_origin=ownership_origin,
    )


def get_current_owner_since(db: Session, vehicle: Vehicle) -> Optional[datetime]:
    assignment = get_primary_vehicle_owner_assignment(db, int(vehicle.id))
    if assignment:
        return assignment.owned_from or assignment.assigned_at
    return None


def get_owned_vehicle_ids(
    db: Session,
    customer: Customer,
    *,
    tenant_id: Optional[int] = None,
) -> set[int]:
    """
    Vrátí ID vozidel, která aktuálně patří zákazníkovi.

    Primárně používá explicitní ownership vazbu. Legacy `vehicles.user_email`
    slouží pouze jako compat fallback pro bezpečný přechod a při nalezení
    starých dat se pokusí založit ownership assignment.
    """
    customer_id = getattr(customer, "id", None)
    if customer_id is None:
        return set()

    tenant_scope = tenant_id if tenant_id is not None else getattr(customer, "tenant_id", None)
    ownership_query = db.query(VehicleOwnership.vehicle_id).join(
        Vehicle, Vehicle.id == VehicleOwnership.vehicle_id,
    ).filter(
        VehicleOwnership.customer_id == customer_id,
        VehicleOwnership.is_active.is_(True),
    )
    if tenant_scope is not None:
        ownership_query = ownership_query.filter(
            VehicleOwnership.tenant_id == tenant_scope, Vehicle.tenant_id == tenant_scope,
        )

    owned_vehicle_ids = {
        int(vehicle_id)
        for (vehicle_id,) in ownership_query.all()
        if vehicle_id is not None
    }
    normalized_email = _normalize_email(getattr(customer, "email", None))
    if not normalized_email:
        return owned_vehicle_ids

    legacy_query = db.query(Vehicle).filter(func.lower(Vehicle.user_email) == normalized_email)
    if tenant_scope is not None:
        legacy_query = legacy_query.filter(Vehicle.tenant_id == tenant_scope)

    legacy_vehicles = legacy_query.all()
    for vehicle in legacy_vehicles:
        assignment = backfill_vehicle_owner_assignment(db, vehicle)
        if assignment and assignment.is_active and assignment.customer_id == customer.id:
            owned_vehicle_ids.add(int(vehicle.id))
    if legacy_vehicles:
        db.flush()
    return owned_vehicle_ids


def get_owned_vehicle_rows(
    db: Session,
    customer: Customer,
    *,
    tenant_id: Optional[int] = None,
) -> list[Vehicle]:
    owned_vehicle_ids = get_owned_vehicle_ids(db, customer, tenant_id=tenant_id)
    if not owned_vehicle_ids:
        return []

    tenant_scope = tenant_id if tenant_id is not None else getattr(customer, "tenant_id", None)
    query = db.query(Vehicle).filter(Vehicle.id.in_(sorted(owned_vehicle_ids)))
    if tenant_scope is not None:
        query = query.filter(Vehicle.tenant_id == tenant_scope)
    return query.order_by(Vehicle.created_at.desc(), Vehicle.id.desc()).all()


def get_owned_vehicle(
    db: Session,
    customer: Customer,
    vehicle_id: int,
    *,
    tenant_id: Optional[int] = None,
) -> Optional[Vehicle]:
    owned_vehicle_ids = get_owned_vehicle_ids(db, customer, tenant_id=tenant_id)
    if int(vehicle_id) not in owned_vehicle_ids:
        return None

    tenant_scope = tenant_id if tenant_id is not None else getattr(customer, "tenant_id", None)
    query = db.query(Vehicle).filter(Vehicle.id == int(vehicle_id))
    if tenant_scope is not None:
        query = query.filter(Vehicle.tenant_id == tenant_scope)
    return query.first()
