"""Repeatable additive private-message migration, run only at pre-deploy."""
# This is migration 0028. Later model columns are added by migration 0030,
# so replaying 0028 must not create their indexes against a 0029 database.
BASELINE_INDEX_NAMES = frozenset({
    'ix_admin_messages_recipient_id', 'ix_admin_messages_sender_id',
    'ix_admin_messages_sent_at', 'ix_admin_message_unread',
    'ix_admin_message_ack', 'ix_admin_message_commands_recipient_id',
})


def migrate_connection(connection):
    from src.modules.vehicle_hub import models
    from src.modules.vehicle_hub.admin_message_models import TABLES
    for table in TABLES:
        table.create(connection,checkfirst=True)
        for index in table.indexes:
            if index.name in BASELINE_INDEX_NAMES:
                index.create(connection,checkfirst=True)


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
