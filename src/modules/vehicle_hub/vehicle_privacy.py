"""Privacy boundaries follow the owner who supplied data, not the current VIN owner."""
import json
from datetime import date, datetime

from fastapi import HTTPException
from sqlalchemy import or_
from src.core.rbac import is_admin
from .models import (VehicleOwnership, VehicleOwnershipArchive, VehicleRecordPrivacy,
    VehicleRepairPrivacy, VehicleAttachmentPrivacy, ServiceRecord, RepairPhotoSession, Reminder, Vehicle)

PRIVATE_PROFILE_FIELDS = ('nickname', 'notes', 'tyres_info', 'insurance_provider', 'insurance_valid_until',
    'photo_path', 'orv_number', 'orv_scan_source', 'orv_front_image_path', 'orv_back_image_path',
    'orv_scanned_at', 'orv_confidence_json', 'data_trust_state')
IDENTITY_FIELDS = ('brand', 'model', 'year', 'engine', 'vin', 'plate', 'stk_valid_until', 'current_mileage_km')
TECHNICAL_CATEGORIES = {'OLEJ', 'STK', 'SERVIS', 'PNEU', 'BRZDY', 'OPRAVA', 'ÚDRŽBA',
    'Výměna oleje', 'Pravidelná údržba', 'Oprava', 'Pneumatiky', 'Brzdy', 'Kontrola tachometru'}


def attachment_keys(raw):
    try: items = json.loads(raw or '[]')
    except (ValueError, TypeError): return set()
    if not isinstance(items, list): return set()
    return {str(item[field]) for item in items if isinstance(item, dict)
            for field in ('storage_key', 'path') if item.get(field)}


def prepare_owner_change(db, vehicle, new_owner_id):
    """Called under the vehicle write lock, before changing tenant or private fields."""
    periods = (db.query(VehicleOwnership).filter_by(vehicle_id=vehicle.id, ownership_type='owner')
        .order_by(VehicleOwnership.is_active.desc(), VehicleOwnership.owned_from.desc(), VehicleOwnership.id.desc()).populate_existing().all())
    if not periods or periods[0].customer_id == new_owner_id:
        return  # First assignment or the same owner's recovery, not a disclosure.
    period = periods[0]
    key = f'{vehicle.id}:{period.id}:{(period.owned_from or period.assigned_at).isoformat()}'
    existing = db.query(VehicleOwnershipArchive).filter_by(period_key=key).first()
    if existing:
        return  # transfer helper and assignment helper share this idempotent boundary.
    # Read the committed fields after the row lock, not a stale ORM object or
    # replacement values submitted together with an administrator's transfer.
    with db.no_autoflush:
        original = db.execute(Vehicle.__table__.select().where(Vehicle.id == vehicle.id)).mappings().one()
    profile = {field: original.get(field) for field in PRIVATE_PROFILE_FIELDS + IDENTITY_FIELDS}
    profile = {key: value.isoformat() if isinstance(value, (date, datetime)) else value for key, value in profile.items()}
    archive = VehicleOwnershipArchive(vehicle_id=vehicle.id, owner_customer_id=period.customer_id,
        period_key=key, profile_json=json.dumps(profile, ensure_ascii=False))
    db.add(archive); db.flush()
    mapped_records = {row.record_id for row in db.query(VehicleRecordPrivacy).join(ServiceRecord,
        ServiceRecord.id == VehicleRecordPrivacy.record_id).filter(ServiceRecord.vehicle_id == vehicle.id)}
    known_keys = {key for (key,) in db.query(VehicleAttachmentPrivacy.storage_key)}
    for record in db.query(ServiceRecord).filter_by(vehicle_id=vehicle.id):
        if record.id in mapped_records: continue
        db.add(VehicleRecordPrivacy(record_id=record.id, archive_id=archive.id, owner_customer_id=period.customer_id))
        for file_key in attachment_keys(record.attachments):
            if file_key not in known_keys:
                known_keys.add(file_key)
                db.add(VehicleAttachmentPrivacy(storage_key=file_key, vehicle_id=vehicle.id,
                    owner_customer_id=period.customer_id, author_customer_id=record.created_by_service_customer_id or record.user_id,
                    archive_id=archive.id))
    for session in db.query(RepairPhotoSession).filter_by(vehicle_id=vehicle.id):
        if db.get(VehicleRepairPrivacy, session.id) is None:
            db.add(VehicleRepairPrivacy(session_id=session.id, archive_id=archive.id, owner_customer_id=period.customer_id))
    # Previously uploaded, still unattached files belong to the ending period too.
    db.query(VehicleAttachmentPrivacy).filter_by(vehicle_id=vehicle.id, archive_id=None,
        owner_customer_id=period.customer_id).update({'archive_id': archive.id}, synchronize_session='fetch')
    # Stop sending reminders tied to the previous owner after a transfer.
    db.query(Reminder).filter_by(vehicle_id=vehicle.id, customer_id=period.customer_id).update(
        {"is_completed": True}, synchronize_session="fetch")
    for field in PRIVATE_PROFILE_FIELDS: setattr(vehicle, field, None)
    vehicle.nickname = ' '.join(str(getattr(vehicle, field) or '') for field in ('brand','model')).strip() or 'Vozidlo'
    db.flush()


