"""Recipient corrections retain history and cannot take ownership or revive a link."""
from datetime import datetime, timedelta
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from test_service_invitation_consent import fixture, pending
from src.modules.vehicle_hub.models import ServiceCustomerInvite, Vehicle, VehicleServiceLink, ServiceCustomerLink
from src.modules.vehicle_hub.routers_v1 import service_workspace as w
from src.modules.vehicle_hub.ownership import ensure_vehicle_owner_assignment, may_restore_vehicle_profile
from src.modules.vehicle_hub.service_access import create_or_update_vehicle_service_link


def correct(s, row, email='corrected@example.com', expected=None, actor=None):
    return w.correct_service_invitation_recipient(row.id,w.CorrectServiceInviteRecipientRequest(
        invite_email=email,expected_email=expected or row.invite_email),current_user=actor or s.service,db=s.db)


def car(s,email):
    v=Vehicle(tenant_id=s.service.tenant_id,user_email=email,nickname='Prepared vehicle',vin='TMBJJ7NE0J0123456')
    s.db.add(v);s.db.flush()
    create_or_update_vehicle_service_link(s.db,tenant_id=s.service.tenant_id,service_customer_id=s.service.id,
        owner_customer_id=s.service.id,vehicle_id=v.id,approved_by_customer_id=s.service.id,source_type='pending_owner_registration')
    s.db.commit();return v


def test_replacement_retains_old_address_revokes_token_and_old_inbox(fixture):
    s=fixture;row=pending(s);old_token=row.token
    r=correct(s,row,s.stranger.email)
    new=s.db.get(ServiceCustomerInvite,r['invite_id'])
    assert r['email_sent'] and r['corrected'] and row.status=='corrected'
    assert row.invite_email==s.owner.email and row.token!=old_token
    assert new.invite_email==s.stranger.email and new.id!=row.id and new.status=='pending'
    assert len(s.delivered)==1 and s.delivered[0]['invite_email']==s.stranger.email
    assert w.list_incoming_service_invitations(s.owner,s.db)['items']==[]
    assert [x['id'] for x in w.list_incoming_service_invitations(s.stranger,s.db)['items']]==[new.id]
    with pytest.raises(HTTPException):w.accept_service_invitation(w.AcceptServiceInviteRequest(token=old_token),s.owner,s.db)
    with pytest.raises(HTTPException):w.resend_service_invitation(row.id,s.service,s.db)
    with pytest.raises(HTTPException):w.delete_service_invitation(row.id,s.service,s.db)
    assert row.status=='corrected' and s.db.query(ServiceCustomerLink).count()==0


def test_unclaimed_vehicle_follows_address_without_copy_or_ownership(fixture):
    s=fixture;row=pending(s);v=car(s,row.invite_email);before=s.db.query(Vehicle).count()
    r=correct(s,row,s.stranger.email)
    assert r['updated_vehicle_count']==1 and v.user_email==s.stranger.email
    assert s.db.query(Vehicle).count()==before
    assert not may_restore_vehicle_profile(s.db,vehicle=v,customer=s.owner)
    assert may_restore_vehicle_profile(s.db,vehicle=v,customer=s.stranger)
    assert s.db.query(ServiceCustomerLink).count()==0


@pytest.mark.parametrize('state',['accepted','declined','cancelled','corrected'])
def test_finished_invitation_is_not_editable(fixture,state):
    s=fixture;row=pending(s);row.status=state;s.db.commit()
    with pytest.raises(HTTPException) as e:correct(s,row)
    assert e.value.status_code==409 and not s.delivered and row.status==state


@pytest.mark.parametrize('field',['accepted_at','linked_customer_id'])
def test_inconsistent_accepted_metadata_is_fail_closed(fixture,field):
    s=fixture;row=pending(s);setattr(row,field,datetime.utcnow() if field=='accepted_at' else s.owner.id);s.db.commit()
    with pytest.raises(HTTPException):correct(s,row)
    assert not s.delivered


def test_expired_invitation_can_be_corrected(fixture):
    s=fixture;row=pending(s);row.status='expired';s.db.commit()
    r=correct(s,row);assert s.db.get(ServiceCustomerInvite,r['invite_id']).expires_at>datetime.utcnow()


def test_owned_vehicle_is_never_reassigned(fixture):
    s=fixture;row=pending(s);v=car(s,row.invite_email)
    ensure_vehicle_owner_assignment(s.db,vehicle=v,owner=s.owner);s.db.commit()
    with pytest.raises(HTTPException) as e:correct(s,row)
    assert e.value.status_code==409 and row.status=='pending' and v.user_email==s.owner.email and not s.delivered


def test_other_service_vehicle_and_existing_private_car_untouched(fixture):
    s=fixture;row=pending(s);other=car(s,row.invite_email)
    link=s.db.query(VehicleServiceLink).filter_by(vehicle_id=other.id).one();link.service_customer_id=s.stranger.id;s.db.commit()
    r=correct(s,row);assert r['updated_vehicle_count']==0
    assert other.user_email==s.owner.email and all(v.user_email==s.owner.email for v in s.cars)


@pytest.mark.parametrize('case',['stale','duplicate','same','self','other_sender'])
def test_conflicts_do_not_send_or_modify(fixture,case):
    s=fixture;row=pending(s);kwargs={}
    if case=='stale':kwargs['expected']='stale@example.com'
    if case=='duplicate':
        dupe=ServiceCustomerInvite(service_tenant_id=s.service.tenant_id,service_customer_id=s.service.id,invite_email='corrected@example.com',token='other-private-token',status='pending',expires_at=datetime.utcnow()+timedelta(days=2));s.db.add(dupe);s.db.commit()
    if case=='same':kwargs['email']=s.owner.email
    if case=='self':kwargs['email']=s.service.email
    if case=='other_sender':s.stranger.role='service';s.db.commit();kwargs['actor']=s.stranger
    with pytest.raises(HTTPException):correct(s,row,**kwargs)
    assert row.status=='pending' and not s.delivered


def test_invalid_email_is_rejected_before_execution():
    with pytest.raises(ValidationError):w.CorrectServiceInviteRecipientRequest(invite_email='bad @',expected_email='old@example.com')


def test_failed_delivery_keeps_correction_and_explicit_retry(fixture,monkeypatch):
    s=fixture;row=pending(s);monkeypatch.setattr(w,'_send_invitation_email',lambda **k:False)
    r=correct(s,row)
    assert r['corrected'] and not r['email_sent'] and 'nepodařilo' in r['message']
    items=w.list_service_invitations(limit=200,current_user=s.service,db=s.db)
    old=next(i for i in items if i['id']==row.id);new=next(i for i in items if i['id']==r['invite_id'])
    assert not old['can_resend'] and not old['can_edit_email'] and not old['can_delete']
    assert new['can_resend'] and new['can_edit_email']


def test_listing_expiry_is_read_only(fixture, monkeypatch):
    s=fixture;row=pending(s);row.expires_at=datetime.utcnow()-timedelta(days=1);s.db.commit()
    def unexpected_lock(*args):raise AssertionError('Reading invitations must not take a write lock')
    monkeypatch.setattr(w,'lock_service_contacts',unexpected_lock)
    items=w.list_service_invitations(limit=200,current_user=s.service,db=s.db)
    assert items[0]['status']=='expired' and items[0]['can_edit_email']
    assert row.status=='pending' and not s.db.dirty
