"""All tests use an isolated in-memory database and fake gateway; no charges or emails."""
import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from starlette.requests import Request

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import Tenant, License, LicensePaymentTransaction
from src.modules.vehicle_hub.routers_v1 import license_status as billing
from src.modules.vehicle_hub.routers_v1 import mobile_billing as mobile

@pytest.fixture
def setup(monkeypatch):
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    db.add(Tenant(id=1, name='Billing test', license_key='billing-fixture'))
    db.add(License(tenant_id=1, plan='free', status='active', vehicles_limit=1))
    db.commit()
    monkeypatch.setattr(billing, 'load_runtime_settings', lambda: {})
    cfg = billing._load_comgate_config()
    cfg.update(enabled=True, configured=True, merchant='507933', secret='fixture-secret', test_mode=False)
    monkeypatch.setattr(billing, '_load_comgate_config', lambda: cfg)
    monkeypatch.setattr(billing, '_ensure_subscription_schema', lambda *a, **k: True)
    monkeypatch.setattr(billing, '_send_subscription_notification', lambda *a, **k: dict(email_sent=0, push_sent=0))
    monkeypatch.setattr(billing, '_post_comgate', lambda *a, **k: pytest.fail('Unexpected gateway call'))
    user = SimpleNamespace(id=1, tenant_id=1, email='fixture@example.invalid', role='user', name='Fixture', phone='')
    yield db, user, cfg
    db.close(); engine.dispose()

def request(trans=None):
    return Request(dict(type='http', method='GET', headers=[], scheme='https', server=('app.example.invalid',443), path='/', query_string=(f'transId={trans}' if trans else '').encode()))

def purchase(**changes):
    data=dict(plan='basic', billing_period='monthly', request_id=uuid4(), expected_amount_halers=9900,
              expected_currency='CZK', expected_test_mode=False, expected_recurring=True, contract_version=mobile.CONTRACT_VERSION,
              accept_terms=True, accept_immediate_service=True, accept_recurring=True)
    data.update(changes)
    return mobile.Purchase(**data)

def created(setup, monkeypatch, payload=None):
    db,user,cfg=setup
    calls=[]
    def gateway(url, values):
        calls.append(values)
        return dict(code='0', transId='TEST-ONE', redirect='https://pay1.comgate.cz/fixture')
    monkeypatch.setattr(billing, '_post_comgate', gateway)
    result=mobile.checkout(payload or purchase(),request(),user,db)
    return result,calls

def paid_response(row, **changes):
    data=dict(code='0',status='PAID',price='9900',curr='CZK',merchant='507933',test='false',transId=row.trans_id,refId=row.ref_id)
    data.update(changes); return data

def test_checkout_records_consents_and_is_idempotent(setup, monkeypatch):
    db,user,cfg=setup; payload=purchase()
    result,calls=created(setup,monkeypatch,payload)
    again=mobile.checkout(payload,request(),user,db)
    assert result == again and len(calls)==1
    row=db.query(LicensePaymentTransaction).one()
    assert json.loads(row.payload_json)['legal_consents']['customer_id']==1
    assert calls[0]['secret']=='fixture-secret' and 'url_result' not in calls[0]
    assert len(calls[0]['label'])<=16 and 'payment-return.html' in calls[0]['url_paid']
    assert 'secret' not in json.dumps(result)

@pytest.mark.parametrize('changes', [dict(accept_terms=False),dict(accept_recurring=False),dict(accept_immediate_service=False),dict(contract_version='old'),dict(expected_amount_halers=1),dict(expected_currency='EUR'),dict(expected_test_mode=True),dict(expected_recurring=False),dict(expected_recurring=None)])
def test_rejects_invalid_order_before_gateway(setup, changes):
    db,user,cfg=setup
    with pytest.raises(HTTPException): mobile.checkout(purchase(**changes),request(),user,db)
    assert db.query(LicensePaymentTransaction).count()==0

