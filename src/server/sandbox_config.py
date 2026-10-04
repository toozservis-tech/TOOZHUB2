"""Fail-closed configuration for the separate App Review / TestFlight service.

This module deliberately has no imports from the application. Validate the
destination and credentials before any module can create a database engine.
"""
from pathlib import Path
from urllib.parse import urlsplit
import re


def validate_sandbox_config(environment, root: Path) -> Path:
    if environment.get("SV_ISOLATED_APPLE_SANDBOX") != "1":
        raise RuntimeError("The isolated Sandbox service requires explicit activation.")
    if (environment.get("APPLE_IAP_ENVIRONMENT") != "Sandbox"
            or environment.get("APPLE_IAP_ENABLED") != "1"):
        raise RuntimeError("This service accepts only enabled Apple Sandbox billing.")
    if (root / ".env").exists():
        raise RuntimeError("The Sandbox service must not load a checkout .env file.")
    if (environment.get("DATABASE_SCHEMA") or environment.get("VEHICLE_DB_URL")):
        raise RuntimeError("Legacy or shared database configuration is forbidden.")

    configured_root = Path(environment.get("SANDBOX_DATA_ROOT", "/var/data"))
    data_root = configured_root.resolve()
    if not configured_root.is_absolute() or str(data_root) in {"/", "/tmp", str(root.resolve())}:
        raise RuntimeError("Configure a dedicated persistent Sandbox data directory.")
    expected_database = data_root / "sv-sandbox.sqlite3"
    if (environment.get("DATABASE_URL") != f"sqlite:///{expected_database}"
            or expected_database.is_symlink()
            or environment.get("DATA_DIR_PATH") != str(data_root / "files")):
        raise RuntimeError("Database and private files must use the dedicated Sandbox disk.")

    # Reject inherited production providers, email/push delivery and bypasses.
    forbidden_prefixes = ("SMTP_", "EMAIL_", "RESEND_", "SUPABASE_", "COMGATE_",
                          "APNS_", "VAPID_", "OPENAI_")
    forbidden_names = {"SPRAVA_VOZIDEL_ADMIN_TENANT_ID", "TOOZHUB_ADMIN_TENANT_ID",
                       "SPRAVA_VOZIDEL_ADMIN_FORCE_PREMIUM", "TOOZHUB_ADMIN_FORCE_PREMIUM"}
    if any(value and (name.startswith(forbidden_prefixes) or name in forbidden_names)
           for name, value in environment.items()):
        raise RuntimeError("Production providers and license bypasses are forbidden in Sandbox.")
    secret = environment.get("JWT_SECRET_KEY", "")
    if len(secret) < 40 or secret == "sprava-vozidel-dev-secret-change-in-production":
        raise RuntimeError("The Sandbox service needs its own strong persistent signing secret.")
    for number in (1, 2):
        password_hash = environment.get(f"SANDBOX_CUSTOMER_{number}_PASSWORD_HASH", "")
        if not re.fullmatch(r"\$2[aby]\$1[2-6]\$[./A-Za-z0-9]{53}", password_hash):
            raise RuntimeError("Configure bcrypt password hashes for the two synthetic accounts.")
    public_url = urlsplit(environment.get("PUBLIC_API_BASE_URL", ""))
    if (public_url.scheme != "https" or not public_url.hostname
            or public_url.hostname == "app.toozservis.cz"
            or public_url.username or public_url.password or public_url.query
            or public_url.fragment or public_url.path not in {"", "/"}):
        raise RuntimeError("Sandbox requires its own HTTPS origin, distinct from production.")
    return data_root
