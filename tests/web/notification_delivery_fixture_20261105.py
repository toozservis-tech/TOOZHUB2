"""Loopback-only private-message QA; real routes with isolated synthetic SQLite."""
import os
import json
import time
import base64
from pathlib import Path
from datetime import datetime,timedelta
fixture=Path(os.environ['MESSAGE_QA_DB']).resolve()
os.environ['JWT_SECRET_KEY']='notification-fixture-only-never-production-key-20261105'
os.environ['PUSH_DELIVERY_ENABLED']='false'
from cryptography.fernet import Fernet
os.environ['PUSH_TOKEN_ENCRYPTION_KEY']=Fernet.generate_key().decode()
os.environ['APNS_SANDBOX_KEY_ID']='synthetic-sandbox'
os.environ['APNS_SANDBOX_PRIVATE_KEY']='fixture-no-real-provider-key'
os.environ['APNS_KEY_ID']='synthetic'
os.environ['APNS_TEAM_ID']='synthetic'
os.environ['APNS_PRIVATE_KEY']='fixture-no-real-provider-key'
os.environ['APNS_BUNDLE_IDS']='cz.fixture,cz.toozservis.spravavozidel'
os.environ['FCM_PROJECT_ID']='synthetic-fixture'
os.environ['FCM_SERVICE_ACCOUNT_JSON']='{}'
os.environ['FCM_BUNDLE_IDS']='cz.toozservis.evidencevozidel,cz.fixture,cz.toozservis.spravavozidel.android,cz.toozservis.spravavozidel.android.push.qa.preview'

if fixture.suffix!='.sqlite' or not fixture.parent.name.startswith('admin-messages-qa-') or Path(os.environ['MESSAGE_QA_DB']).is_symlink():
    raise RuntimeError('Use an isolated admin-messages-qa-* directory and a real SQLite file.')
resume=fixture.exists()
if resume and os.environ.get('MESSAGE_QA_RESUME')!='1':raise RuntimeError('Preserve existing evidence: choose a new database or explicitly resume this fixture.')
fixture.parent.mkdir(parents=True,exist_ok=True)
os.environ['DATABASE_URL']='sqlite:///'+str(fixture)
os.environ['DATA_DIR_PATH']=str(fixture.parent)
os.environ['ENVIRONMENT']='test'
os.environ.pop('DATABASE_SCHEMA',None)
from fastapi import FastAPI,Depends,Header,HTTPException,Query
from typing import Literal
from fastapi.responses import FileResponse,PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.modules.vehicle_hub.database import Base,get_db
from src.modules.vehicle_hub.models import Customer,Tenant,SecurityAccessLog,License
from src.modules.vehicle_hub.admin_incident_models import AdminIncident,AdminIncidentHistory
from src.modules.vehicle_hub.email_verification import EmailVerification
from src.modules.vehicle_hub.referrals import TABLES as referral_tables
from src.modules.vehicle_hub.vehicle_transfer_models import VehicleTransferInvitation
from src.core.auth import get_current_user_email
from src.server import admin_api
from src.server.admin_messages import recipient_router,run_command,Send,message_view
from src.modules.vehicle_hub.admin_message_models import AdminMessage,AdminMessageCommand
from src.modules.vehicle_hub.notification_delivery_models import TABLES as notification_tables,AnnouncementPolicy,NotificationItem,PushOutbox
from src.modules.vehicle_hub.routers_v1.notifications import router as notification_router
from src.modules.vehicle_hub.models import SystemNotification,Vehicle,VehicleOwnership
from src.modules.vehicle_hub.vehicle_update_models import VehicleUpdate
from src.core.security import create_access_token
engine=create_engine('sqlite:///'+str(fixture),connect_args={'check_same_thread':False})
Base.metadata.create_all(engine);Session=sessionmaker(bind=engine)
setup={};tokens={}
def encoded(value):return base64.urlsafe_b64encode(json.dumps(value,separators=(',',':')).encode()).decode().rstrip('=')
with Session() as db:
    for group in (() if resume else ('ios','web','android')):
        data={'users':{},'events':{}}
        for role in ('admin','user','service','stranger'):
            tenant=Tenant(name='Synthetic '+group+' '+role,license_key='QA-'+group+'-'+role);db.add(tenant);db.flush()
            user=Customer(email=group+'-'+role+'@example.com',name='Ukázkový '+{'admin':'správce','user':'zákazník','service':'servis','stranger':'jiný účet'}[role],tenant_id=tenant.id,role='user' if role=='stranger' else role,password_hash='unused-fixture');db.add(user);db.flush()
            db.add(License(tenant_id=tenant.id,plan='free',status='active',vehicles_limit=1));db.add(EmailVerification(customer_id=user.id,verified_at=datetime.utcnow()))
            now=int(time.time());jwt=create_access_token({'sub':user.email,'sv':0,'amr':['password','totp'],'admin_verified_until':now+86400},expires_delta=timedelta(days=1),session_id='qa-'+str(user.id))
            token='qa-'+group+'-'+role;tokens[token]=user.id;tokens[jwt]=user.id
            data['users'][role]={'id':user.id,'email':user.email,'role':user.role,'name':user.name,'token':token,'jwt':jwt}
        for key,path,status in [('analytics','/analytics/monthly-costs',403),('server','/api/v1/vehicles/{vehicle_id}',500),('unknown','/api/v1/service-jobs/{job_id}',403),('healthy','/referrals/me',200)]:
            actor=data['users']['user'];event=SecurityAccessLog(customer_id=actor['id'],user_email=actor['email'],event_type='request_failed' if status>=400 else 'request_completed',endpoint=path,
                ip_address='192.0.2.10',created_at=datetime.utcnow()-timedelta(minutes=len(data['events'])),details=json.dumps({'status':status,'app_version':'1.0.7','app_build':'56','client_platform':group,'server_environment':'test','reason':'PRIVATE-FIXTURE-NOT-EXPORT','resource':'VINPRIVATE12345678'}));db.add(event);db.flush();data['events'][key]=event.id
        setup[group]=data
    db.commit()