def test_ambiguous_network_failure_never_creates_second_charge(setup, monkeypatch):
    db,user,cfg=setup; calls=[]; payload=purchase()
    def fail(*args): calls.append(1); raise HTTPException(503,'timeout')
    monkeypatch.setattr(billing,'_post_comgate',fail)
    for value in [payload,payload,purchase()]:
        with pytest.raises(HTTPException): mobile.checkout(value,request(),user,db)
    assert len(calls)==1

@pytest.mark.parametrize('changes',[dict(status='AUTHORIZED'),dict(status='PENDING'),dict(status='CANCELLED'),dict(price='1'),dict(curr='EUR'),dict(test='true'),dict(merchant='other'),dict(refId='forged'),dict(transId='other')])
def test_unverified_or_unpaid_never_grants_license(setup, monkeypatch, changes):
    db,user,cfg=setup; created(setup,monkeypatch); row=db.query(LicensePaymentTransaction).one()
    monkeypatch.setattr(billing,'_post_comgate',lambda *a: paid_response(row,**changes))
    asyncio.run(billing.comgate_result(request(row.trans_id),db))
    assert db.query(License).one().plan=='free'
    assert not billing._is_trans_already_paid(db,row.trans_id)

def test_paid_activates_once_and_keeps_consents(setup,monkeypatch):
    db,user,cfg=setup; created(setup,monkeypatch); row=db.query(LicensePaymentTransaction).one()
    monkeypatch.setattr(billing,'_post_comgate',lambda *a: paid_response(row))
    assert asyncio.run(billing.comgate_result(request(row.trans_id),db)).status_code==200
    subscription=billing._get_subscription(db,1); end=subscription.current_period_end
    assert db.query(License).one().plan=='basic'
    assert subscription.init_recurring_id == row.trans_id
    monkeypatch.setattr(billing,'_post_comgate',lambda *a: pytest.fail('duplicate gateway call'))
    assert asyncio.run(billing.comgate_result(request(row.trans_id),db)).status_code==200
    assert subscription.current_period_end==end
    assert json.loads(row.payload_json)['legal_consents']['terms'] is True

def test_test_payment_never_grants_real_license(setup,monkeypatch):
    db,user,cfg=setup; cfg['test_mode']=True
    created(setup,monkeypatch,purchase(expected_test_mode=True));row=db.query(LicensePaymentTransaction).one()
    monkeypatch.setattr(billing,'_post_comgate',lambda *a: paid_response(row,test='true'))
    asyncio.run(billing.comgate_result(request(row.trans_id),db))
    assert db.query(License).one().plan=='free'
    assert mobile._transaction(row)['confirmed'] is True
    assert billing._get_subscription(db,1) is None

def test_history_and_refresh_are_tenant_scoped(setup,monkeypatch):
    db,user,cfg=setup; created(setup,monkeypatch)
    other=SimpleNamespace(tenant_id=2)
    assert mobile.transactions(other,db)['items']==[]
    with pytest.raises(HTTPException) as error: asyncio.run(mobile.refresh(1,other,db))
    assert error.value.status_code==404

def test_unknown_transaction_does_not_contact_gateway(setup):
    assert asyncio.run(billing.comgate_result(request('UNKNOWN'),setup[0])).status_code==404

@pytest.mark.parametrize('gateway_test', ['false', 'true'])
def test_restored_cancelled_checkout_can_be_reconciled_across_modes(setup, monkeypatch, gateway_test):
    db,user,cfg=setup; created(setup,monkeypatch)
    row=db.query(LicensePaymentTransaction).one()
    row.payload_json=json.dumps({'code':'0','redirect':'https://pay1.comgate.cz/old'})
    db.commit(); cfg['test_mode']=gateway_test != 'true'
    monkeypatch.setattr(billing,'_post_comgate',lambda *a:paid_response(row,status='CANCELLED',test=gateway_test))
    result=asyncio.run(mobile.refresh(row.id,user,db))
    assert result['status']=='CANCELLED'
    assert db.query(License).one().plan=='free'
    assert json.loads(row.payload_json)['legacy_reconciliation']['status']=='CANCELLED'
    # The historical row is retained, but no longer blocks a new checkout.
    cfg['test_mode']=False
    monkeypatch.setattr(billing,'_post_comgate',lambda *a:dict(code='0',transId='NEW',redirect='https://pay1.comgate.cz/new'))
    mobile.checkout(purchase(),request(),user,db)
    assert db.query(LicensePaymentTransaction).count()==2

