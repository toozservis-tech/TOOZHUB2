from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core import config as app_config
from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.decoder.models import VehicleDecodedData
from src.modules.vehicle_hub.models import Customer, Tenant, VehicleCatalogImage
import src.modules.vehicle_hub.services.catalog_image_service as catalog_image_service_module
from src.modules.vehicle_hub.services.catalog_image_service import (
    _provider_adapter,
    build_vehicle_image_queries,
    get_vehicle_catalog_image_service,
    normalize_vehicle_text,
    resolve_catalog_image_storage_file,
    score_image_candidate,
)


def _make_db(tmp_path: Path):
    db_path = tmp_path / "vehicle_catalog_image_service.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    tenant = Tenant(name="Tenant", license_key="tenant-key")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    user = Customer(tenant_id=tenant.id, email="owner@example.com", role="user", name="Owner")
    db.add(user)
    db.commit()
    db.refresh(user)
    return db, engine, tenant, user


def _decoded() -> VehicleDecodedData:
    return VehicleDecodedData(
        vin="VF3TESTVIN1234567",
        make="Peugeot",
        model="Boxer",
        production_year=2019,
        body_type="van",
        source_priority=["existing-vin-decoder"],
    )


def test_normalize_vehicle_text_handles_aliases() -> None:
    assert normalize_vehicle_text("Škoda") == "skoda"
    assert normalize_vehicle_text("vw") == "volkswagen"
    assert normalize_vehicle_text("Mercedes-Benz") == "mercedes"
    assert normalize_vehicle_text("Peugeot") == "peugeot"


def test_build_vehicle_image_queries_returns_expected_variants() -> None:
    queries = build_vehicle_image_queries(
        {"make": "Peugeot", "model": "Boxer", "year": 2019, "body_type": "van"}
    )
    assert queries[0] == "Peugeot Boxer 2019 van white front view exterior photo"
    assert any("front three quarter" in item or "front 3/4" in item for item in queries)
    assert any("exterior photo" in item for item in queries)
    assert all(any(color in item for color in ("white", "grey")) for item in queries)


def test_score_image_candidate_rewards_match_and_penalizes_interior() -> None:
    good = score_image_candidate(
        {
            "title": "Peugeot Boxer 2019 official exterior",
            "image_url": "https://example.com/boxer.jpg",
            "thumbnail_url": "https://example.com/boxer-thumb.jpg",
            "source_url": "https://example.com/boxer",
            "source_domain": "example.com",
            "width": 1280,
            "height": 720,
            "snippet": "white van front three quarter",
            "provider": "mock",
        },
        {"make": "Peugeot", "model": "Boxer", "year": 2019, "body_type": "van", "preferred_color": "white"},
    )
    bad = score_image_candidate(
        {
            "title": "Peugeot Boxer 2019 interior lifestyle",
            "image_url": "https://example.com/interior.jpg",
            "thumbnail_url": "https://example.com/interior-thumb.jpg",
            "source_url": "https://example.com/interior",
            "source_domain": "example.com",
            "width": 1280,
            "height": 720,
            "snippet": "interior dashboard",
            "provider": "mock",
        },
        {"make": "Peugeot", "model": "Boxer", "year": 2019, "body_type": "van", "preferred_color": "white"},
    )
    assert good >= 75
    assert bad < good


def test_score_image_candidate_does_not_treat_toyota_as_toy() -> None:
    score = score_image_candidate(
        {
            "title": "Toyota Verso 2012 white front three quarter exterior",
            "image_url": "https://example.com/toyota-verso.jpg",
            "thumbnail_url": "https://example.com/toyota-verso-thumb.jpg",
            "source_url": "https://example.com/toyota-verso",
            "source_domain": "example.com",
            "width": 1200,
            "height": 900,
            "snippet": "Toyota Verso used car exterior",
            "provider": "mock",
        },
        {"make": "Toyota", "model": "Verso", "year": 2012, "body_type": None, "preferred_color": "white"},
    )
    assert score >= 75


def test_provider_disabled_returns_placeholder(tmp_path: Path, monkeypatch) -> None:
    db, engine, _tenant, user = _make_db(tmp_path)
    storage_dir = tmp_path / "catalog_vehicle_images"
    storage_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(catalog_image_service_module, "CATALOG_IMAGE_STORAGE_DIR", storage_dir)
    monkeypatch.setattr(app_config, "VEHICLE_IMAGE_PROVIDER", "disabled")
    _provider_adapter.cache_clear()
    get_vehicle_catalog_image_service.cache_clear()
    service = get_vehicle_catalog_image_service()
    result = service.preview_from_decoded_vehicle(
        db=db,
        vin="VF3TESTVIN1234567",
        decoded_vehicle=_decoded(),
        preferred_color=None,
        force_refresh=False,
        current_user=user,
    )
    assert result.ok is True
    assert result.catalog_image["provider"] == "disabled"
    assert result.catalog_image["url"] == "/web/assets/vehicle-placeholder.svg"
    db.close()
    engine.dispose()


