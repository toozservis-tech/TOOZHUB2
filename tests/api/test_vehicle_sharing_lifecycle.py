"""Synthetic consent lifecycle: no live API, email or customer data."""
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import (
    Customer, Tenant, Vehicle, VehicleOwnership, VehicleServiceLink,
    ServiceAccessRequest, ServiceVehicleAccess, ServiceCustomerLink, ServiceRecord,
)
from src.modules.vehicle_hub.ownership import (
    ensure_vehicle_owner_assignment, release_vehicle_owner_assignment, transfer_vehicle_to_new_owner,
)
from src.modules.vehicle_hub.service_access import (
    create_or_update_vehicle_service_link, service_can_read_vehicle,
    backfill_vehicle_service_links_from_legacy_access,
)
from src.modules.vehicle_hub.routers_v1 import services, vehicles, service_workspace


@pytest.fixture
def sharing(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'consent.sqlite'}")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False)()
    actors = {}
    for name, role in [('owner','user'), ('buyer','user'), ('service','service'), ('other_service','service'), ('admin','admin')]:
        tenant = Tenant(name=name, license_key=f'fixture-{name}')
        db.add(tenant); db.flush()
        actor = Customer(tenant_id=tenant.id, email=f'{name}@example.invalid', role=role)
        db.add(actor); db.flush(); actors[name] = actor
    # Consent/privacy tests require a paid customer; billing is tested separately.
    from src.modules.licensing.service import upgrade_license_plan
    for name in ['owner', 'buyer']:
        upgrade_license_plan(db, actors[name].tenant_id, 'premium')
    owner = actors['owner']
    car = Vehicle(tenant_id=owner.tenant_id, user_email=owner.email, nickname='Fixture car', stk_valid_until=date(2030,1,1))
    db.add(car); db.flush(); ensure_vehicle_owner_assignment(db, vehicle=car, owner=owner)
    link = create_or_update_vehicle_service_link(db, tenant_id=owner.tenant_id,
        service_customer_id=actors['service'].id, owner_customer_id=owner.id, vehicle_id=car.id,
        approved_by_customer_id=owner.id, source_type='direct_user_grant')
    db.add(ServiceCustomerLink(service_customer_id=actors['service'].id, customer_id=owner.id,
        service_tenant_id=actors['service'].tenant_id, customer_tenant_id=owner.tenant_id))
    request = ServiceAccessRequest(tenant_id=owner.tenant_id, owner_customer_id=owner.id,
        vehicle_id=car.id, service_customer_id=actors['other_service'].id, status='pending')
    db.add(request)
    record = ServiceRecord(tenant_id=owner.tenant_id, vehicle_id=car.id,
        description='Historical repair must survive', created_by_service_customer_id=actors['service'].id, service_access_link_id=link.id)
    db.add(record); db.commit()
    monkeypatch.setattr(services, '_ensure_services_schema', lambda db: None)
    monkeypatch.setattr(service_workspace, '_ensure_service_workspace_schema', lambda db: None)
    monkeypatch.setattr(vehicles, '_ensure_vehicle_photo_column', lambda db: None)
    yield SimpleNamespace(db=db, car=car, link=link, request=request, record=record, **actors)
    db.close(); engine.dispose()


def test_disconnect_closes_current_and_legacy_access(sharing):
    s = sharing
    result = services.disconnect_my_service_contact(s.service.id, current_user=s.owner, db=s.db)
    assert result['disconnected'] and result['revoked_vehicles_count'] == 1
    assert not service_can_read_vehicle(s.db, s.service, s.car.id)
    s.db.refresh(s.link); assert s.link.status == 'revoked'
    assert s.db.query(ServiceRecord).count() == 1


def test_replace_revokes_previous_service_in_both_models(sharing):
    s = sharing
    result = services.grant_vehicle_access_to_service(services.VehicleAccessGrantRequest(
        vehicle_id=s.car.id, service_id=s.other_service.id, conflict_strategy='replace'), current_user=s.owner, db=s.db)
    assert result['revoked_conflict_service_ids'] == [s.service.id]
    assert not service_can_read_vehicle(s.db, s.service, s.car.id)
    assert service_can_read_vehicle(s.db, s.other_service, s.car.id)


@pytest.mark.parametrize('operation', ['release', 'transfer', 'assignment'])
def test_ownership_change_closes_grants_pending_requests_and_preserves_evidence(sharing, operation):
    s = sharing
    if operation == 'release':
        assert release_vehicle_owner_assignment(s.db, vehicle=s.car, owner=s.owner)
    elif operation == 'transfer':
        transfer_vehicle_to_new_owner(s.db, vehicle=s.car, new_owner=s.buyer)
    else:
        ensure_vehicle_owner_assignment(s.db, vehicle=s.car, owner=s.buyer)
    s.db.commit()
    assert not service_can_read_vehicle(s.db, s.service, s.car.id)
    s.db.refresh(s.link); s.db.refresh(s.request)
    assert s.link.status == 'revoked' and s.link.owner_customer_id == s.owner.id
    assert s.link.revoked_at and s.link.revoked_reason
    assert s.request.status == 'revoked'
    assert s.db.query(ServiceVehicleAccess).filter_by(status='active').count() == 0
    assert s.db.query(ServiceRecord).one().description == 'Historical repair must survive'


