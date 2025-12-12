from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

# Podpora DATABASE_URL i VEHICLE_DB_URL (zpětná kompatibilita)
# Použít DATABASE_URL pokud existuje, jinak VEHICLE_DB_URL, jinak default SQLite
DB_URL = os.getenv("DATABASE_URL") or os.getenv("VEHICLE_DB_URL", "sqlite:///./vehicles.db")

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

