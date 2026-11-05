"""Independent SQLite transactions for notification receipts and worker leases."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
from datetime import datetime,timedelta
import pytest
from sqlalchemy import create_engine,event
from sqlalchemy.orm import sessionmaker
from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import Customer,Tenant,SystemNotification
from src.modules.vehicle_hub.admin_message_models import AdminMessage
from src.modules.vehicle_hub.notification_delivery_models import NotificationItem,NotificationCommand,AnnouncementPolicy,PushDevice,PushOutbox
from src.modules.vehicle_hub.notification_inbox import materialize,command,collect_new
from scripts.migrate_notification_delivery import migrate
from src.core.rate_limiter import rate_limiter

@pytest.fixture
def sessions(tmp_path):
    engine=create_engine(f'sqlite:///{tmp_path}/race.sqlite',connect_args={'check_same_thread':False,'timeout':15})
    @event.listens_for(engine,'connect')
    def fk(connection,_):connection.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine);migrate(engine)
    factory=sessionmaker(bind=engine)
    with factory() as db:
        db.add(Tenant(id=1,name='Synthetic',license_key='synthetic'));db.flush()
        db.add_all([Customer(id=1,tenant_id=1,email='admin@example.com',role='admin'),Customer(id=2,tenant_id=1,email='user@example.com',role='user')]);db.flush()
        db.add(AdminMessage(recipient_id=2,sender_id=1,sender_kind='admin',body='Synthetic',requires_ack=True));db.commit()
    rate_limiter.clear();yield factory;engine.dispose()

def simultaneous(functions):
    barrier=Barrier(len(functions))
    def run(fn):barrier.wait(timeout=10);return fn()
    with ThreadPoolExecutor(max_workers=len(functions)) as pool:return list(pool.map(run,functions))

def test_parallel_materialize_and_collect_only_one_item(sessions):
    def render():
        with sessions() as db:materialize(db,db.get(Customer,2));db.commit()
    def worker():
        with sessions() as db:collect_new(db)
    simultaneous([render,render,worker])
    with sessions() as db:assert db.query(NotificationItem).count()==1

def test_concurrent_same_confirmation_uuid_is_once(sessions):
    with sessions() as db:materialize(db,db.get(Customer,2));db.commit();identity=db.query(NotificationItem).one().id
    cid=uuid4()
    def confirm():
        with sessions() as db:return command(db,db.get(Customer,2),'ack',[identity],cid)
    results=simultaneous([confirm,confirm])
    assert results[0]['item']['acknowledged_at']==results[1]['item']['acknowledged_at']
    with sessions() as db:assert db.query(NotificationCommand).count()==1

def test_concurrent_distinct_confirmation_preserves_first_timestamp(sessions):
    with sessions() as db:materialize(db,db.get(Customer,2));db.commit();identity=db.query(NotificationItem).one().id
    def confirm():
        with sessions() as db:return command(db,db.get(Customer,2),'ack',[identity],uuid4())
    results=simultaneous([confirm,confirm])
    assert results[0]['item']['acknowledged_at']==results[1]['item']['acknowledged_at']
    with sessions() as db:assert db.query(NotificationCommand).count()==2

def test_bounded_broadcast_fanout_resumes_without_skip_or_duplicate(sessions):
    with sessions() as db:
        for i in range(3,10):db.add(Customer(id=i,tenant_id=1,email=f'user{i}@example.com',role='user'))
        db.add(SystemNotification(target_type='all',message='Broadcast'));db.commit()
    for _ in range(5):
        with sessions() as db:collect_new(db,fanout_limit=2)
    with sessions() as db:
        assert db.query(NotificationItem).filter_by(kind='announcement').count()==8
        assert db.query(NotificationItem).filter_by(kind='admin_message').count()==1
