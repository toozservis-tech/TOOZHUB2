"""Owner lifecycle contracts on isolated SQLite only; no network or real accounts."""
from datetime import datetime, timedelta
from uuid import uuid4
import json
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from src.modules.vehicle_hub.database import get_db
from src.modules.vehicle_hub.models import Vehicle, VehicleOwnershipArchive, VehicleOwnership, Reminder, Reservation, ServiceRecord
from src.modules.vehicle_hub.vehicle_lifecycle_models import VehicleLifecycleEvent
from src.modules.vehicle_hub.routers_v1 import vehicle_lifecycle as routes, vehicle_archives, vehicles
from src.modules.vehicle_hub.routers_v1.auth import get_current_user
from src.modules.vehicle_hub.routers_v1.service_jobs import create_job, JobCreate
from src.modules.vehicle_hub import vehicle_lifecycle as domain
from src.modules.vehicle_hub.ownership import may_restore_vehicle_profile, transfer_vehicle_to_new_owner
from src.modules.vehicle_hub.account_erasure import erase_account
from test_service_jobs import ctx


def payload(ctx, action, version=0, **kwargs):
    return routes.VehicleLifecycleAction(client_id=uuid4(), ownership_id=ctx[5].id,
        ownership_token=domain.ownership_token(ctx[4].id, ctx[5]), expected_version=version, action=action, **kwargs)


def apply(ctx, value):
    return routes.update_lifecycle(ctx[4].id, value, ctx[1], ctx[0])


def test_deposit_reactivate_preserves_ownership_grants_history_and_reminders(ctx):
    db, owner, service, _, vehicle, assignment, link = ctx
    reminder = Reminder(tenant_id=owner.tenant_id, customer_id=owner.id, vehicle_id=vehicle.id,
        type='SERVIS', text='Nezahodit', is_manual=True, is_completed=False)
    record = ServiceRecord(tenant_id=owner.tenant_id, vehicle_id=vehicle.id, user_id=owner.id,
        description='History', created_by_ai=False)
    db.add_all([reminder, record]); db.commit()
    initial = routes.get_lifecycle(vehicle.id, owner, db)
    assert initial['version'] == 0 and initial['state'] == 'active'
    deposited = apply(ctx, payload(ctx, 'deposited', note='Dočasně nepoužívám'))
    assert deposited['state'] == 'deposited' and deposited['archive_id'] is None
    assert assignment.is_active and link.status == 'approved' and not reminder.is_completed
    assert db.query(VehicleOwnershipArchive).count() == 0 and db.query(ServiceRecord).count() == 1
    state = routes.get_lifecycle(vehicle.id, owner, db)
    assert state['version'] == 1 and 'reactivated' in state['actions'] and 'deposited' not in state['actions']
    assert apply(ctx, payload(ctx, 'reactivated', 1))['state'] == 'active'
    assert assignment.is_active and link.status == 'approved' and reminder.text == 'Nezahodit'


@pytest.mark.parametrize('action', ['sold', 'removed', 'scrapped'])
def test_end_archives_immediately_preserves_identity_and_retries_after_release(ctx, action):
    db, owner, service, stranger, vehicle, assignment, link = ctx
    vehicle.notes = 'PRIVATE owner data'; vehicle.nickname = 'Private nickname'
    db.add(ServiceRecord(tenant_id=owner.tenant_id, vehicle_id=vehicle.id, user_id=owner.id,
        description='Private history')); db.commit()
    request = payload(ctx, action, note='Vlastní oznámení')
    result = apply(ctx, request)
    assert result['state'] == 'archived' and result['archive_id'] and result['version'] == 1
    assert apply(ctx, request) == result
    assert db.query(VehicleLifecycleEvent).count() == 1
    assert db.query(Vehicle).count() == 1 and db.query(ServiceRecord).count() == 1
    assert vehicle.notes is None and assignment.owned_until and not assignment.is_active
    assert link.status == 'revoked'
    archive = db.get(VehicleOwnershipArchive, result['archive_id'])
    data = json.loads(archive.profile_json)
    assert data['notes'] == 'PRIVATE owner data' and data['lifecycle']['action'] == action
    assert data['lifecycle']['owner_reported'] and not data['lifecycle']['official_registry_change']
    assert vehicle_archives.archive_out(archive)['lifecycle']['action'] == action
    assert may_restore_vehicle_profile(db, vehicle=vehicle, customer=owner) == (action == 'removed')
    with pytest.raises(HTTPException):
        routes.get_lifecycle(vehicle.id, owner, db)
    with pytest.raises(HTTPException):
        vehicle_archives.archive_detail(archive.id, service, db)
    stranger.role = 'user'; db.commit()
    with pytest.raises(HTTPException):
        vehicle_archives.archive_detail(archive.id, stranger, db)
    assert vehicle_archives.archive_detail(archive.id, owner, db)['profile']['notes'] == 'PRIVATE owner data'


