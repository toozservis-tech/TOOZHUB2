"""Shared iOS/Android owner lifecycle contract; no runtime DDL."""
from datetime import date
from typing import Literal, Optional
from uuid import UUID
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Customer
from .. import vehicle_lifecycle as lifecycle
from .auth import get_current_user

router = APIRouter(tags=['vehicle-lifecycle'])


class VehicleLifecycleAction(BaseModel):
    client_id: UUID
    ownership_id: int = Field(ge=1)
    ownership_token: str = Field(pattern=r'^[a-f0-9]{64}$')
    expected_version: int = Field(ge=0)
    action: Literal['sold', 'removed', 'scrapped', 'deposited', 'reactivated']
    note: Optional[str] = Field(default=None, max_length=1000)
    effective_date: Optional[date] = None


@router.get('/vehicles/{vehicle_id}/lifecycle')
def get_lifecycle(vehicle_id: int, current_user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    lifecycle.ready(db)
    assignment = lifecycle.current_owner(db, vehicle_id, current_user)
    state, version = lifecycle.current_state(db, assignment)
    return {'vehicle_id': vehicle_id, 'ownership_id': assignment.id,
        'ownership_token': lifecycle.ownership_token(vehicle_id, assignment), 'version': version,
        'state': state, 'actions': lifecycle.actions_for(state)}


@router.post('/vehicles/{vehicle_id}/lifecycle')
def update_lifecycle(vehicle_id: int, payload: VehicleLifecycleAction,
        current_user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        result = lifecycle.apply_action(db, vehicle_id=vehicle_id, actor=current_user, payload=payload)
        db.commit()
        return result
    except IntegrityError:
        db.rollback()
        # The version and UUID constraints also guard non-locking SQLite clients.
        from fastapi import HTTPException
        raise HTTPException(409, 'Operace již byla zpracována nebo se stav vozidla změnil. Obnovte jej.')
    except Exception:
        db.rollback()
        raise
