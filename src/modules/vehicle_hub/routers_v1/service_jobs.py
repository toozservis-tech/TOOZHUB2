"""Transactional, owner-scoped workshop lifecycle. No runtime schema changes."""
from datetime import datetime
from hashlib import sha256
import json
from typing import Literal, Optional
from uuid import UUID, uuid5, NAMESPACE_URL
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from ..database import get_db
from ..models import Customer, Vehicle, ServiceRecord, ServiceRecordAuditLog
from ..ownership import lock_vehicle_access, get_primary_vehicle_owner_assignment
from ..service_access import require_service_vehicle_link, get_active_vehicle_service_link, attach_service_access_to_record
from ..service_job_models import ServiceJob, ServiceJobEvent
from ..schema_management import assert_module_ready
from ..vehicle_updates import publish_vehicle_update
from .auth import get_current_user

def _schema_ready(db: Session = Depends(get_db)):
    assert_module_ready(db, 'service_jobs', detail_prefix='Servisní zakázky nejsou připravené')
    assert_module_ready(db, 'vehicle_updates', detail_prefix='Upozornění vozidla nejsou připravená')


router = APIRouter(tags=['service-jobs-v1'], dependencies=[Depends(_schema_ready)])


class JobCreate(BaseModel):
    client_id: UUID
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=10000)
    mileage: Optional[int] = Field(default=None, ge=0, le=10000000)


class JobUpdate(BaseModel):
    client_id: UUID
    expected_version: int = Field(ge=1)
    status: Optional[Literal['in_progress', 'completed', 'cancelled']] = None
    message: str = Field(min_length=1, max_length=10000)
    mileage: Optional[int] = Field(default=None, ge=0, le=10000000)
    price: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)


def _digest(data):
    return sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()


def _owner_id(db, vehicle_id):
    assignment = get_primary_vehicle_owner_assignment(db, vehicle_id)
    if not assignment:
        raise HTTPException(409, 'Vozidlo nemá aktuálního vlastníka.')
    return assignment.customer_id


def _role(user):
    return str(user.role or '').strip().lower()


def _service(user):
    if _role(user) != 'service' or user.is_disabled or user.is_deleted:
        raise HTTPException(403, 'Zakázku může měnit pouze oprávněný servis.')


def _authorize(db, job, user, write=False):
    if not job:
        raise HTTPException(404, 'Zakázka nebyla nalezena.')
    owner_id = _owner_id(db, job.vehicle_id)
    assignment = get_primary_vehicle_owner_assignment(db, job.vehicle_id)
    # Private progress belongs to the ownership period captured at acceptance.
    if (owner_id != job.owner_id or assignment.id != job.ownership_id
            or (assignment.owned_from or assignment.assigned_at) != job.ownership_started_at):
        raise HTTPException(404, 'Zakázka nebyla nalezena.')
    if not write and user.id == owner_id and not user.is_disabled and not user.is_deleted:
        return None
    _service(user)
    if user.id != job.service_id:
        raise HTTPException(404, 'Zakázka nebyla nalezena.')
    if write:
        return require_service_vehicle_link(db, current_user=user, vehicle_id=job.vehicle_id, require_create_record=True)
    link = get_active_vehicle_service_link(db, service_customer_id=user.id, vehicle_id=job.vehicle_id)
    if not link or not link.scope_vehicle_history_read:
        raise HTTPException(403, 'Přístup servisu k vozidlu byl odvolán.')
    return link


def _serialize(db, job):
    return {key: getattr(job, key) for key in ('id', 'vehicle_id', 'service_id', 'status', 'title', 'description', 'mileage', 'version', 'created_at', 'updated_at', 'completed_at', 'final_record_id')} | {
        'events': [{key: getattr(event, key) for key in ('id', 'status', 'message', 'created_at', 'actor_id')}
                   for event in db.query(ServiceJobEvent).filter_by(job_id=job.id).order_by(ServiceJobEvent.id).all()]}