@pytest.mark.parametrize('changes', [dict(status='PAID'),dict(status='PENDING'),dict(status='AUTHORIZED'),dict(price='1'),dict(refId='other'),dict(merchant='other'),dict(test='unknown')])
def test_restored_unknown_or_mismatched_payment_stays_blocked(setup, monkeypatch, changes):
    db,user,cfg=setup; created(setup,monkeypatch)
    row=db.query(LicensePaymentTransaction).one(); row.payload_json='{}'; db.commit()
    values=dict(status='CANCELLED'); values.update(changes)
    monkeypatch.setattr(billing,'_post_comgate',lambda *a:paid_response(row,**values))
    assert asyncio.run(billing.comgate_result(request(row.trans_id),db)).status_code==409
    assert row.provider_status=='PENDING'
    assert db.query(License).one().plan=='free'

def test_catalog_and_readiness_do_not_expose_secret(setup):
    db,user,cfg=setup
    assert 'fixture-secret' not in json.dumps(mobile.catalog(request(),user))
    with pytest.raises(HTTPException): mobile.readiness(request(),user)
    user.role='admin'; assert 'fixture-secret' not in json.dumps(mobile.readiness(request(),user))

def test_cancel_keeps_current_paid_period(setup,monkeypatch):
    db,user,cfg=setup; created(setup,monkeypatch); row=db.query(LicensePaymentTransaction).one()
    monkeypatch.setattr(billing,'_post_comgate',lambda *a: paid_response(row))
    asyncio.run(billing.comgate_result(request(row.trans_id),db))
    end=billing._get_subscription(db,1).current_period_end
    billing.cancel_subscription_endpoint(user,db)
    assert db.query(License).one().plan=='basic'
    assert billing._get_subscription(db,1).current_period_end==end
    assert billing._get_subscription(db,1).auto_renew_enabled is False

@pytest.mark.parametrize('url', ['http://payments.comgate.cz/x','https://payments.comgate.cz.evil.test/x','https://comgate.cz@evil.test/x','https://evil.comgate.cz/x'])
def test_gateway_url_rejects_untrusted_hosts(url): assert not billing._valid_gateway_url(url)

def recurring_fixture(setup):
    from datetime import timedelta
    from src.modules.vehicle_hub.models import LicenseSubscription
    db,user,cfg=setup
    sub=LicenseSubscription(tenant_id=1,provider='comgate',status='active',plan_current='basic',billing_period='monthly',auto_renew_enabled=True,
                            init_recurring_id='INITIAL',current_period_start=billing._utcnow()-timedelta(days=31),
                            current_period_end=billing._utcnow()-timedelta(minutes=5),next_charge_at=billing._utcnow()-timedelta(minutes=5))
    db.add(sub);db.commit();return sub

def test_pending_renewal_is_checked_not_charged_again(setup,monkeypatch):
    db,user,cfg=setup;sub=recurring_fixture(setup);calls=[]
    def gateway(url,values):
        calls.append(url)
        if url.endswith('/recurring'): return dict(code='0',transId='RENEWAL')
        row=db.query(LicensePaymentTransaction).one()
        return paid_response(row,status='PENDING')
    monkeypatch.setattr(billing,'_post_comgate',gateway)
    args=dict(cfg=cfg,runtime_cfg={'recurring_url':'https://payments.comgate.cz/v1.0/recurring'},subscription=sub,tenant_id=1,plan='basic',billing_period='monthly',db=db)
    assert billing._charge_subscription_recurring(**args)['pending']
    assert billing._charge_subscription_recurring(**args)['pending']
    assert len([u for u in calls if u.endswith('/recurring')])==1

