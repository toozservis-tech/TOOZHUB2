"""Owner/service negotiation. A proposal is never a confirmed appointment."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Customer, Vehicle, Reservation, ServiceCustomerLink
from ..booking_request_models import BookingRequest, BookingRequestEvent
from ..ownership import get_primary_vehicle_owner_assignment, lock_vehicle_access
from ..service_accounts import is_active_service_account
from ..schema_management import assert_module_ready
from ..vehicle_updates import publish_vehicle_update
from .auth import get_current_user


def ready(db: Session = Depends(get_db)):
    assert_module_ready(db, 'booking_requests', detail_prefix='Objednání do servisu není připravené')


router = APIRouter(prefix='/service-booking-requests', tags=['service-booking-requests'], dependencies=[Depends(ready)])


def utc(value):
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value and value.tzinfo else value


class BookingCreate(BaseModel):
    client_id: UUID
    vehicle_id: int = Field(gt=0)
    service_id: int = Field(gt=0)
    service_type: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=2000)
    preferred_datetime: datetime | None = None

    @field_validator('service_type', 'description')
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError('Doplňte popis požadavku.')
        return value.strip()

    @field_validator('preferred_datetime')
    @classmethod
    def normalize_date(cls, value):
        return utc(value)


class BookingDecision(BaseModel):
    client_id: UUID
    expected_version: int = Field(ge=1)
    action: Literal['accept', 'propose', 'reject', 'accept_proposal', 'cancel']
    message: str = Field(default='', max_length=2000)
    proposed_datetime: datetime | None = None

    @field_validator('proposed_datetime')
    @classmethod
    def normalize_date(cls, value):
        return utc(value)


def digest(payload):
    return sha256(json.dumps(payload.model_dump(mode='json'), sort_keys=True).encode()).hexdigest()


def actor_role(actor):
    role = str(actor.role or '').lower()
    if actor.is_disabled or actor.is_deleted or role not in {'user', 'service'}:
        raise HTTPException(403, 'Tato funkce je pro aktivní zákazníky a servisy.')
    return role


def serialize(db, row):
    service, owner = db.get(Customer, row.service_id), db.get(Customer, row.owner_id)
    reservation = db.get(Reservation, row.reservation_id) if row.reservation_id else None
    return {k: getattr(row, k) for k in ('id', 'owner_id', 'service_id', 'vehicle_id', 'vehicle_name',
        'vehicle_plate', 'service_type', 'description', 'preferred_datetime', 'proposed_datetime',
        'service_reply', 'status', 'version', 'reservation_id', 'created_at', 'updated_at')} | {
        'service_name': (service.name or service.email or 'Servis') if service else 'Servis',
        'customer_name': (owner.name or 'Zákazník') if owner else 'Zákazník',
        'reservation_status': reservation.status if reservation else None,
        'scheduled_datetime': reservation.start_datetime if reservation else None,
        'events': [{k: getattr(e, k) for k in ('id', 'actor_id', 'action', 'message', 'proposed_datetime', 'created_at')}
            for e in db.query(BookingRequestEvent).filter_by(request_id=row.id).order_by(BookingRequestEvent.id).all()]}


def current_owner(db, row):
    assignment = get_primary_vehicle_owner_assignment(db, row.vehicle_id)
    if not assignment or assignment.customer_id != row.owner_id or assignment.id != row.ownership_id or (assignment.owned_from or assignment.assigned_at) != row.ownership_started_at:
        raise HTTPException(409, 'Vlastnictví vozidla se změnilo. Tento požadavek už nelze měnit.')


def future(value):
    if value is None or value <= datetime.utcnow():
        raise HTTPException(422, 'Vyberte budoucí termín, nebo požádejte servis o jeho návrh.')


@router.get('')
def list_requests(current_user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    role = actor_role(current_user)
    query = db.query(BookingRequest).filter((BookingRequest.service_id if role == 'service' else BookingRequest.owner_id) == current_user.id)
    return {'items': [serialize(db, r) for r in query.order_by(BookingRequest.updated_at.desc(), BookingRequest.id.desc()).limit(200).all()]}


@router.post('')
def create_request(payload: BookingCreate, current_user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    if actor_role(current_user) != 'user':
        raise HTTPException(403, 'Požadavek odesílá vlastník vozidla.')
    lock_vehicle_access(db, payload.vehicle_id)
    # Serialize retries from all this owner's devices without creating credentials.
    db.query(Customer).filter(Customer.id == current_user.id).with_for_update().first()
    existing = db.query(BookingRequest).filter_by(owner_id=current_user.id, client_id=str(payload.client_id)).first()
    if existing:
        if existing.payload_hash != digest(payload):
            raise HTTPException(409, 'Tento požadavek už byl odeslán s jinými údaji.')
        return serialize(db, existing)
    vehicle = db.get(Vehicle, payload.vehicle_id)
    ownership = get_primary_vehicle_owner_assignment(db, payload.vehicle_id)
    if not vehicle or not ownership or ownership.customer_id != current_user.id:
        raise HTTPException(403, 'Objednat můžete pouze své vozidlo.')
    service = db.get(Customer, payload.service_id)
    linked = db.query(ServiceCustomerLink.id).filter_by(service_customer_id=payload.service_id, customer_id=current_user.id, status='active').first()
    if (not is_active_service_account(service) or not (service.password_hash or linked)
            or not (service.workshop_same_as_registered is not None or service.tenant_id == current_user.tenant_id or linked)):
        raise HTTPException(404, 'Vybraný servis není dostupný.')
    if payload.preferred_datetime is not None:
        future(payload.preferred_datetime)
    row = BookingRequest(owner_id=current_user.id, service_id=service.id, vehicle_id=vehicle.id,
        ownership_id=ownership.id, ownership_started_at=ownership.owned_from or ownership.assigned_at,
        vehicle_name=(vehicle.nickname or ' '.join(filter(None, [vehicle.brand, vehicle.model])) or 'Vozidlo')[:200],
        vehicle_plate=vehicle.plate, client_id=str(payload.client_id), payload_hash=digest(payload),
        service_type=payload.service_type, description=payload.description, preferred_datetime=payload.preferred_datetime)
    db.add(row); db.flush()
    db.add(BookingRequestEvent(request_id=row.id, actor_id=current_user.id, client_id=str(payload.client_id),
        payload_hash=digest(payload), action='created', message=payload.description, proposed_datetime=payload.preferred_datetime))
    db.commit(); db.refresh(row)
    return serialize(db, row)


@router.post('/{request_id}/decision')
def decide(request_id: int, payload: BookingDecision, current_user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    role = actor_role(current_user)
    row = db.get(BookingRequest, request_id)
    if not row or (row.service_id if role == 'service' else row.owner_id) != current_user.id:
        raise HTTPException(404, 'Požadavek nebyl nalezen.')
    lock_vehicle_access(db, row.vehicle_id)
    row = db.query(BookingRequest).filter_by(id=row.id).populate_existing().with_for_update().one()
    previous = db.query(BookingRequestEvent).filter_by(request_id=row.id, client_id=str(payload.client_id)).first()
    if previous:
        if previous.actor_id != current_user.id or previous.payload_hash != digest(payload):
            raise HTTPException(409, 'Opakovaná akce má jiné údaje.')
        return serialize(db, row)
    current_owner(db, row)
    if row.version != payload.expected_version:
        raise HTTPException(409, 'Požadavek se mezitím změnil. Obnovte seznam a zkontrolujte odpověď.')
    if row.status not in {'pending', 'proposed'}:
        raise HTTPException(409, 'Tento požadavek už je uzavřený.')
    allowed = {'accept', 'propose', 'reject'} if role == 'service' else {'accept_proposal', 'cancel'}
    if payload.action not in allowed:
        raise HTTPException(403, 'Tuto akci provádí druhá strana.')
    when = None
    if payload.action == 'accept':
        if row.status != 'pending':
            raise HTTPException(409, 'Navržený termín musí potvrdit zákazník.')
        when = row.preferred_datetime
        future(when)
    elif payload.action == 'accept_proposal':
        if row.status != 'proposed':
            raise HTTPException(409, 'Servis zatím nenavrhl termín.')
        when = row.proposed_datetime
        future(when)
    elif payload.action == 'propose':
        future(payload.proposed_datetime)
    elif payload.action == 'reject' and not payload.message.strip():
        raise HTTPException(422, 'Napište zákazníkovi krátký důvod odmítnutí.')
    if when:
        if not is_active_service_account(db.get(Customer, row.service_id)):
            raise HTTPException(409, "Vybraný servis už není aktivní.")
        # Serialize confirmations for one service, including different vehicles.
        db.query(Customer).filter_by(id=row.service_id).with_for_update().first()
        if db.query(Reservation.id).filter(Reservation.service_id == row.service_id,
                Reservation.start_datetime == when, Reservation.status.in_(['PENDING', 'CONFIRMED'])).first():
            raise HTTPException(409, 'Servis už má na tento čas rezervaci. Navrhněte jiný termín.')
        vehicle = db.get(Vehicle, row.vehicle_id)
        reservation = Reservation(tenant_id=vehicle.tenant_id, customer_id=row.owner_id,
            service_id=row.service_id, vehicle_id=row.vehicle_id, service_type=row.service_type,
            note=row.description, start_datetime=when, status='CONFIRMED', source_platform='mobile_quick_booking')
        db.add(reservation); db.flush()
        row.reservation_id = reservation.id
        row.status = 'confirmed'
    elif payload.action == 'propose':
        row.proposed_datetime = payload.proposed_datetime
        row.status = 'proposed'
    else:
        row.status = 'rejected' if payload.action == 'reject' else 'cancelled'
    if role == 'service':
        row.service_reply = payload.message.strip() or None
    row.version += 1
    row.updated_at = datetime.utcnow()
    db.add(BookingRequestEvent(request_id=row.id, actor_id=current_user.id, client_id=str(payload.client_id),
        payload_hash=digest(payload), action=payload.action, message=payload.message.strip() or None,
        proposed_datetime=when or payload.proposed_datetime))
    if role == 'service':
        title = {'confirmed':'Servis potvrdil rezervaci', 'proposed':'Servis navrhl termín', 'rejected':'Servis odmítl požadavek'}[row.status]
        publish_vehicle_update(db, vehicle_id=row.vehicle_id, actor_id=current_user.id, event_type='booking.'+row.status,
            title=title, message='Otevřete Rezervace a zkontrolujte odpověď servisu.',
            source_type='service_booking_requests', source_id=row.id, dedupe_key=f'booking:{row.id}:{row.version}')
    db.commit(); db.refresh(row)
    return serialize(db, row)
