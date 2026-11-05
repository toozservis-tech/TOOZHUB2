from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, EmailStr, field_validator
from uuid import UUID
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Customer
from .. import vehicle_transfers as transfers
from .auth import get_current_user

router = APIRouter(prefix='/vehicle-transfers', tags=['vehicle-transfers'])

class Decision(BaseModel):
    accept: bool
    code: Optional[str] = Field(default=None, max_length=128)

class Recipient(BaseModel):
    buyer_email: EmailStr

    @field_validator('buyer_email')
    @classmethod
    def normalize_email(cls, value): return str(value).strip().lower()

class VerifiedTransfer(Recipient):
    reason: str = Field(min_length=10, max_length=1000)
    review_token: str = Field(pattern=r'^[a-f0-9]{64}$')
    request_id: UUID

    @field_validator('reason')
    @classmethod
    def valid_reason(cls, value):
        value = value.strip()
        if len(value) < 10: raise ValueError('Popište ověřené podklady alespoň deseti znaky.')
        return value


def deliver_committed(db, row):
    # Internal call after authorized creation, never a client-supplied sender.
    invite_id, seller_id = row.id, row.seller_id
    db.commit()
    try:
        transfers.send_invitation(db, invite_id, db.get(Customer, seller_id))
    except Exception:
        db.rollback()
    return db.get(transfers.Invite, invite_id)


@router.post('/from-archive/{archive_id}')
def invite_from_archive(archive_id: int, payload: Recipient,
        user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        row = transfers.from_archive(db, archive_id, user, payload.buyer_email)
        return transfers.output(db, deliver_committed(db, row), user)
    except Exception:
        db.rollback(); raise


@router.get('/admin/vehicles/{vehicle_id}')
def review_transfer(vehicle_id: int, user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    return transfers.admin_review(db, vehicle_id, user)


@router.post('/admin/vehicles/{vehicle_id}')
def verify_transfer(vehicle_id: int, payload: VerifiedTransfer,
        user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    try:
        row = transfers.admin_invite(db, vehicle_id, user, payload)
        row = deliver_committed(db, row)
        return transfers.output(db, row, db.get(Customer, row.seller_id))
    except Exception:
        db.rollback(); raise

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
