"""Offline invitation/vehicle privacy checks using real database relationships."""
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import Customer, Tenant, Vehicle, ServiceCustomerInvite, ServiceCustomerLink
from src.modules.vehicle_hub.ownership import ensure_vehicle_owner_assignment
from src.modules.vehicle_hub.service_access import create_or_update_vehicle_service_link
from src.modules.vehicle_hub.routers_v1 import service_workspace as workspace, services


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'invites.sqlite'}")
    @event.listens_for(engine, 'connect')
    def foreign_keys(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False)()
    actors = {}
    for name, role in [('owner', 'user'), ('stranger', 'user'), ('service', 'service')]:
        tenant = Tenant(name=name, license_key='invitation-' + name)
        db.add(tenant); db.flush()
        actor = Customer(tenant_id=tenant.id, role=role, email=name+'@example.com', name=name)
        db.add(actor); db.flush(); actors[name] = actor
    owner = actors['owner']
    cars = []
    for name in ['shared', 'private']:
        car = Vehicle(tenant_id=owner.tenant_id, user_email=owner.email, nickname=name,
            plate=name, stk_valid_until=date(2030, 1, 1))
        db.add(car); db.flush(); ensure_vehicle_owner_assignment(db, vehicle=car, owner=owner)
        cars.append(car)
    db.commit()
    delivered = []
    monkeypatch.setattr(workspace, '_send_invitation_email', lambda **kwargs: delivered.append(kwargs) or True)
    yield SimpleNamespace(db=db, cars=cars, delivered=delivered, **actors)
    db.close(); engine.dispose()


def send(s):
    return workspace.send_service_invitation(workspace.SendServiceInviteRequest(
        invite_email=s.owner.email), current_user=s.service, db=s.db)


def pending(s):
    row = ServiceCustomerInvite(service_tenant_id=s.service.tenant_id, service_customer_id=s.service.id,
        invite_email=s.owner.email, token='synthetic_invitation_token_only', status='pending',
        expires_at=datetime.utcnow()+timedelta(days=1))
    s.db.add(row); s.db.commit()
    return row


def test_existing_account_must_accept_invitation(fixture):
    s=fixture; result=send(s)
    assert not result.get('linked_now', False)
    assert s.db.query(ServiceCustomerLink).count()==0
    assert s.db.query(ServiceCustomerInvite).one().status=='pending'
    assert result['email_sent'] and len(s.delivered)==1


def lookup(s, email, actor=None):
    return workspace.lookup_customer_email(workspace.CustomerEmailLookupRequest(customer_email=email),
        current_user=actor or s.service, db=s.db).model_dump()


def test_email_lookup_distinguishes_registration_without_exposing_profile(fixture):
    s=fixture
    existing=lookup(s, 'OWNER@EXAMPLE.COM')
    assert existing == {'email':'owner@example.com', 'registration_status':'registered',
        'connection_status':'none', 'customer_id':None, 'vehicles': existing['vehicles']}
    assert {v['id'] for v in existing['vehicles']} == {v.id for v in s.cars}
    assert all(set(v) == {'id','brand','model','year','plate','access_status'} for v in existing['vehicles'])
    new=lookup(s, 'new@example.com')
    assert new['registration_status']=='new' and new['connection_status']=='none'
    assert len(s.delivered)==0 and s.db.query(ServiceCustomerLink).count()==0
    assert s.db.query(ServiceCustomerInvite).count()==0


