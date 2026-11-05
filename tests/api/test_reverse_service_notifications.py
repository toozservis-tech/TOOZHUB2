"""Real transactional mutations -> exact service's minimal operational receipts."""
from datetime import datetime,timedelta
from uuid import uuid4
import pytest
from test_reservation_notification_delivery import booking_flow,inbox,create
from test_quick_service_booking import flow,decision
from test_service_http_lifecycle import http_flow
from src.modules.vehicle_hub.models import Customer,Reservation,ServiceAccessRequest,VehicleServiceLink
from src.modules.vehicle_hub.booking_request_models import BookingRequest
from src.modules.vehicle_hub.operational_notification_models import NotificationOperationalEvent as Event
from src.modules.vehicle_hub.routers_v1 import reservations,booking_requests


def test_regular_customer_create_cancel_delete_notify_exact_service_and_retain_minimal_history(booking_flow):
    f=booking_flow;row=create(f,'owner');path='/api/v1/reservations/'+str(row['id'])
    first=inbox(f,'second');assert len(first)==1 and first[0]['action']=={'type':'reservation','id':row['id'],'vehicle_id':None}
    assert inbox(f,'service')==[] and inbox(f,'stranger')==[] and inbox(f)==[]
    assert f.client.put(path,headers=f.headers['owner'],json={'status':'CANCELLED'}).status_code==200
    assert f.client.put(path,headers=f.headers['owner'],json={'status':'CANCELLED'}).status_code==400
    assert len(inbox(f,'second'))==2
    assert f.client.delete(path,headers=f.headers['owner']).status_code==200
    events=inbox(f,'second');assert len(events)==3
    assert all(e['action'] is None and 'PRIVATE' not in e['body'] for e in events)
    detail=f.client.get('/api/v1/service-notification-events/'+str(events[0]['source_id']),headers=f.headers['second'])
    assert detail.status_code==200 and detail.json()['source_available'] is False
    for role in ['owner','service','stranger']:
        assert f.client.get('/api/v1/service-notification-events/'+str(events[0]['source_id']),headers=f.headers[role]).status_code==404
    assert f.external_attempts==[]


def test_quick_request_create_propose_accept_routes_and_retries(booking_flow):
    f=booking_flow;payload={'client_id':str(uuid4()),'vehicle_id':f.vehicle_id,'service_id':f.actors['second']['id'],'service_type':'Repair','description':'PRIVATE'}
    row=f.client.post(f.path,headers=f.headers['owner'],json=payload).json()
    assert f.client.post(f.path,headers=f.headers['owner'],json=payload).json()['id']==row['id']
    items=inbox(f,'second');assert len(items)==1 and items[0]['action']['type']=='booking_request'
    for role,status in [('second',200),('owner',200),('service',404),('stranger',404)]:
        assert f.client.get(f.path+'/'+str(row['id']),headers=f.headers[role]).status_code==status
    _,proposal=decision(f,row,'second','propose',proposed_datetime=(datetime.utcnow()+timedelta(days=4)).isoformat())
    assert len(inbox(f,'second'))==1
    command,accepted=decision(f,proposal,'owner','accept_proposal')
    assert f.client.post(f.path+f'/{row["id"]}/decision',headers=f.headers['owner'],json=command).status_code==200
    assert len(inbox(f,'second'))==2 and inbox(f,'second')[0]['title']=='Zákazník přijal navržený termín'
    with f.factory() as db:assert db.query(Event).count()==2 and db.query(Reservation).count()==1


def test_quick_cancel_actual_mutation_rolls_back_if_hook_fails(booking_flow,monkeypatch):
    f=booking_flow
    row=f.client.post(f.path,headers=f.headers['owner'],json={'client_id':str(uuid4()),'vehicle_id':f.vehicle_id,'service_id':f.actors['second']['id'],'service_type':'Repair','description':'Test'}).json()
    def fail(*a,**k):raise RuntimeError('Synthetic reverse failure')
    monkeypatch.setattr(booking_requests,'booking_change',fail)
    with pytest.raises(RuntimeError,match='Synthetic reverse failure'):
        decision(f,row,'owner','cancel')
    with f.factory() as db:
        assert db.get(BookingRequest,row['id']).status=='pending'
        assert db.query(Event).count()==1


def test_regular_create_hook_failure_rolls_back_business_row(booking_flow,monkeypatch):
    f=booking_flow
    def fail(*a,**k):raise RuntimeError('Synthetic reverse failure')
    monkeypatch.setattr(reservations,'booking_change',fail)
    with pytest.raises(RuntimeError,match='Synthetic reverse failure'):create(f,'owner')
    with f.factory() as db:assert db.query(Reservation).count()==db.query(Event).count()==0


def access_request(f):
    r=f.client.post('/api/v1/services/workspace/access-requests',headers=f.headers['service'],json={'vehicle_id':f.vehicle_id,'lookup_query':'HTTP001','note':'PRIVATE-ACCESS-REASON'})
    assert r.status_code==200,r.text
    return r.json()['request_id']


@pytest.mark.parametrize('decision_value',['approved','rejected'])
def test_owner_access_decision_delivers_minimal_service_history_without_vehicle_bypass(booking_flow,decision_value):
    f=booking_flow;identity=access_request(f)
    r=f.client.put(f'/api/v1/services/access-requests/{identity}',headers=f.headers['owner'],json={'decision':decision_value})
    assert r.status_code==200,r.text
    event=inbox(f,'service')[0];assert event['kind']=='service_event'
    assert event['action']=={'type':'service_access','id':event['source_id'],'vehicle_id':None}
    detail=f.client.get('/api/v1/service-notification-events/'+str(event['source_id']),headers=f.headers['service']).json()
    assert detail['current_status']==decision_value
    assert not any(key in detail for key in ('vehicle_id','vin','plate','owner_id','email','note'))
    assert 'PRIVATE' not in str(detail)
    if decision_value=='rejected':
        assert f.client.get(f'/api/v1/vehicles/{f.vehicle_id}/records',headers=f.headers['service']).status_code==403
    assert inbox(f,'second')==[]


