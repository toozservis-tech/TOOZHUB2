"""
SEC-HIGH-005: Vehicle listing must never fall back to tenant-unsafe query paths.
"""
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import Vehicle as VehicleModel
from src.modules.vehicle_hub.routers_v1 import vehicles as vehicles_router


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "vehicles_sec_high_005.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _seed_vehicle(db_session, *, tenant_id: int, user_email: str, nickname: str) -> VehicleModel:
    vehicle = VehicleModel(
        tenant_id=tenant_id,
        user_email=user_email,
        nickname=nickname,
        stk_valid_until=date(2030, 1, 1),
    )
    db_session.add(vehicle)
    db_session.commit()
    db_session.refresh(vehicle)
    return vehicle


def test_get_vehicles_requires_tenant_context(db_session) -> None:
    _seed_vehicle(
        db_session,
        tenant_id=10,
        user_email="sec-high-005@example.com",
        nickname="Unsafe fallback candidate",
    )

    current_user = SimpleNamespace(email="sec-high-005@example.com", tenant_id=None)

    with pytest.raises(HTTPException) as exc_info:
        vehicles_router.get_vehicles(current_user=current_user, db=db_session)

    assert exc_info.value.status_code == 403


def test_get_vehicles_returns_only_same_tenant_records(db_session) -> None:
    own = _seed_vehicle(
        db_session,
        tenant_id=100,
        user_email="sec-high-005@example.com",
        nickname="Tenant 100 vehicle",
    )
    _seed_vehicle(
        db_session,
        tenant_id=200,
        user_email="sec-high-005@example.com",
        nickname="Tenant 200 vehicle",
    )

    current_user = SimpleNamespace(email="sec-high-005@example.com", tenant_id=100)
    vehicles = vehicles_router.get_vehicles(current_user=current_user, db=db_session)

    returned_ids = {item.id for item in vehicles}
    assert returned_ids == {own.id}


def test_listing_validation_failure_is_explicit_and_private(db_session, monkeypatch, capsys, caplog):
    marker = 'PRIVATE_VEHICLE_INFORMATION'
    own = _seed_vehicle(db_session, tenant_id=100, user_email='private-list@example.invalid', nickname=marker)
    current_user = SimpleNamespace(email=own.user_email, tenant_id=100)
    class InvalidSchema:
        @staticmethod
        def model_validate(*args, **kwargs):
            raise ValueError(marker)
    monkeypatch.setattr(vehicles_router, 'VehicleOutV1', InvalidSchema)
    with pytest.raises(HTTPException) as error:
        vehicles_router.get_vehicles(current_user=current_user, db=db_session)
    assert error.value.status_code == 500  # Must not pretend this is an empty account.
    assert marker not in error.value.detail
    captured = capsys.readouterr()
    assert marker not in captured.out + captured.err + caplog.text
    assert current_user.email not in captured.out + captured.err + caplog.text


@pytest.mark.parametrize('integrity', [True, False])
def test_creation_error_does_not_expose_database_or_private_values(db_session, monkeypatch, capsys, caplog, integrity):
    import json
    from sqlalchemy.exc import IntegrityError
    from src.modules.licensing import service as licensing_service
    marker = 'PRIVATE_SQL_OR_CREDENTIAL_VALUE'
    monkeypatch.setattr(licensing_service, 'assert_vehicle_quota', lambda *args: None)
    def fail(**kwargs):
        if integrity:
            raise IntegrityError('SELECT ' + marker, {}, ValueError(marker))
        raise RuntimeError(marker)
    monkeypatch.setattr(vehicles_router, '_find_existing_vehicle_by_vin_globally', fail)
    current_user = SimpleNamespace(email='private-create@example.invalid', tenant_id=100)
    response = vehicles_router.create_vehicle(vehicles_router.VehicleCreateV1(
        nickname='Fixture only', stk_valid_until=date(2030, 1, 1)), current_user, db_session)
    assert response.status_code == (400 if integrity else 500)
    assert marker not in response.body.decode()
    assert len(json.loads(response.body)['error']['details']['incident_id']) == 32
    captured = capsys.readouterr()
    assert marker not in captured.out + captured.err + caplog.text
    assert current_user.email not in captured.out + captured.err + caplog.text
