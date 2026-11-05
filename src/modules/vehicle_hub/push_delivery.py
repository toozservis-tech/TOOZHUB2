"""Encrypted, session-bound devices and leased durable push delivery.

Provider acceptance is not a delivery/read receipt. At-least-once retry uses a
stable collapse/tag ID; a worker crash after acceptance may repeat a push.
"""
from datetime import datetime,timedelta
from dataclasses import dataclass
import hashlib,hmac,json,os,re,time
from urllib.parse import urlsplit
from uuid import uuid4
from cryptography.fernet import Fernet,InvalidToken
from sqlalchemy import or_,and_,update,select
from fastapi import HTTPException
from .notification_delivery_models import PushDevice,PushOutbox,NotificationItem,NotificationCursor
from .notification_inbox import active_user,source_for,summary,requires_ack
from .models import Customer
from .account_state import customer_session_version
from src.core.session_revocation import RevokedAccessToken,token_digest
from src.core.security import decode_access_token_payload


def digest(value):return hashlib.sha256(value.encode()).hexdigest()

def cipher():
    try:return Fernet(os.environ['PUSH_TOKEN_ENCRYPTION_KEY'].encode())
    except (KeyError,ValueError):raise HTTPException(503,'Push upozornění zatím nejsou na serveru nastavena. Zprávy najdete v aplikaci.') from None

def configured(platform,environment=None):
    if platform=='apns':
        if environment is None:return configured('apns','production') or configured('apns','sandbox')
        if environment not in {'production','sandbox'}:return False
        prefix='APNS_SANDBOX_' if environment=='sandbox' else 'APNS_'
        keys=['APNS_TEAM_ID','APNS_BUNDLE_IDS',prefix+'KEY_ID',prefix+'PRIVATE_KEY']
    else:
        keys={'fcm':['FCM_PROJECT_ID','FCM_SERVICE_ACCOUNT_JSON','FCM_BUNDLE_IDS'],
              'webpush':['VAPID_PRIVATE_KEY','VAPID_PUBLIC_KEY','VAPID_CLAIMS_SUBJECT']}[platform]
    return all(bool(os.getenv(key,'')) for key in keys)

@dataclass(frozen=True)
class DeliveryPolicy:
    enabled:bool
    valid:bool
    recipients:frozenset|None

    def allows(self,recipient_id):
        return self.enabled and self.valid and (self.recipients is None or recipient_id in self.recipients)

def delivery_policy():
    """Read afresh at claim/send; malformed nonempty canary config fails closed."""
    enabled=os.getenv('PUSH_DELIVERY_ENABLED','').lower() in {'1','true'}
    raw=os.getenv('PUSH_DELIVERY_RECIPIENT_IDS','').strip()
    if not raw:return DeliveryPolicy(enabled,True,None)
    parts=raw.split(',')
    if len(raw)>10000 or len(parts)>1000 or any(not re.fullmatch(r'[1-9][0-9]{0,9}',part.strip()) or int(part.strip())>2147483647 for part in parts):
        return DeliveryPolicy(enabled,False,frozenset())
    return DeliveryPolicy(enabled,True,frozenset(int(part.strip()) for part in parts))

def public_status():
    policy=delivery_policy()
    return {'registration_available':bool(os.getenv('PUSH_TOKEN_ENCRYPTION_KEY')),
        'dispatch_enabled':policy.enabled and policy.valid,
        'dispatch_limited':policy.recipients is not None,
        'dispatch_configuration_valid':policy.valid,
        'providers':{p:{'configured':configured(p)} for p in ('apns','fcm','webpush')}}

def valid_web_endpoint(endpoint):
    try:
        u=urlsplit(endpoint)
        # Only established browser push-provider HTTPS hosts; no arbitrary URL,
        # IP, credentials, port, redirect, fragment, or custom destination.
        host=(u.hostname or '').lower()
        allowed=host in {'fcm.googleapis.com','updates.push.services.mozilla.com','web.push.apple.com'} or host.endswith('.push.services.mozilla.com') or host.endswith('.notify.windows.com')
        return u.scheme=='https' and bool(allowed) and u.port in (None,443) and not u.username and not u.password and not u.fragment and len(endpoint)<=4096
    except ValueError:return False

