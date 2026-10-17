"""Transactional publication for every registered service ORM writer.

No network delivery inside a transaction. A failed business mutation cannot
leave a notification behind. Captured recipients never change after a transfer.
"""
from datetime import datetime
from hashlib import sha256
from uuid import uuid4
from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session
from .vehicle_update_models import VehicleUpdate, VehicleUpdateReceipt


def publish_vehicle_update(db, *, vehicle_id, actor_id, event_type, title, message,
                           source_type, source_id, dedupe_key, service_job_id=None):
    from .models import Customer, Vehicle, VehicleOwnership
    from .ownership import lock_vehicle_access
    from .schema_management import assert_module_ready
    assert_module_ready(db, "vehicle_updates", detail_prefix="Upozornění vozidel nejsou připravena")
    lock_vehicle_access(db, vehicle_id)
    owner = db.query(VehicleOwnership).filter(
        VehicleOwnership.vehicle_id == vehicle_id, VehicleOwnership.is_active.is_(True),
        VehicleOwnership.is_primary.is_(True)).order_by(VehicleOwnership.id).first()
    actor = db.get(Customer, actor_id)
    vehicle = db.get(Vehicle, vehicle_id)
    if owner is None or actor is None or vehicle is None or owner.customer_id == actor_id:
        return None
    if any(isinstance(row, VehicleUpdate) and row.dedupe_key == dedupe_key for row in db.new) or db.query(VehicleUpdate.id).filter_by(dedupe_key=dedupe_key).first():
        return None
    row = VehicleUpdate(tenant_id=vehicle.tenant_id, vehicle_id=vehicle_id,
        recipient_id=owner.customer_id, ownership_id=owner.id,
        ownership_started_at=owner.owned_from or owner.assigned_at,
        actor_id=actor_id, event_type=event_type,
        title=title, message=message, source_type=source_type, source_id=source_id,
        dedupe_key=dedupe_key, service_job_id=service_job_id)
    db.add(row)
    return row


@event.listens_for(Session, "before_flush")
def capture_service_changes(db, context, instances):
    from .models import (Customer, Vehicle, ServiceRecord, ServiceRecordAuditLog,
        ServiceIntake, ServiceAccessRequest, RepairPhotoSession, RepairEvidencePhoto,
        Reminder, VehicleAttachmentPrivacy)
    from .schema_management import assert_module_ready
    candidates = []
    actor_context = db.info.get("vehicle_update_actor_id")
    for row in list(db.new) + list(db.dirty) + list(db.deleted):
        if getattr(row, "_skip_vehicle_update", False):
            continue
        fresh = row in db.new
        actor = vehicle_id = None
        kind = title = message = None
        if row in db.deleted and not isinstance(row, Reminder):
            continue
        if isinstance(row, VehicleUpdate) and not fresh:
            if db.is_modified(row):
                raise RuntimeError("Vehicle update events are immutable")
        elif isinstance(row, ServiceAccessRequest) and fresh:
            actor, vehicle_id = row.service_customer_id, row.vehicle_id
            kind, title = "access_request.created", "Servis žádá o přístup k vozidlu"
            message = "Zkontrolujte žádost a rozhodněte o přístupu v sekci Servisy."
        elif isinstance(row, ServiceIntake) and fresh:
            actor, vehicle_id = row.service_id, row.vehicle_id
            kind, title, message = "intake.received", "Vozidlo přijato do servisu", "Servis uložil příjem vozidla."
        elif isinstance(row, ServiceRecord) and fresh:
            actor, vehicle_id = row.created_by_service_customer_id or row.user_id, row.vehicle_id
            kind, title, message = "record.created", "Nový servisní záznam", "Servis přidal záznam do historie vozidla."
        elif isinstance(row, ServiceRecordAuditLog) and fresh:
            actor, vehicle_id = row.changed_by_user_id, row.vehicle_id
            kind, title, message = "record.updated", "Změna servisního záznamu", "V historii vozidla je nová úprava."
        elif isinstance(row, RepairPhotoSession) and fresh:
            actor, vehicle_id = row.service_id, row.vehicle_id
            kind, title, message = "repair.created", "Nová dokumentace opravy", "Servis založil fotodokumentaci opravy."
        elif isinstance(row, RepairEvidencePhoto) and fresh:
            session = db.get(RepairPhotoSession, row.session_id)
            actor, vehicle_id = row.author_id, session.vehicle_id if session else None
            kind, title, message = "repair.photo_added", "Nová fotografie opravy", "Servis přidal fotografii k opravě vozidla."
        elif isinstance(row, Reminder) and (fresh or row in db.deleted or db.is_modified(row)):
            actor, vehicle_id = actor_context or (row.created_by_service_customer_id if fresh else None), row.vehicle_id
            kind, title, message = "reminder.updated", "Aktualizace připomínky vozidla", "Servis přidal nebo upravil připomínku."
            if row in db.deleted:
                kind, title, message = "reminder.deleted", "Odebraná připomínka vozidla", "Servis odebral připomínku vozidla."
        elif isinstance(row, VehicleAttachmentPrivacy) and fresh:
            actor, vehicle_id = row.author_customer_id, row.vehicle_id
            kind, title, message = "document.added", "Nový dokument vozidla", "Servis nahrál dokument k vozidlu."
        elif isinstance(row, Vehicle) and not fresh and db.is_modified(row, include_collections=False):
            actor, vehicle_id = actor_context, row.id
            kind, title, message = "vehicle.updated", "Aktualizace vozidla", "Servis upravil informace o vozidle."
        if not actor or not vehicle_id or not kind:
            continue
        customer = db.get(Customer, actor)
        if customer is None or str(customer.role or "").strip().lower() != "service":
            continue
        assert_module_ready(db, "vehicle_updates", detail_prefix="Upozornění vozidel nejsou připravena")
        candidates.append((row, actor, vehicle_id, kind, title, message,
                           str(uuid4()) if not fresh else 'created'))
    if candidates:
        from .ownership import lock_vehicle_access
        for vehicle_id in sorted({item[2] for item in candidates}):
            lock_vehicle_access(db, vehicle_id)
        # Resolve owner only after the business flush, when all IDs exist.
        db.info.setdefault("vehicle_update_pending", []).extend(candidates)


