"""Post-completion photos append evidence without rewriting the completed repair."""
import base64
from datetime import datetime, timedelta
from io import BytesIO
from uuid import uuid4

import pytest
from fastapi import HTTPException
from PIL import Image

from test_service_jobs import ctx
from test_service_job_consent import pending, create, finish, decide
from src.modules.vehicle_hub.models import ServiceRecord, ServiceRecordAuditLog
from src.modules.vehicle_hub.service_job_models import ServiceJobEvent, ServiceJobPhoto
from src.modules.vehicle_hub.vehicle_update_models import VehicleUpdate
from src.modules.vehicle_hub.routers_v1 import service_jobs as jobs


def photo_payload(color='blue'):
    data = BytesIO()
    Image.new('RGB', (20, 20), color).save(data, 'JPEG')
    return jobs.JobPhotoUpload(client_id=uuid4(), caption='Kontrola po opravě',
        content_base64=base64.b64encode(data.getvalue()).decode())


@pytest.mark.parametrize('consent', ['pending', 'rejected', 'approved'])
def test_completed_photo_persists_once_and_preserves_completion(pending, consent):
    context, _ = pending
    db, owner, service, other, vehicle, *_ = context
    job, _ = create(pending)
    if consent != 'pending':
        decide(pending, consent)
        job = jobs.get_job(job['id'], service, db)
    completed = finish(context, job)
    audits_before = db.query(ServiceRecordAuditLog).count()
    records_before = [(r.id, r.snapshot_hash, r.performed_at, r.price)
                      for r in db.query(ServiceRecord).all()]
    events_before = db.query(ServiceJobEvent).count()
    payload = photo_payload()
    result = jobs.upload_service_job_photo(job['id'], payload, service, db)
    updated = result['job']
    assert updated['status'] == 'completed'
    assert updated['completed_at'] == completed['completed_at']
    assert updated['completion_price'] == completed['completion_price']
    assert updated['final_record_id'] == completed['final_record_id']
    assert updated['version'] == completed['version'] + 1
    event = db.query(ServiceJobEvent).order_by(ServiceJobEvent.id.desc()).first()
    assert event.actor_id == service.id
    assert event.message == 'Fotografie doplněná po dokončení: Kontrola po opravě'
    assert event.created_at >= completed['completed_at']
    assert db.query(ServiceRecordAuditLog).count() == audits_before
    assert [(r.id, r.snapshot_hash, r.performed_at, r.price)
            for r in db.query(ServiceRecord).all()] == records_before

    # Lost responses and selecting the same file again must not duplicate history.
    assert jobs.upload_service_job_photo(job['id'], payload, service, db)['photo']['id'] == result['photo']['id']
    retry = photo_payload()
    assert jobs.upload_service_job_photo(job['id'], retry, service, db)['photo']['id'] == result['photo']['id']
    assert db.query(ServiceJobPhoto).count() == 1
    assert db.query(ServiceJobEvent).count() == events_before + 1
    assert db.query(VehicleUpdate).filter_by(event_type='job.photo').count() == (1 if consent == 'approved' else 0)
    db.expire_all()
    assert len(jobs.get_job(job['id'], service, db)['photos']) == 1

    with pytest.raises(HTTPException):
        jobs.view_job_photo(job['id'], result['photo']['id'], other, db)
    if consent == 'approved':
        assert jobs.view_job_photo(job['id'], result['photo']['id'], owner, db).media_type == 'image/jpeg'
    else:
        with pytest.raises(HTTPException):
            jobs.view_job_photo(job['id'], result['photo']['id'], owner, db)
    if consent == 'pending':
        decide(pending)
        assert jobs.view_job_photo(job['id'], result['photo']['id'], owner, db).media_type == 'image/jpeg'
        assert db.query(ServiceRecord).count() == 1
        assert db.query(ServiceRecord).one().performed_at == completed['completed_at']


@pytest.mark.parametrize('status', ['handed_over', 'cancelled'])
def test_closed_or_cancelled_work_still_rejects_new_photo(pending, status):
    context, _ = pending
    db, _, service, *_ = context
    job, _ = create(pending)
    if status == 'handed_over':
        completed = finish(context, job)
        jobs.hand_over_job(job['id'], jobs.JobHandover(client_id=uuid4(),
            expected_version=completed['version']), service, db)
    else:
        jobs.update_job(job['id'], jobs.JobUpdate(client_id=uuid4(), expected_version=job['version'],
            status='cancelled', message='Zákazník zrušil opravu'), service, db)
    with pytest.raises(HTTPException) as error:
        jobs.upload_service_job_photo(job['id'], photo_payload(), service, db)
    assert error.value.status_code == 409
    assert db.query(ServiceJobPhoto).count() == 0


@pytest.mark.parametrize('boundary', ['other_service', 'owner', 'disabled', 'revoked', 'transferred'])
def test_completed_photo_keeps_service_authorization(pending, boundary):
    context, _ = pending
    db, owner, service, other, _, assignment, link = context
    job, _ = create(pending)
    decide(pending)
    job = jobs.get_job(job['id'], service, db)
    finish(context, job)
    actor = service
    if boundary == 'other_service':
        other.role = 'service'
        actor = other
    elif boundary == 'owner':
        actor = owner
    elif boundary == 'disabled':
        service.is_disabled = True
    elif boundary == 'revoked':
        link.status = 'revoked'
    elif boundary == 'transferred':
        assignment.customer_id = other.id
        assignment.owned_from = datetime.utcnow() + timedelta(seconds=1)
    db.commit()
    with pytest.raises(HTTPException):
        jobs.upload_service_job_photo(job['id'], photo_payload(), actor, db)
    assert db.query(ServiceJobPhoto).count() == 0