def test_lookup_then_request_accept_and_repeated_add_is_idempotent(fixture):
    s=fixture
    assert lookup(s,s.owner.email)['connection_status']=='none'
    send(s)
    assert lookup(s,s.owner.email)['connection_status']=='pending'
    assert workspace.list_service_customers(current_user=s.service,db=s.db)==[]
    inbox=workspace.list_incoming_service_invitations(current_user=s.owner,db=s.db)['items']
    assert len(inbox)==1
    workspace.accept_service_invitation(workspace.AcceptServiceInviteRequest(invitation_id=inbox[0]['id']),
        current_user=s.owner,db=s.db)
    assert lookup(s,s.owner.email)['customer_id']==s.owner.id
    assert lookup(s,s.owner.email)['connection_status']=='linked'
    assert [x['customer_id'] for x in workspace.list_service_customers(current_user=s.service,db=s.db)]==[s.owner.id]
    assert workspace.list_customer_vehicles(s.owner.id,current_user=s.service,db=s.db)==[]
    repeated=send(s)
    assert repeated['already_linked'] and not repeated['email_sent']
    assert len(s.delivered)==1 and s.db.query(ServiceCustomerInvite).count()==1


def test_lookup_pending_is_scoped_to_sender_and_expiry(fixture):
    s=fixture; row=pending(s)
    assert lookup(s,s.owner.email)['connection_status']=='pending'
    row.service_customer_id=s.stranger.id; s.db.commit()
    assert lookup(s,s.owner.email)['connection_status']=='none'
    row.service_customer_id=s.service.id;row.expires_at=datetime.utcnow()-timedelta(seconds=1);s.db.commit()
    assert lookup(s,s.owner.email)['connection_status']=='none'


@pytest.mark.parametrize('state', ['self','admin','service','disabled','deleted'])
def test_unavailable_email_cannot_be_invited_as_client(fixture,state):
    s=fixture; actor=s.owner
    if state=='self': actor=s.service
    elif state in {'admin','service'}: actor.role=state
    elif state=='disabled': actor.is_disabled=True
    else: actor.is_deleted=True
    s.db.commit()
    assert lookup(s,actor.email)['registration_status']=='unavailable'
    with pytest.raises(HTTPException) as exc:
        workspace.send_service_invitation(workspace.SendServiceInviteRequest(invite_email=actor.email),
            current_user=s.service,db=s.db)
    assert exc.value.status_code==400 and not s.delivered


def test_customer_cannot_enumerate_accounts_and_lookup_is_rate_limited(fixture):
    s=fixture
    with pytest.raises(HTTPException) as denied: lookup(s,s.stranger.email,actor=s.owner)
    assert denied.value.status_code==403
    for _ in range(40): lookup(s,s.owner.email)
    with pytest.raises(HTTPException) as throttled: lookup(s,s.owner.email)
    assert throttled.value.status_code==429


def test_lookup_requires_a_complete_email(fixture):
    from pydantic import ValidationError
    for email in ['owner','@example.com','owner@','%example.com']:
        with pytest.raises(ValidationError): workspace.CustomerEmailLookupRequest(customer_email=email)


def test_resend_does_not_grant_access_to_registered_customer(fixture):
    s=fixture; row=pending(s)
    result=workspace.resend_service_invitation(row.id,current_user=s.service,db=s.db)
    assert result['status']=='pending'
    assert s.db.query(ServiceCustomerLink).count()==0


def test_legacy_link_route_requires_customer_confirmation(fixture):
    s=fixture
    result=workspace.link_existing_customer(workspace.LinkExistingCustomerRequest(
        customer_email=s.owner.email),current_user=s.service,db=s.db)
    assert result['linked'] is False
    assert s.db.query(ServiceCustomerLink).count()==0


def test_invitation_link_does_not_expose_token_or_admin_web(fixture):
    result=send(fixture)
    assert result['registration_url'].endswith('/web/service-invitation.html')
    assert 'token' not in result['registration_url']


