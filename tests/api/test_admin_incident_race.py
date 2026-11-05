"""Exercise actual concurrent conditional writes on independent SQLite connections."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4
from datetime import datetime
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import Tenant,Customer,SecurityAccessLog
from src.modules.vehicle_hub.admin_incident_models import AdminIncident,AdminIncidentEvent,AdminIncidentHistory
from src.server.admin_incidents import apply_command,Transition,fingerprint

def test_concurrent_admin_commands_have_one_winner_and_preserve_history(tmp_path):
    engine=create_engine('sqlite:///'+str(tmp_path/'race.sqlite'),connect_args={'check_same_thread':False,'timeout':10})
    Base.metadata.create_all(engine);Session=sessionmaker(bind=engine)
    with Session() as db:
        tenant=Tenant(name='QA',license_key='QA');db.add(tenant);db.flush()
        admin=Customer(tenant_id=tenant.id,email='admin@example.com',role='admin');db.add(admin);db.flush()
        event=SecurityAccessLog(user_email='unknown@example.com',event_type='request_failed',endpoint='/analytics/summary',details='{"status":403}');db.add(event);db.flush()
        case=AdminIncident(source_event_id=event.id,actor_key='unknown@example.com',fingerprint=fingerprint(event),active_fingerprint=fingerprint(event),created_by=admin.id)
        db.add(case);db.flush();db.add(AdminIncidentEvent(incident_id=case.id,event_id=event.id));db.commit();case_id=case.id;admin_id=admin.id
    barrier=Barrier(2)
    def change(status):
        with Session() as db:
            case=db.get(AdminIncident,case_id);admin=db.get(Customer,admin_id)
            command=Transition(status=status,note='Independently checked',expected_version=1,client_id=uuid4())
            barrier.wait()
            try:apply_command(db,case,admin,command,'transition');return 200
            except HTTPException as error:return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(change,['resolved','dismissed']))
    assert sorted(results)==[200,409]
    with Session() as db:
        assert db.get(AdminIncident,case_id).version==2
        assert db.query(AdminIncidentHistory).count()==1
        assert db.query(SecurityAccessLog).count()==1
    engine.dispose()

def test_recurrence_cannot_attach_to_concurrently_closed_case(tmp_path,monkeypatch):
    from sqlalchemy.sql.dml import Update
    from src.server.admin_incidents import create_router
    engine=create_engine('sqlite:///'+str(tmp_path/'recurrence.sqlite'),connect_args={'check_same_thread':False,'timeout':10})
    Base.metadata.create_all(engine);Session=sessionmaker(bind=engine)
    endpoint=next(route.endpoint for route in create_router(lambda:None).routes if route.path.endswith('/from-event/{event_id}'))
    with Session() as db:
        tenant=Tenant(name='QA',license_key='QA');db.add(tenant);db.flush()
        admin=Customer(tenant_id=tenant.id,email='admin@example.com',role='admin');db.add(admin);db.flush();admin_id=admin.id
        events=[]
        for _ in range(2):
            event=SecurityAccessLog(user_email='unknown@example.com',event_type='request_failed',endpoint='/analytics/summary',details='{"status":403}');db.add(event);db.flush();events.append(event.id)
        db.commit();first=endpoint(events[0],admin,db);case_id=first['id']
    with Session() as db:
        admin=db.get(Customer,admin_id);original=db.execute;closed=False
        def execute(statement,*args,**kwargs):
            nonlocal closed
            if not closed and isinstance(statement,Update) and statement.table.name=='admin_incidents':
                closed=True
                with Session() as closer:
                    apply_command(closer,closer.get(AdminIncident,case_id),closer.get(Customer,admin_id),Transition(status='resolved',note='Verified earlier occurrence',expected_version=1,client_id=uuid4()),'transition')
            return original(statement,*args,**kwargs)
        with monkeypatch.context() as patcher:
            patcher.setattr(db,'execute',execute)
            with pytest.raises(HTTPException) as conflict:endpoint(events[1],admin,db)
            assert conflict.value.status_code==409
        assert db.query(AdminIncidentEvent).filter_by(event_id=events[1]).count()==0
        assert db.get(AdminIncident,case_id).status=='resolved'
        retried=endpoint(events[1],admin,db)
        assert retried['status']=='open' and retried['id']!=case_id
    engine.dispose()
