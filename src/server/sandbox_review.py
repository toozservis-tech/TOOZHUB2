"""Dedicated, synthetic-only API for App Review and TestFlight.

Run in a separate service/process/disk with its own JWT secret. Production does
not import this module. Real controllers, quotas and Apple signature validation
are used; no paid plan is fabricated and no customer database is copied.
"""
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from pathlib import Path
import asyncio
import os
import secrets

from .sandbox_config import validate_sandbox_config

_root = Path(__file__).resolve().parents[2]
_data_root = validate_sandbox_config(os.environ, _root)
os.umask(0o077)
_data_root.mkdir(parents=True, exist_ok=True, mode=0o700)
(_data_root / "files").mkdir(exist_ok=True, mode=0o700)
os.environ["ENVIRONMENT"] = "production"
for _flag in ("ENABLE_IP_GEOLOOKUP", "ENABLE_BROWSER_GEOLOCATION_OVERRIDE", "ENABLE_REVERSE_GEOCODE"):
    os.environ[_flag] = "0"

# All application imports follow validation of the database destination.
from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import event, inspect, text
from src.core.security_middleware import SecurityHeadersMiddleware, RateLimitMiddleware
from src.modules.vehicle_hub.database import Base, SessionLocal, engine, get_db
from src.modules.vehicle_hub.models import Customer, Tenant, License, Vehicle, ServiceRecord
from src.modules.vehicle_hub.ownership import ensure_vehicle_owner_assignment
from src.modules.vehicle_hub.routers_v1.auth import get_current_user
from src.modules.vehicle_hub.routers_v1 import (
    apple_billing, vehicles, vehicle_archives, service_records, analytics,
    reminder_settings, reminders, repair_photos, reservations, services,
    service_workspace, capabilities, vin_lookup, ares_lookup,
)
from src.server.routers import user_auth, user_account, user_security
from src.modules.licensing.service import get_license_status
from src.modules.licensing.apple_reconciliation import reconcile_subscriptions, interval_seconds
from src.modules.licensing import apple_store
from src.modules.vehicle_hub import account_erasure  # Register lifecycle tables before create_all.
from src.core import file_erasure

# Configuration errors must fail deployment instead of silently disabling IAP.
apple_store.config()


@event.listens_for(engine, "connect")
def _configure_sandbox_database(connection, record):
    cursor = connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=10000")
        cursor.execute("PRAGMA journal_mode=WAL")
    finally:
        cursor.close()


def initialize_fixture():
    """Create once; restarts must never reset purchases or revive erased accounts."""
    tables = set(inspect(engine).get_table_names())
    if tables and "sandbox_fixture_marker" not in tables:
        raise RuntimeError("Refusing a database not created by this isolated Sandbox service.")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE IF NOT EXISTS sandbox_fixture_marker (version INTEGER PRIMARY KEY)"))
    with SessionLocal() as db:
        if db.execute(text("SELECT version FROM sandbox_fixture_marker")).first():
            # Only the two fixture identities may ever exist in this database.
            if any(c.email not in {"sandbox-1@example.com", "sandbox-2@example.com"}
                   or c.role != "user" or c.id != c.tenant_id
                   for c in db.query(Customer).all()):
                raise RuntimeError("Unexpected identity in the synthetic Sandbox database.")
            return
        if db.query(Customer).count() or db.query(Tenant).count():
            raise RuntimeError("Refusing to seed a non-empty Sandbox database.")
        for number in (1, 2):
            db.add(Tenant(id=number, name=f"Sandbox {number}", license_key=secrets.token_hex(24)))
            db.flush()
            customer = Customer(id=number, tenant_id=number, name=f"Testovací účet {number}",
                                email=f"sandbox-{number}@example.com", role="user",
                                password_hash=os.environ[f"SANDBOX_CUSTOMER_{number}_PASSWORD_HASH"],
                                notify_email=False, notify_sms=False)
            db.add(customer)
            db.add(License(tenant_id=number, plan="free", status="active", vehicles_limit=1))
            db.flush()
            vehicle = Vehicle(tenant_id=number, user_email=customer.email,
                              nickname="Ukázkové vozidlo", brand="Ukázka", model="Sandbox")
            db.add(vehicle)
            db.flush()
            ensure_vehicle_owner_assignment(db, vehicle=vehicle, owner=customer)
            db.add(ServiceRecord(tenant_id=number, vehicle_id=vehicle.id, user_id=number,
                                 description="Ukázková výměna oleje", category="OLEJ", price=1200,
                                 performed_at=datetime(2026, 1, 1)))
        db.execute(text("INSERT INTO sandbox_fixture_marker (version) VALUES (1)"))
        db.commit()


async def _reconcile():
    while True:
        await asyncio.sleep(interval_seconds())
        try:
            await asyncio.to_thread(reconcile_subscriptions)
        except Exception:
            # Never log JWS, signing material, personal identifiers or upstream responses.
            print("[SANDBOX] Apple reconciliation unavailable; retry scheduled.")


async def _remove_erased_files():
    while True:
        try:
            await asyncio.to_thread(file_erasure.process_file_erasures)
        except Exception:
            print("[SANDBOX] Private file cleanup unavailable; retry scheduled.")
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(app):
    tasks = [asyncio.create_task(_reconcile()), asyncio.create_task(_remove_erased_files())]
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task


initialize_fixture()
app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.include_router(apple_billing.router, prefix="/api/v1/license")
for feature_router in (vehicles.router, vehicle_archives.router, service_records.router,
                       analytics.router, reminder_settings.router, reminders.router,
                       repair_photos.router, reservations.router, services.router,
                       service_workspace.router, capabilities.router, vin_lookup.router,
                       ares_lookup.router):
    app.include_router(feature_router, prefix="/api/v1")
app.include_router(user_auth.router)
app.include_router(user_account.router)
app.include_router(user_security.router)


@app.middleware("http")
async def isolate_public_surface(request, call_next):
    # Reviewer/test accounts are provisioned separately; no public registration,
    # outgoing recovery messages, admin console, real payments or push enrollment.
    blocked = {"/user/register", "/user/register/service-request", "/user/forgot-password",
               "/user/request-password-reset", "/user/reset-password",
               "/user/email-verification/resend"}
    path = request.url.path
    if path in blocked or path.startswith(("/admin", "/web_admin", "/api/v1/push")):
        return JSONResponse(status_code=404, content={"detail": "V testovacím prostředí není tato akce dostupná."})
    try:
        response = await call_next(request)
    except Exception as exc:
        from src.core.private_errors import report_exception
        reference = report_exception(exc)
        return JSONResponse(status_code=500, content={"detail": "Testovací požadavek se nepodařilo dokončit.",
                                                     "incident_id": reference},
                            headers={"Cache-Control": "no-store"})
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-SpravaVozidel-Environment"] = "Sandbox"
    return response


@app.get("/health")
def health():
    return {"status": "ok", "environment": "Sandbox", "synthetic_data_only": True}


@app.get("/api/v1/license/status")
def license_status(user=Depends(get_current_user), db=Depends(get_db)):
    return get_license_status(db, user.tenant_id, user.email)


@app.get("/api/v1/system-notifications")
def notifications(user=Depends(get_current_user)):
    return {"items": [], "count": 0}
