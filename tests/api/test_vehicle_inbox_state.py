"""Recipient mailbox controls never erase service/audit data or cross accounts."""
from datetime import datetime, timedelta
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import inspect
from test_vehicle_updates import ctx, publish
from src.modules.vehicle_hub.models import ServiceRecord
from src.modules.vehicle_hub.vehicle_update_models import (
    VehicleUpdate, VehicleUpdateReceipt, VehicleUpdateInboxState, VehicleUpdateInboxAction)
from src.modules.vehicle_hub.routers_v1.vehicle_updates import (
    list_updates, mark_read, update_receipt, ReceiptUpdate)


def feed(db, owner, folder="inbox", limit=30, before_id=None):
    return list_updates(before_id=before_id, limit=limit, current_user=owner, db=db, folder=folder)


def change(db, owner, update, **values):
    return update_receipt(update.id, ReceiptUpdate(**values), owner, db)


def test_explicit_read_unread_and_retry_preserve_event_and_action_history(ctx):
    db, owner, *_ = ctx
    row = publish(ctx); db.commit()
    assert feed(db, owner)["items"][0]["read"] is False
    first = change(db, owner, row, read=True)
    assert first["read"] and first["read_at"].endswith("Z")
    assert first == change(db, owner, row, read=True)
    assert db.query(VehicleUpdateInboxAction).count() == 1
    unread = change(db, owner, row, read=False)
    assert unread["read"] is False and unread["read_at"] is None
    assert unread["unread_count"] == 1
    assert change(db, owner, row, read=False) == unread
    assert db.query(VehicleUpdateReceipt).count() == 0
    actions = db.query(VehicleUpdateInboxAction).order_by(VehicleUpdateInboxAction.id).all()
    assert [(a.from_read, a.to_read) for a in actions] == [(False, True), (True, False)]
    assert db.query(VehicleUpdate).one().message == "Kontrola brzd"


def test_archive_trash_restore_and_old_read_do_not_resurrect_or_count_hidden_items(ctx):
    db, owner, *_ = ctx
    row = publish(ctx); db.commit()
    archived = change(db, owner, row, folder="archive")
    assert archived["folder"] == "archive" and archived["archived_at"]
    assert archived["deleted_at"] is None and archived["unread_count"] == 0
    assert change(db, owner, row, folder="archive") == archived
    assert feed(db, owner)["items"] == []
    assert len(feed(db, owner, "archive")["items"]) == 1
    assert feed(db, owner)["folder_counts"] == {"inbox": 0, "archive": 1, "trash": 0}
    trashed = change(db, owner, row, folder="trash")
    assert trashed["deleted_at"] and trashed["archived_at"] is None
    assert change(db, owner, row, folder="trash") == trashed
    assert mark_read(row.id, owner, db) == {"read": True}
    assert feed(db, owner, "trash")["items"][0]["read"]
    assert feed(db, owner)["items"] == []
    restored = change(db, owner, row, folder="inbox", read=False)
    assert restored["deleted_at"] is None and restored["archived_at"] is None
    assert restored["unread_count"] == 1
    assert feed(db, owner)["folder_counts"] == {"inbox": 1, "archive": 0, "trash": 0}
    assert db.query(VehicleUpdate).count() == 1
    assert db.query(VehicleUpdateInboxAction).count() == 4


@pytest.mark.parametrize("folder", ["inbox", "archive", "trash"])
def test_recipient_isolation_for_all_folders_and_mutations_even_admin(ctx, folder):
    db, owner, service, stranger, *_ = ctx
    row = publish(ctx); db.commit()
    change(db, owner, row, folder=folder)
    before = db.query(VehicleUpdateInboxAction).count()
    for other in (service, stranger):
        result = feed(db, other, folder)
        assert result["items"] == [] and result["unread_count"] == 0
        assert result["folder_counts"] == {"inbox": 0, "archive": 0, "trash": 0}
        for values in ({"read": True}, {"read": False}, {"folder": "trash"}, {"folder": "inbox"}):
            with pytest.raises(HTTPException) as error:
                change(db, other, row, **values)
            assert error.value.status_code == 404
    assert db.query(VehicleUpdateInboxAction).count() == before


