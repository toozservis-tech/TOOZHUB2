"""Real erasure transactions against disposable SQLite with all FK checks on."""
import json
from datetime import datetime, timedelta
from uuid import uuid4
from unittest.mock import patch

import httpx
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from src.core import file_erasure, file_storage
from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub import models as m
from src.modules.vehicle_hub.account_erasure import erase_account
from src.modules.vehicle_hub.email_verification import EmailVerification
from src.modules.licensing.apple_models import AppleBillingIdentity, AppleSubscription


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    engine = create_engine('sqlite:///' + str(tmp_path / 'fixture.sqlite'))
    event.listen(engine, 'connect', lambda db, _: db.execute('PRAGMA foreign_keys=ON'))
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = factory()
    root = tmp_path / 'private'
    root.mkdir()
    monkeypatch.setattr(file_storage, 'DATA_DIR', root)
    monkeypatch.setattr(file_storage, '_config', lambda: None)
    def add(model, **values):
        row = model(**values); db.add(row); db.flush(); return row
    tenant = add(m.Tenant, name='Delete owner', license_key=uuid4().hex)
    other_tenant = add(m.Tenant, name='Keep organisation', license_key=uuid4().hex)
    owner = add(m.Customer, tenant_id=tenant.id, email='erase@example.invalid', name='Private owner')
    other = add(m.Customer, tenant_id=other_tenant.id, email='keep@example.invalid', name='Keep owner')
    service = add(m.Customer, tenant_id=other_tenant.id, email='service@example.invalid', role='service')
    car = add(m.Vehicle, tenant_id=tenant.id, user_email=owner.email, plate='ERASE')
    keep_car = add(m.Vehicle, tenant_id=tenant.id, user_email='wrong-legacy@example.invalid', plate='KEEP')
    add(m.VehicleOwnership, tenant_id=tenant.id, customer_id=owner.id, vehicle_id=car.id,
        assigned_by_customer_id=owner.id, ownership_type='owner')
    add(m.VehicleOwnership, tenant_id=tenant.id, customer_id=other.id, vehicle_id=keep_car.id,
        assigned_by_customer_id=owner.id, ownership_type='owner')
    record = add(m.ServiceRecord, tenant_id=tenant.id, vehicle_id=keep_car.id, user_id=other.id,
                 description='Preserve somebody else’s history', deleted_by_user_id=owner.id)
    def write(directory, name):
        path=root/directory/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b'fixture-private-content')
        return path
    db.commit()
    yield db, factory, add, write, owner, other, service, car, keep_car, record
    db.close(); engine.dispose()


