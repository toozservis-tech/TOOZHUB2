"""Admin-only support workflow; no impersonation, payment changes or automatic AI calls."""
from __future__ import annotations
import hashlib
import json
import re
from datetime import datetime, timezone, timedelta
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import inspect, func, or_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from src.modules.vehicle_hub.database import get_db
from src.modules.vehicle_hub.models import Customer, SecurityAccessLog, DeveloperActionAuditLog, License
from src.modules.vehicle_hub.admin_incident_models import AdminIncident as Case, AdminIncidentEvent as Link, AdminIncidentHistory as History, TABLES
from src.server.security_tracking import access_event_view
from src.core.config import ALLOWED_ORIGINS

PROBLEMS = {'login_failed','login_rate_limited','blocked_ip','login_blocked_ip','request_failed'}
ACTIVE = ('open', 'in_progress')
Status = Literal['open','in_progress','resolved','dismissed']
# Only known route vocabulary survives export. All identifiers/unknown segments are redacted.
ROUTE_WORDS = set('api v1 v2 admin-api control-center analytics summary monthly-costs categories category-breakdown vehicles vehicle records attachments download users user me login register security admin-status license licensing status subscriptions subscription referrals transfer transfers transfer-invitations vehicle-transfers invitations lifecycle ownership archives history access-history access-accounts health settings service services jobs service-jobs clients documents reservations reminders notifications payments profile incidents from-event transition notes check diagnostic public-demo request verify auth session renew activity costs'.split())


def stamp(value):
    return value.replace(tzinfo=timezone.utc).isoformat() if value else None


def safe_endpoint(value):
    raw = str(value or '').split('?',1)[0].split('#',1)[0]
    if not raw.startswith('/') or raw.startswith('//'):
        return '/{redacted}'
    return '/' + '/'.join(part if part in ROUTE_WORDS else '{id}' if part.isdigit() or re.fullmatch(r'\{[a-z_]+\}',part) else '{redacted}' for part in raw.strip('/').split('/')[:12])


def raw_details(event):
    try:
        data = json.loads(event.details or '{}')
        return data if isinstance(data,dict) else {}
    except (ValueError,TypeError):
        return {}


def http_status(event):
    value = str(raw_details(event).get('status',''))
    return int(value) if value.isdigit() and 100 <= int(value) <= 599 else None


def actor_key(event):
    return (event.user_email or '').strip().lower() or ('IP: '+(event.ip_address or 'nezjištěna'))


def fingerprint(event):
    # Internal only; never export this actor-dependent digest.
    parts = [actor_key(event), event.event_type, str(event.endpoint or '').split('?',1)[0],
             str(raw_details(event).get('resource','')), http_status(event)]
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()


def ready(db):
    schema = inspect(db.connection())
    return all(schema.has_table(table.name) for table in TABLES)


def require_ready(db):
    if not ready(db):
        raise HTTPException(503, 'Řešení problémů čeká na aktualizaci serveru. Původní historie je zachovaná.')


def event_view(event):
    return {'id':event.id,'user_email':event.user_email,'event_type':event.event_type,
            'endpoint':event.endpoint,'created_at':stamp(event.created_at), **access_event_view(event)}


def source(db, case):
    event=db.get(SecurityAccessLog,case.source_event_id)
    if not event: raise HTTPException(409,'Původní událost chybí. Historii musí prověřit správce serveru.')
    return event


def current_customer(db,case):
    if case.customer_id: return db.get(Customer,case.customer_id)
    return db.query(Customer).filter(func.lower(Customer.email)==case.actor_key.lower()).first()


