import os

# Konfigurace serveru
# Pro produkci použijte 0.0.0.0 (přijímá připojení zvenčí)
HOST = os.getenv("HOST", "0.0.0.0")  # 0.0.0.0 pro Cloudflare Tunnel, 127.0.0.1 pro lokální vývoj
PORT = int(os.getenv("PORT", "8000"))  # Port pro backend

# Databáze
DB_URL = os.getenv("VEHICLE_DB_URL", "sqlite:///./vehicles.db")

# Environment
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# CORS - dynamické nastavení podle režimu
# Produkce: konkrétní domény
# Development: všechny origins
if ENVIRONMENT == "production":
    # Produkce - pouze konkrétní domény
    origins_str = os.getenv(
        "ALLOWED_ORIGINS",
        "https://toozservis.cz,https://www.toozservis.cz,https://hub.toozservis.cz"
    )
    ALLOWED_ORIGINS = [origin.strip() for origin in origins_str.split(",")]
else:
    # Development - všechny origins
    ALLOWED_ORIGINS = ["*"]