setup_file=fixture.with_suffix('.setup.json')
if resume:
    with Session() as db:
        if db.query(Customer).count()!=12 or any(not customer.email.endswith('@example.com') for customer in db.query(Customer)):
            raise RuntimeError('Resume only the exact synthetic fixture.')
    if setup_file.exists():setup=json.loads(setup_file.read_text())
    else:
        with Session() as db:
            for group in ('ios','web','android'):
                data={'users':{},'events':{}}
                for role in ('admin','user','service','stranger'):
                    user=db.query(Customer).filter_by(email=group+'-'+role+'@example.com').one()
                    now=int(time.time());jwt=create_access_token({'sub':user.email,'sv':0,'amr':['password','totp'],'admin_verified_until':now+86400},expires_delta=timedelta(days=1),session_id='qa-'+str(user.id))
                    data['users'][role]={'id':user.id,'email':user.email,'role':user.role,'name':user.name,'token':'qa-'+group+'-'+role,'jwt':jwt}
                events=db.query(SecurityAccessLog).filter_by(user_email=group+'-user@example.com').order_by(SecurityAccessLog.id).all()
                data['events']=dict(zip(('analytics','server','unknown','healthy'),[event.id for event in events]))
                setup[group]=data
setup_file.write_text(json.dumps(setup))
for data in setup.values():
    for user in data['users'].values():tokens[user['token']]=user['id'];tokens[user['jwt']]=user['id']
app=FastAPI()
request_log=[]
request_sequence=0
@app.middleware('http')
async def loopback_only(request,call_next):
    if not request.client or request.client.host not in ('127.0.0.1','::1','testclient'):return PlainTextResponse('Loopback QA only',status_code=403)
    global request_sequence
    response=await call_next(request)
    identity=tokens.get(request.headers.get('authorization','').removeprefix('Bearer '))
    principal=next(((group,role) for group,data in setup.items() for role,user in data['users'].items() if user['id']==identity),None)
    if principal and request.url.path.startswith(('/api/v1/','/admin-api/','/user/')):
        request_sequence+=1
        request_log.append({'sequence':request_sequence,'group':principal[0],'role':principal[1],
            'method':request.method,'path':request.url.path,'status':response.status_code})
    return response
def database():
    with Session() as db:yield db
def actor(authorization:str=Header(''),db=Depends(get_db)):
    identity=tokens.get(authorization.removeprefix('Bearer '))
    if not identity:raise HTTPException(401)
    return db.get(Customer,identity)
def email(user=Depends(actor)):return user.email
app.dependency_overrides[get_db]=database
app.dependency_overrides[get_current_user_email]=email
app.include_router(admin_api.router)
app.include_router(recipient_router,prefix="/api/v1")
app.include_router(notification_router,prefix='/api/v1')
from scripts.migrate_notification_delivery import migrate
migrate(engine)
from src.modules.vehicle_hub.routers_v1 import analytics
from src.modules.vehicle_hub.routers_v1.auth import get_current_user
app.dependency_overrides[get_current_user]=actor
app.include_router(analytics.router,prefix='/api/v1')
@app.get('/user/me')
def me(user=Depends(actor)):return {'id':user.id,'email':user.email,'name':user.name,'role':user.role,'tenant_id':user.tenant_id}
@app.get('/user/security/admin-status')
def assurance(user=Depends(actor)):
    if user.role!='admin':raise HTTPException(403)
    return {'required':True,'verified':True,'valid_until':time.time()+3600,'role':user.role}
