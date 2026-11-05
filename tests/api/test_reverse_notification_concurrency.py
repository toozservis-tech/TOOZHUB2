"""Two independent SQLite sessions race identical explicit reply commands."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import Customer,Tenant
from src.modules.vehicle_hub.admin_message_models import AdminMessage,AdminMessageCommand
from src.server.admin_messages import Reply,run_command
from src.modules.vehicle_hub.notification_inbox import collect_new
from src.modules.vehicle_hub.notification_delivery_models import NotificationItem
from scripts.migrate_notification_delivery import migrate as migrate29
from scripts.migrate_reverse_notifications import migrate


def test_competing_explicit_replies_and_workers_keep_one_source_one_target(tmp_path):
    engine=create_engine(f'sqlite:///{tmp_path}/concurrent.sqlite',connect_args={'timeout':10,'check_same_thread':False})
    Base.metadata.create_all(engine);factory=sessionmaker(bind=engine,autoflush=False)
    with factory() as db:
        db.add(Tenant(id=1,name='Synthetic',license_key='synthetic'));db.flush()
        db.add_all([Customer(id=1,tenant_id=1,email='user@example.com',role='user'),Customer(id=2,tenant_id=1,email='admin@example.com',role='admin')]);db.flush()
        db.add(AdminMessage(id=1,recipient_id=1,sender_id=2,sender_kind='admin',body='Original synthetic message'));db.commit()
    migrate29(engine);migrate(engine)
    barrier=Barrier(2);payload=Reply(client_id=uuid4(),body='Same synthetic reply',reply_to_message_id=1)
    def reply():
        with factory() as db:
            actor=db.get(Customer,1);barrier.wait(timeout=10)
            return run_command(db,actor,actor,payload,'reply')['message']['id']
    with ThreadPoolExecutor(max_workers=2) as pool:ids=list(pool.map(lambda _:reply(),range(2)))
    assert ids[0]==ids[1]
    barrier=Barrier(2)
    def worker():
        with factory() as db:barrier.wait(timeout=10);collect_new(db)
    with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(lambda _:worker(),range(2)))
    with factory() as db:
        assert db.query(AdminMessage).filter_by(sender_kind='recipient').count()==1
        assert db.query(AdminMessageCommand).count()==1
        row=db.query(NotificationItem).filter_by(kind='admin_reply').one();assert row.recipient_id==2
    engine.dispose()
