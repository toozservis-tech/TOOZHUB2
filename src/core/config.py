"""
Centrální konfigurace pro TooZ Hub 2
Podporuje načítání z environment variables a .env souboru
"""
import os
from pathlib import Path

# Pokusit se načíst .env soubor
try:
    from dotenv import load_dotenv, dotenv_values
    from io import StringIO
    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
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
                        env_loaded = True
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
                            env_loaded = True
                            break
                        except Exception:
                            continue
            except (UnicodeDecodeError, Exception):
                continue
        
        # Pokud se nepodařilo načíst žádné kódování, zkusit standardní load_dotenv
        if not env_loaded:
            try:
                load_dotenv(env_path)
            except Exception:
                # Pokud všechno selže, pokračovat bez .env souboru
                import warnings
                warnings.warn(f"Nepodařilo se načíst .env soubor z {env_path}. Používají se výchozí hodnoty.")
except ImportError:
    pass  # python-dotenv není nainstalován
except Exception as e:
    # Při jakékoliv chybě pokračovat bez .env souboru
    import warnings
    warnings.warn(f"Chyba při načítání .env souboru: {e}. Používají se výchozí hodnoty.")

# =============================================================================
# SERVER CONFIGURATION
# =============================================================================

HOST = os.getenv("HOST", "0.0.0.0")  # 0.0.0.0 pro Cloudflare Tunnel, 127.0.0.1 pro lokální vývoj
PORT = int(os.getenv("PORT", "8000"))
ENVIRONMENT = os.getenv("ENVIRONMENT", os.getenv("APP_ENV", "development"))  # development | production

# =============================================================================
# DATABASE
# =============================================================================

# Databázová URL - podpora DATABASE_URL i VEHICLE_DB_URL (zpětná kompatibilita)
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("VEHICLE_DB_URL", "sqlite:///./vehicles.db")
VEHICLE_DB_URL = DATABASE_URL  # Alias pro zpětnou kompatibilitu

# =============================================================================
# JWT CONFIGURATION
# =============================================================================

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "toozhub2-dev-secret-key-change-in-production")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))  # 24 hours

# =============================================================================
# API CLIENT CONFIGURATION
# =============================================================================

# Dynamicky vytvořit BASE_API_URL z HOST a PORT, pokud není explicitně zadáno
_default_api_url = f"http://{HOST}:{PORT}"
BASE_API_URL = os.getenv("TOOZHUB_API_URL", _default_api_url)

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
ENABLE_SERVICE_MODULE = os.getenv("ENABLE_SERVICE_MODULE", "true").lower() == "true"

# AI / Autopilot Configuration
AUTOPILOT_SHARED_SECRET = os.getenv("AUTOPILOT_SHARED_SECRET", "")

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

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
PDF_DIR = DATA_DIR / "pdfs"
IMAGES_DIR = DATA_DIR / "images"

# Vytvořit složky pokud neexistují
for directory in [DATA_DIR, UPLOADS_DIR, PDF_DIR, IMAGES_DIR]:
    directory.mkdir(parents=True, exist_ok=True)