def test_mock_provider_returns_stable_result(tmp_path: Path, monkeypatch) -> None:
    db, engine, _tenant, user = _make_db(tmp_path)
    storage_dir = tmp_path / "catalog_vehicle_images"
    storage_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(catalog_image_service_module, "CATALOG_IMAGE_STORAGE_DIR", storage_dir)
    monkeypatch.setattr(app_config, "VEHICLE_IMAGE_PROVIDER", "mock")
    monkeypatch.setattr(app_config, "VEHICLE_IMAGE_API_KEY", "")
    _provider_adapter.cache_clear()
    get_vehicle_catalog_image_service.cache_clear()
    service = get_vehicle_catalog_image_service()
    result = service.preview_from_decoded_vehicle(
        db=db,
        vin="VF3TESTVIN1234567",
        decoded_vehicle=_decoded(),
        preferred_color="white",
        force_refresh=False,
        current_user=user,
    )
    assert result.ok is True
    assert result.catalog_image["provider"] == "mock"
    assert result.catalog_image["representative"] is True
    assert result.catalog_image["verified_real_vehicle"] is False
    assert result.catalog_image["url"].startswith("/api/v1/vehicles/catalog-images/")
    row = db.query(VehicleCatalogImage).first()
    assert row is not None
    stored_file = resolve_catalog_image_storage_file(row)
    assert stored_file is not None and stored_file.exists()
    db.close()
    engine.dispose()


def test_cache_hit_and_cache_miss_and_force_refresh(tmp_path: Path, monkeypatch) -> None:
    db, engine, tenant, user = _make_db(tmp_path)
    storage_dir = tmp_path / "catalog_vehicle_images"
    storage_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(catalog_image_service_module, "CATALOG_IMAGE_STORAGE_DIR", storage_dir)
    monkeypatch.setattr(app_config, "VEHICLE_IMAGE_PROVIDER", "mock")
    _provider_adapter.cache_clear()
    get_vehicle_catalog_image_service.cache_clear()
    service = get_vehicle_catalog_image_service()

    first = service.preview_from_decoded_vehicle(
        db=db,
        vin="VF3TESTVIN1234567",
        decoded_vehicle=_decoded(),
        preferred_color="white",
        force_refresh=False,
        current_user=user,
    )
    assert first.catalog_image["provider"] == "mock"
    rows = db.query(VehicleCatalogImage).filter(VehicleCatalogImage.tenant_id == tenant.id).all()
    assert len(rows) == 1

    second = service.preview_from_decoded_vehicle(
        db=db,
        vin="VF3TESTVIN1234567",
        decoded_vehicle=_decoded(),
        preferred_color="white",
        force_refresh=False,
        current_user=user,
    )
    assert second.catalog_image["provider"] == "cache"

    third = service.preview_from_decoded_vehicle(
        db=db,
        vin="VF3TESTVIN1234567",
        decoded_vehicle=_decoded(),
        preferred_color="white",
        force_refresh=True,
        current_user=user,
    )
    assert third.catalog_image["provider"] == "mock"
    assert db.query(VehicleCatalogImage).count() == 1
    db.close()
    engine.dispose()


def test_provider_failure_returns_fallback_not_500(tmp_path: Path, monkeypatch) -> None:
    db, engine, _tenant, user = _make_db(tmp_path)
    storage_dir = tmp_path / "catalog_vehicle_images"
    storage_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(catalog_image_service_module, "CATALOG_IMAGE_STORAGE_DIR", storage_dir)
    monkeypatch.setattr(app_config, "VEHICLE_IMAGE_PROVIDER", "mock")
    _provider_adapter.cache_clear()
    get_vehicle_catalog_image_service.cache_clear()
    service = get_vehicle_catalog_image_service()

    class FailingProvider:
        name = "mock"

        def search(self, query: str, *, limit: int):
            raise RuntimeError("boom")

    monkeypatch.setattr(
        "src.modules.vehicle_hub.services.catalog_image_service._provider_adapter",
        lambda: FailingProvider(),
    )
    result = service.preview_from_decoded_vehicle(
        db=db,
        vin="VF3TESTVIN1234567",
        decoded_vehicle=_decoded(),
        preferred_color="white",
        force_refresh=True,
        current_user=user,
    )
    assert result.ok is True
    assert result.catalog_image["url"] == "/web/assets/vehicle-placeholder.svg"
    assert result.warnings
    db.close()
    engine.dispose()


def test_missing_local_catalog_file_falls_back_to_new_lookup(tmp_path: Path, monkeypatch) -> None:
    db, engine, tenant, user = _make_db(tmp_path)
    storage_dir = tmp_path / "catalog_vehicle_images"
    storage_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(catalog_image_service_module, "CATALOG_IMAGE_STORAGE_DIR", storage_dir)
    monkeypatch.setattr(app_config, "VEHICLE_IMAGE_PROVIDER", "mock")
    _provider_adapter.cache_clear()
    get_vehicle_catalog_image_service.cache_clear()
    service = get_vehicle_catalog_image_service()

    first = service.preview_from_decoded_vehicle(
        db=db,
        vin="VF3TESTVIN1234567",
        decoded_vehicle=_decoded(),
        preferred_color="white",
        force_refresh=False,
        current_user=user,
    )
    assert first.catalog_image["provider"] == "mock"
    row = db.query(VehicleCatalogImage).filter(VehicleCatalogImage.tenant_id == tenant.id).first()
    assert row is not None
    stored_file = resolve_catalog_image_storage_file(row)
    assert stored_file is not None
    stored_file.unlink()

    second = service.preview_from_decoded_vehicle(
        db=db,
        vin="VF3TESTVIN1234567",
        decoded_vehicle=_decoded(),
        preferred_color="white",
        force_refresh=False,
        current_user=user,
    )
    assert second.catalog_image["provider"] == "mock"
    recreated_file = resolve_catalog_image_storage_file(row)
    assert recreated_file is not None and recreated_file.exists()
    db.close()
    engine.dispose()
