"""Explicit additive booking_requests migration; never executed by a request."""
from importlib.util import spec_from_file_location, module_from_spec
from pathlib import Path
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text


def migrate(bind=None):
    if bind is None:
        from src.modules.vehicle_hub.database import engine
        bind = engine
    path = Path(__file__).resolve().parents[1] / 'alembic/versions/20261018_0016_booking_requests.py'
    spec = spec_from_file_location('booking_requests_migration', path)
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)
    with bind.begin() as connection:
        if connection.dialect.name == 'postgresql':
            connection.execute(text("SET LOCAL lock_timeout = '10s'"))
            connection.execute(text("SET LOCAL statement_timeout = '60s'"))
            connection.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('sv:schema:service-booking-requests', 0))"))
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()


if __name__ == '__main__':
    migrate()
    print('Service booking request tables ready. Existing reservations retained.')
