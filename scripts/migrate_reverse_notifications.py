"""Additive targeted service/admin-reply delivery; no historical push replay."""
from sqlalchemy import inspect,text,select,func

def migrate_connection(connection):
    from datetime import datetime
    from src.modules.vehicle_hub import models
    from src.modules.vehicle_hub.admin_message_models import AdminMessage
    from src.modules.vehicle_hub.operational_notification_models import NotificationOperationalEvent
    from src.modules.vehicle_hub.notification_delivery_models import NotificationCursor
    NotificationOperationalEvent.__table__.create(connection,checkfirst=True)
    known={c['name'] for c in inspect(connection).get_columns('admin_messages')}
    for name,target in [('reply_to_message_id','admin_messages'),('reply_to_notification_id','system_notifications'),('addressed_admin_id','customers')]:
        if name not in known:
            connection.execute(text(f'ALTER TABLE admin_messages ADD COLUMN {name} INTEGER REFERENCES {target}(id) ON DELETE SET NULL'))
    for idx in AdminMessage.__table__.indexes:idx.create(connection,checkfirst=True)
    for idx in NotificationOperationalEvent.__table__.indexes:idx.create(connection,checkfirst=True)
    checks=inspect(connection).get_check_constraints('notification_items')
    old=next((c for c in checks if c['name']=='ck_notification_kind'),None)
    expression="kind IN ('admin_message','announcement','vehicle_update','service_event','admin_reply')"
    if not old or 'service_event' not in old['sqltext'] or 'admin_reply' not in old['sqltext']:
        if connection.dialect.name=='sqlite':
            if connection.execute(text('PRAGMA foreign_keys')).scalar():
                raise RuntimeError('SQLite migration must use migrate(bind) to preserve FK-linked history safely.')
            from alembic.migration import MigrationContext
            from alembic.operations import Operations
            with Operations(MigrationContext.configure(connection)).batch_alter_table('notification_items',recreate='always') as batch:
                if old:batch.drop_constraint('ck_notification_kind',type_='check')
                batch.create_check_constraint('ck_notification_kind',expression)
        else:
            if old:connection.execute(text('ALTER TABLE notification_items DROP CONSTRAINT ck_notification_kind'))
            connection.execute(text('ALTER TABLE notification_items ADD CONSTRAINT ck_notification_kind CHECK ('+expression+')'))
    for kind,model in [('service_event',NotificationOperationalEvent),('admin_reply',AdminMessage)]:
        if connection.execute(select(NotificationCursor.kind).where(NotificationCursor.kind==kind)).first():continue
        last=connection.execute(select(func.max(model.id))).scalar() or 0
        connection.execute(NotificationCursor.__table__.insert().values(kind=kind,source_id=last,rollout_at=datetime.utcnow()))

def migrate(bind=None):
    if bind is None:
        from src.modules.vehicle_hub.database import engine
        bind=engine
    with bind.connect() as connection:
        sqlite=connection.dialect.name=='sqlite';fk=0
        if sqlite:
            fk=connection.execute(text('PRAGMA foreign_keys')).scalar();connection.commit()
            connection.execute(text('PRAGMA foreign_keys=OFF'));connection.commit()
        try:
            with connection.begin():
                if connection.dialect.name=='postgresql':
                    connection.execute(text("SET LOCAL lock_timeout='10s'"))
                    connection.execute(text("SET LOCAL statement_timeout='60s'"))
                    connection.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('sv:schema:reverse-notifications',0))"))
                migrate_connection(connection)
                if sqlite and connection.execute(text('PRAGMA foreign_key_check')).first():
                    raise RuntimeError('SQLite FK integrity check failed; migration rolled back.')
        finally:
            if sqlite:connection.execute(text(f'PRAGMA foreign_keys={int(bool(fk))}'));connection.commit()

if __name__=='__main__':migrate()
