"""Testy servisní mapy – vlastní DB vrstva."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import Customer, ServiceLocation, Tenant
from src.modules.vehicle_hub.service_map.claim_service import (
    approve_service_location_claim,
    create_service_location_claim,
)
from src.modules.vehicle_hub.service_map.constants import (
    CATEGORY_AUTOSERVIS,
    CATEGORY_PNEUSERVIS,
    CATEGORY_STK,
    SOURCE_MDCR,
    SOURCE_OSM,
    SOURCE_VERIFIED_SERVICE,
)
from src.modules.vehicle_hub.service_map.mdcr_stk_sme_importer import import_mdcr_stk_sme
from src.modules.vehicle_hub.service_map.osm_importer import import_osm_overpass_json
from src.modules.vehicle_hub.service_map.search_service import (
    PII_FORBIDDEN_KEYS,
    USER_SEARCH_MAX_LIMIT,
    search_service_locations,
)


@pytest.fixture()
def db_session(tmp_path: Path):
    db_path = tmp_path / "service_map_test.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        tenant = Tenant(name="Map Tenant", license_key="map-tenant-key")
        db.add(tenant)
        db.commit()
        db.refresh(tenant)

        user = Customer(
            tenant_id=tenant.id,
            email="map-user@example.com",
            password_hash="hash",
            role="user",
            name="Map User",
        )
        service = Customer(
            tenant_id=tenant.id,
            email="map-service@example.com",
            password_hash="hash",
            role="service",
            name="Map Service",
        )
        admin = Customer(
            tenant_id=tenant.id,
            email="map-admin@example.com",
            password_hash="hash",
            role="developer_admin",
            name="Map Admin",
        )
        db.add_all([user, service, admin])
        db.commit()
        for row in (user, service, admin):
            db.refresh(row)

        inactive = ServiceLocation(
            source_type=SOURCE_OSM,
            source_external_id="osm/node/inactive",
            name="Zavřený servis",
            normalized_name="zavreny servis",
            category=CATEGORY_AUTOSERVIS,
            lat=49.75,
            lng=16.47,
            city="Svitavy",
            verification_status="imported",
            is_active=False,
        )
        active = ServiceLocation(
            source_type=SOURCE_OSM,
            source_external_id="osm/node/active",
            name="Autoservis Svitavy Test",
            normalized_name="autoservis svitavy test",
            category=CATEGORY_AUTOSERVIS,
            lat=49.756,
            lng=16.469,
            city="Svitavy",
            phone="+420777000111",
            verification_status="imported",
            is_active=True,
        )
        verified = ServiceLocation(
            source_type=SOURCE_VERIFIED_SERVICE,
            source_external_id="verified/1",
            name="Ověřený servis Partner",
            normalized_name="overeny servis partner",
            category=CATEGORY_AUTOSERVIS,
            lat=49.757,
            lng=16.470,
            city="Svitavy",
            verification_status="verified",
            linked_service_tenant_id=tenant.id,
            is_active=True,
        )
        db.add_all([inactive, active, verified])
        db.commit()
        yield db, {"tenant": tenant, "user": user, "service": service, "admin": admin, "active": active, "verified": verified}
    finally:
        db.close()


def test_search_radius_and_category(db_session):
    db, ctx = db_session
    items, total, _meta = search_service_locations(db, lat=49.756, lng=16.469, radius_km=5, category=CATEGORY_AUTOSERVIS)
    assert total >= 1
    assert ctx["active"].name in {row["name"] for row in items}
    empty, total_zero, _ = search_service_locations(db, lat=49.756, lng=16.469, radius_km=5, category="stk")
    assert total_zero == 0
    assert empty == []


def test_bounds_search(db_session):
    db, ctx = db_session
    items, total, meta = search_service_locations(
        db,
        north=49.80,
        south=49.74,
        east=16.50,
        west=16.44,
        lat=49.756,
        lng=16.469,
        limit=50,
    )
    assert meta["mode"] == "bounds"
    assert total >= 1
    assert ctx["active"].name in {row["name"] for row in items}


def test_max_limit_clamp(db_session):
    db, _ctx = db_session
    items, total, meta = search_service_locations(db, lat=49.756, lng=16.469, radius_km=30, limit=9999)
    assert meta["limit"] == USER_SEARCH_MAX_LIMIT
    assert len(items) <= USER_SEARCH_MAX_LIMIT


def test_q_search_normalized_name(db_session):
    db, ctx = db_session
    items, total, _ = search_service_locations(db, lat=49.756, lng=16.469, radius_km=10, q="svitavy test")
    assert total >= 1
    assert any(row["id"] == ctx["active"].id for row in items)


def test_verified_only(db_session):
    db, ctx = db_session
    items, total, _ = search_service_locations(db, lat=49.756, lng=16.469, radius_km=10, verified_only=True)
    assert total >= 1
    assert all(row["is_verified"] for row in items)
    assert any(row["id"] == ctx["verified"].id for row in items)


def test_inactive_not_returned(db_session):
    db, _ctx = db_session
    items, total, _ = search_service_locations(db, lat=49.75, lng=16.47, radius_km=30)
    names = {row["name"] for row in items}
    assert "Zavřený servis" not in names
    assert total >= 1


def test_osm_import_updates_same_external_id(db_session):
    db, _ctx = db_session
    payload = {
        "elements": [
            {
                "type": "node",
                "id": 999001,
                "lat": 49.757,
                "lon": 16.470,
                "tags": {"shop": "car_repair", "name": "OSM Import Test"},
            }
        ]
    }
    first = import_osm_overpass_json(db, payload, import_batch_id="batch-1")
    assert first["inserted"] == 1
    second = import_osm_overpass_json(db, payload, import_batch_id="batch-2")
    assert second["updated"] == 1
    assert second["inserted"] == 0
    count = db.query(ServiceLocation).filter(ServiceLocation.source_external_id == "node/999001").count()
    assert count == 1


def test_duplicate_within_100m_not_merged(db_session):
    db, ctx = db_session
    payload = {
        "elements": [
            {
                "type": "node",
                "id": 999002,
                "lat": 49.7561,
                "lon": 16.4691,
                "tags": {"shop": "car_repair", "name": "Autoservis Svitavy Test"},
            }
        ]
    }
    result = import_osm_overpass_json(db, payload, import_batch_id="dup-batch")
    assert result["inserted"] == 1 or result["duplicates_suspected"] >= 1
    total_rows = db.query(ServiceLocation).filter(ServiceLocation.category == CATEGORY_AUTOSERVIS).count()
    assert total_rows >= 2


def test_verified_service_not_overwritten_by_osm(db_session):
    db, ctx = db_session
    verified = ctx["verified"]
    old_name = verified.name
    payload = {
        "elements": [
            {
                "type": "node",
                "id": 888001,
                "lat": float(verified.lat),
                "lon": float(verified.lng),
                "tags": {"shop": "car_repair", "name": "Podvržený název"},
            }
        ]
    }
    import_osm_overpass_json(db, payload, import_batch_id="protect-batch")
    db.refresh(verified)
    assert verified.name == old_name
    assert verified.verification_status == "verified"


def test_mdcr_higher_confidence_than_osm(db_session):
    db, _ctx = db_session
    mdcr = import_mdcr_stk_sme(
        db,
        [
            {
                "source_external_id": "MDCR-STK-1",
                "name": "STK MDČR Test",
                "lat": 49.76,
                "lng": 16.48,
                "category": "stk",
                "city": "Svitavy",
            }
        ],
        import_batch_id="mdcr-batch",
    )
    assert mdcr["inserted"] == 1
    row = db.query(ServiceLocation).filter(ServiceLocation.source_external_id == "MDCR-STK-1").first()
    assert row is not None
    assert row.confidence_score == 0.92
    assert row.source_type == SOURCE_MDCR
    assert row.category == CATEGORY_STK


def test_service_can_claim_admin_links_tenant(db_session):
    db, ctx = db_session
    claim = create_service_location_claim(
        db,
        location_id=int(ctx["active"].id),
        service_tenant_id=int(ctx["tenant"].id),
        submitted_by_user_id=int(ctx["service"].id),
        ico="12345678",
        business_name="Test Servis s.r.o.",
    )
    assert claim.claim_status == "pending"
    approved = approve_service_location_claim(db, claim_id=int(claim.id), admin_user_id=int(ctx["admin"].id))
    assert approved.claim_status == "approved"
    db.refresh(ctx["active"])
    assert ctx["active"].verification_status == "verified"
    assert ctx["active"].linked_service_tenant_id == ctx["tenant"].id


def test_claim_verified_other_tenant_goes_admin_review(db_session):
    db, ctx = db_session
    other_tenant = Tenant(name="Other", license_key="other-key")
    db.add(other_tenant)
    db.commit()
    db.refresh(other_tenant)
    claim = create_service_location_claim(
        db,
        location_id=int(ctx["verified"].id),
        service_tenant_id=int(other_tenant.id),
        submitted_by_user_id=int(ctx["service"].id),
        business_name="Cizí servis",
    )
    assert claim.claim_status == "pending"
    assert "verified_owner_conflict" in (claim.fraud_flags_json or "")


def test_release_candidate_keeps_service_map_backend_only():
    """The additive release exposes the service-map API without activating staging UI assets."""
    from src.modules.vehicle_hub.routers_v1 import service_map

    paths = {route.path for route in service_map.router.routes}
    assert service_map.router.prefix == "/service-map"
    assert "/service-map/search" in paths
    assert "/service-map/locations/{location_id}" in paths


def test_user_search_excludes_duplicate_verification(db_session):
    db, _ctx = db_session
    dup = ServiceLocation(
        source_type=SOURCE_OSM,
        source_external_id="osm/node/dup-search-test",
        name="Duplicitní servis test",
        normalized_name="duplicitni servis test",
        category=CATEGORY_AUTOSERVIS,
        lat=49.751,
        lng=16.471,
        verification_status="duplicate",
        is_active=True,
    )
    db.add(dup)
    db.commit()

    user_items, user_total, _ = search_service_locations(db, lat=49.751, lng=16.471, radius_km=5)
    admin_items, admin_total, _ = search_service_locations(
        db, lat=49.751, lng=16.471, radius_km=5, admin_mode=True
    )
    assert not any(item["verification_status"] == "duplicate" for item in user_items)
    assert not any(int(item["id"]) == int(dup.id) for item in user_items)
    assert any(item["verification_status"] == "duplicate" for item in admin_items)
    assert any(int(item["id"]) == int(dup.id) for item in admin_items)
    assert admin_total >= user_total


def test_search_payload_has_no_pii(db_session):
    db, _ctx = db_session
    items, _total, _ = search_service_locations(db, lat=49.756, lng=16.469, radius_km=10)
    assert items
    for item in items:
        assert PII_FORBIDDEN_KEYS.isdisjoint(set(item.keys()))
