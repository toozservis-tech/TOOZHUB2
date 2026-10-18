"""Account-scoped vehicle inbox. Viewing never approves access requests."""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, exists, func
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Customer, VehicleOwnership, Vehicle
from ..vehicle_update_models import VehicleUpdate, VehicleUpdateReceipt
from ..schema_management import assert_module_ready
from .auth import get_current_user

router = APIRouter(prefix="/vehicle-updates", tags=["vehicle-updates"])


def inbox_query(db, user):
    # Recipient is captured at publication; current ownership is checked again.
    # Neither the buyer nor the former owner receives the other's private feed.
    ownership = exists().where(and_(VehicleOwnership.vehicle_id == VehicleUpdate.vehicle_id,
        VehicleOwnership.id == VehicleUpdate.ownership_id,
        func.coalesce(VehicleOwnership.owned_from, VehicleOwnership.assigned_at) == VehicleUpdate.ownership_started_at,
        VehicleOwnership.customer_id == user.id, VehicleOwnership.is_active.is_(True),
        VehicleOwnership.is_primary.is_(True)))
    return db.query(VehicleUpdate).filter(VehicleUpdate.recipient_id == user.id, ownership)


def iso(value):
    return value.isoformat(timespec="milliseconds") + "Z" if value else None


@router.get("")
def list_updates(before_id: int | None = Query(None, gt=0), limit: int = Query(30, ge=1, le=100),
                 current_user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    assert_module_ready(db, "vehicle_updates", detail_prefix="Upozornění vozidel nejsou připravena")
    query = inbox_query(db, current_user)
    read = exists().where(and_(VehicleUpdateReceipt.update_id == VehicleUpdate.id,
                               VehicleUpdateReceipt.recipient_id == current_user.id))
    unread_count = query.filter(~read).count()
    if before_id is not None:
        query = query.filter(VehicleUpdate.id < before_id)
    rows = query.order_by(VehicleUpdate.id.desc()).limit(limit + 1).all()
    has_more = len(rows) > limit
    rows = rows[:limit]
    ids = [row.id for row in rows]
    vehicles = {v.id: v for v in db.query(Vehicle).filter(Vehicle.id.in_({row.vehicle_id for row in rows})).all()} if rows else {}
    receipts = {row.update_id: row.read_at for row in db.query(VehicleUpdateReceipt).filter(
        VehicleUpdateReceipt.recipient_id == current_user.id,
        VehicleUpdateReceipt.update_id.in_(ids)).all()} if ids else {}
    return {"items": [{"id": row.id, "vehicle_id": row.vehicle_id,
        "vehicle_name": (vehicles[row.vehicle_id].nickname or ' '.join(filter(None,
            [vehicles[row.vehicle_id].brand, vehicles[row.vehicle_id].model]))) if row.vehicle_id in vehicles else None,
        "vehicle_plate": vehicles[row.vehicle_id].plate if row.vehicle_id in vehicles else None,
        "service_job_id": row.service_job_id, "event_type": row.event_type,
        "record_id": row.source_id if row.source_type == "service_records" else None,
        "title": row.title, "message": row.message, "occurred_at": iso(row.occurred_at),
        "source_type": row.source_type, "source_id": row.source_id,
        "read_at": iso(receipts.get(row.id))} for row in rows],
        "unread_count": unread_count, "has_more": has_more,
        "next_before_id": rows[-1].id if has_more and rows else None}


@router.post("/{update_id}/read")
def mark_read(update_id: int, current_user: Customer = Depends(get_current_user),
              db: Session = Depends(get_db)):
    assert_module_ready(db, "vehicle_updates", detail_prefix="Upozornění vozidel nejsou připravena")
    row = inbox_query(db, current_user).filter(VehicleUpdate.id == update_id).with_for_update().first()
    if row is None:
        raise HTTPException(404, "Upozornění nebylo nalezeno.")
    if db.get(VehicleUpdateReceipt, (row.id, current_user.id)) is None:
        db.add(VehicleUpdateReceipt(update_id=row.id, recipient_id=current_user.id))
        db.commit()
    return {"read": True}
