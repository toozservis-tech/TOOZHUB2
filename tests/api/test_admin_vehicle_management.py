"""Real API/database operations with synthetic users; mail and external services never run."""
from datetime import datetime
from types import SimpleNamespace
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, insert
from sqlalchemy.orm import sessionmaker
from src.modules.vehicle_hub.database import Base, get_db
from src.modules.vehicle_hub import models as m
from src.modules.vehicle_hub.ownership import ensure_vehicle_owner_assignment
from src.modules.vehicle_hub.routers_v1 import vehicles, service_records, services
from src.modules.vehicle_hub.routers_v1.auth import get_current_user
from src.core.auth import get_current_user_email
from src.server import admin_api


@pytest.fixture
def scenario(tmp_path, monkeypatch):
    engine = create_engine(f'sqlite:///{tmp_path}/admin.sqlite', connect_args={'check_same_thread': False})
    Base.metadata.create_all(engine); db = sessionmaker(bind=engine, autoflush=False)()
    actors = {}
    for name, role in [('admin', 'developer_admin'), ('owner', 'user'), ('buyer', 'user'), ('service', 'service')]:
        tenant = m.Tenant(name=name, license_key=name); db.add(tenant); db.flush()
        actor = m.Customer(email=name+'@example.com', role=role, name=name, tenant_id=tenant.id,
                           street='Office', street_number='1', city='Praha', zip='11000', password_hash='fixture')
        db.add(actor); db.flush(); actors[name] = actor
    cars = []
    for owner in [actors['owner'], actors['buyer']]:
        identity = db.execute(insert(m.Vehicle.__table__).values(tenant_id=owner.tenant_id, user_email=owner.email,
            vin='TMBJF73T2B9044629', plate='1AB2345', nickname='Synthetic')).inserted_primary_key[0]
        car = db.get(m.Vehicle, identity); ensure_vehicle_owner_assignment(db, vehicle=car, owner=owner); cars.append(car)
    record = m.ServiceRecord(vehicle_id=cars[0].id, tenant_id=actors['owner'].tenant_id,
        user_id=actors['owner'].id, description='Private original work', performed_at=datetime(2025,1,1),
        attachments=f'[{{"storage_key":"tenant_2/vehicle_{cars[0].id}/private.pdf"}}]')
    db.add(record); db.commit()
    monkeypatch.setattr(vehicles, '_ensure_vehicle_photo_column', lambda _: None)
    monkeypatch.setattr(admin_api, 'ensure_customer_account_state_schema', lambda _: None)
    monkeypatch.setattr(services, '_geocode_address', lambda _: None)
    app=FastAPI(); state=SimpleNamespace(db=db, actor=actors['admin'], actors=actors, source=cars[0], target=cars[1], record=record)
    for router in [admin_api.router, vehicles.router, service_records.router, services.router]:
        app.include_router(router, prefix='' if router is admin_api.router else '/api/v1')
    app.dependency_overrides[get_db]=lambda: db
    app.dependency_overrides[get_current_user]=lambda: state.actor
    app.dependency_overrides[get_current_user_email]=lambda: state.actor.email
    with TestClient(app) as client: state.client=client; yield state
    db.close(); engine.dispose()


def test_admin_full_vehicle_history_and_edit(scenario):
    s=scenario
    detail=s.client.get(f'/admin-api/vehicles/{s.source.id}/detail')
    assert detail.status_code==200 and detail.json()['service_records'][0]['description']=='Private original work'
    records=s.client.get(f'/api/v1/vehicles/{s.source.id}/records')
    assert records.status_code==200 and len(records.json())==1
    update=s.client.put(f'/api/v1/vehicles/{s.source.id}/records/{s.record.id}', json={'description':'Reviewed correction'})
    assert update.status_code==200 and update.json()['description']=='Reviewed correction'
    assert s.db.query(m.ServiceRecordAuditLog).count()==1
    for role in ['owner','service']:
        s.actor=s.actors[role]
        assert s.client.get(f'/admin-api/vehicles/{s.source.id}/detail').status_code==403