def can_read_record_private(db, record, actor):
    if is_admin(actor.role): return True
    privacy = db.get(VehicleRecordPrivacy, record.id)
    return privacy is None or actor.id in (privacy.owner_customer_id, record.created_by_service_customer_id, record.user_id)


def private_record_filter(db, actor):
    if is_admin(actor.role): return True
    protected = db.query(VehicleRecordPrivacy.record_id).filter(VehicleRecordPrivacy.record_id == ServiceRecord.id,
        or_(VehicleRecordPrivacy.owner_customer_id.is_(None), VehicleRecordPrivacy.owner_customer_id != actor.id)).exists()
    return or_(~protected, ServiceRecord.user_id == actor.id, ServiceRecord.created_by_service_customer_id == actor.id)


def technical_record(record):
    # New transient model, not mutation of the original evidence or ORM identity.
    view = ServiceRecord(id=record.id, vehicle_id=record.vehicle_id, performed_at=record.performed_at,
        mileage=record.mileage, description='Servisní záznam před převodem vozidla',
        category=record.category if record.category in TECHNICAL_CATEGORIES else None,
        created_by_ai=False, is_deleted=False)
    view.is_historical_summary = True
    return view


def record_for_actor(db, record, actor):
    if can_read_record_private(db, record, actor): return record
    if record.is_deleted: raise HTTPException(404, 'Servisní záznam nebyl nalezen.')
    return technical_record(record)


def require_private_record(db, record, actor):
    if not can_read_record_private(db, record, actor):
        raise HTTPException(403, 'Záznam původního vlastníka nelze měnit. Můžete přidat vlastní nový záznam.')


def register_attachment(db, *, vehicle_id, key, actor):
    from .ownership import get_primary_vehicle_owner_assignment
    ownership = get_primary_vehicle_owner_assignment(db, vehicle_id)
    db.add(VehicleAttachmentPrivacy(storage_key=key, vehicle_id=vehicle_id,
        owner_customer_id=ownership.customer_id if ownership else None, author_customer_id=actor.id))
    db.flush()


def require_attachment_private(db, *, vehicle_id, key, actor):
    if is_admin(actor.role): return
    row = db.get(VehicleAttachmentPrivacy, key)
    if row is not None:
        if row.vehicle_id == vehicle_id and actor.id in (row.owner_customer_id, row.author_customer_id): return
        # An approved service can read the current owner's uploaded documents;
        # old owner documents never become available with the new owner's grant.
        from .ownership import get_primary_vehicle_owner_assignment
        current = get_primary_vehicle_owner_assignment(db, vehicle_id)
        if row.vehicle_id == vehicle_id and current and row.owner_customer_id == current.customer_id and row.archive_id is None:
            return  # Caller has already checked current vehicle/service access.
        raise HTTPException(403, 'K této soukromé příloze nemáte přístup.')
    if db.query(VehicleOwnershipArchive.id).filter_by(vehicle_id=vehicle_id).first():
        raise HTTPException(403, 'Příloha nemá ověřené přiřazení k vašemu období vlastnictví.')
    # Compatibility only for files on vehicles with no transfer boundary yet.


def may_read_repair_private(db, row, actor):
    if is_admin(actor.role) or row.service_id == actor.id: return True
    boundary = db.get(VehicleRepairPrivacy, row.id)
    return boundary is None or boundary.owner_customer_id == actor.id


def require_attachment_write_period(db, *, vehicle_id, key, record_id=None):
    """Reading original evidence does not authorize sharing it with a new owner."""
    file = db.get(VehicleAttachmentPrivacy, key)
    if file is None or file.archive_id is None:
        return
    record = db.get(VehicleRecordPrivacy, record_id) if record_id else None
    if record and record.archive_id == file.archive_id:
        return  # Existing private record remains in the original period.
    from .ownership import get_primary_vehicle_owner_assignment
    current = get_primary_vehicle_owner_assignment(db, vehicle_id)
    if current and current.customer_id == file.owner_customer_id:
        return  # The same person's own data, not disclosure to another account.
    raise HTTPException(403, 'Doklad předchozího vlastníka nelze připojit k novému období vlastnictví.')
