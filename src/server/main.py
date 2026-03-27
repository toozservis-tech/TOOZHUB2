"""
Backend server pro TooZ Hub 2
Poskytuje API pro autentizaci, správu uživatelů a vozidel
"""

import sys
import os
import asyncio
import base64
import hashlib
import hmac
import json
import secrets
import struct
import shutil
import tempfile
import time
import unicodedata
import zipfile
from pathlib import Path
from urllib.parse import quote

# Přidání kořenového adresáře projektu do Python path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from fastapi import FastAPI, HTTPException, Depends, Request, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.background import BackgroundTask
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime, date, timedelta
from sqlalchemy import func, or_

from src.core.config import (
    ALLOWED_ORIGINS,
    ENVIRONMENT,
    HOST,
    PORT,
    JWT_SECRET_KEY,
    ENABLE_AI_FEATURES,
    ENABLE_CUSTOMER_COMMANDS,
    ENABLE_AUTOPILOT_API,
)
from src.core.security import (
    hash_password, 
    verify_password, 
    needs_rehash,
    create_access_token, 
    decode_access_token
)
from src.core.auth import get_current_user_email, security
from src.modules.vehicle_hub.database import SessionLocal, engine
from src.modules.vehicle_hub.models import (
    BotCommand,
    CustomerCommand,
    Customer,
    CustomerSecuritySettings,
    EmailNotificationLog,
    Instance,
    License,
    PushSubscription,
    Reminder as ReminderModel,
    Reservation as ReservationModel,
    SecurityAccessLog,
    SecurityBlockedIp,
    ServiceCustomerInvite,
    ServiceCustomerLink,
    ServiceDocumentIngestion,
    ServiceIntake,
    ServiceRecord as ServiceRecordModel,
    ServiceRegistrationRequest,
    Tenant,
    Vehicle as VehicleModel,
)
from src.modules.vehicle_hub.account_state import (
    ensure_customer_account_state_schema,
    customer_is_deleted,
    customer_is_disabled,
    customer_session_version,
    touch_customer_last_login,
)
from src.modules.vehicle_hub.tenant_provisioning import (
    create_dedicated_tenant,
    ensure_default_license_for_tenant,
)
from src.modules.vehicle_hub.schema_management import get_capabilities
from src.modules.vehicle_hub.routers_v1.ares_lookup import lookup_ares as lookup_ares_v1
from src.modules.vehicle_hub.routers_v1.auth import get_current_user as get_v1_current_user
from src.server.security_tracking import extract_client_ip, log_security_event, log_user_activity
from src.server.runtime_settings import get_runtime_setting_bool
from src.server.control_center_jobs import is_job_paused
# decode_vin_api není již používán - VIN decode endpoint je v decoder routeru
# Vehicle Decoder Engine router
try:
    from src.modules.vehicle_hub.decoder.router import router as decoder_router
    DECODER_AVAILABLE = True
except ImportError as e:
    print(f"[SERVER] Warning: Vehicle Decoder Engine není dostupný: {e}")
    DECODER_AVAILABLE = False

# Import AI Features modely, aby se tabulky vytvořily (jen pokud jsou feature flags zapnuté)
if ENABLE_AI_FEATURES:
    try:
        from src.modules.ai_features.models import (
            UsageAnalytics,
            FeatureSuggestion,
            FeatureVote,
            FeatureFeedback,
            FeatureDependency,
            AutoImplementationLog
        )
        AI_FEATURES_AVAILABLE = True
    except ImportError as e:
        print(f"[SERVER] Warning: AI Features modely nejsou dostupné: {e}")
        AI_FEATURES_AVAILABLE = False
else:
    print("[SERVER] AI Features modely přeskočeny (ENABLE_AI_FEATURES=false)")
    AI_FEATURES_AVAILABLE = False

# BEZPEČNOST: Kontrola JWT_SECRET_KEY v produkci
if ENVIRONMENT == "production":
    default_secret = "toozhub2-dev-secret-key-change-in-production"
    if JWT_SECRET_KEY == default_secret:
        import sys
        print("[SERVER] ERROR: KRITICKA CHYBA BEZPECNOSTI!")
        print("[SERVER] V produkci musí být nastaven JWT_SECRET_KEY v .env souboru!")
        print("[SERVER] Výchozí hodnota není bezpečná.")
        print("[SERVER] Vygenerujte nový klíč pomocí: python -c \"import secrets; print(secrets.token_urlsafe(32))\"")
        sys.exit(1)
    else:
        print("[SERVER] OK: JWT_SECRET_KEY je nastaven (neni vychozi hodnota)")

# Validace konfigurace při startu
try:
    from src.core.config_validator import log_config_status
    config_valid, config_status, missing_keys = log_config_status()
    
    # V PROD: pokud chybí kritické klíče, upozornit (ale neukončit, pokud to není JWT)
    if ENVIRONMENT == "production" and not config_valid:
        if "JWT_SECRET_KEY" in missing_keys:
            import sys
            print("[SERVER] FATAL: Aplikace nemůže běžet bez JWT_SECRET_KEY v produkci!")
            sys.exit(1)
        else:
            print("[SERVER] WARNING: Některé klíče chybí, ale aplikace může běžet")
except Exception as e:
    print(f"[SERVER] WARNING: Chyba při validaci konfigurace: {e}")
    import traceback
    traceback.print_exc()

# Import version info
try:
    from VERSION import __version__, __version_name__, __build_date__, __update_info__
    APP_VERSION = __version__
    APP_VERSION_NAME = __version_name__
    BUILD_DATE = __build_date__
    UPDATE_INFO = __update_info__
except ImportError:
    # Fallback pokud VERSION.py neexistuje
    APP_VERSION = "2.1.0"
    APP_VERSION_NAME = "TOOZHUB2.1"
    BUILD_DATE = "2025-01-27"
    UPDATE_INFO = "Aktualizace s vizuálními úpravami a vylepšeními"

app = FastAPI(title="TooZ Hub 2 API", version=APP_VERSION)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


ENABLE_REMINDER_NOTIFICATION_WORKER = _env_bool("ENABLE_REMINDER_NOTIFICATION_WORKER", True)
try:
    REMINDER_NOTIFICATION_WORKER_INTERVAL_SEC = max(
        60,
        int(os.getenv("REMINDER_NOTIFICATION_WORKER_INTERVAL_SEC", "300")),
    )
except ValueError:
    REMINDER_NOTIFICATION_WORKER_INTERVAL_SEC = 300

ENABLE_LICENSE_SUBSCRIPTION_WORKER = _env_bool("ENABLE_LICENSE_SUBSCRIPTION_WORKER", True)
try:
    LICENSE_SUBSCRIPTION_WORKER_INTERVAL_SEC = max(
        300,
        int(os.getenv("LICENSE_SUBSCRIPTION_WORKER_INTERVAL_SEC", "3600")),
    )
except ValueError:
    LICENSE_SUBSCRIPTION_WORKER_INTERVAL_SEC = 3600

_reminder_notification_task: asyncio.Task | None = None
_license_subscription_task: asyncio.Task | None = None
ENABLE_FILE_BROWSER = _env_bool("ENABLE_FILE_BROWSER", False)

_pending_2fa_logins: dict[str, dict] = {}
TOTP_PERIOD_SECONDS = 30
TOTP_DIGITS = 6
TOTP_VERIFY_WINDOW_STEPS = 1
TOTP_LOGIN_CHALLENGE_TTL_SECONDS = 5 * 60
TOTP_ISSUER_NAME = "TooZ Hub 2"


def _cleanup_expired_2fa_challenges() -> None:
    now = time.time()
    expired_tokens = [
        token
        for token, payload in _pending_2fa_logins.items()
        if float(payload.get("expires_at", 0)) <= now
    ]
    for token in expired_tokens:
        _pending_2fa_logins.pop(token, None)


def _create_2fa_login_challenge(customer: Customer, expected_role: str | None = None) -> tuple[str, int]:
    _cleanup_expired_2fa_challenges()
    challenge_token = secrets.token_urlsafe(32)
    expires_at = time.time() + TOTP_LOGIN_CHALLENGE_TTL_SECONDS
    _pending_2fa_logins[challenge_token] = {
        "email": customer.email,
        "tenant_id": customer.tenant_id,
        "customer_id": customer.id,
        "expected_role": expected_role or "",
        "attempts": 0,
        "expires_at": expires_at,
    }
    return challenge_token, TOTP_LOGIN_CHALLENGE_TTL_SECONDS


def _normalize_totp_code(value: str | None) -> str:
    raw = str(value or "").strip()
    return "".join(ch for ch in raw if ch.isdigit())


def _generate_totp_secret() -> str:
    # RFC 4226/6238 kompatibilní 20-byte secret (Base32 bez "=")
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").replace("=", "")


def _decode_totp_secret(secret: str) -> bytes:
    normalized = "".join((secret or "").split()).upper()
    if not normalized:
        raise ValueError("TOTP secret je prázdný")
    padding = "=" * ((8 - len(normalized) % 8) % 8)
    return base64.b32decode(normalized + padding, casefold=True)


