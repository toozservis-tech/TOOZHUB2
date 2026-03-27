from __future__ import annotations

import asyncio
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.core.config import (
    ALLOWED_ORIGINS,
    ENABLE_AI_FEATURES,
    ENABLE_AUTOPILOT_API,
    ENABLE_CUSTOMER_COMMANDS,
    ENVIRONMENT,
    HOST,
    JWT_SECRET_KEY,
    PORT,
)
from src.core.security_middleware import AntiTamperingMiddleware, RateLimitMiddleware, SecurityHeadersMiddleware
from src.modules.vehicle_hub.account_state import ensure_customer_account_state_schema
from src.modules.vehicle_hub.database import SessionLocal, engine
from src.modules.vehicle_hub.schema_management import get_capabilities
from src.server.control_center_jobs import is_job_paused
from src.server.main_helpers import APP_VERSION, APP_VERSION_NAME, BUILD_DATE, UPDATE_INFO
from src.server.routers import instances
from src.server.routers.system import public_path, router as system_router
from src.server.routers.user_account import router as user_account_router
from src.server.routers.user_auth import router as user_auth_router
from src.server.routers.user_security import router as user_security_router
from src.server.runtime_settings import get_runtime_setting_bool


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

ENABLE_FILE_BROWSER = _env_bool("ENABLE_FILE_BROWSER", False)

_reminder_notification_task: asyncio.Task | None = None
_license_subscription_task: asyncio.Task | None = None

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


if ENVIRONMENT == "production":
    default_secret = "toozhub2-dev-secret-key-change-in-production"
    if JWT_SECRET_KEY == default_secret:
        print("[SERVER] ERROR: KRITICKA CHYBA BEZPECNOSTI!")
        print("[SERVER] V produkci musí být nastaven JWT_SECRET_KEY v .env souboru!")
        print("[SERVER] Výchozí hodnota není bezpečná.")
        print('[SERVER] Vygenerujte nový klíč pomocí: python -c "import secrets; print(secrets.token_urlsafe(32))"')
        raise SystemExit(1)
    print("[SERVER] OK: JWT_SECRET_KEY je nastaven (neni vychozi hodnota)")

try:
    from src.core.config_validator import log_config_status

    config_valid, config_status, missing_keys = log_config_status()
    if ENVIRONMENT == "production" and not config_valid:
        if "JWT_SECRET_KEY" in missing_keys:
            print("[SERVER] FATAL: Aplikace nemůže běžet bez JWT_SECRET_KEY v produkci!")
            raise SystemExit(1)
        print("[SERVER] WARNING: Některé klíče chybí, ale aplikace může běžet")
except Exception as exc:
    print(f"[SERVER] WARNING: Chyba při validaci konfigurace: {exc}")
    import traceback

    traceback.print_exc()


async def _reminder_notification_worker() -> None:
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


def _is_maintenance_bypass_path(path: str) -> bool:
    path_lc = (path or "").lower()
    if path_lc in _MAINTENANCE_BYPASS_EXACT:
        return True
    if any(path_lc.startswith(prefix) for prefix in _MAINTENANCE_BYPASS_RUNTIME_PREFIXES):
        return True
    return any(path_lc.startswith(prefix) for prefix in _MAINTENANCE_BYPASS_PREFIXES)


def _register_exception_handler(app: FastAPI) -> None:
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        import traceback

        error_traceback = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        print(f"[ERROR] Neošetřená výjimka: {type(exc).__name__}: {str(exc)}")
        print(f"[ERROR] Path: {request.url.path}")
        print(f"[ERROR] Method: {request.method}")
        print(f"[ERROR] Traceback:\n{error_traceback}")
        return JSONResponse(
            status_code=500,
            content={
                "detail": f"Interní chyba serveru: {str(exc)}",
                "type": type(exc).__name__,
                "path": request.url.path,
            },
        )


