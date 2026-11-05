"""Loopback-only shared client QA. Synthetic data, captured mail, never production mounted."""
import os
import re
import json
import time
import base64
from datetime import datetime
from pathlib import Path
from uuid import uuid4
from fastapi import FastAPI, APIRouter, Depends, Header, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.modules.vehicle_hub.database import Base, get_db
from src.modules.vehicle_hub.models import Tenant, Customer, Vehicle, VehicleOwnership, License
from src.modules.vehicle_hub.email_verification import EmailVerification
from src.modules.vehicle_hub.routers_v1 import vehicle_lifecycle, vehicle_transfers, vehicle_archives, referrals, vehicles
from src.modules.vehicle_hub.routers_v1.auth import get_current_user
from src.modules.vehicle_hub import referrals as referral_domain
from src.modules.email_client.service import EmailService
from src.modules.vehicle_hub.vehicle_duplicates import references
from src.modules.vehicle_hub import booking_request_models  # register lazy extension tables

fixture = Path(os.environ['TRANSFER_QA_DB']).resolve()
if fixture.suffix != '.sqlite' or not fixture.parent.name.startswith('transfer-referral-qa-'):
    raise RuntimeError('QA database must be a local .sqlite inside a dedicated transfer-referral-qa-* directory.')
if Path(os.environ['TRANSFER_QA_DB']).is_symlink():
    raise RuntimeError('QA database cannot be a symlink.')
resume=fixture.exists()
if resume and os.environ.get('TRANSFER_QA_RESUME')!='1': raise RuntimeError('QA database already exists; preserve evidence and use a fresh path or explicit QA resume.')
fixture.parent.mkdir(parents=True,exist_ok=True)
engine=create_engine('sqlite:///'+str(fixture),connect_args={'check_same_thread':False})
# Administrator detail loads additional related models lazily. Register their
# tables before create_all so a fresh fixture has the same complete schema.
list(references())
Base.metadata.create_all(engine)
Session=sessionmaker(bind=engine)
setup={};tokens={};mail_path=fixture.with_suffix('.mail.json');mail=json.loads(mail_path.read_text()) if mail_path.exists() else []
def capture(self,*args,**kwargs):
    if not args or not str(args[0]).endswith('@example.com'):
        raise RuntimeError('QA mail capture accepts synthetic recipients only.')
    mail.append(args);mail_path.write_text(json.dumps(mail));return True
EmailService.send_simple_email=capture
with Session() as db:
    if resume:
        from src.modules.vehicle_hub.models import VehicleOwnershipArchive
        if db.query(Customer).count()!=12:raise RuntimeError('Resume is restricted to this exact synthetic fixture.')
        for prefix in ('','web-','android-'):
            users={role:db.query(Customer).filter_by(email=prefix+role+'@example.com').one() for role in ('seller','buyer','admin','stranger')}
            cars={kind:db.query(Vehicle).filter_by(model='Octavia '+prefix+kind).one().id for kind in ('active','legacy','admin')}
            cars['legacy_archive']=db.query(VehicleOwnershipArchive).filter_by(vehicle_id=cars['legacy']).one().id
            for role,user in users.items():tokens['qa-'+prefix+role]=user.id
            setup[prefix.rstrip('-') or 'ios']={'users':{k:{'id':v.id,'email':v.email,'token':'qa-'+prefix+k} for k,v in users.items()},'vehicles':cars}