def _register(db,user,body,token):
    from .notification_inbox import require_ready
    from src.server.admin_messages import lock_recipient
    require_ready(db);lock_recipient(db,user)
    if not active_user(user):raise HTTPException(403,'Push je dostupný zákazníkům a servisům.')
    claims=decode_access_token_payload(token)
    if not claims or claims.get('sub','').lower()!=user.email.lower() or not claims.get('exp') or claims.get('demo') or claims.get('public_demo'):
        raise HTTPException(401,'Přihlaste se znovu.')
    from src.core.rate_limiter import rate_limiter
    if not rate_limiter.check_rate_limit(f'push-register:{user.id}',30,60):raise HTTPException(429,'Příliš mnoho registrací. Zkuste to za chvíli.')
    enc=cipher()
    if not configured(body.platform,body.environment):raise HTTPException(503,'Push upozornění pro toto zařízení zatím nejsou nastavena. Zprávy najdete v aplikaci.')
    if body.platform=='apns':
        if not re.fullmatch(r'[0-9a-fA-F]{32,256}',body.token):raise HTTPException(422,'Neplatný token zařízení.')
        allowed={v.strip() for v in os.getenv('APNS_BUNDLE_IDS','').split(',') if v.strip()}
    elif body.platform=='fcm':
        if not re.fullmatch(r'[a-zA-Z0-9_:\-]{20,4096}',body.token):raise HTTPException(422,'Neplatný token zařízení.')
        allowed={v.strip() for v in os.getenv('FCM_BUNDLE_IDS','').split(',') if v.strip()}
        if body.environment!='production':raise HTTPException(422,'Neplatné prostředí FCM.')
    else:
        allowed={'web'}
        if not valid_web_endpoint(body.token) or not body.web_keys:raise HTTPException(422,'Neplatná registrace prohlížeče.')
        for key in ('auth','p256dh'):
            if not re.fullmatch(r'[A-Za-z0-9_\-=]{16,256}',body.web_keys.get(key,'')):raise HTTPException(422,'Neplatné klíče prohlížeče.')
    if body.bundle_id not in allowed:raise HTTPException(422,'Tato aplikace není povolena pro push.')
    iid=str(body.installation_id);secret=digest(body.installation_secret)
    token_hash=digest(body.platform+'|'+body.environment+'|'+body.bundle_id+'|'+body.token)
    existing=db.query(PushDevice).filter(or_(PushDevice.installation_id==iid,PushDevice.token_hash==token_hash)).with_for_update().all()
    if len(existing)>1:raise HTTPException(409,'Registrace zařízení se změnila. Obnovte povolení oznámení.')
    row=existing[0] if existing else None
    if row and (row.installation_id!=iid or not hmac.compare_digest(row.installation_secret_hash,secret)):
        raise HTTPException(409,'Registrace zařízení se změnila. Obnovte povolení oznámení.')
    now=datetime.utcnow()
    if row is None:
        row=PushDevice(installation_id=iid,installation_secret_hash=secret,generation=1)
        db.add(row)
    elif row.recipient_id!=user.id or row.session_digest!=token_digest(token,claims) or row.token_hash!=token_hash or not row.active:
        row.generation+=1
    row.recipient_id=user.id;row.platform=body.platform;row.environment=body.environment;row.bundle_id=body.bundle_id
    row.token_hash=token_hash;row.token_ciphertext=enc.encrypt(json.dumps({'token':body.token,'web_keys':body.web_keys}).encode()).decode()
    row.session_digest=token_digest(token,claims);row.session_version=customer_session_version(user)
    row.session_expires_at=datetime.utcfromtimestamp(claims['exp']);row.permission=body.permission
    row.active=True;row.revoked_at=None;row.updated_at=now
    db.flush()
    # Existing eligible unread events since rollout may be delivered after the
    # user opts in, but there is no historical-backlog or acknowledged replay.
    from .notification_inbox import source_for,ensure_item
    from .models import SystemNotification
    for item in db.query(NotificationItem).filter_by(recipient_id=user.id,read_at=None):
        cursor=db.get(NotificationCursor,item.kind)
        source=source_for(db,item,user,for_delivery=True)
        if source is None and item.kind=='announcement':
            candidate=db.get(SystemNotification,item.source_id)
            # Scheduled sources remain generic candidates until the due-time
            # audience check; registering later must not miss the future send.
            if candidate and candidate.is_active and candidate.starts_at and candidate.starts_at>now and (not candidate.expires_at or candidate.expires_at>candidate.starts_at):
                source=candidate
        if cursor and item.created_at>=cursor.rollout_at and source is not None:
            ensure_item(db,user,item.kind,source,queue=True)
    result={'id':row.id,'active':True,'platform':row.platform,'environment':row.environment}
    try:db.commit()
    except __import__('sqlalchemy').exc.IntegrityError:
        db.rollback();raise HTTPException(409,'Registrace zařízení se změnila. Obnovte povolení oznámení.') from None
    return result