def _register_middlewares(app: FastAPI) -> None:
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
        allow_headers=["*", "Authorization", "Content-Type", "Accept"],
        expose_headers=["*"],
    )
    app.add_middleware(AntiTamperingMiddleware)
    app.add_middleware(RateLimitMiddleware, calls=100, period=60)

    @app.middleware("http")
    async def maintenance_mode_middleware(request: Request, call_next):
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
        path = (request.url.path or "").lower()
        is_frontend_asset = (
            path.startswith("/web_admin")
            or path.startswith("/admin-static")
            or path == "/web"
            or path.startswith("/web/")
        )

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
            for header in ("etag", "last-modified"):
                if header in response.headers:
                    del response.headers[header]
        return response


def _include_feature_routers(app: FastAPI) -> None:
    try:
        from src.modules.vehicle_hub.decoder.router import router as decoder_router

        app.include_router(decoder_router)
        print("[SERVER] Vehicle Decoder Engine router zaregistrován: /api/vehicles/decode-vin, /api/vehicles/decode-plate")
    except ImportError as exc:
        print(f"[SERVER] Warning: Vehicle Decoder Engine není dostupný: {exc}")

    if ENABLE_FILE_BROWSER:
        try:
            from src.server.file_browser import router as file_browser_router

            app.include_router(file_browser_router)
            print("[SERVER] File Browser zaregistrován: /files/ (ENABLE_FILE_BROWSER=1)")
        except ImportError as exc:
            print(f"[SERVER] Warning: File Browser není dostupný: {exc}")
    else:
        print("[SERVER] File Browser router přeskočen (ENABLE_FILE_BROWSER=false)")

    try:
        from src.modules.vehicle_hub.routers_v1 import api_router as v1_api_router

        app.include_router(v1_api_router)
        print("[SERVER] API v1 routery zaregistrovány: /api/v1/")
    except ImportError as exc:
        print(f"[SERVER] Warning: API v1 routery nejsou dostupné: {exc}")
        import traceback

        traceback.print_exc()

    if ENABLE_AUTOPILOT_API:
        try:
            from src.modules.vehicle_hub.routers_v1.autopilot import router as autopilot_router

            app.include_router(autopilot_router)
            print("[SERVER] Autopilot M2M API router zaregistrován: /api/autopilot/")
        except ImportError as exc:
            print(f"[SERVER] Warning: Autopilot M2M API router není dostupný: {exc}")
            import traceback

            traceback.print_exc()
    else:
        print("[SERVER] Autopilot M2M API router přeskočen (ENABLE_AUTOPILOT_API=false)")

    if ENABLE_CUSTOMER_COMMANDS:
        try:
            from src.modules.vehicle_hub.routers_v1.customer_commands import router as customer_commands_router

            app.include_router(customer_commands_router)
            print("[SERVER] Customer Commands API router zaregistrován: /api/customer-commands/")
        except ImportError as exc:
            print(f"[SERVER] Warning: Customer Commands API router není dostupný: {exc}")
            import traceback

            traceback.print_exc()
    else:
        print("[SERVER] Customer Commands API router přeskočen (ENABLE_CUSTOMER_COMMANDS=false)")

    try:
        from src.server.admin_api import router as admin_api_router

        app.include_router(admin_api_router)
        print("[SERVER] Admin API router zaregistrován: /admin-api/")
    except ImportError as exc:
        print(f"[SERVER] Warning: Admin API router není dostupný: {exc}")
        import traceback

        traceback.print_exc()

    app.include_router(instances.router)
    print("[SERVER] Instances API router zaregistrován: /api/instances/")

    if ENABLE_AI_FEATURES:
        try:
            from src.modules.ai_features.routers import router as ai_features_router

            app.include_router(ai_features_router)
            print("[SERVER] AI Features router zaregistrován: /api/v1/ai-features/")
        except ImportError as exc:
            print(f"[SERVER] Warning: AI Features router není dostupný: {exc}")
            import traceback

            traceback.print_exc()
    else:
        print("[SERVER] AI Features router přeskočen (ENABLE_AI_FEATURES=false)")

    app.include_router(user_auth_router)
    app.include_router(user_account_router)
    app.include_router(user_security_router)
    app.include_router(system_router)