def test_customer_vehicle_list_only_exposes_explicitly_shared_cars(fixture):
    s=fixture
    s.db.add(ServiceCustomerLink(service_customer_id=s.service.id,service_tenant_id=s.service.tenant_id,
        customer_id=s.owner.id,customer_tenant_id=s.owner.tenant_id))
    create_or_update_vehicle_service_link(s.db,tenant_id=s.owner.tenant_id,service_customer_id=s.service.id,
        owner_customer_id=s.owner.id,vehicle_id=s.cars[0].id,approved_by_customer_id=s.owner.id,source_type='direct_user_grant')
    s.db.commit()
    result=workspace.list_customer_vehicles(s.owner.id,current_user=s.service,db=s.db)
    assert [row['id'] for row in result]==[s.cars[0].id]
    customers=workspace.list_service_customers(current_user=s.service,db=s.db)
    assert customers[0]['vehicles_count']==1


def test_unconfirmed_legacy_link_does_not_expose_customer(fixture):
    s=fixture
    s.db.add(ServiceCustomerLink(service_customer_id=s.service.id,service_tenant_id=s.service.tenant_id,
        customer_id=s.owner.id,customer_tenant_id=s.owner.tenant_id))
    s.db.commit()
    assert workspace.list_service_customers(current_user=s.service,db=s.db)==[]
    with pytest.raises(HTTPException) as exc:
        workspace.list_customer_vehicles(s.owner.id,current_user=s.service,db=s.db)
    assert exc.value.status_code==403


def test_only_recipient_can_accept_and_acceptance_does_not_share_all_cars(fixture):
    s=fixture; row=pending(s)
    payload=workspace.AcceptServiceInviteRequest(token=row.token)
    with pytest.raises(HTTPException) as denied:
        workspace.accept_service_invitation(payload,current_user=s.stranger,db=s.db)
    assert denied.value.status_code in {403,404}
    assert s.db.query(ServiceCustomerLink).count()==0
    assert workspace.accept_service_invitation(payload,current_user=s.owner,db=s.db)['accepted']
    assert workspace.list_customer_vehicles(s.owner.id,current_user=s.service,db=s.db)==[]


def test_disconnected_invitation_cannot_be_replayed(fixture):
    s=fixture; row=pending(s)
    payload=workspace.AcceptServiceInviteRequest(token=row.token)
    workspace.accept_service_invitation(payload,current_user=s.owner,db=s.db)
    services.disconnect_my_service_contact(s.service.id,current_user=s.owner,db=s.db)
    with pytest.raises(HTTPException) as exc:
        workspace.accept_service_invitation(payload,current_user=s.owner,db=s.db)
    assert exc.value.status_code==409
    assert s.db.query(ServiceCustomerLink).one().status=='archived'


def test_inbox_only_contains_own_pending_invites_without_bearer_tokens(fixture):
    s=fixture; row=pending(s)
    assert workspace.list_incoming_service_invitations(current_user=s.stranger,db=s.db)=={'items': []}
    result=workspace.list_incoming_service_invitations(current_user=s.owner,db=s.db)
    assert [item['id'] for item in result['items']]==[row.id]
    assert 'token' not in result['items'][0]
    assert s.owner.email not in repr(result)


@pytest.mark.parametrize('state', ['expired','cancelled','declined','service_disabled','email_unverified'])
def test_invalid_invitations_never_grant_consent(fixture,state):
    s=fixture; row=pending(s)
    if state=='expired': row.expires_at=datetime.utcnow()-timedelta(seconds=1)
    elif state=='service_disabled': s.service.is_disabled=True
    elif state=='email_unverified':
        from src.modules.vehicle_hub.email_verification import prepare_verification
        prepare_verification(s.db,s.owner)
    else: row.status=state
    s.db.commit()
    with pytest.raises(HTTPException) as exc:
        workspace.accept_service_invitation(workspace.AcceptServiceInviteRequest(invitation_id=row.id),current_user=s.owner,db=s.db)
    assert exc.value.status_code in {403,409}
    assert s.db.query(ServiceCustomerLink).count()==0