def register(db,user,body,token):
    from sqlalchemy.exc import IntegrityError
    try:return _register(db,user,body,token)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409,'Registrace zařízení se změnila. Obnovte povolení oznámení.') from None


def unregister(db,user,body):
    from .notification_inbox import require_ready
    require_ready(db)
    row=db.query(PushDevice).filter_by(installation_id=str(body.installation_id),recipient_id=user.id).with_for_update().first()
    if row and hmac.compare_digest(row.installation_secret_hash,digest(body.installation_secret)):
        row.active=False;row.generation+=1;row.revoked_at=datetime.utcnow()
        db.commit()
    # Never reveal another account's registration or token.
    return {'ok':True}

def eligible_device(db,device,user,now=None):
    now=now or datetime.utcnow()
    if not active_user(user) or not device.active or device.recipient_id!=user.id or device.session_expires_at<=now or device.session_version!=customer_session_version(user):return False
    return db.execute(select(RevokedAccessToken.digest).where(RevokedAccessToken.digest==device.session_digest)).first() is None

@dataclass(frozen=True)
class Outcome:
    state:str # accepted | retry | invalid | blocked
    code:str
    retry_after:int=60


def generic_payload(item,badge):
    return {'title':'Evidence Vozidel','body':'V aplikaci na vás čeká nové oznámení.',
        'notification_id':item.id,'kind':item.kind,'badge_count':badge,'route':'notifications',
        'url':'/web/customer.html#notifications','tag':f'notification-{item.id}'}

