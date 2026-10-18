"""Explicit, retry-safe pre-deploy migration; never called by request handlers."""
from pathlib import Path
import importlib.util
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text


def check(bind=None):
    """Read-only deployment check; never creates tables or updates rows."""
    from sqlalchemy.orm import Session
    from src.modules.vehicle_hub.schema_management import module_schema_report
    if bind is None:
        from src.modules.vehicle_hub.database import engine
        bind = engine
    with Session(bind) as db:
        return module_schema_report(db, "vehicle_updates")


def migrate(bind=None):
    if bind is None:
        from src.modules.vehicle_hub.database import engine
        bind = engine
    path = Path(__file__).resolve().parents[1] / "alembic/versions/20261018_0017_vehicle_update_inbox.py"
    spec = importlib.util.spec_from_file_location("vehicle_update_inbox_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with bind.begin() as connection:
        if connection.dialect.name == "postgresql":
            connection.execute(text("SET LOCAL lock_timeout = '10s'"))
            connection.execute(text("SET LOCAL statement_timeout = '60s'"))
            connection.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('sv:schema:vehicle-update-inbox', 0))"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()


if __name__ == "__main__":
    import argparse
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Read-only schema readiness check")
    args = parser.parse_args()
    if args.check:
        result = check()
        print(json.dumps(result))
        raise SystemExit(0 if result["available"] else 1)
    migrate()
    print("Vehicle inbox folders ready. Existing events, read states and repair records retained.")
