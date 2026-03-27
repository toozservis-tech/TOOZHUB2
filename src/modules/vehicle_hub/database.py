from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os
from pathlib import Path

# Podpora DATABASE_URL i VEHICLE_DB_URL (zpětná kompatibilita)
# Použít DATABASE_URL pokud existuje, jinak VEHICLE_DB_URL, jinak default SQLite
_db_url_env = os.getenv("DATABASE_URL") or os.getenv("VEHICLE_DB_URL")

if _db_url_env:
    DB_URL = _db_url_env
else:
    # Default: SQLite v /opt/toozhub2/data/vehicles.db (absolutní path)
    # File location: /opt/toozhub2/app/src/modules/vehicle_hub/database.py
    # Need to go up 5 levels: database.py -> vehicle_hub -> modules -> src -> app -> /opt/toozhub2
    project_root = Path(__file__).parent.parent.parent.parent.parent  # /opt/toozhub2/app/src/modules/vehicle_hub -> /opt/toozhub2
    data_dir = project_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)  # Vytvořit složku pokud neexistuje
    db_file = data_dir / "vehicles.db"
    DB_URL = f"sqlite:///{db_file}"

# Connect args pro SQLite
connect_args = {"check_same_thread": False} if DB_URL.startswith("sqlite") else {}

# Engine s poolováním (pro PostgreSQL), nebo bez (pro SQLite)
if DB_URL.startswith("postgresql") or DB_URL.startswith("postgres"):
    engine = create_engine(
        DB_URL,
        pool_size=20,
        max_overflow=30,
        future=True,
        connect_args={}
    )
else:
    # SQLite - bez poolování
    engine = create_engine(DB_URL, connect_args=connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