def full_graph(f):
    db, _, add, write, owner, other, service, car, _, _=f
    paths=[]
    car.photo_path='cover.jpg'; paths.append(write('vehicle_photos','cover.jpg'))
    scan=add(m.VehicleORVScan,tenant_id=owner.tenant_id,vehicle_id=car.id,initiated_by_customer_id=owner.id,
             front_image_path='scan/front.jpg',back_image_path='scan/back.jpg',parsed_owner_json='{"name":"Private"}')
    car.orv_front_image_path=scan.front_image_path; car.orv_back_image_path=scan.back_image_path
    paths += [write('vehicle_orv_scans',scan.front_image_path),write('vehicle_orv_scans',scan.back_image_path)]
    visit=add(m.RepairPhotoSession,vehicle_id=car.id,service_id=service.id,title='Fixture',client_id=str(uuid4()))
    add(m.RepairEvidencePhoto,session_id=visit.id,author_id=service.id,author_name='Fixture',phase='before',
        note='Private note',source='camera',sha256='a'*64,file_path='repair.jpg',mime_type='image/jpeg',size_bytes=1,client_id=str(uuid4()))
    paths.append(write('private_repair_photos','repair.jpg'))
    lookup=add(m.ServiceVehicleLookupAudit,tenant_id=owner.tenant_id,service_customer_id=service.id,
        matched_owner_customer_id=owner.id,matched_vehicle_id=car.id)
    request=add(m.ServiceAccessRequest,tenant_id=owner.tenant_id,service_customer_id=service.id,
        owner_customer_id=owner.id,vehicle_id=car.id,lookup_audit_id=lookup.id,decided_by_customer_id=owner.id)
    link=add(m.VehicleServiceLink,tenant_id=owner.tenant_id,service_customer_id=service.id,
        owner_customer_id=owner.id,vehicle_id=car.id,source_request_id=request.id,approved_by_customer_id=owner.id)
    record=add(m.ServiceRecord,tenant_id=owner.tenant_id,vehicle_id=car.id,user_id=owner.id,description='Delete',
        service_access_link_id=link.id,created_by_service_customer_id=service.id,
        attachments=json.dumps([{'storage_key':'invoice.pdf'}]))
    paths.append(write('service_record_attachments','invoice.pdf'))
    add(m.ServiceRecordAuditLog,tenant_id=owner.tenant_id,service_record_id=record.id,vehicle_id=car.id,
        changed_by_user_id=owner.id,previous_snapshot_json=json.dumps({'attachments':[{'storage_key':'old.pdf'}]}))
    paths.append(write('service_record_attachments','old.pdf'))
    docpath=write('service_workspace_docs','ingest.pdf');paths.append(docpath)
    add(m.ServiceDocumentIngestion,service_tenant_id=service.tenant_id,service_customer_id=service.id,
        customer_id=owner.id,vehicle_id=car.id,auto_created_service_record_id=record.id,stored_file_path=str(docpath))
    add(m.VehicleTachometerHistoryEntry,tenant_id=owner.tenant_id,vehicle_id=car.id,raw_payload_json='{}')
    add(m.ServiceIntake,tenant_id=owner.tenant_id,service_id=service.id,customer_id=owner.id,vehicle_id=car.id)
    add(m.Reservation,tenant_id=owner.tenant_id,service_id=service.id,customer_id=owner.id,vehicle_id=car.id,
        start_datetime=datetime.utcnow())
    add(m.Reminder,tenant_id=owner.tenant_id,customer_id=owner.id,vehicle_id=car.id,type='GENERAL',text='Private',due_date=datetime.utcnow().date())
    add(m.ServiceVehicleAccess,service_customer_id=service.id,customer_id=owner.id,vehicle_id=car.id,granted_by_customer_id=owner.id)
    add(m.ServiceCustomerLink,service_tenant_id=service.tenant_id,service_customer_id=service.id,
        customer_tenant_id=owner.tenant_id,customer_id=owner.id)
    add(m.ServiceCustomerInvite,service_tenant_id=service.tenant_id,service_customer_id=service.id,
        invite_email=owner.email,token=uuid4().hex,linked_customer_id=owner.id)
    add(m.EmailNotificationLog,tenant_id=owner.tenant_id,customer_id=owner.id,email=owner.email,
        subject='Fixture',notification_type='fixture')
    add(m.SecurityAccessLog,tenant_id=owner.tenant_id,customer_id=owner.id,user_email=owner.email,
        endpoint='/fixture',event_type='fixture')
    add(m.BotCommand,tenant_id=owner.tenant_id,user_id=owner.id,user_email=owner.email,raw_text='Private')
    add(m.CustomerCommand,tenant_id=owner.tenant_id,vehicle_id=car.id,customer_email=owner.email,
        raw_text='Private',source='fixture',intent_type='QUESTION')
    add(m.CustomerSecuritySettings,tenant_id=owner.tenant_id,customer_id=owner.id)
    add(m.PushSubscription,tenant_id=owner.tenant_id,customer_id=owner.id,
        endpoint='https://push.example.invalid/fixture',p256dh='fixture',auth='fixture')
    add(EmailVerification,customer_id=owner.id)
    add(m.DeveloperActionAuditLog,developer_id=owner.id,developer_email=owner.email,
        action_type='fixture',target_resource='fixture')
    add(m.SystemNotification,created_by_customer_id=owner.id,message='Private')
    add(m.SecurityBlockedIp,ip_address='192.0.2.42',blocked_by_customer_id=owner.id,blocked_by_email=owner.email)
    add(m.Instance,tenant_id=owner.tenant_id,device_id='private-device')
    add(m.LicenseSubscription,tenant_id=owner.tenant_id,status='active',auto_renew_enabled=True,
        init_recurring_id='private-recurring',next_charge_at=datetime.utcnow())
    add(m.LicensePaymentTransaction,tenant_id=owner.tenant_id,trans_id='paid-fixture',amount_halers=100,event_type='paid')
    identity=add(AppleBillingIdentity,token=str(uuid4()),customer_id=owner.id,tenant_id=owner.tenant_id)
    add(AppleSubscription,id='Sandbox:fixture',account_token=identity.token,environment='Sandbox',
        original_transaction_id='fixture',transaction_id='fixture',product_id='fixture',plan='basic',period='monthly',
        status=1,signed_date=1,expires_at=datetime.utcnow(),access_until=datetime.utcnow())
    db.commit()
    return paths,identity.token