def _calculate_totp(secret: str, for_unix_time: int) -> str:
    key = _decode_totp_secret(secret)
    counter = int(for_unix_time // TOTP_PERIOD_SECONDS)
    counter_bytes = struct.pack(">Q", counter)
    digest = hmac.new(key, counter_bytes, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    truncated = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    code = truncated % (10 ** TOTP_DIGITS)
    return f"{code:0{TOTP_DIGITS}d}"


def _verify_totp(secret: str, code: str, now_ts: int | None = None) -> bool:
    normalized_code = _normalize_totp_code(code)
    if len(normalized_code) != TOTP_DIGITS:
        return False
    now_unix = int(now_ts if now_ts is not None else time.time())
    for step in range(-TOTP_VERIFY_WINDOW_STEPS, TOTP_VERIFY_WINDOW_STEPS + 1):
        ts = now_unix + (step * TOTP_PERIOD_SECONDS)
        expected = _calculate_totp(secret, ts)
        if hmac.compare_digest(expected, normalized_code):
            return True
    return False


def _build_totp_uri(secret: str, account_email: str) -> str:
    issuer_encoded = quote(TOTP_ISSUER_NAME)
    account_encoded = quote(f"{TOTP_ISSUER_NAME}:{account_email}")
    return (
        f"otpauth://totp/{account_encoded}"
        f"?secret={secret}&issuer={issuer_encoded}&algorithm=SHA1&digits={TOTP_DIGITS}&period={TOTP_PERIOD_SECONDS}"
    )


def _get_or_create_security_settings(db, customer: Customer) -> CustomerSecuritySettings:
    settings = (
        db.query(CustomerSecuritySettings)
        .filter(CustomerSecuritySettings.customer_id == customer.id)
        .first()
    )
    if settings:
        if settings.tenant_id != customer.tenant_id:
            settings.tenant_id = customer.tenant_id
            db.commit()
            db.refresh(settings)
        return settings

    settings = CustomerSecuritySettings(
        tenant_id=customer.tenant_id,
        customer_id=customer.id,
        two_factor_enabled=False,
        biometric_enabled=False,
        biometric_preferred=False,
    )
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return settings


async def _reminder_notification_worker() -> None:
    """
    Periodická serverová kontrola připomínek (email + push), aby notifikace
    fungovaly i bez otevřeného UI.
    """
    await asyncio.sleep(20)
    while True:
        db = SessionLocal()
        try:
            if is_job_paused("reminders.notification.check"):
                print("[REMINDERS_WORKER] paused by Developer Control Center")
            else:
                from src.modules.vehicle_hub.routers_v1.reminders import check_and_send_reminder_notifications

                result = check_and_send_reminder_notifications(db=db)
                print(
                    "[REMINDERS_WORKER] check done: "
                    f"sent={result.get('notifications_sent', 0)}, "
                    f"email={result.get('email_notifications_sent', 0)}, "
                    f"push={result.get('push_notifications_sent', 0)}, "
                    f"errors={result.get('errors', 0)}"
                )
        except Exception as exc:
            print(f"[REMINDERS_WORKER] check failed: {exc}")
        finally:
            db.close()

        await asyncio.sleep(REMINDER_NOTIFICATION_WORKER_INTERVAL_SEC)


async def _license_subscription_worker() -> None:
    """
    Periodické zpracování lifecycle předplatného licencí (renewal, grace, notifikace).
    """
    await asyncio.sleep(30)
    while True:
        db = SessionLocal()
        try:
            if is_job_paused("license.subscription.cycle"):
                print("[LICENSE_SUBSCRIPTION_WORKER] paused by Developer Control Center")
            else:
                from src.modules.vehicle_hub.routers_v1.license_status import process_license_subscription_jobs

                result = process_license_subscription_jobs(db=db)
                print(
                    "[LICENSE_SUBSCRIPTION_WORKER] cycle: "
                    f"renewal_success={result.get('renewal_success', 0)}, "
                    f"renewal_failed={result.get('renewal_failed', 0)}, "
                    f"downgraded_free={result.get('downgraded_free', 0)}, "
                    f"cancel_finalized={result.get('cancel_finalized', 0)}, "
                    f"notified={result.get('notified', 0)}, "
                    f"errors={result.get('errors', 0)}"
                )
        except Exception as exc:
            print(f"[LICENSE_SUBSCRIPTION_WORKER] cycle failed: {exc}")
        finally:
            db.close()

        await asyncio.sleep(LICENSE_SUBSCRIPTION_WORKER_INTERVAL_SEC)


@app.on_event("startup")
async def _start_background_workers() -> None:
    global _reminder_notification_task, _license_subscription_task
    db = SessionLocal()
    try:
        ensure_customer_account_state_schema(db)
        capabilities = get_capabilities(db)
        unavailable = [
            name
            for name, report in (capabilities.get("modules") or {}).items()
            if not report.get("available")
        ]
        if unavailable:
            print(f"[SCHEMA] WARNING: disabled modules until migrations run: {', '.join(unavailable)}")
        else:
            print("[SCHEMA] active modules verified")
        from src.modules.vehicle_hub.routers_v1.license_status import _ensure_subscription_schema

        if _ensure_subscription_schema(db, strict=False):
            print("[LICENSE_SUBSCRIPTION] schema check OK")
        else:
            print(
                "[LICENSE_SUBSCRIPTION] WARNING: missing subscription tables. "
                "Run: python3 scripts/migrate_database.py"
            )
    except Exception as exc:
        print(f"[LICENSE_SUBSCRIPTION] WARNING: schema check failed: {exc}")
    finally:
        db.close()

    if not ENABLE_REMINDER_NOTIFICATION_WORKER:
        print("[REMINDERS_WORKER] disabled (ENABLE_REMINDER_NOTIFICATION_WORKER=0)")
    elif _reminder_notification_task is None:
        _reminder_notification_task = asyncio.create_task(_reminder_notification_worker())
        print(
            "[REMINDERS_WORKER] started "
            f"(interval={REMINDER_NOTIFICATION_WORKER_INTERVAL_SEC}s)"
        )

    if not ENABLE_LICENSE_SUBSCRIPTION_WORKER:
        print("[LICENSE_SUBSCRIPTION_WORKER] disabled (ENABLE_LICENSE_SUBSCRIPTION_WORKER=0)")
    elif _license_subscription_task is None:
        _license_subscription_task = asyncio.create_task(_license_subscription_worker())
        print(
            "[LICENSE_SUBSCRIPTION_WORKER] started "
            f"(interval={LICENSE_SUBSCRIPTION_WORKER_INTERVAL_SEC}s)"
        )


@app.on_event("shutdown")
async def _stop_background_workers() -> None:
    global _reminder_notification_task, _license_subscription_task
    if _reminder_notification_task is None:
        pass
    else:
        _reminder_notification_task.cancel()
        try:
            await _reminder_notification_task
        except asyncio.CancelledError:
            pass
        finally:
            _reminder_notification_task = None
        print("[REMINDERS_WORKER] stopped")

    if _license_subscription_task is None:
        return
    _license_subscription_task.cancel()
    try:
        await _license_subscription_task
    except asyncio.CancelledError:
        pass
    finally:
        _license_subscription_task = None
    print("[LICENSE_SUBSCRIPTION_WORKER] stopped")

# =============================================================================
# GLOBÁLNÍ EXCEPTION HANDLER - ZABRÁNÍ PÁDŮM SERVERU
# =============================================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Globální handler pro všechny neošetřené výjimky.
    Zabraňuje pádu serveru a vrací chybovou odpověď.
    """
    import traceback
    
    # Logovat chybu
    error_traceback = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    print(f"[ERROR] Neošetřená výjimka: {type(exc).__name__}: {str(exc)}")
    print(f"[ERROR] Path: {request.url.path}")
    print(f"[ERROR] Method: {request.method}")
    print(f"[ERROR] Traceback:\n{error_traceback}")
    
    # Vrátit chybovou odpověď (nechat server běžet)
    from fastapi.responses import JSONResponse
    return JSONResponse(
        status_code=500,
        content={
            "detail": f"Interní chyba serveru: {str(exc)}",
            "type": type(exc).__name__,
            "path": request.url.path
        }
    )

# Security - použít z src.core.auth (definováno tam)

# Security Middleware - přidat před CORS
from src.core.security_middleware import (
    SecurityHeadersMiddleware,
    RateLimitMiddleware,
    AntiTamperingMiddleware
)
from src.core.rate_limiter import rate_limiter  # Globální instance pro rate limiting

# Security headers (nejdřív - aplikuje se na všechny odpovědi)
app.add_middleware(SecurityHeadersMiddleware)

# CORS middleware - MUSÍ být před rate limiting a auth (pro OPTIONS preflight)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  # Dynamicky z config.py (omezené v produkci, všechny v dev)
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
    allow_headers=["*", "Authorization", "Content-Type", "Accept"],
    expose_headers=["*"],
)

# Anti-tampering (detekce manipulace)
app.add_middleware(AntiTamperingMiddleware)

# Rate limiting (ochrana proti DDoS) - po CORS
app.add_middleware(RateLimitMiddleware, calls=100, period=60)


_MAINTENANCE_BYPASS_PREFIXES = (
    "/admin-api",
    "/web_admin",
    "/admin-static",
    "/health",
)
_MAINTENANCE_BYPASS_EXACT: set[str] = {
    "/version",
    "/version/history",
    "/user/login",
    "/user/login/2fa",
}
_MAINTENANCE_BYPASS_RUNTIME_PREFIXES = (
    "/api/v1/license/comgate/result",
)


def _is_maintenance_bypass_path(path: str) -> bool:
    path_lc = (path or "").lower()
    if path_lc in _MAINTENANCE_BYPASS_EXACT:
        return True
    if any(path_lc.startswith(prefix) for prefix in _MAINTENANCE_BYPASS_RUNTIME_PREFIXES):
        return True
    return any(path_lc.startswith(prefix) for prefix in _MAINTENANCE_BYPASS_PREFIXES)


@app.middleware("http")
async def maintenance_mode_middleware(request: Request, call_next):
    """
    Vynutí globální režim údržby z Developer Admin nastavení.
    /admin-api a /web_admin zůstávají dostupné, aby šlo režim vypnout.
    """
    maintenance_enabled = get_runtime_setting_bool("general", "maintenance_mode", False)
    if not maintenance_enabled:
        return await call_next(request)

    path = (request.url.path or "").lower()
    if _is_maintenance_bypass_path(path):
        return await call_next(request)

    retry_after_sec = "300"
    if path.startswith("/api/") or path.startswith("/user/"):
        response = JSONResponse(
            status_code=503,
            content={
                "detail": "Aplikace je dočasně v režimu údržby. Zkuste to prosím za několik minut.",
                "maintenance_mode": True,
            },
        )
    else:
        response = HTMLResponse(
            status_code=503,
            content=(
                "<!doctype html><html lang='cs'><head><meta charset='utf-8'>"
                "<meta name='viewport' content='width=device-width, initial-scale=1'>"
                "<title>TooZ Hub 2 - Údržba</title>"
                "<style>body{font-family:Arial,sans-serif;margin:0;background:#0f172a;color:#e2e8f0;}"
                ".wrap{min-height:100vh;display:flex;align-items:center;justify-content:center;padding:24px;}"
                ".card{max-width:680px;background:#1e293b;border:1px solid #334155;border-radius:16px;padding:28px;}"
                "h1{margin:0 0 10px;font-size:28px;}p{margin:0 0 8px;line-height:1.55;color:#cbd5e1;}"
                "</style></head><body><div class='wrap'><div class='card'>"
                "<h1>Aplikace je v režimu údržby</h1>"
                "<p>Probíhá aktualizace systému. Dočasně není možné aplikaci používat.</p>"
                "<p>Zkuste to prosím znovu za několik minut.</p>"
                "</div></div></body></html>"
            ),
        )

    response.headers["Retry-After"] = retry_after_sec
    return response


@app.middleware("http")
async def admin_assets_no_cache_middleware(request: Request, call_next):
    """
    Zabrání agresivnímu cachování frontendu v prohlížeči.
    Potřebujeme mít jistotu, že po nasazení se načte aktuální web/admin JS a CSS.
    """
    path = (request.url.path or "").lower()
    is_frontend_asset = (
        path.startswith("/web_admin")
        or path.startswith("/admin-static")
        or path == "/web"
        or path.startswith("/web/")
    )

    # U frontendu vypnout podmíněné requesty (If-None-Match/If-Modified-Since),
    # aby se po nasazení nenačítal zastaralý obsah přes 304.
    if is_frontend_asset:
        original_headers = request.scope.get("headers", [])
        filtered_headers = [
            (k, v)
            for (k, v) in original_headers
            if k.lower() not in (b"if-none-match", b"if-modified-since")
        ]
        if len(filtered_headers) != len(original_headers):
            scope = dict(request.scope)
            scope["headers"] = filtered_headers
            request = Request(scope, request.receive)

    response = await call_next(request)

    if is_frontend_asset:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        response.headers["Surrogate-Control"] = "no-store"
        # Starlette StaticFiles přidává ETag/Last-Modified; odstraníme je, aby
        # klient neposílal další conditional GET a neskončil na staré verzi.
        for header in ("etag", "last-modified"):
            if header in response.headers:
                del response.headers[header]
    return response

# Include Vehicle Decoder Engine router
if DECODER_AVAILABLE:
    app.include_router(decoder_router)
    print("[SERVER] Vehicle Decoder Engine router zaregistrován: /api/vehicles/decode-vin, /api/vehicles/decode-plate")

# Include File Browser router pouze při explicitním zapnutí
if ENABLE_FILE_BROWSER:
    try:
        from src.server.file_browser import router as file_browser_router
        app.include_router(file_browser_router)
        print("[SERVER] File Browser zaregistrován: /files/ (ENABLE_FILE_BROWSER=1)")
    except ImportError as e:
        print(f"[SERVER] Warning: File Browser není dostupný: {e}")
else:
    print("[SERVER] File Browser router přeskočen (ENABLE_FILE_BROWSER=false)")

# Include API v1 routery (TooZ Hub v1.0)
try:
    from src.modules.vehicle_hub.routers_v1 import api_router as v1_api_router
    app.include_router(v1_api_router)
    print("[SERVER] API v1 routery zaregistrovány: /api/v1/")
    
    # Diagnostika: Vypiš všechny routes v v1_api_router obsahující "license"
    license_routes_in_v1 = []
    for route in v1_api_router.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            if 'license' in route.path.lower():
                for method in sorted(route.methods):
                    if method in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']:
                        license_routes_in_v1.append(f"{method} {route.path}")
    
    if license_routes_in_v1:
        print(f"[SERVER] Found license routes in v1_api_router: {license_routes_in_v1}")
    else:
        print("[SERVER] WARNING: No license routes found in v1_api_router!")
        
    # Diagnostika: Vypiš všechny routes v app obsahující "license" PO registraci
    all_license_routes = []
    for route in app.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            if 'license' in route.path.lower():
                for method in sorted(route.methods):
                    if method in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']:
                        all_license_routes.append(f"{method} {route.path}")
    
    if all_license_routes:
        print(f"[SERVER] All license routes in app (after registration): {all_license_routes}")
        if any('/api/v1/license/status' in r for r in all_license_routes):
            print("[SERVER] ✓ /api/v1/license/status is registered in app")
        else:
            print("[SERVER] ❌ /api/v1/license/status NOT found in app routes!")
    else:
        print("[SERVER] ❌ No license routes found in app at all!")
        
except ImportError as e:
    print(f"[SERVER] Warning: API v1 routery nejsou dostupné: {e}")
    import traceback
    traceback.print_exc()

# Include Autopilot M2M API router
if ENABLE_AUTOPILOT_API:
    try:
        from src.modules.vehicle_hub.routers_v1.autopilot import router as autopilot_router
        app.include_router(autopilot_router)
        print("[SERVER] Autopilot M2M API router zaregistrován: /api/autopilot/")
    except ImportError as e:
        print(f"[SERVER] Warning: Autopilot M2M API router není dostupný: {e}")
        import traceback
        traceback.print_exc()
else:
    print("[SERVER] Autopilot M2M API router přeskočen (ENABLE_AUTOPILOT_API=false)")

# Include Customer Commands API router (Command Bot v1)
if ENABLE_CUSTOMER_COMMANDS:
    try:
        from src.modules.vehicle_hub.routers_v1.customer_commands import router as customer_commands_router
        app.include_router(customer_commands_router)
        print("[SERVER] Customer Commands API router zaregistrován: /api/customer-commands/")
    except ImportError as e:
        print(f"[SERVER] Warning: Customer Commands API router není dostupný: {e}")
        import traceback
        traceback.print_exc()
else:
    print("[SERVER] Customer Commands API router přeskočen (ENABLE_CUSTOMER_COMMANDS=false)")

# Include Admin API router
try:
    from src.server.admin_api import router as admin_api_router
    app.include_router(admin_api_router)
    print("[SERVER] Admin API router zaregistrován: /admin-api/")
except ImportError as e:
    print(f"[SERVER] Warning: Admin API router není dostupný: {e}")
    import traceback
    traceback.print_exc()

# Include Instances API router (multi-tenant)
try:
    from src.server.routers import instances
    app.include_router(instances.router)
    print("[SERVER] Instances API router zaregistrován: /api/instances/")
except ImportError as e:
    print(f"[SERVER] Warning: Instances API router není dostupný: {e}")
    import traceback
    traceback.print_exc()

# Include AI Features router (automatické navrhování funkcí)
if ENABLE_AI_FEATURES:
    try:
        from src.modules.ai_features.routers import router as ai_features_router
        app.include_router(ai_features_router)
        print("[SERVER] AI Features router zaregistrován: /api/v1/ai-features/")
    except ImportError as e:
        print(f"[SERVER] Warning: AI Features router není dostupný: {e}")
        import traceback
        traceback.print_exc()
else:
    print("[SERVER] AI Features router přeskočen (ENABLE_AI_FEATURES=false)")

# ============= MODELY =============

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    name: Optional[str] = None
    ico: Optional[str] = None
    dic: Optional[str] = None
    street: Optional[str] = None
    street_number: Optional[str] = None
    city: Optional[str] = None
    zip: Optional[str] = None
    phone: Optional[str] = None


class ServiceRegisterRequest(BaseModel):
    email: EmailStr
    password: str
    ico: str = Field(min_length=8, max_length=16)
    service_name: str = Field(min_length=2, max_length=200)
    responsible_person: str = Field(min_length=2, max_length=200)
    phone: str = Field(min_length=6, max_length=64)
    street: str = Field(min_length=2, max_length=200)
    street_number: Optional[str] = Field(default=None, max_length=64)
    city: str = Field(min_length=2, max_length=120)
    zip: str = Field(min_length=3, max_length=32)
    dic: Optional[str] = Field(default=None, max_length=64)
    registration_purpose: str = Field(min_length=10, max_length=2000)


class ServiceRegisterResponse(BaseModel):
    request_id: int
    status: str = "pending"
    message: str


class UserLogin(BaseModel):
    email: EmailStr
    password: str
    expected_role: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class LoginResponse(BaseModel):
    access_token: Optional[str] = None
    token_type: str = "bearer"
    user: Optional[dict] = None
    two_factor_required: bool = False
    challenge_token: Optional[str] = None
    challenge_expires_in: Optional[int] = None


class RegisterTokenResponse(TokenResponse):
    email_sent: bool = False
    registration_email_status: Optional[str] = None


class UserResponse(BaseModel):
    """Kompletní informace o uživateli"""
    id: int
    email: str
    name: Optional[str] = None
    ico: Optional[str] = None
    dic: Optional[str] = None
    street: Optional[str] = None
    street_number: Optional[str] = None
    city: Optional[str] = None
    zip: Optional[str] = None
    phone: Optional[str] = None
    notify_email: bool = True
    notify_sms: bool = False
    notify_stk: bool = True
    notify_oil: bool = True
    notify_general: bool = True
    role: str = "user"
    created_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class UserUpdate(BaseModel):
    """Model pro aktualizaci uživatelského profilu"""
    name: Optional[str] = None
    ico: Optional[str] = None
    dic: Optional[str] = None
    street: Optional[str] = None
    street_number: Optional[str] = None
    city: Optional[str] = None
    zip: Optional[str] = None
    phone: Optional[str] = None
    notify_email: Optional[bool] = None
    notify_sms: Optional[bool] = None
    notify_stk: Optional[bool] = None
    notify_oil: Optional[bool] = None
    notify_general: Optional[bool] = None


class ChangePasswordRequest(BaseModel):
    """Model pro změnu hesla"""
    current_password: str
    new_password: str


class DeleteAccountRequest(BaseModel):
    """Model pro nevratné smazání účtu."""
    current_password: str = Field(min_length=1, max_length=256)
    confirmation_text: str = Field(min_length=3, max_length=64)
    export_downloaded: bool = False


class DeleteAccountResponse(BaseModel):
    deleted: bool
    message: str
    deleted_counts: dict


class SupportContactRequest(BaseModel):
    """Model pro odeslání zprávy na podporu."""
    category: str = Field(default="obecné", max_length=64)
    subject: str = Field(min_length=3, max_length=180)
    message: str = Field(min_length=10, max_length=4000)
    phone: Optional[str] = Field(default=None, max_length=64)
    include_diagnostics: bool = True
    page_url: Optional[str] = Field(default=None, max_length=500)
    user_agent: Optional[str] = Field(default=None, max_length=600)


class TwoFactorLoginVerifyRequest(BaseModel):
    challenge_token: str = Field(min_length=16, max_length=256)
    code: str = Field(min_length=6, max_length=12)


class SecuritySettingsResponse(BaseModel):
    two_factor_enabled: bool
    totp_configured: bool
    biometric_enabled: bool
    biometric_preferred: bool


class TotpSetupResponse(BaseModel):
    secret: str
    otpauth_uri: str
    digits: int
    period_seconds: int
    message: str


class TotpEnableRequest(BaseModel):
    code: str = Field(min_length=6, max_length=12)


class TotpDisableRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    code: str = Field(min_length=6, max_length=12)


class BiometricSecurityPreferenceRequest(BaseModel):
    enabled: bool
    preferred: Optional[bool] = None


# Schémata pro vehicles, service records, reservations jsou nyní v src/modules/vehicle_hub/routers_v1/schemas.py
# (VehicleCreateV1, VehicleOutV1, ServiceRecordCreateV1, ServiceRecordOutV1, ReservationCreateV1, ReservationOutV1)
# VIN decode schémata jsou v src/modules/vehicle_hub/decoder/models.py
# Reminder schémata jsou v src/modules/vehicle_hub/routers_v1/schemas.py
# (ReminderOutV1, ReminderCreateV1, ReminderUpdateV1)


# ============= POMOCNÉ FUNKCE =============

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def normalize_email(email: str) -> str:
    """Normalizuje email pro porovnání nezávislé na velikosti písmen."""
    return email.strip().lower()


def get_customer_by_email(db, email: str):
    """Vrátí zákazníka podle emailu bez ohledu na velikost písmen."""
    ensure_customer_account_state_schema(db)
    normalized_email = normalize_email(email)
    return db.query(Customer).filter(func.lower(Customer.email) == normalized_email).first()


def get_active_ip_block(db, ip_address: Optional[str]) -> Optional[SecurityBlockedIp]:
    """Vrátí aktivní blokaci IP. Expirované blokace automaticky deaktivuje."""
    if not ip_address:
        return None

    now = datetime.utcnow()
    block = (
        db.query(SecurityBlockedIp)
        .filter(
            SecurityBlockedIp.ip_address == ip_address,
            SecurityBlockedIp.is_active.is_(True),
        )
        .order_by(SecurityBlockedIp.blocked_at.desc())
        .first()
    )
    if not block:
        return None

    if block.expires_at and block.expires_at <= now:
        block.is_active = False
        block.unblocked_at = now
        db.commit()
        return None

    return block


def normalize_ico(value: Optional[str]) -> Optional[str]:
    """Normalizuje IČO na 8 číslic nebo vrátí None."""
    if value is None:
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return digits or None


ACCOUNT_DELETE_CONFIRM_TOKENS = {
    "SMAZAT UCET",
    "DELETE ACCOUNT",
}


def _normalize_delete_confirmation(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = " ".join(normalized.strip().upper().split())
    return normalized


def _safe_filename(value: str, fallback: str, max_length: int = 80) -> str:
    raw = str(value or "").strip()
    if not raw:
        raw = fallback
    normalized = unicodedata.normalize("NFKD", raw)
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    normalized = "".join(ch if ch.isalnum() or ch in {"-", "_", " "} else "_" for ch in normalized)
    normalized = "_".join(normalized.split())
    normalized = normalized.strip("._")[:max_length]
    return normalized or fallback


def _serialize_export_value(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def _model_to_export_dict(row) -> dict:
    payload: dict = {}
    for column in row.__table__.columns:
        payload[column.name] = _serialize_export_value(getattr(row, column.name))
    return payload


def _build_vehicle_export_pdf(
    output_path: Path,
    *,
    customer: Customer,
    vehicle: VehicleModel,
    records: list[ServiceRecordModel],
    reminders: list[ReminderModel],
    reservations: list[ReservationModel],
) -> None:
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT, TA_CENTER
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except ImportError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Export PDF není dostupný (chybí reportlab): {exc}",
        ) from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=20 * mm,
        bottomMargin=16 * mm,
    )
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "ExportTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=colors.HexColor("#0f172a"),
        alignment=TA_CENTER,
        spaceAfter=6,
    )
    subtitle_style = ParagraphStyle(
        "ExportSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        textColor=colors.HexColor("#475569"),
        alignment=TA_CENTER,
        spaceAfter=14,
    )
    section_style = ParagraphStyle(
        "ExportSection",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        textColor=colors.HexColor("#1e293b"),
        alignment=TA_LEFT,
        spaceBefore=10,
        spaceAfter=6,
    )
    text_style = ParagraphStyle(
        "ExportText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#1e293b"),
    )

    def _fmt_dt(value) -> str:
        if not value:
            return "-"
        if isinstance(value, datetime):
            return value.strftime("%d.%m.%Y %H:%M")
        if isinstance(value, date):
            return value.strftime("%d.%m.%Y")
        return str(value)

    vehicle_name = vehicle.nickname or f"{vehicle.brand or ''} {vehicle.model or ''}".strip() or f"Vozidlo #{vehicle.id}"
    owner_text = customer.name or customer.email

    story = [
        Paragraph("TooZ Hub 2 • Export vozidla", title_style),
        Paragraph(
            f"Generováno {datetime.utcnow().strftime('%d.%m.%Y %H:%M UTC')} pro účet {customer.email}",
            subtitle_style,
        ),
        Paragraph("1) Identifikace vozidla", section_style),
    ]

    vehicle_table_data = [
        ["Název", vehicle_name],
        ["SPZ", vehicle.plate or "-"],
        ["VIN", vehicle.vin or "-"],
        ["Značka / Model", f"{vehicle.brand or '-'} / {vehicle.model or '-'}"],
        ["Rok výroby", str(vehicle.year) if vehicle.year else "-"],
        ["Motor", vehicle.engine or "-"],
        ["Platnost STK", _fmt_dt(vehicle.stk_valid_until)],
        ["Pojištění", vehicle.insurance_provider or "-"],
        ["Platnost pojištění", _fmt_dt(vehicle.insurance_valid_until)],
        ["Vlastník účtu", owner_text or "-"],
        ["Poznámky", vehicle.notes or "-"],
    ]
    vehicle_table = Table(vehicle_table_data, colWidths=[52 * mm, 120 * mm])
    vehicle_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f8fafc")),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#0f172a")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (1, 0), (1, -1), "Helvetica"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#dbe3ef")),
                ("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(vehicle_table)

    story.append(Paragraph("2) Servisní záznamy", section_style))
    if records:
        service_table_data = [["Datum", "Km", "Kategorie", "Popis", "Cena"]]
        for row in records:
            service_table_data.append(
                [
                    _fmt_dt(row.performed_at),
                    str(row.mileage) if row.mileage is not None else "-",
                    row.category or "-",
                    row.description or "-",
                    (f"{row.price:,.2f} CZK".replace(",", " ") if row.price is not None else "-"),
                ]
            )
        service_table = Table(service_table_data, colWidths=[28 * mm, 20 * mm, 26 * mm, 78 * mm, 26 * mm])
        service_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d1d9e6")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        story.append(service_table)
        for row in records:
            if row.note:
                story.append(Spacer(1, 2))
                story.append(Paragraph(f"Poznámka ({_fmt_dt(row.performed_at)}): {row.note}", text_style))
    else:
        story.append(Paragraph("U vozidla zatím nejsou evidovány žádné servisní záznamy.", text_style))

    story.append(Paragraph("3) Připomínky", section_style))
    if reminders:
        for reminder in reminders:
            reminder_text = (
                f"• [{reminder.type}] {reminder.text or '-'} "
                f"(termín: {_fmt_dt(reminder.due_date)}, metoda: {reminder.notification_method or 'globální'})"
            )
            story.append(Paragraph(reminder_text, text_style))
    else:
        story.append(Paragraph("K vozidlu nejsou přiřazeny žádné připomínky.", text_style))

    story.append(Paragraph("4) Rezervace", section_style))
    if reservations:
        for reservation in reservations:
            reservation_text = (
                f"• {reservation.service_type or 'Servis'} | "
                f"{_fmt_dt(reservation.start_datetime)} - {_fmt_dt(reservation.end_datetime)} | "
                f"stav: {reservation.status or '-'}"
            )
            story.append(Paragraph(reservation_text, text_style))
            if reservation.note:
                story.append(Paragraph(f"Poznámka: {reservation.note}", text_style))
    else:
        story.append(Paragraph("K vozidlu nejsou evidovány žádné rezervace.", text_style))

    doc.build(story)


def _bulk_delete(query) -> int:
    return int(query.delete(synchronize_session=False) or 0)


def _parse_email_targets(raw_value: str) -> list[str]:
    if not raw_value:
        return []
    targets: list[str] = []
    for part in str(raw_value).split(","):
        email = normalize_email(part)
        if email and "@" in email:
            targets.append(email)
    return targets


def get_registration_alert_recipients(db) -> list[str]:
    """
    Sestaví seznam příjemců notifikací o registraci.
    Priorita:
    1) ENV REGISTRATION_ALERT_EMAILS (CSV)
    2) ENV DEVELOPER_ALERT_EMAIL
    3) účty v DB s role developer_admin/admin
    """
    recipients: set[str] = set()

    recipients.update(_parse_email_targets(os.getenv("REGISTRATION_ALERT_EMAILS", "")))
    recipients.update(_parse_email_targets(os.getenv("DEVELOPER_ALERT_EMAIL", "")))

    admin_emails = (
        db.query(Customer.email)
        .filter(Customer.role.in_(["developer_admin", "admin"]))
        .all()
    )
    for row in admin_emails:
        email = normalize_email(row[0] if row else "")
        if email:
            recipients.add(email)

    return sorted(recipients)


def send_registration_alert_email(
    db,
    *,
    registration_type: str,
    account_email: str,
    account_name: Optional[str] = None,
    account_ico: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> dict:
    """
    Odešle notifikaci developerovi/adminovi o nové registraci.
    Selhání notifikace nesmí zablokovat registraci.
    """
    result = {
        "sent": False,
        "status": "skipped",
        "recipients": [],
        "error": None,
    }
    try:
        recipients = get_registration_alert_recipients(db)
        result["recipients"] = recipients
        if not recipients:
            result["status"] = "no_recipients"
            return result

        from src.modules.email_client.service import EmailService, EmailMessage

        email_service = EmailService()
        if not email_service.is_configured():
            result["status"] = "smtp_not_configured"
            return result

        now_utc = datetime.utcnow().strftime("%d.%m.%Y %H:%M:%S UTC")
        safe_name = (account_name or "").strip() or "-"
        safe_ico = normalize_ico(account_ico) or "-"
        safe_type = "servis" if str(registration_type).lower() == "service" else "uživatel"
        meta = metadata or {}

        detail_lines = []
        for key, value in meta.items():
            if value is None:
                continue
            detail_lines.append(f"- {key}: {value}")
        detail_block = "\n".join(detail_lines) if detail_lines else "- bez doplňujících údajů"

        subject = f"[TooZ Hub 2] Nová registrace ({safe_type})"
        body = f"""Byla vytvořena nová registrace v TooZ Hub 2.

