import base64
from io import BytesIO
from uuid import uuid4
import pytest
from PIL import Image
from fastapi import HTTPException
from test_service_jobs import ctx
from test_service_job_consent import pending, decide
from src.modules.vehicle_hub.routers_v1 import service_jobs as api
from src.modules.vehicle_hub.service_job_models import ServiceJob, ServiceJobPhoto
from src.modules.vehicle_hub.models import ServiceRecord

def image(stage):
    out=BytesIO(); Image.new('RGB',(480,320), {'intake_front':'orange','intake_right':'blue','intake_rear':'green','intake_left':'purple','after':'yellow','damage':'red'}[stage]).save(out,'PNG')
    return base64.b64encode(out.getvalue()).decode()

def photo(db,service,jid,stage):
    body=api.JobPhotoUpload(client_id=uuid4(),stage=stage,caption=stage,content_base64=image(stage))
    reply=api.upload_service_job_photo(jid,body,service,db)
    assert api.upload_service_job_photo(jid,body,service,db)['photo']['id']==reply['photo']['id']
    return reply['job']

def change(db,service,job,status):
    return api.update_job(job['id'],api.JobUpdate(client_id=uuid4(),expected_version=job['version'],status=status,message='Výměna oleje a kontrola brzd',price=2400 if status=='completed' else None),service,db)

@pytest.mark.parametrize('decision',['pending','approved','rejected'])
def test_guided_intake_completion_and_consent(pending, decision):
    context, request = pending
    db,owner,service,other,vehicle,*_=context
    job=api.create_job(vehicle.id,api.JobCreate(client_id=uuid4(),workflow_version=1,access_request_id=request.id,title='Příjem vozidla'),service,db)
    assert job['workflow']['next_step']=='intake'
    if decision!='pending': decide(pending,decision)
    with pytest.raises(HTTPException):change(db,service,job,'in_progress')
    with pytest.raises(HTTPException):photo(db,service,job['id'],'after')
    for stage,_ in api.INTAKE_VIEWS:
        job=photo(db,service,job['id'],stage)
    assert job['workflow']['next_step']=='request'
    job=change(db,service,job,'in_progress')
    assert job['title']=='Výměna oleje a kontrola brzd'
    with pytest.raises(HTTPException):change(db,service,job,'completed')
    # The same image cannot fill a different angle or the after-repair requirement.
    with pytest.raises(HTTPException):
        api.upload_service_job_photo(job['id'],api.JobPhotoUpload(client_id=uuid4(),stage='after',content_base64=image('intake_front')),service,db)
    job=photo(db,service,job['id'],'damage')
    job=photo(db,service,job['id'],'after')
    job=change(db,service,job,'completed')
    assert job['workflow']['next_step']=='done'
    assert db.query(ServiceJobPhoto).count()==6
    assert db.query(ServiceRecord).count()==(1 if decision=='approved' else 0)
    if decision=='approved':
        assert len(api.get_job(job['id'],owner,db)['photos'])==6
    else:
        with pytest.raises(HTTPException):api.get_job(job['id'],owner,db)
    with pytest.raises(HTTPException):api.get_job(job['id'],other,db)
    assert api.get_job(job['id'],service,db)['status']=='completed'

def test_work_catalog_service_only(ctx):
    db,owner,service,*_=ctx
    assert len(api.work_catalog(service)['items'])>=40
    with pytest.raises(HTTPException):api.work_catalog(owner)

