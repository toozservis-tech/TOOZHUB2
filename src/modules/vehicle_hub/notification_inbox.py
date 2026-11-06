"""Unified account inbox; authorization is rechecked against each source.

Announcement content is snapshotted only for an eligible recipient to preserve
archive history. No private body enters push payloads. Historical sources can
be surfaced without delivering historical push notifications.
"""
from datetime import datetime
import hashlib,json
from sqlalchemy import inspect,or_,and_,func,case
from fastapi import HTTPException
from .notification_delivery_models import NotificationItem as Item,NotificationCommand as Command,AnnouncementPolicy,NotificationCursor,PushDevice,PushOutbox,TABLES
from .admin_message_models import AdminMessage
from .operational_notification_models import NotificationOperationalEvent
from .reply_notifications import active_admin
from .push_policy import delivery_policy
from .models import Customer,SystemNotification,License,VehicleOwnership
from .vehicle_update_models import VehicleUpdate,VehicleUpdateReceipt,VehicleUpdateInboxState

KINDS={'admin_message':AdminMessage,'announcement':SystemNotification,'vehicle_update':VehicleUpdate,'service_event':NotificationOperationalEvent,'admin_reply':AdminMessage}

def ready(db):
    inspector=inspect(db.connection())
    return all(inspector.has_table(t.name) for t in TABLES) and inspector.has_table(NotificationOperationalEvent.__tablename__) and {'addressed_admin_id','reply_to_message_id','reply_to_notification_id'}.issubset({c['name'] for c in inspector.get_columns('admin_messages')})

def require_ready(db):
    if not ready(db):raise HTTPException(503,'Centrum oznámení čeká na aktualizaci serveru. Zkuste to později.')

def active_user(user):return user and user.role in {'user','service'} and not(user.is_deleted or user.is_disabled)

def active_recipient(user):return bool(active_user(user) or active_admin(user))

def announcement_matches(db,row,user,now=None,ignore_time=False):
    now=now or datetime.utcnow()
    if not row.is_active or (not ignore_time and row.starts_at and row.starts_at>now) or (row.expires_at and row.expires_at<=now):return False
    if row.target_type=='all':return True
    if row.target_type=='user':return str(user.id)==row.target_value
    if row.target_type=='tenant':return str(user.tenant_id)==row.target_value
    if row.target_type=='plan':
        license=db.query(License).filter_by(tenant_id=user.tenant_id).first()
        return bool(license and str(license.plan or '').lower()==str(row.target_value or '').lower())
    return False

def source_for(db,item,user,*,for_delivery=False):
    if item.recipient_id!=user.id or not active_recipient(user):return None
    if active_admin(user) and item.kind!='admin_reply':return None
    if item.kind=='admin_reply' and not active_admin(user):return None
    row=db.get(KINDS[item.kind],item.source_id)
    if item.kind=='announcement' and item.available_at is not None and not for_delivery:
        from types import SimpleNamespace
        return SimpleNamespace(id=item.source_id,title=item.snapshot_title,message=item.snapshot_body,
            snapshot_requires_ack=bool(item.snapshot_requires_ack),
            archived=not(row and announcement_matches(db,row,user)))
    if row is None:return None
    if item.kind=='admin_reply':return row if row.addressed_admin_id==user.id and row.sender_kind=='recipient' else None
    if item.kind=='service_event':return row if user.role=='service' and row.recipient_id==user.id else None
    if item.kind=='admin_message':return row if row.recipient_id==user.id and row.sender_kind=='admin' else None
    if item.kind=='announcement':return row if announcement_matches(db,row,user) else None
    owner=db.query(VehicleOwnership).filter_by(id=row.ownership_id,vehicle_id=row.vehicle_id,customer_id=user.id,is_active=True,is_primary=True).first()
    if row.recipient_id!=user.id or not owner or (owner.owned_from or owner.assigned_at)!=row.ownership_started_at:return None
    state=db.get(VehicleUpdateInboxState,(row.id,user.id))
    return row if state is None or state.folder=='inbox' else None

def source_time(kind,row):return row.sent_at if kind in ('admin_message','admin_reply') else row.occurred_at if kind=='vehicle_update' else row.created_at