@event.listens_for(Session, "after_flush_postexec")
def store_service_changes(db, context):
    from .models import Vehicle, VehicleOwnership
    pending = db.info.pop("vehicle_update_pending", [])
    connection = db.connection()
    for row, actor, vehicle_id, kind, title, message, operation in pending:
        owner = connection.execute(select(VehicleOwnership.id, VehicleOwnership.customer_id,
            VehicleOwnership.owned_from, VehicleOwnership.assigned_at).where(
            VehicleOwnership.vehicle_id == vehicle_id,
            VehicleOwnership.is_active.is_(True), VehicleOwnership.is_primary.is_(True)
        ).order_by(VehicleOwnership.id)).first()
        if not owner or owner.customer_id == actor:
            continue
        tenant = connection.execute(select(Vehicle.tenant_id).where(Vehicle.id == vehicle_id)).scalar()
        identity = getattr(row, "id", None)
        if identity is None:
            # Upload privacy uses a storage key instead of a numeric source ID.
            identity = vehicle_id
        state = inspect(row)
        values = {a.key: str(getattr(row, a.key)) for a in state.mapper.column_attrs}
        fingerprint = sha256(repr(sorted(values.items())).encode()).hexdigest()
        key = f"{row.__tablename__}:{getattr(row, 'id', getattr(row, 'storage_key', vehicle_id))}:{kind}:{fingerprint}:{operation}"
        # Use a digest to bound keys even for long storage paths.
        key = sha256(key.encode()).hexdigest()
        if connection.execute(select(VehicleUpdate.id).where(VehicleUpdate.dedupe_key == key)).first():
            continue
        connection.execute(VehicleUpdate.__table__.insert().values(
            tenant_id=tenant, vehicle_id=vehicle_id, recipient_id=owner.customer_id,
            ownership_id=owner.id, actor_id=actor,
            ownership_started_at=owner.owned_from or owner.assigned_at,
            event_type=kind, title=title, message=message, source_type=row.__tablename__,
            source_id=identity, dedupe_key=key, occurred_at=datetime.utcnow()))


@event.listens_for(Session, "after_rollback")
def discard_pending_changes(db):
    db.info.pop("vehicle_update_pending", None)


@event.listens_for(Session, "before_flush")
def forbid_event_removal(db, context, instances):
    if any(isinstance(row, VehicleUpdate) for row in db.deleted):
        raise RuntimeError("Vehicle update events are immutable")
