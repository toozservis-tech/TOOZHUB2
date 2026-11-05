"""Immutable, narrowly addressed service events; never copies customer notes."""
from datetime import datetime
from sqlalchemy import Column,Integer,String,DateTime,ForeignKey,UniqueConstraint,CheckConstraint,event
from .database import Base

class NotificationOperationalEvent(Base):
    __tablename__='notification_operational_events'
    id=Column(Integer,primary_key=True)
    recipient_id=Column(Integer,ForeignKey('customers.id',ondelete='CASCADE'),nullable=False,index=True)
    actor_id=Column(Integer,ForeignKey('customers.id',ondelete='SET NULL'),nullable=True,index=True)
    source_type=Column(String(32),nullable=False)
    source_id=Column(Integer,nullable=False)
    event_type=Column(String(64),nullable=False)
    dedupe_key=Column(String(160),nullable=False,unique=True)
    created_at=Column(DateTime,nullable=False,default=datetime.utcnow,index=True)
    __table_args__=(CheckConstraint("source_type IN ('reservation','booking_request','access_request','service_link')",name='ck_operational_source'),)

@event.listens_for(NotificationOperationalEvent,'before_update')
def prevent_update(mapper,connection,target):
    raise RuntimeError('Operational notification sources are immutable')
