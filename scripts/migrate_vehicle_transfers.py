"""Explicit additive invitation migration. No request-time DDL or data rewrite."""
from sqlalchemy import text
from src.modules.vehicle_hub.vehicle_transfer_models import VehicleTransferInvitation

def migrate_connection(connection):
    VehicleTransferInvitation.__table__.create(connection, checkfirst=True)

def migrate(bind=None):
    if bind is None:
        from src.modules.vehicle_hub.database import engine
        bind = engine
    with bind.begin() as connection:
        if connection.dialect.name == 'postgresql':
            connection.execute(text("SET LOCAL lock_timeout = '10s'"))
            connection.execute(text("SET LOCAL statement_timeout = '60s'"))
            connection.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('sv:schema:vehicle-transfers', 0))"))
        migrate_connection(connection)

if __name__ == '__main__':
    migrate()
    print('Vehicle transfer invitations ready; existing owners unchanged.')