def check_case(db,case):
    """Strict SELECT-only diagnostics, including unconsumed rewards (no grant/refresh helpers)."""
    event=source(db,case); status=http_status(event); endpoint=safe_endpoint(event.endpoint)
    customer=current_customer(db,case)
    checks=[]; actions=[]
    def check(code,label,state,detail):checks.append({'code':code,'label':label,'state':state,'detail':detail,'message':detail})
    def action(code,label,target):actions.append({'code':code,'label':label,'target':target})
    restricted=None
    if customer:
        disabled=bool(customer.is_deleted or customer.is_disabled)
        check('account','Stav účtu','warning' if disabled else 'success','Účet je neaktivní.' if disabled else 'Účet je aktivní.')
        check('role','Role účtu','success',{'user':'Zákazník','service':'Servis','admin':'Administrátor','developer_admin':'Administrátor'}.get(customer.role,'Neznámá role'))
        license=db.query(License).filter_by(tenant_id=customer.tenant_id).first()
        now=datetime.utcnow(); plan=license.plan if license else 'free'
        active=license is None or license.status=='active' and (license.valid_to is None or license.valid_to>now)
        # Read already-active grants, never schedule waiting rewards or mint new ones.
        from src.modules.vehicle_hub.referrals import ReferralReward
        if inspect(db.connection()).has_table(ReferralReward.__tablename__):
            reward=db.query(ReferralReward.id).filter(ReferralReward.customer_id==customer.id,
                ReferralReward.revoked_at.is_(None),ReferralReward.waiting_for_paid.is_(False),
                ReferralReward.starts_at<=now,or_(ReferralReward.ends_at.is_(None),ReferralReward.ends_at>now)).first()
            if reward and (license is None or license.status=='active'): plan='premium';active=True
        privileged=customer.role in {'admin','developer_admin','service'}
        restricted=not privileged and not (active and plan=='premium')
        check('license','Aktuální tarif','warning' if not active else 'success',
              ('Tarif '+{'free':'Zdarma','basic':'Basic','premium':'Premium'}.get(plan,'neznámý'))+(' je aktivní.' if active else ' není aktivní.')+(' Role servisu nebo správce se řídí vlastními oprávněními.' if privileged else ''))
        if endpoint.startswith('/analytics/') or endpoint.startswith('/api/v1/analytics/'):
            check('analytics','Přístup k analytice nyní','warning' if restricted else 'success',
                  'Současný zákaznický tarif analytiku neobsahuje. Historický důvod chyby z toho nelze potvrdit.' if restricted else 'Současná role nebo tarif analytiku umožňuje; starší chybu je potřeba prověřit samostatně.')
            action('review_license','Zkontrolovat tarif a oprávnění','licenses')
        if 'transfer' in (event.endpoint or '') or 'lifecycle' in (event.endpoint or '') or '/vehicles' in endpoint:
            from src.modules.vehicle_hub.vehicle_transfer_models import VehicleTransferInvitation
            if inspect(db.connection()).has_table(VehicleTransferInvitation.__tablename__):
                pending=db.query(VehicleTransferInvitation).filter(VehicleTransferInvitation.status=='pending',or_(VehicleTransferInvitation.seller_id==customer.id,func.lower(VehicleTransferInvitation.buyer_email)==customer.email.lower())).count()
                check('transfers','Čekající převody','warning' if pending else 'success',f'Čekajících převodů tohoto účtu: {pending}. Převod vyžaduje souhlas příjemce; kontrola jej neprovádí.')
                action('review_transfer','Otevřít převody vozidel','transfers')
        if 'referral' in (event.endpoint or ''):
            from src.modules.vehicle_hub.referrals import Referral
            if inspect(db.connection()).has_table(Referral.__tablename__):
                total=db.query(Referral).filter_by(referrer_id=customer.id).count()
                qualified=db.query(Referral).filter_by(referrer_id=customer.id).filter(Referral.qualified_at.isnot(None)).count()
                check('referrals','Pozvánky a odměny','success',f'Pozvaných účtů: {total}; splněné podmínky: {qualified}. Kontrola nepřipisuje odměny.')
                action('review_referrals','Otevřít pozvánky a odměny','referrals')
        action('review_account','Otevřít účet','accounts')
    else:
        check('account','Účet','unknown','K události není nalezený účet. Může jít o pokus o přihlášení před registrací.')
    reason=raw_details(event).get('error_code') or raw_details(event).get('reason')
    if status==403 and reason in {'FEATURE_DISABLED','LICENSE_INACTIVE','LICENSE_EXPIRED','subscription_required'}:
        code='known_subscription_restriction'; title='Zaznamenané omezení tarifu'
        explanation='Událost obsahuje kód omezení tarifu. Samotné odmítnutí chrání přístup; prověřte, zda aplikace nezobrazuje zamčenou funkci jako chybu.'
    elif status==403 and restricted and '/analytics/' in endpoint:
        code='current_restriction_possible';title='Možné omezení tarifu'
        explanation='Dnes účet nemá přístup k analytice. U původní události není doložen důvod HTTP 403. Nejde o potvrzenou diagnózu ani opravu.'
    elif status==403:
        code='access_denied_unexplained';title='Odepřený přístup k prověření'
        explanation='HTTP 403 sám neříká, zda jde o roli, tarif, souhlas majitele nebo chybu aplikace. Ověřte konkrétní krok a jeho oprávnění.'
    elif status==401:
        code='authentication_required';title='Přihlášení k prověření';explanation='Server odmítl ověření přihlášení. Prověřte opakování po novém přihlášení; heslo ani kód nevyžadujte do diagnostiky.'
    elif status and status>=500:
        code='server_error';title='Chyba serveru';explanation='Server nedokončil požadavek. Předejte anonymizovanou diagnostiku k opravě a poté ověřte stejný krok.'
    elif event.event_type!='request_failed':
        code='security_event';title='Bezpečnostní událost';explanation='Událost zaznamenává neúspěšný nebo omezený přístup. Ověřte očekávané chování bez odstraňování historie.'
    else:
        code='request_rejected';title='Požadavek k prověření';explanation='Záznam neobsahuje dost důkazů pro automatickou opravu. Doplňte postup reprodukce a bezpečnou diagnostiku.'
    action('reproduce','Ověřit původní krok a zapsat výsledek','activity')
    action('export_diagnostic','Připravit diagnostiku pro podporu','diagnostic')
    return {'checked_at':stamp(datetime.utcnow()),'diagnosis':{'code':code,'title':title,'explanation':explanation,'suggested_actions':actions},'checks':checks}