@pytest.mark.parametrize('action', ['sold', 'removed', 'scrapped', 'deposited', 'reactivated'])
def test_nonowners_including_admin_or_service_cannot_change_lifecycle(ctx, action):
    db, _, service, admin, vehicle, _, _ = ctx
    request = payload(ctx, action)
    for actor in (service, admin):
        with pytest.raises(HTTPException) as error:
            routes.update_lifecycle(vehicle.id, request, actor, db)
        assert error.value.status_code == 403
        with pytest.raises(HTTPException):
            routes.get_lifecycle(vehicle.id, actor, db)
    assert db.query(VehicleLifecycleEvent).count() == 0


def test_conflicting_uuid_stale_version_invalid_transition_and_future_date(ctx):
    db = ctx[0]
    invalid = payload(ctx, 'reactivated')
    with pytest.raises(HTTPException) as error: apply(ctx, invalid)
    assert error.value.status_code == 409
    request = payload(ctx, 'deposited')
    apply(ctx, request)
    for conflicting in [request.model_copy(update={'note': 'Changed payload'}), payload(ctx, 'reactivated', 0), payload(ctx, 'deposited', 1)]:
        with pytest.raises(HTTPException) as error: apply(ctx, conflicting)
        assert error.value.status_code == 409
    with pytest.raises(HTTPException) as error:
        apply(ctx, payload(ctx, 'reactivated', 1, effective_date=(datetime.utcnow()+timedelta(days=3)).date()))
    assert error.value.status_code == 422
    assert db.query(VehicleLifecycleEvent).count() == 1


def test_open_job_blocks_end_without_changing_any_ownership_data(ctx):
    db, owner, service, _, vehicle, assignment, link = ctx
    create_job(vehicle.id, JobCreate(client_id=uuid4(), title='Rozpracovaná oprava'), service, db)
    with pytest.raises(HTTPException) as error: apply(ctx, payload(ctx, 'sold'))
    assert error.value.status_code == 409 and 'zakázku' in error.value.detail
    assert assignment.is_active and link.status == 'approved'
    assert db.query(VehicleOwnershipArchive).count() == 0
    assert db.query(VehicleLifecycleEvent).count() == 0


@pytest.mark.parametrize('status', ['PENDING', 'CONFIRMED'])
def test_future_reservation_blocks_end_and_is_not_automatically_cancelled(ctx, status):
    db, owner, service, _, vehicle, assignment, link = ctx
    booking = Reservation(tenant_id=owner.tenant_id, vehicle_id=vehicle.id, customer_id=owner.id,
        service_id=service.id, start_datetime=datetime.utcnow()+timedelta(days=3), status=status)
    db.add(booking); db.commit()
    with pytest.raises(HTTPException) as error: apply(ctx, payload(ctx, 'removed'))
    assert error.value.status_code == 409 and 'rezervaci' in error.value.detail
    db.refresh(booking)
    assert booking.status == status and assignment.is_active and link.status == 'approved'
    # Deposit explicitly preserves bookings rather than cancelling them.
    assert apply(ctx, payload(ctx, 'deposited'))['state'] == 'deposited'
    assert booking.status == status


def test_failed_release_rolls_back_archive_private_fields_and_event(ctx, monkeypatch):
    db, owner, _, _, vehicle, assignment, link = ctx
    vehicle.notes = 'Private snapshot'; db.commit()
    def fail(*args, **kwargs): raise RuntimeError('isolated failure after archive')
    monkeypatch.setattr(domain, 'release_vehicle_owner_assignment', fail)
    with pytest.raises(RuntimeError): apply(ctx, payload(ctx, 'removed'))
    db.refresh(vehicle); db.refresh(assignment); db.refresh(link)
    assert vehicle.notes == 'Private snapshot' and assignment.is_active and link.status == 'approved'
    assert db.query(VehicleOwnershipArchive).count() == 0
    assert db.query(VehicleLifecycleEvent).count() == 0


def test_legacy_delete_now_archives_immediately_and_keeps_admin_policy(ctx, monkeypatch):
    db, owner, _, admin, vehicle, assignment, link = ctx
    monkeypatch.setattr(vehicles, '_ensure_vehicle_photo_column', lambda db: None)
    vehicle.notes = 'Original private profile'; db.commit()
    result = vehicles.delete_vehicle(vehicle.id, admin, db)
    assert result['message'] and not assignment.is_active and link.status == 'revoked'
    archive = db.query(VehicleOwnershipArchive).one()
    assert json.loads(archive.profile_json)['notes'] == 'Original private profile'
    assert json.loads(archive.profile_json)['lifecycle']['action'] == 'removed'
    assert not json.loads(archive.profile_json)['lifecycle']['owner_reported']
    assert db.query(VehicleLifecycleEvent).one().actor_id == admin.id
    assert may_restore_vehicle_profile(db, vehicle=vehicle, customer=owner)


def test_new_owner_period_starts_at_zero_without_exposing_previous_private_events(ctx):
    db, owner, _, buyer, vehicle, assignment, _ = ctx
    apply(ctx, payload(ctx, 'removed', note='Private former period'))
    transfer_vehicle_to_new_owner(db, vehicle=vehicle, new_owner=buyer); db.commit()
    state = routes.get_lifecycle(vehicle.id, buyer, db)
    assert state['state'] == 'active' and state['version'] == 0
    assert 'Private former period' not in json.dumps(state)
    assert vehicle_archives.list_archives(buyer, db) == []
    with pytest.raises(HTTPException): routes.get_lifecycle(vehicle.id, owner, db)