def test_transfer_and_return_cannot_read_restore_or_count_former_private_inbox(ctx):
    db, owner, service, stranger, vehicle, assignment, _ = ctx
    row = publish(ctx); db.commit()
    change(db, owner, row, folder="trash")
    assignment.is_active = False; db.commit()
    for person in (owner, stranger):
        for folder in ("inbox", "archive", "trash"):
            assert feed(db, person, folder)["items"] == []
        with pytest.raises(HTTPException) as error:
            change(db, person, row, folder="inbox")
        assert error.value.status_code == 404
    assignment.is_active = True
    assignment.owned_from = datetime.utcnow() + timedelta(days=1)
    db.commit()
    assert feed(db, owner, "trash")["items"] == []
    with pytest.raises(HTTPException):
        mark_read(row.id, owner, db)
    assert db.query(VehicleUpdate).count() == 1
    assert db.query(VehicleUpdateInboxAction).count() == 1


def test_folder_pagination_does_not_drop_events_and_counts_are_not_page_counts(ctx):
    db, owner, *_ = ctx
    rows = [publish(ctx, f"folders-{i}") for i in range(9)]
    db.commit()
    for i, row in enumerate(rows):
        change(db, owner, row, folder=("inbox", "archive", "trash")[i % 3])
    for folder in ("inbox", "archive", "trash"):
        first = feed(db, owner, folder, limit=2)
        second = feed(db, owner, folder, limit=2, before_id=first["next_before_id"])
        assert first["has_more"] and not second["has_more"]
        assert first["unread_count"] == second["unread_count"] == 3
        assert first["folder_counts"] == {"inbox": 3, "archive": 3, "trash": 3}
        assert len({row["id"] for page in (first, second) for row in page["items"]}) == 3
        assert all(row["folder"] == folder for page in (first, second) for row in page["items"])


def test_trash_does_not_modify_service_record_documents_or_immutable_event(ctx):
    db, owner, service, _, vehicle, *_ = ctx
    attachments = '[{"storage_key":"synthetic/repair.pdf","name":"repair.pdf"}]'
    record = ServiceRecord(tenant_id=vehicle.tenant_id, vehicle_id=vehicle.id,
        user_id=service.id, created_by_service_customer_id=service.id,
        description="Původní oprava", attachments=attachments)
    db.add(record); db.commit()
    snapshot = [(row.id, row.title, row.message, row.source_id) for row in db.query(VehicleUpdate).all()]
    assert len(snapshot) == 2  # Record and its persisted documentation.
    for row in db.query(VehicleUpdate).all():
        change(db, owner, row, read=True, folder="trash")
    db.expire_all()
    assert db.get(ServiceRecord, record.id).attachments == attachments
    assert db.get(ServiceRecord, record.id).description == "Původní oprava"
    assert not db.get(ServiceRecord, record.id).is_deleted
    assert [(r.id, r.title, r.message, r.source_id) for r in db.query(VehicleUpdate).all()] == snapshot
    action = db.query(VehicleUpdateInboxAction).first()
    action.to_folder = "inbox"
    with pytest.raises(RuntimeError, match="immutable"):
        db.commit()
    db.rollback()
    db.delete(db.query(VehicleUpdateInboxAction).first())
    with pytest.raises(RuntimeError, match="immutable"):
        db.commit()
    db.rollback()


@pytest.mark.parametrize("payload", [{}, {"read": None}, {"read": "false"}, {"read": 0},
    {"folder": "all"}, {"folder": "permanent_delete"}, {"recipient_id": 2, "read": True}])
def test_mutation_validation_rejects_ambiguous_or_spoofed_state(payload):
    with pytest.raises(ValidationError):
        ReceiptUpdate(**payload)


def test_http_contract_validation_and_legacy_read_response(ctx):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.modules.vehicle_hub.routers_v1.vehicle_updates import router, get_current_user, get_db
    db, owner, *_ = ctx
    row = publish(ctx); db.commit()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: owner
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as client:
        endpoint = f"/vehicle-updates/{row.id}"
        assert client.put(endpoint + "/receipt", json={"read": "false"}).status_code == 422
        assert client.get("/vehicle-updates", params={"folder": "other"}).status_code == 422
        response = client.put(endpoint + "/receipt", json={"read": True, "folder": "archive"})
        assert response.status_code == 200 and response.json()["unread_count"] == 0
        feed = client.get("/vehicle-updates", params={"folder": "archive", "limit": 1}).json()
        assert feed["folder_counts"] == {"inbox": 0, "archive": 1, "trash": 0}
        assert feed["items"][0]["read"] and feed["items"][0]["folder"] == "archive"
        assert client.post(endpoint + "/read").json() == {"read": True}
        assert client.get("/vehicle-updates").json()["items"] == []
        assert client.put("/vehicle-updates/999999/receipt", json={"read": False}).status_code == 404