def _mount_static_directories(app: FastAPI) -> None:
    try:
        if public_path.exists():
            app.mount("/public", StaticFiles(directory=str(public_path)), name="public_static")
            print(f"[SERVER] Public file server zaregistrován: /public/ (directory: {public_path})")
    except (OSError, ValueError) as exc:
        print(f"[SERVER] Warning: Could not mount public directory: {exc}")

    try:
        admin_web_path = Path(__file__).parent.parent.parent / "web_admin"
        if admin_web_path.exists():
            app.mount("/web_admin", StaticFiles(directory=str(admin_web_path), html=True), name="web_admin")
            print(f"[SERVER] Admin web zaregistrován: /web_admin/ (directory: {admin_web_path})")
            app.mount("/admin-static", StaticFiles(directory=str(admin_web_path)), name="admin_static")
            print(f"[SERVER] Admin static files zaregistrovány: /admin-static/ (directory: {admin_web_path})")
    except (OSError, ValueError) as exc:
        print(f"[SERVER] Warning: Could not mount admin web directory: {exc}")

    try:
        web_path = Path(__file__).parent.parent.parent / "web"
        if web_path.exists():
            app.mount("/web", StaticFiles(directory=str(web_path), html=True), name="web")
            print(f"[SERVER] Web interface zaregistrován: /web/ (directory: {web_path})")
        else:
            print(f"[SERVER] WARNING: Web directory not found: {web_path}")
    except (OSError, ValueError) as exc:
        print(f"[SERVER] Warning: Could not mount web directory: {exc}")


def _register_lifecycle_hooks(app: FastAPI) -> None:
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
            print(f"[REMINDERS_WORKER] started (interval={REMINDER_NOTIFICATION_WORKER_INTERVAL_SEC}s)")

        if not ENABLE_LICENSE_SUBSCRIPTION_WORKER:
            print("[LICENSE_SUBSCRIPTION_WORKER] disabled (ENABLE_LICENSE_SUBSCRIPTION_WORKER=0)")
        elif _license_subscription_task is None:
            _license_subscription_task = asyncio.create_task(_license_subscription_worker())
            print(f"[LICENSE_SUBSCRIPTION_WORKER] started (interval={LICENSE_SUBSCRIPTION_WORKER_INTERVAL_SEC}s)")

    @app.on_event("shutdown")
    async def _stop_background_workers() -> None:
        global _reminder_notification_task, _license_subscription_task
        if _reminder_notification_task is not None:
            _reminder_notification_task.cancel()
            try:
                await _reminder_notification_task
            except asyncio.CancelledError:
                pass
            finally:
                _reminder_notification_task = None
            print("[REMINDERS_WORKER] stopped")

        if _license_subscription_task is not None:
            _license_subscription_task.cancel()
            try:
                await _license_subscription_task
            except asyncio.CancelledError:
                pass
            finally:
                _license_subscription_task = None
            print("[LICENSE_SUBSCRIPTION_WORKER] stopped")


def create_app() -> FastAPI:
    app = FastAPI(title="TooZ Hub 2 API", version=APP_VERSION)
    _register_exception_handler(app)
    _register_middlewares(app)
    _include_feature_routers(app)
    _mount_static_directories(app)
    _register_lifecycle_hooks(app)
    return app


def init_version_history() -> None:
    try:
        from src.modules.vehicle_hub.models import VersionHistory
        from src.server.version import log_version_update, read_version

        db = SessionLocal()
        try:
            current_version = read_version()
            existing = db.query(VersionHistory).filter(VersionHistory.version == current_version).first()
            if not existing:
                log_version_update(
                    db=db,
                    version=current_version,
                    description="Kompletní redesign UI + zavedení verzování",
                )
                print(f"[SERVER] OK: Verze {current_version} zapisana do historie verzi")
            else:
                print(f"[SERVER] INFO: Verze {current_version} uz je v historii verzi")
        finally:
            db.close()
    except Exception as exc:
        print(f"[SERVER] Warning: Nelze inicializovat historii verzí: {exc}")
        import traceback

        traceback.print_exc()


