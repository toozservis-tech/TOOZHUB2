from __future__ import annotations

import base64
from datetime import date
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import Customer, Tenant, Vehicle as VehicleModel
from src.modules.vehicle_hub.ownership import ensure_vehicle_owner_assignment
from src.modules.vehicle_hub.routers_v1 import vehicles as vehicles_router


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "vehicle_photo_api.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _seed_owned_vehicle(db_session):
    tenant = Tenant(name="Photo Tenant", license_key="photo-tenant-key")
    db_session.add(tenant)
    db_session.flush()

    owner = Customer(
        tenant_id=tenant.id,
        email="photo-user@example.com",
        password_hash="hash",
        role="user",
    )
    db_session.add(owner)
    db_session.flush()

    vehicle = VehicleModel(
        tenant_id=tenant.id,
        user_email=owner.email,
        nickname="Photo Car",
        vin="TMBJF73T2B9044629",
        stk_valid_until=date(2030, 1, 1),
    )
    db_session.add(vehicle)
    db_session.flush()

    ensure_vehicle_owner_assignment(
        db_session,
        vehicle=vehicle,
        owner=owner,
        assigned_by_customer_id=owner.id,
    )
    db_session.commit()
    db_session.refresh(owner)
    db_session.refresh(vehicle)
    return owner, vehicle


def _png_base64(size: tuple[int, int], color: tuple[int, int, int]) -> str:
    image = Image.new("RGB", size, color)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def test_upload_vehicle_photo_normalizes_to_canonical_jpeg(db_session, monkeypatch, tmp_path: Path) -> None:
    owner, vehicle = _seed_owned_vehicle(db_session)
    photos_dir = tmp_path / "vehicle_photos"
    photos_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(vehicles_router, "VEHICLE_PHOTOS_DIR", photos_dir)

    response = vehicles_router.upload_vehicle_photo(
        vehicle_id=vehicle.id,
        payload=vehicles_router.VehiclePhotoUploadRequest(
            file_name="source.png",
            file_mime_type="image/png",
            file_content_base64=_png_base64((2200, 1600), (12, 120, 220)),
        ),
        current_user=owner,
        db=db_session,
    )

    db_session.refresh(vehicle)
    assert vehicle.photo_path is not None
    assert vehicle.photo_path.endswith(".jpg")
    assert "1280x720 JPEG" in response["message"]

    stored_file = photos_dir / vehicle.photo_path
    assert stored_file.exists()
    assert stored_file.stat().st_size <= vehicles_router.MAX_VEHICLE_PHOTO_OUTPUT_SIZE_BYTES

    with Image.open(stored_file) as normalized:
        assert normalized.format == "JPEG"
        assert normalized.size == vehicles_router.VEHICLE_PHOTO_TARGET_SIZE

    file_response = vehicles_router.get_vehicle_photo(vehicle_id=vehicle.id, current_user=owner, db=db_session)
    assert file_response.media_type == "image/jpeg"


def test_upload_vehicle_photo_rejects_raw_payload_over_40_mb(db_session, monkeypatch, tmp_path: Path) -> None:
    owner, vehicle = _seed_owned_vehicle(db_session)
    photos_dir = tmp_path / "vehicle_photos"
    photos_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(vehicles_router, "VEHICLE_PHOTOS_DIR", photos_dir)

    oversized_payload = base64.b64encode(b"x" * (vehicles_router.MAX_VEHICLE_PHOTO_RAW_SIZE_BYTES + 1)).decode("ascii")

    with pytest.raises(vehicles_router.HTTPException) as exc:
        vehicles_router.upload_vehicle_photo(
            vehicle_id=vehicle.id,
            payload=vehicles_router.VehiclePhotoUploadRequest(
                file_name="oversized.jpg",
                file_mime_type="image/jpeg",
                file_content_base64=oversized_payload,
            ),
            current_user=owner,
            db=db_session,
        )

    assert exc.value.status_code == 413
    assert "max 40 MB" in str(exc.value.detail)
