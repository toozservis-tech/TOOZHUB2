"""Private administrator conversations; bodies immutable outside explicit erasure."""
from datetime import datetime
from sqlalchemy import Column,Integer,String,Text,Boolean,DateTime,ForeignKey,UniqueConstraint,CheckConstraint,Index
from .database import Base


class AdminMessage(Base):
    __tablename__='admin_messages'
    id=Column(Integer,primary_key=True)
    recipient_id=Column(Integer,ForeignKey('customers.id'),nullable=False,index=True)
    sender_id=Column(Integer,ForeignKey('customers.id'),nullable=True,index=True)
    sender_kind=Column(String(16),nullable=False)
    reply_to_message_id=Column(Integer,ForeignKey('admin_messages.id',ondelete='SET NULL'),nullable=True,index=True)
    reply_to_notification_id=Column(Integer,ForeignKey('system_notifications.id',ondelete='SET NULL'),nullable=True,index=True)
    addressed_admin_id=Column(Integer,ForeignKey('customers.id',ondelete='SET NULL'),nullable=True,index=True)
    body=Column(Text,nullable=False)
    body_erased=Column(Boolean,nullable=False,default=False)
    requires_ack=Column(Boolean,nullable=False,default=False)
    sent_at=Column(DateTime,nullable=False,default=datetime.utcnow,index=True)
    read_at=Column(DateTime,nullable=True)
    acknowledged_at=Column(DateTime,nullable=True)
    __table_args__=(CheckConstraint("sender_kind IN ('admin','recipient')",name='ck_admin_message_sender'),
                   CheckConstraint("sender_kind = 'admin' OR requires_ack = false",name='ck_admin_message_ack_sender'),
                   Index('ix_admin_message_unread','recipient_id','sender_kind','read_at'),
                   Index('ix_admin_message_ack','recipient_id','requires_ack','acknowledged_at'))


class AdminMessageCommand(Base):
    """Idempotent commands also audit send/read/ack without copying private bodies."""
    __tablename__='admin_message_commands'
    id=Column(Integer,primary_key=True)
    actor_id=Column(Integer,ForeignKey('customers.id'),nullable=False)
    recipient_id=Column(Integer,ForeignKey('customers.id'),nullable=False,index=True)
    client_id=Column(String(36),nullable=False)
    kind=Column(String(24),nullable=False)
    request_hash=Column(String(64),nullable=False)
    message_id=Column(Integer,ForeignKey('admin_messages.id'),nullable=True)
    result_count=Column(Integer,nullable=False,default=0)
    message_ids_json=Column(Text,nullable=True)  # IDs only: no message bodies/tokens.
    created_at=Column(DateTime,nullable=False,default=datetime.utcnow)
    __table_args__=(UniqueConstraint('actor_id','client_id',name='uq_admin_message_command'),)


TABLES=[AdminMessage.__table__,AdminMessageCommand.__table__]


def erase_account_messages(db,customer):
    from sqlalchemy import inspect,or_
    if not all(inspect(db.connection()).has_table(table.name) for table in TABLES):return
    if 'addressed_admin_id' in {c['name'] for c in inspect(db.connection()).get_columns('admin_messages')}:
        db.query(AdminMessage).filter_by(addressed_admin_id=customer.id).update({'addressed_admin_id':None},synchronize_session=False)
    ids=db.query(AdminMessage.id).filter_by(recipient_id=customer.id)
    db.query(AdminMessageCommand).filter(or_(AdminMessageCommand.recipient_id==customer.id,
        AdminMessageCommand.actor_id==customer.id,AdminMessageCommand.message_id.in_(ids))).delete(synchronize_session=False)
    db.query(AdminMessage).filter_by(recipient_id=customer.id).delete(synchronize_session=False)
    # Other recipients retain the fact/time of a message, not private author text.
    db.query(AdminMessage).filter_by(sender_id=customer.id).update({'sender_id':None,'body_erased':True,
        'body':'Obsah zprávy odstraněn při výmazu autora účtu.','requires_ack':False},synchronize_session=False)
