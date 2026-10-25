"""Work can precede consent; no owner history, file, alert or cost leaks before it."""
import base64
from datetime import datetime, timedelta
from io import BytesIO
from uuid import uuid4
import json
import pytest
from fastapi import HTTPException
from test_service_jobs import ctx
from src.modules.vehicle_hub.models import ServiceAccessRequest, ServiceRecord, VehicleAttachmentPrivacy
from src.modules.vehicle_hub.service_job_models import ServiceJob, ServiceJobDocument
from src.modules.vehicle_hub.vehicle_update_models import VehicleUpdate
from src.modules.vehicle_hub.routers_v1 import service_jobs as jobs, services
from src.modules.vehicle_hub.routers_v1.schemas import ServiceAccessRequestDecisionV1
from src.modules.vehicle_hub.vehicle_privacy import require_attachment_private


@pytest.fixture
def pending(ctx, monkeypatch, tmp_path):
    db, owner, service, stranger, vehicle, assignment, link = ctx
    link.status = 'revoked'
    request = ServiceAccessRequest(tenant_id=owner.tenant_id, service_customer_id=service.id,
        owner_customer_id=owner.id, vehicle_id=vehicle.id, status='pending', requested_at=datetime.utcnow())
    db.add(request); db.commit()
    monkeypatch.setattr(services, 'assert_customer_feature', lambda *a, **kw: None)
    from src.modules.vehicle_hub.routers_v1 import service_records
    monkeypatch.setattr(service_records, 'SERVICE_RECORD_ATTACHMENTS_DIR', tmp_path/'attachments')
    monkeypatch.setattr(service_records, 'persist_file', lambda path, data: path.write_bytes(data))
    monkeypatch.setattr(service_records, 'cached_file', lambda path: path if path.exists() else None)
    return ctx, request


def create(pending):
    ctx, request = pending
    db, _, service, _, vehicle, _, _ = ctx
    payload = jobs.JobCreate(client_id=uuid4(), access_request_id=request.id, title='Výměna oleje', mileage=123456)
    return jobs.create_job(vehicle.id, payload, service, db), payload


def finish(ctx, job):
    db, _, service, *_ = ctx
    started = jobs.update_job(job['id'], jobs.JobUpdate(client_id=uuid4(), expected_version=job['version'],
        status='in_progress', message='Vypuštění oleje'), service, db)
    payload = jobs.JobUpdate(client_id=uuid4(), expected_version=started['version'],
        status='completed', message='Nový olej a filtr, kontrola těsnosti', price=2500)
    result = jobs.update_job(job['id'], payload, service, db)
    assert jobs.update_job(job['id'], payload, service, db)['id'] == result['id']
    return result


def decide(pending, decision='approved'):
    ctx, request = pending
    return services.resolve_service_access_request(request.id, ServiceAccessRequestDecisionV1(decision=decision), ctx[1], ctx[0])


def denied(call, code=None):
    with pytest.raises(HTTPException) as exc: call()
    if code: assert exc.value.status_code == code


def test_completed_private_work_publishes_once_with_original_time(pending):
    ctx, request = pending
    db, owner, service, other, vehicle, *_ = ctx
    job, payload = create(pending)
    assert not job['shared_with_owner'] and job['consent_status']=='pending'
    assert jobs.create_job(vehicle.id,payload,service,db)['id']==job['id']
    completed = finish(ctx,job)
    assert completed['final_record_id'] is None
    assert db.query(ServiceRecord).count()==0 and db.query(VehicleUpdate).filter(VehicleUpdate.event_type.like('job.%')).count()==0
    assert jobs.list_jobs(vehicle.id,owner,db)['items']==[]
    denied(lambda:jobs.get_job(job['id'],owner,db))
    denied(lambda:jobs.get_job(job['id'],other,db))
    denied(lambda:jobs.list_jobs(vehicle.id,service,db))
    assert len(jobs.list_jobs(vehicle.id,service,db,request.id)['items'])==1
    assert jobs.list_work_before_consent(service,db)['items'][0]['job_count']==1
    decide(pending)
    record=db.query(ServiceRecord).one()
    assert record.performed_at==completed['completed_at'] and record.price==2500
    assert jobs.get_job(job['id'],owner,db)['shared_with_owner']
    assert len(jobs.list_jobs(vehicle.id,owner,db)['items'])==1
    assert db.query(VehicleUpdate).filter_by(event_type='job.shared').count()==1
    denied(lambda:decide(pending),409)
    jobs.publish_work_after_consent(db,request,service,ctx[-1]);db.commit()
    assert db.query(ServiceRecord).count()==1


