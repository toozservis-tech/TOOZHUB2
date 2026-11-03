"""Referral qualification, money isolation, immutable attribution and role boundaries."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import Customer, Tenant, Vehicle, VehicleOwnership, License, ServiceRegistrationRequest, ServiceAccessRequest
from src.modules.vehicle_hub.email_verification import EmailVerification
from src.modules.vehicle_hub.service_job_models import ServiceJob
from src.modules.vehicle_hub import referrals as r
from src.modules.vehicle_hub.routers_v1 import referrals as api
from src.modules.licensing.service import get_license_status, has_customer_feature, assert_vehicle_quota

@pytest.fixture
def state():
    engine=create_engine('sqlite://')
    Base.metadata.create_all(engine)
    db=sessionmaker(bind=engine)()
    def customer(n,role='user',tenant=None):
        if tenant is None:
            t=Tenant(name=f'Tenant {n}',license_key=f'key-{n}');db.add(t);db.flush();tenant=t.id
        c=Customer(tenant_id=tenant,email=f'qa-{n}@example.com',name=f'Test {n}',role=role,password_hash='hash')
        db.add(c);db.flush();return c
    owner=customer('owner');admin=customer('admin','admin');foreign=customer('foreign',tenant=owner.tenant_id)
    db.add(License(tenant_id=owner.tenant_id,plan='free',status='active',vehicles_limit=1))
    db.commit()
    yield SimpleNamespace(db=db,owner=owner,admin=admin,foreign=foreign,customer=customer,engine=engine)
    db.close();engine.dispose()

def activate(s,c,verify=True):
    if verify:s.db.add(EmailVerification(customer_id=c.id,verified_at=datetime.utcnow()))
    v=Vehicle(tenant_id=c.tenant_id,user_email=c.email,vin=f'QA{c.id:015}',nickname='Ukázka')
    s.db.add(v);s.db.flush()
    s.db.add(VehicleOwnership(tenant_id=c.tenant_id,vehicle_id=v.id,customer_id=c.id,ownership_type='owner',is_primary=True,is_active=True))
    s.db.commit();return v

def invite(s,n,verify=True):
    code=r.code_for(s.db,s.owner);c=s.customer(n);r.attach(s.db,code,customer=c);activate(s,c,verify);return c

def test_unique_personal_code_share_no_reward_no_private_identity(state):
    s=state
    first=api.my_referrals(s.owner,s.db)
    assert first['code']==api.my_referrals(s.owner,s.db)['code']
    assert first['code']!=api.my_referrals(s.foreign,s.db)['code']
    page=api.join(first['code'],'service',s.db).body.decode()
    assert s.owner.email not in page and s.owner.name not in page
    assert 'spravavozidel://referral?' in page and s.db.query(r.ReferralReward).count()==0
    assert '/web/customer.html#referral=' in page and '&amp;kind=service' in page
    assert s.db.query(ServiceAccessRequest).count()==0

def test_three_verified_vehicle_owners_award_once_and_every_three(state):
    s=state
    for n in range(2):invite(s,str(n))
    assert api.my_referrals(s.owner,s.db)['rewards']==[]
    invite(s,'third',verify=False)
    assert api.my_referrals(s.owner,s.db)['rewards']==[]
    c=s.db.query(Customer).filter_by(email='qa-third@example.com').one()
    s.db.add(EmailVerification(customer_id=c.id,verified_at=datetime.utcnow()));s.db.commit()
    result=api.my_referrals(s.owner,s.db)
    assert len(result['rewards'])==1 and result['qualified_users']==3
    assert all(x['email'] is None and x['name'] is None for x in result['referrals'])
    for _ in range(3):api.my_referrals(s.owner,s.db)
    assert s.db.query(r.ReferralReward).count()==1
    for n in range(3,6):invite(s,str(n))
    result=api.my_referrals(s.owner,s.db)
    assert len(result['rewards'])==2
    a,b=s.db.query(r.ReferralReward).order_by(r.ReferralReward.id).all()
    assert a.ends_at==b.starts_at
    assert r.next_month(datetime(2027,1,31,8,10))==datetime(2027,2,28,8,10)

def test_server_license_unlocks_only_inviter_not_other_account_in_tenant(state):
    s=state
    for n in range(3):invite(s,str(n))
    result=get_license_status(s.db,s.owner.tenant_id,s.owner.email)
    assert result['plan']=='premium' and result['vehicles_limit']==0 and result['statistics_enabled']
    assert has_customer_feature(s.db,s.owner,'statistics')
    assert not has_customer_feature(s.db,s.foreign,'statistics')
    assert get_license_status(s.db,s.foreign.tenant_id,s.foreign.email)['plan']=='free'
    paid=s.db.query(License).filter_by(tenant_id=s.owner.tenant_id).one()
    assert paid.plan=='free' and paid.valid_to is None
    activate(s,s.owner)
    assert_vehicle_quota(s.db,s.owner.tenant_id,customer=s.owner)
    with pytest.raises(HTTPException):assert_vehicle_quota(s.db,s.foreign.tenant_id,customer=s.foreign)
    reward=s.db.query(r.ReferralReward).one();reward.ends_at=datetime.utcnow()-timedelta(seconds=1);s.db.commit()
    assert get_license_status(s.db,s.owner.tenant_id,s.owner.email)['plan']=='free'

def test_paid_premium_is_not_overwritten_rewards_queue_and_no_transfer(state):
    s=state;paid=s.db.query(License).one();paid.plan='premium';paid.valid_to=datetime(2028,2,5);s.db.commit()
    for n in range(3):invite(s,str(n))
    api.my_referrals(s.owner,s.db)
    reward=s.db.query(r.ReferralReward).one()
    assert reward.starts_at==datetime(2028,2,5) and reward.ends_at==datetime(2028,3,5)
    s.db.refresh(paid);assert paid.plan=='premium' and paid.valid_to==datetime(2028,2,5)

def test_service_requires_approval_verified_email_and_completed_job(state):
    s=state;code=r.code_for(s.db,s.owner)
    req=ServiceRegistrationRequest(status='pending',email='new-workshop@example.com',password_hash='hash',ico='12345678',service_name='Nový servis',responsible_person='Test Servis',phone='+420777777777',street='Testovací',city='Praha',zip='11000',registration_purpose='Servisní práce')
    s.db.add(req);s.db.flush();r.attach(s.db,code,service_request=req);s.db.commit()
    assert api.my_referrals(s.owner,s.db)['qualified_services']==0
    c=s.customer('service','service');req.status='approved';req.approved_customer_id=c.id;s.db.commit()
    v=activate(s,c)
    assert api.my_referrals(s.owner,s.db)['qualified_services']==0
    job=ServiceJob(tenant_id=c.tenant_id,service_id=c.id,vehicle_id=v.id,client_id=str(uuid4()),creation_hash='hash',title='Oprava',status='completed',completed_at=datetime.utcnow())
    s.db.add(job);s.db.commit()
    result=api.my_referrals(s.owner,s.db)
    assert result['qualified_services']==1 and len(result['rewards'])==1
    assert s.db.query(ServiceAccessRequest).count()==0

def test_admin_award_idempotent_audited_and_revoked_not_reissued(state):
    s=state
    payload=api.GrantInput(request_id=uuid4(),kind='lifetime',reason='Aktivní přivádění nových zákazníků')
    with pytest.raises(HTTPException) as error:api.admin_reward(s.owner.id,payload,s.foreign,s.db)
    assert error.value.status_code==403
    first=api.admin_reward(s.owner.id,payload,s.admin,s.db)
    assert api.admin_reward(s.owner.id,payload,s.admin,s.db)['id']==first['id']
    assert first['lifetime'] and get_license_status(s.db,s.owner.tenant_id,s.owner.email)['plan']=='premium'
    api.revoke_reward(s.owner.id,first['id'],api.RevokeInput(reason='Chybné přidělení při testu'),s.admin,s.db)
    assert get_license_status(s.db,s.owner.tenant_id,s.owner.email)['plan']=='free'
    with pytest.raises(HTTPException):api.admin_detail(s.owner.id,s.foreign,s.db)
    data=api.admin_detail(s.owner.id,s.admin,s.db)
    assert data['email']==s.owner.email

def test_self_invitation_and_invalid_code_rejected(state):
    s=state;code=r.code_for(s.db,s.owner)
    with pytest.raises(HTTPException):r.attach(s.db,code,customer=s.owner)
    with pytest.raises(HTTPException):r.attach(s.db,'non-existing-code',customer=s.foreign)
    assert s.db.query(r.Referral).count()==0

def test_deleted_or_disabled_invitee_never_qualifies(state):
    s=state
    for n in range(3):
        c=invite(s,str(n));c.is_disabled=True
    s.db.commit()
    assert not api.my_referrals(s.owner,s.db)['rewards']

def test_migration_idempotent(state):
    from scripts.migrate_referrals import migrate
    s=state;r.code_for(s.db,s.owner);s.db.commit()
    migrate(s.engine);migrate(s.engine)
    assert s.db.query(r.ReferralCode).count()==1

def test_concurrent_reconciliation_does_not_grant_twice(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    engine=create_engine('sqlite:///'+str(tmp_path/'race.sqlite'),connect_args={'timeout':20})
    Base.metadata.create_all(engine);factory=sessionmaker(bind=engine)
    with factory() as db:
        tenant=Tenant(name='Race',license_key='race');db.add(tenant);db.flush()
        owner=Customer(tenant_id=tenant.id,email='race@example.com',role='user');db.add(owner);db.flush();owner_id=owner.id
        for i in range(3):
            c=Customer(tenant_id=tenant.id,email=f'race-{i}@example.com',role='user');db.add(c);db.flush()
            db.add(r.Referral(referrer_id=owner.id,customer_id=c.id,kind='user',qualified_at=datetime.utcnow(),reason='qualified'))
        db.commit()
    barrier=Barrier(2)
    def worker():
        with factory() as db:
            owner=db.get(Customer,owner_id);barrier.wait()
            r.evaluate(db,owner);db.commit()
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs=[pool.submit(worker),pool.submit(worker)]
        for job in jobs:job.result(timeout=25)
    with factory() as db:assert db.query(r.ReferralReward).count()==1
    engine.dispose()

def test_revocation_never_regrants_automatic_award(state):
    s=state
    for n in range(3):invite(s,str(n))
    response=api.my_referrals(s.owner,s.db);id=response['rewards'][0]['id']
    api.revoke_reward(s.owner.id,id,api.RevokeInput(reason='Zjištěné duplicitní účty'),s.admin,s.db)
    for _ in range(3):api.my_referrals(s.owner,s.db)
    assert s.db.query(r.ReferralReward).count()==1
    assert r.active_reward(s.db,s.owner) is None

def test_invalid_deep_link_code_and_disabled_owner_are_not_public(state):
    s=state;code=r.code_for(s.db,s.owner);s.owner.is_disabled=True;s.db.commit()
    with pytest.raises(HTTPException) as error:api.join(code,'user',s.db)
    assert error.value.status_code==404


def test_qualifying_event_grants_without_inviter_opening_profile(state):
    s=state
    for n in range(3):
        c=invite(s,'event-'+str(n))
        r.evaluate_for_customer(s.db,c.id)
        s.db.commit()
    assert s.db.query(r.ReferralReward).count()==1
    assert s.db.query(r.Referral).filter(r.Referral.qualified_at.isnot(None)).count()==3
    r.evaluate_for_customer(s.db,c.id);s.db.commit()
    assert s.db.query(r.ReferralReward).count()==1


def test_admin_missing_recipient_returns_404(state):
    s=state
    with pytest.raises(HTTPException) as error:
        api.admin_reward(999999,api.GrantInput(request_id=uuid4(),kind='month',reason='Kontrola neexistujícího účtu'),s.admin,s.db)
    assert error.value.status_code==404


def test_paid_renewal_keeps_month_waiting_then_releases_whole_month(state):
    s=state;paid=s.db.query(License).one();paid.plan='premium';paid.valid_to=datetime(2028,11,30);s.db.commit()
    for n in range(3):invite(s,'renewal-'+str(n))
    r.evaluate(s.db,s.owner,now=datetime(2028,11,15));s.db.commit()
    reward=s.db.query(r.ReferralReward).one()
    assert reward.waiting_for_paid and reward.starts_at==datetime(2028,11,30)
    paid.valid_to=datetime(2028,12,30);s.db.commit()
    r.evaluate(s.db,s.owner,now=datetime(2028,12,15));s.db.commit()
    assert reward.waiting_for_paid and r.active_reward(s.db,s.owner,now=datetime(2028,12,15)) is None
    assert reward.starts_at==datetime(2028,12,30)
    paid.plan='free';paid.valid_to=None;s.db.commit()
    r.evaluate(s.db,s.owner,now=datetime(2029,1,5));s.db.commit()
    assert not reward.waiting_for_paid
    assert reward.starts_at==datetime(2029,1,5) and reward.ends_at==datetime(2029,2,5)
    assert s.db.query(r.ReferralReward).count()==1


def test_administrator_reason_cannot_be_only_whitespace():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):api.GrantInput(request_id=uuid4(),kind='month',reason='      ')
    with pytest.raises(ValidationError):api.RevokeInput(reason='      ')


def test_migration_upgrades_previous_reward_table_without_losing_history(state):
    from sqlalchemy import text, inspect
    from scripts.migrate_referrals import migrate
    s=state
    reward=r.grant(s.db,s.owner,source='admin',ordinal=1,reason='Historická odměna')
    reward_id=reward.id;s.db.commit();s.db.close()
    with s.engine.begin() as connection:
        connection.execute(text('ALTER TABLE referral_rewards DROP COLUMN waiting_for_paid'))
    assert 'waiting_for_paid' not in {c['name'] for c in inspect(s.engine).get_columns('referral_rewards')}
    migrate(s.engine);migrate(s.engine)
    reward=s.db.get(r.ReferralReward,reward_id)
    assert reward.reason=='Historická odměna' and reward.waiting_for_paid is False


def test_license_read_commits_legacy_ownership_before_activity_writer(tmp_path):
    """A legacy car must not leave a write lock while response activity is logged."""
    from sqlalchemy import update
    from src.modules.licensing.service import get_or_create_license
    engine = create_engine('sqlite:///' + str(tmp_path / 'legacy.sqlite'), connect_args={'timeout': 0.1})
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as reader:
        tenant = Tenant(name='Legacy QA', license_key='legacy-qa')
        reader.add(tenant); reader.flush()
        customer = Customer(tenant_id=tenant.id, email='legacy-qa@example.com',
                            name='Legacy QA', role='user', password_hash='hash')
        reader.add(customer); reader.flush()
        car = Vehicle(tenant_id=tenant.id, user_email=customer.email,
                      vin='QALEGACY000000001', nickname='Legacy car')
        reader.add(car); reader.commit()
        get_or_create_license(reader, tenant.id)
        tenant_id, customer_id, email = tenant.id, customer.id, customer.email
        result = get_license_status(reader, tenant_id, email)
        assert result['vehicles_current_user'] == 1
        # The request reader intentionally remains open, as in the ASGI middleware.
        with factory() as writer:
            assert writer.query(VehicleOwnership).filter_by(customer_id=customer_id).count() == 1
            writer.execute(update(Customer).where(Customer.id == customer_id).values(name='Activity writer'))
            writer.commit()
    engine.dispose()
