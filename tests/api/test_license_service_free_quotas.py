"""Kvóty SERVICE FREE vs FULL — přímé volání licenční vrstvy (SQLite in-memory)."""
from __future__ import annotations

from datetime import date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.licensing.service import (
    LicenseError,
    assert_service_customer_link_quota,
    assert_service_invoice_monthly_quota,
    assert_service_monthly_service_record_quota,
    assert_service_vehicle_link_quota,
    assert_vehicle_quota,
)
from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import (
    Customer,
    License,
    ServiceCustomerLink,
    ServiceInvoice,
    ServiceRecord,
    Tenant,
    Vehicle,
    VehicleServiceLink,
)


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _seed_service_tenant_free(db, *, key_suffix: str = "a") -> tuple[Tenant, Customer]:
    t = Tenant(
        name="SVC",
        license_key=f"lic-sf-{key_suffix}",
        workspace_route_kind="service",
        workspace_slug=f"wsvc-{key_suffix}"[:160],
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    svc = Customer(
        tenant_id=t.id,
        email=f"svc.sf.{key_suffix}@example.com",
        password_hash="x",
        name="Servis",
        role="service",
    )
    db.add(svc)
    db.commit()
    db.refresh(svc)
    lic = License(
        tenant_id=t.id,
        plan="service_free",
        status="active",
        vehicles_limit=1,
        valid_from=datetime.utcnow(),
    )
    db.add(lic)
    db.commit()
    return t, svc


def test_service_free_customer_link_quota_fourth_blocks(db_session):
    db = db_session
    t, svc = _seed_service_tenant_free(db, key_suffix="cl")
    for i in range(3):
        u = Customer(
            tenant_id=t.id,
            email=f"u{i}-cl@ex.com",
            password_hash="x",
            name=f"U{i}",
            role="user",
        )
        db.add(u)
        db.commit()
        db.refresh(u)
        db.add(
            ServiceCustomerLink(
                service_tenant_id=t.id,
                service_customer_id=svc.id,
                customer_tenant_id=t.id,
                customer_id=u.id,
                status="active",
            )
        )
    db.commit()

    with pytest.raises(LicenseError) as ei:
        assert_service_customer_link_quota(db, service_customer_id=int(svc.id))
    assert ei.value.code == "SERVICE_FREE_CUSTOMER_LINKS_EXCEEDED"


def test_service_free_vehicle_link_quota_blocks(db_session):
    db = db_session
    t, svc = _seed_service_tenant_free(db, key_suffix="vl")
    u = Customer(tenant_id=t.id, email="one-vl@ex.com", password_hash="x", name="O", role="user")
    db.add(u)
    db.commit()
    db.refresh(u)
    for i in range(3):
        vin = ("1HGBH41JX" + f"{i:08d}")[:17]
        assert len(vin) == 17
        v = Vehicle(
            tenant_id=t.id,
            user_email=u.email,
            nickname=f"V{i}",
            vin=vin,
        )
        db.add(v)
        db.flush()
        db.add(
            VehicleServiceLink(
                tenant_id=t.id,
                service_customer_id=svc.id,
                owner_customer_id=u.id,
                vehicle_id=v.id,
                status="approved",
                source_type="test",
                approved_at=datetime.utcnow(),
                approved_by_customer_id=u.id,
            )
        )
    db.commit()

    with pytest.raises(LicenseError) as ei:
        assert_service_vehicle_link_quota(db, service_customer_id=int(svc.id))
    assert ei.value.code == "SERVICE_FREE_VEHICLE_LINKS_EXCEEDED"


def test_service_free_invoice_monthly_quota_blocks(db_session):
    db = db_session
    t, svc = _seed_service_tenant_free(db, key_suffix="inv")
    cust = Customer(tenant_id=t.id, email="cust-inv@ex.com", password_hash="x", name="C", role="user")
    db.add(cust)
    db.commit()
    db.refresh(cust)
    v = Vehicle(tenant_id=t.id, user_email=cust.email, nickname="X", vin="TMB11111111111111")
    db.add(v)
    db.commit()
    db.refresh(v)
    for _ in range(3):
        db.add(
            ServiceInvoice(
                tenant_id=t.id,
                service_id=svc.id,
                customer_id=cust.id,
                vehicle_id=v.id,
                status="issued",
                subtotal=100.0,
                tax_total=21.0,
                total=121.0,
                issued_at=datetime.utcnow(),
            )
        )
    db.commit()

    with pytest.raises(LicenseError) as ei:
        assert_service_invoice_monthly_quota(db, service_customer_id=int(svc.id))
    assert ei.value.code == "SERVICE_FREE_MONTHLY_INVOICES_EXCEEDED"


def test_service_free_monthly_service_record_quota_blocks(db_session):
    db = db_session
    t, svc = _seed_service_tenant_free(db, key_suffix="sr")
    cust = Customer(tenant_id=t.id, email="c2-sr@ex.com", password_hash="x", name="C", role="user")
    db.add(cust)
    db.commit()
    db.refresh(cust)
    v = Vehicle(tenant_id=t.id, user_email=cust.email, nickname="Y", vin="TMB22222222222222")
    db.add(v)
    db.commit()
    db.refresh(v)
    now = datetime.utcnow()
    for i in range(3):
        db.add(
            ServiceRecord(
                tenant_id=t.id,
                vehicle_id=v.id,
                description=f"r{i}",
                created_by_service_customer_id=svc.id,
                origin="service_workspace",
                performed_at=now,
                updated_at=now,
            )
        )
    db.commit()

    with pytest.raises(LicenseError) as ei:
        assert_service_monthly_service_record_quota(db, service_customer_id=int(svc.id))
    assert ei.value.code == "SERVICE_FREE_MONTHLY_SERVICE_RECORDS_EXCEEDED"


def test_user_free_second_vehicle_quota(db_session):
    db = db_session
    t = Tenant(name="U", license_key="lic-uf", workspace_route_kind="user", workspace_slug="uslug1")
    db.add(t)
    db.commit()
    db.refresh(t)
    lic = License(tenant_id=t.id, plan="free", status="active", vehicles_limit=1, valid_from=datetime.utcnow())
    db.add(lic)
    u = Customer(tenant_id=t.id, email="owner-uf@ex.com", password_hash="x", name="O", role="user")
    db.add(u)
    db.commit()
    db.refresh(u)
    db.add(
        Vehicle(
            tenant_id=t.id,
            user_email=u.email,
            nickname="First",
            stk_valid_until=date.today(),
        )
    )
    db.commit()

    with pytest.raises(LicenseError) as ei:
        assert_vehicle_quota(db, int(t.id))
    assert ei.value.code == "LICENSE_QUOTA_EXCEEDED"