def test_unknown_renewal_outcome_stays_reserved(setup,monkeypatch):
    db,user,cfg=setup;sub=recurring_fixture(setup);calls=[]
    def gateway(*args): calls.append(1);raise HTTPException(503,'timeout')
    monkeypatch.setattr(billing,'_post_comgate',gateway)
    args=dict(cfg=cfg,runtime_cfg={'recurring_url':'https://payments.comgate.cz/v1.0/recurring'},subscription=sub,tenant_id=1,plan='basic',billing_period='monthly',db=db)
    with pytest.raises(HTTPException):billing._charge_subscription_recurring(**args)
    assert billing._charge_subscription_recurring(**args)['pending']
    assert len(calls)==1

def test_renewal_charges_scheduled_plan_and_applies_only_once(setup,monkeypatch):
    db,user,cfg=setup;sub=recurring_fixture(setup);sub.pending_plan_change='premium';db.commit();calls=[]
    monkeypatch.setattr(billing,'_load_subscription_runtime_config',lambda:dict(recurring_url='https://payments.comgate.cz/v1.0/recurring',grace_days=7,notify_days=[]))
    def gateway(url,values):
        calls.append((url,values))
        if url.endswith('/recurring'):return dict(code='0',transId='RENEWAL')
        row=db.query(LicensePaymentTransaction).filter(LicensePaymentTransaction.trans_id=='RENEWAL').one()
        return paid_response(row,price='29900')
    monkeypatch.setattr(billing,'_post_comgate',gateway)
    result=billing.process_license_subscription_jobs(db)
    assert result['renewal_success']==1
    assert calls[0][1]['price']=='29900'
    assert db.query(License).one().plan=='premium'
    end=sub.current_period_end
    billing.process_license_subscription_jobs(db)
    assert sub.current_period_end==end and len(calls)==2

def test_gateway_status_secret_is_discarded(monkeypatch):
    response=SimpleNamespace(status_code=200,text='code=0&status=PAID&secret=topsecret&payerAcc=private&price=9900')
    monkeypatch.setattr(billing.httpx,'post',lambda *a,**k:response)
    assert billing._post_comgate('https://payments.comgate.cz/v1.0/status',{})==dict(code='0',status='PAID',price='9900')

def test_ledger_failure_rolls_back_license_activation(setup,monkeypatch):
    db,user,cfg=setup;created(setup,monkeypatch);row=db.query(LicensePaymentTransaction).one()
    monkeypatch.setattr(billing,'_post_comgate',lambda *a:paid_response(row))
    def fail(*a,**k):raise RuntimeError('simulated ledger failure')
    monkeypatch.setattr(billing,'_record_payment_transaction',fail)
    response=asyncio.run(billing.comgate_result(request(row.trans_id),db))
    assert response.status_code==503
    assert db.query(License).one().plan=='free'
    assert billing._get_subscription(db,1) is None
    assert not billing._is_trans_already_paid(db,row.trans_id)

def test_admin_settings_are_write_only_and_keep_saved_secret(monkeypatch):
    from src.server import admin_api
    values={'comgate':{'secret':{'value':'fixture-secret','value_type':'string'},'merchant':{'value':'507933','value_type':'string'}}}
    monkeypatch.setattr(admin_api,'load_admin_settings',lambda:values)
    saved=[];monkeypatch.setattr(admin_api,'save_admin_settings',lambda value:saved.append(value))
    public=admin_api.get_admin_settings(email='admin@example.invalid',db=None)
    assert 'fixture-secret' not in json.dumps(public)
    payload=admin_api.SettingsUpdatePayload(settings=[dict(category='comgate',key='secret',value='••••••••',value_type='string')])
    result=admin_api.update_admin_settings(payload,email='admin@example.invalid',db=None)
    assert saved[0]['comgate']['secret']['value']=='fixture-secret'
    assert 'fixture-secret' not in json.dumps(result)

