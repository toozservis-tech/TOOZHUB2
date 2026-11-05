"""Transactional customer->service notifications, independent of vehicle consent."""
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import inspect
from .operational_notification_models import NotificationOperationalEvent as Event

TITLES={
 'reservation.created':'Nová rezervace od zákazníka',
 'reservation.cancelled':'Zákazník zrušil rezervaci',
 'reservation.deleted':'Zákazník odstranil rezervaci',
 'booking_request.created':'Nový požadavek do servisu',
 'booking_request.proposal_accepted':'Zákazník přijal navržený termín',
 'booking_request.cancelled':'Zákazník zrušil požadavek',
 'service_access.approved':'Majitel schválil přístup k vozidlu',
 'service_access.rejected':'Majitel odmítl přístup k vozidlu',
 'service_access.revoked':'Přístup k vozidlu byl odvolán',
}

def emit(db,*,recipient_id,actor_id,source_type,source_id,event_type,dedupe_key=None):
    from .models import Customer
    if event_type not in TITLES:raise ValueError('Unsupported operational event')
    target=db.get(Customer,recipient_id)
    if not target or target.role!='service' or target.is_deleted or target.is_disabled:return None
    if not inspect(db.connection()).has_table(Event.__tablename__):
        raise HTTPException(503,'Servisní oznámení čekají na aktualizaci serveru.')
    key=dedupe_key or f'{source_type}:{source_id}:{event_type}:{uuid4()}'
    existing=next((row for row in db.new if isinstance(row,Event) and row.dedupe_key==key),None)
    if existing:return existing
    existing=db.query(Event).filter_by(dedupe_key=key).first()
    if existing:return existing
    row=Event(recipient_id=recipient_id,actor_id=actor_id,source_type=source_type,
        source_id=source_id,event_type=event_type,dedupe_key=key)
    db.add(row)
    return row

def booking_change(db,row,actor,event_type,*,quick=False,event_id=None):
    if actor.role!='user' or actor.id!=(row.owner_id if quick else row.customer_id):return None
    return emit(db,recipient_id=row.service_id,actor_id=actor.id,
        source_type='booking_request' if quick else 'reservation',source_id=row.id,event_type=event_type,
        dedupe_key=f'booking-event:{event_id}' if event_id else (f'reservation:{row.id}:created' if event_type=='reservation.created' else None))

def event_context(db,event,user):
    """Minimal receipt remains visible after revocation; no vehicle data is returned."""
    from .models import Reservation,ServiceAccessRequest,VehicleServiceLink
    from .booking_request_models import BookingRequest
    if event.recipient_id!=user.id or user.role!='service' or user.is_deleted or user.is_disabled:
        raise HTTPException(404,'Servisní oznámení není dostupné.')
    model={'reservation':Reservation,'booking_request':BookingRequest,'access_request':ServiceAccessRequest,'service_link':VehicleServiceLink}[event.source_type]
    row=db.get(model,event.source_id)
    target=getattr(row,'service_id',None) if event.source_type in ('reservation','booking_request') else getattr(row,'service_customer_id',None)
    available=bool(row and target==user.id)
    status=str(row.status) if available else 'unavailable'
    action=None
    if event.source_type in ('reservation','booking_request') and available:
        action={'type':event.source_type,'id':event.source_id,'vehicle_id':None}
    elif event.source_type in ('access_request','service_link'):
        action={'type':'service_access','id':event.id,'vehicle_id':None}
    return {'event_id':event.id,'occurred_at':event.created_at.isoformat(timespec='microseconds')+'Z','event_type':event.event_type,'source_type':event.source_type,'source_id':event.source_id,
        'title':TITLES[event.event_type], 'message':'Otevřete související přehled a zkontrolujte aktuální stav. Toto oznámení samo nemění oprávnění.',
        'current_status':status,'source_available':available,'action':action}