@router.get('/vehicles/{vehicle_id}/service-jobs')
def list_jobs(vehicle_id: int, current_user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.is_disabled or current_user.is_deleted:
        raise HTTPException(403, 'Účet není aktivní.')
    owner_id = _owner_id(db, vehicle_id)
    assignment = get_primary_vehicle_owner_assignment(db, vehicle_id)
    query = db.query(ServiceJob).filter_by(vehicle_id=vehicle_id, owner_id=owner_id, ownership_id=assignment.id,
        ownership_started_at=assignment.owned_from or assignment.assigned_at)
    if current_user.id != owner_id:
        _service(current_user)
        link = get_active_vehicle_service_link(db, service_customer_id=current_user.id, vehicle_id=vehicle_id)
        if not link or not link.scope_vehicle_history_read:
            raise HTTPException(403, 'Servis nemá přístup k vozidlu.')
        query = query.filter_by(service_id=current_user.id)
    return {'items': [_serialize(db, job) for job in query.order_by(ServiceJob.id.desc()).all()]}


@router.get('/service-jobs/{job_id}')
def get_job(job_id: int, current_user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    job = db.get(ServiceJob, job_id)
    _authorize(db, job, current_user)
    return _serialize(db, job)


def create_job_from_intake(db, *, intake, current_user):
    """Join legacy intake to the lifecycle in its existing transaction; never commit."""
    _service(current_user)
    lock_vehicle_access(db, intake.vehicle_id)
    require_service_vehicle_link(db, current_user=current_user, vehicle_id=intake.vehicle_id, require_create_record=True)
    assert_module_ready(db, 'service_jobs', detail_prefix='Servisní zakázky nejsou připravené')
    existing = db.query(ServiceJob).filter_by(intake_id=intake.id).first()
    if existing:
        _authorize(db, existing, current_user, write=True)
        return existing
    vehicle = db.get(Vehicle, intake.vehicle_id)
    owner_id = _owner_id(db, intake.vehicle_id)
    if owner_id != intake.customer_id:
        raise HTTPException(409, 'Vlastník vozidla se změnil. Obnovte příjemku.')
    assignment = get_primary_vehicle_owner_assignment(db, vehicle.id)
    client_id = str(uuid5(NAMESPACE_URL, f'toozservis:service-intake:{intake.id}'))
    job = ServiceJob(tenant_id=vehicle.tenant_id, vehicle_id=vehicle.id,
        service_id=current_user.id, owner_id=owner_id, intake_id=intake.id,
        ownership_id=assignment.id, ownership_started_at=assignment.owned_from or assignment.assigned_at,
        vin_snapshot=vehicle.vin, client_id=client_id,
        creation_hash=_digest({'intake_id': intake.id}), title='Servisní zakázka',
        description=intake.work_description, mileage=intake.odometer_km)
    db.add(job)
    db.flush()
    db.add(ServiceJobEvent(job_id=job.id, actor_id=current_user.id, client_id=client_id,
        payload_hash=job.creation_hash, status='received',
        message=intake.work_description or 'Vozidlo přijato do servisu.'))
    db.flush()
    publish_vehicle_update(db, vehicle_id=job.vehicle_id, actor_id=current_user.id,
        event_type='job.received', title='Vozidlo přijato do servisu',
        message=intake.work_description or 'Servis uložil příjem vozidla.',
        source_type='service_job', source_id=job.id,
        dedupe_key=f'service-job:{job.id}:created', service_job_id=job.id)
    return job


@router.post('/vehicles/{vehicle_id}/service-jobs')
def create_job(vehicle_id: int, payload: JobCreate, current_user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    _service(current_user)
    lock_vehicle_access(db, vehicle_id)
    require_service_vehicle_link(db, current_user=current_user, vehicle_id=vehicle_id, require_create_record=True)
    owner_id = _owner_id(db, vehicle_id)
    digest = _digest({'vehicle_id': vehicle_id, **payload.model_dump()})
    existing = db.query(ServiceJob).filter_by(service_id=current_user.id, client_id=str(payload.client_id)).first()
    if existing:
        _authorize(db, existing, current_user, write=True)
        if existing.creation_hash != digest:
            raise HTTPException(409, 'Stejný identifikátor již patří jiné zakázce.')
        return _serialize(db, existing)
    if not payload.title.strip():
        raise HTTPException(422, 'Vyplňte název zakázky.')
    vehicle = db.get(Vehicle, vehicle_id)
    assignment = get_primary_vehicle_owner_assignment(db, vehicle_id)
    job = ServiceJob(tenant_id=vehicle.tenant_id, vehicle_id=vehicle_id, service_id=current_user.id,
        owner_id=owner_id, ownership_id=assignment.id, ownership_started_at=assignment.owned_from or assignment.assigned_at, vin_snapshot=vehicle.vin, client_id=str(payload.client_id), creation_hash=digest,
        title=payload.title.strip(), description=payload.description, mileage=payload.mileage)
    db.add(job)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        # The service-wide UUID also protects concurrent creates for different vehicles.
        raise HTTPException(409, 'Identifikátor zakázky již byl použit. Obnovte stav.')
    db.add(ServiceJobEvent(job_id=job.id, actor_id=current_user.id, client_id=str(payload.client_id),
        payload_hash=digest, status='received', message=payload.description or 'Vozidlo přijato do servisu.'))
    db.flush()
    publish_vehicle_update(db, vehicle_id=job.vehicle_id, actor_id=current_user.id,
        event_type='job.received', title='Vozidlo přijato do servisu',
        message=payload.description or job.title, source_type='service_job', source_id=job.id,
        dedupe_key=f'service-job:{job.id}:created', service_job_id=job.id)
    db.commit()
    return _serialize(db, job)


@router.post('/service-jobs/{job_id}/updates')
def update_job(job_id: int, payload: JobUpdate, current_user: Customer = Depends(get_current_user), db: Session = Depends(get_db)):
    _service(current_user)
    job = db.get(ServiceJob, job_id)
    if not job:
        raise HTTPException(404, 'Zakázka nebyla nalezena.')
    lock_vehicle_access(db, job.vehicle_id)
    db.refresh(job)
    link = _authorize(db, job, current_user, write=True)
    digest = _digest(payload.model_dump())
    previous = db.query(ServiceJobEvent).filter_by(job_id=job.id, client_id=str(payload.client_id)).first()
    if previous:
        if previous.payload_hash != digest:
            raise HTTPException(409, 'Stejný identifikátor již patří jiné aktualizaci.')
        return _serialize(db, job)
    if job.version != payload.expected_version:
        raise HTTPException(409, 'Zakázka se změnila. Obnovte její stav.')
    if job.status in ('completed', 'cancelled'):
        raise HTTPException(409, 'Ukončenou zakázku již nelze měnit.')
    if not payload.message.strip():
        raise HTTPException(422, 'Vyplňte zprávu pro vlastníka vozidla.')
    target = payload.status or job.status
    if target == 'completed' and job.status != 'in_progress':
        raise HTTPException(409, 'Před dokončením nejprve zahajte práci.')
    if payload.price is not None and target != 'completed':
        raise HTTPException(422, 'Cenu uveďte při dokončení zakázky.')
    now = datetime.utcnow()
    job.status, job.updated_at, job.version = target, now, job.version + 1
    if payload.mileage is not None:
        job.mileage = payload.mileage
    if target == 'completed':
        # Completion and final history entry share this transaction and vehicle lock.
        history = db.query(ServiceJobEvent).filter_by(job_id=job.id).order_by(ServiceJobEvent.id).all()
        timeline_note = '\n'.join(f'{item.created_at.isoformat()} [{item.status}] {item.message}' for item in history)
        timeline_note += f'\n{now.isoformat()} [completed] {payload.message.strip()}'
        record = ServiceRecord(tenant_id=job.tenant_id, vehicle_id=job.vehicle_id, user_id=current_user.id,
            performed_at=now, mileage=job.mileage, description=payload.message.strip(),
            price=payload.price, note=timeline_note, category=job.title, created_by_ai=False)
        record._skip_vehicle_update = True
        attach_service_access_to_record(record=record, current_user=current_user, access_link=link)
        db.add(record)
        db.flush()
        from .service_records import _service_record_snapshot, _snapshot_json_and_hash
        snapshot, record.snapshot_hash = _snapshot_json_and_hash(_service_record_snapshot(record))
        audit = ServiceRecordAuditLog(tenant_id=job.tenant_id, service_record_id=record.id, vehicle_id=job.vehicle_id,
            changed_by_user_id=current_user.id, action='create', previous_snapshot_json='{}',
            new_snapshot_json=snapshot, snapshot_hash=record.snapshot_hash, change_reason='service_job_completion')
        audit._skip_vehicle_update = True
        db.add(audit)
        job.final_record_id, job.completed_at = record.id, now
    db.add(ServiceJobEvent(job_id=job.id, actor_id=current_user.id, client_id=str(payload.client_id),
        payload_hash=digest, status=target, message=payload.message.strip()))
    db.flush()
    titles = {'in_progress': 'Na vozidle probíhá oprava', 'completed': 'Servis vozidla dokončen',
              'cancelled': 'Servisní zakázka zrušena', 'received': 'Nová informace ze servisu'}
    publish_vehicle_update(db, vehicle_id=job.vehicle_id, actor_id=current_user.id,
        event_type=f'job.{target}' if payload.status else 'job.updated',
        title=titles[target] if payload.status else 'Nová informace ze servisu',
        message=payload.message.strip(), source_type='service_job', source_id=job.id,
        dedupe_key=f'service-job:{job.id}:update:{payload.client_id}', service_job_id=job.id)
    db.commit()
    return _serialize(db, job)