def test_complete_graph_erases_only_own_data_and_files_after_commit(fixture):
    db,factory,_,_,owner,other,service,car,keep_car,keep_record=fixture
    paths,token=full_graph(fixture)
    owner_id,car_id=owner.id,car.id
    counts=erase_account(db,owner)
    assert counts['customers']==1 and counts['vehicles']==1
    assert all(path.exists() for path in paths), 'No irreversible I/O before transaction commit'
    db.commit();db.expire_all()
    assert db.get(m.Customer,owner_id) is None
    assert db.get(m.Customer,other.id) and db.get(m.Customer,service.id)
    assert db.get(m.Vehicle,car_id) is None
    assert db.get(m.Vehicle,keep_car.id).plate=='KEEP', 'A last customer is not authority to erase the whole tenant'
    assert db.get(m.ServiceRecord,keep_record.id).description=='Preserve somebody else’s history'
    assert db.get(m.ServiceRecord,keep_record.id).deleted_by_user_id is None
    assert db.get(AppleBillingIdentity,token).customer_id is None
    assert db.get(AppleBillingIdentity,token).tenant_id is None
    assert db.query(AppleSubscription).count()==1 and db.query(m.LicensePaymentTransaction).count()==1
    subscription=db.query(m.LicenseSubscription).one()
    assert not subscription.auto_renew_enabled and subscription.next_charge_at is None and subscription.init_recurring_id is None
    assert db.query(file_erasure.FileErasure).count()==len(paths)
    result=file_erasure.process_file_erasures(session_factory=factory,limit=30,now=datetime.utcnow()+timedelta(seconds=1))
    assert result=={'removed':len(paths),'retrying':0}
    assert all(not path.exists() for path in paths)


def test_delegate_never_erases_vehicle_or_another_authors_records(fixture):
    db,_,add,_,owner,other,_,car,keep_car,_=fixture
    db.query(m.VehicleOwnership).filter_by(customer_id=owner.id,vehicle_id=car.id).update({'ownership_type':'delegated'})
    add(m.VehicleOwnership,tenant_id=owner.tenant_id,vehicle_id=car.id,customer_id=other.id,ownership_type='owner')
    db.commit();erase_account(db,owner);db.commit()
    assert db.query(m.Vehicle).count()==2
    assert db.query(m.VehicleOwnership).filter_by(customer_id=other.id).count()==2


def test_coowner_survives_and_becomes_primary(fixture):
    db,_,add,_,owner,other,_,car,_,_=fixture
    assignment=add(m.VehicleOwnership,tenant_id=owner.tenant_id,vehicle_id=car.id,customer_id=other.id,
                   ownership_type='owner',is_primary=False)
    db.commit();erase_account(db,owner);db.commit();db.expire_all()
    assert db.get(m.Vehicle,car.id).user_email==other.email
    assert db.get(m.VehicleOwnership,assignment.id).is_primary