Typ registrace: {safe_type}
Email účtu: {account_email}
Název/Jméno: {safe_name}
IČO: {safe_ico}
Čas: {now_utc}

Detaily:
{detail_block}
"""

        html_body = f"""
<html lang="cs">
<body style="font-family: Arial, sans-serif; line-height: 1.55; color: #1e293b;">
  <div style="max-width: 660px; margin: 0 auto; padding: 18px;">
    <h2 style="margin: 0 0 10px; color: #1d4ed8;">Nová registrace v TooZ Hub 2</h2>
    <p><strong>Typ registrace:</strong> {safe_type}</p>
    <p><strong>Email účtu:</strong> {account_email}<br>
       <strong>Název/Jméno:</strong> {safe_name}<br>
       <strong>IČO:</strong> {safe_ico}<br>
       <strong>Čas:</strong> {now_utc}</p>
    <p><strong>Detaily:</strong></p>
    <pre style="background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:10px; white-space:pre-wrap;">{detail_block}</pre>
  </div>
</body>
</html>
"""

        message = EmailMessage(
            to=recipients,
            subject=subject,
            body=body,
            html_body=html_body,
        )
        email_service.send_email(message)

        result["sent"] = True
        result["status"] = "sent"
        return result
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = str(exc)
        print(f"[REGISTER] Developer alert email selhal: {exc}")
        return result




# ============= AUTH ENDPOINTY =============

@app.post("/user/register", response_model=RegisterTokenResponse)
def register_user(user_data: UserRegister, db=Depends(get_db)):
    """Registrace nového uživatele"""
    normalized_email = normalize_email(user_data.email)
    normalized_ico = normalize_ico(user_data.ico)

    # Validace hesla
    if not user_data.password or len(user_data.password) < 6:
        raise HTTPException(status_code=400, detail="Heslo musí mít alespoň 6 znaků")
    
    # Zkontrolovat, zda uživatel s tímto emailem neexistuje
    existing = get_customer_by_email(db, normalized_email)
    if existing:
        raise HTTPException(status_code=400, detail="Uživatel s tímto emailem již existuje")
    
    # Vytvořit nového uživatele s bcrypt hashem
    try:
        hashed_password = hash_password(user_data.password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    
    # Každý nový uživatel dostane vlastní tenant (izolace dat a licence).
    dedicated_tenant = create_dedicated_tenant(
        db,
        owner_email=normalized_email,
        owner_name=user_data.name,
    )
    
    customer = Customer(
        tenant_id=dedicated_tenant.id,
        email=normalized_email,
        password_hash=hashed_password,
        name=user_data.name,
        ico=normalized_ico,
        dic=user_data.dic,
        street=user_data.street,
        street_number=user_data.street_number,
        city=user_data.city,
        zip=user_data.zip,
        phone=user_data.phone,
    )
    
    db.add(customer)
    db.commit()
    db.refresh(customer)

    # Vytvořit výchozí free licenci pro tenant.
    ensure_default_license_for_tenant(db, dedicated_tenant.id)

    # Odeslat potvrzovací email (neblokující - registrace musí projít i bez SMTP)
    email_sent = False
    registration_email_status = "not_configured"
    try:
        from src.modules.email_client.service import EmailService

        email_service = EmailService()
        if email_service.is_configured():
            registered_at = datetime.utcnow().strftime("%d.%m.%Y %H:%M")
            user_name = (customer.name or "uživateli").strip()

            email_body = f"""
Dobrý den {user_name},

vaše registrace do TooZ Hub 2 byla úspěšně dokončena.

Registrovaný účet: {customer.email}
Datum registrace: {registered_at} UTC

Nyní se můžete přihlásit a začít spravovat svá vozidla.

S pozdravem,
TooZ Hub 2
"""

            html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #6366f1;">Vítejte v TooZ Hub 2</h2>
        <p>Dobrý den {user_name},</p>
        <p>vaše registrace do <strong>TooZ Hub 2</strong> byla úspěšně dokončena.</p>
        <div style="background: #f3f4f6; padding: 15px; border-radius: 8px; margin: 20px 0;">
            <p style="margin: 0;"><strong>Registrovaný účet:</strong> {customer.email}</p>
            <p style="margin: 6px 0 0;"><strong>Datum registrace:</strong> {registered_at} UTC</p>
        </div>
        <p>Nyní se můžete přihlásit a začít spravovat svá vozidla.</p>
        <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
        <p style="color: #666; font-size: 0.9em;">S pozdravem,<br>TooZ Hub 2</p>
    </div>
</body>
</html>
"""
            try:
                email_service.send_simple_email(
                    to=customer.email,
                    subject="Potvrzení registrace - TooZ Hub 2",
                    body=email_body,
                    html_body=html_body,
                )
                email_sent = True
                registration_email_status = "sent"
                print(f"[REGISTER] OK: Potvrzovací email odeslán na: {customer.email}")
            except Exception as email_ex:
                registration_email_status = "failed"
                print(f"[REGISTER] ERROR: Nepodařilo se odeslat registrační email: {email_ex}")
        else:
            print("[REGISTER] WARNING: SMTP není nakonfigurováno, potvrzovací email nebyl odeslán")
    except Exception as e:
        registration_email_status = "failed"
        print(f"[REGISTER] ERROR: Neočekávaná chyba při odesílání registračního emailu: {e}")

    # Notifikace developer/admin o nové registraci uživatele.
    developer_alert = send_registration_alert_email(
        db,
        registration_type="user",
        account_email=customer.email,
        account_name=customer.name,
        account_ico=customer.ico,
        metadata={
            "customer_id": customer.id,
            "tenant_id": customer.tenant_id,
            "role": customer.role or "user",
        },
    )
    if developer_alert.get("status") not in {"sent", "no_recipients", "smtp_not_configured"}:
        print(f"[REGISTER] Developer alert status: {developer_alert.get('status')} error={developer_alert.get('error')}")
    
    # Vytvořit JWT token
    access_token = create_access_token(data={"sub": customer.email, "sv": customer_session_version(customer)})
    
    return RegisterTokenResponse(
        access_token=access_token,
        user={
            "id": customer.id,
            "email": customer.email,
            "name": customer.name,
            "ico": customer.ico,
            "role": customer.role or "user"
        },
        email_sent=email_sent,
        registration_email_status=registration_email_status,
    )


