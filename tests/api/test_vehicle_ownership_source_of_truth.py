from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import Customer, Tenant, Vehicle as VehicleModel, VehicleOwnership
from src.modules.vehicle_hub.ownership import ensure_vehicle_owner_assignment, user_owns_vehicle
from src.modules.vehicle_hub.routers_v1 import vehicles as vehicles_router


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "vehicle_ownership_source_of_truth.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def test_vehicle_listing_uses_ownership_source_of_truth(db_session) -> None:
    tenant = Tenant(name="Ownership Tenant", license_key="ownership-tenant-key")
    owner = Customer(
        tenant_id=1,
        email="owner@example.com",
        password_hash="hash",
        role="user",
    )
    db_session.add(tenant)
    db_session.flush()
    owner.tenant_id = tenant.id
    db_session.add(owner)
    db_session.flush()

    vehicle = VehicleModel(
        tenant_id=tenant.id,
        user_email="legacy-wrong@example.com",
        nickname="Owned Vehicle",
        stk_valid_until=date(2030, 1, 1),
    )
    db_session.add(vehicle)
    db_session.flush()
    ensure_vehicle_owner_assignment(db_session, vehicle=vehicle, owner=owner, assigned_by_customer_id=owner.id)
    db_session.commit()

    assert user_owns_vehicle(db_session, owner, vehicle) is True

    current_user = SimpleNamespace(email=owner.email, tenant_id=tenant.id, id=owner.id)
    vehicles = vehicles_router.get_vehicles(current_user=current_user, db=db_session)
    assert [item.id for item in vehicles] == [vehicle.id]


def test_vehicle_create_creates_primary_ownership_assignment(db_session) -> None:
    tenant = Tenant(name="Create Tenant", license_key="create-tenant-key")
    owner = Customer(
        tenant_id=1,
        email="creator@example.com",
        password_hash="hash",
        role="user",
    )
    db_session.add(tenant)
    db_session.flush()
    owner.tenant_id = tenant.id
    db_session.add(owner)
    db_session.commit()
    db_session.refresh(owner)

    payload = vehicles_router.VehicleCreateV1(
        nickname="Nové auto",
        plate="1AB2345",
        stk_valid_until=date(2030, 1, 1),
    )
    created = vehicles_router.create_vehicle(vehicle_data=payload, current_user=owner, db=db_session)

    ownership = (
        db_session.query(VehicleOwnership)
        .filter(VehicleOwnership.vehicle_id == created.id, VehicleOwnership.customer_id == owner.id)
        .first()
    )
    assert ownership is not None
    assert ownership.is_primary is True
    assert ownership.is_active is True
