"""Provider wire contracts with local HTTP interception; never real APNs/FCM."""
from types import SimpleNamespace
from unittest.mock import patch
import json
import pytest,httpx
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
from src.modules.vehicle_hub.push_delivery import send_provider,generic_payload,Outcome

@pytest.fixture
def config(monkeypatch):
    key=ec.generate_private_key(ec.SECP256R1()).private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()).decode()
    for k,v in {'APNS_SANDBOX_KEY_ID':'QASANDBOX','APNS_SANDBOX_PRIVATE_KEY':key,'APNS_KEY_ID':'QAPRODUCTION','APNS_TEAM_ID':'QATEAM','APNS_PRIVATE_KEY':key,'APNS_BUNDLE_IDS':'cz.fixture','FCM_PROJECT_ID':'synthetic-fixture','FCM_BUNDLE_IDS':'cz.fixture','FCM_SERVICE_ACCOUNT_JSON':json.dumps({'token_uri':'https://oauth2.googleapis.com/token'}),'VAPID_PUBLIC_KEY':'qa','VAPID_PRIVATE_KEY':'qa','VAPID_CLAIMS_SUBJECT':'mailto:test@example.invalid'}.items():monkeypatch.setenv(k,v)
    return generic_payload(SimpleNamespace(id=19,kind='admin_message'),4)

def intercept(monkeypatch,response,requests):
    original=httpx.Client
    def handle(request):requests.append(request);return response
    monkeypatch.setattr(httpx,'Client',lambda **kwargs:original(transport=httpx.MockTransport(handle),**kwargs))

def test_apns_uses_correct_environment_topic_generic_payload_and_count(monkeypatch,config):
    requests=[];intercept(monkeypatch,httpx.Response(200),requests)
    device=SimpleNamespace(platform='apns',environment='sandbox',bundle_id='cz.fixture')
    result=send_provider(device,{'token':'ab'*32},config)
    assert result.state=='accepted'
    request=requests[0];assert request.url.host=='api.sandbox.push.apple.com'
    import jwt
    assert jwt.get_unverified_header(request.headers['authorization'].split(' ',1)[1])['kid']=='QASANDBOX'
    assert request.headers['apns-topic']=='cz.fixture';assert request.headers['apns-push-type']=='alert'
    body=json.loads(request.content);assert body['aps']['badge']==4;assert body['notification_id']==19
    assert set(body)=={'aps','notification_id','kind','route'}
    assert body['aps']['alert']['body']=='V aplikaci na vás čeká nové oznámení.'

def test_apns_invalid_token_and_transient_retry_are_classified(monkeypatch,config):
    requests=[];intercept(monkeypatch,httpx.Response(410,json={'reason':'Unregistered','private':'never-store'}),requests)
    result=send_provider(SimpleNamespace(platform='apns',environment='production',bundle_id='cz.fixture'),{'token':'ab'*32},config)
    assert result==Outcome('invalid','apns_invalid_token');assert requests[0].url.host=='api.push.apple.com'
    import jwt
    assert jwt.get_unverified_header(requests[0].headers['authorization'].split(' ',1)[1])['kid']=='QAPRODUCTION'

def fake_credentials(monkeypatch):
    from google.oauth2 import service_account
    creds=SimpleNamespace(token='qa-access-token',refresh=lambda request:None)
    monkeypatch.setattr(service_account.Credentials,'from_service_account_info',lambda *a,**k:creds)

def test_fcm_generic_notification_data_channel_and_single_badge(monkeypatch,config):
    fake_credentials(monkeypatch);requests=[];intercept(monkeypatch,httpx.Response(200,json={'name':'accepted'}),requests)
    result=send_provider(SimpleNamespace(platform='fcm',environment='production',bundle_id='cz.fixture'),{'token':'qa-registration-token'},config)
    assert result.state=='accepted';request=requests[0]
    assert request.url.host=='fcm.googleapis.com';assert request.url.path=='/v1/projects/synthetic-fixture/messages:send'
    body=json.loads(request.content)['message'];assert body['notification']['body']=='V aplikaci na vás čeká nové oznámení.'
    assert body['data']=={'notification_id':'19','kind':'admin_message','badge_count':'4','route':'notifications'}
    assert body['android']['notification']['channel_id']=='evidence_messages_v1'
    assert body['android']['notification']['notification_count']==4
    assert body['android']['notification']['tag']=='evidence_notifications'

def test_fcm_invalid_argument_does_not_wrongly_revoke_token(monkeypatch,config):
    fake_credentials(monkeypatch);intercept(monkeypatch,httpx.Response(400,json={'error':{'status':'INVALID_ARGUMENT','message':'private details'}}),[])
    result=send_provider(SimpleNamespace(platform='fcm',environment='production',bundle_id='cz.fixture'),{'token':'qa-token'},config)
    assert result.state=='blocked';assert 'private' not in result.code

def test_fcm_unregistered_revokes_and_rate_limit_honors_retry(monkeypatch,config):
    fake_credentials(monkeypatch);intercept(monkeypatch,httpx.Response(404,json={'error':{'details':[{'errorCode':'UNREGISTERED'}]}}),[])
    result=send_provider(SimpleNamespace(platform='fcm',environment='production',bundle_id='cz.fixture'),{'token':'qa-token'},config)
    assert result.state=='invalid';assert result.code=='fcm_unregistered'

def test_webpush_allowlist_generic_payload_and_redirects_disabled(monkeypatch,config):
    captured={}
    def webpush(**kwargs):captured.update(kwargs)
    monkeypatch.setattr('pywebpush.webpush',webpush)
    result=send_provider(SimpleNamespace(platform='webpush'),{'token':'https://web.push.apple.com/test','web_keys':{'auth':'qa','p256dh':'qa'}},config)
    assert result.state=='accepted'
    assert json.loads(captured['data'])['notification_id']==19
    with patch('requests.Session.request',return_value=SimpleNamespace(status_code=200)) as request:
        captured['requests_session'].get('https://web.push.apple.com/test')
        assert request.call_args.kwargs['allow_redirects'] is False
    assert send_provider(SimpleNamespace(platform='webpush'),{'token':'http://127.0.0.1/secret'},config).state=='invalid'


@pytest.mark.parametrize('environment,prefix',[('production','APNS_'),('sandbox','APNS_SANDBOX_')])
def test_apns_missing_environment_key_never_falls_back_to_other_key(monkeypatch,config,environment,prefix):
    monkeypatch.delenv(prefix+'PRIVATE_KEY');requests=[]
    intercept(monkeypatch,httpx.Response(200),requests)
    result=send_provider(SimpleNamespace(platform='apns',environment=environment,bundle_id='cz.fixture'),{'token':'ab'*32},config)
    assert result==Outcome('blocked','provider_not_configured',900)
    assert requests==[]