def test_service_erasure_removes_its_evidence_not_customer_car(fixture):
    db,_,_,_,owner,_,service,car,_,_=fixture
    full_graph(fixture)
    erase_account(db,service);db.commit();db.expire_all()
    assert db.get(m.Customer,owner.id) and db.get(m.Vehicle,car.id)
    assert db.query(m.RepairEvidencePhoto).count()==0 and db.query(m.RepairPhotoSession).count()==0
    assert db.query(m.ServiceRecord).count()==1


def test_rollback_preserves_identity_and_original_files(fixture):
    db,_,_,_,owner,_,_,_,_,_=fixture
    paths,_=full_graph(fixture)
    erase_account(db,owner);db.rollback()
    assert db.get(m.Customer,owner.id)
    assert db.query(file_erasure.FileErasure).count()==0
    assert all(path.exists() for path in paths)


def test_shared_attachment_is_not_removed(fixture):
    db,_,add,write,owner,_,_,car,_,keep_record=fixture
    path=write('service_record_attachments','shared.pdf')
    payload=json.dumps([{'storage_key':'shared.pdf'}]);keep_record.attachments=payload
    add(m.ServiceRecord,tenant_id=owner.tenant_id,vehicle_id=car.id,user_id=owner.id,description='Own',attachments=payload)
    db.commit();erase_account(db,owner);db.commit()
    assert db.query(file_erasure.FileErasure).count()==0 and path.exists()


def test_receipt_proves_completion_without_retaining_account_identity(fixture):
    db,factory,_,_,owner,_,_,_,_,_=fixture
    full_graph(fixture)
    erase_account(db,owner)
    receipt=db.info['account_erasure_receipt'];db.commit()
    assert len(receipt)==43
    assert file_erasure.receipt_status(db,'A'*43) is None
    status=file_erasure.receipt_status(db,receipt)
    assert not status['completed'] and status['files_pending']>0
    saved=db.query(file_erasure.AccountErasureReceipt).one()
    assert receipt!=saved.token_digest
    assert 'email' not in saved.paths_json and '@' not in saved.paths_json
    file_erasure.process_file_erasures(session_factory=factory,limit=30,now=datetime.utcnow()+timedelta(seconds=1))
    db.expire_all()
    status=file_erasure.receipt_status(db,receipt)
    assert status['completed'] and status['files_pending']==0
    assert db.query(file_erasure.AccountErasureReceipt).one().paths_json=='[]'


def test_receipt_status_api_needs_secret_receipt_not_deleted_login(fixture):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.modules.vehicle_hub.database import get_db
    from src.server.routers import user_account
    from src.core.rate_limiter import rate_limiter
    db,factory,_,_,owner,_,_,_,_,_=fixture
    erase_account(db,owner);receipt=db.info['account_erasure_receipt'];db.commit()
    app=FastAPI();app.include_router(user_account.router)
    def test_db():
        with factory() as session: yield session
    app.dependency_overrides[get_db]=test_db
    rate_limiter.clear()

    with TestClient(app) as client:
        response=client.post('/user/account-erasure/status',json={'receipt':receipt})
        assert response.status_code==200 and response.json()['completed']
        assert response.headers['cache-control']=='no-store'
        assert client.post('/user/account-erasure/status',json={'receipt':'A'*43}).status_code==404
        assert client.post('/user/account-erasure/status',json={'receipt':'1'}).status_code==422
    rate_limiter.clear()


def test_delayed_comgate_confirmation_cannot_restore_renewal_after_erasure(fixture):
    from src.modules.vehicle_hub.routers_v1 import license_status as billing
    db,_,_,_,owner,_,_,_,_,_=fixture
    full_graph(fixture)
    tenant_id=owner.tenant_id
    erase_account(db,owner);db.commit()
    with patch.object(billing,'upgrade_license_plan') as upgrade:
        subscription=billing._activate_subscription_from_paid_payment(db,tenant_id=tenant_id,
            plan='premium',billing_period='monthly',trans_id='delayed-fixture',init_recurring_id='must-not-be-restored')
        db.commit()
        upgrade.assert_not_called()
    assert subscription.status=='canceled'
    assert not subscription.auto_renew_enabled and subscription.next_charge_at is None and subscription.init_recurring_id is None