def requires_ack(db,item,source):
    if item.kind=='admin_message':return bool(source.requires_ack and not source.body_erased)
    if item.kind=='announcement' and item.available_at is not None:return bool(item.snapshot_requires_ack)
    policy=db.get(AnnouncementPolicy,source.id) if item.kind=='announcement' else None
    return bool(policy and policy.requires_ack)

def sync_receipts(db,item,source):
    if item.kind=='admin_message':
        if source.read_at:item.read_at=source.read_at
        if source.acknowledged_at:item.acknowledged_at=source.acknowledged_at
    elif item.kind=='vehicle_update':
        receipt=db.get(VehicleUpdateReceipt,(source.id,item.recipient_id))
        item.read_at=receipt.read_at if receipt else None

def ensure_item(db,user,kind,source,*,queue=False):
    item=db.query(Item).filter_by(recipient_id=user.id,kind=kind,source_id=source.id).first()
    if item is None:
        item=Item(recipient_id=user.id,kind=kind,source_id=source.id,created_at=source_time(kind,source))
        db.add(item);db.flush()
    if kind=='announcement' and item.available_at is None and announcement_matches(db,source,user):
        policy=db.get(AnnouncementPolicy,source.id)
        item.available_at=datetime.utcnow();item.snapshot_title=source.title or 'Oznámení administrace'
        item.snapshot_body=source.message;item.snapshot_requires_ack=bool(policy and policy.requires_ack)
    sync_receipts(db,item,source)
    if queue and not item.read_at and not item.dismissed_at and not item.acknowledged_at:
        delivery = delivery_policy()
        now = datetime.utcnow()
        for device in db.query(PushDevice).filter_by(recipient_id=user.id,active=True):
            if not delivery.can_queue(user.id, device, item.created_at, now):
                continue
            if not db.query(PushOutbox.id).filter_by(item_id=item.id,device_id=device.id).first():
                db.add(PushOutbox(item_id=item.id,device_id=device.id,device_generation=device.generation,
                    next_attempt_at=max(datetime.utcnow(),source.starts_at) if kind=='announcement' and source.starts_at else datetime.utcnow()))
    return item

def materialize(db,user):
    require_ready(db)
    # Serialize materialization with receipt commands and worker for this account.
    from src.server.admin_messages import lock_recipient
    lock_recipient(db,user)
    if active_admin(user):
        for row in db.query(AdminMessage).filter(AdminMessage.addressed_admin_id==user.id,AdminMessage.sender_kind=='recipient',~db.query(Item.id).filter(Item.recipient_id==user.id,Item.kind=='admin_reply',Item.source_id==AdminMessage.id).exists()).order_by(AdminMessage.id):
            ensure_item(db,user,'admin_reply',row)
        db.flush();return
    if user.role=='service':
        for row in db.query(NotificationOperationalEvent).filter(NotificationOperationalEvent.recipient_id==user.id,~db.query(Item.id).filter(Item.recipient_id==user.id,Item.kind=='service_event',Item.source_id==NotificationOperationalEvent.id).exists()).order_by(NotificationOperationalEvent.id):
            ensure_item(db,user,'service_event',row)
    for row in db.query(AdminMessage).filter(AdminMessage.recipient_id==user.id,AdminMessage.sender_kind=='admin',
            ~db.query(Item.id).filter(Item.recipient_id==user.id,Item.kind=='admin_message',Item.source_id==AdminMessage.id).exists()).order_by(AdminMessage.id):
        ensure_item(db,user,'admin_message',row)
    for row in db.query(SystemNotification).filter(SystemNotification.is_active.is_(True),
            ~db.query(Item.id).filter(Item.recipient_id==user.id,Item.kind=='announcement',Item.source_id==SystemNotification.id).exists()).order_by(SystemNotification.id):
        if announcement_matches(db,row,user):ensure_item(db,user,'announcement',row)
    # Exact ownership epoch is checked again before every display and dispatch.
    owned=db.query(VehicleOwnership.id).filter_by(customer_id=user.id,is_active=True,is_primary=True)
    for row in db.query(VehicleUpdate).filter(VehicleUpdate.recipient_id==user.id,VehicleUpdate.ownership_id.in_(owned),
            ~db.query(Item.id).filter(Item.recipient_id==user.id,Item.kind=='vehicle_update',Item.source_id==VehicleUpdate.id).exists()).order_by(VehicleUpdate.id):
        ensure_item(db,user,'vehicle_update',row)
    # Scheduled announcements may already have an item but become available now.
    for item in db.query(Item).filter_by(recipient_id=user.id,kind='announcement',available_at=None):
        source=db.get(SystemNotification,item.source_id)
        if source and announcement_matches(db,source,user):ensure_item(db,user,'announcement',source)
    db.flush()

