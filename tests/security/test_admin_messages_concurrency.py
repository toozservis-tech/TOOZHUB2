"""Actual independent SQLite transactions: duplicate commands and read/arrival races."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine,event
from sqlalchemy.orm import sessionmaker
from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import Customer,Tenant
from src.modules.vehicle_hub.admin_message_models import AdminMessage,AdminMessageCommand
from src.server.admin_messages import run_command,Send,Read,Operation
from src.core.rate_limiter import rate_limiter

@pytest.fixture
def sessions(tmp_path):
    engine=create_engine(f'sqlite:///{tmp_path}/race.sqlite',connect_args={'check_same_thread':False,'timeout':15})
    @event.listens_for(engine,'connect')
    def fk(connection,_):connection.execute('PRAGMA foreign_keys=ON')
    Base.metadata.create_all(engine)
    factory=sessionmaker(bind=engine)
    with factory() as db:
        db.add(Tenant(id=1,name='Synthetic',license_key='synthetic'));db.flush()
        db.add_all([Customer(id=1,tenant_id=1,email='admin@example.com',role='admin'),
                    Customer(id=2,tenant_id=1,email='one@example.com',role='user'),
                    Customer(id=3,tenant_id=1,email='two@example.com',role='user')]);db.commit()
    rate_limiter.clear()
    yield factory
    engine.dispose()


def simultaneous(functions):
    barrier=Barrier(len(functions))
    def run(fn):
        barrier.wait(timeout=10)
        return fn()
    with ThreadPoolExecutor(max_workers=len(functions)) as pool:return list(pool.map(run,functions))


def perform(factory,kind,payload,*,recipient=2,admin=True,message_id=None):
    with factory() as db:
        actor=db.get(Customer,1 if admin else recipient);target=db.get(Customer,recipient)
        try:return run_command(db,actor,target,payload,kind,admin=admin,message_id=message_id)
        except HTTPException as error:return error.status_code


def test_concurrent_same_send_uuid_creates_exactly_one_message_and_audit(sessions):
    body=Send(body='One immutable message',requires_ack=True,client_id=uuid4())
    results=simultaneous([lambda:perform(sessions,'send',body),lambda:perform(sessions,'send',body)])
    assert all(isinstance(row,dict) for row in results),results
    assert results[0]['message']['id']==results[1]['message']['id']
    with sessions() as db:
        assert db.query(AdminMessage).count()==1
        assert db.query(AdminMessageCommand).count()==1


def test_concurrent_conflicting_uuid_different_recipients_rolls_back_extra_message(sessions):
    identity=uuid4();one=Send(body='First',client_id=identity);two=Send(body='Different',client_id=identity)
    results=simultaneous([lambda:perform(sessions,'send',one),lambda:perform(sessions,'send',two,recipient=3)])
    assert sum(isinstance(row,dict) for row in results)==1,results
    assert 409 in results
    with sessions() as db:
        assert db.query(AdminMessage).count()==1
        assert db.query(AdminMessageCommand).count()==1


def test_concurrent_new_message_and_read_do_not_mark_unseen_new_message(sessions):
    previous=perform(sessions,'send',Send(body='Previously shown',client_id=uuid4()))['message']
    read=Read(message_ids=[previous['id']],client_id=uuid4())
    results=simultaneous([lambda:perform(sessions,'read',read,admin=False),
                         lambda:perform(sessions,'send',Send(body='Just arrived',requires_ack=True,client_id=uuid4()))])
    assert all(isinstance(row,dict) for row in results),results
    with sessions() as db:
        old,new=db.query(AdminMessage).order_by(AdminMessage.id).all()
        assert old.read_at is not None
        assert new.read_at is None and new.acknowledged_at is None


def test_concurrent_distinct_ack_commands_keep_first_receipt_time(sessions):
    message=perform(sessions,'send',Send(body='Please acknowledge',requires_ack=True,client_id=uuid4()))['message']
    results=simultaneous([lambda:perform(sessions,'ack',Operation(client_id=uuid4()),admin=False,message_id=message['id']),
                         lambda:perform(sessions,'ack',Operation(client_id=uuid4()),admin=False,message_id=message['id'])])
    assert all(isinstance(row,dict) for row in results),results
    assert results[0]['message']['acknowledged_at']==results[1]['message']['acknowledged_at']
    with sessions() as db:
        acknowledgments=db.query(AdminMessageCommand).filter_by(kind='ack').all()
        assert sum(row.result_count for row in acknowledgments)==1
        assert db.query(AdminMessage).count()==1