with Session() as db:
    prefixes=() if resume else ('','web-','android-')
    for prefix in prefixes:
        users={}
        for role in ('seller','buyer','admin','stranger'):
            tenant=Tenant(name='QA '+prefix+role,license_key='QA-'+prefix+role);db.add(tenant);db.flush()
            user=Customer(tenant_id=tenant.id,email=prefix+role+'@example.com',name='QA '+prefix+role,role='admin' if role=='admin' else 'user',password_hash='unused-fixture')
            db.add(user);db.flush();users[role]=user;tokens['qa-'+prefix+role]=user.id
            db.add(EmailVerification(customer_id=user.id,verified_at=datetime.utcnow()))
            db.add(License(tenant_id=tenant.id,plan='premium',status='active',vehicles_limit=0))
        referral_domain.attach(db,referral_domain.code_for(db,users['seller']),customer=users['buyer'])
        cars={}
        for kind in ('active','legacy','admin'):
            car=Vehicle(tenant_id=users['seller'].tenant_id,user_email=users['seller'].email,vin='TMBQA'+str(len(setup)*10+len(cars)+1).zfill(12),brand='Škoda',model='Octavia '+prefix+kind,plate='QA'+str(len(setup)*10+len(cars)+1),notes='PRIVATE SELLER NOTE')
            db.add(car);db.flush();owned=VehicleOwnership(tenant_id=car.tenant_id,vehicle_id=car.id,customer_id=users['seller'].id,ownership_type='owner',is_primary=True,is_active=True,assigned_by_customer_id=users['seller'].id,assigned_at=datetime.utcnow(),created_at=datetime.utcnow(),updated_at=datetime.utcnow());db.add(owned);db.flush();cars[kind]=car.id
            if kind=='legacy':
                state=vehicle_lifecycle.get_lifecycle(car.id,users['seller'],db)
                result=vehicle_lifecycle.update_lifecycle(car.id,vehicle_lifecycle.VehicleLifecycleAction(client_id=uuid4(),ownership_id=state['ownership_id'],ownership_token=state['ownership_token'],expected_version=state['version'],action='sold',sale={'mode':'outside_app','reason':'dealer'}),users['seller'],db)
                cars['legacy_archive']=result['archive_id']
        setup[prefix.rstrip('-') or 'ios']={'users':{k:{'id':v.id,'email':v.email,'token':'qa-'+prefix+k} for k,v in users.items()},'vehicles':cars}
        db.commit()
# Syntactically valid, explicitly fixture-only JWTs let unchanged client session
# scheduling run. Only this local dependency override recognizes these tokens.
def encoded(value):return base64.urlsafe_b64encode(json.dumps(value,separators=(',',':')).encode()).decode().rstrip('=')
for group in setup.values():
    for user in group['users'].values():
        now=int(time.time());claims={'sub':user['email'],'jti':'qa-'+str(user['id']),'sv':0,'iat':now,'exp':now+86400,'amr':['password']}
        user['jwt']=encoded({'alg':'HS256','typ':'JWT'})+'.'+encoded(claims)+'.'+base64.urlsafe_b64encode(b'local-fixture-only-not-a-production-signature').decode().rstrip('=')
        tokens[user['jwt']]=user['id']
app=FastAPI()
@app.middleware('http')
async def loopback_only(request, call_next):
    if not request.client or request.client.host not in ('127.0.0.1', '::1', 'testclient'):
        return PlainTextResponse('Loopback QA only',status_code=403)
    return await call_next(request)
for router in (vehicle_lifecycle.router,vehicle_transfers.router,vehicle_archives.router,referrals.router,vehicles.router):app.include_router(router,prefix='/api/v1')
def database():
    with Session() as db:yield db
def actor(authorization:str=Header(''),db=Depends(get_db)):
    identity=tokens.get(authorization.removeprefix('Bearer '))
    if not identity:raise HTTPException(401)
    return db.get(Customer,identity)
app.dependency_overrides[get_db]=database
app.dependency_overrides[get_current_user]=actor
from src.server import admin_api
def fixture_admin(user=Depends(actor)):
    if user.role!='admin':raise HTTPException(403)
    return user.email
app.dependency_overrides[admin_api.require_developer_admin]=fixture_admin
selected_admin=APIRouter()
for route in admin_api.router.routes:
    if route.path in ('/admin-api/vehicles','/admin-api/vehicles/{vehicle_id}/detail','/admin-api/users') and 'GET' in route.methods:
        selected_admin.routes.append(route)
app.include_router(selected_admin)
@app.get('/user/me')
def me(user=Depends(actor)):return {'id':user.id,'email':user.email,'name':user.name,'role':user.role}
@app.get('/user/email-verification')
def verification(user=Depends(actor),db=Depends(database)):
    row=db.get(EmailVerification,user.id)
    return {'required':bool(row and not row.verified_at),'verified':bool(row and row.verified_at)}
