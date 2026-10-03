"""Account erasure with explicit ownership scope and transactional file cleanup.

The caller owns the transaction. This function never commits, deletes a tenant,
calls a storage provider, or follows a legacy email over an explicit ownership.
"""
import json
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, and_, func, inspect, or_

from src.core.file_erasure import enqueue_file_erasure
from src.modules.vehicle_hub import models as m
from src.modules.vehicle_hub.email_verification import EmailVerification
from src.core.mfa import MFAState, MFALoginChallenge, MFAAttemptBudget
from src.modules.vehicle_hub.ownership import get_owned_vehicle_ids
from src.modules.vehicle_hub.database import Base


class ErasedTenant(Base):
    """No identity data; prevents a delayed callback from enabling another charge."""
    __tablename__ = "erased_account_tenants"
    tenant_id = Column(Integer, ForeignKey("tenants.id"), primary_key=True)
    erased_at = Column(DateTime, nullable=False, default=datetime.utcnow)


def tenant_was_erased(db, tenant_id: int) -> bool:
    return (inspect(db.connection()).has_table(ErasedTenant.__tablename__)
            and db.get(ErasedTenant, tenant_id) is not None)


def _attachments(raw):
    if not raw:
        return []
    payload = json.loads(raw)
    if not isinstance(payload, list):
        raise ValueError("Invalid attachment inventory")
    return [str(item.get("storage_key") or item.get("path")) for item in payload
            if isinstance(item, dict) and (item.get("storage_key") or item.get("path"))]