def test_accept_is_idempotent_without_duplication_and_decline_grants_nothing(fixture):
    s=fixture; row=pending(s)
    payload=workspace.AcceptServiceInviteRequest(invitation_id=row.id,decision='decline')
    assert workspace.accept_service_invitation(payload,current_user=s.owner,db=s.db)['accepted'] is False
    assert s.db.query(ServiceCustomerLink).count()==0
    send(s); row=s.db.query(ServiceCustomerInvite).filter_by(status='pending').one()
    payload=workspace.AcceptServiceInviteRequest(invitation_id=row.id)
    assert workspace.accept_service_invitation(payload,current_user=s.owner,db=s.db)['accepted']
    assert workspace.accept_service_invitation(payload,current_user=s.owner,db=s.db)['accepted']
    assert s.db.query(ServiceCustomerLink).count()==1
    link=s.db.query(ServiceCustomerLink).one()
    assert link.consented_at and link.consented_by_customer_id==s.owner.id


def test_service_cannot_accept_invitation_as_customer(fixture):
    s=fixture; row=pending(s)
    row.invite_email=s.service.email; s.db.commit()
    with pytest.raises(HTTPException) as exc:
        workspace.accept_service_invitation(workspace.AcceptServiceInviteRequest(invitation_id=row.id),current_user=s.service,db=s.db)
    assert exc.value.status_code==403


def test_sender_budget_is_durable_and_resend_does_not_bypass_it(fixture):
    s=fixture; send(s); row=s.db.query(ServiceCustomerInvite).one()
    for _ in range(9): workspace.resend_service_invitation(row.id,current_user=s.service,db=s.db)
    with pytest.raises(HTTPException) as exc:
        workspace.resend_service_invitation(row.id,current_user=s.service,db=s.db)
    assert exc.value.status_code==429
    assert len(s.delivered)==10


def test_preregistration_cannot_create_relationship_for_unconsenting_account(fixture):
    s=fixture
    with pytest.raises(HTTPException) as exc:
        workspace.create_pending_vehicle_registration(workspace.PendingVehicleRegistrationRequest(
            invite_email=s.owner.email,vehicle=workspace.ServiceWorkspaceVehicleCreateRequest(
                nickname='new fixture',vin='TMBTEST0000000001',stk_valid_until=date(2030,1,1))),current_user=s.service,db=s.db)
    assert exc.value.status_code==403
    assert s.db.query(ServiceCustomerLink).count()==0 and s.db.query(Vehicle).count()==2


def test_contact_consent_migration_preserves_old_rows_and_is_repeatable(tmp_path):
    from sqlalchemy import text
    from src.modules.vehicle_hub.service_contact_consent import migrate_contact_consent
    engine=create_engine(f"sqlite:///{tmp_path / 'migration.sqlite'}")
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE service_customer_links (id INTEGER PRIMARY KEY, note TEXT)'))
        connection.execute(text("INSERT INTO service_customer_links VALUES (1, 'original')"))
        migrate_contact_consent(connection); migrate_contact_consent(connection)
        assert tuple(connection.execute(text('SELECT * FROM service_customer_links')).one())==(1,'original',None,None)
    engine.dispose()


def consent(s):
    row=pending(s)
    workspace.accept_service_invitation(workspace.AcceptServiceInviteRequest(invitation_id=row.id),current_user=s.owner,db=s.db)


def reminders(s):
    return workspace.list_service_workspace_reminders(customer_id=None,vehicle_id=None,
        include_completed=True,limit=200,current_user=s.service,db=s.db)


def test_private_customer_reminders_are_not_service_records(fixture):
    from src.modules.vehicle_hub.models import Reminder
    s=fixture; consent(s)
    private=Reminder(tenant_id=s.owner.tenant_id,customer_id=s.owner.id,type='VLASTNI',text='private fixture')
    s.db.add(private);s.db.commit()
    assert reminders(s)==[]
    with pytest.raises(HTTPException) as exc:
        workspace.update_service_workspace_reminder(private.id,
            workspace.ServiceWorkspaceReminderUpdateRequest(text='changed fixture'),current_user=s.service,db=s.db)
    assert exc.value.status_code==404;s.db.rollback()
    with pytest.raises(HTTPException) as exc:
        workspace.delete_service_workspace_reminder(private.id,current_user=s.service,db=s.db)
    assert exc.value.status_code==404;s.db.rollback()
    assert s.db.get(Reminder,private.id).text=='private fixture'


