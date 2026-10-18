"""Owner-only, transactional archive/deposit decisions. Never commit here."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from hmac import compare_digest
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import func
from .models import Vehicle, VehicleOwnershipArchive, Reservation
from .ownership import get_primary_vehicle_owner_assignment, lock_vehicle_access, release_vehicle_owner_assignment
from .service_job_models import ServiceJob
from .vehicle_lifecycle_models import VehicleLifecycleEvent
from .vehicle_privacy import prepare_owner_change
from .schema_management import assert_module_ready

END_ACTIONS = {'sold', 'removed', 'scrapped'}
MESSAGES = {
    'sold': 'Prodej byl zaznamenán. Vozidlo je v osobním archivu; kupující nebyl automaticky přiřazen.',
    'removed': 'Vozidlo bylo odebráno z aktivních vozidel. Historie zůstává v osobním archivu.',
    'scrapped': 'Oznámení o likvidaci bylo zaznamenáno do osobního archivu. Nejde o úřední vyřazení vozidla.',
    'deposited': 'Vozidlo je označeno jako v depozitu. Vlastnictví, historie i připomínky zůstávají zachované.',
    'reactivated': 'Vozidlo je znovu označeno jako v provozu. Vlastnictví a historie zůstávají zachované.',
}


def ready(db):
    assert_module_ready(db, 'vehicle_lifecycle', detail_prefix='Správa životního cyklu vozidla není připravená')


def current_owner(db, vehicle_id, actor):
    if getattr(actor, 'is_disabled', False) or getattr(actor, 'is_deleted', False):
        raise HTTPException(403, 'Účet není aktivní.')
    assignment = get_primary_vehicle_owner_assignment(db, vehicle_id)
    if not assignment or assignment.customer_id != actor.id:
        raise HTTPException(403, 'Nemáte aktuální vlastnické oprávnění k tomuto vozidlu.')
    return assignment


def period_start(assignment):
    return assignment.owned_from or assignment.assigned_at


def ownership_token(vehicle_id, assignment):
    started = period_start(assignment)
    if started.tzinfo is not None:
        started = started.astimezone(timezone.utc).replace(tzinfo=None)
    canonical = started.isoformat(timespec='microseconds')
    return sha256(f'{vehicle_id}:{assignment.id}:{canonical}'.encode()).hexdigest()


def latest_event(db, assignment):
    return db.query(VehicleLifecycleEvent).filter_by(ownership_id=assignment.id,
        ownership_started_at=period_start(assignment)).order_by(VehicleLifecycleEvent.version.desc()).first()


def current_state(db, assignment):
    last = latest_event(db, assignment)
    return (last.state, last.version) if last else ('active', 0)


def actions_for(state):
    return ['sold', 'removed', 'scrapped', 'reactivated' if state == 'deposited' else 'deposited']


def ensure_no_open_work(db, vehicle_id, assignment):
    from sqlalchemy import inspect
    from .booking_request_models import BookingRequest
    if inspect(db.connection()).has_table(BookingRequest.__tablename__):
        enquiry = db.query(BookingRequest.id).filter_by(vehicle_id=vehicle_id, ownership_id=assignment.id,
            ownership_started_at=period_start(assignment)).filter(BookingRequest.status.in_(['pending', 'proposed'])).first()
        if enquiry:
            raise HTTPException(409, 'Vozidlo má otevřený požadavek na servis. Nejdříve jej zrušte v Rezervacích nebo dokončete domluvu.')
    job = db.query(ServiceJob.id).filter_by(vehicle_id=vehicle_id, ownership_id=assignment.id,
        ownership_started_at=period_start(assignment)).filter(
            ServiceJob.status.notin_(['completed', 'cancelled'])).first()
    if job:
        raise HTTPException(409, 'Vozidlo má rozpracovanou servisní zakázku. Nejdříve ji se servisem dokončete nebo zrušte.')
    booking = db.query(Reservation.id).filter(Reservation.vehicle_id == vehicle_id,
        Reservation.customer_id == assignment.customer_id,
        func.upper(func.trim(Reservation.status)).in_(['PENDING', 'CONFIRMED']),
        Reservation.start_datetime >= datetime.utcnow()).first()
    if booking:
        raise HTTPException(409, 'Vozidlo má budoucí rezervaci. Nejdříve ji zrušte nebo vyřešte se servisem.')


def archive_and_release(db, *, vehicle, assignment, actor_id, action, note, effective_date):
    """Caller holds vehicle lock. Keep this before release, never after."""
    ensure_no_open_work(db, vehicle.id, assignment)
    key = f'{vehicle.id}:{assignment.id}:{period_start(assignment).isoformat()}'
    prepare_owner_change(db, vehicle, None)
    archive = db.query(VehicleOwnershipArchive).filter_by(period_key=key,
        owner_customer_id=assignment.customer_id).one()
    profile = json.loads(archive.profile_json)
    profile['lifecycle'] = {'action': action, 'note': note, 'effective_date': effective_date.isoformat(),
        'reported_at': datetime.utcnow().isoformat(), 'reported_by': actor_id,
        'owner_reported': actor_id == assignment.customer_id, 'official_registry_change': False}
    archive.profile_json = json.dumps(profile, ensure_ascii=False)
    # Release helper derives the same owner and revokes both generations of grants.
    from .models import Customer
    owner = db.get(Customer, assignment.customer_id)
    if not owner or not release_vehicle_owner_assignment(db, vehicle=vehicle, owner=owner,
            revoked_by_customer_id=actor_id):
        raise HTTPException(409, 'Vlastnictví vozidla se změnilo. Obnovte jeho stav.')
    db.flush()
    return archive


def apply_action(db, *, vehicle_id, actor, payload, legacy_assignment=None):
    ready(db)
    if getattr(actor, 'is_disabled', False) or getattr(actor, 'is_deleted', False):
        raise HTTPException(403, 'Účet není aktivní.')
    try:
        lock_vehicle_access(db, vehicle_id)
    except HTTPException as error:
        if error.status_code == 404 and legacy_assignment is None:
            raise HTTPException(403, 'Nemáte aktuální vlastnické oprávnění k tomuto vozidlu.')
        raise
    request_data = {'vehicle_id': vehicle_id, **payload.model_dump()}
    digest = sha256(json.dumps(request_data, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()
    previous = db.query(VehicleLifecycleEvent).filter_by(actor_id=actor.id,
        client_id=str(payload.client_id)).first()
    if previous:
        if previous.payload_hash != digest:
            raise HTTPException(409, 'Identifikátor této operace již byl použit pro jiné údaje.')
        return json.loads(previous.response_json)
    assignment = legacy_assignment or current_owner(db, vehicle_id, actor)
    # Legacy DELETE has already applied its existing owner/admin write policy.
    # Refresh even that assignment after the common vehicle lock.
    current = get_primary_vehicle_owner_assignment(db, vehicle_id)
    if not current or current.id != assignment.id or current.customer_id != assignment.customer_id:
        raise HTTPException(409, 'Vlastnictví vozidla se změnilo. Obnovte jeho stav.')
    assignment = current
    if payload.ownership_id != assignment.id:
        raise HTTPException(409, 'Vlastnictví vozidla se změnilo. Obnovte jeho stav.')
    if not compare_digest(payload.ownership_token, ownership_token(vehicle_id, assignment)):
        raise HTTPException(409, 'Vlastnické období vozidla se změnilo. Obnovte jeho stav.')
    state, version = current_state(db, assignment)
    if version != payload.expected_version:
        raise HTTPException(409, 'Stav vozidla se změnil. Obnovte jej před další úpravou.')
    if payload.action == 'deposited' and state != 'active':
        raise HTTPException(409, 'Vozidlo již je v depozitu.')
    if payload.action == 'reactivated' and state != 'deposited':
        raise HTTPException(409, 'Do provozu lze vrátit pouze vozidlo v depozitu.')
    today = datetime.now(ZoneInfo('Europe/Prague')).date()
    effective_date = payload.effective_date or today
    if effective_date > today:
        raise HTTPException(422, 'Datum události nemůže být v budoucnosti.')
    vehicle = db.get(Vehicle, vehicle_id)
    archive = None
    if payload.action in END_ACTIONS:
        archive = archive_and_release(db, vehicle=vehicle, assignment=assignment, actor_id=actor.id,
            action=payload.action, note=payload.note, effective_date=effective_date)
        new_state = 'archived'
    else:
        new_state = 'deposited' if payload.action == 'deposited' else 'active'
    result = {'vehicle_id': vehicle_id, 'action': payload.action, 'state': new_state,
        'version': version + 1, 'archive_id': archive.id if archive else None, 'message': MESSAGES[payload.action]}
    db.add(VehicleLifecycleEvent(vehicle_id=vehicle_id, ownership_id=assignment.id,
        ownership_started_at=period_start(assignment), owner_id=assignment.customer_id,
        actor_id=actor.id, client_id=str(payload.client_id), payload_hash=digest,
        action=payload.action, state=new_state, version=version+1, note=payload.note,
        effective_date=effective_date, archive_id=archive.id if archive else None,
        response_json=json.dumps(result, ensure_ascii=False)))
    db.flush()
    return result