def stamp(value):return value.isoformat(timespec='microseconds')+'Z' if value else None

def item_view(db,item,user,source=None):
    source=source or source_for(db,item,user)
    if source is None:raise HTTPException(404,'Oznámení není dostupné.')
    sync_receipts(db,item,source)
    action={'type':'admin_messages' if item.kind=='admin_message' else item.kind,'id':item.source_id,
            'vehicle_id':source.vehicle_id if item.kind=='vehicle_update' else None}
    if item.kind=='service_event':
        from .operational_notifications import event_context
        context=event_context(db,source,user);title=context['title'];body=context['message'];action=context['action']
    elif item.kind=='admin_reply':
        title='Odpověď na vaši zprávu';body=source.body
        action={'type':'admin_conversation','id':source.recipient_id,'vehicle_id':None}
    else:
        title='Zpráva administrace' if item.kind=='admin_message' else source.title or 'Oznámení administrace'
        body=source.body if item.kind=='admin_message' else source.message
    return {'id':item.id,'kind':item.kind,'source_id':item.source_id,'title':title,'body':body,
        'requires_ack':requires_ack(db,item,source),'archived':bool(getattr(source,'archived',False)),'created_at':stamp(item.created_at),'read_at':stamp(item.read_at),
        'acknowledged_at':stamp(item.acknowledged_at),'dismissed_at':stamp(item.dismissed_at),
        'action':action}

def accessible(db,user):
    result=[]
    for item in db.query(Item).filter_by(recipient_id=user.id).order_by(Item.id.desc()):
        source=source_for(db,item,user)
        if source is not None:result.append((item,source));sync_receipts(db,item,source)
    return result

def is_pending(db,item,source):
    if item.kind in ('vehicle_update','service_event','admin_reply'):return False
    if getattr(source,'archived',False):return False
    return item.acknowledged_at is None if requires_ack(db,item,source) else item.dismissed_at is None and item.acknowledged_at is None