def test_rejection_retains_work_in_service_history_only(pending):
    ctx, request=pending
    db, owner, service, _, vehicle, *_=ctx
    job,_=create(pending);decide(pending,'rejected')
    completed=finish(ctx,job)
    assert completed['consent_status']=='rejected' and not completed['shared_with_owner']
    assert jobs.get_job(job['id'],service,db)['status']=='completed'
    assert jobs.list_jobs(vehicle.id,owner,db)['items']==[]
    assert db.query(ServiceRecord).count()==0 and db.query(VehicleUpdate).filter(VehicleUpdate.event_type.like('job.%')).count()==0
    assert jobs.list_work_before_consent(service,db)['items'][0]['status']=='rejected'
    denied(lambda:jobs.create_job(vehicle.id,jobs.JobCreate(client_id=uuid4(),title='Nová',access_request_id=request.id),service,db),409)


def test_files_are_private_including_direct_attachment_paths_then_shared(pending):
    ctx, request=pending
    db, owner, service, _, vehicle, *_=ctx
    job,_=create(pending)
    from PIL import Image
    from PyPDF2 import PdfWriter
    image=BytesIO();Image.new('RGB',(20,20),'red').save(image,'JPEG')
    photo=jobs.upload_service_job_photo(job['id'],jobs.JobPhotoUpload(client_id=uuid4(),
        caption='Nový filtr',content_base64=base64.b64encode(image.getvalue()).decode()),service,db)
    pdf=BytesIO();writer=PdfWriter();writer.add_blank_page(width=100,height=100);writer.write(pdf)
    payload=jobs.JobDocumentUpload(client_id=uuid4(),file_name='Faktura.pdf',content_base64=base64.b64encode(pdf.getvalue()).decode())
    updated=jobs.upload_job_document(job['id'],payload,service,db)
    jobs.upload_job_document(job['id'],payload,service,db)
    assert db.query(ServiceJobDocument).count()==1
    assert len(updated['photos'])==1 and len(updated['documents'])==1
    for file in db.query(VehicleAttachmentPrivacy).all():
        assert file.owner_customer_id is None
        denied(lambda:require_attachment_private(db,vehicle_id=vehicle.id,key=file.storage_key,actor=owner),403)
        require_attachment_private(db,vehicle_id=vehicle.id,key=file.storage_key,actor=service)
    document_id=updated['documents'][0]['id'];photo_id=photo['photo']['id']
    denied(lambda:jobs.view_job_document(job['id'],document_id,owner,db))
    denied(lambda:jobs.view_job_photo(job['id'],photo_id,owner,db))
    finish(ctx,updated);decide(pending)
    attachments=json.loads(db.query(ServiceRecord).one().attachments)
    assert {file['mime_type'] for file in attachments}=={'application/pdf','image/jpeg'}
    for file in db.query(VehicleAttachmentPrivacy).all():
        assert file.owner_customer_id==owner.id
        require_attachment_private(db,vehicle_id=vehicle.id,key=file.storage_key,actor=owner)
    assert jobs.view_job_document(job['id'],document_id,owner,db).media_type=='application/pdf'
    assert jobs.view_job_photo(job['id'],photo_id,owner,db).media_type=='image/jpeg'


def test_in_progress_approval_then_completion_uses_one_job(pending):
    ctx,_=pending;db,owner,service,*_=ctx
    job,_=create(pending);decide(pending)
    published=jobs.get_job(job['id'],owner,db)
    assert published['version']==job['version']+1
    done=finish(ctx,published)
    assert done['final_record_id'] and db.query(ServiceRecord).count()==1
    assert db.query(ServiceJob).count()==1


def test_transfer_keeps_private_evidence_but_blocks_changes_and_publication(pending):
    ctx,request=pending;db,owner,service,other,vehicle,assignment,_=ctx
    job,_=create(pending);assignment.customer_id=other.id;db.commit()
    assert jobs.get_job(job['id'],service,db)['consent_status']=='ownership_changed'
    denied(lambda:jobs.get_job(job['id'],other,db))
    denied(lambda:jobs.update_job(job['id'],jobs.JobUpdate(client_id=uuid4(),expected_version=1,message='Změna'),service,db),409)
    denied(lambda:decide(pending))
    assert db.query(ServiceRecord).count()==0
    assignment.customer_id=owner.id;assignment.owned_from=datetime.utcnow()+timedelta(days=1);db.commit()
    denied(lambda:jobs.publish_work_after_consent(db,request,service,ctx[-1]),409)


