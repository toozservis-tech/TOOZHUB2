"""
PRIV-MED-006: vehicle detail responses should minimize owner-linked data exposure.
"""
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import Vehicle as VehicleModel, Customer, Tenant, VehicleServiceLink
from src.modules.vehicle_hub.ownership import ensure_vehicle_owner_assignment
from src.modules.vehicle_hub.routers_v1 import vehicles as vehicles_router


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "vehicle_priv_med_006.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    @event.listens_for(engine, 'connect')
    def enable_foreign_keys(connection, _): connection.execute('PRAGMA foreign_keys=ON')
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _seed_vehicle(db_session) -> tuple[VehicleModel, Customer, Customer]:
    tenant = Tenant(name='Privacy fixture', license_key='privacy-owner-fixture')
    service_tenant = Tenant(name='Service fixture', license_key='privacy-service-fixture')
    db_session.add_all([tenant, service_tenant]); db_session.flush()
    owner = Customer(tenant_id=tenant.id, email='owner.privacy@example.invalid', role='user')
    service = Customer(tenant_id=service_tenant.id, email='service@example.invalid', role='service')
    db_session.add_all([owner, service]); db_session.flush()
    vehicle = VehicleModel(
        tenant_id=tenant.id,
        user_email=owner.email,
        nickname="Privacy Vehicle",
        stk_valid_until=date(2030, 1, 1),
    )
    db_session.add(vehicle)
    db_session.flush()
    ensure_vehicle_owner_assignment(db_session, vehicle=vehicle, owner=owner)
    db_session.add(VehicleServiceLink(tenant_id=owner.tenant_id, service_customer_id=service.id,
        owner_customer_id=owner.id, vehicle_id=vehicle.id, status='approved',
        scope_vehicle_history_read=True, scope_create_service_record=True))
    db_session.commit()
    db_session.refresh(vehicle)
    return vehicle, owner, service


def test_vehicle_detail_redacts_owner_data_for_non_owner_service(
    db_session,
) -> None:
    vehicle, _, service_user = _seed_vehicle(db_session)

    payload = vehicles_router.get_vehicle(vehicle.id, current_user=service_user, db=db_session)

    assert payload["id"] == vehicle.id
    assert payload["user_email"] == "hidden"
    assert payload["tenant_id"] is None
    assert payload['permissions']['can_create_service_record'] is True
    assert payload['permissions']['can_manage_photo'] is False


def test_vehicle_detail_keeps_owner_data_for_owner(
    db_session,
) -> None:
    vehicle, owner_user, _ = _seed_vehicle(db_session)

    payload = vehicles_router.get_vehicle(vehicle.id, current_user=owner_user, db=db_session)

    assert payload["user_email"] == vehicle.user_email
    assert payload["tenant_id"] == vehicle.tenant_id
    assert payload['permissions']['can_manage_photo'] is True