@app.get('/user/email-verification')
def verified(user=Depends(actor)):return {'required':False,'verified':True}
@app.get('/qa/setup')
def config():return setup
@app.post('/qa/seed-messages')
def seed_messages(group:Literal['ios','web','android']='web',recipient:Literal['user','service']='user',db=Depends(database)):
    from uuid import uuid4
    admin=db.get(Customer,setup[group]['users']['admin']['id']);user=db.get(Customer,setup[group]['users'][recipient]['id'])
    ordinary=run_command(db,admin,user,Send(body='Dobrý den, ověřujeme stav vašeho účtu. Toto je soukromá ukázková zpráva administrace.',requires_ack=False,client_id=uuid4()),'send',admin=True)
    required=run_command(db,admin,user,Send(body='Prosím potvrďte převzetí této zkušební zprávy. Otevření konverzace samo potvrzení nenahrazuje.',requires_ack=True,client_id=uuid4()),'send',admin=True)
    return {'ordinary':ordinary['message'],'required':required['message'],'summary':required['summary']}
@app.post('/qa/seed-message-history')
def seed_message_history(group:Literal['ios','web','android']='web',recipient:Literal['user','service']='user',
        count:int=Query(55,ge=1,le=100),sender:Literal['recipient','admin']='recipient',db=Depends(database)):
    user=db.get(Customer,setup[group]['users'][recipient]['id'])
    sender_id=setup[group]['users']['admin']['id'] if sender=='admin' else user.id
    rows=[]
    for number in range(count):
        row=AdminMessage(recipient_id=user.id,sender_id=sender_id,sender_kind=sender,
            body=f'Historická ukázková zpráva {number+1}: podklad pro ověření stránkování.',requires_ack=False,
            sent_at=datetime.utcnow()-timedelta(days=1,minutes=count-number))
        db.add(row);rows.append(row)
    db.commit()
    return {'ids':[row.id for row in rows],'items':[message_view(db,row) for row in rows],'count':len(rows)}

@app.get('/qa/message-assertions')
def message_assertions(db=Depends(database)):
    return {'messages': [{'id':item.id,'recipient_id':item.recipient_id,'sender_kind':item.sender_kind,'requires_ack':item.requires_ack,
        'read_at':str(item.read_at) if item.read_at else None,'acknowledged_at':str(item.acknowledged_at) if item.acknowledged_at else None} for item in db.query(AdminMessage).all()],
        'command_count':db.query(AdminMessageCommand).count(),'original_events':db.query(SecurityAccessLog).count()}
@app.get('/qa/assertions')
def assertions(db=Depends(database)):
    return {'case_count':db.query(AdminIncident).count(),'history_count':db.query(AdminIncidentHistory).count(),'original_events':db.query(SecurityAccessLog).count(),
            'cases':[{'id':case.id,'status':case.status,'version':case.version,'actor':case.actor_key} for case in db.query(AdminIncident).all()]}
@app.get('/admin-session.js')
def session_script():return FileResponse(Path(__file__).resolve().parents[2]/'src/server/admin_session.js')
@app.get('/web/customer.html')
def product_customer():
    from fastapi.responses import HTMLResponse
    html=(Path(os.environ['NOTIFICATION_QA_WEB_ROOT'])/'index.html').read_text().replace('/admin-session.js','/web/customer-session.js')
    html=html.replace('</head>','<link rel="stylesheet" href="customer.css"><link rel="stylesheet" href="admin-messages.css"></head>')
    html=html.replace('</body>','<script src="vendor/jsQR-1.4.0.js"></script><script src="job-timeline.js"></script><script src="customer-features.js"></script><script src="service-features.js"></script><script src="admin-messages.js"></script></body>')
    return HTMLResponse(html,headers={'Cache-Control':'no-store'})
@app.get('/api/v1/license/status')
def license_status(user=Depends(actor),db=Depends(get_db)):
    from src.modules.licensing.service import get_license_status
    return get_license_status(db,user.tenant_id,user.email)
@app.get('/api/v1/system-notifications')
def notifications(user=Depends(actor)):return {'items':[],'count':0,'total':0,'unread_count':0}
@app.get('/api/v1/vehicles')
@app.get('/api/v1/reminders')
@app.get('/api/v1/reservations')
@app.get('/api/v1/reservations/my')
def empty_records(user=Depends(actor)):return []
@app.post('/qa/plan')
def plan(group:Literal['ios','web','android']='web',plan:Literal['free','basic','premium']='free',db=Depends(get_db)):
    user=db.get(Customer,setup[group]['users']['user']['id']);row=db.query(License).filter_by(tenant_id=user.tenant_id).one()
    row.plan=plan;row.status='active';row.valid_to=None;db.commit();return {'plan':plan}
