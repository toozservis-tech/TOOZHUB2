"""Private two-way support messages. No email/push fanout or third-party sending."""
from __future__ import annotations
import hashlib
import json
from datetime import datetime,timezone
from typing import Optional
from urllib.parse import urlsplit
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query,Request,Response
from pydantic import BaseModel,ConfigDict,Field,field_validator
from sqlalchemy import inspect,func,case,or_,and_,update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from src.core.config import ALLOWED_ORIGINS
from src.core.rate_limiter import rate_limiter
from src.modules.vehicle_hub.database import get_db
from src.modules.vehicle_hub.models import Customer,DeveloperActionAuditLog
from src.modules.vehicle_hub.admin_message_models import AdminMessage as Message,AdminMessageCommand as Command,TABLES
from src.modules.vehicle_hub.routers_v1.auth import get_current_user

ADMIN_ROLES={'admin','developer_admin'}
RECIPIENT_ROLES={'user','service'}


def stamp(value):return value.replace(tzinfo=timezone.utc).isoformat() if value else None


def ready(db):return all(inspect(db.connection()).has_table(table.name) for table in TABLES)


def require_ready(db):
    if not ready(db):raise HTTPException(503,'Soukromé zprávy čekají na aktualizaci serveru. Zkuste to prosím později.')


def origin_guard(request,response):
    response.headers['Cache-Control']='no-store';response.headers['Pragma']='no-cache'
    if request.method in {'POST','PUT','PATCH','DELETE'}:
        origin=request.headers.get('origin')
        if request.headers.get('sec-fetch-site')=='cross-site':raise HTTPException(403,'Požadavek z jiného webu není povolen.')
        if origin:
            incoming=urlsplit(origin);own=urlsplit(str(request.base_url))
            allowed={(own.scheme,own.netloc)}|{(urlsplit(v).scheme,urlsplit(v).netloc) for v in ALLOWED_ORIGINS if v!='*'}
            if origin=='null' or incoming.path not in ('','/') or (incoming.scheme,incoming.netloc) not in allowed:
                raise HTTPException(403,'Požadavek musí pocházet z této aplikace.')


def target(db,customer_id):
    recipient=db.get(Customer,customer_id)
    if not recipient:raise HTTPException(404,'Účet nenalezen.')
    if recipient.role not in RECIPIENT_ROLES:raise HTTPException(422,'Příjemcem může být zákazník nebo servis.')
    return recipient


def recipient_view(recipient):
    return {'id':recipient.id,'name':recipient.name,'email':recipient.email,'role':recipient.role,
            'active':not(recipient.is_deleted or recipient.is_disabled)}


def summary(db,recipient_id,*,admin=False):
    incoming_admin=and_(Message.sender_kind=='recipient',Message.read_at.is_(None))
    incoming_recipient=and_(Message.sender_kind=='admin',Message.read_at.is_(None))
    pending=and_(Message.sender_kind=='admin',Message.requires_ack.is_(True),Message.acknowledged_at.is_(None))
    counts=db.query(func.coalesce(func.sum(case((incoming_admin,1),else_=0)),0),
        func.coalesce(func.sum(case((incoming_recipient,1),else_=0)),0),
        func.coalesce(func.sum(case((pending,1),else_=0)),0),
        func.coalesce(func.sum(case((or_(incoming_recipient,pending),1),else_=0)),0),
        func.max(Message.id)).filter(Message.recipient_id==recipient_id).one()
    return {'unread_count':int(counts[0] if admin else counts[1]),'unread_admin_count':int(counts[0]),
        'unread_recipient_count':int(counts[1]),'pending_ack_count':int(counts[2]),
        'banner_count':int(counts[0] if admin else counts[3]),'last_message_id':counts[4]}


def message_view(db,message,*,admin=False):
    result={'id':message.id,'sender_kind':message.sender_kind,'body':message.body,'body_erased':message.body_erased,
        'requires_ack':message.requires_ack,'sent_at':stamp(message.sent_at),'read_at':stamp(message.read_at),
        'acknowledged_at':stamp(message.acknowledged_at),
        'sender_label':'Správce aplikace' if message.sender_kind=='admin' else 'Vy'}
    if admin:
        actor=db.get(Customer,message.sender_id) if message.sender_id else None
        result['sender_name']=actor.name or actor.email if actor else 'Odstraněný účet'
        result['sender_label']='Administrace' if message.sender_kind=='admin' else result['sender_name']
    return result


def history(db,recipient,limit,before_id,*,admin=False,pending_only=False):
    require_ready(db)
    query=db.query(Message).filter_by(recipient_id=recipient.id)
    if pending_only:
        query=query.filter(Message.sender_kind=='admin',or_(Message.read_at.is_(None),and_(Message.requires_ack.is_(True),Message.acknowledged_at.is_(None))))
    if before_id:query=query.filter(Message.id<before_id)
    rows=query.order_by(Message.id.desc()).limit(limit+1).all()
    more=len(rows)>limit;rows=rows[:limit]
    return {'recipient':recipient_view(recipient),'pending_only':pending_only,'items':[message_view(db,item,admin=admin) for item in reversed(rows)],
        'has_more':more,'next_before_id':rows[-1].id if more and rows else None,
        'summary':summary(db,recipient.id,admin=admin)}


