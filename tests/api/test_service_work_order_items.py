"""Targeted tests for service work-order items and intake -> work-order conversion."""
from __future__ import annotations

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