def erase_account(db, customer) -> dict[str, int]:
    account_id, tenant_id = customer.id, customer.tenant_id
    email = (customer.email or "").strip().lower()
    counts = {}
    files = set()

    def remove(model, condition, label=None):
        count = db.query(model).filter(condition).delete(synchronize_session=False)
        key = label or model.__tablename__
        counts[key] = counts.get(key, 0) + count

    def detach(model, column, **fields):
        fields[column.key] = None
        db.query(model).filter(column == account_id).update(fields, synchronize_session=False)

    def file(directory, value):
        if value:
            files.add((directory, value))

    # Lock the identity first; all writes keep their FK to this identity until commit.
    db.query(m.Customer).filter_by(id=account_id).with_for_update().one()
    get_owned_vehicle_ids(db, customer, tenant_id=tenant_id)  # Backfill safe legacy rows only.
    assignments = db.query(m.VehicleOwnership).filter_by(
        customer_id=account_id, ownership_type="owner", is_active=True,
    ).with_for_update().all()
    owned_ids = {row.vehicle_id for row in assignments}
    # Merged originals are hidden from normal browsing, but their original
    # owner's erasure must still cover the private profile and its documents.
    alias_ids = {identity for (identity,) in db.query(m.Vehicle.id).execution_options(include_merged_vehicles=True).filter(
        m.Vehicle.merged_into_id.isnot(None), func.lower(m.Vehicle.user_email) == email)}
    owned_ids |= alias_ids
    other_owners = db.query(m.VehicleOwnership).filter(
        m.VehicleOwnership.vehicle_id.in_(owned_ids), m.VehicleOwnership.customer_id != account_id,
        m.VehicleOwnership.ownership_type == "owner", m.VehicleOwnership.is_active.is_(True),
    ).with_for_update().all()
    shared_ids = {row.vehicle_id for row in other_owners}
    historical_ids = {vehicle_id for (vehicle_id,) in db.query(m.VehicleOwnershipArchive.vehicle_id).filter(
        m.VehicleOwnershipArchive.vehicle_id.in_(owned_ids - shared_ids),
        m.VehicleOwnershipArchive.owner_customer_id.isnot(None),
        m.VehicleOwnershipArchive.owner_customer_id != account_id)}
    surviving_alias_targets = {identity for (identity,) in db.query(m.Vehicle.merged_into_id)
        .execution_options(include_merged_vehicles=True).filter(
            m.Vehicle.merged_into_id.in_(owned_ids - shared_ids), ~m.Vehicle.id.in_(alias_ids))}
    historical_ids |= surviving_alias_targets
    # The current account cannot erase another person's original documents.
    # Close its own period first so the normal erasure graph removes only its data.
    from .vehicle_privacy import prepare_owner_change
    for vehicle in db.query(m.Vehicle).execution_options(include_merged_vehicles=True).filter(m.Vehicle.id.in_(historical_ids)).with_for_update().populate_existing():
        prepare_owner_change(db, vehicle, None)
        # A merge may already have archived this ownership period. Never leave
        # its current private fields behind merely because the archive exists.
        if vehicle.id in alias_ids:
            from .vehicle_privacy import PRIVATE_PROFILE_FIELDS
            for field in PRIVATE_PROFILE_FIELDS: setattr(vehicle, field, None)
            vehicle.nickname = 'Vozidlo'
        db.add(m.VehicleOwnershipArchive(vehicle_id=vehicle.id, owner_customer_id=None,
            period_key=f"owner-erased:{vehicle.id}:{account_id}", profile_json="{}"))
    db.flush()
    vehicle_ids = owned_ids - shared_ids - historical_ids
    vehicles = db.query(m.Vehicle).execution_options(include_merged_vehicles=True).filter(m.Vehicle.id.in_(vehicle_ids)).with_for_update().all()
    for vehicle in vehicles:
        file("vehicle_photos", vehicle.photo_path)
        file("vehicle_orv_scans", vehicle.orv_front_image_path)
        file("vehicle_orv_scans", vehicle.orv_back_image_path)

    # Shared vehicles remain with an existing owner. Delegation never authorizes erasure.
    for vehicle_id in shared_ids:
        owners = sorted((row for row in other_owners if row.vehicle_id == vehicle_id), key=lambda row: row.id)
        if any(row.vehicle_id == vehicle_id and row.is_primary for row in assignments):
            for row in owners:
                row.is_primary = row is owners[0]
        owner = db.get(m.Customer, owners[0].customer_id)
        db.query(m.Vehicle).filter_by(id=vehicle_id).update({"user_email": owner.email}, synchronize_session=False)
    # Clear stale aliases on vehicles the deleting account no longer owns.
    db.query(m.Vehicle).filter(func.lower(m.Vehicle.user_email) == email,
                              ~m.Vehicle.id.in_(vehicle_ids)).update(
        {"user_email": "removed-account@invalid"}, synchronize_session=False)
    db.flush()

    # Completed ownership periods remain private and participate in erasure.
    archives = db.query(m.VehicleOwnershipArchive).filter(or_(
        m.VehicleOwnershipArchive.owner_customer_id == account_id,
        m.VehicleOwnershipArchive.vehicle_id.in_(vehicle_ids))).all()
    archive_ids = [row.id for row in archives]
    for row in archives:
        profile = json.loads(row.profile_json)
        file("vehicle_photos", profile.get("photo_path"))
        file("vehicle_orv_scans", profile.get("orv_front_image_path"))
        file("vehicle_orv_scans", profile.get("orv_back_image_path"))
    archived_records = db.query(m.VehicleRecordPrivacy.record_id).filter_by(owner_customer_id=account_id)
    archived_repairs = db.query(m.VehicleRepairPrivacy.session_id).filter_by(owner_customer_id=account_id)
    attachment_condition = or_(m.VehicleAttachmentPrivacy.owner_customer_id == account_id,
        m.VehicleAttachmentPrivacy.author_customer_id == account_id,
        m.VehicleAttachmentPrivacy.vehicle_id.in_(vehicle_ids))
    for row in db.query(m.VehicleAttachmentPrivacy).filter(attachment_condition):
        file("service_record_attachments", row.storage_key)
    # Keep a deny tombstone until the file erasure queue has succeeded.
    db.query(m.VehicleAttachmentPrivacy).filter_by(owner_customer_id=account_id).update(
        {"owner_customer_id": None, "author_customer_id": None}, synchronize_session=False)
    detach(m.VehicleAttachmentPrivacy, m.VehicleAttachmentPrivacy.author_customer_id)

    sessions = db.query(m.RepairPhotoSession).filter(or_(
        m.RepairPhotoSession.service_id == account_id, m.RepairPhotoSession.vehicle_id.in_(vehicle_ids),
        m.RepairPhotoSession.id.in_(archived_repairs),
    ))
    session_ids = [row.id for row in sessions.all()]
    photo_condition = or_(m.RepairEvidencePhoto.session_id.in_(session_ids), m.RepairEvidencePhoto.author_id == account_id)
    for row in db.query(m.RepairEvidencePhoto).filter(photo_condition).with_for_update():
        file("private_repair_photos", row.file_path)
    remove(m.RepairEvidencePhoto, photo_condition)
    remove(m.VehicleRepairPrivacy, m.VehicleRepairPrivacy.session_id.in_(session_ids))
    remove(m.RepairPhotoSession, m.RepairPhotoSession.id.in_(session_ids))

    # User-created content is removed, including copies of attachments and audit snapshots.
    record_condition = or_(m.ServiceRecord.vehicle_id.in_(vehicle_ids), m.ServiceRecord.user_id == account_id,
                           m.ServiceRecord.created_by_service_customer_id == account_id,
                           m.ServiceRecord.id.in_(archived_records))
    record_ids = [row.id for row in db.query(m.ServiceRecord).filter(record_condition)]
    record_condition = m.ServiceRecord.id.in_(record_ids)
    for row in db.query(m.ServiceRecord).filter(record_condition).with_for_update():
        for path in _attachments(row.attachments):
            file("service_record_attachments", path)
    document_condition = or_(m.ServiceDocumentIngestion.customer_id == account_id,
        m.ServiceDocumentIngestion.service_customer_id == account_id,
        m.ServiceDocumentIngestion.vehicle_id.in_(vehicle_ids),
        m.ServiceDocumentIngestion.auto_created_service_record_id.in_(record_ids))
    for row in db.query(m.ServiceDocumentIngestion).filter(document_condition).with_for_update():
        file("service_workspace_docs", row.stored_file_path)
    remove(m.ServiceDocumentIngestion, document_condition, "service_documents")
    audit_condition = or_(m.ServiceRecordAuditLog.service_record_id.in_(record_ids),
                         m.ServiceRecordAuditLog.changed_by_user_id == account_id)
    for row in db.query(m.ServiceRecordAuditLog).filter(audit_condition):
        for raw in [row.previous_snapshot_json, row.new_snapshot_json]:
            if raw:
                snapshot = json.loads(raw)
                attachments = snapshot.get("attachments") if isinstance(snapshot, dict) else None
                if attachments:
                    for path in _attachments(attachments if isinstance(attachments, str) else json.dumps(attachments)):
                        file("service_record_attachments", path)
    remove(m.ServiceRecordAuditLog, audit_condition)
    remove(m.VehicleRecordPrivacy, m.VehicleRecordPrivacy.record_id.in_(record_ids))
    remove(m.ServiceRecord, record_condition)
    detach(m.ServiceRecord, m.ServiceRecord.deleted_by_user_id, deletion_reason=None)

    scan_condition = or_(m.VehicleORVScan.vehicle_id.in_(vehicle_ids), m.VehicleORVScan.initiated_by_customer_id == account_id)
    for row in db.query(m.VehicleORVScan).filter(scan_condition).with_for_update():
        file("vehicle_orv_scans", row.front_image_path)
        file("vehicle_orv_scans", row.back_image_path)
    remove(m.VehicleORVScan, scan_condition)
    remove(m.VehicleTachometerHistoryEntry, m.VehicleTachometerHistoryEntry.vehicle_id.in_(vehicle_ids))

    for model in [m.ServiceIntake, m.Reservation]:
        remove(model, or_(model.customer_id == account_id, model.service_id == account_id, model.vehicle_id.in_(vehicle_ids)))
    remove(m.Reminder, or_(m.Reminder.customer_id == account_id, m.Reminder.vehicle_id.in_(vehicle_ids)))
    link_condition = or_(m.VehicleServiceLink.service_customer_id == account_id,
        m.VehicleServiceLink.owner_customer_id == account_id, m.VehicleServiceLink.vehicle_id.in_(vehicle_ids))
    link_ids = [row.id for row in db.query(m.VehicleServiceLink).filter(link_condition)]
    db.query(m.ServiceRecord).filter(m.ServiceRecord.service_access_link_id.in_(link_ids)).update(
        {"service_access_link_id": None}, synchronize_session=False)
    remove(m.VehicleServiceLink, link_condition)
    for column in [m.VehicleServiceLink.approved_by_customer_id, m.VehicleServiceLink.revoked_by_customer_id]:
        detach(m.VehicleServiceLink, column)
    request_condition = or_(m.ServiceAccessRequest.service_customer_id == account_id,
        m.ServiceAccessRequest.owner_customer_id == account_id, m.ServiceAccessRequest.vehicle_id.in_(vehicle_ids))
    request_ids = [row.id for row in db.query(m.ServiceAccessRequest).filter(request_condition)]
    db.query(m.VehicleServiceLink).filter(m.VehicleServiceLink.source_request_id.in_(request_ids)).update(
        {"source_request_id": None}, synchronize_session=False)
    remove(m.ServiceAccessRequest, request_condition)
    detach(m.ServiceAccessRequest, m.ServiceAccessRequest.decided_by_customer_id)
    lookup_condition = or_(m.ServiceVehicleLookupAudit.service_customer_id == account_id,
        m.ServiceVehicleLookupAudit.matched_owner_customer_id == account_id,
        m.ServiceVehicleLookupAudit.matched_vehicle_id.in_(vehicle_ids))
    lookup_ids = [row.id for row in db.query(m.ServiceVehicleLookupAudit).filter(lookup_condition)]
    db.query(m.ServiceAccessRequest).filter(m.ServiceAccessRequest.lookup_audit_id.in_(lookup_ids)).update(
        {"lookup_audit_id": None}, synchronize_session=False)
    remove(m.ServiceVehicleLookupAudit, lookup_condition)
    remove(m.ServiceVehicleAccess, or_(m.ServiceVehicleAccess.service_customer_id == account_id,
        m.ServiceVehicleAccess.customer_id == account_id, m.ServiceVehicleAccess.vehicle_id.in_(vehicle_ids)))
    detach(m.ServiceVehicleAccess, m.ServiceVehicleAccess.granted_by_customer_id)
    remove(m.ServiceCustomerLink, or_(m.ServiceCustomerLink.customer_id == account_id,
                                     m.ServiceCustomerLink.service_customer_id == account_id), "service_links")
    remove(m.ServiceCustomerInvite, or_(m.ServiceCustomerInvite.service_customer_id == account_id,
        m.ServiceCustomerInvite.linked_customer_id == account_id,
        func.lower(m.ServiceCustomerInvite.invite_email) == email), "service_invites")

    for model, customer_column, email_column in [
        (m.EmailNotificationLog, m.EmailNotificationLog.customer_id, m.EmailNotificationLog.email),
        (m.SecurityAccessLog, m.SecurityAccessLog.customer_id, m.SecurityAccessLog.user_email),
        (m.BotCommand, m.BotCommand.user_id, m.BotCommand.user_email),
    ]:
        remove(model, or_(customer_column == account_id, func.lower(email_column) == email))
    remove(m.CustomerCommand, or_(func.lower(m.CustomerCommand.customer_email) == email,
                                 m.CustomerCommand.vehicle_id.in_(vehicle_ids)))
    for model in [m.PushSubscription, m.CustomerSecuritySettings, EmailVerification, MFAState, MFALoginChallenge, MFAAttemptBudget]:
        remove(model, model.customer_id == account_id)
    remove(m.ServiceRegistrationRequest, func.lower(m.ServiceRegistrationRequest.email) == email)
    for column in [m.ServiceRegistrationRequest.reviewed_by_customer_id, m.ServiceRegistrationRequest.approved_customer_id]:
        detach(m.ServiceRegistrationRequest, column)
    remove(m.DeveloperActionAuditLog, or_(m.DeveloperActionAuditLog.developer_id == account_id,
        m.DeveloperActionAuditLog.target_resource == f"user:{account_id}"))
    # Keep proof that an administrator acted, while erasing the subject's copied
    # private payload from the new edit/merge audit records too.
    for audit in db.query(m.DeveloperActionAuditLog).filter(m.DeveloperActionAuditLog.action_type.in_(
        ['vehicle.merge', 'vehicle.update', 'vehicle.delete', 'reminder.admin_update', 'reservation.admin_update',
         'service_intake.update', 'service.workshop.update'])):
        payload = json.loads(audit.parameters_json or '{}')
        if account_id in payload.get('affected_customer_ids', []):
            audit.parameters_json = json.dumps({'private_payload_erased': True})
    for column, email_field in [(m.SecurityBlockedIp.blocked_by_customer_id, "blocked_by_email"),
                                (m.SecurityBlockedIp.unblocked_by_customer_id, "unblocked_by_email")]:
        detach(m.SecurityBlockedIp, column, **{email_field: None})
    remove(m.SystemNotification, or_(m.SystemNotification.created_by_customer_id == account_id,
        and_(m.SystemNotification.target_type == "user", m.SystemNotification.target_value == str(account_id))))
    remove(m.VehicleOwnership, or_(m.VehicleOwnership.customer_id == account_id,
                                   m.VehicleOwnership.vehicle_id.in_(vehicle_ids)))
    detach(m.VehicleOwnership, m.VehicleOwnership.assigned_by_customer_id)
    for model in (m.VehicleRecordPrivacy, m.VehicleRepairPrivacy, m.VehicleAttachmentPrivacy):
        db.query(model).filter(model.archive_id.in_(archive_ids)).update({"archive_id": None}, synchronize_session=False)
    remove(m.VehicleAttachmentPrivacy, m.VehicleAttachmentPrivacy.vehicle_id.in_(vehicle_ids))
    remove(m.VehicleOwnershipArchive, m.VehicleOwnershipArchive.id.in_(archive_ids))
    remove(m.Vehicle, m.Vehicle.id.in_(vehicle_ids))

    # Apple transaction ownership cannot be reassigned to a newly created account.
    # Apple tables are optional until the billing migration is enabled.
    from src.modules.licensing.apple_models import AppleBillingIdentity
    if inspect(db.connection()).has_table(AppleBillingIdentity.__tablename__):
        db.query(AppleBillingIdentity).filter_by(customer_id=account_id).update(
            {"customer_id": None, "tenant_id": None}, synchronize_session=False)
    remove(m.Customer, m.Customer.id == account_id)

    # Never delete an entire tenant by inference. Other owners' cars and billing
    # ledgers can still refer to it. Remove only the abandoned identity and renewal.
    if not db.query(m.Customer.id).filter_by(tenant_id=tenant_id).first():
        if db.get(ErasedTenant, tenant_id) is None:
            db.add(ErasedTenant(tenant_id=tenant_id))
        db.query(m.Tenant).filter_by(id=tenant_id).update({"name": "Odstraněný účet"}, synchronize_session=False)
        remove(m.Instance, m.Instance.tenant_id == tenant_id)
        db.query(m.LicenseSubscription).filter_by(tenant_id=tenant_id).update({
            "auto_renew_enabled": False, "init_recurring_id": None, "next_charge_at": None,
            "pending_plan_change": None, "status": "canceled", "cancel_requested_at": datetime.utcnow(),
        }, synchronize_session=False)

    # Some legacy records intentionally share the same file. Preserve references
    # belonging to surviving records rather than destroying another account's copy.
    from src.core.file_erasure import private_path
    surviving = set()
    def keep(directory, value):
        if value:
            surviving.add(private_path(directory, value))
    for photo, front, back in db.query(m.Vehicle.photo_path, m.Vehicle.orv_front_image_path, m.Vehicle.orv_back_image_path):
        keep("vehicle_photos", photo); keep("vehicle_orv_scans", front); keep("vehicle_orv_scans", back)
    for (profile_json,) in db.query(m.VehicleOwnershipArchive.profile_json):
        profile = json.loads(profile_json)
        keep("vehicle_photos", profile.get("photo_path"))
        keep("vehicle_orv_scans", profile.get("orv_front_image_path"))
        keep("vehicle_orv_scans", profile.get("orv_back_image_path"))
    for front, back in db.query(m.VehicleORVScan.front_image_path, m.VehicleORVScan.back_image_path):
        keep("vehicle_orv_scans", front); keep("vehicle_orv_scans", back)
    for (path,) in db.query(m.RepairEvidencePhoto.file_path): keep("private_repair_photos", path)
    for (path,) in db.query(m.ServiceDocumentIngestion.stored_file_path): keep("service_workspace_docs", path)
    for (raw,) in db.query(m.ServiceRecord.attachments):
        for path in _attachments(raw): keep("service_record_attachments", path)
    for old, new in db.query(m.ServiceRecordAuditLog.previous_snapshot_json, m.ServiceRecordAuditLog.new_snapshot_json):
        for raw in [old, new]:
            if raw:
                snapshot = json.loads(raw)
                attachments = snapshot.get("attachments") if isinstance(snapshot, dict) else None
                if attachments:
                    for path in _attachments(attachments if isinstance(attachments, str) else json.dumps(attachments)):
                        keep("service_record_attachments", path)
    from src.core.file_erasure import create_receipt
    from src.core.file_storage import DATA_DIR
    queued_paths = []
    for directory, value in sorted(files):
        path = private_path(directory, value)
        if path not in surviving:
            enqueue_file_erasure(db, directory, value)
            queued_paths.append(path.relative_to(DATA_DIR.resolve()).as_posix())
    counts["private_files_queued"] = len(set(queued_paths))
    db.info["account_erasure_receipt"] = create_receipt(db, queued_paths)
    return counts