def test_erasure_handles_lifecycle_event_foreign_keys(ctx):
    db, owner, _, _, vehicle, assignment, _ = ctx
    db.connection().exec_driver_sql('PRAGMA foreign_keys=ON')
    apply(ctx, payload(ctx, 'removed'))
    identity = owner.id
    erase_account(db, owner); db.commit()
    assert db.query(VehicleLifecycleEvent).count() == 0
    assert db.query(VehicleOwnershipArchive).count() == 0


def test_additive_migration_is_repeatable_and_preserves_vehicle(ctx):
    from scripts.migrate_vehicle_lifecycle import migrate
    db, _, _, _, vehicle, _, _ = ctx
    identity = vehicle.id
    db.commit()
    VehicleLifecycleEvent.__table__.drop(db.get_bind())
    migrate(db.get_bind()); migrate(db.get_bind())
    assert db.get(Vehicle, identity) and db.query(VehicleLifecycleEvent).count() == 0


def test_http_contract_field_limits_and_fail_closed_without_migration(ctx):
    db, owner, _, _, vehicle, assignment, _ = ctx
    app = FastAPI(); app.include_router(routes.router, prefix='/api/v1')
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: owner
    with TestClient(app) as client:
        path = f'/api/v1/vehicles/{vehicle.id}/lifecycle'
        assert client.get(path).json()['state'] == 'active'
        raw = {'client_id': str(uuid4()), 'ownership_id': assignment.id,
            'ownership_token': domain.ownership_token(vehicle.id, assignment), 'expected_version': 0,
            'action': 'deposited', 'note': 'x'*1001}
        assert client.post(path, json=raw).status_code == 422
        raw['note'] = 'Dočasný depozit'
        response = client.post(path, json=raw)
        assert response.status_code == 200 and response.json()['version'] == 1
    # A fresh engine is used so an earlier successful schema cache cannot apply.
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    engine = create_engine('sqlite://')
    with sessionmaker(bind=engine)() as empty:
        with pytest.raises(HTTPException) as error: routes.get_lifecycle(vehicle.id, owner, empty)
        assert error.value.status_code == 503
    engine.dispose()


@pytest.mark.parametrize('path', ['removed_restore', 'admin_transfer_return'])
def test_unexecuted_old_request_cannot_act_on_reused_same_owner_assignment(ctx, path):
    db, owner, _, buyer, vehicle, assignment, _ = ctx
    old_request = payload(ctx, 'deposited')
    identity = assignment.id
    if path == 'removed_restore':
        apply(ctx, payload(ctx, 'removed'))
    else:
        transfer_vehicle_to_new_owner(db, vehicle=vehicle, new_owner=buyer)
        db.commit()
    transfer_vehicle_to_new_owner(db, vehicle=vehicle, new_owner=owner)
    db.commit()
    new_state = routes.get_lifecycle(vehicle.id, owner, db)
    assert new_state['ownership_id'] == identity and new_state['version'] == 0
    assert new_state['ownership_token'] != old_request.ownership_token
    with pytest.raises(HTTPException) as error:
        apply(ctx, old_request)
    assert error.value.status_code == 409 and 'období' in error.value.detail
    assert routes.get_lifecycle(vehicle.id, owner, db)['state'] == 'active'
    assert apply(ctx, payload(ctx, 'deposited'))['state'] == 'deposited'



def test_missing_and_ended_ownership_return_403_without_existence_disclosure(ctx):
    db, owner, _, _, vehicle, _, _ = ctx
    for action in [lambda: routes.get_lifecycle(vehicle.id+10000, owner, db),
                   lambda: routes.update_lifecycle(vehicle.id+10000, payload(ctx, 'removed'), owner, db)]:
        with pytest.raises(HTTPException) as error: action()
        assert error.value.status_code == 403
    request = payload(ctx, 'removed')
    result = apply(ctx, request)
    with pytest.raises(HTTPException) as error: routes.get_lifecycle(vehicle.id, owner, db)
    assert error.value.status_code == 403
    assert apply(ctx, request) == result


def test_receipt_is_bound_to_original_actor_and_immutable_audit_cannot_be_edited(ctx):
    db, owner, service, admin, vehicle, _, _ = ctx
    request = payload(ctx, 'removed', note='Original decision')
    original = apply(ctx, request)
    for actor in (service, admin):
        with pytest.raises(HTTPException) as error:
            routes.update_lifecycle(vehicle.id, request, actor, db)
        assert error.value.status_code == 403
    event = db.query(VehicleLifecycleEvent).one()
    event.note = 'Tampered decision'
    with pytest.raises(RuntimeError): db.commit()
    db.rollback()
    assert db.query(VehicleLifecycleEvent).one().note == 'Original decision'
    assert apply(ctx, request) == original
