"""Kvóty SERVICE FREE vs FULL — přímé volání licenční vrstvy (SQLite in-memory)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.licensing.service import (
    LicenseError,
    activate_initial_user_trial,
    assert_service_customer_link_quota,
    assert_service_invoice_monthly_quota,
    assert_service_monthly_service_record_quota,
    assert_service_vehicle_link_quota,
    assert_vehicle_quota,
    get_license_status,
    upgrade_license_plan,
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


def test_first_login_activates_user_premium_trial(db_session):
    db = db_session
    t = Tenant(name="Trial", license_key="lic-trial", workspace_route_kind="user", workspace_slug="trial-user")
    db.add(t)
    db.commit()
    db.refresh(t)
    u = Customer(tenant_id=t.id, email="trial@example.com", password_hash="x", name="Trial", role="user")
    db.add(u)
    db.commit()
    db.refresh(u)
    lic = License(tenant_id=t.id, plan="free", status="active", vehicles_limit=1, valid_from=datetime.utcnow())
    db.add(lic)
    db.commit()

    start = datetime(2026, 5, 21, 10, 0, 0)
    trial = activate_initial_user_trial(db, u, now=start)
    db.commit()

    assert trial is not None
    assert trial.plan == "premium"
    assert trial.vehicles_limit == 0
    assert trial.valid_from == start
    assert trial.valid_to == start + timedelta(days=30)
    status = get_license_status(db, int(t.id), u.email)
    assert status["plan"] == "premium"
    assert status["trial_active"] is True
    assert status["is_expired_trial"] is False


def test_expired_user_trial_behaves_as_free_without_data_loss(db_session):
    db = db_session
    t = Tenant(name="Expired Trial", license_key="lic-expired-trial", workspace_route_kind="user", workspace_slug="expired-trial")
    db.add(t)
    db.commit()
    db.refresh(t)
    u = Customer(tenant_id=t.id, email="expired-trial@example.com", password_hash="x", name="Trial", role="user")
    db.add(u)
    db.commit()
    db.refresh(u)
    db.add(
        License(
            tenant_id=t.id,
            plan="premium",
            status="active",
            vehicles_limit=0,
            valid_from=datetime.utcnow() - timedelta(days=40),
            valid_to=datetime.utcnow() - timedelta(days=1),
        )
    )
    for i in range(2):
        db.add(
            Vehicle(
                tenant_id=t.id,
                user_email=u.email,
                nickname=f"Kept {i}",
                vin=f"TRIAL{i:012d}"[:17],
            )
        )
    db.commit()

    status = get_license_status(db, int(t.id), u.email)
    assert status["stored_plan"] == "premium"
    assert status["plan"] == "free"
    assert status["is_expired_trial"] is True
    assert status["vehicles_current"] == 2
    assert status["is_over_limit"] is True

    with pytest.raises(LicenseError) as ei:
        assert_vehicle_quota(db, int(t.id))
    assert ei.value.code == "LICENSE_QUOTA_EXCEEDED"
    assert ei.value.details["plan"] == "free"


def test_paid_upgrade_clears_expired_trial_valid_to(db_session):
    db = db_session
    t = Tenant(name="Paid After Trial", license_key="lic-paid-after-trial", workspace_route_kind="user", workspace_slug="paid-after-trial")
    db.add(t)
    db.commit()
    db.refresh(t)
    u = Customer(tenant_id=t.id, email="paid-after-trial@example.com", password_hash="x", name="Paid", role="user")
    db.add(u)
    db.commit()
    db.refresh(u)
    expired_at = datetime.utcnow() - timedelta(days=1)
    db.add(
        License(
            tenant_id=t.id,
            plan="premium",
            status="active",
            vehicles_limit=0,
            valid_from=datetime.utcnow() - timedelta(days=40),
            valid_to=expired_at,
        )
    )
    db.commit()

    upgrade_license_plan(db, int(t.id), "premium")
    status = get_license_status(db, int(t.id), u.email)

    lic = db.query(License).filter(License.tenant_id == int(t.id)).first()
    assert lic.valid_to is None
    assert status["plan"] == "premium"
    assert status["trial_active"] is False
    assert status["is_expired_trial"] is False