def inbox_query(db,user):
    """Filter and count in SQL; no N+1 scan of a growing account history."""
    now=datetime.utcnow()
    if active_admin(user):
        query=db.query(Item).join(AdminMessage,and_(Item.kind=='admin_reply',Item.source_id==AdminMessage.id)).filter(
            Item.recipient_id==user.id,AdminMessage.addressed_admin_id==user.id,AdminMessage.sender_kind=='recipient')
        from sqlalchemy import false
        return query,Item.read_at,false(),Item.acknowledged_at,false()
    owner=db.query(VehicleOwnership.id).filter(VehicleOwnership.id==VehicleUpdate.ownership_id,
        VehicleOwnership.vehicle_id==VehicleUpdate.vehicle_id,VehicleOwnership.customer_id==user.id,
        VehicleOwnership.is_active.is_(True),VehicleOwnership.is_primary.is_(True),
        func.coalesce(VehicleOwnership.owned_from,VehicleOwnership.assigned_at)==VehicleUpdate.ownership_started_at).exists()
    current_plan=db.query(License.plan).filter(License.tenant_id==user.tenant_id).limit(1).scalar_subquery()
    announcement_target=or_(SystemNotification.target_type=='all',
        and_(SystemNotification.target_type=='user',SystemNotification.target_value==str(user.id)),
        and_(SystemNotification.target_type=='tenant',SystemNotification.target_value==str(user.tenant_id)),
        and_(SystemNotification.target_type=='plan',func.lower(SystemNotification.target_value)==func.lower(current_plan)))
    announcement_active=func.coalesce(and_(SystemNotification.is_active.is_(True),
        or_(SystemNotification.starts_at.is_(None),SystemNotification.starts_at<=now),
        or_(SystemNotification.expires_at.is_(None),SystemNotification.expires_at>now),announcement_target),False)
    scope=or_(and_(Item.kind=='service_event',NotificationOperationalEvent.recipient_id==user.id,user.role=='service'),and_(Item.kind=='admin_message',AdminMessage.recipient_id==user.id,AdminMessage.sender_kind=='admin'),
        and_(Item.kind=='announcement',or_(Item.available_at.isnot(None),announcement_active)),
        and_(Item.kind=='vehicle_update',VehicleUpdate.recipient_id==user.id,owner,
            or_(VehicleUpdateInboxState.folder.is_(None),VehicleUpdateInboxState.folder=='inbox')))
    query=db.query(Item).outerjoin(NotificationOperationalEvent,and_(Item.kind=='service_event',Item.source_id==NotificationOperationalEvent.id)).outerjoin(AdminMessage,and_(Item.kind=='admin_message',Item.source_id==AdminMessage.id)) \
        .outerjoin(SystemNotification,and_(Item.kind=='announcement',Item.source_id==SystemNotification.id)) \
        .outerjoin(AnnouncementPolicy,AnnouncementPolicy.source_id==SystemNotification.id) \
        .outerjoin(VehicleUpdate,and_(Item.kind=='vehicle_update',Item.source_id==VehicleUpdate.id)) \
        .outerjoin(VehicleUpdateReceipt,and_(VehicleUpdateReceipt.update_id==VehicleUpdate.id,VehicleUpdateReceipt.recipient_id==user.id)) \
        .outerjoin(VehicleUpdateInboxState,and_(VehicleUpdateInboxState.update_id==VehicleUpdate.id,VehicleUpdateInboxState.recipient_id==user.id)) \
        .filter(Item.recipient_id==user.id,scope)
    read=case((and_(Item.kind=='announcement',~announcement_active),Item.created_at),(Item.kind=='admin_message',AdminMessage.read_at),(Item.kind=='vehicle_update',VehicleUpdateReceipt.read_at),else_=Item.read_at)
    required=or_(and_(Item.kind=='admin_message',AdminMessage.requires_ack.is_(True),AdminMessage.body_erased.is_(False)),
        and_(Item.kind=='announcement',func.coalesce(Item.snapshot_requires_ack,AnnouncementPolicy.requires_ack,False).is_(True)))
    ack=case((Item.kind=='admin_message',AdminMessage.acknowledged_at),else_=Item.acknowledged_at)
    pending=and_(Item.kind.in_(['admin_message','announcement']),or_(Item.kind!='announcement',announcement_active),
        or_(and_(required,ack.is_(None)),and_(~required,Item.dismissed_at.is_(None),ack.is_(None))))
    return query,read,required,ack,pending

def summary(db,user,rows=None):
    query,read,required,ack,pending=inbox_query(db,user)
    values=query.with_entities(func.coalesce(func.sum(case((read.is_(None),1),else_=0)),0),
        func.coalesce(func.sum(case((pending,1),else_=0)),0),
        func.coalesce(func.sum(case((and_(required,ack.is_(None),pending),1),else_=0)),0)).one()
    return {'unread_count':int(values[0]),'badge_count':int(values[0]),'pending_admin_count':int(values[1]),'pending_ack_count':int(values[2])}

def page(db,user,limit=30,before_id=None,pending_only=False):
    materialize(db,user)
    query,read,required,ack,pending=inbox_query(db,user)
    if before_id is not None:query=query.filter(Item.id<before_id)
    if pending_only:query=query.filter(pending)
    rows=query.order_by(Item.id.desc()).limit(limit+1).all()
    more=len(rows)>limit;rows=rows[:limit]
    result={'items':[item_view(db,item,user) for item in rows],
        'next_before_id':rows[-1].id if more else None,'has_more':more,'summary':summary(db,user)}
    db.commit();return result