def test_service_reminder_crud_and_revocation(fixture):
    from src.modules.vehicle_hub.models import Reminder
    s=fixture;consent(s)
    payload=workspace.ServiceWorkspaceReminderCreateRequest(customer_id=s.owner.id,vehicle_id=s.cars[0].id,text='service fixture')
    with pytest.raises(HTTPException) as exc:
        workspace.create_service_workspace_reminder(payload,current_user=s.service,db=s.db)
    assert exc.value.status_code==403;s.db.rollback()
    grant=create_or_update_vehicle_service_link(s.db,tenant_id=s.owner.tenant_id,service_customer_id=s.service.id,
        owner_customer_id=s.owner.id,vehicle_id=s.cars[0].id,approved_by_customer_id=s.owner.id,source_type='direct_user_grant')
    s.db.commit()
    created=workspace.create_service_workspace_reminder(payload,current_user=s.service,db=s.db)
    assert s.db.get(Reminder,created['id']).created_by_service_customer_id==s.service.id
    assert [r['id'] for r in reminders(s)]==[created['id']]
    workspace.update_service_workspace_reminder(created['id'],workspace.ServiceWorkspaceReminderUpdateRequest(
        text='updated fixture'),current_user=s.service,db=s.db)
    grant.status='revoked';s.db.commit()
    assert reminders(s)==[]
    with pytest.raises(HTTPException) as exc:
        workspace.delete_service_workspace_reminder(created['id'],current_user=s.service,db=s.db)
    assert exc.value.status_code==404;s.db.rollback()
    assert s.db.get(Reminder,created['id']).text=='updated fixture'


def test_contact_reminder_requires_current_consent_and_retains_customer_data(fixture):
    from src.modules.vehicle_hub.models import Reminder
    s=fixture;consent(s)
    created=workspace.create_service_workspace_reminder(workspace.ServiceWorkspaceReminderCreateRequest(
        customer_id=s.owner.id,text='contact fixture'),current_user=s.service,db=s.db)
    assert len(reminders(s))==1
    services.disconnect_my_service_contact(s.service.id,current_user=s.owner,db=s.db)
    assert reminders(s)==[]
    assert s.db.get(Reminder,created['id']) is not None


def test_deleted_customer_cannot_be_managed_even_with_historical_consent(fixture):
    s=fixture;consent(s);s.owner.is_deleted=True;s.db.commit()
    with pytest.raises(HTTPException) as exc:
        workspace.create_service_workspace_reminder(workspace.ServiceWorkspaceReminderCreateRequest(
            customer_id=s.owner.id,text='blocked fixture'),current_user=s.service,db=s.db)
    assert exc.value.status_code==404


def request_car(s, car=None, email=None, actor=None):
    return workspace.request_customer_vehicle_access(workspace.CustomerVehicleAccessRequest(
        customer_email=email or s.owner.email, vehicle_id=(car or s.cars[0]).id,
        note="Prosím potvrďte servis vybraného vozidla."), current_user=actor or s.service, db=s.db)