def test_shared_tenant_does_not_cancel_other_accounts_subscription(fixture):
    from src.modules.vehicle_hub.account_erasure import ErasedTenant
    db,_,add,_,owner,_,_,_,_,_=fixture
    full_graph(fixture)
    add(m.Customer,tenant_id=owner.tenant_id,email='same-tenant@example.invalid')
    db.commit();erase_account(db,owner);db.commit()
    assert db.query(ErasedTenant).count()==0
    assert db.query(m.LicenseSubscription).one().auto_renew_enabled


def test_symlink_outside_private_storage_never_removes_target(fixture,tmp_path):
    db,_,_,_,_,_,_,_,_,_=fixture
    outside=tmp_path/'outside';outside.mkdir();target=outside/'keep.txt';target.write_text('keep')
    (file_storage.DATA_DIR/'vehicle_photos').symlink_to(outside,target_is_directory=True)
    with pytest.raises(ValueError): file_erasure.enqueue_file_erasure(db,'vehicle_photos','keep.txt')
    assert target.read_text()=='keep'


@pytest.mark.parametrize('raw',['../outside.txt','/tmp/outside.txt','nested/../../outside.txt','nested\\..\\..\\outside.txt'])
def test_invalid_private_path_never_queues_or_deletes(fixture,raw):
    db,_,_,_,owner,_,_,car,_,_=fixture
    car.photo_path=raw;db.commit()
    with pytest.raises(ValueError): erase_account(db,owner)
    db.rollback(); assert db.get(m.Customer,owner.id)
    assert db.query(file_erasure.FileErasure).count()==0


def test_storage_failure_retries_after_restart_without_losing_request(fixture,monkeypatch):
    db,factory,_,write,_,_,_,_,_,_=fixture
    path=write('vehicle_photos','retry.jpg')
    file_erasure.enqueue_file_erasure(db,'vehicle_photos','retry.jpg');db.commit()
    monkeypatch.setattr(file_storage,'_config',lambda: ('https://storage.example.invalid/object/bucket/', {'apikey':'fixture'}))
    now=datetime.utcnow()+timedelta(seconds=1)
    with patch.object(file_erasure.httpx,'delete',side_effect=httpx.ConnectError('private remote failure')):
        assert file_erasure.process_file_erasures(session_factory=factory,now=now)=={'removed':0,'retrying':1}
    assert path.exists()
    db.expire_all();row=db.query(file_erasure.FileErasure).one();assert row.attempts==1
    response=httpx.Response(200,json={'message':'Successfully deleted'},request=httpx.Request('DELETE','https://storage.example.invalid'))
    with patch.object(file_erasure.httpx,'delete',return_value=response) as provider:
        assert file_erasure.process_file_erasures(session_factory=factory,now=now+timedelta(hours=1))=={'removed':1,'retrying':0}
        assert provider.call_args.args[0].endswith(file_storage._key(path))
    assert not path.exists()


def test_missing_cloud_object_is_idempotent_but_permission_denial_is_not(fixture,monkeypatch):
    _,_,_,write,_,_,_,_,_,_=fixture
    path=write('vehicle_photos','missing.jpg')
    monkeypatch.setattr(file_storage,'_config',lambda: ('https://storage.example.invalid/object/bucket/', {'apikey':'fixture'}))
    def response(code,body): return httpx.Response(code,json=body,request=httpx.Request('DELETE','https://storage.example.invalid'))
    with patch.object(file_erasure.httpx,'delete',return_value=response(403,{'error':'denied'})):
        with pytest.raises(httpx.HTTPStatusError): file_erasure.erase_private_file('vehicle_photos/missing.jpg')
    assert path.exists()
    with patch.object(file_erasure.httpx,'delete',return_value=response(400,{'statusCode':'404','error':'not_found'})):
        file_erasure.erase_private_file('vehicle_photos/missing.jpg')
        file_erasure.erase_private_file('vehicle_photos/missing.jpg')
    assert not path.exists()