@app.get('/api/v1/license/status')
def licence(user=Depends(actor),db=Depends(database)):
    from src.modules.licensing.service import get_license_status
    return get_license_status(db,user.tenant_id,user.email)
@app.get('/user/security/admin-status')
def administrator_status(user=Depends(actor)):
    if user.role!='admin':raise HTTPException(403)
    return {'required':True,'verified':True,'valid_until':time.time()+3600,'role':user.role}
@app.get('/web/customer.html',response_class=HTMLResponse)
def product_customer():
    from src.server.web_access import customer_web
    return customer_web()
@app.get('/admin-session.js')
def admin_session():return FileResponse(Path(__file__).resolve().parents[2]/'src/server/admin_session.js')
@app.get('/qa/setup')
def configuration():return setup
@app.get('/qa/mail-code',response_class=PlainTextResponse)
def mail_code(buyer_email:str='buyer@example.com'):
    for entry in reversed(mail):
        if entry[0]==buyer_email:
            found=re.search(r'Jednorázový kód: ([0-9a-f]+)',entry[2])
            if found:return found.group(1)
    raise HTTPException(404)
@app.get('/qa/assertions')
def assertions(group:str='web',db=Depends(database)):
    from src.modules.vehicle_hub.vehicle_transfer_models import VehicleTransferInvitation
    data=setup[group];ids=[data['vehicles'][key] for key in ('active','legacy','admin')]
    rows=db.query(VehicleTransferInvitation).filter(VehicleTransferInvitation.vehicle_id.in_(ids)).all()
    owners=db.query(VehicleOwnership).filter(VehicleOwnership.vehicle_id.in_(ids),VehicleOwnership.is_active==True,VehicleOwnership.is_primary==True).all()
    return {'invitations':[{'id':row.id,'vehicle_id':row.vehicle_id,'status':row.status,'email':row.buyer_email}for row in rows],
        'owners':{str(row.vehicle_id):db.get(Customer,row.customer_id).email for row in owners},'email_count':len(mail)}
@app.get('/qa/client',response_class=HTMLResponse)
def browser_client():return '''<!doctype html><html lang="cs"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="/web/referral-features.css"><title>Syntetické ověření převodu a pozvání</title></head><body>
<h1>Ověření zákaznického webu</h1><label>Účet <select id="account"><option>seller</option><option>buyer</option><option>admin</option><option>stranger</option></select></label>
<button id="manage">Správa aktivního vozidla</button><button id="inbox">Převzetí vozidla</button><button id="legacy">Pozvat z archivu</button><button id="review">Ověřit převod administrátorem</button><button id="referrals">Pozvánky a odměny</button>
<script src="/web/vendor/referral-qr.js"></script><script src="/web/referral-features.js"></script><script src="/web/vehicle-transfers.js"></script><script>
let generation=0,config;const account=document.getElementById('account');
window.AdminBrowserSession={token:()=> 'qa-web-'+account.value,snapshot:()=>({generation}),assertCurrent:s=>{if(s.generation!==generation)throw new DOMException('changed','AbortError');},request:(url,init={},s)=>{if(s)AdminBrowserSession.assertCurrent(s);return fetch(url,{...init,headers:{...(init.headers||{}),Authorization:'Bearer '+AdminBrowserSession.token()}});}};
account.onchange=()=>{generation++;dispatchEvent(new Event('admin-session-ended'));};
fetch('/qa/setup').then(r=>r.json()).then(all=>{config=all.web;document.body.dataset.ready='true';});
document.getElementById('manage').onclick=()=>VehicleTransfers.openManagement(config.vehicles.active);
document.getElementById('inbox').onclick=()=>VehicleTransfers.openInbox();
document.getElementById('legacy').onclick=()=>VehicleTransfers.sendFromArchive(config.vehicles.legacy_archive);
document.getElementById('review').onclick=()=>VehicleTransfers.openAdminReview(config.vehicles.admin);
document.getElementById('referrals').onclick=()=>ReferralFeatures.openPersonal();
</script></body></html>'''
app.mount('/web',StaticFiles(directory=Path(__file__).resolve().parents[2]/'web'),name='web')
app.mount('/web_admin',StaticFiles(directory=Path(__file__).resolve().parents[2]/'web_admin',html=True),name='web_admin')