def test_selected_car_requires_owner_consent_and_never_shares_other_cars(fixture):
    from src.modules.vehicle_hub.models import License, ServiceAccessRequest
    from src.modules.vehicle_hub.routers_v1.schemas import ServiceAccessRequestDecisionV1
    s=fixture
    s.db.add(License(tenant_id=s.owner.tenant_id,plan='premium',status='active',vehicles_limit=100));s.db.commit()
    result=request_car(s)
    assert result['created'] and result['status']=='pending'
    assert workspace.list_service_customers(current_user=s.service,db=s.db)==[]
    statuses={v['id']:v['access_status'] for v in lookup(s,s.owner.email)['vehicles']}
    assert statuses=={s.cars[0].id:'pending',s.cars[1].id:'available'}
    duplicate=request_car(s)
    assert not duplicate['created'] and duplicate['request_id']==result['request_id']
    assert s.db.query(ServiceAccessRequest).count()==1
    assert services.get_service_access_requests(current_user=s.stranger,db=s.db)=={'requests':[]}
    inbox=services.get_service_access_requests(current_user=s.owner,db=s.db)['requests']
    assert len(inbox)==1 and inbox[0]['vehicle_id']==s.cars[0].id
    decision=ServiceAccessRequestDecisionV1(decision='approved')
    with pytest.raises(HTTPException) as exc:
        services.resolve_service_access_request(result['request_id'],decision,current_user=s.stranger,db=s.db)
    assert exc.value.status_code==404
    services.resolve_service_access_request(result['request_id'],decision,current_user=s.owner,db=s.db)
    assert lookup(s,s.owner.email)['connection_status']=='linked'
    assert lookup(s,s.owner.email)['customer_id']==s.owner.id
    assert [r['id'] for r in workspace.list_customer_vehicles(s.owner.id,current_user=s.service,db=s.db)]==[s.cars[0].id]
    statuses={v['id']:v['access_status'] for v in lookup(s,s.owner.email)['vehicles']}
    assert statuses=={s.cars[0].id:'approved',s.cars[1].id:'available'}
    with pytest.raises(HTTPException) as exc: request_car(s)
    assert exc.value.status_code==409


def test_owner_can_reject_selected_vehicle(fixture):
    from src.modules.vehicle_hub.routers_v1.schemas import ServiceAccessRequestDecisionV1
    s=fixture;result=request_car(s)
    services.resolve_service_access_request(result['request_id'],ServiceAccessRequestDecisionV1(decision='rejected'),current_user=s.owner,db=s.db)
    assert workspace.list_service_customers(current_user=s.service,db=s.db)==[]
    assert all(v['access_status']=='available' for v in lookup(s,s.owner.email)['vehicles'])


@pytest.mark.parametrize('state',['wrong_email','transferred','released','merged','disabled','deleted'])
def test_stale_or_tampered_selection_never_requests_another_owners_car(fixture,state):
    from src.modules.vehicle_hub.models import ServiceAccessRequest
    from src.modules.vehicle_hub.ownership import release_vehicle_owner_assignment
    s=fixture;lookup(s,s.owner.email);email=s.owner.email
    if state=='wrong_email': email=s.stranger.email
    elif state=='transferred': ensure_vehicle_owner_assignment(s.db,vehicle=s.cars[0],owner=s.stranger)
    elif state=='released': release_vehicle_owner_assignment(s.db,vehicle=s.cars[0],owner=s.owner)
    elif state=='merged': s.cars[0].merged_into_id=s.cars[1].id
    elif state=='disabled': s.owner.is_disabled=True
    else: s.owner.is_deleted=True
    s.db.commit()
    with pytest.raises(HTTPException) as exc: request_car(s,email=email)
    assert exc.value.status_code==409
    assert s.db.query(ServiceAccessRequest).count()==0


def test_vehicle_request_role_and_rate_limit(fixture):
    s=fixture
    with pytest.raises(HTTPException) as exc: request_car(s,actor=s.stranger)
    assert exc.value.status_code==403
    for _ in range(20): request_car(s)
    with pytest.raises(HTTPException) as exc: request_car(s)
    assert exc.value.status_code==429


def test_lookup_excludes_released_and_merged_cars(fixture):
    from src.modules.vehicle_hub.ownership import release_vehicle_owner_assignment
    s=fixture
    release_vehicle_owner_assignment(s.db,vehicle=s.cars[0],owner=s.owner)
    s.cars[1].merged_into_id=s.cars[0].id;s.db.commit()
    assert lookup(s,s.owner.email)['vehicles']==[]