def test_old_owner_cannot_reapprove_after_transfer(sharing):
    s = sharing
    transfer_vehicle_to_new_owner(s.db, vehicle=s.car, new_owner=s.buyer); s.db.commit()
    with pytest.raises(HTTPException) as denied:
        create_or_update_vehicle_service_link(s.db, tenant_id=s.owner.tenant_id,
            service_customer_id=s.service.id, owner_customer_id=s.owner.id, vehicle_id=s.car.id,
            approved_by_customer_id=s.owner.id, source_type='direct_user_grant')
    assert denied.value.status_code in [403, 409]


def test_legacy_backfill_never_revives_explicit_revocation(sharing):
    s = sharing; s.link.status = 'revoked'; s.db.commit()
    backfill_vehicle_service_links_from_legacy_access(s.db); s.db.commit()
    s.db.refresh(s.link)
    assert s.link.status == 'revoked'
    assert not service_can_read_vehicle(s.db, s.service, s.car.id)


def test_unrelated_release_does_not_revoke_owners_service(sharing):
    s = sharing
    assert not release_vehicle_owner_assignment(s.db, vehicle=s.car, owner=s.buyer)
    assert service_can_read_vehicle(s.db, s.service, s.car.id)


def test_administrator_can_release_actual_owner_without_deleting_history(sharing):
    s = sharing
    result = vehicles.delete_vehicle(s.car.id, current_user=s.admin, db=s.db)
    assert 'message' in result
    assert s.db.query(VehicleOwnership).filter_by(vehicle_id=s.car.id, is_active=True).count() == 0
    assert not service_can_read_vehicle(s.db, s.service, s.car.id)
    assert s.db.get(ServiceRecord, s.record.id)


def test_same_owner_update_keeps_existing_consent(sharing):
    s = sharing
    ensure_vehicle_owner_assignment(s.db, vehicle=s.car, owner=s.owner); s.db.commit()
    assert service_can_read_vehicle(s.db,s.service,s.car.id)


def test_stale_grant_never_exposes_transferred_vehicle_in_service_lists(sharing):
    s = sharing
    transfer_vehicle_to_new_owner(s.db,vehicle=s.car,new_owner=s.buyer); s.db.commit()
    # Simulate an old inconsistent row restored from a historical database.
    s.link.status='approved'; s.db.commit()
    assert not service_can_read_vehicle(s.db,s.service,s.car.id)
    assert service_workspace.list_approved_service_vehicles(current_user=s.service,db=s.db)['items']==[]
    assert service_workspace._get_shared_vehicle_ids_for_pair(s.db,service_customer_id=s.service.id,customer_id=s.owner.id)==set()


def test_disconnect_cancels_pending_request_without_existing_contact(sharing):
    s=sharing
    result=services.disconnect_my_service_contact(s.other_service.id,current_user=s.owner,db=s.db)
    assert result['disconnected']
    s.db.refresh(s.request); assert s.request.status=='revoked'


def test_disconnect_legacy_only_permission_cannot_be_revived_by_migration(sharing):
    s=sharing
    # No historic record may point at the removed synthetic legacy grant.
    s.record.service_access_link_id=None; s.db.flush(); s.db.delete(s.link); s.db.commit()
    services.disconnect_my_service_contact(s.service.id,current_user=s.owner,db=s.db)
    backfill_vehicle_service_links_from_legacy_access(s.db); s.db.commit()
    assert s.db.query(ServiceVehicleAccess).filter_by(status='active').count()==0
    assert s.db.query(VehicleServiceLink).count()==0


def test_admin_reassignment_uses_same_consent_lifecycle(sharing):
    from src.server.admin_api import _reassign_vehicle_primary_owner
    s=sharing
    _reassign_vehicle_primary_owner(s.db,vehicle=s.car,owner=s.buyer,assigned_by_customer_id=s.admin.id)
    s.db.commit(); s.db.refresh(s.link)
    assert s.link.status=='revoked' and s.link.revoked_by_customer_id==s.admin.id
    assert s.car.tenant_id==s.buyer.tenant_id
    assert s.db.query(ServiceRecord).count()==1


def test_preregistered_vehicle_is_available_only_to_creating_service(sharing):
    s=sharing
    car=Vehicle(tenant_id=s.service.tenant_id,user_email='not-yet-registered@example.invalid',nickname='Preregistered',stk_valid_until=date(2030,1,1))
    s.db.add(car); s.db.flush()
    create_or_update_vehicle_service_link(s.db,tenant_id=s.service.tenant_id,service_customer_id=s.service.id,
        owner_customer_id=s.service.id,vehicle_id=car.id,approved_by_customer_id=s.service.id,source_type='pending_owner_registration')
    s.db.commit()
    assert service_can_read_vehicle(s.db,s.service,car.id)
    assert not service_can_read_vehicle(s.db,s.other_service,car.id)


def test_legacy_owner_backfill_cannot_be_stolen_by_vin_claim(sharing):
    s=sharing
    car=Vehicle(tenant_id=s.owner.tenant_id,user_email=s.owner.email,nickname='Legacy protected',
        vin='TMBJF73T2B9044629',stk_valid_until=date(2030,1,1))
    s.db.add(car);s.db.commit()
    response=vehicles.create_vehicle(vehicles.VehicleCreateV1(nickname='Not authorized',vin=car.vin,
        stk_valid_until=date(2030,1,1)),current_user=s.buyer,db=s.db)
    assert response.status_code==409
    s.db.refresh(car);assert car.user_email==s.owner.email and car.nickname=='Legacy protected'
