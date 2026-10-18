"""Apply only the additive workshop/identity migration before the API starts.

Existing profiles and contacts are retained. No duplicate is merged automatically.
The database transaction rolls back the complete migration on failure.
"""
from pathlib import Path
import importlib.util
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text


def _already_applied(connection):
    """Read-only check: avoid re-running DDL on a live, protected VIN table."""
    if connection.dialect.name != "postgresql":
        return False
    return bool(connection.scalar(text("""
        SELECT to_regclass('vehicle_vin_claims') IS NOT NULL
          AND EXISTS (
            SELECT 1 FROM pg_trigger
            WHERE tgrelid = to_regclass('vehicles')
              AND tgname = 'sv_vehicle_vin_guard'
              AND NOT tgisinternal AND tgenabled <> 'D'
          )
          AND EXISTS (
            SELECT 1 FROM pg_attribute
            WHERE attrelid = to_regclass('vehicles')
              AND attname = 'merged_into_id' AND NOT attisdropped
          )
          AND EXISTS (
            SELECT 1 FROM pg_attribute
            WHERE attrelid = to_regclass('vehicles')
              AND attname = 'merged_vin' AND NOT attisdropped
          )
    """)))


def migrate_connection(connection):
    if _already_applied(connection):
        # Already guarded: never DROP / CREATE the VIN trigger on every boot.
        return
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
