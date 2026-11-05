"""Invitation attribution; registration is not vehicle-sharing consent."""
import html
import json
from datetime import datetime
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session
from src.core.config import PUBLIC_API_BASE_URL
from src.core.rbac import is_admin
from src.core.mfa import limit_attempt
from ..database import get_db
from ..models import Customer, DeveloperActionAuditLog
from .. import referrals as r
from .auth import get_current_user

router = APIRouter(prefix='/referrals', tags=['referrals'])


def _reward(row):
    return dict(id=row.id, source=row.source, starts_at=row.starts_at, ends_at=row.ends_at,
                lifetime=row.ends_at is None, reason=row.reason, revoked_at=row.revoked_at, waiting_for_paid=row.waiting_for_paid)


def _entry(db, row, *, admin=False):
    target = r._target(db, row)
    available = target is not None and not target.is_deleted and not target.is_disabled
    verification = db.get(r.EmailVerification, target.id) if available else None
    verified = verification is not None and verification.verified_at is not None
    # Only the actual referrer (or a privileged administrator) reaches this DTO.
    # Unverified addresses may belong to somebody else; never disclose those.
    contact = available and (admin or verified)
    return dict(id=row.id, kind=row.kind, status=row.reason, created_at=row.created_at,
                qualified_at=row.qualified_at, email_verified=verified,
                contact_available=contact, name=target.name if contact else None,
                email=target.email if contact else None)


def _status(db, owner, *, admin=False):
    r.evaluate(db, owner)
    rows=db.query(r.Referral).filter_by(referrer_id=owner.id).order_by(r.Referral.id.desc()).all()
    users=sum(x.kind == 'user' and x.qualified_at is not None for x in rows)
    services=sum(x.kind == 'service' and x.qualified_at is not None for x in rows)
    rewards=db.query(r.ReferralReward).filter_by(customer_id=owner.id).order_by(r.ReferralReward.id.desc()).all()
    details=[_entry(db, row, admin=admin) for row in rows[:200]]
    return dict(customer_id=owner.id, name=owner.name or owner.email, email=owner.email if admin else None,
                registrations=len(rows), qualified_users=users, qualified_services=services,
                users_to_next_reward=3-users%3, referrals=details, rewards=[_reward(g) for g in rewards],
                rules='Měsíc Premium za každé 3 nové ověřené uživatele s prvním vozidlem nebo 1 nový ověřený servis s první dokončenou zakázkou. Doživotní Premium schvaluje administrátor.',
                billing_note='Odměna neruší placené předplatné. Měsíc je kalendářní, další odměny navazují. Při placeném Premium bonus čeká a nespotřebovává se ani při obnovení platby. Spustí se při příštím načtení tarifu po skončení placeného Premium.')


@router.get('/me')
def my_referrals(current_user: Customer=Depends(get_current_user), db: Session=Depends(get_db)):
    r.require_ready(db)
    code=r.code_for(db,current_user)
    result=_status(db,current_user)
    root=PUBLIC_API_BASE_URL.rstrip('/')+'/api/v1/referrals/join/'+code
    result.update(code=code, user_url=root+'?kind=user', service_url=root+'?kind=service')
    db.commit()
    return result


@router.get('/me/invitees/{referral_id}')
def my_invitee(referral_id: int, current_user: Customer=Depends(get_current_user), db: Session=Depends(get_db)):
    r.require_ready(db)
    row = db.query(r.Referral).filter_by(id=referral_id, referrer_id=current_user.id).first()
    if row is None: raise HTTPException(404, 'Pozvaný účet nebyl nalezen.')
    r.evaluate(db, current_user)
    result = _entry(db, row)
    db.commit()
    return result


@router.get('/admin')
def admin_referrals(search: str=Query('', max_length=120), offset: int=Query(0,ge=0),
    current_user: Customer=Depends(get_current_user),db: Session=Depends(get_db)):
    if not is_admin(current_user.role): raise HTTPException(403,'Přehled pozvánek je dostupný pouze administrátorovi.')
    r.require_ready(db)
    query=db.query(Customer).join(r.ReferralCode,r.ReferralCode.customer_id == Customer.id)
    if search.strip():
        term='%'+search.strip().replace('%','\\%').replace('_','\\_')+'%'
        query=query.filter(Customer.email.ilike(term,escape='\\') | Customer.name.ilike(term,escape='\\'))
    # Paginated aggregate list; detail fetch performs reconciliation, no global write sweep.
    total=query.count(); items=[]
    for customer in query.order_by(r.ReferralCode.created_at.desc(),Customer.id.desc()).offset(offset).limit(30):
        rows=db.query(r.Referral).filter_by(referrer_id=customer.id)
        items.append(dict(id=customer.id,name=customer.name or customer.email,email=customer.email,
                          registrations=rows.count(),qualified=rows.filter(r.Referral.qualified_at.isnot(None)).count()))
    return dict(total=total,items=items,offset=offset,limit=30)


@router.get('/admin/{customer_id}')
def admin_detail(customer_id:int,current_user:Customer=Depends(get_current_user),db:Session=Depends(get_db)):
    if not is_admin(current_user.role): raise HTTPException(403,'Přehled je dostupný pouze administrátorovi.')
    r.require_ready(db)
    customer=db.get(Customer,customer_id)
    if not customer: raise HTTPException(404,'Účet nenalezen.')
    result=_status(db,customer,admin=True);db.commit();return result


