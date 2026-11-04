from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Customer
from .. import vehicle_transfers as transfers
from .auth import get_current_user

router = APIRouter(prefix='/vehicle-transfers', tags=['vehicle-transfers'])

class Decision(BaseModel):
    accept: bool
    code: Optional[str] = Field(default=None, max_length=128)

@router.get('')
def list_transfers(user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    return transfers.list_for(db, user)

@router.post('/{invite_id}/decision')
def decide_transfer(invite_id: int, payload: Decision, user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    from src.core.rate_limiter import rate_limiter
    if not rate_limiter.check_rate_limit(f'transfer-decision:{user.id}', 20, 60):
        raise HTTPException(429, 'Příliš mnoho pokusů. Zkuste to za minutu.')
    try:
        result = transfers.decide(db, invite_id, user, accept=payload.accept, code=payload.code)
        db.commit(); return result
    except Exception:
        db.rollback(); raise

@router.post('/{invite_id}/cancel')
def cancel_transfer(invite_id: int, user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        result = transfers.cancel(db, invite_id, user)
        db.commit(); return result
    except Exception:
        db.rollback(); raise

@router.post('/{invite_id}/resend')
def resend_transfer(invite_id: int, user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    return transfers.send_invitation(db, invite_id, user, resend=True)
