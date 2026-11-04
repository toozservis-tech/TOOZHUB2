"""Sale recipient validation uses an isolated database; sends no email."""
from hashlib import sha256
import json
from datetime import date
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from test_vehicle_lifecycle import ctx, payload, apply
from src.modules.vehicle_hub.routers_v1 import vehicle_lifecycle as routes, vehicle_archives
from src.modules.vehicle_hub.models import VehicleOwnershipArchive, VehicleOwnership
from src.modules.vehicle_hub.vehicle_lifecycle_models import VehicleLifecycleEvent
from src.modules.vehicle_hub import vehicle_lifecycle as domain


@pytest.mark.parametrize('sale', [
    {'mode': 'new_owner'},
    {'mode': 'new_owner', 'buyer_email': 'wrong'},
    {'mode': 'new_owner', 'buyer_email': 'buyer@example.com', 'reason': 'dealer'},
    {'mode': 'outside_app'},
    {'mode': 'outside_app', 'reason': 'export', 'buyer_email': 'buyer@example.com'},
    {'mode': 'outside_app', 'reason': 'other', 'reason_detail': ' '},
    {'mode': 'outside_app', 'reason': 'unknown'},
])
def test_invalid_sale_cannot_be_encoded_as_valid_request(ctx, sale):
    with pytest.raises(ValidationError): payload(ctx, 'sold', sale=sale)
    assert ctx[5].is_active
    assert ctx[0].query(VehicleOwnershipArchive).count() == 0


def test_missing_recipient_and_self_sale_fail_before_any_archive(ctx):
    ctx[1].email = 'seller@example.com'; ctx[0].commit()
    for sale in [None, {'mode': 'new_owner', 'buyer_email': ctx[1].email}]:
        with pytest.raises(HTTPException) as error: apply(ctx, payload(ctx, 'sold', sale=sale))
        assert error.value.status_code == 422
        assert ctx[5].is_active
        assert ctx[0].query(VehicleOwnershipArchive).count() == 0


def test_buyer_is_durable_in_seller_archive_but_not_assigned_or_exposed(ctx):
    db, seller, service, buyer, vehicle, assignment, _ = ctx
    buyer.email = 'buyer@example.com'; db.commit()
    request = payload(ctx, 'sold', sale={'mode': 'new_owner', 'buyer_email': buyer.email.upper()})
    receipt = apply(ctx, request)
    assert apply(ctx, request) == receipt
    archive = vehicle_archives.archive_detail(receipt['archive_id'], seller, db)
    assert archive['profile']['lifecycle']['sale'] == {'mode': 'new_owner', 'buyer_email': buyer.email.lower()}
    assert db.query(VehicleOwnership).filter_by(vehicle_id=vehicle.id, customer_id=buyer.id, is_active=True).count() == 0
    assert vehicle_archives.list_archives(buyer, db) == []
    with pytest.raises(HTTPException) as denied:
        vehicle_archives.archive_detail(receipt['archive_id'], buyer, db)
    assert denied.value.status_code == 404
    with pytest.raises(HTTPException): vehicle_archives.archive_detail(receipt['archive_id'], service, db)
    assert db.query(VehicleLifecycleEvent).count() == 1
    changed = request.model_copy(update={'sale': routes.VehicleSaleDetails(mode='new_owner', buyer_email='another@example.com')})
    with pytest.raises(HTTPException) as error: apply(ctx, changed)
    assert error.value.status_code == 409


@pytest.mark.parametrize('reason', ['dealer', 'export', 'other'])
def test_explicit_sale_without_recipient_is_durable_and_idempotent(ctx, reason):
    sale = {'mode': 'outside_app', 'reason': reason}
    if reason == 'other': sale['reason_detail'] = '  Kupující aplikaci nepoužívá  '
    request = payload(ctx, 'sold', sale=sale)
    receipt = apply(ctx, request)
    assert apply(ctx, request) == receipt
    record = vehicle_archives.archive_detail(receipt['archive_id'], ctx[1], ctx[0])['profile']['lifecycle']['sale']
    assert record['reason'] == reason and 'buyer_email' not in record
    if reason == 'other': assert record['reason_detail'] == 'Kupující aplikaci nepoužívá'


def test_sale_details_are_rejected_for_other_actions(ctx):
    with pytest.raises(HTTPException) as error:
        apply(ctx, payload(ctx, 'removed', sale={'mode': 'outside_app', 'reason': 'dealer'}))
    assert error.value.status_code == 422 and ctx[5].is_active


def test_already_committed_legacy_sale_retry_still_returns_same_receipt(ctx):
    db, actor, _, _, vehicle, assignment, _ = ctx
    legacy = payload(ctx, 'sold', sale=None)
    old_data = {'vehicle_id': vehicle.id, **legacy.model_dump()}
    old_data.pop('sale')
    digest = sha256(json.dumps(old_data, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()
    receipt = {'vehicle_id': vehicle.id, 'action': 'sold', 'state': 'archived', 'version': 1, 'archive_id': 9, 'message': 'Legacy receipt'}
    db.add(VehicleLifecycleEvent(vehicle_id=vehicle.id, ownership_id=assignment.id,
        ownership_started_at=domain.period_start(assignment), owner_id=actor.id, actor_id=actor.id,
        client_id=str(legacy.client_id), payload_hash=digest, action='sold', state='archived', version=1,
        effective_date=date.today(), response_json=json.dumps(receipt)))
    db.commit()
    assert apply(ctx, legacy) == receipt
    assert db.query(VehicleLifecycleEvent).count() == 1


def test_http_contract_advertises_support_and_persists_validated_sale(ctx):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from src.modules.vehicle_hub.database import get_db
    from src.modules.vehicle_hub.routers_v1.auth import get_current_user
    app = FastAPI(); app.include_router(routes.router, prefix='/api/v1')
    app.include_router(vehicle_archives.router, prefix='/api/v1')
    app.dependency_overrides[get_db] = lambda: ctx[0]
    app.dependency_overrides[get_current_user] = lambda: ctx[1]
    path = f'/api/v1/vehicles/{ctx[4].id}/lifecycle'
    with TestClient(app) as client:
        assert client.get(path).json()['sale_details_version'] == 2
        body = payload(ctx, 'sold', sale=None).model_dump(mode='json')
        assert client.post(path, json=body).status_code == 422
        body['sale'] = {'mode': 'outside_app', 'reason': 'export'}
        receipt = client.post(path, json=body)
        assert receipt.status_code == 200
        assert client.post(path, json=body).json() == receipt.json()
        archived = client.get(f"/api/v1/vehicle-archives/{receipt.json()['archive_id']}")
        assert archived.status_code == 200
        assert archived.json()['profile']['lifecycle']['sale'] == body['sale']
