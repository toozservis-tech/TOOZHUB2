"""Explicit additive migration; run before deploying service-update writers."""
from pathlib import Path
import importlib.util
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text


def migrate(bind=None):
    if bind is None:
        from src.modules.vehicle_hub.database import engine
        bind = engine
    path = Path(__file__).resolve().parents[1] / 'alembic/versions/20261017_0014_service_jobs_updates.py'
    spec = importlib.util.spec_from_file_location('service_updates_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with bind.begin() as connection:
        if connection.dialect.name == 'postgresql':
            connection.execute(text("SET LOCAL lock_timeout = '10s'"))
            connection.execute(text("SET LOCAL statement_timeout = '60s'"))
            connection.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('sv:schema:service-updates', 0))"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()


if __name__ == '__main__':
    migrate()
    print('Service jobs and vehicle inbox ready. Existing data retained.')