def incident_title(event):
    endpoint=safe_endpoint(event.endpoint)
    path=endpoint.removeprefix('/api/v1')
    known={'/analytics/monthly-costs':'Měsíční náklady','/analytics/summary':'Statistiky',
           '/analytics/categories':'Rozdělení nákladů','/admin-api/control-center/health':'Dostupnost služeb',
           '/user/login':'Přihlášení','/license/status':'Tarif a předplatné'}
    area=known.get(path)
    if not area:
        for prefix,label in (('/vehicles','Vozidlo'),('/vehicle-transfers','Převod vozidla'),
                ('/referrals','Pozvánky a odměny'),('/service-jobs','Servisní zakázka'),
                ('/reservations','Rezervace'),('/reminders','Připomínky'),('/license','Tarif a předplatné')):
            if path==prefix or path.startswith(prefix+'/'):area=label;break
    area=area or 'Požadavek aplikace'
    status=http_status(event)
    if status==403:result='Odepřený přístup'
    elif status==401:result='Vyžadované přihlášení'
    elif status and status>=500:result='Chyba serveru'
    elif event.event_type in ('login_failed','login_rate_limited','login_blocked_ip','blocked_ip'):result='Neúspěšné nebo omezené přihlášení'
    else:result='Požadavek k prověření'
    return result+' · '+area


