"""
Centrální konfigurace pro Správu vozidel
Podporuje načítání z environment variables a .env souboru
"""
import os
from pathlib import Path

from src.core.env_aliases import env_prefer_new

APP_ROOT = Path(__file__).resolve().parent.parent.parent
WORKSPACE_ROOT = APP_ROOT.parent
DEFAULT_RUNTIME_DB_PATH = WORKSPACE_ROOT / "data" / "vehicles.db"
DEFAULT_RUNTIME_DB_URL = f"sqlite:///{DEFAULT_RUNTIME_DB_PATH}"
LEGACY_APP_DATA_DB_PATH = APP_ROOT / "data" / "vehicles.db"

# Pokusit se načíst .env soubor
_env_loaded = False
_env_source = None
try:
    from dotenv import load_dotenv, dotenv_values
    from io import StringIO
    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        _env_source = str(env_path)
        # Zkusit načíst s různými kódováními (UTF-8, Windows-1250, latin-1)
        env_loaded = False
        for encoding in ['utf-8', 'windows-1250', 'cp1250', 'latin-1']:
            try:
                with open(env_path, 'r', encoding=encoding, errors='replace') as f:
                    env_content = f.read()
                # Pokud obsah vypadá rozumně (nejsou tam jen náhodné znaky), použij ho
                if env_content and len(env_content) > 10:
                    try:
                        # Načíst proměnné pomocí dotenv_values
                        env_vars = dotenv_values(stream=StringIO(env_content))
                        # Nastavit do os.environ
                        for key, value in env_vars.items():
                            if key and value is not None:
                                os.environ.setdefault(key, value)
                        _env_loaded = True
                        print(f"[CONFIG] .env soubor načten z: {env_path}")
                        break
                    except Exception:
                        # Pokud dotenv_values selže, zkusit načíst řádek po řádku
                        try:
                            for line in env_content.split('\n'):
                                line = line.strip()
                                if line and not line.startswith('#') and '=' in line:
                                    key, value = line.split('=', 1)
                                    key = key.strip()
                                    value = value.strip().strip('"').strip("'")
                                    if key:
                                        os.environ.setdefault(key, value)
                            _env_loaded = True
                            print(f"[CONFIG] .env soubor načten z: {env_path} (fallback parser)")
                            break
                        except Exception:
                            continue
            except (UnicodeDecodeError, Exception):
                continue
        
        # Pokud se nepodařilo načíst žádné kódování, zkusit standardní load_dotenv
        if not _env_loaded:
            try:
                load_dotenv(env_path)
                _env_loaded = True
                print(f"[CONFIG] .env soubor načten z: {env_path} (load_dotenv)")
            except Exception:
                # Pokud všechno selže, pokračovat bez .env souboru
                print(f"[CONFIG] WARNING: Nepodařilo se načíst .env soubor z {env_path}")
    else:
        print(f"[CONFIG] .env soubor neexistuje: {env_path}")
except ImportError:
    print("[CONFIG] WARNING: python-dotenv není nainstalován - .env soubor nebude načten")
    pass  # python-dotenv není nainstalován
except Exception as e:
    # Při jakékoliv chybě pokračovat bez .env souboru
    print(f"[CONFIG] ERROR: Chyba při načítání .env souboru: {e}")

# Export informace o načtení .env
ENV_FILE_LOADED = _env_loaded
ENV_FILE_SOURCE = _env_source

# =============================================================================
# SERVER CONFIGURATION
# =============================================================================

HOST = os.getenv("HOST", "0.0.0.0")  # 0.0.0.0 pro Cloudflare Tunnel, 127.0.0.1 pro lokální vývoj
PORT = int(os.getenv("PORT", "8000"))
ENVIRONMENT = os.getenv("ENVIRONMENT", os.getenv("APP_ENV", "development"))  # development | production

# =============================================================================
# DATABASE
# =============================================================================

# Databázová URL - source-of-truth pro backend runtime.
# Priorita:
# 1) explicitní DATABASE_URL
# 2) legacy VEHICLE_DB_URL
# 3) canonical runtime SQLite v ../data/vehicles.db
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("VEHICLE_DB_URL") or DEFAULT_RUNTIME_DB_URL
VEHICLE_DB_URL = DATABASE_URL  # Alias pro zpětnou kompatibilitu