@app.get('/qa/requests')
def requests(group:Literal['ios','web','android']='web',after:int=Query(0,ge=0)):
    rows=[item for item in request_log if item['group']==group and item['sequence']>after]
    return {'total':len(rows),'last_sequence':request_sequence,'items':rows}
@app.get('/qa/request-counts')
def counts(group:Literal['ios','web','android']='web',after:int=Query(0,ge=0)):
    rows=[item for item in request_log if item['group']==group and item['sequence']>after]
    values={}
    for item in rows:values[item['path']]=values.get(item['path'],0)+1
    return {'total':len(rows),'last_sequence':request_sequence,'counts':values}
app.mount('/web',StaticFiles(directory=Path(os.environ['NOTIFICATION_QA_WEB_ROOT']),html=True),name='web')
app.mount('/web_admin',StaticFiles(directory=Path(__file__).resolve().parents[2]/'web_admin',html=True),name='web_admin')

@app.post('/qa/seed-notification')
def seed_notification(group:Literal['ios','web','android']='web',recipient:Literal['user','service']='user',
        kind:Literal['announcement','admin_message','vehicle_update']='announcement',required:bool=False,
        title:str=Query('Ukázkové oznámení',max_length=120),body:str=Query('Soukromý zkušební obsah pro ověření oznámení.',max_length=4000),db=Depends(database)):
    from uuid import uuid4
    from src.modules.vehicle_hub.notification_inbox import materialize,page,collect_new
    admin=db.get(Customer,setup[group]['users']['admin']['id']);user=db.get(Customer,setup[group]['users'][recipient]['id'])
    if kind=='admin_message':
        source=run_command(db,admin,user,Send(body=body,requires_ack=required,client_id=uuid4()),'send',admin=True)['message']['id']
    elif kind=='announcement':
        row=SystemNotification(target_type='user',target_value=str(user.id),title=title,message=body,is_active=True,created_by_customer_id=admin.id)
        db.add(row);db.flush();source=row.id;db.add(AnnouncementPolicy(source_id=source,requires_ack=required));db.commit()
    else:
        vehicle=Vehicle(tenant_id=user.tenant_id,user_email=user.email,nickname='Ukázkové vozidlo',vin='ZZZ'+uuid4().hex[:14].upper())
        db.add(vehicle);db.flush();owner=VehicleOwnership(vehicle_id=vehicle.id,customer_id=user.id,tenant_id=user.tenant_id,is_active=True,is_primary=True,ownership_type='owner',assigned_at=datetime.utcnow())
        owner.owned_from=owner.assigned_at
        db.add(owner);db.flush()
        row=VehicleUpdate(tenant_id=user.tenant_id,vehicle_id=vehicle.id,recipient_id=user.id,ownership_id=owner.id,ownership_started_at=owner.assigned_at,actor_id=admin.id,event_type='record.created',title=title,message=body,source_type='qa_fixture',source_id=1,dedupe_key=str(uuid4()))
        db.add(row);db.flush();source=row.id;db.commit()
    collect_new(db);materialize(db,user);db.commit()
    item=db.query(NotificationItem).filter_by(recipient_id=user.id,kind=kind,source_id=source).one()
    from src.modules.vehicle_hub.notification_inbox import item_view,summary
    return {'item':item_view(db,item,user),'summary':summary(db,user)}

@app.get('/qa/notification-assertions')
def notification_assertions(group:Literal['ios','web','android']='web',db=Depends(database)):
    ids=[v['id'] for v in setup[group]['users'].values()]
    return {'items':[{'id':i.id,'recipient_id':i.recipient_id,'kind':i.kind,'source_id':i.source_id,'read_at':str(i.read_at) if i.read_at else None,'dismissed_at':str(i.dismissed_at) if i.dismissed_at else None,'acknowledged_at':str(i.acknowledged_at) if i.acknowledged_at else None} for i in db.query(NotificationItem).filter(NotificationItem.recipient_id.in_(ids))],
        'provider_sends':0,'dispatch_enabled':False}

@app.post('/qa/archive-notification')
def archive_notification(identifier:int,group:Literal['ios','web','android']='web',db=Depends(database)):
    ids=[u['id'] for u in setup[group]['users'].values()]
    item=db.get(NotificationItem,identifier)
    if not item or item.recipient_id not in ids or item.kind!='announcement':raise HTTPException(404)
    from src.modules.vehicle_hub.notification_inbox import materialize,item_view,summary
    user=db.get(Customer,item.recipient_id);materialize(db,user)
    row=db.get(SystemNotification,item.source_id);row.expires_at=datetime.utcnow()-timedelta(seconds=1);db.commit()
    return {'item':item_view(db,item,user),'summary':summary(db,user)}