def row(db,case,*,detail=False):
    event=source(db,case);customer=current_customer(db,case)
    result={'id':case.id,'source_event_id':case.source_event_id,'status':case.status,'version':case.version,
        'title':incident_title(event),
        'actor':{'customer_id':customer.id if customer else None,'name':customer.name if customer else None,'email':customer.email if customer else event.user_email,'role':customer.role if customer else None},
        'created_at':stamp(case.created_at),'updated_at':stamp(case.updated_at),
        'recurrence_count':db.query(Link).filter_by(incident_id=case.id).count()}
    result['linked_event_count']=result['recurrence_count']
    result['grouping_explanation']='Spojujeme stejný účet, operaci, zdroj a výsledek. Jde o ručně připojené výskyty, nikoli počet všech historických chyb.'
    if detail:
        result['events']=[event_view(item) for item in db.query(SecurityAccessLog).join(Link,Link.event_id==SecurityAccessLog.id).filter(Link.incident_id==case.id).order_by(SecurityAccessLog.created_at.desc(),SecurityAccessLog.id.desc()).limit(200)]
        result['events_truncated']=result['recurrence_count']>200
        result['history']=[{'id':item.id,'action':item.action,'status':item.status,'note':item.note,'version':item.version,'created_at':stamp(item.created_at),'admin_email':admin_email} for item,admin_email in db.query(History,Customer.email).outerjoin(Customer,Customer.id==History.admin_id).filter(History.incident_id==case.id).order_by(History.id.desc()).limit(200)]
        result['history_total']=db.query(History).filter_by(incident_id=case.id).count()
        result['history_truncated']=result['history_total']>len(result['history'])
        result.update(check_case(db,case))
    return result


def audit(db,case,admin,action):
    db.add(DeveloperActionAuditLog(developer_id=admin.id,developer_email=admin.email,
        action_type='incident.'+action,target_resource=f'incident:{case.id}',
        parameters_json=json.dumps({'status':case.status,'version':case.version}),result='success',status_code=200))


def require_case(db,case_id):
    require_ready(db);case=db.get(Case,case_id)
    if not case: raise HTTPException(404,'Problém nenalezen.')
    return case


