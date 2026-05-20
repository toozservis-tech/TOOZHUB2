"""Targeted tests for service work-order items and intake -> work-order conversion."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub import schema_management as schema_management_mod
from src.modules.vehicle_hub.database import Base, get_db
from src.modules.vehicle_hub.models import (
    Customer,
    GlobalAuditLog,
    ServiceCustomerLink,
    ServiceIntake,
    ServiceWorkOrder,
    ServiceWorkOrderCsvImport,
    ServiceWorkOrderItem,
    Tenant,
    Vehicle,
    VehicleOwnership,
    VehicleServiceLink,
)
from src.modules.vehicle_hub.routers_v1 import service_workspace_work_orders as work_order_items_router
from src.modules.vehicle_hub.routers_v1.auth import get_current_user


@pytest.fixture()
def work_order_items_ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(schema_management_mod, "assert_module_ready", lambda *a, **k: None)
    monkeypatch.setattr(work_order_items_router, "assert_module_ready", lambda *a, **k: None)

    db_path = tmp_path / "service_work_order_items.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()

    tenant = Tenant(name="T-work-order-items", license_key="lic-work-order-items")
    db.add(tenant)
    db.commit()
    db.refresh(tenant)

    def mk_customer(email: str, role: str, name: str) -> Customer:
        c = Customer(
            tenant_id=tenant.id,
            email=email,
            password_hash="x",
            name=name,
            role=role,
        )
        db.add(c)
        db.commit()
        db.refresh(c)
        return c

    service_a = mk_customer("service-a@example.com", "service", "Servis A")
    service_b = mk_customer("service-b@example.com", "service", "Servis B")
    owner = mk_customer("owner@example.com", "user", "Majitel")

    vehicle = Vehicle(
        tenant_id=tenant.id,
        user_email=owner.email,
        nickname="Servisní Octavia",
        plate="1A11111",
        vin="TMBTEST0000000001",
        brand="Skoda",
        model="Octavia",
    )
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    db.add(
        VehicleOwnership(
            tenant_id=tenant.id,
            vehicle_id=vehicle.id,
            customer_id=owner.id,
            ownership_type="owner",
            ownership_origin="manual",
            is_primary=True,
            is_active=True,
        )
    )
    db.add(
        ServiceCustomerLink(
            service_tenant_id=service_a.tenant_id,
            service_customer_id=service_a.id,
            customer_tenant_id=owner.tenant_id,
            customer_id=owner.id,
            status="active",
            note="items test",
        )
    )
    db.add(
        VehicleServiceLink(
            tenant_id=tenant.id,
            service_customer_id=service_a.id,
            owner_customer_id=owner.id,
            vehicle_id=vehicle.id,
            status="approved",
            approved_at=datetime.utcnow(),
            approved_by_customer_id=owner.id,
        )
    )
    db.commit()

    intake = ServiceIntake(
        tenant_id=tenant.id,
        service_id=service_a.id,
        service_tenant_id=service_a.tenant_id,
        vehicle_id=vehicle.id,
        customer_id=owner.id,
        intake_status="intake_started",
        intake_source="service_cases_api",
        owner_approval_required=False,
        owner_approval_status="approved",
        customer_request="Klepe přední náprava",
        intake_note="Převzato u recepce",
        created_by=service_a.id,
    )
    db.add(intake)
    db.commit()
    db.refresh(intake)

    app = FastAPI()
    app.include_router(work_order_items_router.router, prefix="/api/v1")

    def override_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_db

    def set_user(user: Customer):
        app.dependency_overrides[get_current_user] = lambda: user

    client = TestClient(app)
    try:
        yield {
            "client": client,
            "db": db,
            "set_user": set_user,
            "tenant": tenant,
            "service_a": service_a,
            "service_b": service_b,
            "owner": owner,
            "vehicle": vehicle,
            "intake": intake,
        }
    finally:
        app.dependency_overrides.clear()
        db.close()
        engine.dispose()


def _create_order(ctx) -> int:
    ctx["set_user"](ctx["service_a"])
    r = ctx["client"].post(f"/api/v1/services/workspace/vehicle-intakes/{ctx['intake'].id}/create-work-order", json={})
    assert r.status_code == 201, r.text
    return int(r.json()["work_order"]["id"])


def test_create_work_order_from_intake(work_order_items_ctx):
    ctx = work_order_items_ctx
    work_order_id = _create_order(ctx)

    row = ctx["db"].query(ServiceWorkOrder).filter(ServiceWorkOrder.id == work_order_id).first()
    assert row is not None
    assert row.source_type == "intake"
    assert row.source_intake_id == ctx["intake"].id
    assert row.service_customer_id == ctx["service_a"].id

    audit = (
        ctx["db"]
        .query(GlobalAuditLog)
        .filter(
            GlobalAuditLog.entity_type == "service_work_order",
            GlobalAuditLog.entity_id == work_order_id,
            GlobalAuditLog.action == "SERVICE_WORK_ORDER_CREATED_FROM_INTAKE",
        )
        .first()
    )
    assert audit is not None


@pytest.mark.parametrize(
    ("item_type", "name"),
    [
        ("labor", "Diagnostika závady"),
        ("material", "Olejový filtr"),
        ("other", "Likvidace odpadu"),
    ],
)
def test_work_order_item_types_are_saved(work_order_items_ctx, item_type: str, name: str):
    ctx = work_order_items_ctx
    work_order_id = _create_order(ctx)
    r = ctx["client"].post(
        f"/api/v1/services/workspace/work-orders/{work_order_id}/items",
        json={
            "type": item_type,
            "name": name,
            "quantity": 2,
            "unit": "ks",
            "vat_rate": 21,
            "sale_price_without_vat": 100,
        },
    )
    assert r.status_code == 201, r.text
    item = r.json()["item"]
    assert item["type"] == item_type
    assert item["name"] == name
    assert item["line_total_without_vat"] == 200
    assert item["vat_amount"] == 42
    assert item["line_total_with_vat"] == 242


def test_summary_counts_vat_and_groups(work_order_items_ctx):
    ctx = work_order_items_ctx
    work_order_id = _create_order(ctx)
    for payload in (
        {"type": "labor", "name": "Práce", "quantity": 1.5, "unit": "h", "vat_rate": 21, "sale_price_without_vat": 800},
        {"type": "material", "name": "Díl", "quantity": 2, "unit": "ks", "vat_rate": 21, "sale_price_without_vat": 500, "discount_percent": 10},
        {"type": "other", "name": "Ekologický poplatek", "quantity": 1, "unit": "ks", "vat_rate": 0, "sale_price_without_vat": 100},
    ):
        r = ctx["client"].post(f"/api/v1/services/workspace/work-orders/{work_order_id}/items", json=payload)
        assert r.status_code == 201, r.text

    r = ctx["client"].get(f"/api/v1/services/workspace/work-orders/{work_order_id}/summary")
    assert r.status_code == 200, r.text
    summary = r.json()
    assert summary["groups"]["labor"]["total_without_vat"] == 1200
    assert summary["groups"]["material"]["total_without_vat"] == 900
    assert summary["groups"]["other"]["total_without_vat"] == 100
    assert summary["total_without_vat"] == 2200
    assert summary["vat_total"] == 441
    assert summary["total_with_vat"] == 2641


def test_foreign_service_cannot_modify_other_work_order(work_order_items_ctx):
    ctx = work_order_items_ctx
    work_order_id = _create_order(ctx)
    ctx["set_user"](ctx["service_b"])
    r = ctx["client"].post(
        f"/api/v1/services/workspace/work-orders/{work_order_id}/items",
        json={"type": "labor", "name": "Cizí práce", "sale_price_without_vat": 100},
    )
    assert r.status_code == 404


def test_delete_item_is_soft_delete_and_audited(work_order_items_ctx):
    ctx = work_order_items_ctx
    work_order_id = _create_order(ctx)
    r = ctx["client"].post(
        f"/api/v1/services/workspace/work-orders/{work_order_id}/items",
        json={"type": "material", "name": "Díl", "quantity": 1, "sale_price_without_vat": 300},
    )
    assert r.status_code == 201, r.text
    item_id = int(r.json()["item"]["id"])

    r = ctx["client"].delete(f"/api/v1/services/workspace/work-orders/{work_order_id}/items/{item_id}")
    assert r.status_code == 200, r.text

    item = ctx["db"].query(ServiceWorkOrderItem).filter(ServiceWorkOrderItem.id == item_id).first()
    assert item is not None
    assert item.deleted_at is not None
    assert item.deleted_by == ctx["service_a"].id

    audit = (
        ctx["db"]
        .query(GlobalAuditLog)
        .filter(
            GlobalAuditLog.entity_type == "service_work_order_item",
            GlobalAuditLog.entity_id == item_id,
            GlobalAuditLog.action == "SERVICE_WORK_ORDER_ITEM_DELETED",
        )
        .first()
    )
    assert audit is not None

    summary = r.json()["summary"]
    assert summary["total_without_vat"] == 0


def test_non_service_user_gets_403(work_order_items_ctx):
    ctx = work_order_items_ctx
    work_order_id = _create_order(ctx)
    ctx["set_user"](ctx["owner"])
    r = ctx["client"].get(f"/api/v1/services/workspace/work-orders/{work_order_id}/summary")
    assert r.status_code == 403


def test_csv_preview_detects_semicolon_and_does_not_write_items(work_order_items_ctx):
    ctx = work_order_items_ctx
    work_order_id = _create_order(ctx)
    ctx["set_user"](ctx["service_a"])
    csv_body = "název dílu;kód dílu;množství;prodej bez dph\nOlejový filtr;OF123;2;150\n"

    r = ctx["client"].post(
        f"/api/v1/services/workspace/work-orders/{work_order_id}/csv/preview",
        files={"file": ("parts.csv", csv_body.encode("utf-8"), "text/csv")},
    )

    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["delimiter"] == ";"
    assert payload["detected_mapping"]["name"] == "název dílu"
    assert payload["validation"]["importable_count"] == 1
    assert ctx["db"].query(ServiceWorkOrderItem).filter(ServiceWorkOrderItem.work_order_id == work_order_id).count() == 0


def test_csv_preview_detects_comma(work_order_items_ctx):
    ctx = work_order_items_ctx
    work_order_id = _create_order(ctx)
    ctx["set_user"](ctx["service_a"])
    csv_body = "name,code,quantity,sale_price_without_vat\nBrzdové destičky,BD1,1,900\n"

    r = ctx["client"].post(
        f"/api/v1/services/workspace/work-orders/{work_order_id}/csv/preview",
        files={"file": ("parts.csv", csv_body.encode("utf-8"), "text/csv")},
    )

    assert r.status_code == 200, r.text
    assert r.json()["delimiter"] == ","


def test_csv_import_inserts_valid_material_items_and_returns_summary(work_order_items_ctx):
    ctx = work_order_items_ctx
    work_order_id = _create_order(ctx)
    ctx["set_user"](ctx["service_a"])
    csv_body = "name;code;quantity;unit;vat_rate;purchase_price_without_vat;sale_price_without_vat;discount_percent;note\nOlej;OL1;2;ks;21;80;120;0;Poznámka\n"
    mapping = {
        "name": "name",
        "code": "code",
        "quantity": "quantity",
        "unit": "unit",
        "vat_rate": "vat_rate",
        "purchase_price_without_vat": "purchase_price_without_vat",
        "sale_price_without_vat": "sale_price_without_vat",
        "discount_percent": "discount_percent",
        "note": "note",
    }

    r = ctx["client"].post(
        f"/api/v1/services/workspace/work-orders/{work_order_id}/csv/import",
        files={"file": ("parts.csv", csv_body.encode("utf-8"), "text/csv")},
        data={"mapping_json": json.dumps(mapping), "skip_duplicates": "true"},
    )

    assert r.status_code == 200, r.text
    result = r.json()["import_result"]
    assert result["imported_count"] == 1
    assert result["skipped_count"] == 0
    assert r.json()["summary"]["groups"]["material"]["total_without_vat"] == 240
    item = ctx["db"].query(ServiceWorkOrderItem).filter(ServiceWorkOrderItem.work_order_id == work_order_id).first()
    assert item is not None
    assert item.item_type == "material"
    assert item.source == "csv"
    assert item.note == "Poznámka"


def test_csv_import_skips_invalid_rows(work_order_items_ctx):
    ctx = work_order_items_ctx
    work_order_id = _create_order(ctx)
    ctx["set_user"](ctx["service_a"])
    csv_body = "name;quantity;sale_price_without_vat;vat_rate\nValidní díl;1;100;21\nVadný díl;-2;50;21\nŠpatné DPH;1;30;15\n"
    mapping = {"name": "name", "quantity": "quantity", "sale_price_without_vat": "sale_price_without_vat", "vat_rate": "vat_rate"}

    r = ctx["client"].post(
        f"/api/v1/services/workspace/work-orders/{work_order_id}/csv/import",
        files={"file": ("parts.csv", csv_body.encode("utf-8"), "text/csv")},
        data={"mapping_json": json.dumps(mapping), "skip_duplicates": "true"},
    )

    assert r.status_code == 200, r.text
    result = r.json()["import_result"]
    assert result["imported_count"] == 1
    assert result["skipped_count"] == 2
    assert len(result["error_rows"]) == 2
    assert {row["row_number"] for row in result["error_rows"]} == {3, 4}


def test_csv_import_skips_duplicates_and_writes_import_audit(work_order_items_ctx):
    ctx = work_order_items_ctx
    work_order_id = _create_order(ctx)
    ctx["set_user"](ctx["service_a"])
    mapping = {"name": "name", "code": "code", "quantity": "quantity", "sale_price_without_vat": "sale_price_without_vat"}
    csv_body = "name;code;quantity;sale_price_without_vat\nDuplicitní díl;DUP;1;100\n"

    first = ctx["client"].post(
        f"/api/v1/services/workspace/work-orders/{work_order_id}/csv/import",
        files={"file": ("parts.csv", csv_body.encode("utf-8"), "text/csv")},
        data={"mapping_json": json.dumps(mapping), "skip_duplicates": "true"},
    )
    assert first.status_code == 200, first.text
    second = ctx["client"].post(
        f"/api/v1/services/workspace/work-orders/{work_order_id}/csv/import",
        files={"file": ("parts.csv", csv_body.encode("utf-8"), "text/csv")},
        data={"mapping_json": json.dumps(mapping), "skip_duplicates": "true"},
    )

    assert second.status_code == 200, second.text
    result = second.json()["import_result"]
    assert result["imported_count"] == 0
    assert result["duplicate_count"] == 1
    assert result["skipped_count"] == 1
    assert ctx["db"].query(ServiceWorkOrderItem).filter(ServiceWorkOrderItem.work_order_id == work_order_id, ServiceWorkOrderItem.source == "csv").count() == 1
    import_record = ctx["db"].query(ServiceWorkOrderCsvImport).filter(ServiceWorkOrderCsvImport.work_order_id == work_order_id).order_by(ServiceWorkOrderCsvImport.id.desc()).first()
    assert import_record is not None
    assert import_record.duplicate_count == 1
    audit = (
        ctx["db"]
        .query(GlobalAuditLog)
        .filter(
            GlobalAuditLog.entity_type == "service_work_order_csv_import",
            GlobalAuditLog.entity_id == import_record.id,
            GlobalAuditLog.action == "SERVICE_WORK_ORDER_CSV_IMPORTED",
        )
        .first()
    )
    assert audit is not None


def test_csv_import_foreign_service_gets_403(work_order_items_ctx):
    ctx = work_order_items_ctx
    work_order_id = _create_order(ctx)
    ctx["set_user"](ctx["service_b"])
    csv_body = "name;quantity;sale_price_without_vat\nCizí díl;1;100\n"
    mapping = {"name": "name", "quantity": "quantity", "sale_price_without_vat": "sale_price_without_vat"}

    r = ctx["client"].post(
        f"/api/v1/services/workspace/work-orders/{work_order_id}/csv/import",
        files={"file": ("parts.csv", csv_body.encode("utf-8"), "text/csv")},
        data={"mapping_json": json.dumps(mapping), "skip_duplicates": "true"},
    )

    assert r.status_code == 403