@app.post("/user/register/service-request", response_model=ServiceRegisterResponse)
def register_service_request(payload: ServiceRegisterRequest, db=Depends(get_db)):
    """
    Vytvoří žádost o servisní účet.
    Servisní účet se aktivuje až po schválení developer_admin/admin.
    """
    normalized_email = normalize_email(payload.email)
    ico_digits = normalize_ico(payload.ico) or ""

    if not payload.password or len(payload.password) < 6:
        raise HTTPException(status_code=400, detail="Heslo musí mít alespoň 6 znaků")
    if len(ico_digits) != 8:
        raise HTTPException(status_code=400, detail="IČO musí obsahovat přesně 8 číslic")

    if get_customer_by_email(db, normalized_email):
        raise HTTPException(status_code=400, detail="Účet s tímto emailem již existuje")

    # Jedno IČO může mít pouze jeden servisní účet/žádost.
    existing_service_customer_same_ico = (
        db.query(Customer)
        .filter(
            Customer.role == "service",
            Customer.ico == ico_digits,
            func.lower(Customer.email) != normalized_email,
        )
        .first()
    )
    if existing_service_customer_same_ico:
        raise HTTPException(
            status_code=400,
            detail="Toto IČO je už registrováno u jiného servisního účtu.",
        )

    existing_request_same_ico = (
        db.query(ServiceRegistrationRequest)
        .filter(
            ServiceRegistrationRequest.ico == ico_digits,
            func.lower(ServiceRegistrationRequest.email) != normalized_email,
            ServiceRegistrationRequest.status.in_(["pending", "approved"]),
        )
        .first()
    )
    if existing_request_same_ico:
        raise HTTPException(
            status_code=400,
            detail="Toto IČO už má aktivní nebo schválenou servisní registraci.",
        )

    existing_request = (
        db.query(ServiceRegistrationRequest)
        .filter(func.lower(ServiceRegistrationRequest.email) == normalized_email)
        .first()
    )

    hashed_password = hash_password(payload.password)
    now = datetime.utcnow()

    if existing_request:
        if existing_request.status == "pending":
            raise HTTPException(
                status_code=400,
                detail="Žádost pro tento email už čeká na schválení developerem.",
            )
        if existing_request.status == "approved":
            raise HTTPException(
                status_code=400,
                detail="Tato servisní registrace už byla schválena. Přihlaste se.",
            )

        existing_request.status = "pending"
        existing_request.password_hash = hashed_password
        existing_request.ico = ico_digits
        existing_request.service_name = payload.service_name.strip()
        existing_request.responsible_person = payload.responsible_person.strip()
        existing_request.phone = payload.phone.strip()
        existing_request.street = payload.street.strip()
        existing_request.street_number = (payload.street_number or "").strip() or None
        existing_request.city = payload.city.strip()
        existing_request.zip = payload.zip.strip()
        existing_request.dic = (payload.dic or "").strip() or None
        existing_request.registration_purpose = payload.registration_purpose.strip()
        existing_request.reviewed_by_customer_id = None
        existing_request.reviewed_at = None
        existing_request.review_note = None
        existing_request.approved_customer_id = None
        existing_request.approved_tenant_id = None
        existing_request.updated_at = now
        db.commit()
        db.refresh(existing_request)

        developer_alert = send_registration_alert_email(
            db,
            registration_type="service",
            account_email=existing_request.email,
            account_name=existing_request.service_name,
            account_ico=existing_request.ico,
            metadata={
                "request_id": existing_request.id,
                "status": existing_request.status,
                "city": existing_request.city,
                "responsible_person": existing_request.responsible_person,
                "phone": existing_request.phone,
                "purpose": existing_request.registration_purpose[:180],
                "event": "service_request_resubmitted",
            },
        )
        if developer_alert.get("status") not in {"sent", "no_recipients", "smtp_not_configured"}:
            print(f"[REGISTER] Developer alert status: {developer_alert.get('status')} error={developer_alert.get('error')}")

        return ServiceRegisterResponse(
            request_id=existing_request.id,
            status="pending",
            message="Žádost o servisní registraci byla znovu odeslána ke schválení.",
        )

    new_request = ServiceRegistrationRequest(
        status="pending",
        email=normalized_email,
        password_hash=hashed_password,
        ico=ico_digits,
        service_name=payload.service_name.strip(),
        responsible_person=payload.responsible_person.strip(),
        phone=payload.phone.strip(),
        street=payload.street.strip(),
        street_number=(payload.street_number or "").strip() or None,
        city=payload.city.strip(),
        zip=payload.zip.strip(),
        dic=(payload.dic or "").strip() or None,
        registration_purpose=payload.registration_purpose.strip(),
        created_at=now,
        updated_at=now,
    )

    db.add(new_request)
    db.commit()
    db.refresh(new_request)

    developer_alert = send_registration_alert_email(
        db,
        registration_type="service",
        account_email=new_request.email,
        account_name=new_request.service_name,
        account_ico=new_request.ico,
        metadata={
            "request_id": new_request.id,
            "status": new_request.status,
            "city": new_request.city,
            "responsible_person": new_request.responsible_person,
            "phone": new_request.phone,
            "purpose": new_request.registration_purpose[:180],
            "event": "service_request_created",
        },
    )
    if developer_alert.get("status") not in {"sent", "no_recipients", "smtp_not_configured"}:
        print(f"[REGISTER] Developer alert status: {developer_alert.get('status')} error={developer_alert.get('error')}")

    return ServiceRegisterResponse(
        request_id=new_request.id,
        status="pending",
        message="Žádost o servisní účet byla přijata. Aktivace proběhne po ověření developerem.",
    )


@app.post("/user/login", response_model=LoginResponse)
def login_user(login_data: UserLogin, request: Request, db=Depends(get_db)):
    """
    Přihlášení uživatele
    Rate limiting je řešen přes RateLimitMiddleware (globální) a specifický limit pro tento endpoint
    """
    normalized_email = normalize_email(login_data.email)
    # Diagnostika: potvrzení, že request dorazil na server (email maskovaný)
    _mask = normalized_email[:2] + "***" + normalized_email[-1:] if len(normalized_email) > 3 else "***"
    print(f"[LOGIN] Request received for {_mask} (path={request.url.path})")
    try:
        # Rate limiting kontrolu provádí middleware, ale přidáváme i jemnější limit
        # pro login (kombinace email + IP), aby se uživatelé navzájem neblokovali
        # při sdílené veřejné IP adrese.
        client_ip = extract_client_ip(request) or "unknown"
        ip_block = get_active_ip_block(db, client_ip)
        if ip_block:
            detail_payload = {
                "reason": "blocked_ip",
                "blocked_at": ip_block.blocked_at.isoformat() if ip_block.blocked_at else None,
                "expires_at": ip_block.expires_at.isoformat() if ip_block.expires_at else None,
            }
            if ip_block.reason:
                detail_payload["block_reason"] = ip_block.reason
            log_security_event(
                event_type="login_blocked_ip",
                request=request,
                user_email=normalized_email,
                endpoint=str(request.url.path),
                details=detail_payload,
            )
            raise HTTPException(
                status_code=403,
                detail="Přístup z této IP adresy je dočasně zablokován."
            )

        key = f"login:{normalized_email}:{client_ip}"
        
        # Kontrola rate limitu (5 pokusů za minutu)
        if not rate_limiter.check_rate_limit(key, max_calls=5, period=60):
            log_security_event(
                event_type="login_rate_limited",
                request=request,
                user_email=normalized_email,
                endpoint=str(request.url.path),
                details={"reason": "rate_limit", "max_calls": 5, "period_sec": 60},
            )
            raise HTTPException(
                status_code=429,
                detail="Příliš mnoho pokusů o přihlášení. Zkuste to znovu za minutu."
            )
        
        customer = get_customer_by_email(db, normalized_email)
        if not customer:
            log_security_event(
                event_type="login_failed",
                request=request,
                user_email=normalized_email,
                endpoint=str(request.url.path),
                details={"reason": "user_not_found"},
            )
            raise HTTPException(status_code=401, detail="Neplatný email nebo heslo")

        if customer_is_deleted(customer):
            log_security_event(
                event_type="login_failed",
                request=request,
                user_email=normalized_email,
                customer_id=customer.id,
                tenant_id=customer.tenant_id,
                endpoint=str(request.url.path),
                details={"reason": "account_deleted"},
            )
            raise HTTPException(status_code=403, detail="Účet byl deaktivován.")

        if customer_is_disabled(customer):
            log_security_event(
                event_type="login_failed",
                request=request,
                user_email=normalized_email,
                customer_id=customer.id,
                tenant_id=customer.tenant_id,
                endpoint=str(request.url.path),
                details={"reason": "account_disabled"},
            )
            raise HTTPException(status_code=403, detail="Účet je dočasně pozastaven.")
        
        # Ověřit heslo
        if not customer.password_hash:
            log_security_event(
                event_type="login_failed",
                request=request,
                user_email=normalized_email,
                customer_id=customer.id,
                tenant_id=customer.tenant_id,
                endpoint=str(request.url.path),
                details={"reason": "missing_password_hash"},
            )
            raise HTTPException(status_code=401, detail="Neplatný email nebo heslo")
        
        if not verify_password(login_data.password, customer.password_hash):
            log_security_event(
                event_type="login_failed",
                request=request,
                user_email=normalized_email,
                customer_id=customer.id,
                tenant_id=customer.tenant_id,
                endpoint=str(request.url.path),
                details={"reason": "invalid_password"},
            )
            raise HTTPException(status_code=401, detail="Neplatný email nebo heslo")
        
        requested_role = (login_data.expected_role or "").strip().lower()
        if requested_role in {"user", "service"}:
            customer_role = (customer.role or "user").strip().lower()
            if requested_role == "service" and customer_role not in {"service", "admin", "developer_admin"}:
                log_security_event(
                    event_type="login_failed",
                    request=request,
                    user_email=normalized_email,
                    customer_id=customer.id,
                    tenant_id=customer.tenant_id,
                    endpoint=str(request.url.path),
                    details={"reason": "role_mismatch_service", "customer_role": customer_role},
                )
                raise HTTPException(
                    status_code=403,
                    detail="Tento účet není servisní. Přepněte režim na Uživatel.",
                )
            if requested_role == "user" and customer_role == "service":
                log_security_event(
                    event_type="login_failed",
                    request=request,
                    user_email=normalized_email,
                    customer_id=customer.id,
                    tenant_id=customer.tenant_id,
                    endpoint=str(request.url.path),
                    details={"reason": "role_mismatch_user", "customer_role": customer_role},
                )
                raise HTTPException(
                    status_code=403,
                    detail="Tento účet je servisní. Přepněte režim na Servis.",
                )

        # Pokud je potřeba přehashovat (upgrade z SHA256 na bcrypt)
        if needs_rehash(customer.password_hash):
            customer.password_hash = hash_password(login_data.password)
            db.commit()

        security_settings = (
            db.query(CustomerSecuritySettings)
            .filter(CustomerSecuritySettings.customer_id == customer.id)
            .first()
        )
        if (
            security_settings
            and security_settings.two_factor_enabled
            and security_settings.totp_secret
        ):
            challenge_token, expires_in = _create_2fa_login_challenge(
                customer=customer,
                expected_role=requested_role if requested_role in {"user", "service"} else None,
            )
            log_security_event(
                event_type="login_2fa_challenge_issued",
                request=request,
                user_email=customer.email,
                customer_id=customer.id,
                tenant_id=customer.tenant_id,
                endpoint=str(request.url.path),
                details={"role": customer.role or "user", "expires_in_sec": expires_in},
            )
            return LoginResponse(
                two_factor_required=True,
                challenge_token=challenge_token,
                challenge_expires_in=expires_in,
            )

        touch_customer_last_login(customer)
        db.commit()

        # Vytvořit JWT token (včetně session version pro force logout).
        access_token = create_access_token(data={"sub": customer.email, "sv": customer_session_version(customer)})

        log_security_event(
            event_type="login_success",
            request=request,
            user_email=customer.email,
            customer_id=customer.id,
            tenant_id=customer.tenant_id,
            endpoint=str(request.url.path),
            details={"role": customer.role or "user"},
        )
        
        return LoginResponse(
            access_token=access_token,
            user={
                "id": customer.id,
                "email": customer.email,
                "name": customer.name,
                "ico": customer.ico,
                "role": customer.role or "user"
            }
        )
    except HTTPException:
        # Re-raise HTTP exceptions (401, 429, etc.)
        raise
    except Exception as e:
        # Logovat všechny ostatní chyby
        import traceback
        error_details = traceback.format_exc()
        print(f"[LOGIN ERROR] {str(e)}")
        print(f"[LOGIN ERROR] Traceback:\n{error_details}")
        raise HTTPException(
            status_code=500,
            detail=f"Interní chyba serveru: {str(e)}"
        )


@app.post("/user/login/2fa", response_model=TokenResponse)
def verify_login_two_factor(
    payload: TwoFactorLoginVerifyRequest,
    request: Request,
    db=Depends(get_db),
):
    """Dokončí přihlášení po zadání TOTP kódu."""
    _cleanup_expired_2fa_challenges()
    challenge = _pending_2fa_logins.get(payload.challenge_token)
    if not challenge:
        raise HTTPException(
            status_code=401,
            detail="2FA výzva vypršela nebo je neplatná. Přihlaste se znovu.",
        )

    expires_at = float(challenge.get("expires_at", 0))
    if expires_at <= time.time():
        _pending_2fa_logins.pop(payload.challenge_token, None)
        raise HTTPException(
            status_code=401,
            detail="2FA výzva vypršela. Přihlaste se znovu.",
        )

    attempts = int(challenge.get("attempts", 0))
    if attempts >= 5:
        _pending_2fa_logins.pop(payload.challenge_token, None)
        raise HTTPException(
            status_code=429,
            detail="Překročen počet pokusů o 2FA ověření. Přihlaste se znovu.",
        )

    email = challenge.get("email")
    customer = get_customer_by_email(db, str(email or ""))
    if not customer:
        _pending_2fa_logins.pop(payload.challenge_token, None)
        raise HTTPException(status_code=401, detail="Uživatel pro 2FA ověření nebyl nalezen")
    if customer_is_deleted(customer):
        _pending_2fa_logins.pop(payload.challenge_token, None)
        raise HTTPException(status_code=403, detail="Účet byl deaktivován.")
    if customer_is_disabled(customer):
        _pending_2fa_logins.pop(payload.challenge_token, None)
        raise HTTPException(status_code=403, detail="Účet je dočasně pozastaven.")

    expected_role = str(challenge.get("expected_role") or "").strip().lower()
    customer_role = (customer.role or "user").strip().lower()
    if expected_role == "service" and customer_role not in {"service", "admin", "developer_admin"}:
        _pending_2fa_logins.pop(payload.challenge_token, None)
        raise HTTPException(status_code=403, detail="Tento účet není servisní.")
    if expected_role == "user" and customer_role == "service":
        _pending_2fa_logins.pop(payload.challenge_token, None)
        raise HTTPException(status_code=403, detail="Tento účet je servisní.")

    security_settings = (
        db.query(CustomerSecuritySettings)
        .filter(CustomerSecuritySettings.customer_id == customer.id)
        .first()
    )
    if not security_settings or not security_settings.two_factor_enabled or not security_settings.totp_secret:
        _pending_2fa_logins.pop(payload.challenge_token, None)
        raise HTTPException(status_code=400, detail="2FA není pro tento účet aktivní")

    if not _verify_totp(security_settings.totp_secret, payload.code):
        challenge["attempts"] = attempts + 1
        _pending_2fa_logins[payload.challenge_token] = challenge
        log_security_event(
            event_type="login_2fa_failed",
            request=request,
            user_email=customer.email,
            customer_id=customer.id,
            tenant_id=customer.tenant_id,
            endpoint=str(request.url.path),
            details={"attempts": challenge["attempts"]},
        )
        raise HTTPException(status_code=401, detail="Neplatný 2FA kód")

    _pending_2fa_logins.pop(payload.challenge_token, None)
    touch_customer_last_login(customer)
    db.commit()
    access_token = create_access_token(data={"sub": customer.email, "sv": customer_session_version(customer)})

    log_security_event(
        event_type="login_2fa_success",
        request=request,
        user_email=customer.email,
        customer_id=customer.id,
        tenant_id=customer.tenant_id,
        endpoint=str(request.url.path),
        details={"role": customer.role or "user"},
    )

    return TokenResponse(
        access_token=access_token,
        user={
            "id": customer.id,
            "email": customer.email,
            "name": customer.name,
            "ico": customer.ico,
            "role": customer.role or "user",
        },
    )


@app.get("/user/me", response_model=UserResponse)
def get_current_user(
    request: Request,
    email: str = Depends(get_current_user_email),
    db=Depends(get_db),
):
    """Vrátí aktuálně přihlášeného uživatele"""
    customer = db.query(Customer).filter(Customer.email == email).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")
    log_user_activity(
        request=request,
        user_email=customer.email,
        customer_id=customer.id,
        tenant_id=customer.tenant_id,
        endpoint=str(request.url.path),
        details={"source": "user_me"},
    )
    return customer