def test_reviewed_merge_preserves_owner_privacy_and_archives_source(scenario):
    s=scenario
    report=s.client.get('/admin-api/vehicles/duplicates').json()
    assert report['checked_vehicles']==2 and {g['kind'] for g in report['groups']}=={'vin','plate'}
    url=f'/admin-api/vehicles/merge-preview?source_id={s.source.id}&target_id={s.target.id}'
    preview=s.client.get(url).json(); assert preview['different_owner']
    result=s.client.post('/admin-api/vehicles/merge', json={'source_id':s.source.id,'target_id':s.target.id,
        'preview_token':preview['preview_token'],'reason':'Owner reviewed duplicate identity'})
    assert result.status_code==200, result.text
    assert s.record.vehicle_id==s.target.id and s.source.merged_into_id==s.target.id and s.source.vin is None
    assert len(s.client.get('/admin-api/vehicles').json())==1
    assert s.client.get('/admin-api/vehicles/duplicates').json()['total']==0
    assert s.db.query(m.DeveloperActionAuditLog).filter_by(action_type='vehicle.merge').count()==1
    s.actor=s.actors['buyer']
    visible=s.client.get(f'/api/v1/vehicles/{s.target.id}/records').json()
    assert visible[0]['description']!='Private original work' and visible[0].get('attachments') is None
    assert s.client.get(f'/api/v1/vehicles/{s.target.id}/records/attachments/download?key=tenant_2/vehicle_{s.source.id}/private.pdf').status_code==403
    s.actor=s.actors['owner']
    assert s.client.get(f'/api/v1/vehicles/{s.source.id}').status_code in (403,404)
    assert s.client.get(f'/api/v1/vehicles/{s.target.id}').status_code==403
    assert s.client.get(url).status_code==403


def test_stale_merge_and_mismatching_vin_do_not_write(scenario):
    s=scenario; url=f'/admin-api/vehicles/merge-preview?source_id={s.source.id}&target_id={s.target.id}'
    preview=s.client.get(url).json(); s.record.description='Changed after preview'; s.db.commit()
    payload={'source_id':s.source.id,'target_id':s.target.id,'preview_token':preview['preview_token'],'reason':'Review duplicate'}
    assert s.client.post('/admin-api/vehicles/merge',json=payload).status_code==409
    assert s.source.merged_into_id is None and s.record.vehicle_id==s.source.id
    s.source.vin='WVWZZZ1JZXW000001'; s.db.commit()
    assert s.client.get(url).status_code==409


def test_workshop_separate_from_office_and_authenticated_directory(scenario, monkeypatch):
    s=scenario; service=s.actors['service']; s.actor=service
    body={'workshop_same_as_registered':False,'workshop_street':'Repair street','workshop_city':'Olomouc','workshop_zip':'77900'}
    assert s.client.put(f'/api/v1/services/{service.id}/workshop',json=body).status_code==200
    assert service.city=='Praha' and service.workshop_city=='Olomouc'
    s.actor=s.actors['owner']
    assert s.client.get(f'/api/v1/services/{service.id}/workshop').status_code==403
    result=s.client.get('/api/v1/services/discovery').json()['services']; assert len(result)==1
    assert result[0]['city']=='Olomouc' and result[0]['street']=='Repair street'
    assert s.client.get('/api/v1/services/area-directory?city=Praha').json()['count']==0
    assert s.client.get('/api/v1/services/area-directory?city=Olomouc').json()['count']==1
    s.actor=service
    assert s.client.put(f'/api/v1/services/{service.id}/workshop',json={'workshop_same_as_registered':True}).status_code==200
    assert s.client.get('/api/v1/services/discovery').json()['services'][0]['city']=='Praha'


def test_incomplete_workshop_not_accepted(scenario):
    s=scenario; s.actor=s.actors['service']; identity=s.actor.id
    assert s.client.put(f'/api/v1/services/{identity}/workshop',json={'workshop_same_as_registered':False}).status_code==422
    assert s.actor.workshop_same_as_registered is None