def test_owner_revoke_keeps_receipt_but_service_loses_vehicle_access(booking_flow):
    f=booking_flow;identity=access_request(f)
    assert f.client.put(f'/api/v1/services/access-requests/{identity}',headers=f.headers['owner'],json={'decision':'approved'}).status_code==200
    from src.modules.vehicle_hub.service_access import revoke_vehicle_service_link
    for _ in range(2):
        with f.factory() as db:
            revoke_vehicle_service_link(db,service_customer_id=f.actors['service']['id'],vehicle_id=f.vehicle_id,revoked_by_customer_id=f.actors['owner']['id'],reason='Private revoke reason')
            db.commit()
    items=inbox(f,'service');assert len(items)==2
    assert items[0]['title']=='Přístup k vozidlu byl odvolán'
    assert f.client.get(f'/api/v1/vehicles/{f.vehicle_id}/records',headers=f.headers['service']).status_code==403
    assert f.client.get('/api/v1/service-notification-events/'+str(items[0]['source_id']),headers=f.headers['service']).json()['current_status']=='revoked'
    with f.factory() as db:db.get(Customer,f.actors['service']['id']).is_disabled=True;db.commit()
    assert f.client.get('/api/v1/notifications',headers=f.headers['service']).status_code in (401,403)


def test_event_rows_are_immutable_and_transactional_dedupe(booking_flow):
    f=booking_flow
    from src.modules.vehicle_hub.operational_notifications import emit
    with f.factory() as db:
        kwargs=dict(recipient_id=f.actors['second']['id'],actor_id=f.actors['owner']['id'],source_type='reservation',source_id=999,event_type='reservation.created',dedupe_key='synthetic-once')
        a=emit(db,**kwargs);b=emit(db,**kwargs);assert a is b;db.commit()
        assert emit(db,**kwargs).id==a.id
        a.event_type='reservation.cancelled'
        with pytest.raises(RuntimeError,match='immutable'):db.commit()
        db.rollback();assert db.query(Event).one().event_type=='reservation.created'


def test_access_decision_hook_failure_rolls_back_consent_and_publication(booking_flow,monkeypatch):
    f=booking_flow;identity=access_request(f)
    from src.modules.vehicle_hub import operational_notifications
    def fail(*a,**k):raise RuntimeError('Synthetic consent notification failure')
    monkeypatch.setattr(operational_notifications,'emit',fail)
    # Handler reports a safe server error, but no granted access may be committed.
    result=f.client.put(f'/api/v1/services/access-requests/{identity}',headers=f.headers['owner'],json={'decision':'approved'})
    assert result.status_code==500,result.text
    with f.factory() as db:
        assert db.get(ServiceAccessRequest,identity).status=='pending'
        assert db.query(VehicleServiceLink).filter_by(service_customer_id=f.actors['service']['id'],vehicle_id=f.vehicle_id,status='approved').count()==0
        assert db.query(Event).count()==0
    assert f.client.get(f'/api/v1/vehicles/{f.vehicle_id}/records',headers=f.headers['service']).status_code==403


def test_direct_grant_revoke_deduplicates_and_event_erase_does_not_touch_other_service(booking_flow):
    f=booking_flow
    from src.modules.vehicle_hub.service_access import revoke_vehicle_service_link
    from src.modules.vehicle_hub.notification_delivery_models import erase_account_notifications
    for _ in range(2):
        with f.factory() as db:
            revoke_vehicle_service_link(db,service_customer_id=f.actors['second']['id'],vehicle_id=f.vehicle_id,revoked_by_customer_id=f.actors['owner']['id'],reason='Direct grant revoked')
            db.commit()
    assert len(inbox(f,'second'))==1
    with f.factory() as db:
        assert db.query(Event).one().source_type=='service_link'
        erase_account_notifications(db,db.get(Customer,f.actors['owner']['id']));db.commit()
        assert db.query(Event).count()==0
    assert inbox(f,'second')==[]


def test_quick_cancellation_notifies_service_once(booking_flow):
    f=booking_flow;row=f.client.post(f.path,headers=f.headers['owner'],json={'client_id':str(uuid4()),'vehicle_id':f.vehicle_id,'service_id':f.actors['second']['id'],'service_type':'Repair','description':'Test'}).json()
    command,cancelled=decision(f,row,'owner','cancel')
    assert cancelled['status']=='cancelled'
    assert f.client.post(f.path+f'/{row["id"]}/decision',headers=f.headers['owner'],json=command).status_code==200
    assert len(inbox(f,'second'))==2
    assert inbox(f,'second')[0]['title']=='Zákazník zrušil požadavek'


def test_operational_notice_read_and_dismiss_do_not_change_booking_or_consent(booking_flow):
    f=booking_flow;row=create(f,'owner');item=inbox(f,'second')[0]
    r=f.client.post('/api/v1/notifications/read',headers=f.headers['second'],json={'client_id':str(uuid4()),'message_ids':[item['id']]})
    assert r.status_code==200 and r.json()['summary']['badge_count']==0
    r=f.client.post(f'/api/v1/notifications/{item["id"]}/dismiss',headers=f.headers['second'],json={'client_id':str(uuid4())})
    assert r.status_code==200
    with f.factory() as db:
        assert db.get(Reservation,row['id']).status=='PENDING'
        assert db.query(Event).count()==1
    assert len(inbox(f,'second'))==1
