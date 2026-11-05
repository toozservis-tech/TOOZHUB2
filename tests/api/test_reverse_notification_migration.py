"""0030 preserves the real old CHECK, foreign keys, queue and receipt data."""
import re
from datetime import datetime,timedelta
from sqlalchemy import create_engine,event,inspect,text
from sqlalchemy.schema import CreateTable
from sqlalchemy.orm import sessionmaker
from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub import models
from src.modules.vehicle_hub.admin_message_models import AdminMessage,AdminMessageCommand
from src.modules.vehicle_hub.notification_delivery_models import NotificationItem,PushDevice,PushOutbox,NotificationCursor
from src.modules.vehicle_hub.operational_notification_models import NotificationOperationalEvent
from scripts.migrate_notification_delivery import migrate as migrate29
from scripts.migrate_reverse_notifications import migrate


def old_engine(tmp_path):
    engine=create_engine(f'sqlite:///{tmp_path}/old29.sqlite')
    @event.listens_for(engine,'connect')
    def fk(connection,_):connection.execute('PRAGMA foreign_keys=ON')
    with engine.begin() as conn:
        ddl=str(CreateTable(AdminMessage.__table__).compile(engine))
        for name in ('reply_to_message_id','reply_to_notification_id','addressed_admin_id'):
            ddl=re.sub(r'\n\t'+name+r' INTEGER,','',ddl)
            ddl=re.sub(r'\n\tFOREIGN KEY\('+name+r'\)[^\n]+\n?', '\n',ddl)
        ddl=re.sub(r',\s*\)', '\n)', ddl)
        conn.exec_driver_sql(ddl)
        ddl=str(CreateTable(NotificationItem.__table__).compile(engine)).replace(", 'service_event', 'admin_reply'",'').replace(",'service_event','admin_reply'",'')
        conn.exec_driver_sql(ddl)
    Base.metadata.create_all(engine,tables=[t for t in Base.metadata.sorted_tables if t.name not in {'admin_messages','notification_items','notification_operational_events'}])
    with engine.begin() as c:
        c.execute(models.Tenant.__table__.insert().values(id=1,name='Synthetic',license_key='synthetic'))
        c.execute(models.Customer.__table__.insert(),[{'id':1,'tenant_id':1,'email':'u@example.com','role':'user'},{'id':2,'tenant_id':1,'email':'a@example.com','role':'admin'}])
        c.execute(text("INSERT INTO admin_messages (id,recipient_id,sender_id,sender_kind,body,body_erased,requires_ack,sent_at,read_at) VALUES (5,1,2,'admin','Retain message',0,0,'2026-01-01','2026-01-02')"))
        c.execute(NotificationItem.__table__.insert().values(id=9,recipient_id=1,kind='admin_message',source_id=5,created_at=datetime(2026,1,1),read_at=datetime(2026,1,2)))
        c.execute(PushDevice.__table__.insert().values(id=11,recipient_id=1,installation_id='synthetic',installation_secret_hash='hash',platform='apns',environment='sandbox',bundle_id='fixture',token_hash='hash',token_ciphertext='encrypted-synthetic',session_digest='digest',session_version=0,session_expires_at=datetime(2030,1,1),permission='authorized'))
        c.execute(PushOutbox.__table__.insert().values(id=12,item_id=9,device_id=11,device_generation=1,state='accepted',attempts=1,accepted_at=datetime(2026,1,2),last_code='apns_accepted'))
        c.execute(AdminMessageCommand.__table__.insert().values(id=15,actor_id=2,recipient_id=1,client_id='synthetic',kind='send',request_hash='hash',message_id=5,result_count=1))
    migrate29(engine)
    return engine


def test_0030_old_schema_preserves_child_rows_indexes_fks_and_cursor_repeatability(tmp_path):
    engine=old_engine(tmp_path)
    try:
        assert 'addressed_admin_id' not in {c['name'] for c in inspect(engine).get_columns('admin_messages')}
        migrate(engine)
        with engine.connect() as c:
            assert c.execute(text('PRAGMA foreign_keys')).scalar()==1
            assert not c.execute(text('PRAGMA foreign_key_check')).all()
            assert c.execute(text('SELECT id,item_id,state,attempts FROM notification_push_outbox')).one()==(12,9,'accepted',1)
            assert c.execute(text('SELECT message_id FROM admin_message_commands')).scalar()==5
        with sessionmaker(bind=engine)() as db:
            assert db.get(AdminMessage,5).body=='Retain message'
            assert db.get(NotificationItem,9).read_at==datetime(2026,1,2)
            original={r.kind:(r.source_id,r.rollout_at) for r in db.query(NotificationCursor)}
            assert original['admin_reply'][0]==5 and original['service_event'][0]==0
        migrate(engine)
        with sessionmaker(bind=engine)() as db:
            assert {r.kind:(r.source_id,r.rollout_at) for r in db.query(NotificationCursor)}==original
            db.add(NotificationItem(recipient_id=2,kind='admin_reply',source_id=100));db.commit()
        assert 'ix_admin_messages_addressed_admin_id' in {i['name'] for i in inspect(engine).get_indexes('admin_messages')}
        assert 'uq_notification_source' in {u['name'] for u in inspect(engine).get_unique_constraints('notification_items')}
        assert any('service_event' in c['sqltext'] for c in inspect(engine).get_check_constraints('notification_items'))
    finally:engine.dispose()


def test_missing_0030_is_reported_unavailable_before_new_column_queries(tmp_path):
    from src.modules.vehicle_hub.notification_inbox import ready
    engine=old_engine(tmp_path)
    try:
        with sessionmaker(bind=engine)() as db:assert not ready(db)
        migrate(engine)
        with sessionmaker(bind=engine)() as db:assert ready(db)
    finally:engine.dispose()