@app.put("/user/me", response_model=UserResponse)
def update_current_user(
    user_update: UserUpdate,
    request: Request,
    email: str = Depends(get_current_user_email),
    db=Depends(get_db)
):
    """Aktualizuje profil přihlášeného uživatele"""
    customer = db.query(Customer).filter(Customer.email == email).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")
    log_user_activity(
        request=request,
        user_email=customer.email,
        customer_id=customer.id,
        tenant_id=customer.tenant_id,
        endpoint=str(request.url.path),
        details={"source": "user_update_profile"},
    )
    
    # Aktualizovat pouze poskytnutá pole
    update_data = user_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if hasattr(customer, field):
            setattr(customer, field, value)
    
    db.commit()
    db.refresh(customer)
    return customer


@app.get("/user/me/export")
def export_current_user_data(
    request: Request,
    email: str = Depends(get_current_user_email),
    db=Depends(get_db),
):
    """Stáhne kompletní export dat uživatele (ZIP + PDF report pro každé vozidlo)."""
    customer = get_customer_by_email(db, email)
    if not customer:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")

    normalized_email = normalize_email(customer.email or email)
    vehicles_query = db.query(VehicleModel).filter(func.lower(VehicleModel.user_email) == normalized_email)
    if customer.tenant_id:
        vehicles_query = vehicles_query.filter(VehicleModel.tenant_id == customer.tenant_id)
    vehicles = vehicles_query.order_by(VehicleModel.created_at.asc()).all()
    vehicle_ids = [v.id for v in vehicles]
    vehicle_record_condition = ServiceRecordModel.vehicle_id.in_(vehicle_ids) if vehicle_ids else (ServiceRecordModel.id == -1)
    vehicle_reminder_condition = ReminderModel.vehicle_id.in_(vehicle_ids) if vehicle_ids else (ReminderModel.id == -1)
    vehicle_reservation_condition = ReservationModel.vehicle_id.in_(vehicle_ids) if vehicle_ids else (ReservationModel.id == -1)
    vehicle_intake_condition = ServiceIntake.vehicle_id.in_(vehicle_ids) if vehicle_ids else (ServiceIntake.id == -1)
    vehicle_document_condition = ServiceDocumentIngestion.vehicle_id.in_(vehicle_ids) if vehicle_ids else (ServiceDocumentIngestion.id == -1)
    vehicle_customer_command_condition = CustomerCommand.vehicle_id.in_(vehicle_ids) if vehicle_ids else (CustomerCommand.id == -1)

    service_records = db.query(ServiceRecordModel).filter(
        or_(
            ServiceRecordModel.user_id == customer.id,
            vehicle_record_condition,
        )
    ).order_by(ServiceRecordModel.performed_at.asc()).all()

    reminders = db.query(ReminderModel).filter(
        or_(
            ReminderModel.customer_id == customer.id,
            vehicle_reminder_condition,
        )
    ).order_by(ReminderModel.created_at.asc()).all()

    reservations = db.query(ReservationModel).filter(
        or_(
            ReservationModel.customer_id == customer.id,
            ReservationModel.service_id == customer.id,
            vehicle_reservation_condition,
        )
    ).order_by(ReservationModel.start_datetime.asc()).all()

    service_intakes = db.query(ServiceIntake).filter(
        or_(
            ServiceIntake.customer_id == customer.id,
            ServiceIntake.service_id == customer.id,
            vehicle_intake_condition,
        )
    ).order_by(ServiceIntake.created_at.asc()).all()

    service_links = db.query(ServiceCustomerLink).filter(
        or_(
            ServiceCustomerLink.service_customer_id == customer.id,
            ServiceCustomerLink.customer_id == customer.id,
        )
    ).order_by(ServiceCustomerLink.created_at.asc()).all()

    service_invites = db.query(ServiceCustomerInvite).filter(
        or_(
            ServiceCustomerInvite.service_customer_id == customer.id,
            ServiceCustomerInvite.linked_customer_id == customer.id,
            func.lower(ServiceCustomerInvite.invite_email) == normalized_email,
        )
    ).order_by(ServiceCustomerInvite.created_at.asc()).all()

    service_documents = db.query(ServiceDocumentIngestion).filter(
        or_(
            ServiceDocumentIngestion.customer_id == customer.id,
            ServiceDocumentIngestion.service_customer_id == customer.id,
            vehicle_document_condition,
        )
    ).order_by(ServiceDocumentIngestion.created_at.asc()).all()

    email_logs = db.query(EmailNotificationLog).filter(
        or_(
            EmailNotificationLog.customer_id == customer.id,
            func.lower(EmailNotificationLog.email) == normalized_email,
        )
    ).order_by(EmailNotificationLog.sent_at.asc()).all()

    push_subscriptions = db.query(PushSubscription).filter(
        PushSubscription.customer_id == customer.id
    ).order_by(PushSubscription.created_at.asc()).all()

    security_logs = db.query(SecurityAccessLog).filter(
        or_(
            SecurityAccessLog.customer_id == customer.id,
            func.lower(SecurityAccessLog.user_email) == normalized_email,
        )
    ).order_by(SecurityAccessLog.created_at.asc()).all()

    registration_requests = db.query(ServiceRegistrationRequest).filter(
        func.lower(ServiceRegistrationRequest.email) == normalized_email
    ).order_by(ServiceRegistrationRequest.created_at.asc()).all()

    bot_commands = db.query(BotCommand).filter(
        or_(
            BotCommand.user_id == customer.id,
            func.lower(BotCommand.user_email) == normalized_email,
        )
    ).order_by(BotCommand.created_at.asc()).all()

    customer_commands = db.query(CustomerCommand).filter(
        or_(
            func.lower(CustomerCommand.customer_email) == normalized_email,
            vehicle_customer_command_condition,
        )
    ).order_by(CustomerCommand.created_at.asc()).all()

    security_settings = (
        db.query(CustomerSecuritySettings)
        .filter(CustomerSecuritySettings.customer_id == customer.id)
        .first()
    )

    export_payload = {
        "meta": {
            "generated_at_utc": datetime.utcnow().isoformat(),
            "app": "TooZ Hub 2",
            "version": APP_VERSION,
            "customer_id": customer.id,
            "tenant_id": customer.tenant_id,
            "email": customer.email,
        },
        "account": _model_to_export_dict(customer),
        "security_settings": _model_to_export_dict(security_settings) if security_settings else None,
        "counts": {
            "vehicles": len(vehicles),
            "service_records": len(service_records),
            "reminders": len(reminders),
            "reservations": len(reservations),
            "service_intakes": len(service_intakes),
            "service_links": len(service_links),
            "service_invites": len(service_invites),
            "service_documents": len(service_documents),
            "email_logs": len(email_logs),
            "push_subscriptions": len(push_subscriptions),
            "security_logs": len(security_logs),
            "service_registration_requests": len(registration_requests),
            "bot_commands": len(bot_commands),
            "customer_commands": len(customer_commands),
        },
        "vehicles": [_model_to_export_dict(v) for v in vehicles],
        "service_records": [_model_to_export_dict(v) for v in service_records],
        "reminders": [_model_to_export_dict(v) for v in reminders],
        "reservations": [_model_to_export_dict(v) for v in reservations],
        "service_intakes": [_model_to_export_dict(v) for v in service_intakes],
        "service_links": [_model_to_export_dict(v) for v in service_links],
        "service_invites": [_model_to_export_dict(v) for v in service_invites],
        "service_documents": [_model_to_export_dict(v) for v in service_documents],
        "email_logs": [_model_to_export_dict(v) for v in email_logs],
        "push_subscriptions": [_model_to_export_dict(v) for v in push_subscriptions],
        "security_logs": [_model_to_export_dict(v) for v in security_logs],
        "service_registration_requests": [_model_to_export_dict(v) for v in registration_requests],
        "bot_commands": [_model_to_export_dict(v) for v in bot_commands],
        "customer_commands": [_model_to_export_dict(v) for v in customer_commands],
    }

    tmp_dir_path = Path(tempfile.mkdtemp(prefix="toozhub_export_"))
    data_dir = tmp_dir_path / "data"
    pdf_dir = tmp_dir_path / "vozidla_pdf"
    data_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir.mkdir(parents=True, exist_ok=True)

    export_json_path = data_dir / "kompletni_export.json"
    account_summary_path = data_dir / "ucet_prehled.json"
    readme_path = tmp_dir_path / "README.txt"

    export_json_path.write_text(
        json.dumps(export_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    account_summary = {
        "generated_at_utc": export_payload["meta"]["generated_at_utc"],
        "email": customer.email,
        "name": customer.name,
        "customer_id": customer.id,
        "tenant_id": customer.tenant_id,
        "counts": export_payload["counts"],
    }
    account_summary_path.write_text(
        json.dumps(account_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    readme_path.write_text(
        (
            "TooZ Hub 2 - Export dat\n"
            "\n"
            "Obsah archivu:\n"
            "- data/kompletni_export.json  (kompletní strojově čitelný export)\n"
            "- data/ucet_prehled.json      (stručný přehled účtu)\n"
            "- vozidla_pdf/*.pdf           (strukturovaný report pro každé vozidlo)\n"
            "\n"
            "Doporučení: Před smazáním účtu archiv bezpečně uložte.\n"
        ),
        encoding="utf-8",
    )

    reminders_by_vehicle: dict[int, list[ReminderModel]] = {}
    for reminder in reminders:
        if reminder.vehicle_id:
            reminders_by_vehicle.setdefault(int(reminder.vehicle_id), []).append(reminder)

    reservations_by_vehicle: dict[int, list[ReservationModel]] = {}
    for reservation in reservations:
        if reservation.vehicle_id:
            reservations_by_vehicle.setdefault(int(reservation.vehicle_id), []).append(reservation)

    records_by_vehicle: dict[int, list[ServiceRecordModel]] = {}
    for record in service_records:
        if record.vehicle_id:
            records_by_vehicle.setdefault(int(record.vehicle_id), []).append(record)

    for vehicle in vehicles:
        vehicle_identifier = vehicle.plate or vehicle.nickname or f"vozidlo_{vehicle.id}"
        safe_identifier = _safe_filename(vehicle_identifier, fallback=f"vozidlo_{vehicle.id}")
        pdf_name = f"{vehicle.id:04d}_{safe_identifier}.pdf"
        pdf_path = pdf_dir / pdf_name
        _build_vehicle_export_pdf(
            pdf_path,
            customer=customer,
            vehicle=vehicle,
            records=records_by_vehicle.get(vehicle.id, []),
            reminders=reminders_by_vehicle.get(vehicle.id, []),
            reservations=reservations_by_vehicle.get(vehicle.id, []),
        )

    export_file_name = f"toozhub_export_{customer.id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.zip"
    zip_path = tmp_dir_path / export_file_name
    with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zip_file:
        for file_path in sorted(tmp_dir_path.rglob("*")):
            if file_path == zip_path:
                continue
            if file_path.is_file():
                zip_file.write(file_path, arcname=str(file_path.relative_to(tmp_dir_path)))

    log_user_activity(
        request=request,
        user_email=customer.email,
        customer_id=customer.id,
        tenant_id=customer.tenant_id,
        endpoint=str(request.url.path),
        details={"source": "user_export_data", "vehicles": len(vehicles)},
    )

    return FileResponse(
        path=str(zip_path),
        filename=export_file_name,
        media_type="application/zip",
        background=BackgroundTask(shutil.rmtree, str(tmp_dir_path), True),
    )


@app.delete("/user/me", response_model=DeleteAccountResponse)
def delete_current_user_account(
    payload: DeleteAccountRequest,
    request: Request,
    email: str = Depends(get_current_user_email),
    db=Depends(get_db),
):
    """Nenávratně smaže účet uživatele i navázaná data."""
    customer = get_customer_by_email(db, email)
    if not customer:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")

    confirmation = _normalize_delete_confirmation(payload.confirmation_text)
    if confirmation not in ACCOUNT_DELETE_CONFIRM_TOKENS:
        raise HTTPException(
            status_code=400,
            detail="Potvrzení smazání nesouhlasí. Zadejte přesně text: SMAZAT UCET",
        )

    if not payload.export_downloaded:
        raise HTTPException(
            status_code=400,
            detail="Před smazáním účtu je nutné stáhnout export dat.",
        )

    if not customer.password_hash or not verify_password(payload.current_password, customer.password_hash):
        raise HTTPException(status_code=400, detail="Neplatné současné heslo")

    normalized_email = normalize_email(customer.email or email)

    # Vozidla uživatele jsou primárně navázaná přes user_email.
    vehicles_query = db.query(VehicleModel).filter(func.lower(VehicleModel.user_email) == normalized_email)
    if customer.tenant_id:
        vehicles_query = vehicles_query.filter(VehicleModel.tenant_id == customer.tenant_id)
    vehicle_ids = [row.id for row in vehicles_query.with_entities(VehicleModel.id).all()]

    deleted_counts: dict[str, int] = {}
    tenant_id = customer.tenant_id
    no_vehicle_match_docs = ServiceDocumentIngestion.id == -1
    no_vehicle_match_intakes = ServiceIntake.id == -1
    no_vehicle_match_reservations = ReservationModel.id == -1
    no_vehicle_match_reminders = ReminderModel.id == -1
    no_vehicle_match_records = ServiceRecordModel.id == -1
    no_vehicle_match_commands = CustomerCommand.id == -1
    no_vehicle_match_vehicles = VehicleModel.id == -1

    vehicle_docs_condition = ServiceDocumentIngestion.vehicle_id.in_(vehicle_ids) if vehicle_ids else no_vehicle_match_docs
    vehicle_intakes_condition = ServiceIntake.vehicle_id.in_(vehicle_ids) if vehicle_ids else no_vehicle_match_intakes
    vehicle_reservation_condition = ReservationModel.vehicle_id.in_(vehicle_ids) if vehicle_ids else no_vehicle_match_reservations
    vehicle_reminder_condition = ReminderModel.vehicle_id.in_(vehicle_ids) if vehicle_ids else no_vehicle_match_reminders
    vehicle_record_condition = ServiceRecordModel.vehicle_id.in_(vehicle_ids) if vehicle_ids else no_vehicle_match_records
    vehicle_command_condition = CustomerCommand.vehicle_id.in_(vehicle_ids) if vehicle_ids else no_vehicle_match_commands
    vehicle_self_condition = VehicleModel.id.in_(vehicle_ids) if vehicle_ids else no_vehicle_match_vehicles

    try:
        # Uvolnit referenční vazby ze schvalování servisních registrací.
        db.query(ServiceRegistrationRequest).filter(
            ServiceRegistrationRequest.reviewed_by_customer_id == customer.id
        ).update({ServiceRegistrationRequest.reviewed_by_customer_id: None}, synchronize_session=False)
        db.query(ServiceRegistrationRequest).filter(
            ServiceRegistrationRequest.approved_customer_id == customer.id
        ).update({ServiceRegistrationRequest.approved_customer_id: None}, synchronize_session=False)
        if tenant_id:
            db.query(ServiceRegistrationRequest).filter(
                ServiceRegistrationRequest.approved_tenant_id == tenant_id
            ).update({ServiceRegistrationRequest.approved_tenant_id: None}, synchronize_session=False)

        deleted_counts["service_documents"] = _bulk_delete(
            db.query(ServiceDocumentIngestion).filter(
                or_(
                    ServiceDocumentIngestion.customer_id == customer.id,
                    ServiceDocumentIngestion.service_customer_id == customer.id,
                    vehicle_docs_condition,
                )
            )
        )
        deleted_counts["service_intakes"] = _bulk_delete(
            db.query(ServiceIntake).filter(
                or_(
                    ServiceIntake.customer_id == customer.id,
                    ServiceIntake.service_id == customer.id,
                    vehicle_intakes_condition,
                )
            )
        )
        deleted_counts["reservations"] = _bulk_delete(
            db.query(ReservationModel).filter(
                or_(
                    ReservationModel.customer_id == customer.id,
                    ReservationModel.service_id == customer.id,
                    vehicle_reservation_condition,
                )
            )
        )
        deleted_counts["reminders"] = _bulk_delete(
            db.query(ReminderModel).filter(
                or_(
                    ReminderModel.customer_id == customer.id,
                    vehicle_reminder_condition,
                )
            )
        )
        deleted_counts["service_records"] = _bulk_delete(
            db.query(ServiceRecordModel).filter(
                or_(
                    ServiceRecordModel.user_id == customer.id,
                    vehicle_record_condition,
                )
            )
        )
        deleted_counts["service_links"] = _bulk_delete(
            db.query(ServiceCustomerLink).filter(
                or_(
                    ServiceCustomerLink.service_customer_id == customer.id,
                    ServiceCustomerLink.customer_id == customer.id,
                )
            )
        )
        deleted_counts["service_invites"] = _bulk_delete(
            db.query(ServiceCustomerInvite).filter(
                or_(
                    ServiceCustomerInvite.service_customer_id == customer.id,
                    ServiceCustomerInvite.linked_customer_id == customer.id,
                    func.lower(ServiceCustomerInvite.invite_email) == normalized_email,
                )
            )
        )
        deleted_counts["email_logs"] = _bulk_delete(
            db.query(EmailNotificationLog).filter(
                or_(
                    EmailNotificationLog.customer_id == customer.id,
                    func.lower(EmailNotificationLog.email) == normalized_email,
                )
            )
        )
        deleted_counts["push_subscriptions"] = _bulk_delete(
            db.query(PushSubscription).filter(PushSubscription.customer_id == customer.id)
        )
        deleted_counts["security_logs"] = _bulk_delete(
            db.query(SecurityAccessLog).filter(
                or_(
                    SecurityAccessLog.customer_id == customer.id,
                    func.lower(SecurityAccessLog.user_email) == normalized_email,
                )
            )
        )
        deleted_counts["bot_commands"] = _bulk_delete(
            db.query(BotCommand).filter(
                or_(
                    BotCommand.user_id == customer.id,
                    func.lower(BotCommand.user_email) == normalized_email,
                )
            )
        )
        deleted_counts["customer_commands"] = _bulk_delete(
            db.query(CustomerCommand).filter(
                or_(
                    func.lower(CustomerCommand.customer_email) == normalized_email,
                    vehicle_command_condition,
                )
            )
        )
        deleted_counts["service_registration_requests"] = _bulk_delete(
            db.query(ServiceRegistrationRequest).filter(
                func.lower(ServiceRegistrationRequest.email) == normalized_email
            )
        )
        deleted_counts["security_settings"] = _bulk_delete(
            db.query(CustomerSecuritySettings).filter(CustomerSecuritySettings.customer_id == customer.id)
        )
        deleted_counts["vehicles"] = _bulk_delete(
            db.query(VehicleModel).filter(
                or_(
                    func.lower(VehicleModel.user_email) == normalized_email,
                    vehicle_self_condition,
                )
            )
        )
        deleted_counts["customers"] = _bulk_delete(
            db.query(Customer).filter(Customer.id == customer.id)
        )

        # Pokud po smazání účtu tenant nikoho neobsahuje, dočistit tenant-scoped záznamy.
        if tenant_id:
            remaining_customers = db.query(Customer.id).filter(Customer.tenant_id == tenant_id).count()
            if remaining_customers == 0:
                deleted_counts["tenant_service_documents"] = _bulk_delete(
                    db.query(ServiceDocumentIngestion).filter(ServiceDocumentIngestion.service_tenant_id == tenant_id)
                )
                deleted_counts["tenant_records"] = _bulk_delete(
                    db.query(ServiceRecordModel).filter(ServiceRecordModel.tenant_id == tenant_id)
                )
                deleted_counts["tenant_reminders"] = _bulk_delete(
                    db.query(ReminderModel).filter(ReminderModel.tenant_id == tenant_id)
                )
                deleted_counts["tenant_reservations"] = _bulk_delete(
                    db.query(ReservationModel).filter(ReservationModel.tenant_id == tenant_id)
                )
                deleted_counts["tenant_intakes"] = _bulk_delete(
                    db.query(ServiceIntake).filter(ServiceIntake.tenant_id == tenant_id)
                )
                deleted_counts["tenant_vehicles"] = _bulk_delete(
                    db.query(VehicleModel).filter(VehicleModel.tenant_id == tenant_id)
                )
                deleted_counts["tenant_push_subscriptions"] = _bulk_delete(
                    db.query(PushSubscription).filter(PushSubscription.tenant_id == tenant_id)
                )
                deleted_counts["tenant_email_logs"] = _bulk_delete(
                    db.query(EmailNotificationLog).filter(EmailNotificationLog.tenant_id == tenant_id)
                )
                deleted_counts["tenant_security_logs"] = _bulk_delete(
                    db.query(SecurityAccessLog).filter(SecurityAccessLog.tenant_id == tenant_id)
                )
                deleted_counts["tenant_bot_commands"] = _bulk_delete(
                    db.query(BotCommand).filter(BotCommand.tenant_id == tenant_id)
                )
                deleted_counts["tenant_customer_commands"] = _bulk_delete(
                    db.query(CustomerCommand).filter(CustomerCommand.tenant_id == tenant_id)
                )
                deleted_counts["tenant_instances"] = _bulk_delete(
                    db.query(Instance).filter(Instance.tenant_id == tenant_id)
                )
                deleted_counts["tenant_license"] = _bulk_delete(
                    db.query(License).filter(License.tenant_id == tenant_id)
                )
                deleted_counts["tenants"] = _bulk_delete(
                    db.query(Tenant).filter(Tenant.id == tenant_id)
                )

        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Smazání účtu selhalo: {exc}",
        ) from exc

    return DeleteAccountResponse(
        deleted=True,
        message="Účet i navázaná data byly trvale smazány.",
        deleted_counts=deleted_counts,
    )


@app.put("/user/change-password")
def change_password(
    password_data: ChangePasswordRequest,
    request: Request,
    email: str = Depends(get_current_user_email),
    db=Depends(get_db)
):
    """Změní heslo přihlášeného uživatele a pošle potvrzovací email"""
    from src.modules.email_client.service import EmailService
    from datetime import datetime
    
    customer = db.query(Customer).filter(Customer.email == email).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")
    log_user_activity(
        request=request,
        user_email=customer.email,
        customer_id=customer.id,
        tenant_id=customer.tenant_id,
        endpoint=str(request.url.path),
        details={"source": "user_change_password"},
    )
    
    # Ověřit současné heslo
    if not customer.password_hash:
        raise HTTPException(status_code=400, detail="Uživatel nemá nastavené heslo")
    
    if not verify_password(password_data.current_password, customer.password_hash):
        raise HTTPException(status_code=400, detail="Neplatné současné heslo")
    
    # Validace nového hesla
    if not password_data.new_password or len(password_data.new_password) < 6:
        raise HTTPException(status_code=400, detail="Nové heslo musí mít alespoň 6 znaků")
    
    # Nastavit nové heslo
    customer.password_hash = hash_password(password_data.new_password)
    db.commit()
    
    # Odeslat potvrzovací email
    email_sent = False
    email_error = None
    email_service = EmailService()
    
    try:
        if email_service.is_configured():
            print(f"[CHANGE_PASSWORD] Odesílám potvrzovací email na: {email}")
            
            # Získat jméno uživatele pro personalizaci emailu
            user_name = customer.name or "Uživateli"
            change_time = datetime.utcnow().strftime("%d.%m.%Y %H:%M")
            
            email_body = f"""
Dobrý den {user_name},

vaše heslo k účtu v TooZ Hub 2 bylo úspěšně změněno.

Změna byla provedena: {change_time} UTC

Pokud jste tuto změnu neprovedli, okamžitě kontaktujte podporu.

S pozdravem,
TooZ Hub 2
"""
            html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #6366f1;">Potvrzení změny hesla - TooZ Hub 2</h2>
        <p>Dobrý den {user_name},</p>
        <p>vaše heslo k účtu v <strong>TooZ Hub 2</strong> bylo úspěšně změněno.</p>
        <div style="background: #f3f4f6; padding: 15px; border-radius: 8px; margin: 20px 0;">
            <p style="margin: 0;"><strong>Datum změny:</strong> {change_time} UTC</p>
        </div>
        <p style="color: #ef4444; font-weight: bold;">Pokud jste tuto změnu neprovedli, okamžitě kontaktujte podporu.</p>
        <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
        <p style="color: #666; font-size: 0.9em;">S pozdravem,<br>TooZ Hub 2</p>
    </div>
</body>
</html>
"""
            try:
                email_service.send_simple_email(
                    to=email,
                    subject="Potvrzení změny hesla - TooZ Hub 2",
                    body=email_body,
                    html_body=html_body
                )
                email_sent = True
                print(f"[CHANGE_PASSWORD] OK: Potvrzovací email úspěšně odeslán na: {email}")
            except Exception as email_ex:
                email_error = str(email_ex)
                print(f"[CHANGE_PASSWORD] ERROR: Chyba při odesílání emailu: {email_error}")
                import traceback
                traceback.print_exc()
        else:
            print(f"[CHANGE_PASSWORD] WARNING: Email není nakonfigurován (chybí SMTP údaje)")
    except Exception as e:
        email_error = str(e)
        print(f"[CHANGE_PASSWORD] ERROR: Neočekávaná chyba: {email_error}")
        import traceback
        traceback.print_exc()
    
    # Vrátit odpověď s informací o odeslání emailu
    response_message = "Heslo bylo úspěšně změněno"
    if email_sent:
        response_message += " a potvrzovací email byl odeslán"
    elif email_error:
        response_message += f" (email nebyl odeslán: {email_error})"
    else:
        response_message += " (email není nakonfigurován)"
    
    return {
        "message": response_message,
        "email_sent": email_sent,
        "password_changed": True
    }


@app.get("/user/security/settings", response_model=SecuritySettingsResponse)
def get_security_settings(
    request: Request,
    email: str = Depends(get_current_user_email),
    db=Depends(get_db),
):
    customer = get_customer_by_email(db, email)
    if not customer:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")

    settings = _get_or_create_security_settings(db, customer)
    log_user_activity(
        request=request,
        user_email=customer.email,
        customer_id=customer.id,
        tenant_id=customer.tenant_id,
        endpoint=str(request.url.path),
        details={"source": "user_security_settings_read"},
    )

    return SecuritySettingsResponse(
        two_factor_enabled=bool(settings.two_factor_enabled),
        totp_configured=bool(settings.totp_secret),
        biometric_enabled=bool(settings.biometric_enabled),
        biometric_preferred=bool(settings.biometric_preferred),
    )


@app.post("/user/security/totp/setup", response_model=TotpSetupResponse)
def setup_totp(
    request: Request,
    email: str = Depends(get_current_user_email),
    db=Depends(get_db),
):
    customer = get_customer_by_email(db, email)
    if not customer:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")

    settings = _get_or_create_security_settings(db, customer)
    secret = _generate_totp_secret()
    settings.totp_secret = secret
    settings.two_factor_enabled = False
    settings.totp_enabled_at = None
    db.commit()

    log_security_event(
        event_type="totp_setup_started",
        request=request,
        user_email=customer.email,
        customer_id=customer.id,
        tenant_id=customer.tenant_id,
        endpoint=str(request.url.path),
        details={"role": customer.role or "user"},
    )

    return TotpSetupResponse(
        secret=secret,
        otpauth_uri=_build_totp_uri(secret, customer.email),
        digits=TOTP_DIGITS,
        period_seconds=TOTP_PERIOD_SECONDS,
        message="Naskenujte klíč v aplikaci Google/Microsoft Authenticator a potvrďte 6místným kódem.",
    )


@app.post("/user/security/totp/enable")
def enable_totp(
    payload: TotpEnableRequest,
    request: Request,
    email: str = Depends(get_current_user_email),
    db=Depends(get_db),
):
    customer = get_customer_by_email(db, email)
    if not customer:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")

    settings = _get_or_create_security_settings(db, customer)
    if not settings.totp_secret:
        raise HTTPException(
            status_code=400,
            detail="Nejprve spusťte nastavení 2FA (vygenerování tajného klíče).",
        )

    if not _verify_totp(settings.totp_secret, payload.code):
        raise HTTPException(status_code=400, detail="Neplatný ověřovací kód")

    settings.two_factor_enabled = True
    settings.totp_enabled_at = datetime.utcnow()
    db.commit()

    log_security_event(
        event_type="totp_enabled",
        request=request,
        user_email=customer.email,
        customer_id=customer.id,
        tenant_id=customer.tenant_id,
        endpoint=str(request.url.path),
        details={"role": customer.role or "user"},
    )

    return {"message": "Dvoufázové ověření bylo aktivováno.", "two_factor_enabled": True}


@app.post("/user/security/totp/disable")
def disable_totp(
    payload: TotpDisableRequest,
    request: Request,
    email: str = Depends(get_current_user_email),
    db=Depends(get_db),
):
    customer = get_customer_by_email(db, email)
    if not customer:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")

    if not customer.password_hash or not verify_password(payload.current_password, customer.password_hash):
        raise HTTPException(status_code=401, detail="Neplatné současné heslo")

    settings = _get_or_create_security_settings(db, customer)
    if not settings.two_factor_enabled or not settings.totp_secret:
        raise HTTPException(status_code=400, detail="2FA není aktivní")

    if not _verify_totp(settings.totp_secret, payload.code):
        raise HTTPException(status_code=400, detail="Neplatný 2FA kód")

    settings.two_factor_enabled = False
    settings.totp_secret = None
    settings.totp_enabled_at = None
    db.commit()

    log_security_event(
        event_type="totp_disabled",
        request=request,
        user_email=customer.email,
        customer_id=customer.id,
        tenant_id=customer.tenant_id,
        endpoint=str(request.url.path),
        details={"role": customer.role or "user"},
    )

    return {"message": "Dvoufázové ověření bylo vypnuto.", "two_factor_enabled": False}


@app.post("/user/security/biometric")
def update_biometric_preference(
    payload: BiometricSecurityPreferenceRequest,
    request: Request,
    email: str = Depends(get_current_user_email),
    db=Depends(get_db),
):
    customer = get_customer_by_email(db, email)
    if not customer:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")

    settings = _get_or_create_security_settings(db, customer)
    settings.biometric_enabled = bool(payload.enabled)
    settings.biometric_preferred = bool(payload.preferred) if payload.preferred is not None else bool(payload.enabled)
    db.commit()

    log_user_activity(
        request=request,
        user_email=customer.email,
        customer_id=customer.id,
        tenant_id=customer.tenant_id,
        endpoint=str(request.url.path),
        details={
            "source": "user_biometric_preference",
            "enabled": bool(payload.enabled),
            "preferred": bool(settings.biometric_preferred),
        },
    )

    return {
        "message": "Biometrická preference byla uložena. Pro plné biometrické přihlášení je nutné mít aktivní Passkey/WebAuthn tok v klientovi.",
        "biometric_enabled": bool(settings.biometric_enabled),
        "biometric_preferred": bool(settings.biometric_preferred),
    }


@app.get("/user/ares")
def get_ares_data(
    ico: str,
    current_user: Customer = Depends(get_v1_current_user),
    db=Depends(get_db),
):
    """Deprecated wrapper. Source-of-truth je /api/v1/ares/{ico}."""
    return lookup_ares_v1(ico=ico, current_user=current_user, db=db)


@app.post("/user/support")
def contact_support(
    payload: SupportContactRequest,
    request: Request,
    email: str = Depends(get_current_user_email),
    db=Depends(get_db),
):
    """Odešle zprávu uživatele na technickou podporu."""
    from src.modules.email_client.service import EmailService

    normalized_email = normalize_email(email)
    customer = get_customer_by_email(db, normalized_email)
    if not customer:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")

    category = (payload.category or "obecné").strip()[:64]
    subject = (payload.subject or "").strip()
    message = (payload.message or "").strip()
    phone = (payload.phone or "").strip() or None

    if len(subject) < 3:
        raise HTTPException(status_code=400, detail="Předmět musí mít alespoň 3 znaky")
    if len(message) < 10:
        raise HTTPException(status_code=400, detail="Zpráva musí mít alespoň 10 znaků")

    support_email = (
        os.getenv("SUPPORT_EMAIL", "").strip()
        or os.getenv("SMTP_FROM", "").strip()
        or os.getenv("SMTP_USER", "").strip()
    )
    if not support_email:
        raise HTTPException(
            status_code=503,
            detail="Podpora není dostupná - chybí konfigurace cílového emailu",
        )

    source_ip = extract_client_ip(request)
    created_at = datetime.utcnow().strftime("%d.%m.%Y %H:%M UTC")
    app_url = (payload.page_url or "").strip() or None
    user_agent = (payload.user_agent or "").strip() or request.headers.get("user-agent")

    diagnostic_lines = []
    if payload.include_diagnostics:
        diagnostic_lines.append(f"IP: {source_ip or '-'}")
        diagnostic_lines.append(f"Tenant ID: {customer.tenant_id}")
        if app_url:
            diagnostic_lines.append(f"URL: {app_url}")
        if user_agent:
            diagnostic_lines.append(f"User-Agent: {user_agent}")

    diagnostics_text = "\n".join(diagnostic_lines) if diagnostic_lines else "Nezahrnuto"

    subject_line = f"[TooZ Hub Podpora] [{category}] {subject}"
    body = (
        f"Nová zpráva z panelu podpory\n\n"
        f"Datum: {created_at}\n"
        f"Uživatel: {customer.name or '-'}\n"
        f"Email: {customer.email}\n"
        f"Telefon: {phone or customer.phone or '-'}\n"
        f"Kategorie: {category}\n"
        f"Předmět: {subject}\n\n"
        f"Zpráva:\n{message}\n\n"
        f"Diagnostika:\n{diagnostics_text}\n"
    )

    html_lines = "".join(
        f"<li><strong>{line.split(':', 1)[0]}:</strong> {line.split(':', 1)[1].strip() if ':' in line else line}</li>"
        for line in diagnostic_lines
    ) or "<li>Nezahrnuto</li>"
    html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #1f2937;">
  <div style="max-width: 760px; margin: 0 auto; padding: 20px;">
    <h2 style="margin: 0 0 16px; color: #312e81;">Nová zpráva na podporu</h2>
    <p><strong>Datum:</strong> {created_at}</p>
    <p><strong>Uživatel:</strong> {customer.name or '-'}</p>
    <p><strong>Email:</strong> {customer.email}</p>
    <p><strong>Telefon:</strong> {phone or customer.phone or '-'}</p>
    <p><strong>Kategorie:</strong> {category}</p>
    <p><strong>Předmět:</strong> {subject}</p>
    <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 14px; margin: 14px 0;">
      <strong>Zpráva:</strong>
      <p style="white-space: pre-wrap; margin: 8px 0 0;">{message}</p>
    </div>
    <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 10px; padding: 14px;">
      <strong>Diagnostika</strong>
      <ul style="margin: 8px 0 0 18px; padding: 0;">
        {html_lines}
      </ul>
    </div>
  </div>
</body>
</html>
"""

    email_service = EmailService()
    if not email_service.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Podpora není dostupná - SMTP není nakonfigurováno",
        )

    try:
        email_service.send_simple_email(
            to=support_email,
            subject=subject_line,
            body=body,
            html_body=html_body,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Nepodařilo se odeslat zprávu podpory: {exc}") from exc

    log_security_event(
        event_type="support_contact_submitted",
        request=request,
        user_email=customer.email,
        customer_id=customer.id,
        tenant_id=customer.tenant_id,
        endpoint=str(request.url.path),
        details={
            "category": category,
            "subject": subject[:120],
            "has_phone": bool(phone),
            "include_diagnostics": bool(payload.include_diagnostics),
        },
    )

    return {"message": "Požadavek byl odeslán na podporu."}


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


@app.post("/user/forgot-password")
@app.post("/user/request-password-reset")
def forgot_password(request: ForgotPasswordRequest, db=Depends(get_db)):
    """Odeslání reset odkazu na email"""
    from datetime import timedelta
    import secrets
    from src.modules.email_client.service import EmailService
    from src.core.config import PUBLIC_API_BASE_URL
    
    normalized_email = normalize_email(request.email)
    customer = get_customer_by_email(db, normalized_email)
    
    # Vždy vrátit úspěch (bezpečnost - neodhalit, zda email existuje)
    if not customer:
        return {"message": "Pokud email existuje, byl odeslán reset odkaz"}
    
    target_email = customer.email
    
    # Vytvořit reset token
    reset_token = secrets.token_urlsafe(32)
    reset_token_expires = datetime.utcnow() + timedelta(hours=24)  # 24 hodin platnost
    
    customer.reset_token = reset_token
    customer.reset_token_expires = reset_token_expires
    db.commit()
    
    # Vytvořit reset odkaz
    reset_url = f"{PUBLIC_API_BASE_URL}/reset-password.html?token={reset_token}"
    
    # Odeslat email
    email_sent = False
    email_error = None
    email_service = EmailService()  # Definovat před try blokem
    
    try:
        # Diagnostika - zkontrolovat konfiguraci
        print(f"[RESET] Kontroluji email konfiguraci...")
        print(f"[RESET] SMTP_HOST: {email_service.host}")
        print(f"[RESET] SMTP_PORT: {email_service.port}")
        print(f"[RESET] SMTP_USER: {'***' if email_service.username else '(není nastaveno)'}")
        print(f"[RESET] SMTP_FROM: {email_service.from_email}")
        print(f"[RESET] SMTP configured: {email_service.is_configured()}")
        # NIKDY nelogovat SMTP_PASSWORD
        
        if email_service.is_configured():
            print(f"[RESET] Pokusím se odeslat email na: {target_email}")
            email_body = f"""
Dobrý den,

obdrželi jsme žádost o obnovení hesla k vašemu účtu v TooZ Hub 2.

Pro vytvoření nového hesla klikněte na následující odkaz:
{reset_url}

Tento odkaz je platný 24 hodin.

Pokud jste tento požadavek nevytvořili, ignorujte tento email.

S pozdravem,
TooZ Hub 2
"""
            html_body = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #6366f1;">Obnovení hesla - TooZ Hub 2</h2>
        <p>Dobrý den,</p>
        <p>obdrželi jsme žádost o obnovení hesla k vašemu účtu.</p>
        <p>Pro vytvoření nového hesla klikněte na následující tlačítko:</p>
        <div style="text-align: center; margin: 30px 0;">
            <a href="{reset_url}" style="background-color: #6366f1; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; display: inline-block;">Obnovit heslo</a>
        </div>
        <p>Nebo zkopírujte tento odkaz do prohlížeče:</p>
        <p style="word-break: break-all; color: #6366f1;">{reset_url}</p>
        <p><small>Tento odkaz je platný 24 hodin.</small></p>
        <p>Pokud jste tento požadavek nevytvořili, ignorujte tento email.</p>
        <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
        <p style="color: #666; font-size: 0.9em;">S pozdravem,<br>TooZ Hub 2</p>
    </div>
</body>
</html>
"""
            try:
                email_service.send_simple_email(
                    to=target_email,
                    subject="Obnovení hesla - TooZ Hub 2",
                    body=email_body,
                    html_body=html_body
                )
                email_sent = True
                print(f"[RESET] OK: Email uspesne odeslan na: {target_email}")
            except Exception as email_ex:
                email_error = str(email_ex)
                print(f"[RESET] ERROR: Chyba pri odesilani emailu: {email_error}")
                import traceback
                traceback.print_exc()
        else:
            print(f"[RESET] WARNING: Email NENI nakonfigurovan (chybi SMTP udaje)")
            print(f"[RESET] Reset URL (pro testování): {reset_url}")
            print(f"[RESET] Nastavte v .env souboru: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD")
    except Exception as e:
        email_error = str(e)
        print(f"[RESET] ERROR: Neocekavana chyba: {email_error}")
        import traceback
        traceback.print_exc()
    
    # Vrátit odpověď s informací o stavu
    from src.core.config import ENVIRONMENT
    
    if email_sent:
        return {"message": "Pokud email existuje, byl odeslán reset odkaz", "email_sent": True}
    elif email_error:
        is_configured = email_service.is_configured() if email_service else False
        # Zkontrolovat, zda je chyba autentizace
        error_message = "Email nebyl odeslán."
        if "authentication failed" in email_error.lower() or "535" in email_error:
            error_message = "Chyba autentizace SMTP - zkontrolujte uživatelské jméno a heslo v .env souboru."
        elif "connection" in email_error.lower() or "timeout" in email_error.lower():
            error_message = "Chyba připojení k SMTP serveru - zkontrolujte SMTP_HOST a SMTP_PORT."
        else:
            error_message = f"Email nebyl odeslán: {email_error}"
        
        response = {
            "message": error_message,
            "email_sent": False
        }
        
        # V PROD nikdy nevracet reset_url ani error_detail
        # V DEV může vrátit reset_url pro testování
        if ENVIRONMENT != "production":
            response["reset_url"] = reset_url
            response["error_detail"] = email_error
        
        return response
    else:
        response = {
            "message": "Email není nakonfigurován. Nastavte SMTP údaje v .env souboru.",
            "email_sent": False
        }
        
        # V PROD nikdy nevracet reset_url
        # V DEV může vrátit reset_url pro testování
        if ENVIRONMENT != "production":
            response["reset_url"] = reset_url
        
        return response


@app.get("/reset-password.html", response_class=HTMLResponse)
def reset_password_page():
    """Servuje reset-password.html stránku"""
    web_path = Path(__file__).parent.parent.parent / "web" / "reset-password.html"
    if web_path.exists():
        return FileResponse(web_path)
    else:
        raise HTTPException(status_code=404, detail="Reset password page not found")


@app.post("/user/reset-password")
def reset_password(request: ResetPasswordRequest, db=Depends(get_db)):
    """Reset hesla pomocí tokenu"""
    # Validace hesla
    if not request.new_password or len(request.new_password) < 6:
        raise HTTPException(status_code=400, detail="Heslo musí mít alespoň 6 znaků")
    
    # Najít uživatele podle tokenu
    customer = db.query(Customer).filter(
        Customer.reset_token == request.token,
        Customer.reset_token_expires > datetime.utcnow()
    ).first()
    
    if not customer:
        raise HTTPException(status_code=400, detail="Neplatný nebo expirovaný reset token")
    
    # Nastavit nové heslo
    customer.password_hash = hash_password(request.new_password)
    customer.reset_token = None
    customer.reset_token_expires = None
    db.commit()
    
    return {"message": "Heslo bylo úspěšně změněno"}


# ============= VOZIDLA ENDPOINTY =============
# Endpointy pro vehicles jsou nyní v src/modules/vehicle_hub/routers_v1/vehicles.py
# Router je zaregistrován pod /api/v1/vehicles
# VIN decode endpoint je v src/modules/vehicle_hub/decoder/router.py pod /api/vehicles/decode-vin

# ============= SERVISNÍ ZÁZNAMY ENDPOINTY =============
# Endpointy pro service records jsou nyní v src/modules/vehicle_hub/routers_v1/service_records.py
# Router je zaregistrován pod /api/v1/vehicles/{vehicle_id}/records

# ============= SERVISY =============
# Endpointy pro services jsou nyní v src/modules/vehicle_hub/routers_v1/services.py
# Router je zaregistrován pod /api/v1/services

# ============= REZERVACE =============
# Endpointy pro reservations jsou nyní v src/modules/vehicle_hub/routers_v1/reservations.py
# Router je zaregistrován pod /api/v1/reservations


# ============= PŘIPOMÍNKY =============
# Endpointy pro reminders jsou nyní v src/modules/vehicle_hub/routers_v1/reminders.py
# Router je zaregistrován pod /api/v1/reminders


# ============= PUBLIC FILE SERVER =============
# POZNÁMKA: /web mount je až na konci, PO všech routerech, aby neblokoval API routes

# Veřejná cesta k sdíleným souborům
public_path = Path(__file__).parent.parent.parent / "public_share"
public_path.mkdir(parents=True, exist_ok=True)

@app.get("/public/", response_class=HTMLResponse)
@app.get("/public/{path:path}", response_class=HTMLResponse)
def public_file_list(path: str = ""):
    """Zobrazí seznam souborů a složek v public_share"""
    # Normalizace cesty - odstranit koncové lomítko
    path_clean = path.strip("/") if path else ""
    
    # Rozdělení na části
    path_parts = [p for p in path_clean.split("/") if p and p != "." and p != ".."]
    target_path = public_path
    if path_parts:
        target_path = public_path / "/".join(path_parts)
    
    # Bezpečnostní kontrola - zabránit directory traversal
    try:
        target_path = target_path.resolve()
        if not str(target_path).startswith(str(public_path.resolve())):
            raise HTTPException(status_code=403, detail="Neplatná cesta")
    except:
        raise HTTPException(status_code=404, detail="Cesta nenalezena")
    
    if not target_path.exists():
        raise HTTPException(status_code=404, detail="Cesta neexistuje")
    
    # Pokud je to soubor, přesměrujeme na static files
    if target_path.is_file():
        return FileResponse(target_path)
    
    # Generování HTML seznamu pro složku
    items = []
    try:
        for item in sorted(target_path.iterdir()):
            if item.name.startswith('.'):
                continue  # Skrýt skryté soubory
            
            rel_path = str(item.relative_to(public_path)).replace("\\", "/")
            size = ""
            if item.is_file():
                size_bytes = item.stat().st_size
                if size_bytes < 1024:
                    size = f"{size_bytes} B"
                elif size_bytes < 1024 * 1024:
                    size = f"{size_bytes / 1024:.1f} KB"
                else:
                    size = f"{size_bytes / (1024 * 1024):.1f} MB"
            
            items.append({
                "name": item.name,
                "path": rel_path,
                "is_dir": item.is_dir(),
                "size": size,
                "modified": datetime.fromtimestamp(item.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            })
    except PermissionError:
        raise HTTPException(status_code=403, detail="Přístup zamítnut")
    
    # Breadcrumb navigace
    breadcrumb = '<a href="/public/">🏠 Kořen</a>'
    current_breadcrumb_path = ""
    for part in path_parts:
        current_breadcrumb_path += "/" + part
        breadcrumb += f' / <a href="/public{current_breadcrumb_path}/">{part}</a>'
    
    # HTML šablona
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Veřejné soubory - TooZ Hub 2</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }}
            .container {{
                max-width: 1200px;
                margin: 0 auto;
                background: white;
                border-radius: 12px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
                overflow: hidden;
            }}
            .header {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 30px;
                text-align: center;
            }}
            .header h1 {{
                font-size: 2em;
                margin-bottom: 10px;
            }}
            .breadcrumb {{
                background: #f8f9fa;
                padding: 15px 30px;
                border-bottom: 1px solid #dee2e6;
                font-size: 14px;
            }}
            .breadcrumb a {{
                color: #667eea;
                text-decoration: none;
            }}
            .breadcrumb a:hover {{
                text-decoration: underline;
            }}
            .file-list {{
                padding: 30px;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
            }}
            th {{
                background: #f8f9fa;
                padding: 15px;
                text-align: left;
                font-weight: 600;
                color: #495057;
                border-bottom: 2px solid #dee2e6;
            }}
            td {{
                padding: 15px;
                border-bottom: 1px solid #f0f0f0;
            }}
            tr:hover {{
                background: #f8f9fa;
            }}
            .folder {{
                color: #ff9800;
                font-weight: bold;
            }}
            .folder::before {{
                content: "📁 ";
            }}
            .file {{
                color: #2196F3;
            }}
            .file::before {{
                content: "📄 ";
            }}
            a {{
                color: inherit;
                text-decoration: none;
            }}
            a:hover {{
                text-decoration: underline;
            }}
            .size {{
                color: #6c757d;
                font-size: 0.9em;
            }}
            .modified {{
                color: #6c757d;
                font-size: 0.9em;
            }}
            .empty {{
                text-align: center;
                padding: 60px 20px;
                color: #6c757d;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📁 Veřejné soubory</h1>
                <p>TooZ Hub 2 - Public File Server</p>
            </div>
            <div class="breadcrumb">
                {breadcrumb}
            </div>
            <div class="file-list">
    """
    
    if items:
        html += """
                <table>
                    <thead>
                        <tr>
                            <th>Název</th>
                            <th>Velikost</th>
                            <th>Upraveno</th>
                        </tr>
                    </thead>
                    <tbody>
        """
        
        for item in items:
            if item["is_dir"]:
                link = f'/public/{item["path"]}/'
                html += f"""
                        <tr>
                            <td class="folder"><a href="{link}">{item["name"]}</a></td>
                            <td class="size">-</td>
                            <td class="modified">{item["modified"]}</td>
                        </tr>
                """
            else:
                link = f'/public/{item["path"]}'
                html += f"""
                        <tr>
                            <td class="file"><a href="{link}" target="_blank">{item["name"]}</a></td>
                            <td class="size">{item["size"]}</td>
                            <td class="modified">{item["modified"]}</td>
                        </tr>
                """
        
        html += """
                    </tbody>
                </table>
        """
    else:
        html += """
                <div class="empty">
                    <p>📂 Tato složka je prázdná</p>
                </div>
        """
    
    html += """
            </div>
        </div>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html)

# Mount static files pro konkrétní soubory (pod endpointy, aby neměl přednost před route)
try:
    if public_path.exists():
        app.mount("/public", StaticFiles(directory=str(public_path)), name="public_static")
        print(f"[SERVER] Public file server zaregistrován: /public/ (directory: {public_path})")
except (OSError, ValueError) as e:
    print(f"[SERVER] Warning: Could not mount public directory: {e}")

# Mount admin static files (jako statické soubory, podobně jako /web)
try:
    admin_web_path = Path(__file__).parent.parent.parent / "web_admin"
    if admin_web_path.exists():
        app.mount("/web_admin", StaticFiles(directory=str(admin_web_path), html=True), name="web_admin")
        print(f"[SERVER] Admin web zaregistrován: /web_admin/ (directory: {admin_web_path})")
        # Zachovat /admin-static pro zpětnou kompatibilitu (CSS/JS soubory)
        app.mount("/admin-static", StaticFiles(directory=str(admin_web_path)), name="admin_static")
        print(f"[SERVER] Admin static files zaregistrovány: /admin-static/ (directory: {admin_web_path})")
except (OSError, ValueError) as e:
    print(f"[SERVER] Warning: Could not mount admin web directory: {e}")


# ============= WEB INTERFACE (MOUNT NA KONCI) =============
# POZNÁMKA: StaticFiles mounty musí být až na konci, PO všech routerech
# aby neblokovaly API routes

# Mount web directory jako statické soubory
try:
    web_path = Path(__file__).parent.parent.parent / "web"
    if web_path.exists():
        app.mount("/web", StaticFiles(directory=str(web_path), html=True), name="web")
        print(f"[SERVER] Web interface zaregistrován: /web/ (directory: {web_path})")
    else:
        print(f"[SERVER] WARNING: Web directory not found: {web_path}")
except (OSError, ValueError) as e:
    print(f"[SERVER] Warning: Could not mount web directory: {e}")

# ============= ROOT & HEALTH =============

@app.get("/")
def root():
    """Root endpoint - redirect to web interface"""
    return RedirectResponse(url="/web/index.html", status_code=302)


@app.get("/api")
def api_root():
    """API root endpoint"""
    try:
        from VERSION import __version__, __version_name__, __build_date__, __update_info__
        version = __version__
        version_name = __version_name__
        build_date = __build_date__
        update_info = __update_info__
    except ImportError:
        version = APP_VERSION
        version_name = APP_VERSION_NAME
        build_date = BUILD_DATE
        update_info = UPDATE_INFO
    
    return {
        "message": "TooZ Hub 2 API",
        "version": version,
        "version_name": version_name,
        "build_date": build_date,
        "update_info": update_info,
        "environment": ENVIRONMENT,
        "features": {
            "jwt_auth": True,
            "bcrypt_passwords": True,
            "vehicles": True,
            "vin_decoder": True,
            "ai_features": ENABLE_AI_FEATURES,
            "customer_commands": ENABLE_CUSTOMER_COMMANDS,
            "autopilot_api": ENABLE_AUTOPILOT_API
        },
        "endpoints": {
            "register": "/user/register",
            "register_service_request": "/user/register/service-request",
            "login": "/user/login",
            "me": "/user/me",
            "me_export": "/user/me/export",
            "me_delete": "/user/me",
            "ares": "/user/ares?ico=ICO",
            "support": "/user/support",
            "vehicles": "/api/v1/vehicles",
            "decode_vin": "/api/vehicles/decode-vin"
        },
        "web_interface": "/web/index.html" if Path(__file__).parent.parent.parent.joinpath("web").exists() else None
    }


@app.get("/health")
@app.options("/health")  # Explicitní OPTIONS pro CORS preflight
def health_check():
    """Health check endpoint - nevyžaduje autentizaci, není rate-limited"""
    try:
        from VERSION import __version__, __version_name__, __build_date__, __update_info__
        version = __version__
        version_name = __version_name__
        build_date = __build_date__
        update_info = __update_info__
    except ImportError:
        version = APP_VERSION
        version_name = APP_VERSION_NAME
        build_date = BUILD_DATE
        update_info = UPDATE_INFO
    
    return {
        "status": "ok",
        "project": "TOOZHUB2",
        "service": "TooZ Hub 2 API",
        "version": version,
        "version_name": version_name,
        "build_date": build_date,
        "update_info": update_info,
        "environment": ENVIRONMENT,
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/health/config")
@app.options("/health/config")  # Explicitní OPTIONS pro CORS preflight
def health_config():
    """
    Config health check endpoint - vrací stav konfigurace (bez hodnot)
    Nevyžaduje autentizaci, není rate-limited
    """
    try:
        from src.core.config_validator import validate_config
        is_valid, config_status, missing_keys = validate_config()
        
        return {
            "status": "ok" if is_valid else "warning",
            "environment": config_status["environment"],
            "jwt_configured": config_status["jwt_configured"],
            "dataovo_configured": config_status["dataovo_configured"],
            "smtp_configured": config_status["smtp_configured"],
            "env_file_exists": config_status["env_file_exists"],
            "env_file_readable": config_status["env_file_readable"],
            "env_file_path": config_status["env_file_path"],
            "missing_keys": missing_keys,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }


@app.get("/version")
def get_version():
    """Endpoint pro získání informací o verzi projektu"""
    try:
        from src.server.version import get_version_info
        return get_version_info()
    except Exception as e:
        # Fallback na VERSION.py
        try:
            from VERSION import __version__, __version_name__
            from datetime import datetime
            return {
                "project": "TooZ Hub 2",
                "version": __version__,
                "build_time": datetime.now().isoformat()
            }
        except ImportError:
            return {
                "project": "TooZ Hub 2",
                "version": APP_VERSION,
                "build_time": datetime.now().isoformat()
            }


# Debug endpoint pro vypsání rout (jen pro autentizované uživatele)
@app.get("/api/_debug/routes")
def debug_routes(current_user_email: str = Depends(get_current_user_email)):
    """
    Vrátí seznam registrovaných routes (jen pro autentizované uživatele)
    """
    routes_list = []
    for route in app.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            for method in sorted(route.methods):
                if method in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS']:
                    routes_list.append({
                        'method': method,
                        'path': route.path
                    })
    
    # Seřadit podle path
    routes_list.sort(key=lambda x: x['path'])
    
    return {
        'total_routes': len(routes_list),
        'routes': routes_list,
        'api_v1_routes': [r for r in routes_list if '/api/v1/' in r['path']],
        'vehicles_routes': [r for r in routes_list if '/vehicles' in r['path']],
        'user_email': current_user_email
    }


# Debug endpoint pro DB statistiky (jen pro autentizované uživatele)
@app.get("/api/_debug/db_stats")
def debug_db_stats(
    current_user_email: str = Depends(get_current_user_email),
    db=Depends(get_db)
):
    """
    Vrátí statistiky databáze (jen pro autentizované uživatele)
    """
    import os
    from pathlib import Path
    
    # Získat DB URL a cwd
    db_url = os.getenv("DATABASE_URL") or os.getenv("VEHICLE_DB_URL", "sqlite:///./vehicles.db")
    cwd = str(Path.cwd())
    
    # Pokud je SQLite, zjistit absolutní cestu k souboru
    if db_url.startswith("sqlite"):
        if db_url.startswith("sqlite:///"):
            db_path = db_url.replace("sqlite:///", "")
            if not os.path.isabs(db_path):
                db_path = os.path.join(cwd, db_path)
        else:
            db_path = db_url
        db_exists = os.path.exists(db_path)
        db_size = os.path.getsize(db_path) if db_exists else 0
    else:
        db_path = db_url
        db_exists = True
        db_size = None
    
    # Načíst statistiky z databáze
    try:
        from src.modules.vehicle_hub.models import Vehicle as VehicleModel, Customer
        
        # Celkový počet vozidel
        vehicles_total = db.query(VehicleModel).count()
        
        # Počet vozidel pro aktuálního uživatele
        vehicles_for_user = db.query(VehicleModel).filter(
            VehicleModel.user_email == current_user_email
        ).count()
        
        # Počet vozidel pro aktuálního uživatele s tenant_id
        current_user = db.query(Customer).filter(Customer.email == current_user_email).first()
        vehicles_for_user_with_tenant = 0
        if current_user and hasattr(current_user, 'tenant_id') and current_user.tenant_id:
            vehicles_for_user_with_tenant = db.query(VehicleModel).filter(
                VehicleModel.user_email == current_user_email,
                VehicleModel.tenant_id == current_user.tenant_id
            ).count()
        
        # Počet uživatelů
        users_total = db.query(Customer).count()
        
        # Získat user_id vozidel pro debug
        vehicles_user_ids = db.query(VehicleModel.user_email).distinct().all()
        vehicles_user_emails = [email[0] for email in vehicles_user_ids]
        
        # Získat tenant_id vozidel pro debug
        vehicles_tenant_ids = db.query(VehicleModel.tenant_id).distinct().all()
        vehicles_tenant_ids_list = [tid[0] for tid in vehicles_tenant_ids if tid[0] is not None]
        
        return {
            "db_url": db_url,
            "db_path": db_path,
            "db_exists": db_exists,
            "db_size": db_size,
            "cwd": cwd,
            "vehicles_total": vehicles_total,
            "vehicles_for_user": vehicles_for_user,
            "vehicles_for_user_with_tenant": vehicles_for_user_with_tenant,
            "users_total": users_total,
            "current_user_email": current_user_email,
            "current_user_tenant_id": getattr(current_user, 'tenant_id', None) if current_user else None,
            "vehicles_user_emails": vehicles_user_emails,
            "vehicles_tenant_ids": vehicles_tenant_ids_list
        }
    except Exception as e:
        import traceback
        return {
            "db_url": db_url,
            "db_path": db_path,
            "db_exists": db_exists,
            "db_size": db_size,
            "cwd": cwd,
            "error": str(e),
            "traceback": traceback.format_exc()
        }


@app.get("/version/history")
def get_version_history(db=Depends(get_db)):
    """Endpoint pro získání historie verzí"""
    try:
        from src.modules.vehicle_hub.models import VersionHistory
        
        # Načtení všech záznamů z historie verzí (nejnovější první)
        history = db.query(VersionHistory).order_by(VersionHistory.applied_at.desc()).all()
        
        return {
            "history": [
                {
                    "id": entry.id,
                    "version": entry.version,
                    "description": entry.description,
                    "applied_at": entry.applied_at.isoformat() if entry.applied_at else None
                }
                for entry in history
            ],
            "total": len(history)
        }
    except Exception as e:
        # Pokud tabulka ještě neexistuje, vrať prázdnou historii
        print(f"[VERSION] Warning: Nelze načíst historii verzí: {e}")
        return {
            "history": [],
            "total": 0,
            "error": "Historie verzí není dostupná"
        }


# Inicializace historie verzí při startu serveru
def init_version_history():
    """Inicializuje historii verzí - zapíše aktuální verzi, pokud tam není"""
    try:
        from src.server.version import read_version, log_version_update
        from src.modules.vehicle_hub.models import VersionHistory
        
        db = SessionLocal()
        try:
            # Načtení aktuální verze
            current_version = read_version()
            
            # Kontrola, zda už verze není v historii
            existing = db.query(VersionHistory).filter(VersionHistory.version == current_version).first()
            if not existing:
                # Zapsání verze do historie
                log_version_update(
                    db=db,
                    version=current_version,
                    description="Kompletní redesign UI + zavedení verzování"
                )
                print(f"[SERVER] OK: Verze {current_version} zapisana do historie verzi")
            else:
                print(f"[SERVER] INFO: Verze {current_version} uz je v historii verzi")
        finally:
            db.close()
    except Exception as e:
        print(f"[SERVER] Warning: Nelze inicializovat historii verzí: {e}")
        import traceback
        traceback.print_exc()

# Spustit inicializaci historie verzí
try:
    init_version_history()
except Exception as e:
    print(f"[SERVER] Warning: Chyba při inicializaci historie verzí: {e}")

# =============================================================================
# DATABASE INFO LOGGING (při startu)
# =============================================================================
print("=" * 60)
print("[DATABASE] Database Configuration")
print("=" * 60)
try:
    from src.modules.vehicle_hub.database import engine
    import os
    from pathlib import Path
    
    print(f"[DATABASE] Engine URL: {engine.url}")
    print(f"[DATABASE] Current working directory: {os.getcwd()}")
    
    if hasattr(engine.url, 'database') and engine.url.database:
        db_path = engine.url.database
        if os.path.isabs(db_path):
            abs_path = db_path
        else:
            abs_path = os.path.abspath(db_path)
        print(f"[DATABASE] Database path (absolute): {abs_path}")
        if os.path.exists(abs_path):
            print(f"[DATABASE] ✅ Database file exists ({os.path.getsize(abs_path)} bytes)")
        else:
            print(f"[DATABASE] ⚠️  Database file does NOT exist: {abs_path}")
    else:
        print(f"[DATABASE] Database path: {engine.url}")
except Exception as e:
    print(f"[DATABASE] ERROR při získávání DB info: {e}")
print("=" * 60)
print()

if __name__ == "__main__":
    import uvicorn
    
    try:
        from VERSION import __version__, __version_name__, __build_date__, __update_info__
        version = __version__
        version_name = __version_name__
        build_date = __build_date__
        update_info = __update_info__
    except ImportError:
        version = APP_VERSION
        version_name = APP_VERSION_NAME
        build_date = BUILD_DATE
        update_info = UPDATE_INFO
    
    print("=" * 60)
    print(f"[SERVER] 🚀 TooZ Hub 2 API Server")
    print(f"[SERVER] 📦 Verze: {version} ({version_name})")
    print(f"[SERVER] 📅 Datum buildu: {build_date}")
    print(f"[SERVER] 🔄 Aktualizace: {update_info}")
    print("=" * 60)
    print(f"[SERVER] Spouštím server na {HOST}:{PORT}")
    print(f"[SERVER] Režim: {ENVIRONMENT}")
    print(f"[SERVER] CORS origins: {ALLOWED_ORIGINS}")
    print("")
    
    # Startup verification: vypiš všechny /api/ routes
    print("\n=== API ROUTES VERIFICATION ===")
    api_routes = []
    for route in app.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            if '/api/' in route.path:
                for method in sorted(route.methods):
                    if method in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']:
                        api_routes.append(f"{method:6} {route.path}")
    
    if api_routes:
        print(f"Found {len(api_routes)} API routes:")
        for route in sorted(api_routes):
            print(f"  {route}")
    else:
        print("WARNING: No API routes found!")
    
    # Verify critical routes
    critical_routes = [
        '/api/v1/vehicles',
        '/api/v1/reminders',
        '/api/v1/reservations/my',
        '/api/v1/license/status'
    ]
    found_critical = []
    for route in app.routes:
        if hasattr(route, 'path'):
            for critical in critical_routes:
                if route.path == critical or route.path.startswith(critical + '/'):
                    found_critical.append(critical)
                    break
    
    missing = set(critical_routes) - set(found_critical)
    if missing:
        print(f"\nWARNING: Missing critical routes: {missing}")
    else:
        print(f"\n✓ All critical routes found: {critical_routes}")
    
    # TODO: Temporary logging - verify license routes are registered
    print("\n=== LICENSE ROUTES VERIFICATION ===")
    license_routes = []
    for route in app.routes:
        if hasattr(route, 'path') and hasattr(route, 'methods'):
            if 'license' in route.path.lower():
                for method in sorted(route.methods):
                    if method in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']:
                        license_routes.append(f"{method:6} {route.path}")
    
    if license_routes:
        print(f"Found {len(license_routes)} license route(s):")
        for route in sorted(license_routes):
            print(f"  {route}")
        # Verify exact path exists
        if any('/api/v1/license/status' in r for r in license_routes):
            print("✓ /api/v1/license/status endpoint is registered")
        else:
            print("❌ WARNING: /api/v1/license/status NOT FOUND!")
    else:
        print("❌ WARNING: No license routes found!")
    
    print("=" * 40)
    print("")
    
    uvicorn.run(app, host=HOST, port=PORT)