def test_admin_event_edits_are_audited_and_cannot_route_to_an_administrator(scenario):
    s=scenario
    reminder=m.Reminder(tenant_id=s.actors['owner'].tenant_id,vehicle_id=s.source.id,customer_id=s.actors['owner'].id,type='STK',text='Before',due_date=datetime(2027,1,1).date())
    reservation=m.Reservation(tenant_id=s.actors['owner'].tenant_id,vehicle_id=s.source.id,customer_id=s.actors['owner'].id,service_id=s.actors['service'].id,
        start_datetime=datetime(2027,1,1,9),end_datetime=datetime(2027,1,1,10),service_type='Before',status='PENDING')
    s.db.add_all([reminder,reservation]);s.db.commit()
    assert s.client.patch(f'/admin-api/reminders/{reminder.id}',json={'text':'After'}).status_code==200
    assert s.client.patch(f'/admin-api/reservations/{reservation.id}',json={'start_datetime':'2027-01-01T08:30:00Z','note':'Reviewed'}).status_code==200
    assert s.db.query(m.DeveloperActionAuditLog).filter(m.DeveloperActionAuditLog.action_type.in_(['reminder.admin_update','reservation.admin_update'])).count()==2
    assert s.client.patch(f'/admin-api/reservations/{reservation.id}',json={'service_id':s.actors['admin'].id}).status_code==404
    assert reservation.service_id==s.actors['service'].id
    assert s.client.patch(f'/admin-api/reservations/{reservation.id}',json={'end_datetime':'2027-01-01T07:00:00Z'}).status_code==422
    assert reservation.end_datetime==datetime(2027,1,1,10)
    assert s.client.patch(f'/admin-api/records/{s.record.id}',json={'vehicle_id':s.target.id}).status_code==409
    assert s.record.vehicle_id==s.source.id


def test_admin_vehicle_correction_preserves_before_and_after(scenario):
    s=scenario
    assert s.client.patch(f'/admin-api/vehicles/{s.source.id}',json={'notes':'Reviewed note','stk_valid_until':None}).status_code==200
    audit=s.db.query(m.DeveloperActionAuditLog).filter_by(action_type='vehicle.update').one()
    import json
    evidence=json.loads(audit.parameters_json)
    assert evidence['before']['notes'] is None and evidence['after']['notes']=='Reviewed note'


@pytest.mark.parametrize('erase_first',['owner','buyer'])
def test_account_erasure_after_merge_preserves_other_owner_and_removes_original_profile(scenario,monkeypatch,tmp_path,erase_first):
    s=scenario
    from src.modules.vehicle_hub.account_erasure import erase_account
    from src.core import file_storage
    Base.metadata.create_all(s.db.bind)
    monkeypatch.setattr(file_storage,'DATA_DIR',tmp_path);monkeypatch.setattr(file_storage,'_config',lambda:None)
    source_id,target_id=s.source.id,s.target.id
    assert s.client.patch(f'/admin-api/vehicles/{source_id}',json={'notes':'Private former profile'}).status_code==200
    preview=s.client.get(f'/admin-api/vehicles/merge-preview?source_id={source_id}&target_id={target_id}').json()
    assert s.client.post('/admin-api/vehicles/merge',json={'source_id':source_id,'target_id':target_id,'preview_token':preview['preview_token'],'reason':'Review duplicate'}).status_code==200
    erase_account(s.db,s.actors[erase_first]);s.db.commit();s.db.expire_all()
    main=s.db.query(m.Vehicle).filter_by(id=target_id).one()
    assert main.notes is None
    if erase_first=='owner':
        assert main.user_email=='buyer@example.com'
        assert s.db.query(m.Vehicle).execution_options(include_merged_vehicles=True).filter_by(id=source_id).count()==0
        assert s.db.query(m.ServiceRecord).count()==0
        assert all('Private former profile' not in row.parameters_json for row in s.db.query(m.DeveloperActionAuditLog))
    else:
        alias=s.db.query(m.Vehicle).execution_options(include_merged_vehicles=True).filter_by(id=source_id).one()
        assert alias.notes=='Private former profile'
        assert s.db.query(m.ServiceRecord).one().description=='Private original work'
        assert main.user_email=='removed-account@invalid'


@pytest.mark.parametrize('original,expected', [
    ('{"oil":true,"brake_fluid":false}', {'oil': True, 'brake_fluid': False, 'overall_ok': True}),
    ('Legacy assessment', {'original_assessment': 'Legacy assessment', 'overall_ok': True}),
])
def test_admin_intake_edit_preserves_signature_and_detailed_fluids(scenario, original, expected):
    s=scenario
    row=m.ServiceIntake(tenant_id=s.actors['owner'].tenant_id,vehicle_id=s.source.id,customer_id=s.actors['owner'].id,
        service_id=s.actors['service'].id,fluids_ok=original,signature='original signature',work_description='Before')
    s.db.add(row);s.db.commit()
    response=s.client.patch(f'/admin-api/service-intakes/{row.id}',json={'work_description':'After','fluids_ok':True})
    assert response.status_code==200,response.text
    import json
    assert json.loads(row.fluids_ok)==expected
    assert row.signature=='original signature'
    assert s.db.query(m.DeveloperActionAuditLog).filter_by(action_type='service_intake.update').count()==1
