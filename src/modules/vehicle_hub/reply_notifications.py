"""A reply addresses only its explicit original author; no implicit fanout."""
from fastapi import HTTPException
from sqlalchemy import inspect
from .admin_message_models import AdminMessage

ADMIN_ROLES={'admin','developer_admin'}
def active_admin(user):return bool(user and user.role in ADMIN_ROLES and not(user.is_deleted or user.is_disabled))

def resolve_reply_target(db,actor,body):
    mid=body.reply_to_message_id;nid=body.reply_to_notification_id
    if not mid and not nid:return {}
    columns={c['name'] for c in inspect(db.connection()).get_columns('admin_messages')}
    if 'addressed_admin_id' not in columns:raise HTTPException(503,'Cílené odpovědi čekají na aktualizaci serveru.')
    from .models import Customer,SystemNotification
    if mid:
        original=db.get(AdminMessage,mid)
        if not original or original.recipient_id!=actor.id or original.sender_kind!='admin':
            raise HTTPException(404,'Původní zpráva není dostupná.')
        target_id=original.sender_id
    else:
        from .notification_delivery_models import NotificationItem
        from .notification_inbox import announcement_matches
        original=db.get(SystemNotification,nid)
        receipt=db.query(NotificationItem.id).filter_by(kind='announcement',source_id=nid,recipient_id=actor.id).filter(NotificationItem.available_at.isnot(None)).first()
        if not original or not(receipt or announcement_matches(db,original,actor)):
            raise HTTPException(404,'Původní oznámení není dostupné.')
        target_id=original.created_by_customer_id
    target=db.get(Customer,target_id) if target_id else None
    return {'reply_to_message_id':mid,'reply_to_notification_id':nid,
        'addressed_admin_id':target.id if active_admin(target) else None}
