from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import (
    Customer,
    ServiceCustomerLink,
    ServiceQuote,
    Tenant,
    Vehicle,
    VehicleOwnership,
    VehicleServiceLink,
)
from src.modules.vehicle_hub.routers_v1 import service_invoices as invoice_router


def test_create_service_invoice_from_quote_and_issue_notifies_owner(tmp_path: Path) -> None:
    db_path = tmp_path / "service_invoice_from_quote.sqlite"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        tenant = Tenant(name="Invoice Quote Tenant", license_key="invoice-quote-key")
        db.add(tenant)
        db.commit()
        db.refresh(tenant)

        owner = Customer(
            tenant_id=tenant.id,
            email="owner.invoice@example.com",
            password_hash="hash-owner",
            role="user",
            name="Klient Faktura",
        )
        service = Customer(
            tenant_id=tenant.id,
            email="service.invoice@example.com",
            password_hash="hash-service",
            role="service",
            name="Servis Faktura",
        )
        db.add_all([owner, service])
        db.commit()
        db.refresh(owner)
        db.refresh(service)

        vehicle = Vehicle(
            tenant_id=tenant.id,
            user_email=owner.email,
            nickname="Octavia Faktura",
            brand="Skoda",
            model="Octavia",
            vin="TMBINVOICEQUOTE123",
            plate="4AB1234",
            stk_valid_until=date.today(),
        )
        db.add(vehicle)
        db.flush()
        db.add(
            VehicleOwnership(
                tenant_id=tenant.id,
                vehicle_id=vehicle.id,
                customer_id=owner.id,
                ownership_type="owner",
                is_primary=True,
                is_active=True,
                assigned_by_customer_id=owner.id,
                assigned_at=datetime.utcnow(),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
        )
        db.add(
            ServiceCustomerLink(
                service_tenant_id=service.tenant_id,
                service_customer_id=service.id,
                customer_tenant_id=owner.tenant_id,
                customer_id=owner.id,
                status="active",
                note="invoice from quote",
            )
        )
        db.add(
            VehicleServiceLink(
                tenant_id=tenant.id,
                service_customer_id=service.id,
                owner_customer_id=owner.id,
                vehicle_id=vehicle.id,
                source_type="manual_test",
                status="approved",
                approved_at=datetime.utcnow(),
                approved_by_customer_id=owner.id,
            )
        )
        db.flush()

        quote = ServiceQuote(
            tenant_id=tenant.id,
            vehicle_id=vehicle.id,
            customer_id=owner.id,
            service_id=service.id,
            items_json='[{"name":"Diagnostika","quantity":1,"unit_price":1500,"total_price":1500},{"name":"Práce","quantity":2,"unit_price":750,"total_price":1500}]',
            total_price=3000,
            status="approved",
        )
        db.add(quote)
        db.commit()
        db.refresh(quote)

        created = invoice_router.create_service_invoice_from_quote(
            quote_id=quote.id,
            current_user=service,
            db=db,
        )

        assert created["status"] == "draft"
        assert created["customer_id"] == owner.id
        assert created["vehicle_id"] == vehicle.id
        assert created["extra"]["source_quote_id"] == quote.id
        assert len(created["lines"]) == 2
        assert round(float(created["total"]), 2) == 3630.0

        same = invoice_router.create_service_invoice_from_quote(
            quote_id=quote.id,
            current_user=service,
            db=db,
        )
        assert same["id"] == created["id"]

        issued = invoice_router.issue_service_invoice(
            invoice_id=int(created["id"]),
            current_user=service,
            db=db,
        )
        assert issued["status"] == "issued"
        assert issued["invoice_number"].startswith("FV-")

        notification = db.execute(
            text(
                "SELECT title, message FROM system_notifications WHERE target_type = 'user' AND target_value = :target ORDER BY id DESC LIMIT 1"
            ),
            {"target": str(owner.id)},
        ).fetchone()
        assert notification is not None
        assert "vystavil fakturu" in (notification[1] or "").lower()
    finally:
        db.close()
        engine.dispose()
