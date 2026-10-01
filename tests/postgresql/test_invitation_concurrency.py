"""Invitation consent under independent PostgreSQL transactions; synthetic data only."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from threading import Barrier

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from src.modules.vehicle_hub.models import Customer, Tenant, ServiceCustomerLink, ServiceCustomerInvite
from src.modules.vehicle_hub.routers_v1 import service_workspace as workspace, services
from src.modules.vehicle_hub.service_contact_consent import migrate_contact_consent


@pytest.fixture
def invitation(pg_db):
    with pg_db.sessions() as db:
        ids={}
        for label,role in [('owner','user'),('service','service')]:
            tenant=Tenant(name=label,license_key=label);db.add(tenant);db.flush()
            actor=Customer(tenant_id=tenant.id,email=label+'@example.invalid',role=role)
            db.add(actor);db.flush();ids[label]=actor.id
        service=db.get(Customer,ids['service'])
        invite=ServiceCustomerInvite(service_tenant_id=service.tenant_id,service_customer_id=service.id,
            invite_email='owner@example.invalid',token='synthetic-concurrency-token',status='pending',
            expires_at=datetime.utcnow()+timedelta(days=1))
        db.add(invite);db.flush();ids['invite']=invite.id;db.commit()
    return ids


def run_parallel(pg_db,ids,decisions):
    barrier=Barrier(len(decisions))
    def worker(action):
        with pg_db.sessions() as db:
            actor=db.get(Customer,ids['owner'])
            barrier.wait(timeout=10)
            try:
                if action=='disconnect':
                    services.disconnect_my_service_contact(ids['service'],current_user=actor,db=db)
                else:
                    workspace.accept_service_invitation(workspace.AcceptServiceInviteRequest(
                        invitation_id=ids['invite'],decision=action),current_user=actor,db=db)
                return action,200
            except HTTPException as exc:
                db.rollback();return action,exc.status_code
    with ThreadPoolExecutor(max_workers=len(decisions)) as pool:
        return list(pool.map(worker,decisions))


def test_parallel_accept_creates_one_confirmed_contact(pg_db,invitation):
    assert run_parallel(pg_db,invitation,['accept']*6)==[('accept',200)]*6
    with pg_db.sessions() as db:
        link=db.query(ServiceCustomerLink).one()
        assert link.consented_by_customer_id==invitation['owner'] and link.consented_at
        assert db.get(ServiceCustomerInvite,invitation['invite']).status=='accepted'


def test_accept_decline_has_one_decision(pg_db,invitation):
    results=run_parallel(pg_db,invitation,['accept','decline'])
    assert sorted(status for _,status in results)==[200,409]
    with pg_db.sessions() as db:
        row=db.get(ServiceCustomerInvite,invitation['invite'])
        assert row.status in {'accepted','declined'}
        assert db.query(ServiceCustomerLink).count()==(1 if row.status=='accepted' else 0)


def test_accept_disconnect_never_reopens_cancelled_consent(pg_db,invitation):
    results=run_parallel(pg_db,invitation,['accept','disconnect'])
    assert ('disconnect',200) in results
    assert all(status in {200,409} for _,status in results)
    with pg_db.sessions() as db:
        assert db.query(ServiceCustomerLink).filter_by(status='active').count()==0
        assert db.get(ServiceCustomerInvite,invitation['invite']).status=='cancelled'
        with pytest.raises(HTTPException) as exc:
            workspace.accept_service_invitation(workspace.AcceptServiceInviteRequest(invitation_id=invitation['invite']),
                current_user=db.get(Customer,invitation['owner']),db=db)
        assert exc.value.status_code==409


def test_additive_migration_preserves_legacy_values_on_postgres(pg_db):
    with pg_db.engine.begin() as connection:
        connection.execute(text('CREATE SCHEMA consent_fixture'))
        connection.execute(text('SET LOCAL search_path TO consent_fixture'))
        connection.execute(text('CREATE TABLE service_customer_links (id INTEGER PRIMARY KEY, note TEXT)'))
        connection.execute(text("INSERT INTO service_customer_links VALUES(1,'original')"))
        connection.execute(text('CREATE TABLE reminders (id INTEGER PRIMARY KEY, text TEXT)'))
        connection.execute(text("INSERT INTO reminders VALUES(1,'personal')"))
        migrate_contact_consent(connection);migrate_contact_consent(connection)
        assert tuple(connection.execute(text('SELECT * FROM service_customer_links')).one())==(1,'original',None,None)
        assert tuple(connection.execute(text('SELECT * FROM reminders')).one())==(1,'personal',None)