def command(db,user,kind,ids,client_id):
    from src.server.admin_messages import lock_recipient
    require_ready(db);lock_recipient(db,user)
    if not active_recipient(user):raise HTTPException(403,'Účet není aktivní.')
    ids=sorted(set(ids));digest=hashlib.sha256(json.dumps([kind,ids]).encode()).hexdigest()
    previous=db.query(Command).filter_by(recipient_id=user.id,client_id=str(client_id)).first()
    if previous and previous.request_hash!=digest:raise HTTPException(409,'Stejný požadavek již byl použit pro jinou akci.')
    items=db.query(Item).filter(Item.recipient_id==user.id,Item.id.in_(ids)).order_by(Item.id).all()
    sources=[source_for(db,i,user) for i in items]
    if len(items)!=len(ids) or any(s is None for s in sources):raise HTTPException(404,'Oznámení není dostupné.')
    if not previous:
        from src.core.rate_limiter import rate_limiter
        if not rate_limiter.check_rate_limit(f'notification-receipts:{user.id}',120,60):raise HTTPException(429,'Příliš mnoho požadavků. Zkuste to za chvíli.')
        now=datetime.utcnow()
        for item,source in zip(items,sources):
            required=requires_ack(db,item,source)
            if kind=='ack' and not required:raise HTTPException(409,'Toto oznámení nevyžaduje potvrzení.')
            if kind=='dismiss' and (required or item.kind=='vehicle_update'):raise HTTPException(409,'Toto oznámení vyžaduje samostatné potvrzení.')
            item.read_at=item.read_at or now
            if kind=='dismiss':item.dismissed_at=item.dismissed_at or now
            if kind=='ack':item.acknowledged_at=item.acknowledged_at or now
            if item.kind=='admin_reply':source.read_at=source.read_at or item.read_at
            if item.kind=='admin_message':
                source.read_at=source.read_at or item.read_at
                if kind=='ack':source.acknowledged_at=source.acknowledged_at or item.acknowledged_at
            if item.kind=='vehicle_update' and not db.get(VehicleUpdateReceipt,(source.id,user.id)):
                db.add(VehicleUpdateReceipt(update_id=source.id,recipient_id=user.id,read_at=item.read_at))
        db.add(Command(recipient_id=user.id,client_id=str(client_id),kind=kind,request_hash=digest,item_ids=json.dumps(ids)))
        db.flush()
    views=[item_view(db,i,user,s) for i,s in zip(items,sources)]
    result={'items':views,'summary':summary(db,user)} if kind=='read' else {'item':views[0],'summary':summary(db,user)}
    db.commit();return result


def collect_new(db,limit=100,fanout_limit=500):
    """Bounded durable source fanout. Atomic cursor + inbox + outbox per batch."""
    from src.server.admin_messages import lock_recipient
    from sqlalchemy import update
    require_ready(db)
    for kind,model in KINDS.items():
        if db.get_bind().dialect.name=='sqlite':
            db.execute(update(NotificationCursor).where(NotificationCursor.kind==kind).values(source_id=NotificationCursor.source_id))
        cursor=db.query(NotificationCursor).filter_by(kind=kind).with_for_update().populate_existing().first()
        if cursor is None:continue # New sources never dispatch until explicit migration initializes their baseline.
        sources=db.query(model).filter(model.id>cursor.source_id).order_by(model.id).limit(limit).all()
        for source in sources:
            more=False
            if kind=='admin_message':
                recipients=[db.get(Customer,source.recipient_id)] if source.sender_kind=='admin' else []
            elif kind in ('vehicle_update','service_event'):recipients=[db.get(Customer,source.recipient_id)]
            elif kind=='admin_reply':recipients=[db.get(Customer,source.addressed_admin_id)] if source.sender_kind=='recipient' and source.addressed_admin_id else []
            else:
                recipients=db.query(Customer).filter(Customer.role.in_(['user','service']),Customer.id>cursor.recipient_cursor).order_by(Customer.id).limit(fanout_limit+1).all()
                more=len(recipients)>fanout_limit;recipients=recipients[:fanout_limit]
            for user in recipients:
                if kind=='announcement':cursor.recipient_cursor=user.id
                if not active_recipient(user):continue
                if active_admin(user) and kind!='admin_reply':continue
                scheduled=kind=='announcement' and source.starts_at and source.starts_at>datetime.utcnow()
                if kind=='announcement' and not scheduled and not announcement_matches(db,source,user):continue
                # For a scheduled plan target, queue candidates now but authorize
                # the actual plan/audience at send time; no body is copied early.
                if scheduled and not source.is_active:continue
                lock_recipient(db,user)
                item=ensure_item(db,user,kind,source)
                if kind=='announcement' or source_for(db,item,user) is not None:
                    ensure_item(db,user,kind,source,queue=source_time(kind,source)>=cursor.rollout_at)
            if more:
                db.commit();return
            cursor.source_id=source.id;cursor.recipient_cursor=0
        db.commit()
