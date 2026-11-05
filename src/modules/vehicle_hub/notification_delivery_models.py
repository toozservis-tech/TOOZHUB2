"""Private durable delivery metadata. Source messages remain authoritative."""
from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, UniqueConstraint, CheckConstraint
from .database import Base

class NotificationItem(Base):
    __tablename__='notification_items'
    id=Column(Integer,primary_key=True)
    recipient_id=Column(Integer,ForeignKey('customers.id',ondelete='CASCADE'),nullable=False,index=True)
    kind=Column(String(24),nullable=False)
    source_id=Column(Integer,nullable=False)
    created_at=Column(DateTime,nullable=False,default=datetime.utcnow)
    available_at=Column(DateTime) # Assigned to this inbox, not a device delivery receipt.
    snapshot_title=Column(Text)
    snapshot_body=Column(Text)
    snapshot_requires_ack=Column(Boolean)
    read_at=Column(DateTime)
    dismissed_at=Column(DateTime)
    acknowledged_at=Column(DateTime)
    __table_args__=(UniqueConstraint('recipient_id','kind','source_id',name='uq_notification_source'),
        CheckConstraint("kind IN ('admin_message','announcement','vehicle_update','service_event','admin_reply')",name='ck_notification_kind'))

class NotificationCommand(Base):
    __tablename__='notification_commands'
    id=Column(Integer,primary_key=True)
    recipient_id=Column(Integer,ForeignKey('customers.id',ondelete='CASCADE'),nullable=False,index=True)
    client_id=Column(String(36),nullable=False)
    kind=Column(String(16),nullable=False)
    request_hash=Column(String(64),nullable=False)
    item_ids=Column(Text,nullable=False)
    created_at=Column(DateTime,nullable=False,default=datetime.utcnow)
    __table_args__=(UniqueConstraint('recipient_id','client_id',name='uq_notification_command'),)

class AnnouncementPolicy(Base):
    __tablename__='notification_announcement_policies'
    source_id=Column(Integer,ForeignKey('system_notifications.id',ondelete='CASCADE'),primary_key=True)
    requires_ack=Column(Boolean,nullable=False,default=False)

class PushDevice(Base):
    __tablename__='notification_devices'
    id=Column(Integer,primary_key=True)
    recipient_id=Column(Integer,ForeignKey('customers.id',ondelete='CASCADE'),nullable=False,index=True)
    installation_id=Column(String(36),nullable=False,unique=True)
    installation_secret_hash=Column(String(64),nullable=False)
    platform=Column(String(16),nullable=False)
    environment=Column(String(16),nullable=False)
    bundle_id=Column(String(160),nullable=False)
    token_hash=Column(String(64),nullable=False,unique=True)
    token_ciphertext=Column(Text,nullable=False)
    session_digest=Column(String(64),nullable=False,index=True)
    session_version=Column(Integer,nullable=False)
    session_expires_at=Column(DateTime,nullable=False)
    permission=Column(String(16),nullable=False)
    active=Column(Boolean,nullable=False,default=True)
    generation=Column(Integer,nullable=False,default=1)
    created_at=Column(DateTime,nullable=False,default=datetime.utcnow)
    updated_at=Column(DateTime,nullable=False,default=datetime.utcnow)
    revoked_at=Column(DateTime)
    __table_args__=(CheckConstraint("platform IN ('apns','fcm','webpush')",name='ck_notification_platform'),)

class PushOutbox(Base):
    __tablename__='notification_push_outbox'
    id=Column(Integer,primary_key=True)
    item_id=Column(Integer,ForeignKey('notification_items.id',ondelete='CASCADE'),nullable=False,index=True)
    device_id=Column(Integer,ForeignKey('notification_devices.id',ondelete='CASCADE'),nullable=False,index=True)
    device_generation=Column(Integer,nullable=False)
    state=Column(String(16),nullable=False,default='queued',index=True)
    attempts=Column(Integer,nullable=False,default=0)
    next_attempt_at=Column(DateTime,nullable=False,default=datetime.utcnow,index=True)
    lease_until=Column(DateTime)
    lease_token=Column(String(36))
    accepted_at=Column(DateTime)
    last_code=Column(String(64)) # Strictly allowlisted codes, never raw provider response.
    created_at=Column(DateTime,nullable=False,default=datetime.utcnow)
    __table_args__=(UniqueConstraint('item_id','device_id',name='uq_notification_push'),)

class NotificationCursor(Base):
    __tablename__='notification_cursors'
    kind=Column(String(24),primary_key=True)
    source_id=Column(Integer,nullable=False,default=0)
    recipient_cursor=Column(Integer,nullable=False,default=0)
    rollout_at=Column(DateTime,nullable=False,default=datetime.utcnow)

TABLES=[NotificationItem.__table__,NotificationCommand.__table__,AnnouncementPolicy.__table__,PushDevice.__table__,PushOutbox.__table__,NotificationCursor.__table__]

def erase_account_notifications(db,customer):
    from sqlalchemy import inspect
    if not inspect(db.connection()).has_table(NotificationItem.__tablename__):return
    from .operational_notification_models import NotificationOperationalEvent as Event
    if inspect(db.connection()).has_table(Event.__tablename__):
        event_ids=db.query(Event.id).filter((Event.recipient_id==customer.id)|(Event.actor_id==customer.id))
        event_items=db.query(NotificationItem.id).filter(NotificationItem.kind=='service_event',NotificationItem.source_id.in_(event_ids))
        db.query(PushOutbox).filter(PushOutbox.item_id.in_(event_items)).delete(synchronize_session=False)
        db.query(NotificationItem).filter(NotificationItem.id.in_(event_items)).delete(synchronize_session=False)
        db.query(Event).filter((Event.recipient_id==customer.id)|(Event.actor_id==customer.id)).delete(synchronize_session=False)
    item_ids=db.query(NotificationItem.id).filter_by(recipient_id=customer.id)
    device_ids=db.query(PushDevice.id).filter_by(recipient_id=customer.id)
    db.query(PushOutbox).filter((PushOutbox.item_id.in_(item_ids))|(PushOutbox.device_id.in_(device_ids))).delete(synchronize_session=False)
    db.query(NotificationCommand).filter_by(recipient_id=customer.id).delete(synchronize_session=False)
    db.query(PushDevice).filter_by(recipient_id=customer.id).delete(synchronize_session=False)
    db.query(NotificationItem).filter_by(recipient_id=customer.id).delete(synchronize_session=False)
