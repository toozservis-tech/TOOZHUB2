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

schema = os.getenv("DATABASE_SCHEMA", "")
if schema and not re.fullmatch(r"[a-z][a-z0-9_]*", schema):
    raise RuntimeError("Invalid database schema")


def _create_engine(*, pool_size=3, max_overflow=2):
    if DB_URL.startswith(("postgresql", "postgres")):
        result = create_engine(DB_URL, pool_size=pool_size, max_overflow=max_overflow,
                               pool_pre_ping=True, hide_parameters=True, future=True)
    else:
        result = create_engine(DB_URL, connect_args=connect_args, hide_parameters=True)
    if schema:
        @event.listens_for(result, "connect")
        def set_schema(connection, record):
            previous = connection.autocommit
            connection.autocommit = True
            try:
                with connection.cursor() as cursor:
                    cursor.execute('SET search_path TO "' + schema + '"')
            finally:
                connection.autocommit = previous
    return result


engine = _create_engine()
# A request holds its transaction while writing its independent audit event.
# Sharing the request pool can deadlock when every request needs one more
# connection to finish. Reserve one bounded PostgreSQL connection for audit;
# keep synchronous, durable writes and the same database/schema.
audit_engine = _create_engine(pool_size=1, max_overflow=0) if engine.dialect.name == "postgresql" else engine

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
AuditSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=audit_engine)
Base = declarative_base()

# Register the shared VIN write guard once, regardless of which router writes.
from . import vehicle_identity  # noqa: E402,F401

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