def send_provider(device,secret,payload):
    """Network adapters use fixed providers and never return raw error text."""
    import httpx
    try:
        if not configured(device.platform,getattr(device,'environment',None)):return Outcome('blocked','provider_not_configured',900)
        if device.platform=='apns':
            import jwt
            prefix='APNS_SANDBOX_' if device.environment=='sandbox' else 'APNS_'
            bearer=jwt.encode({'iss':os.environ['APNS_TEAM_ID'],'iat':int(time.time())},os.environ[prefix+'PRIVATE_KEY'].replace('\\n','\n'),algorithm='ES256',headers={'kid':os.environ[prefix+'KEY_ID']})
            host='api.sandbox.push.apple.com' if device.environment=='sandbox' else 'api.push.apple.com'
            data={'aps':{'alert':{'title':payload['title'],'body':payload['body']},'sound':'default','badge':payload['badge_count']},
                'notification_id':payload['notification_id'],'kind':payload['kind'],'route':'notifications'}
            with httpx.Client(http2=True,timeout=15,follow_redirects=False) as client:
                response=client.post('https://'+host+'/3/device/'+secret['token'],json=data,headers={
                    'authorization':'bearer '+bearer,'apns-topic':device.bundle_id,'apns-push-type':'alert',
                    'apns-priority':'10','apns-expiration':str(int(time.time())+86400),'apns-collapse-id':payload['tag']})
            code=response.json().get('reason','') if response.content else ''
            if response.status_code==200:return Outcome('accepted','apns_accepted')
            if response.status_code==410 or code in {'BadDeviceToken','DeviceTokenNotForTopic'}:return Outcome('invalid','apns_invalid_token')
            if response.status_code in {429,500,503}:return Outcome('retry','apns_temporarily_unavailable',_retry_after(response))
            return Outcome('blocked','apns_configuration_error',900)
        if device.platform=='fcm':
            from google.oauth2 import service_account
            from google.auth.transport.requests import Request
            info=json.loads(os.environ['FCM_SERVICE_ACCOUNT_JSON'])
            if info.get('token_uri')!='https://oauth2.googleapis.com/token':return Outcome('blocked','fcm_configuration_error',900)
            project=os.environ['FCM_PROJECT_ID']
            if not re.fullmatch(r'[a-z][a-z0-9\-]{3,62}',project):return Outcome('blocked','fcm_configuration_error',900)
            creds=service_account.Credentials.from_service_account_info(info,scopes=['https://www.googleapis.com/auth/firebase.messaging'])
            auth_request=Request()
            creds.refresh(lambda *args,**kwargs:auth_request(*args,**{**kwargs,'timeout':15}))
            data={'message':{'token':secret['token'],'data':{k:str(payload[k]) for k in ('notification_id','kind','badge_count','route')},
                'notification':{'title':payload['title'],'body':payload['body']},
                'android':{'priority':'HIGH','ttl':'86400s','collapse_key':payload['tag'],
                    'restricted_package_name':device.bundle_id,'notification':{'tag':'evidence_notifications','notification_count':payload['badge_count'],'channel_id':'evidence_messages_v1'}}}}
            with httpx.Client(timeout=15,follow_redirects=False) as client:
                response=client.post('https://fcm.googleapis.com/v1/projects/'+project+'/messages:send',json=data,headers={'Authorization':'Bearer '+creds.token})
            if response.status_code==200:return Outcome('accepted','fcm_accepted')
            errors=(response.json().get('error') or {}).get('details') or []
            if any(v.get('errorCode')=='UNREGISTERED' for v in errors if isinstance(v,dict)):return Outcome('invalid','fcm_unregistered')
            if response.status_code in {429,500,503}:return Outcome('retry','fcm_temporarily_unavailable',_retry_after(response))
            return Outcome('blocked','fcm_configuration_error',900)
        if not valid_web_endpoint(secret['token']):return Outcome('invalid','webpush_invalid_endpoint')
        from pywebpush import webpush,WebPushException
        # requests follows redirects by default. Override for subscription endpoints.
        import requests
        class NoRedirectSession(requests.Session):
            def request(self,*args,**kwargs):kwargs['allow_redirects']=False;return super().request(*args,**kwargs)
        try:
            webpush(subscription_info={'endpoint':secret['token'],'keys':secret['web_keys']},data=json.dumps(payload),
                vapid_private_key=os.environ['VAPID_PRIVATE_KEY'],vapid_claims={'sub':os.environ['VAPID_CLAIMS_SUBJECT']},
                ttl=86400,timeout=15,requests_session=NoRedirectSession())
            return Outcome('accepted','webpush_accepted')
        except WebPushException as exc:
            status=getattr(exc.response,'status_code',0)
            if status in {404,410}:return Outcome('invalid','webpush_unregistered')
            if status in {429,500,502,503}:return Outcome('retry','webpush_temporarily_unavailable')
            return Outcome('blocked','webpush_configuration_error',900)
    except (httpx.TimeoutException,httpx.NetworkError):return Outcome('retry','provider_network_error')
    except Exception:return Outcome('blocked','provider_configuration_error',900)

def _retry_after(response):
    try:return max(60,min(3600,int(response.headers.get('Retry-After','60'))))
    except ValueError:return 60