class Operation(BaseModel):
    model_config=ConfigDict(extra='forbid')
    client_id:UUID


class Reply(Operation):
    body:str=Field(min_length=1,max_length=4000)
    @field_validator('body')
    @classmethod
    def clean_body(cls,value):
        value=value.strip()
        if not value:raise ValueError('Napište zprávu.')
        if any(ord(c)<32 and c not in '\n\t' for c in value):raise ValueError('Zpráva obsahuje nepovolené znaky.')
        return value


class Send(Reply):
    requires_ack:bool=False


class Read(Operation):
    message_ids:list[int]=Field(min_length=1,max_length=100)
    @field_validator('message_ids',mode='before')
    @classmethod
    def clean_ids(cls,value):
        if not isinstance(value,list) or not 1 <= len(value) <= 100 or any(type(v) is not int or v<1 for v in value):raise ValueError('Vyberte platné zprávy.')
        return sorted(set(value))


def lock_recipient(db,recipient):
    # Serialize a single conversation even on SQLite where FOR UPDATE is a no-op.
    if db.get_bind().dialect.name=='sqlite':
        db.execute(update(Customer).where(Customer.id==recipient.id).values(id=Customer.id),execution_options={'synchronize_session':False})
        db.expire(recipient);db.refresh(recipient)
    else:
        db.query(Customer).filter_by(id=recipient.id).with_for_update().populate_existing().one()


def audit_admin(db,actor,recipient,kind,message_id=None,count=None):
    if actor.role not in ADMIN_ROLES:return
    db.add(DeveloperActionAuditLog(developer_id=actor.id,developer_email=actor.email,
        action_type='admin_message.'+kind,target_resource=f'conversation:{recipient.id}',
        parameters_json=json.dumps({'message_id':message_id,'count':count}),result='success',status_code=200))


def response_for(db,command,*,admin):
    result={'summary':summary(db,command.recipient_id,admin=admin)}
    if command.kind=='read':
        result['updated_count']=command.result_count
        ids=json.loads(command.message_ids_json or '[]')
        result['items']=[message_view(db,item,admin=admin) for item in db.query(Message).filter(
            Message.recipient_id==command.recipient_id,Message.id.in_(ids)).order_by(Message.id)]
    else:
        message=db.get(Message,command.message_id)
        if not message:raise HTTPException(409,'Zpráva již není dostupná.')
        result['message']=message_view(db,message,admin=admin)
    return result


def run_command(db,actor,recipient,body,kind,*,admin=False,message_id=None):
    require_ready(db);lock_recipient(db,recipient)
    if recipient.role not in RECIPIENT_ROLES:raise HTTPException(409,'Role příjemce se změnila. Obnovte účet.')
    if not admin or kind=='send':
        if recipient.is_disabled or recipient.is_deleted:raise HTTPException(409,'Účet příjemce není aktivní.')
    payload={'kind':kind,'recipient_id':recipient.id,'message_id':message_id,**body.model_dump(mode='json')}
    digest=hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    previous=db.query(Command).filter_by(actor_id=actor.id,client_id=str(body.client_id)).first()
    if previous:
        if previous.request_hash!=digest:raise HTTPException(409,'Identifikátor již patří jinému požadavku. Obnovte konverzaci.')
        return response_for(db,previous,admin=admin)
    now=datetime.utcnow();count=0;result_message=None
    if kind in ('send','reply'):
        if not rate_limiter.check_rate_limit(f'private-message:{actor.id}',120 if admin else 20,60):
            raise HTTPException(429,'Odesíláte příliš mnoho zpráv. Počkejte prosím chvíli.')
        result_message=Message(recipient_id=recipient.id,sender_id=actor.id,sender_kind='admin' if admin else 'recipient',
            body=body.body,requires_ack=body.requires_ack if admin else False,sent_at=now)
        db.add(result_message);db.flush();count=1
    elif kind=='read':
        rows=db.query(Message).filter(Message.id.in_(body.message_ids),Message.recipient_id==recipient.id,
            Message.sender_kind==('recipient' if admin else 'admin')).all()
        if len(rows)!=len(body.message_ids):raise HTTPException(403,'Lze označit pouze přijaté zprávy v této konverzaci.')
        for row in rows:
            if row.read_at is None:row.read_at=now;count+=1
    elif kind=='ack':
        result_message=db.query(Message).filter_by(id=message_id,recipient_id=recipient.id,sender_kind='admin',requires_ack=True).first()
        if not result_message:raise HTTPException(403,'Tuto zprávu nelze tímto účtem potvrdit.')
        if result_message.acknowledged_at is None:
            result_message.acknowledged_at=now;result_message.read_at=result_message.read_at or now;count=1
    command=Command(actor_id=actor.id,recipient_id=recipient.id,client_id=str(body.client_id),kind=kind,request_hash=digest,
        message_id=result_message.id if result_message else None,result_count=count,
        message_ids_json=json.dumps(body.message_ids) if kind=='read' else None)
    db.add(command);audit_admin(db,actor,recipient,kind,result_message.id if result_message else None,count)
    try:db.commit()
    except IntegrityError:
        db.rollback();previous=db.query(Command).filter_by(actor_id=actor.id,client_id=str(body.client_id)).first()
        if previous and previous.request_hash==digest:return response_for(db,previous,admin=admin)
        raise HTTPException(409,'Současně vznikl jiný požadavek. Obnovte konverzaci.')
    return response_for(db,command,admin=admin)


