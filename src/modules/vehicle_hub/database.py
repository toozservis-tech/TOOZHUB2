import os
import re
from sqlalchemy import create_engine, event
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
        pool_size=3,
        pool_pre_ping=True,
        hide_parameters=True,
        max_overflow=2,
        future=True,
        connect_args={}
    )
else:
    # SQLite - bez poolování
    engine = create_engine(DB_URL, connect_args=connect_args, hide_parameters=True)

schema = os.getenv("DATABASE_SCHEMA", "")
if schema:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", schema):
        raise RuntimeError("Invalid database schema")
    @event.listens_for(engine, "connect")
    def set_schema(connection, record):
        previous = connection.autocommit
        connection.autocommit = True
        try:
            with connection.cursor() as cursor:
                cursor.execute('SET search_path TO "' + schema + '"')
        finally:
            connection.autocommit = previous

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
