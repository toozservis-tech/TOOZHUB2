"""Real authenticated booking endpoints -> authorized unified inbox; synthetic only."""
from datetime import datetime,timedelta
import pytest
from test_quick_service_booking import flow
from test_service_http_lifecycle import http_flow
from src.modules.vehicle_hub.models import Customer,VehicleServiceLink,VehicleOwnership,Reservation
from src.modules.vehicle_hub.vehicle_update_models import VehicleUpdate
from src.modules.vehicle_hub.routers_v1 import reservations,notifications

@pytest.fixture
def booking_flow(flow,monkeypatch):
    f=flow
    f.client.app.include_router(notifications.router,prefix='/api/v1')
    for name in ('send_reservation_created_email','send_reservation_status_email','send_reservation_rescheduled_email'):
        monkeypatch.setattr(reservations,name,lambda *a,**kw:None)
    with f.factory() as db:
        owner=db.get(Customer,f.actors['owner']['id'])
        db.add(VehicleServiceLink(tenant_id=owner.tenant_id,owner_customer_id=owner.id,
            service_customer_id=f.actors['second']['id'],vehicle_id=f.vehicle_id,status='approved'))
        db.commit()
    return f

def create(f,role='second'):
    response=f.client.post('/api/v1/reservations',headers=f.headers[role],json={
        'service_id':f.actors['second']['id'],'vehicle_id':f.vehicle_id,'service_type':'Synthetic booking',
        'note':'PRIVATE DETAIL NOT IN NOTIFICATION','start_datetime':(datetime.utcnow()+timedelta(days=3)).isoformat()})
    assert response.status_code==200,response.text
    return response.json()

def inbox(f,role='owner'):
    r=f.client.get('/api/v1/notifications',headers=f.headers[role]);assert r.status_code==200,r.text
    return r.json()['items']

def test_service_creation_status_and_schedule_deliver_once_without_private_body(booking_flow):
    f=booking_flow;row=create(f)
    assert inbox(f)[0]['title']=='Servis vytvořil rezervaci'
    path='/api/v1/reservations/'+str(row['id'])
    for patch in ({'status':'CONFIRMED'},{'start_datetime':(datetime.utcnow()+timedelta(days=4)).isoformat()}, {'status':'CANCELLED'}):
        result=f.client.put(path,headers=f.headers['second'],json=patch);assert result.status_code==200,result.text
    items=inbox(f)
    assert len(items)==4
    assert {r['title'] for r in items}=={'Servis vytvořil rezervaci','Servis potvrdil rezervaci','Servis upravil termín rezervace','Servis zrušil rezervaci'}
    assert all('PRIVATE' not in r['body'] and r['action']['vehicle_id']==f.vehicle_id for r in items)
    assert f.client.put(path,headers=f.headers['second'],json={'status':'CANCELLED'}).status_code==200
    assert len(inbox(f))==4
    assert inbox(f,'stranger')==[] and inbox(f,'second')==[]
    assert f.external_attempts==[]

def test_owner_creation_and_cancel_do_not_masquerade_as_service(booking_flow):
    f=booking_flow;row=create(f,'owner')
    assert inbox(f)==[]
    assert f.client.put('/api/v1/reservations/'+str(row['id']),headers=f.headers['owner'],json={'status':'CANCELLED'}).status_code==200
    assert inbox(f)==[]

def test_old_booking_after_sale_never_redirects_notification_to_new_owner(booking_flow):
    f=booking_flow;row=create(f)
    with f.factory() as db:
        owner=db.query(VehicleOwnership).filter_by(vehicle_id=f.vehicle_id,is_active=True).one()
        owner.customer_id=f.actors['stranger']['id'];db.commit()
    r=f.client.put('/api/v1/reservations/'+str(row['id']),headers=f.headers['second'],json={'status':'CONFIRMED'})
    assert r.status_code==200,r.text
    assert inbox(f,'stranger')==[] and inbox(f)==[]
    with f.factory() as db:assert db.query(VehicleUpdate).count()==1

def test_failed_publication_rolls_back_booking_change(booking_flow,monkeypatch):
    f=booking_flow;row=create(f)
    def fail(*a,**kw):raise RuntimeError('Synthetic publication failure')
    monkeypatch.setattr(reservations,'_publish_service_booking_change',fail)
    with pytest.raises(RuntimeError,match='Synthetic publication failure'):
        f.client.put('/api/v1/reservations/'+str(row['id']),headers=f.headers['second'],json={'status':'CONFIRMED'})
    with f.factory() as db:
        assert db.get(Reservation,row['id']).status=='PENDING'
        assert db.query(VehicleUpdate).count()==1


def test_returning_owner_cannot_receive_old_booking_in_new_ownership_epoch(booking_flow):
    f=booking_flow;row=create(f)
    with f.factory() as db:
        owner=db.query(VehicleOwnership).filter_by(vehicle_id=f.vehicle_id,is_active=True).one()
        owner.owned_from=datetime.utcnow()+timedelta(seconds=1);db.commit()
    r=f.client.put('/api/v1/reservations/'+str(row['id']),headers=f.headers['second'],json={'status':'CONFIRMED'})
    assert r.status_code==200,r.text
    assert inbox(f)==[]
    with f.factory() as db:assert db.query(VehicleUpdate).count()==1