def create_admin_router(admin_dependency):
    router=APIRouter(prefix='/control-center/messages',tags=['admin-messages'])
    def context(request:Request,response:Response,email=Depends(admin_dependency),db:Session=Depends(get_db)):
        origin_guard(request,response)
        actor=db.query(Customer).filter(func.lower(Customer.email)==str(email).lower()).first()
        if not actor or actor.role not in ADMIN_ROLES or actor.is_deleted or actor.is_disabled:raise HTTPException(403,'Přístup pouze pro aktivního administrátora.')
        return actor

    @router.get('')
    def inbox(search:str=Query('',max_length=120),unread_only:bool=False,limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0),actor=Depends(context),db:Session=Depends(get_db)):
        require_ready(db)
        stats=db.query(Message.recipient_id.label('recipient_id'),func.max(Message.id).label('last_id'),
            func.sum(case((and_(Message.sender_kind=='recipient',Message.read_at.is_(None)),1),else_=0)).label('unread_admin'),
            func.sum(case((and_(Message.sender_kind=='admin',Message.read_at.is_(None)),1),else_=0)).label('unread_recipient'),
            func.sum(case((and_(Message.sender_kind=='admin',Message.requires_ack.is_(True),Message.acknowledged_at.is_(None)),1),else_=0)).label('pending_ack')).group_by(Message.recipient_id).subquery()
        query=db.query(Customer,Message,stats.c.unread_admin,stats.c.unread_recipient,stats.c.pending_ack).join(stats,stats.c.recipient_id==Customer.id).join(Message,Message.id==stats.c.last_id).filter(Customer.role.in_(RECIPIENT_ROLES))
        if unread_only:query=query.filter(stats.c.unread_admin>0)
        if search.strip():
            term='%'+search.strip().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
            query=query.filter(or_(Customer.email.ilike(term,escape='\\'),Customer.name.ilike(term,escape='\\')))
        return {'total':query.count(),'items':[{'recipient':recipient_view(recipient),'last_message':message_view(db,message,admin=True),
            'unread_admin_count':ua,'unread_recipient_count':ur,'pending_ack_count':pending,'updated_at':stamp(message.sent_at)}
            for recipient,message,ua,ur,pending in query.order_by(Message.id.desc()).offset(offset).limit(limit)]}

    @router.get('/accounts/{customer_id}')
    def conversation(customer_id:int,limit:int=Query(50,ge=1,le=100),before_id:Optional[int]=Query(None,gt=0),actor=Depends(context),db:Session=Depends(get_db)):
        return history(db,target(db,customer_id),limit,before_id,admin=True)

    @router.post('/accounts/{customer_id}')
    def send(customer_id:int,body:Send,actor=Depends(context),db:Session=Depends(get_db)):
        return run_command(db,actor,target(db,customer_id),body,'send',admin=True)

    @router.post('/accounts/{customer_id}/read')
    def read(customer_id:int,body:Read,actor=Depends(context),db:Session=Depends(get_db)):
        return run_command(db,actor,target(db,customer_id),body,'read',admin=True)
    return router


recipient_router=APIRouter(prefix='/admin-messages',tags=['private-admin-messages'])

def recipient_context(request:Request,response:Response,user=Depends(get_current_user)):
    origin_guard(request,response)
    if user.role not in RECIPIENT_ROLES or user.is_deleted or user.is_disabled:raise HTTPException(403,'Zprávy jsou dostupné pouze aktivnímu zákazníkovi nebo servisu.')
    return user


@recipient_router.get('/summary')
def own_summary(user=Depends(recipient_context),db:Session=Depends(get_db)):
    require_ready(db);return summary(db,user.id)


@recipient_router.get('')
def own_history(limit:int=Query(50,ge=1,le=100),before_id:Optional[int]=Query(None,gt=0),pending_only:bool=False,user=Depends(recipient_context),db:Session=Depends(get_db)):
    return history(db,user,limit,before_id,pending_only=pending_only)


@recipient_router.post('')
def reply(body:Reply,user=Depends(recipient_context),db:Session=Depends(get_db)):
    return run_command(db,user,user,body,'reply')


@recipient_router.post('/read')
def read_own(body:Read,user=Depends(recipient_context),db:Session=Depends(get_db)):
    return run_command(db,user,user,body,'read')


@recipient_router.post('/{message_id}/ack')
def ack(message_id:int,body:Operation,user=Depends(recipient_context),db:Session=Depends(get_db)):
    return run_command(db,user,user,body,'ack',message_id=message_id)