class Command(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_version:int=Field(ge=1)
    client_id:UUID
    note:str=Field(default='',max_length=2000)
    @field_validator('note')
    @classmethod
    def clean_note(cls,value):
        value=value.strip()
        if any(ord(c)<32 and c not in '\n\t' for c in value):raise ValueError('Poznámka obsahuje nepovolené znaky.')
        return value


class Transition(Command):
    status:Status


class Note(Command):
    note:str=Field(min_length=3,max_length=2000)


def apply_command(db,case,admin,body,action):
    payload=body.model_dump(mode='json');digest=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()
    previous=db.query(History).filter_by(incident_id=case.id,admin_id=admin.id,client_id=str(body.client_id)).first()
    if previous:
        if previous.request_hash!=digest:raise HTTPException(409,'Tento identifikátor již patří jinému požadavku.')
        return row(db,case,detail=True)
    if case.version!=body.expected_version:raise HTTPException(409,'Problém mezitím upravil jiný správce. Obnovte detail a zkontrolujte aktuální stav.')
    new_status=body.status if action=='transition' else case.status
    reopening=case.status not in ACTIVE and new_status in ACTIVE
    if action=='transition':
        if new_status==case.status:raise HTTPException(422,'Problém již má tento stav. Pro komentář použijte poznámku.')
        allowed=({'open','in_progress','resolved','dismissed'} if case.status in ACTIVE else {'open'})
        if new_status not in allowed:raise HTTPException(422,'Uzavřený problém nejprve znovu otevřete.')
    if (action=='note' or new_status in ('resolved','dismissed') or reopening) and len(body.note)<3:
        raise HTTPException(422,'Zapište důvod nebo výsledek ověření (nejméně 3 znaky).')
    values={'status':new_status,'version':case.version+1,'updated_at':datetime.utcnow(),
            'active_fingerprint':case.fingerprint if new_status in ACTIVE else None}
    changed=db.execute(update(Case).where(Case.id==case.id,Case.version==body.expected_version).values(**values),execution_options={'synchronize_session':False})
    if changed.rowcount!=1:db.rollback();raise HTTPException(409,'Problém mezitím změnil jiný správce. Obnovte detail.')
    db.expire(case);db.refresh(case)
    db.add(History(incident_id=case.id,admin_id=admin.id,action='reopen' if reopening else action,status=case.status,
        note=body.note,client_id=str(body.client_id),request_hash=digest,version=case.version))
    audit(db,case,admin,'reopen' if reopening else action)
    db.commit()
    return row(db,case,detail=True)


def enrich_events(db,items):
    """Optional additive fields; original counts/severity deliberately stay historical."""
    if not items or not ready(db):return items
    links={event_id:case for event_id,case in db.query(Link.event_id,Case).join(Case,Case.id==Link.incident_id).filter(Link.event_id.in_([i['id'] for i in items])).all()}
    for item in items:
        item['can_create_incident']=item.get('event_type') in PROBLEMS
        case=links.get(item['id'])
        item['incident']={'id':case.id,'status':case.status,'version':case.version} if case else None
    return items


def diagnostic(db,case):
    event=source(db,case);meta=raw_details(event)
    def match(key,pattern):
        val=str(meta.get(key,''));return val if re.fullmatch(pattern,val) else 'neuvedeno'
    platform=meta.get('client_platform');platform=platform if platform in ('ios','android','web','macos','iOS','Android') else 'neuvedeno'
    environment=meta.get('server_environment');environment=environment if environment in ('production','sandbox','test','development') else 'neuvedeno'
    # Never interpolate names, email, IP, notes, resource, request IDs, raw reason or UA.
    lines=['Evidence Vozidel — anonymizovaná diagnostika',f'Případ: #{case.id}',f'Stav řešení: {case.status} (verze {case.version})',
           f'Původní událost: #{event.id}',f'Čas UTC: {stamp(event.created_at)}',
           f'Platforma: {platform}',f'Verze aplikace: {match("app_version",r"[0-9]{1,3}(?:\.[0-9]{1,3}){1,3}")}',
           f'Sestavení: {match("app_build",r"[0-9]{1,8}")}',f'Prostředí: {environment}',
           f'Systém: {match("app_os",r"(?:iOS|iPadOS|Android|macOS|Windows|Linux) [0-9]{1,3}(?:\.[0-9]{1,3}){0,3}")}',
           f'Operace: {safe_endpoint(event.endpoint)}',f'HTTP výsledek: {http_status(event) or "neuvedeno"}',
           f'Připojených výskytů: {db.query(Link).filter_by(incident_id=case.id).count()}',
           'Požadavek: prověřte příčinu, navrhněte opravu a konkrétní ověření. Uzavření případu samo chybu neopravuje.',
           'Export neobsahuje identitu účtu, IP, VIN, obsah dokumentů, soukromé poznámky ani přístupové a platební údaje.',
           'Před sdílením zkontrolujte náhled. Původní události zůstávají uložené v administraci.']
    from src.server.client_activity import UI_ACTIONS
    prior=db.query(SecurityAccessLog).filter(SecurityAccessLog.user_email==event.user_email,
        SecurityAccessLog.id<=event.id,SecurityAccessLog.created_at<=event.created_at,
        SecurityAccessLog.created_at>=event.created_at-timedelta(minutes=15),
        SecurityAccessLog.event_type.in_(('client_screen','client_action','request_completed','request_failed'))).order_by(SecurityAccessLog.created_at.desc(),SecurityAccessLog.id.desc()).limit(10).all() if event.user_email and event.created_at else []
    safe_context=[]
    for item in reversed(prior):
        if item.event_type in ('client_screen','client_action'):
            code=raw_details(item).get('ui_code')
            if isinstance(code,str) and code in UI_ACTIONS:
                safe_context.append(f'{stamp(item.created_at)} · {UI_ACTIONS[code]} (krok hlášený aplikací)')
        else:
            safe_context.append(f'{stamp(item.created_at)} · {safe_endpoint(item.endpoint)} · HTTP {http_status(item) or "neuvedeno"} (výsledek zaznamenaný serverem)')
    if safe_context:lines += ['Nejvýše 10 známých kroků v posledních 15 minutách včetně původní události:',*safe_context]
    return {'text':'\n'.join(lines),'redacted':True,'format':'text/plain'}


def create_router(admin_dependency):
    router=APIRouter(prefix='/control-center/incidents',tags=['admin-incidents'])
    def admin_context(request:Request,response:Response,email=Depends(admin_dependency),db:Session=Depends(get_db)):
        response.headers['Cache-Control']='no-store';response.headers['Pragma']='no-cache'
        # Existing API uses explicit bearer auth, never cookie-only privilege. Also
        # reject cross-origin mutation requests rather than trust ambient browser state.
        if request.method in {'POST','PATCH','PUT','DELETE'}:
            origin=request.headers.get('origin')
            if request.headers.get('sec-fetch-site')=='cross-site':raise HTTPException(403,'Požadavek z jiného webu není povolen.')
            if origin:
                incoming=urlsplit(origin);own=urlsplit(str(request.base_url))
                configured={(urlsplit(value).scheme,urlsplit(value).netloc) for value in ALLOWED_ORIGINS if value!='*'}
                allowed=configured | {(own.scheme,own.netloc)}
                if origin=='null' or incoming.path not in ('','/') or (incoming.scheme,incoming.netloc) not in allowed:
                    raise HTTPException(403,'Požadavek musí pocházet z této administrace.')
        admin=db.query(Customer).filter(func.lower(Customer.email)==str(email).lower()).first()
        if not admin or admin.role not in ('admin','developer_admin') or admin.is_deleted or admin.is_disabled:
            raise HTTPException(403,'Přístup pouze pro aktivního administrátora.')
        return admin

    @router.get('')
    def cases(status:Literal['active','all','open','in_progress','resolved','dismissed']='active',search:str=Query('',max_length=120),offset:int=Query(0,ge=0),limit:int=Query(50,ge=1,le=100),admin=Depends(admin_context),db:Session=Depends(get_db)):
        require_ready(db);query=db.query(Case)
        if status=='active':query=query.filter(Case.status.in_(ACTIVE))
        elif status!='all':query=query.filter(Case.status==status)
        if search.strip():
            term='%'+search.strip().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
            query=query.outerjoin(Customer,Customer.id==Case.customer_id).filter(or_(Case.actor_key.ilike(term,escape='\\'),Customer.name.ilike(term,escape='\\')))
        summary={s:0 for s in ('open','in_progress','resolved','dismissed')}
        summary.update(dict(db.query(Case.status,func.count(Case.id)).group_by(Case.status).all()))
        return {'total':query.count(),'summary':summary,'items':[row(db,case) for case in query.order_by(Case.updated_at.desc(),Case.id.desc()).offset(offset).limit(limit)]}

    @router.post('/from-event/{event_id}')
    def from_event(event_id:int,admin=Depends(admin_context),db:Session=Depends(get_db)):
        require_ready(db)
        previous=db.query(Link).filter_by(event_id=event_id).first()
        if previous:return row(db,db.get(Case,previous.incident_id),detail=True)
        event=db.get(SecurityAccessLog,event_id)
        if not event:raise HTTPException(404,'Událost nenalezena.')
        if event.event_type not in PROBLEMS:raise HTTPException(422,'Případ lze založit pouze ze zaznamenaného problému.')
        digest=fingerprint(event)
        case=db.query(Case).filter_by(active_fingerprint=digest).first()
        try:
            if case:
                changed=db.execute(update(Case).where(Case.id==case.id,Case.version==case.version,
                    Case.active_fingerprint==digest,Case.status.in_(ACTIVE)).values(version=Case.version+1,updated_at=datetime.utcnow()),execution_options={'synchronize_session':False})
                if changed.rowcount!=1:
                    db.rollback()
                    raise HTTPException(409,'Stav případu se mezitím změnil. Otevřete událost znovu; nová chyba nesmí zůstat v uzavřeném případu.')
                db.expire(case);db.refresh(case);action='recurrence'
            else:
                customer=db.get(Customer,event.customer_id) if event.customer_id else db.query(Customer).filter(func.lower(Customer.email)==actor_key(event)).first()
                case=Case(source_event_id=event.id,customer_id=customer.id if customer else None,actor_key=actor_key(event),fingerprint=digest,active_fingerprint=digest,created_by=admin.id)
                db.add(case);db.flush();action='created'
            db.add(Link(incident_id=case.id,event_id=event.id));db.add(History(incident_id=case.id,admin_id=admin.id,action=action,status=case.status,version=case.version,note=''))
            audit(db,case,admin,action);db.commit()
        except IntegrityError:
            db.rollback();previous=db.query(Link).filter_by(event_id=event_id).first()
            if previous:return row(db,db.get(Case,previous.incident_id),detail=True)
            raise HTTPException(409,'Současně vznikl obdobný případ. Opakujte otevření události.')
        return row(db,case,detail=True)

    @router.get('/{case_id}')
    def detail(case_id:int,admin=Depends(admin_context),db:Session=Depends(get_db)):
        return row(db,require_case(db,case_id),detail=True)

    @router.post('/{case_id}/transition')
    def transition(case_id:int,body:Transition,admin=Depends(admin_context),db:Session=Depends(get_db)):
        try:return apply_command(db,require_case(db,case_id),admin,body,'transition')
        except IntegrityError:
            db.rollback();raise HTTPException(409,'Existuje novější změna nebo jiný aktivní případ. Obnovte detail.')

    @router.post('/{case_id}/notes')
    def note(case_id:int,body:Note,admin=Depends(admin_context),db:Session=Depends(get_db)):
        try:return apply_command(db,require_case(db,case_id),admin,body,'note')
        except IntegrityError:
            db.rollback();raise HTTPException(409,'Poznámka byla souběžně změněna. Obnovte detail.')

    @router.get('/{case_id}/history')
    def history(case_id:int,offset:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=200),admin=Depends(admin_context),db:Session=Depends(get_db)):
        require_case(db,case_id)
        query=db.query(History,Customer.email).outerjoin(Customer,Customer.id==History.admin_id).filter(History.incident_id==case_id)
        return {'total':query.count(),'offset':offset,'limit':limit,'items':[{'id':item.id,'action':item.action,'status':item.status,'note':item.note,'version':item.version,'created_at':stamp(item.created_at),'admin_email':email} for item,email in query.order_by(History.id.desc()).offset(offset).limit(limit)]}

    @router.get('/{case_id}/events')
    def events(case_id:int,offset:int=Query(0,ge=0),limit:int=Query(100,ge=1,le=200),admin=Depends(admin_context),db:Session=Depends(get_db)):
        require_case(db,case_id)
        query=db.query(SecurityAccessLog).join(Link,Link.event_id==SecurityAccessLog.id).filter(Link.incident_id==case_id)
        return {'total':query.count(),'offset':offset,'limit':limit,'items':[event_view(item) for item in query.order_by(SecurityAccessLog.created_at.desc(),SecurityAccessLog.id.desc()).offset(offset).limit(limit)]}

    @router.get('/{case_id}/check')
    def check(case_id:int,admin=Depends(admin_context),db:Session=Depends(get_db)):
        return check_case(db,require_case(db,case_id))

    @router.get('/{case_id}/diagnostic')
    def export(case_id:int,admin=Depends(admin_context),db:Session=Depends(get_db)):
        return diagnostic(db,require_case(db,case_id))
    return router