def dispatch_one(db,provider=send_provider,now=None):
    policy=delivery_policy()
    if not policy.enabled or not policy.valid:return False
    now=now or datetime.utcnow()
    available=or_(and_(PushOutbox.state.in_(['queued','retry','blocked']),PushOutbox.next_attempt_at<=now),and_(PushOutbox.state=='sending',PushOutbox.lease_until<=now))
    query=db.query(PushOutbox).filter(available)
    if policy.recipients is not None:
        # Excluded recipients must not consume attempts, leases or the cycle's
        # bounded send budget. Registration/collection remain independent.
        query=query.filter(PushOutbox.item_id.in_(select(NotificationItem.id).where(NotificationItem.recipient_id.in_(policy.recipients))))
    row=query.order_by(PushOutbox.id).with_for_update(skip_locked=True).first()
    if row is None:return False
    previous_state=row.state;previous_attempts=row.attempts
    lease=str(uuid4())
    changed=db.execute(update(PushOutbox).where(PushOutbox.id==row.id,available).values(state='sending',lease_token=lease,lease_until=now+timedelta(seconds=120),attempts=PushOutbox.attempts+1),execution_options={'synchronize_session':False}).rowcount
    if changed!=1:db.rollback();return True
    identifier=row.id;db.commit()
    # Recheck after claiming: logout, consent, transfer and account revocation
    # must not be served from a previous identity-map snapshot.
    db.expire_all();row=db.get(PushOutbox,identifier);device=db.get(PushDevice,row.device_id);item=db.get(NotificationItem,row.item_id)
    def release_excluded_claim():
        db.execute(update(PushOutbox).where(PushOutbox.id==identifier,PushOutbox.lease_token==lease).values(
            state='queued' if previous_state=='sending' else previous_state,attempts=previous_attempts,lease_until=None,lease_token=None))
        db.commit()
        return False
    if item is not None and not delivery_policy().allows(item.recipient_id):return release_excluded_claim()
    user=db.get(Customer,item.recipient_id) if item else None
    source=source_for(db,item,user,for_delivery=True) if item and user else None
    if source is not None:
        from .notification_inbox import sync_receipts
        sync_receipts(db,item,source)
    delivery_time=max(item.created_at,source.starts_at) if source is not None and item.kind=='announcement' and source.starts_at else item.created_at if item else now
    if not device or not source or row.device_generation!=device.generation or not eligible_device(db,device,user,now):outcome=Outcome('invalid','binding_or_access_revoked')
    elif item.read_at or item.dismissed_at or item.acknowledged_at:outcome=Outcome('invalid','already_seen')
    elif now-delivery_time>timedelta(days=1):outcome=Outcome('invalid','notification_expired')
    else:
        try:
            secret=json.loads(cipher().decrypt(device.token_ciphertext.encode()))
            payload=generic_payload(item,summary(db,user)['badge_count'])
            # Configuration may have changed while authorization/badge was
            # loaded. Never turn a canary exclusion into a failed notification.
            if not delivery_policy().allows(item.recipient_id):return release_excluded_claim()
            outcome=provider(device,secret,payload)
        except (HTTPException,InvalidToken,ValueError):outcome=Outcome('blocked','token_storage_unavailable',900)
    # Persist only bounded classified outcomes. No token/provider text in errors.
    if not isinstance(outcome,Outcome) or outcome.state not in {'accepted','retry','invalid','blocked'} or not re.fullmatch(r'[a-z_]{1,64}',outcome.code):outcome=Outcome('blocked','provider_invalid_result',900)
    values={'state':{'accepted':'accepted','invalid':'skipped'}.get(outcome.state,outcome.state),'last_code':outcome.code,'lease_until':None,'lease_token':None}
    if outcome.state=='accepted':values['accepted_at']=datetime.utcnow()
    elif outcome.state in {'retry','blocked'}:
        values['next_attempt_at']=now+timedelta(seconds=min(3600,max(outcome.retry_after,30*2**min(row.attempts,7))))
    if row.attempts>=12 and outcome.state in {'retry','blocked'}:values['state']='failed'
    db.execute(update(PushOutbox).where(PushOutbox.id==identifier,PushOutbox.lease_token==lease).values(**values))
    if outcome.code in {'apns_invalid_token','fcm_unregistered','webpush_unregistered'}:
        db.execute(update(PushDevice).where(PushDevice.id==device.id,PushDevice.generation==row.device_generation).values(active=False,revoked_at=datetime.utcnow()))
    db.commit();return True
