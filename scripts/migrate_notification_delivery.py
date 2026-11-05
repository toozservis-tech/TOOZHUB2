"""Additive, repeatable notification rollout; never replays historical push."""
def migrate_connection(connection):
    from datetime import datetime
    from sqlalchemy import select,func,inspect,text
    from src.modules.vehicle_hub import models
    from src.modules.vehicle_hub.admin_message_models import AdminMessage
    from src.modules.vehicle_hub.vehicle_update_models import VehicleUpdate
    from src.modules.vehicle_hub.notification_delivery_models import TABLES,NotificationCursor
    for table in TABLES:
        table.create(connection,checkfirst=True)
        for index in table.indexes:index.create(connection,checkfirst=True)
    # Repeatability also supports a pre-release fixture created by an earlier
    # candidate; these columns have never existed in the public schema.
    known={column['name'] for column in inspect(connection).get_columns('notification_items')}
    for name,kind in [('available_at','TIMESTAMP'),('snapshot_title','TEXT'),('snapshot_body','TEXT'),('snapshot_requires_ack','BOOLEAN')]:
        if name not in known:connection.execute(text(f'ALTER TABLE notification_items ADD COLUMN {name} {kind}'))
    cursor_columns={column['name'] for column in inspect(connection).get_columns('notification_cursors')}
    if 'recipient_cursor' not in cursor_columns:
        connection.execute(text('ALTER TABLE notification_cursors ADD COLUMN recipient_cursor INTEGER NOT NULL DEFAULT 0'))
    for kind,model in [('admin_message',AdminMessage),('announcement',models.SystemNotification),('vehicle_update',VehicleUpdate)]:
        if connection.execute(select(NotificationCursor.kind).where(NotificationCursor.kind==kind)).first():continue
        last=connection.execute(select(func.max(model.id))).scalar() or 0
        connection.execute(NotificationCursor.__table__.insert().values(kind=kind,source_id=last,rollout_at=datetime.utcnow()))

def migrate(bind=None):
    from sqlalchemy import text
    if bind is None:
        from src.modules.vehicle_hub.database import engine
        bind=engine
    with bind.begin() as connection:
        if connection.dialect.name=='postgresql':
            connection.execute(text("SET LOCAL lock_timeout = '10s'"))
            connection.execute(text("SET LOCAL statement_timeout = '60s'"))
            connection.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('sv:schema:notification-delivery',0))"))
        migrate_connection(connection)

if __name__=='__main__':migrate()