class GrantInput(BaseModel):
    request_id: UUID
    kind: Literal['month','lifetime']
    reason: str = Field(min_length=5,max_length=500)

    @field_validator('reason')
    @classmethod
    def reason_not_blank(cls, value):
        value = value.strip()
        if len(value) < 5:
            raise ValueError('Uveďte důvod alespoň pěti znaky.')
        return value


@router.post('/admin/{customer_id}/rewards')
def admin_reward(customer_id:int,payload:GrantInput,current_user:Customer=Depends(get_current_user),db:Session=Depends(get_db)):
    if not is_admin(current_user.role): raise HTTPException(403,'Odměnu může přidělit pouze administrátor.')
    r.require_ready(db)
    limit_attempt(db,current_user.id,'referral-grant',limit=20)
    r.lock_referrer(db, customer_id)
    customer=db.query(Customer).filter_by(id=customer_id).first()
    if not customer or customer.is_disabled or customer.is_deleted: raise HTTPException(404,'Aktivní účet nenalezen.')
    previous=db.query(r.ReferralReward).filter_by(client_id=str(payload.request_id)).first()
    if previous:
        if previous.customer_id != customer_id or previous.reason != payload.reason.strip() or (previous.ends_at is None) != (payload.kind == 'lifetime'):
            raise HTTPException(409,'Toto potvrzení již patří jiné odměně.')
        return _reward(previous)
    ordinal=(db.query(func.max(r.ReferralReward.ordinal)).filter_by(customer_id=customer_id,source='admin').scalar() or 0)+1
    reward=r.grant(db,customer,source='admin',ordinal=ordinal,actor=current_user,lifetime=payload.kind=='lifetime',reason=payload.reason.strip())
    reward.client_id=str(payload.request_id)
    db.add(DeveloperActionAuditLog(developer_id=current_user.id,developer_email=current_user.email,
        action_type='referral.reward.grant',target_resource=f'customer:{customer.id}',
        parameters_json=json.dumps({'reward_id':reward.id,'kind':payload.kind,'reason':reward.reason,'affected_customer_ids':[customer.id]},ensure_ascii=False),result='success',status_code=200))
    db.commit();return _reward(reward)


class RevokeInput(BaseModel):
    reason: str=Field(min_length=5,max_length=500)

    @field_validator('reason')
    @classmethod
    def reason_not_blank(cls, value):
        value = value.strip()
        if len(value) < 5:
            raise ValueError('Uveďte důvod alespoň pěti znaky.')
        return value


@router.post('/admin/{customer_id}/rewards/{reward_id}/revoke')
def revoke_reward(customer_id:int,reward_id:int,payload:RevokeInput,current_user:Customer=Depends(get_current_user),db:Session=Depends(get_db)):
    if not is_admin(current_user.role): raise HTTPException(403,'Odměnu může odebrat pouze administrátor.')
    r.require_ready(db)
    r.lock_referrer(db, customer_id)
    reward=db.query(r.ReferralReward).filter_by(id=reward_id,customer_id=customer_id).first()
    if not reward: raise HTTPException(404,'Odměna nenalezena.')
    if not reward.revoked_at:
        reward.revoked_at=datetime.utcnow()
        db.add(DeveloperActionAuditLog(developer_id=current_user.id,developer_email=current_user.email,action_type='referral.reward.revoke',
            target_resource=f'reward:{reward.id}',parameters_json=json.dumps({'reason':payload.reason.strip(),'affected_customer_ids':[customer_id]},ensure_ascii=False),result='success',status_code=200))
        db.commit()
    return _reward(reward)


@router.get('/join/{code}',response_class=HTMLResponse)
def join(code:str,kind:Literal['user','service']='user',db:Session=Depends(get_db)):
    r.require_ready(db)
    row=db.query(r.ReferralCode).filter_by(code=code).first()
    owner=db.get(Customer,row.customer_id) if row else None
    if not owner or owner.is_deleted or owner.is_disabled: raise HTTPException(404,'Pozvánka není dostupná.')
    # No account/session token, no personal identity, no auto-registration, no e-mail sending.
    safe=html.escape(code,quote=True)
    link=html.escape(f'spravavozidel://referral?code={code}&kind={kind}',quote=True)
    title='Pozvání servisu' if kind=='service' else 'Pozvání do Evidence Vozidel'
    web_link=html.escape(PUBLIC_API_BASE_URL.rstrip('/') + '/web/customer.html#referral=' + code + '&kind=' + kind,quote=True)
    return HTMLResponse(f'''<!doctype html><html lang="cs"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><style>body{{font:18px system-ui;background:#202b40;color:white;margin:0;padding:32px;line-height:1.6}}main{{max-width:560px;margin:auto}}a{{display:block;background:#ff9c31;color:#202b40;padding:16px;border-radius:16px;text-align:center;margin:24px 0;font-weight:bold}}code{{overflow-wrap:anywhere}}</style><main><h1>{title}</h1><p>Pozvánka vás provede novou registrací. Před použitím účtu ověříte svůj e-mail.</p><a href="{link}">Otevřít pozvánku v aplikaci</a><a href="{web_link}">Pokračovat registrací na webu</a><p>Pokud aplikaci ještě nemáte, nainstalujte Evidence Vozidel z obchodu a při registraci vložte kód:</p><code>{safe}</code><p>Po ověření e-mailu uvidí pozývající vaše jméno, e-mail a stav splnění podmínek odměny. Pozvánka nepředává přístup k vozidlům ani dokladům. Započítá se až ověřená registrace a první vozidlo, u schváleného servisu první dokončená zakázka.</p></main></html>''',headers={'Cache-Control':'no-store','Referrer-Policy':'no-referrer','X-Content-Type-Options':'nosniff','Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; frame-ancestors 'none'"})
