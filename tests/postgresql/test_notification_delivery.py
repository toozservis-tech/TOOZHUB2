"""Notification migration/concurrency on a newly initialized Unix-only PostgreSQL."""
from datetime import datetime,timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
from cryptography.fernet import Fernet
from sqlalchemy import inspect
from fastapi import HTTPException
from src.modules.vehicle_hub.models import Customer,Tenant
from src.modules.vehicle_hub.admin_message_models import AdminMessage
from src.modules.vehicle_hub.notification_delivery_models import TABLES,NotificationItem,NotificationCommand,PushDevice,PushOutbox,NotificationCursor
from src.modules.vehicle_hub.notification_inbox import command,materialize,collect_new
from src.modules.vehicle_hub.push_delivery import register,dispatch_one,Outcome
from src.modules.vehicle_hub.routers_v1.notifications import Device
from src.core.security import create_access_token
from scripts.migrate_notification_delivery import migrate


def setup(pg_db,monkeypatch):
    monkeypatch.setenv('PUSH_DELIVERY_ENABLED','true')
    monkeypatch.setenv('PUSH_DELIVERY_RECIPIENT_IDS','1,2,3')
    monkeypatch.delenv('PUSH_PUBLIC_APNS_FROM_UTC',raising=False)
    monkeypatch.setenv('PUSH_TOKEN_ENCRYPTION_KEY',Fernet.generate_key().decode())
    for key,value in {'APNS_SANDBOX_KEY_ID':'qa-sandbox','APNS_SANDBOX_PRIVATE_KEY':'qa-not-production', 'APNS_KEY_ID':'qa','APNS_TEAM_ID':'qa','APNS_PRIVATE_KEY':'qa','APNS_BUNDLE_IDS':'cz.fixture'}.items():monkeypatch.setenv(key,value)
    migrate(pg_db.engine)
    with pg_db.sessions() as db:
        db.add(Tenant(id=1,name='Synthetic',license_key='synthetic'));db.flush()
        db.add_all([Customer(id=1,tenant_id=1,email='admin@example.com',role='admin'),Customer(id=2,tenant_id=1,email='one@example.com',role='user'),Customer(id=3,tenant_id=1,email='two@example.com',role='user')]);db.flush()
        db.add(AdminMessage(recipient_id=2,sender_id=1,sender_kind='admin',body='Synthetic',requires_ack=True));db.commit()
    return create_access_token({'sub':'one@example.com','sv':0})


def simultaneous(functions):
    barrier=Barrier(len(functions))
    def run(fn):barrier.wait(timeout=10);return fn()
    with ThreadPoolExecutor(max_workers=len(functions)) as pool:return list(pool.map(run,functions))


def test_additive_migration_on_existing_schema_repeated_preserves_sources(pg_db,monkeypatch):
    setup(pg_db,monkeypatch)
    with pg_db.engine.begin() as connection:
        for table in reversed(TABLES):table.drop(connection)
    migrate(pg_db.engine);migrate(pg_db.engine)
    with pg_db.sessions() as db:
        assert db.query(AdminMessage).count()==1
        assert db.query(NotificationCursor).count()==3
        materialize(db,db.get(Customer,2));db.commit()
        assert db.query(NotificationItem).count()==1
    inspector=inspect(pg_db.engine)
    assert all(inspector.has_table(table.name) for table in TABLES)
    assert any(c['name']=='uq_notification_source' for c in inspector.get_unique_constraints('notification_items'))


def test_parallel_confirmation_uuid_and_distinct_commands(pg_db,monkeypatch):
    setup(pg_db,monkeypatch)
    with pg_db.sessions() as db:materialize(db,db.get(Customer,2));db.commit();nid=db.query(NotificationItem).one().id
    cid=uuid4()
    def ack(identity):
        with pg_db.sessions() as db:return command(db,db.get(Customer,2),'ack',[nid],identity)
    results=simultaneous([lambda:ack(cid),lambda:ack(cid)])
    assert results[0]['item']['acknowledged_at']==results[1]['item']['acknowledged_at']
    more=simultaneous([lambda:ack(uuid4()),lambda:ack(uuid4())])
    assert all(v['item']['acknowledged_at']==results[0]['item']['acknowledged_at'] for v in more)
    with pg_db.sessions() as db:assert db.query(NotificationCommand).count()==3


def test_parallel_materialize_and_worker_deduplicate(pg_db,monkeypatch):
    setup(pg_db,monkeypatch)
    def render():
        with pg_db.sessions() as db:materialize(db,db.get(Customer,2));db.commit()
    def collect():
        with pg_db.sessions() as db:collect_new(db)
    simultaneous([render,render,collect])
    with pg_db.sessions() as db:assert db.query(NotificationItem).count()==1


def test_token_capture_race_returns_one_registration_one409(pg_db,monkeypatch):
    token=setup(pg_db,monkeypatch)
    tokens={2:token,3:create_access_token({'sub':'two@example.com','sv':0})}
    def add(user):
        body=Device(platform='apns',token='ab'*32,installation_id=uuid4(),installation_secret='s'*40,environment='sandbox',bundle_id='cz.fixture',permission='authorized')
        with pg_db.sessions() as db:
            try:return register(db,db.get(Customer,user),body,tokens[user])
            except HTTPException as error:return error.status_code
    result=simultaneous([lambda:add(2),lambda:add(3)])
    assert sum(isinstance(v,dict) for v in result)==1 and 409 in result,result
    with pg_db.sessions() as db:assert db.query(PushDevice).count()==1


def test_parallel_workers_only_one_provider_acceptance(pg_db,monkeypatch):
    token=setup(pg_db,monkeypatch)
    with pg_db.sessions() as db:
        body=Device(platform='apns',token='ab'*32,installation_id=uuid4(),installation_secret='s'*40,environment='sandbox',bundle_id='cz.fixture',permission='authorized')
        register(db,db.get(Customer,2),body,token);collect_new(db)
    calls=[]
    def provider(*args):calls.append(1);return Outcome('accepted','apns_accepted')
    def worker():
        with pg_db.sessions() as db:return dispatch_one(db,provider)
    simultaneous([worker,worker])
    assert len(calls)==1
    with pg_db.sessions() as db:assert db.query(PushOutbox).one().state=='accepted'
