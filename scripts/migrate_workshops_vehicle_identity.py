"""Apply only the additive workshop/identity migration before the API starts.

Existing profiles and contacts are retained. No duplicate is merged automatically.
The database transaction rolls back the complete migration on failure.
"""
from pathlib import Path
import importlib.util
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text


def migrate_connection(connection):
    path = Path(__file__).resolve().parents[1] / 'alembic/versions/20261002_0013_workshops_vehicle_identity.py'
    spec = importlib.util.spec_from_file_location('workshop_identity_migration', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if connection.dialect.name == 'postgresql':
        connection.execute(text("SET LOCAL lock_timeout = '10s'"))
        connection.execute(text("SET LOCAL statement_timeout = '60s'"))
        connection.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('sv:schema:workshop-identity', 0))"))
    with Operations.context(MigrationContext.configure(connection)):
        module.upgrade()


def migrate(bind=None):
    if bind is None:
        from src.modules.vehicle_hub.database import engine
        bind = engine
    with bind.begin() as connection:
        migrate_connection(connection)


if __name__ == '__main__':
    migrate()
    print('Workshop addresses and unique vehicle identity are ready. Existing profiles retained.')
