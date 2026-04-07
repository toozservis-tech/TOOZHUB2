from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from src.core.config import DATABASE_URL


# Jediná runtime databázová pravda je centrální resolver v src.core.config.
# Legacy VEHICLE_DB_URL zůstává podporovaný pouze jako compat vstup do configu.
DB_URL = DATABASE_URL

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