def log_database_info() -> None:
    print("=" * 60)
    print("[DATABASE] Database Configuration")
    print("=" * 60)
    try:
        print(f"[DATABASE] Engine URL: {engine.url}")
        print(f"[DATABASE] Current working directory: {os.getcwd()}")

        if hasattr(engine.url, "database") and engine.url.database:
            db_path = engine.url.database
            abs_path = db_path if os.path.isabs(db_path) else os.path.abspath(db_path)
            print(f"[DATABASE] Database path (absolute): {abs_path}")
            if os.path.exists(abs_path):
                print(f"[DATABASE] ✅ Database file exists ({os.path.getsize(abs_path)} bytes)")
            else:
                print(f"[DATABASE] ⚠️  Database file does NOT exist: {abs_path}")
        else:
            print(f"[DATABASE] Database path: {engine.url}")
    except Exception as exc:
        print(f"[DATABASE] ERROR při získávání DB info: {exc}")
    print("=" * 60)
    print()


def initialize_process_runtime() -> None:
    try:
        init_version_history()
    except Exception as exc:
        print(f"[SERVER] Warning: Chyba při inicializaci historie verzí: {exc}")
    log_database_info()


def run_server(app: FastAPI) -> None:
    import uvicorn

    version = APP_VERSION
    version_name = APP_VERSION_NAME
    build_date = BUILD_DATE
    update_info = UPDATE_INFO

    print("=" * 60)
    print("[SERVER] 🚀 TooZ Hub 2 API Server")
    print(f"[SERVER] 📦 Verze: {version} ({version_name})")
    print(f"[SERVER] 📅 Datum buildu: {build_date}")
    print(f"[SERVER] 🔄 Aktualizace: {update_info}")
    print("=" * 60)
    print(f"[SERVER] Spouštím server na {HOST}:{PORT}")
    print(f"[SERVER] Režim: {ENVIRONMENT}")
    print(f"[SERVER] CORS origins: {ALLOWED_ORIGINS}")
    print("")

    print("\n=== API ROUTES VERIFICATION ===")
    api_routes = []
    for route in app.routes:
        if hasattr(route, "path") and hasattr(route, "methods"):
            if "/api/" in route.path:
                for method in sorted(route.methods):
                    if method in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
                        api_routes.append(f"{method:6} {route.path}")

    if api_routes:
        print(f"Found {len(api_routes)} API routes:")
        for route in sorted(api_routes):
            print(f"  {route}")
    else:
        print("WARNING: No API routes found!")

    critical_routes = [
        "/api/v1/vehicles",
        "/api/v1/reminders",
        "/api/v1/reservations/my",
        "/api/v1/license/status",
    ]
    found_critical = []
    for route in app.routes:
        if hasattr(route, "path"):
            for critical in critical_routes:
                if route.path == critical or route.path.startswith(critical + "/"):
                    found_critical.append(critical)
                    break

    missing = set(critical_routes) - set(found_critical)
    if missing:
        print(f"\nWARNING: Missing critical routes: {missing}")
    else:
        print(f"\n✓ All critical routes found: {critical_routes}")

    print("\n=== LICENSE ROUTES VERIFICATION ===")
    license_routes = []
    for route in app.routes:
        if hasattr(route, "path") and hasattr(route, "methods"):
            if "license" in route.path.lower():
                for method in sorted(route.methods):
                    if method in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
                        license_routes.append(f"{method:6} {route.path}")

    if license_routes:
        print(f"Found {len(license_routes)} license route(s):")
        for route in sorted(license_routes):
            print(f"  {route}")
        if any("/api/v1/license/status" in r for r in license_routes):
            print("✓ /api/v1/license/status endpoint is registered")
        else:
            print("❌ WARNING: /api/v1/license/status NOT FOUND!")
    else:
        print("❌ WARNING: No license routes found!")

    print("=" * 40)
    print("")
    uvicorn.run(app, host=HOST, port=PORT)
