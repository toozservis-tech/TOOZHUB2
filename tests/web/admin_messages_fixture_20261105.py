"""Loopback-only private-message QA; real routes with isolated synthetic SQLite."""
import os
import json
import time
import base64
from pathlib import Path
from datetime import datetime,timedelta
fixture=Path(os.environ['MESSAGE_QA_DB']).resolve()
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
            now=int(time.time());jwt=encoded({'alg':'HS256','typ':'JWT'})+'.'+encoded({'sub':user.email,'jti':'qa-'+str(user.id),'sv':0,'iat':now,'exp':now+86400,'amr':['password','totp'],'admin_verified_until':now+86400})+'.'+base64.urlsafe_b64encode(b'local-fixture-only-not-production-signature').decode().rstrip('=')
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
                    now=int(time.time());jwt=encoded({'alg':'HS256','typ':'JWT'})+'.'+encoded({'sub':user.email,'jti':'qa-'+str(user.id),'sv':0,'iat':now,'exp':now+86400,'amr':['password','totp'],'admin_verified_until':now+86400})+'.'+base64.urlsafe_b64encode(b'local-fixture-only-not-production-signature').decode().rstrip('=')
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
    from src.server.web_access import customer_web
    return customer_web()
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
app.mount('/web',StaticFiles(directory=Path(__file__).resolve().parents[2]/'web',html=True),name='web')
app.mount('/web_admin',StaticFiles(directory=Path(__file__).resolve().parents[2]/'web_admin',html=True),name='web_admin')