def test_connection_check_is_admin_only_and_does_not_create_payment(setup,monkeypatch):
    db,user,cfg=setup
    with pytest.raises(HTTPException):mobile.connection_check(user)
    user.role='admin';calls=[]
    def response(url,**kwargs):
        calls.append(url);return SimpleNamespace(status_code=200,json=lambda:{'methods':[{'id':'CARD_CZ_COMGATE'}]})
    monkeypatch.setattr(billing.httpx,'post',response)
    assert mobile.connection_check(user)['ok']
    assert calls==['https://payments.comgate.cz/v1.0/methods']
    assert db.query(LicensePaymentTransaction).count()==0

def test_active_subscription_cannot_be_purchased_twice(setup,monkeypatch):
    db,user,cfg=setup;created(setup,monkeypatch);row=db.query(LicensePaymentTransaction).one()
    monkeypatch.setattr(billing,'_post_comgate',lambda *a:paid_response(row))
    asyncio.run(billing.comgate_result(request(row.trans_id),db))
    monkeypatch.setattr(billing,'_post_comgate',lambda *a:pytest.fail('duplicate purchase'))
    with pytest.raises(HTTPException) as error:mobile.checkout(purchase(),request(),user,db)
    assert error.value.status_code==409

def test_definite_rejection_releases_pending_order(setup,monkeypatch):
    db,user,cfg=setup
    monkeypatch.setattr(billing,'_post_comgate',lambda *a:dict(code='1301',message='unknown merchant'))
    with pytest.raises(HTTPException):mobile.checkout(purchase(),request(),user,db)
    assert db.query(LicensePaymentTransaction).one().provider_status=='CANCELLED'

def legacy_subscription(setup):
    from src.modules.vehicle_hub.models import LicenseSubscription
    db, user, cfg = setup
    sub = LicenseSubscription(tenant_id=1, provider='comgate', status='legacy_manual',
        plan_current='basic', billing_period='monthly', auto_renew_enabled=False,
        credit_balance_halers=1)
    db.add(sub); db.commit()
    return sub

def test_legacy_one_time_payment_never_requests_recurring_authority(setup, monkeypatch):
    db, user, cfg = setup
    sub = legacy_subscription(setup)
    user.phone = '+420777000000'
    quote = mobile.quote(mobile.Selection(plan='basic'), user, db)
    assert quote['recurring'] is False and quote['amount_halers'] == 9899
    result, calls = created(setup, monkeypatch, purchase(expected_amount_halers=9899,
        expected_recurring=False, accept_recurring=False))
    assert 'initRecurring' not in calls[0] and 'phone' not in calls[0]
    assert calls[0]['method'] == cfg['method']
    row = db.query(LicensePaymentTransaction).one()
    details = json.loads(row.payload_json)
    assert details['checkout_recurring'] is False
    assert details['legal_consents']['recurring'] is False
    monkeypatch.setattr(billing, '_post_comgate', lambda *a: paid_response(row, price='9899'))
    assert asyncio.run(billing.comgate_result(request(row.trans_id), db)).status_code == 200
    assert sub.auto_renew_enabled is False and not sub.init_recurring_id

def test_one_time_quote_cannot_silently_become_recurring(setup):
    db, user, cfg = setup
    sub = legacy_subscription(setup)
    quote = mobile.quote(mobile.Selection(plan='basic'), user, db)
    # Change between displaying the quote and submitting the checkout, at the same price.
    sub.status = 'canceled'; sub.credit_balance_halers = 0; db.commit()
    with pytest.raises(HTTPException) as error:
        mobile.checkout(purchase(expected_recurring=quote['recurring']), request(), user, db)
    assert error.value.status_code == 409
    assert db.query(LicensePaymentTransaction).count() == 0

def test_recurring_checkout_requests_only_consented_authority(setup, monkeypatch):
    db, user, cfg = setup
    _, calls = created(setup, monkeypatch)
    assert calls[0]['initRecurring'] == 'true'
    assert json.loads(db.query(LicensePaymentTransaction).one().payload_json)['legal_consents']['recurring'] is True
