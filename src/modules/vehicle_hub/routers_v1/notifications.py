from typing import Literal
from uuid import UUID
from fastapi import APIRouter,Depends,Request,Response,Query,HTTPException
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Customer
from ..notification_delivery_models import NotificationItem
from .. import notification_inbox as inbox,push_delivery
from .auth import get_current_user
from src.server.admin_messages import origin_guard,Operation,Read

router=APIRouter(tags=['notification-center'])

def recipient(request:Request,response:Response,user:Customer=Depends(get_current_user)):
    origin_guard(request,response)
    if not inbox.active_recipient(user):raise HTTPException(403,'Oznámení nejsou pro tento účet dostupná.')
    from src.core.security import decode_access_token_payload
    token=request.headers.get('authorization','').removeprefix('Bearer ').strip()
    payload=decode_access_token_payload(token) or {}
    if payload.get('public_demo') or payload.get('demo'):raise HTTPException(403,'Ve zkušebním účtu oznámení nejsou dostupná.')
    return user

@router.get('/notifications/summary')
def get_summary(user=Depends(recipient),db:Session=Depends(get_db)):
    inbox.materialize(db,user);result=inbox.summary(db,user);db.commit();return result

@router.get('/notifications')
def get_inbox(limit:int=Query(30,ge=1,le=100),before_id:int|None=Query(None,ge=1),pending_only:bool=False,user=Depends(recipient),db:Session=Depends(get_db)):
    return inbox.page(db,user,limit,before_id,pending_only)

@router.get('/notifications/{identifier}')
def get_item(identifier:int,user=Depends(recipient),db:Session=Depends(get_db)):
    inbox.require_ready(db)
    item=db.get(NotificationItem,identifier)
    if not item:raise HTTPException(404,'Oznámení není dostupné.')
    return {'item':inbox.item_view(db,item,user),'summary':inbox.summary(db,user)}

@router.post('/notifications/read')
def read_items(body:Read,user=Depends(recipient),db:Session=Depends(get_db)):
    return inbox.command(db,user,'read',body.message_ids,body.client_id)

@router.post('/notifications/{identifier}/dismiss')
def dismiss(identifier:int,body:Operation,user=Depends(recipient),db:Session=Depends(get_db)):
    return inbox.command(db,user,'dismiss',[identifier],body.client_id)

@router.post('/notifications/{identifier}/ack')
def ack(identifier:int,body:Operation,user=Depends(recipient),db:Session=Depends(get_db)):
    return inbox.command(db,user,'ack',[identifier],body.client_id)

class Installation(BaseModel):
    model_config=ConfigDict(extra='forbid')
    installation_id:UUID
    installation_secret:str=Field(min_length=32,max_length=128,pattern=r'^[A-Za-z0-9_\-=]+$')
class Device(Installation):
    platform:Literal['apns','fcm','webpush']
    token:str=Field(min_length=20,max_length=4096)
    permission:Literal['authorized','provisional']
    environment:Literal['production','sandbox']='production'
    bundle_id:str=Field(min_length=1,max_length=160)
    web_keys:dict[str,str]|None=None

@router.get('/push/device-status')
def device_status(user=Depends(recipient)):
    return push_delivery.public_status(user.id)

@router.post('/push/devices')
def register_device(body:Device,request:Request,user=Depends(recipient),db:Session=Depends(get_db)):
    return push_delivery.register(db,user,body,request.headers.get('authorization','').removeprefix('Bearer ').strip())

@router.post('/push/devices/unregister')
def unregister_device(body:Installation,user=Depends(recipient),db:Session=Depends(get_db)):
    return push_delivery.unregister(db,user,body)


@router.get('/service-notification-events/{event_id}')
def service_event(event_id:int,user=Depends(recipient),db:Session=Depends(get_db)):
    from ..operational_notification_models import NotificationOperationalEvent
    from ..operational_notifications import event_context
    inbox.require_ready(db)
    row=db.get(NotificationOperationalEvent,event_id)
    if not row:raise HTTPException(404,'Servisní oznámení není dostupné.')
    return event_context(db,row,user)