def _normalize_sqlite_db_path(db_url: str) -> Path | None:
    raw = str(db_url or "").strip()
    if not raw.startswith("sqlite:///"):
        return None
    db_path = raw.replace("sqlite:///", "", 1)
    if not db_path:
        return None
    path = Path(db_path)
    if not path.is_absolute():
        path = (WORKSPACE_ROOT / path).resolve()
    return path.resolve()


RUNTIME_DB_PATH = _normalize_sqlite_db_path(DATABASE_URL)
LEGACY_APP_DATA_DB_REALPATH = LEGACY_APP_DATA_DB_PATH.resolve() if LEGACY_APP_DATA_DB_PATH.exists() else None
HAS_LEGACY_APP_DATA_DB = LEGACY_APP_DATA_DB_PATH.exists()
LEGACY_APP_DATA_DB_DRIFT = bool(
    RUNTIME_DB_PATH
    and LEGACY_APP_DATA_DB_REALPATH
    and RUNTIME_DB_PATH != LEGACY_APP_DATA_DB_REALPATH
)

# =============================================================================
# JWT CONFIGURATION
# =============================================================================

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "sprava-vozidel-dev-secret-change-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))  # 24 hours

# =============================================================================
# API CLIENT CONFIGURATION
# =============================================================================

# Dynamicky vytvořit BASE_API_URL z HOST a PORT, pokud není explicitně zadáno
_default_api_url = f"http://{HOST}:{PORT}"
_api_url_env = env_prefer_new("SPRAVA_VOZIDEL_API_URL", "TOOZHUB_API_URL")
BASE_API_URL = _api_url_env if _api_url_env is not None else _default_api_url

# Veřejná API URL (pro produkci: https://hub.toozservis.cz)
PUBLIC_API_BASE_URL = os.getenv("PUBLIC_API_BASE_URL", BASE_API_URL)

# =============================================================================
# CORS CONFIGURATION
# =============================================================================

# Výchozí povolené origins pro produkci
DEFAULT_PRODUCTION_ORIGINS = [
    "https://www.toozservis.cz",
    "https://toozservis.cz",
    "https://hub.toozservis.cz",  # Cloudflare Tunnel doména
]

_allowed_origins = os.getenv("ALLOWED_ORIGINS")
if _allowed_origins:
    if _allowed_origins == "*":
        ALLOWED_ORIGINS = ["*"]
    else:
        ALLOWED_ORIGINS = [origin.strip() for origin in _allowed_origins.split(",")]
else:
    # Automatická detekce podle prostředí
    if ENVIRONMENT == "production":
        ALLOWED_ORIGINS = DEFAULT_PRODUCTION_ORIGINS
    else:
        ALLOWED_ORIGINS = ["*"]  # Development - povolit všechny

# =============================================================================
# EMAIL CONFIGURATION
# =============================================================================

# SMTP konfigurace - podpora zpětné kompatibility (SMTP_SERVER -> SMTP_HOST)
SMTP_HOST = os.getenv("SMTP_HOST") or os.getenv("SMTP_SERVER", "smtp.mail.webnode.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))  # Webnode používá SSL na 465, ne STARTTLS na 587
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "info@toozservis.cz")

# =============================================================================
# API CONFIGURATION V1.0
# =============================================================================

# API Base URL (pokud je používán na frontendu)
API_BASE_URL = os.getenv("API_BASE_URL", PUBLIC_API_BASE_URL)

# Frontend Base URL (pro redirecty)
FRONTEND_BASE_URL = os.getenv("FRONTEND_BASE_URL", PUBLIC_API_BASE_URL)