def test_wrong_request_vehicle_actor_and_missing_consent_cannot_create(pending):
    ctx,request=pending;db,owner,service,other,vehicle,*_=ctx
    denied(lambda:jobs.create_job(vehicle.id,jobs.JobCreate(client_id=uuid4(),title='Test'),service,db),403)
    denied(lambda:jobs.create_job(vehicle.id,jobs.JobCreate(client_id=uuid4(),title='Test',access_request_id=request.id),owner,db),403)
    other.role='service';db.commit()
    denied(lambda:jobs.create_job(vehicle.id,jobs.JobCreate(client_id=uuid4(),title='Test',access_request_id=request.id),other,db),404)
    denied(lambda:jobs.list_jobs(vehicle.id,other,db,request.id),404)
    assert db.query(ServiceJob).count()==0


def test_failed_publication_rolls_back_consent_and_all_work(pending,monkeypatch):
    ctx,request=pending;db,owner,service,*_=ctx
    job,_=create(pending);finish(ctx,job)
    def fail(*a,**kw): raise RuntimeError('controlled failure')
    monkeypatch.setattr(jobs,'publish_vehicle_update',fail)
    denied(lambda:decide(pending),500)
    db.expire_all()
    assert db.get(ServiceAccessRequest,request.id).status=='pending'
    assert db.get(ServiceJob,job['id']).consent_published_at is None
    assert db.query(ServiceRecord).count()==0


def test_additive_migration_is_repeatable_and_preserves_old_work(tmp_path):
    from sqlalchemy import create_engine,text,inspect
    from scripts.migrate_service_job_consent import migrate
    engine=create_engine(f'sqlite:///{tmp_path}/old.sqlite')
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE service_jobs (id INTEGER PRIMARY KEY, title TEXT)'))
        conn.execute(text("INSERT INTO service_jobs (id,title) VALUES (1,'Historie')"))
    migrate(engine);migrate(engine)
    with engine.connect() as conn:
        row=conn.execute(text('SELECT title,access_request_id,consent_published_at FROM service_jobs')).one()
        assert tuple(row)==('Historie',None,None)
        assert inspect(conn).has_table('service_job_documents')


def test_private_files_cannot_be_attached_to_owner_visible_records(pending):
    ctx, _ = pending
    db, owner, service, _, vehicle, *_ = ctx
    job, _ = create(pending)
    finish(ctx, job)
    from PyPDF2 import PdfWriter
    from src.modules.vehicle_hub.vehicle_privacy import require_attachment_write_period
    pdf = BytesIO(); writer = PdfWriter(); writer.add_blank_page(width=100, height=100); writer.write(pdf)
    jobs.upload_job_document(job['id'], jobs.JobDocumentUpload(client_id=uuid4(), file_name='Soukroma.pdf',
        content_base64=base64.b64encode(pdf.getvalue()).decode()), service, db)
    key = db.query(ServiceJobDocument).one().storage_key
    denied(lambda: require_attachment_write_period(db, vehicle_id=vehicle.id, key=key), 403)
    decide(pending)
    require_attachment_write_period(db, vehicle_id=vehicle.id, key=key)
    record = db.query(ServiceRecord).one()
    assert record.description == 'Nový olej a filtr, kontrola těsnosti'
    assert json.loads(record.attachments)[0]['storage_key'] == key


def test_history_has_older_pages_and_completed_handover_is_immutable(pending):
    ctx, request = pending
    db, owner, service, _, vehicle, *_ = ctx
    job, _ = create(pending); completed = finish(ctx, job)
    handed = jobs.hand_over_job(job['id'], jobs.JobHandover(client_id=uuid4(), expected_version=completed['version']), service, db)
    denied(lambda: jobs.update_job(job['id'], jobs.JobUpdate(client_id=uuid4(), expected_version=handed['version'], message='Pozdejsi zmena'), service, db),409)
    for index in range(51):
        db.add(ServiceAccessRequest(tenant_id=owner.tenant_id, service_customer_id=service.id,
            owner_customer_id=owner.id, vehicle_id=vehicle.id, status='rejected',
            requested_at=datetime.utcnow()-timedelta(days=index+1), updated_at=datetime.utcnow()-timedelta(days=index+1)))
    db.commit()
    page1 = jobs.list_work_before_consent(service, db)
    page2 = jobs.list_work_before_consent(service, db, page1['next_offset'])
    assert page1['items'][0]['id']==request.id
    assert len(page1['items'])==50 and len(page2['items'])==2 and page2['next_offset'] is None
    assert len({item['id'] for item in page1['items']+page2['items']})==52
