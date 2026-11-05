"""Repeatable additive private-message migration, run only at pre-deploy."""
def migrate_connection(connection):
    from src.modules.vehicle_hub import models
    from src.modules.vehicle_hub.admin_message_models import TABLES
    for table in TABLES:
        table.create(connection,checkfirst=True)
        for index in table.indexes:index.create(connection,checkfirst=True)


def migrate(bind=None):
    from sqlalchemy import text
    if bind is None:
        from src.modules.vehicle_hub.database import engine
        bind=engine
    with bind.begin() as connection:
        if connection.dialect.name=='postgresql':
            connection.execute(text("SET LOCAL lock_timeout = '10s'"))
            connection.execute(text("SET LOCAL statement_timeout = '60s'"))
            connection.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('sv:schema:admin-messages',0))"))
        migrate_connection(connection)


if __name__=='__main__':
    migrate()
    print('Private administrator messages ready; existing history retained.')