# Feature flags
def _env_flag(name: str, default: bool) -> bool:
    """Načte boolean feature flag z env (1/true/yes/on = True)."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


ENABLE_SERVICE_MODULE = _env_flag("ENABLE_SERVICE_MODULE", True)
# Experimentální části jsou ve výchozím stavu v produkci vypnuté.
ENABLE_CUSTOMER_COMMANDS = _env_flag("ENABLE_CUSTOMER_COMMANDS", ENVIRONMENT != "production")
ENABLE_AI_FEATURES = _env_flag("ENABLE_AI_FEATURES", ENVIRONMENT != "production")
# Autopilot M2M může být produkčně potřebný, default proto zůstává zapnutý.
ENABLE_AUTOPILOT_API = _env_flag("ENABLE_AUTOPILOT_API", True)

# AI / Autopilot Configuration
AUTOPILOT_SHARED_SECRET = os.getenv("AUTOPILOT_SHARED_SECRET", "")

# =============================================================================
# WEB PUSH CONFIGURATION
# =============================================================================

WEB_PUSH_ENABLED = _env_flag("WEB_PUSH_ENABLED", True)
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "").strip()
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "").strip()
VAPID_CLAIMS_SUBJECT = os.getenv("VAPID_CLAIMS_SUBJECT", "mailto:info@toozservis.cz").strip()

# =============================================================================
# DATAOVOZIDLECH.CZ API CONFIGURATION (MDČR / Datová kostka)
# =============================================================================

# Podpora více názvů proměnných pro zpětnou kompatibilitu
# DATAOVO_API_KEY / DATAOVO_API_BASE_URL (nové názvy)
# DATAOVOZIDLECH_API_KEY / DATAOVOZIDLECH_API_URL (staré názvy)
DATAOVO_API_KEY = os.getenv("DATAOVO_API_KEY") or os.getenv("DATAOVOZIDLECH_API_KEY", "")
DATAOVO_API_BASE_URL = os.getenv("DATAOVO_API_BASE_URL") or os.getenv("DATAOVOZIDLECH_API_URL", "https://api.dataovozidlech.cz/api/vehicletechnicaldata/v2")

# Aliasy pro zpětnou kompatibilitu
DATAOVOZIDLECH_API_KEY = DATAOVO_API_KEY
DATAOVOZIDLECH_API_URL = DATAOVO_API_BASE_URL

# Alias pro Vehicle Decoder Engine
MDCR_API_BASE_URL = DATAOVO_API_BASE_URL
MDCR_API_TOKEN = DATAOVO_API_KEY

# =============================================================================
# EU VEHICLE OPEN DATA API CONFIGURATION
# =============================================================================

EU_VEHICLE_API_BASE_URL = os.getenv("EU_VEHICLE_API_BASE_URL", "")
EU_VEHICLE_API_TOKEN = os.getenv("EU_VEHICLE_API_TOKEN", "")

# =============================================================================
# FILE PATHS
# =============================================================================

PROJECT_ROOT = APP_ROOT
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
LOCAL_FALLBACK_DATA_DIR = PROJECT_ROOT / ".local_data"


def _resolve_data_dir() -> Path:
    configured = os.getenv("DATA_DIR_PATH", "").strip()
    if configured:
        return Path(configured).expanduser()

    if DEFAULT_DATA_DIR.is_symlink() and not DEFAULT_DATA_DIR.exists():
        fallback = LOCAL_FALLBACK_DATA_DIR
        print(
            f"[CONFIG] data symlink target is unavailable, using local fallback: {fallback}"
        )
        return fallback

    return DEFAULT_DATA_DIR


DATA_DIR = _resolve_data_dir()
UPLOADS_DIR = DATA_DIR / "uploads"
PDF_DIR = DATA_DIR / "pdfs"
IMAGES_DIR = DATA_DIR / "images"

def _ensure_directory(path: Path) -> None:
    """
    Bezpečný bootstrap adresářů i pro případ, kdy `data` je symlink na externí volume.
    """
    if path.exists():
        if path.is_dir():
            return
        raise RuntimeError(f"Path exists but is not a directory: {path}")

    try:
        path.mkdir(parents=True, exist_ok=True)
    except FileExistsError:
        if path.exists() and path.is_dir():
            return
        raise


for directory in [DATA_DIR, UPLOADS_DIR, PDF_DIR, IMAGES_DIR]:
    _ensure_directory(directory)
