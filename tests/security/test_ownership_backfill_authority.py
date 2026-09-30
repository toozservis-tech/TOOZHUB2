"""A stale legacy email must never grant or restore vehicle access."""
import os
import tempfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

sandbox = tempfile.TemporaryDirectory(prefix="ownership-authority-")
os.environ.update(DATABASE_URL="sqlite:///" + sandbox.name + "/unused.sqlite",
                  DATA_DIR_PATH=sandbox.name, ENVIRONMENT="test")
os.environ.pop("DATABASE_SCHEMA", None)

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import Customer, Tenant, Vehicle, VehicleOwnership
from src.modules.vehicle_hub.ownership import (
    backfill_vehicle_owner_assignment, ensure_vehicle_owner_assignment,
    get_owned_vehicle_ids, release_vehicle_owner_assignment, user_owns_vehicle,
)


@pytest.fixture()
def context(tmp_path: Path):
    engine = create_engine("sqlite:///" + str(tmp_path / "authority.sqlite"))
    event.listen(engine, "connect", lambda db, _: db.execute("PRAGMA foreign_keys=ON"))
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, autoflush=False)() as db:
        tenant = Tenant(name="Fixture", license_key="authority-fixture")
        db.add(tenant); db.flush()
        old = Customer(tenant_id=tenant.id, email="old@example.test")
        current = Customer(tenant_id=tenant.id, email="current@example.test")
        db.add_all([old, current]); db.flush()
        vehicle = Vehicle(tenant_id=tenant.id, user_email=old.email, nickname="Transferred fixture")
        db.add(vehicle); db.flush()
        yield db, old, current, vehicle
    engine.dispose()


def test_stale_email_cannot_replace_current_owner(context):
    db, old, current, vehicle = context
    assignment = ensure_vehicle_owner_assignment(db, vehicle=vehicle, owner=current)
    db.commit()
    assert not user_owns_vehicle(db, old, vehicle)
    assert get_owned_vehicle_ids(db, old) == set()
    assert user_owns_vehicle(db, current, vehicle)
    db.refresh(assignment)
    assert assignment.is_active and assignment.customer_id == current.id
    assert db.query(VehicleOwnership).count() == 1


def test_released_assignment_cannot_be_resurrected_by_legacy_email(context):
    db, old, _, vehicle = context
    ensure_vehicle_owner_assignment(db, vehicle=vehicle, owner=old)
    db.commit()
    assert release_vehicle_owner_assignment(db, vehicle=vehicle, owner=old)
    db.commit()
    assert not user_owns_vehicle(db, old, vehicle)
    assert not get_owned_vehicle_ids(db, old)
    assert backfill_vehicle_owner_assignment(db, vehicle) is None
    assert not db.query(VehicleOwnership).one().is_active


def test_legacy_vehicle_without_history_is_migrated_once(context):
    db, old, _, vehicle = context
    assert user_owns_vehicle(db, old, vehicle)
    assert get_owned_vehicle_ids(db, old) == {vehicle.id}
    assert db.query(VehicleOwnership).count() == 1
    assert db.query(VehicleOwnership).one().ownership_origin == "legacy_backfill"


def test_mixed_old_and_new_vehicles_remain_visible(context):
    db, old, _, legacy_vehicle = context
    migrated = Vehicle(tenant_id=old.tenant_id, user_email=old.email, nickname="Already migrated")
    db.add(migrated); db.flush()
    ensure_vehicle_owner_assignment(db, vehicle=migrated, owner=old)
    db.commit()
    assert get_owned_vehicle_ids(db, old) == {legacy_vehicle.id, migrated.id}


@pytest.mark.parametrize("state", ["is_disabled", "is_deleted"])
def test_inactive_legacy_customer_does_not_get_new_assignment(context, state):
    db, old, _, vehicle = context
    setattr(old, state, True); db.commit()
    assert backfill_vehicle_owner_assignment(db, vehicle) is None
    assert db.query(VehicleOwnership).count() == 0


def test_cross_tenant_email_is_not_an_ownership_grant(context):
    db, old, _, vehicle = context
    another = Tenant(name="Other fixture", license_key="other-authority-fixture")
    db.add(another); db.flush()
    vehicle.tenant_id = another.id; db.commit()
    assert backfill_vehicle_owner_assignment(db, vehicle) is None
    assert not user_owns_vehicle(db, old, vehicle)
    assert not get_owned_vehicle_ids(db, old)


def test_existing_delegation_does_not_make_stale_email_primary(context):
    db, old, current, vehicle = context
    db.add(VehicleOwnership(tenant_id=current.tenant_id, vehicle_id=vehicle.id,
                            customer_id=current.id, ownership_type="delegated",
                            is_primary=False, is_active=True))
    db.commit()
    assert not user_owns_vehicle(db, old, vehicle)
    assert not get_owned_vehicle_ids(db, old)
    assert user_owns_vehicle(db, current, vehicle)
    assert not db.query(VehicleOwnership).one().is_primary
