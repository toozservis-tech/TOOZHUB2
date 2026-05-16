from __future__ import annotations

from datetime import date
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core import config as app_config
from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import Customer, Tenant, Vehicle, VehiclePhotoAsset
from src.modules.vehicle_hub.routers_v1 import vehicles as vehicles_router
from src.modules.vehicle_hub.routers_v1.auth import get_current_user
import src.modules.vehicle_hub.services.catalog_image_service as catalog_image_service_module
from src.modules.vehicle_hub.services.catalog_image_service import _provider_adapter, get_vehicle_catalog_image_service


def test_preview_from_vin_mock_mode(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "vehicle_preview_from_vin.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    tenant = Tenant(name="Tenant", license_key="tenant-key")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    owner = Customer(tenant_id=tenant.id, email="owner@example.com", role="user", name="Owner")
    db.add(owner)
    db.commit()
    db.refresh(owner)

    app = FastAPI()
    app.include_router(vehicles_router.router, prefix="/api/v1")

    def override_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[vehicles_router.get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: owner

    storage_dir = tmp_path / "catalog_vehicle_images"
    storage_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(catalog_image_service_module, "CATALOG_IMAGE_STORAGE_DIR", storage_dir)
    monkeypatch.setattr(app_config, "VEHICLE_IMAGE_PROVIDER", "mock")
    monkeypatch.setattr(app_config, "VEHICLE_IMAGE_API_KEY", "")
    monkeypatch.setattr(app_config, "VEHICLE_IMAGE_REGEN_LIMIT_ENABLED", True)
    _provider_adapter.cache_clear()
    get_vehicle_catalog_image_service.cache_clear()

    async def fake_decode_vin(req, db_arg, current_user_arg):
        from src.modules.vehicle_hub.decoder.models import VehicleDecodeResponse, VehicleDecodedData

        return VehicleDecodeResponse(
            success=True,
            data=VehicleDecodedData(
                vin=req.vin,
                make="Peugeot",
                model="Boxer",
                production_year=2019,
                body_type="van",
                source_priority=["existing-vin-decoder"],
            ),
            errors=[],
        )

    monkeypatch.setattr("src.modules.vehicle_hub.decoder.router.decode_vin_core", fake_decode_vin)

    client = TestClient(app)
    response = client.post(
        "/api/v1/vehicles/preview-from-vin",
        json={"vin": "VF3TESTVIN1234567", "preferred_color": "white", "force_refresh": False},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["decoded"]["make"] == "Peugeot"
    assert data["decoded"]["model"] == "Boxer"
    assert data["decoded"]["year"] == 2019
    assert data["catalog_image"]["representative"] is True
    assert data["catalog_image"]["verified_real_vehicle"] is False
    assert data["catalog_image"]["provider"] in {"mock", "cache"}
    assert data["catalog_image"]["url"].startswith("/api/v1/vehicles/catalog-images/")
    assert isinstance(data["warnings"], list)
    assert data["remaining_regenerations"] == 1

    catalog_file_response = client.get(data["catalog_image"]["url"])
    assert catalog_file_response.status_code == 200
    assert catalog_file_response.headers["content-type"].startswith("image/jpeg")

    vehicle = Vehicle(
        tenant_id=tenant.id,
        user_email=owner.email,
        nickname="Peugeot Boxer",
        brand="Peugeot",
        model="Boxer",
        year=2019,
        vin="VF3TESTVN12345678",
        stk_valid_until=date(2027, 1, 1),
    )
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)

    regenerate = client.post(
        f"/api/v1/vehicles/{vehicle.id}/catalog-image/generate",
        json={"preferred_color": "white", "save_to_gallery": True},
    )
    assert regenerate.status_code == 200
    regenerate_data = regenerate.json()
    assert regenerate_data["ok"] is True
    assert regenerate_data["saved_to_gallery"] is True
    assert regenerate_data["remaining_regenerations"] == 0
    assert vehicle.catalog_image_id
    assert vehicle.catalog_image_url.startswith("/api/v1/vehicles/catalog-images/")
    gallery_photo = (
        db.query(VehiclePhotoAsset)
        .filter(
            VehiclePhotoAsset.vehicle_id == vehicle.id,
            VehiclePhotoAsset.role == "gallery",
            VehiclePhotoAsset.photo_kind == "catalog_image",
            VehiclePhotoAsset.deleted_at.is_(None),
        )
        .first()
    )
    assert gallery_photo is not None

    blocked = client.post(
        f"/api/v1/vehicles/{vehicle.id}/catalog-image/generate",
        json={"preferred_color": "white", "save_to_gallery": False},
    )
    assert blocked.status_code == 429

    db.close()
    engine.dispose()
