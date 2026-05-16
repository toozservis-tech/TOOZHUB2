#!/usr/bin/env python3
"""
Založí nebo obnoví ukázkový zákaznický účet s prémiovou licencí, vozidlem a ilustračními záznamy.

Údaje v datech jsou záměrně obecné (žádné reálné servisy, postupy ani citlivé know-how).

Použití:
  cd /opt/toozhub2/app
  export SPRAVA_VOZIDEL_DEMO_ACCOUNT_EMAIL=demo@example.com
  export SPRAVA_VOZIDEL_DEMO_ACCOUNT_PASSWORD='bezpecne-heslo'
  python3 scripts/seed_demo_account.py

Volitelně lze zadat argumenty místo ENV (ENV má přednost, pokud je vyplněné).
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from sqlalchemy import func

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.env_aliases import env_prefer_new  # noqa: E402
from src.core.security import hash_password  # noqa: E402
from src.modules.licensing.service import upgrade_license_plan  # noqa: E402
from src.modules.vehicle_hub.customer_ordinal import assign_admin_ordinal_if_missing  # noqa: E402
from src.modules.vehicle_hub.database import DB_URL, SessionLocal  # noqa: E402
from src.modules.vehicle_hub.models import (  # noqa: E402
    Customer,
    CustomerSecuritySettings,
    Reminder,
    ServiceRecord,
    Vehicle,
)
from src.modules.vehicle_hub.ownership import ensure_vehicle_owner_assignment  # noqa: E402
from src.modules.vehicle_hub.tenant_provisioning import (  # noqa: E402
    create_dedicated_tenant,
    ensure_default_license_for_tenant,
)

# Platný testovací VIN (ISO 3779) — běžně používaný vzor, neodkazuje na konkrétní vůz zákazníka.
DEMO_VIN = "1HGBH41JXMN109186"
DEMO_VEHICLE_TAG = "[sprava-vozidel-demo-seed]"


def _env_email_password(cli_email: str | None, cli_password: str | None) -> tuple[str, str]:
    email = (env_prefer_new("SPRAVA_VOZIDEL_DEMO_ACCOUNT_EMAIL", "TOOZHUB_DEMO_ACCOUNT_EMAIL") or "").strip()
    password = env_prefer_new("SPRAVA_VOZIDEL_DEMO_ACCOUNT_PASSWORD", "TOOZHUB_DEMO_ACCOUNT_PASSWORD") or ""
    if cli_email:
        email = cli_email.strip().lower()
    if cli_password is not None:
        password = cli_password
    return email, password


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _demo_vehicle_notes() -> str:
    return (
        f"{DEMO_VEHICLE_TAG}\n"
        "Ukázkové vozidlo: údaje slouží jen k předvedení funkcí aplikace, nejedná se o reálný provoz."
    )


def _ensure_customer(db, *, email: str, password: str, display_name: str) -> Customer:
    normalized = _normalize_email(email)
    existing = db.query(Customer).filter(func.lower(Customer.email) == normalized).first()
    pwd_hash = hash_password(password)

    if existing:
        existing.password_hash = pwd_hash
        existing.name = display_name
        existing.role = "user"
        existing.is_deleted = False
        existing.is_disabled = False
        existing.account_status = "active"
        existing.email_verified_at = existing.email_verified_at or datetime.utcnow()
        assign_admin_ordinal_if_missing(db, existing)
        db.flush()
        return existing

    tenant = create_dedicated_tenant(db, owner_email=normalized, owner_name=display_name)
    now = datetime.utcnow()
    customer = Customer(
        tenant_id=tenant.id,
        email=normalized,
        password_hash=pwd_hash,
        name=display_name,
        role="user",
        account_status="active",
        email_verified_at=now,
    )
    db.add(customer)
    db.flush()
    assign_admin_ordinal_if_missing(db, customer)
    ensure_default_license_for_tenant(db, customer.tenant_id)
    return customer


def _disable_2fa(db, customer: Customer) -> None:
    row = (
        db.query(CustomerSecuritySettings)
        .filter(CustomerSecuritySettings.customer_id == int(customer.id))
        .first()
    )
    if row is None:
        return
    row.two_factor_enabled = False
    row.totp_secret = None
    row.totp_enabled_at = None


def _ensure_demo_vehicle(db, customer: Customer) -> Vehicle:
    tid = int(customer.tenant_id)
    email = customer.email
    vehicle = (
        db.query(Vehicle)
        .filter(
            Vehicle.tenant_id == tid,
            Vehicle.vin == DEMO_VIN,
        )
        .first()
    )
    today = date.today()
    stk_until = today + timedelta(days=85)
    ins_until = today + timedelta(days=200)

    if vehicle is None:
        vehicle = Vehicle(
            tenant_id=tid,
            user_email=email,
            nickname="Ukázkové vozidlo",
            brand="Obecný výrobce",
            model="Ukázkový model",
            year=2019,
            fuel="Nafta",
            engine="2,0 l (ilustrační údaj)",
            vin=DEMO_VIN,
            plate="DEMO 0001",
            stk_valid_until=stk_until,
            current_mileage_km=125_400,
            insurance_provider="Ilustrační pojišťovna",
            insurance_valid_until=ins_until,
            tyres_info="Letní sada – obecný popis, bez specifikace skutečného dezénu.",
            notes=_demo_vehicle_notes(),
        )
        db.add(vehicle)
        db.flush()
        ensure_vehicle_owner_assignment(
            db,
            vehicle=vehicle,
            owner=customer,
            assigned_by_customer_id=int(customer.id),
        )
        return vehicle

    vehicle.user_email = email
    vehicle.nickname = "Ukázkové vozidlo"
    vehicle.brand = "Obecný výrobce"
    vehicle.model = "Ukázkový model"
    vehicle.year = 2019
    vehicle.fuel = "Nafta"
    vehicle.engine = "2,0 l (ilustrační údaj)"
    vehicle.plate = "DEMO 0001"
    vehicle.stk_valid_until = stk_until
    vehicle.current_mileage_km = 125_400
    vehicle.insurance_provider = "Ilustrační pojišťovna"
    vehicle.insurance_valid_until = ins_until
    vehicle.tyres_info = "Letní sada – obecný popis, bez specifikace skutečného dezénu."
    vehicle.notes = _demo_vehicle_notes()
    vehicle.status = "active"
    db.flush()
    ensure_vehicle_owner_assignment(
        db,
        vehicle=vehicle,
        owner=customer,
        assigned_by_customer_id=int(customer.id),
    )
    return vehicle


def _seed_service_records(db, customer: Customer, vehicle: Vehicle) -> None:
    tid = int(customer.tenant_id)
    vid = int(vehicle.id)
    cid = int(customer.id)
    existing = db.query(ServiceRecord).filter(ServiceRecord.vehicle_id == vid).count()
    if existing >= 2:
        return

    now = datetime.utcnow()
    samples = [
        {
            "performed_at": now - timedelta(days=160),
            "mileage": 120_100,
            "description": "Pravidelná údržba – výměna provozních kapalin (ukázkový záznam)",
            "category": "Pravidelná údržba",
            "price": 4200.0,
            "total_price": 5082.0,
            "note": "Částky a popis jsou ilustrační; nejedná se o reálnou fakturu ani postup konkrétního servisu.",
            "record_status": "approved",
        },
        {
            "performed_at": now - timedelta(days=380),
            "mileage": 112_800,
            "description": "Kontrola brzdového systému – výměna součástí (ukázkový záznam)",
            "category": "Oprava",
            "price": 8900.0,
            "total_price": 10_769.0,
            "note": "Technické detaily záměrně obecné; slouží jen k ukázce evidence zásahů.",
            "record_status": "approved",
        },
    ]

    for row in samples:
        rec = ServiceRecord(
            tenant_id=tid,
            vehicle_id=vid,
            user_id=cid,
            customer_id=cid,
            performed_at=row["performed_at"],
            mileage=row["mileage"],
            description=row["description"],
            category=row["category"],
            price=row["price"],
            total_price=row["total_price"],
            note=row["note"],
            record_status=row["record_status"],
            origin="user_manual",
            visibility_scope="full_current_owner",
        )
        db.add(rec)


def _seed_reminders(db, customer: Customer, vehicle: Vehicle) -> None:
    tid = int(customer.tenant_id)
    vid = int(vehicle.id)
    cid = int(customer.id)
    if db.query(Reminder).filter(Reminder.customer_id == cid, Reminder.vehicle_id == vid).count() >= 1:
        return
    today = date.today()
    db.add(
        Reminder(
            tenant_id=tid,
            customer_id=cid,
            vehicle_id=vid,
            type="STK",
            text="Blíží se termín kontroly STK (ukázková připomínka).",
            due_date=today + timedelta(days=75),
            is_manual=True,
            is_completed=False,
        )
    )
    db.add(
        Reminder(
            tenant_id=tid,
            customer_id=cid,
            vehicle_id=vid,
            type="OLEJ",
            text="Plánovaná výměna oleje dle servisního intervalu (ukázka).",
            due_date=today + timedelta(days=120),
            is_manual=True,
            is_completed=False,
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed ukázkového účtu Správa vozidel")
    parser.add_argument("--email", help="Email účtu (jinak ENV)")
    parser.add_argument("--password", help="Heslo (jinak ENV)")
    parser.add_argument(
        "--name",
        default="Ukázkový uživatel",
        help="Zobrazované jméno",
    )
    args = parser.parse_args()

    email, password = _env_email_password(args.email, args.password)
    if not email or not password:
        print(
            "ERROR: Nastavte SPRAVA_VOZIDEL_DEMO_ACCOUNT_EMAIL a SPRAVA_VOZIDEL_DEMO_ACCOUNT_PASSWORD "
            "nebo použijte --email a --password.",
            file=sys.stderr,
        )
        return 1
    if len(password) < 6:
        print("ERROR: Heslo musí mít alespoň 6 znaků.", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        customer = _ensure_customer(db, email=email, password=password, display_name=args.name)
        upgrade_license_plan(db, int(customer.tenant_id), "premium")
        _disable_2fa(db, customer)
        vehicle = _ensure_demo_vehicle(db, customer)
        _seed_service_records(db, customer, vehicle)
        _seed_reminders(db, customer, vehicle)
        db.commit()
        print(
            f"OK: Ukázkový účet připraven (email={customer.email}, tenant_id={customer.tenant_id}, "
            f"vehicle_id={vehicle.id}, db={DB_URL}).\n"
            "Pro zobrazení tlačítka na přihlášení nastavte také SPRAVA_VOZIDEL_PUBLIC_DEMO_CREDENTIALS=1."
        )
        return 0
    except Exception as exc:
        db.rollback()
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
