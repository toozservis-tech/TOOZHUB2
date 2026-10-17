"""Transactional owner inbox regressions using a private SQLite fixture."""
from datetime import datetime, timedelta
from uuid import uuid4
import pytest
from fastapi import HTTPException
from test_service_jobs import ctx
from src.modules.vehicle_hub.models import (ServiceRecord, ServiceAccessRequest, RepairPhotoSession,
    RepairEvidencePhoto, Reminder, VehicleOwnership)
from src.modules.vehicle_hub.vehicle_update_models import VehicleUpdate, VehicleUpdateReceipt
from src.modules.vehicle_hub.vehicle_updates import publish_vehicle_update
from src.modules.vehicle_hub.routers_v1.vehicle_updates import list_updates, mark_read


def feed(db, owner, limit=30, before_id=None):
    return list_updates(before_id=before_id, limit=limit, current_user=owner, db=db)


def publish(ctx, key=None):
    db, owner, service, stranger, vehicle, assignment, link = ctx
    return publish_vehicle_update(db, vehicle_id=vehicle.id, actor_id=service.id,
        event_type='job.updated', title='Průběh opravy', message='Kontrola brzd',
        source_type='service_job', source_id=1, dedupe_key=key or str(uuid4()))


def test_transaction_rollback_cannot_leak_alert_and_retry_deduplicates(ctx):
    db, owner, *_ = ctx
    publish(ctx, 'retry-1'); db.flush()
    assert feed(db, owner)['unread_count'] == 1
    db.rollback()
    assert feed(db, owner)['items'] == []
    publish(ctx, 'retry-1'); db.commit()
    publish(ctx, 'retry-1'); db.commit()
    assert len(feed(db, owner)['items']) == 1


def test_record_access_request_photo_and_vehicle_updates_reach_owner(ctx):
    db, owner, service, stranger, vehicle, assignment, link = ctx
    db.add(ServiceRecord(tenant_id=vehicle.tenant_id, vehicle_id=vehicle.id,
        user_id=service.id, created_by_service_customer_id=service.id, description='Nové brzdy'))
    db.add(ServiceAccessRequest(tenant_id=vehicle.tenant_id, vehicle_id=vehicle.id,
        service_customer_id=service.id, owner_customer_id=owner.id, request_message='Kontrola'))
    repair = RepairPhotoSession(vehicle_id=vehicle.id, service_id=service.id,
        title='Průběh opravy', client_id=str(uuid4()))
    db.add(repair); db.flush()
    db.add(RepairEvidencePhoto(session_id=repair.id, author_id=service.id,
        author_name='Test servis', phase='during', note='', source='camera',
        sha256='0'*64, file_path='synthetic.png', mime_type='image/png', size_bytes=1, client_id=str(uuid4())))
    db.info['vehicle_update_actor_id'] = service.id
    vehicle.notes = 'Oprava probíhá'
    db.commit()
    events = {row['event_type'] for row in feed(db, owner)['items']}
    assert events == {'record.created', 'access_request.created', 'repair.created', 'repair.photo_added', 'vehicle.updated'}
    assert feed(db, stranger)['items'] == []
    assert feed(db, service)['items'] == []


def test_read_is_account_scoped_idempotent_and_never_changes_event(ctx):
    db, owner, service, stranger, *_ = ctx
    row = publish(ctx); db.commit()
    with pytest.raises(HTTPException) as error:
        mark_read(row.id, stranger, db)
    assert error.value.status_code == 404
    assert db.query(VehicleUpdateReceipt).count() == 0
    assert mark_read(row.id, owner, db) == {'read': True}
    assert mark_read(row.id, owner, db) == {'read': True}
    assert db.query(VehicleUpdateReceipt).count() == 1
    assert feed(db, owner)['unread_count'] == 0
    assert feed(db, owner)['items'][0]['read_at'].endswith('Z')
    assert db.query(VehicleUpdate).one().message == 'Kontrola brzd'


def test_transfer_and_return_cannot_resurface_old_ownership_feed(ctx):
    db, owner, service, stranger, vehicle, assignment, link = ctx
    publish(ctx); db.commit()
    assignment.is_active = False; db.commit()
    assert feed(db, owner)['items'] == []
    assert feed(db, stranger)['items'] == []
    # Ownership rows are reused for returning owners by the production schema.
    assignment.is_active = True
    assignment.owned_from = datetime.utcnow() + timedelta(days=1)
    db.commit()
    assert feed(db, owner)['items'] == []
    publish(ctx); db.commit()
    assert feed(db, owner)['unread_count'] == 1


def test_pagination_and_total_unread_do_not_drop_older_updates(ctx):
    db, owner, *_ = ctx
    for i in range(5):
        publish(ctx, f'page-{i}')
    db.commit()
    first = feed(db, owner, limit=2)
    second = feed(db, owner, limit=2, before_id=first['next_before_id'])
    third = feed(db, owner, limit=2, before_id=second['next_before_id'])
    assert first['unread_count'] == second['unread_count'] == third['unread_count'] == 5
    assert len({i['id'] for page in [first, second, third] for i in page['items']}) == 5
    assert not third['has_more'] and third['next_before_id'] is None


def test_owner_edits_and_scheduler_changes_do_not_masquerade_as_service(ctx):
    db, owner, service, stranger, vehicle, assignment, link = ctx
    db.info['vehicle_update_actor_id'] = owner.id
    vehicle.notes = 'Vlastní poznámka'
    db.commit()
    assert feed(db, owner)['items'] == []
    reminder = Reminder(tenant_id=vehicle.tenant_id, vehicle_id=vehicle.id,
        customer_id=owner.id, created_by_service_customer_id=service.id, type='SERVIS', text='Kontrola')
    db.add(reminder); db.commit()
    db.info.pop('vehicle_update_actor_id', None)
    reminder.last_notified_at = datetime.utcnow(); db.commit()
    assert feed(db, owner)['items'] == []


def test_service_reminder_delete_is_a_visible_update(ctx):
    db, owner, service, stranger, vehicle, assignment, link = ctx
    reminder = Reminder(tenant_id=vehicle.tenant_id, vehicle_id=vehicle.id,
        customer_id=owner.id, created_by_service_customer_id=service.id, type='SERVIS', text='Kontrola')
    db.add(reminder); db.commit()
    db.info['vehicle_update_actor_id'] = service.id
    db.delete(reminder); db.commit()
    assert {r['event_type'] for r in feed(db, owner)['items']} == {'reminder.updated','reminder.deleted'}


def test_events_are_immutable(ctx):
    db, *_ = ctx
    row = publish(ctx); db.commit()
    row.message = 'Přepsat audit'
    with pytest.raises(RuntimeError, match='immutable'):
        db.commit()
    db.rollback()
    row = db.get(VehicleUpdate, row.id)
    db.delete(row)
    with pytest.raises(RuntimeError, match='immutable'):
        db.commit()
    db.rollback()


def test_a_later_return_to_previous_vehicle_value_is_still_a_new_update(ctx):
    db, owner, service, stranger, vehicle, assignment, link = ctx
    db.info['vehicle_update_actor_id'] = service.id
    for note in ['Kontrola', 'Oprava', 'Kontrola']:
        vehicle.notes = note
        db.commit()
    assert len(feed(db, owner)['items']) == 3