def test_additive_migration_preserves_legacy_rows_and_is_repeatable(tmp_path):
    from sqlalchemy import create_engine, text
    from scripts.migrate_service_job_workflow import migrate
    engine=create_engine(f'sqlite:///{tmp_path}/old.sqlite')
    with engine.begin() as db:
        db.execute(text('CREATE TABLE service_jobs (id INTEGER PRIMARY KEY, title TEXT)'))
        db.execute(text('CREATE TABLE service_job_photos (id INTEGER PRIMARY KEY, caption TEXT)'))
        db.execute(text("INSERT INTO service_jobs VALUES(1,'Old completed work')"))
        db.execute(text("INSERT INTO service_job_photos VALUES(1,'Old image')"))
    migrate(engine);migrate(engine)
    with engine.connect() as db:
        assert db.execute(text('SELECT title,workflow_version FROM service_jobs')).one()==('Old completed work',0)
        assert db.execute(text('SELECT caption,stage FROM service_job_photos')).one()==('Old image',None)
    engine.dispose()

from test_service_http_lifecycle import http_flow

def test_guided_reservation_http_and_saved_owner_history(http_flow):
    from datetime import datetime, timedelta
    from src.modules.vehicle_hub.models import Customer, Reservation
    from src.modules.vehicle_hub.service_access import create_or_update_vehicle_service_link
    from src.modules.vehicle_hub.routers_v1 import reservations
    f=http_flow;c=f.client;c.app.include_router(reservations.router,prefix='/api/v1')
    headers={}
    for name in ['owner','service']:
        actor=f.actors[name]
        reply=c.post('/user/login',json={'email':actor['email'],'password':f.password,'expected_role':actor['role']})
        assert reply.status_code==200
        headers[name]={'Authorization':'Bearer '+reply.json()['access_token']}
    with f.factory() as db:
        owner=db.get(Customer,f.actors['owner']['id']);service=db.get(Customer,f.actors['service']['id'])
        create_or_update_vehicle_service_link(db,tenant_id=owner.tenant_id,service_customer_id=service.id,owner_customer_id=owner.id,vehicle_id=f.vehicle_id,approved_by_customer_id=owner.id,source_type='owner_approval')
        booking=Reservation(tenant_id=owner.tenant_id,customer_id=owner.id,service_id=service.id,vehicle_id=f.vehicle_id,service_type='Olej',start_datetime=datetime.utcnow()+timedelta(days=1),status='CONFIRMED')
        db.add(booking);db.commit();bid=booking.id
    route=f'/api/v1/reservations/{bid}/start-job'
    assert c.post(route+'?workflow_version=7',headers=headers['service']).status_code==422
    reply=c.post(route+'?workflow_version=1',headers=headers['service']);assert reply.status_code==200,reply.text
    job=reply.json();jid=job['id'];assert job['workflow_version']==1
    assert c.post(route+'?workflow_version=1',headers=headers['service']).json()['id']==jid
    assert c.post(route,headers=headers['service']).json()['id']==jid
    def update(status):return c.post(f'/api/v1/service-jobs/{jid}/updates',headers=headers['service'],json={'client_id':str(uuid4()),'expected_version':job['version'],'status':status,'message':'Výměna oleje a kontrola','price':1500 if status=='completed' else None})
    assert update('in_progress').status_code==409
    for stage in [x[0] for x in api.INTAKE_VIEWS]:
        result=c.post(f'/api/v1/service-jobs/{jid}/photos',headers=headers['service'],json={'client_id':str(uuid4()),'stage':stage,'content_base64':image(stage)})
        assert result.status_code==200,result.text;job=result.json()['job']
    reply=update('in_progress');assert reply.status_code==200,reply.text;job=reply.json()
    assert update('completed').status_code==409
    result=c.post(f'/api/v1/service-jobs/{jid}/photos',headers=headers['service'],json={'client_id':str(uuid4()),'stage':'after','content_base64':image('after')});assert result.status_code==200,result.text;job=result.json()['job']
    reply=update('completed');assert reply.status_code==200,reply.text
    saved=c.get(f'/api/v1/service-jobs/{jid}',headers=headers['owner']);assert saved.status_code==200
    assert saved.json()['status']=='completed' and saved.json()['final_record_id']
    assert len(saved.json()['photos'])==5
    assert not f.external_attempts
