"""Account-scoped vehicle inbox. Viewing never approves access requests."""
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, StrictBool, model_validator
from sqlalchemy import and_, exists, func
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Customer, VehicleOwnership, Vehicle
from ..vehicle_update_models import VehicleUpdate, VehicleUpdateReceipt, VehicleUpdateInboxState
from ..vehicle_updates import change_inbox_receipt
from ..schema_management import assert_module_ready
from .auth import get_current_user

router = APIRouter(prefix="/vehicle-updates", tags=["vehicle-updates"])
InboxFolder = Literal["inbox", "archive", "trash"]


class ReceiptUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    read: StrictBool | None = None
    folder: InboxFolder | None = None

    @model_validator(mode="after")
    def require_change(self):
        if self.read is None and self.folder is None:
            raise ValueError("Zadejte stav přečtení nebo složku zprávy.")
        return self


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


def folder_clause(user_id, folder):
    state = exists().where(and_(VehicleUpdateInboxState.update_id == VehicleUpdate.id,
        VehicleUpdateInboxState.recipient_id == user_id,
        VehicleUpdateInboxState.folder != "inbox" if folder == "inbox"
            else VehicleUpdateInboxState.folder == folder))
    return ~state if folder == "inbox" else state


def unread_count(db, user):
    read = exists().where(and_(VehicleUpdateReceipt.update_id == VehicleUpdate.id,
        VehicleUpdateReceipt.recipient_id == user.id))
    return inbox_query(db, user).filter(folder_clause(user.id, "inbox"), ~read).count()


def receipt_fields(read_at, state):
    return {"read": read_at is not None, "read_at": iso(read_at),
        "folder": state.folder if state is not None else "inbox",
        "archived_at": iso(state.archived_at) if state is not None else None,
        "deleted_at": iso(state.deleted_at) if state is not None else None}


@router.get("")
def list_updates(before_id: int | None = Query(None, gt=0), limit: int = Query(30, ge=1, le=100),
                 current_user: Customer = Depends(get_current_user), db: Session = Depends(get_db),
                 folder: InboxFolder = "inbox"):
    assert_module_ready(db, "vehicle_updates", detail_prefix="Upozornění vozidel nejsou připravena")
    query = inbox_query(db, current_user)
    folder_counts = {"inbox": 0, "archive": 0, "trash": 0}
    group = func.coalesce(VehicleUpdateInboxState.folder, "inbox")
    for name, count in query.outerjoin(VehicleUpdateInboxState, and_(
            VehicleUpdateInboxState.update_id == VehicleUpdate.id,
            VehicleUpdateInboxState.recipient_id == current_user.id)).with_entities(
                group, func.count(VehicleUpdate.id)).group_by(group).all():
        folder_counts[name] = count
    total_unread = unread_count(db, current_user)
    query = query.filter(folder_clause(current_user.id, folder))
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
    states = {row.update_id: row for row in db.query(VehicleUpdateInboxState).filter(
        VehicleUpdateInboxState.recipient_id == current_user.id,
        VehicleUpdateInboxState.update_id.in_(ids)).all()} if ids else {}
    return {"items": [{"id": row.id, "vehicle_id": row.vehicle_id,
        "vehicle_name": (vehicles[row.vehicle_id].nickname or ' '.join(filter(None,
            [vehicles[row.vehicle_id].brand, vehicles[row.vehicle_id].model]))) if row.vehicle_id in vehicles else None,
        "vehicle_plate": vehicles[row.vehicle_id].plate if row.vehicle_id in vehicles else None,
        "service_job_id": row.service_job_id, "event_type": row.event_type,
        "record_id": row.source_id if row.source_type == "service_records" else None,
        "title": row.title, "message": row.message, "occurred_at": iso(row.occurred_at),
        "source_type": row.source_type, "source_id": row.source_id,
        **receipt_fields(receipts.get(row.id), states.get(row.id))} for row in rows],
        "folder": folder, "folder_counts": folder_counts,
        "unread_count": total_unread, "has_more": has_more,
        "next_before_id": rows[-1].id if has_more and rows else None}


@router.post("/{update_id}/read")
def mark_read(update_id: int, current_user: Customer = Depends(get_current_user),
              db: Session = Depends(get_db)):
    _change_receipt(update_id, ReceiptUpdate(read=True), current_user, db)
    return {"read": True}


def _change_receipt(update_id, data, current_user, db):
    assert_module_ready(db, "vehicle_updates", detail_prefix="Upozornění vozidel nejsou připravena")
    row = inbox_query(db, current_user).filter(VehicleUpdate.id == update_id).with_for_update().first()
    if row is None:
        raise HTTPException(404, "Upozornění nebylo nalezeno.")
    change_inbox_receipt(db, row, read=data.read, folder=data.folder)
    db.commit()  # Also release the event lock for an idempotent retry.
    return row.id


@router.put("/{update_id}/receipt")
def update_receipt(update_id: int, data: ReceiptUpdate,
                   current_user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    identity = _change_receipt(update_id, data, current_user, db)
    receipt = db.get(VehicleUpdateReceipt, (identity, current_user.id))
    state = db.get(VehicleUpdateInboxState, (identity, current_user.id))
    return {"id": identity,
        **receipt_fields(receipt.read_at if receipt is not None else None, state),
        "unread_count": unread_count(db, current_user)}