def test_additive_migration_retains_old_read_receipt_and_has_no_backfill_side_effect(ctx):
    from scripts.migrate_vehicle_update_inbox import migrate, check
    db, owner, *_ = ctx
    row = publish(ctx); db.commit()
    legacy_time = datetime(2026, 10, 1, 12, 30)
    db.add(VehicleUpdateReceipt(update_id=row.id, recipient_id=owner.id, read_at=legacy_time))
    db.commit()
    bind = db.get_bind()
    VehicleUpdateInboxAction.__table__.drop(bind)
    VehicleUpdateInboxState.__table__.drop(bind)
    report = check(bind)
    assert not report["available"] and len(report["missing_tables"]) == 2
    assert "vehicle_update_inbox_states" not in inspect(bind).get_table_names()
    migrate(bind); migrate(bind)
    assert check(bind)["available"]
    assert {"vehicle_update_inbox_states", "vehicle_update_inbox_actions"}.issubset(inspect(bind).get_table_names())
    db.expire_all()
    item = feed(db, owner)["items"][0]
    assert item["folder"] == "inbox" and item["read_at"] == "2026-10-01T12:30:00.000Z"
    assert db.query(VehicleUpdateInboxAction).count() == 0
    assert db.query(VehicleUpdateInboxState).count() == 0
    assert db.query(VehicleUpdate).count() == 1


def test_reviewed_vehicle_deletion_includes_mailbox_state_and_preserves_audit_snapshot(ctx):
    import json
    from sqlalchemy import text
    from src.modules.vehicle_hub.models import Vehicle, Customer, DeveloperActionAuditLog
    from src.modules.vehicle_hub.vehicle_deletion import deletion_preview, delete_reviewed_vehicle
    db, owner, service, admin, vehicle, *_ = ctx
    row = publish(ctx); db.commit()
    change(db, owner, row, read=True, folder="trash")
    vehicle_id, owner_id, service_id = vehicle.id, owner.id, service.id
    db.commit()
    db.execute(text("PRAGMA foreign_keys=ON"))
    assert db.execute(text("PRAGMA foreign_keys")).scalar() == 1
    preview = deletion_preview(db, vehicle_id)
    keys = {item["key"] for item in preview["items"]}
    assert {"vehicle_update_inbox_states", "vehicle_update_inbox_actions"}.issubset(keys)
    # Existing explicit removal includes its own reviewed archive. Merely
    # moving the message to trash above left the vehicle and event intact.
    delete_reviewed_vehicle(db, vehicle_id, preview_token=preview["preview_token"],
        delete_related=True, actor=admin, reason="Synthetic reviewed vehicle removal")
    db.commit(); db.expire_all()
    assert db.get(Vehicle, vehicle_id) is None
    assert db.get(Customer, owner_id) and db.get(Customer, service_id)
    assert db.query(VehicleUpdateInboxState).count() == 0
    assert db.query(VehicleUpdateInboxAction).count() == 0
    archive = json.loads(db.query(DeveloperActionAuditLog).filter_by(action_type="vehicle.delete").one().parameters_json)
    history = archive["deleted_rows"]["vehicle_update_inbox_actions"]
    assert len(history) == 1 and history[0]["to_folder"] == "trash"


@pytest.mark.parametrize("erase_role", ["owner", "service"])
def test_explicit_account_erasure_orders_mailbox_dependencies_and_preserves_other_account(ctx, erase_role):
    from sqlalchemy import text
    from src.modules.vehicle_hub.account_erasure import erase_account
    from src.modules.vehicle_hub.models import Customer
    db, owner, service, stranger, *_ = ctx
    row = publish(ctx); db.commit()
    change(db, owner, row, read=True, folder="archive")
    target = owner if erase_role == "owner" else service
    target_id, keep_id = target.id, stranger.id
    db.commit()
    db.execute(text("PRAGMA foreign_keys=ON"))
    assert db.execute(text("PRAGMA foreign_keys")).scalar() == 1
    erase_account(db, target)
    db.commit(); db.expire_all()
    assert db.get(Customer, target_id) is None and db.get(Customer, keep_id)
    assert db.query(VehicleUpdate).count() == 0
    assert db.query(VehicleUpdateReceipt).count() == 0
    assert db.query(VehicleUpdateInboxState).count() == 0
    assert db.query(VehicleUpdateInboxAction).count() == 0
