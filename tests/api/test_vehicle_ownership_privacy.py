"""Synthetic owner transfer privacy across API, files, export, reminders and erasure."""
import json
from datetime import datetime, timedelta
from pathlib import Path
from zipfile import ZipFile
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import event

from test_vehicle_sharing_lifecycle import sharing
from src.modules.vehicle_hub import models as m
from src.modules.vehicle_hub.ownership import transfer_vehicle_to_new_owner, ensure_vehicle_owner_assignment
from src.modules.vehicle_hub.vehicle_privacy import register_attachment, require_attachment_private
from src.modules.vehicle_hub.routers_v1 import service_records as records, vehicle_archives as archives, repair_photos, analytics, reminders, service_intake
from src.modules.vehicle_hub.routers_v1.schemas import ServiceRecordOutV1, ServiceRecordUpdateV1, ServiceIntakeCreateV1
from src.modules.vehicle_hub.routers_v1.auth import get_current_user
from src.modules.vehicle_hub.database import get_db
from src.modules.vehicle_hub.account_erasure import erase_account
from src.server.main_helpers import export_current_customer_bundle, cleanup_export_dir

PRIVATE = 'PRIVATE-FORMER-OWNER-918'

@pytest.fixture
def data(sharing, monkeypatch, tmp_path):
    s = sharing
    s.db.connection().exec_driver_sql('PRAGMA foreign_keys=ON')
    s.car.notes = PRIVATE; s.car.nickname = PRIVATE
    s.car.photo_path = 'private-cover.jpg'; s.car.orv_front_image_path = 'private-front.jpg'
    s.car.insurance_provider = PRIVATE; s.car.orv_number = PRIVATE
    s.record.description = PRIVATE; s.record.note = PRIVATE; s.record.category = PRIVATE
    s.record.price = 917.25; s.record.mileage = 120000; s.record.performed_at = datetime(2026,1,1)
    s.record.next_service_due_date = datetime.utcnow().date() + timedelta(days=2)
    s.key = f'tenant_{s.owner.tenant_id}/vehicle_{s.car.id}/private.pdf'
    s.record.attachments = json.dumps([{'storage_key':s.key,'path':s.key,'parsed_summary':PRIVATE}])
    s.record.user_id = s.service.id
    s.repair = m.RepairPhotoSession(vehicle_id=s.car.id,service_id=s.service.id,title=PRIVATE,client_id=str(uuid4()))
    s.reminder = m.Reminder(tenant_id=s.owner.tenant_id,customer_id=s.owner.id,vehicle_id=s.car.id,type='VLASTNI',text=PRIVATE,is_manual=True)
    s.db.add_all([s.repair,s.reminder]);s.db.flush()
    s.db.add(m.ServiceIntake(tenant_id=s.owner.tenant_id,customer_id=s.owner.id,service_id=s.service.id,vehicle_id=s.car.id,signature=PRIVATE))
    s.db.add(m.Reservation(tenant_id=s.owner.tenant_id,customer_id=s.owner.id,service_id=s.service.id,vehicle_id=s.car.id,start_datetime=datetime.utcnow(),note=PRIVATE))
    s.db.commit()
    monkeypatch.setattr(records,'assert_module_ready',lambda *a,**kw:None)
    monkeypatch.setattr('src.modules.licensing.service.assert_feature',lambda *a,**kw:None)
    monkeypatch.setattr(reminders,'_ensure_reminders_schema',lambda db:None)
    monkeypatch.setattr('src.server.main_helpers.build_vehicle_export_pdf',lambda path,**kw:Path(path).write_text(json.dumps([r.description for r in kw['records']])))
    monkeypatch.setattr(records,'_refresh_record_attachments_summary',lambda *a:pytest.fail('Must not parse old private evidence for buyer'))
    return s


def transfer(s):
    transfer_vehicle_to_new_owner(s.db,vehicle=s.car,new_owner=s.buyer)
    s.db.commit()
    s.archive = s.db.query(m.VehicleOwnershipArchive).one()
    return s.archive


def test_transfer_archives_private_profile_without_modifying_original_evidence(data):
    s=data; archive=transfer(s)
    assert s.car.notes is None and s.car.orv_number is None and s.car.photo_path is None
    assert s.car.nickname != PRIVATE
    assert json.loads(archive.profile_json)['notes'] == PRIVATE
    assert s.record.description == PRIVATE and s.record.attachments
    assert s.db.query(m.VehicleOwnershipArchive).count()==1
    assert s.reminder.is_completed
    assert archives.list_archives(s.owner,s.db)[0]['id']==archive.id
    assert archives.list_archives(s.buyer,s.db)==[]
    assert archives.archive_detail(archive.id,s.owner,s.db)['records'][0].description==PRIVATE


@pytest.mark.parametrize('actor',['buyer','other_service'])
def test_archive_id_guessing_and_file_guesses_do_not_disclose_metadata(data, actor):
    s=data;archive=transfer(s)
    for operation in [lambda:archives.archive_detail(archive.id,getattr(s,actor),s.db),
        lambda:archives.archive_attachment(archive.id,s.key,getattr(s,actor),s.db),
        lambda:archives.archive_image(archive.id,'cover',getattr(s,actor),s.db)]:
        with pytest.raises(HTTPException) as error: operation()
        assert error.value.status_code==404


@pytest.mark.parametrize('operation',['list','detail'])
def test_buyer_gets_only_technical_summary_and_never_parses_invoice(data, operation):
    s=data;transfer(s)
    row=records.get_service_records(s.car.id,False,s.buyer,s.db)[0] if operation=='list' else records.get_service_record(s.car.id,s.record.id,False,s.buyer,s.db)
    result=ServiceRecordOutV1.model_validate(row,from_attributes=True).model_dump(mode='json')
    assert result['is_historical_summary'] and result['mileage']==120000
    assert PRIVATE not in json.dumps(result) and s.key not in json.dumps(result)
    assert result['price'] is None and result['user_id'] is None
    assert s.record.description==PRIVATE


def test_deleted_old_record_is_not_disclosed_even_when_include_deleted_requested(data):
    s=data;s.record.is_deleted=True;s.db.commit();transfer(s)
    assert records.get_service_records(s.car.id,True,s.buyer,s.db)==[]
    with pytest.raises(HTTPException) as error:records.get_service_record(s.car.id,s.record.id,True,s.buyer,s.db)
    assert error.value.status_code==404
    assert reminders.get_reminders(s.buyer,s.db) is not None


def test_buyer_cannot_edit_original_record(data):
    s=data;transfer(s)
    with pytest.raises(HTTPException) as error:
        records.update_service_record(s.car.id,s.record.id,ServiceRecordUpdateV1(description='Replace original'),s.buyer,s.db)
    assert error.value.status_code==403 and s.record.description==PRIVATE


def test_old_attachments_cannot_be_downloaded_or_laundered_into_new_records(data, monkeypatch):
    s=data;transfer(s)
    monkeypatch.setattr(records,'_resolve_attachment_file',lambda *a,**kw:pytest.fail('No storage access before authorization'))
    with pytest.raises(HTTPException) as error:records.download_service_record_attachment(s.car.id,s.key,s.buyer,s.db)
    assert error.value.status_code==403
    for field in ['storage_key','path']:
        with pytest.raises(HTTPException) as error:
            records._validate_record_attachment_references(json.dumps([{field:s.key}]),vehicle_id=s.car.id,db=s.db,actor=s.buyer)
        assert error.value.status_code==403


def test_repeated_legacy_attachment_reference_produces_single_boundary(data):
    s=data
    s.db.add(m.ServiceRecord(tenant_id=s.owner.tenant_id,vehicle_id=s.car.id,description=PRIVATE,attachments=s.record.attachments))
    s.db.commit();transfer(s)
    assert s.db.query(m.VehicleRecordPrivacy).count()==2
    assert s.db.query(m.VehicleAttachmentPrivacy).count()==1


def test_unattached_upload_stays_private_and_new_upload_remains_usable(data):
    s=data
    oldkey=f'tenant_{s.owner.tenant_id}/vehicle_{s.car.id}/unattached.pdf'
    register_attachment(s.db,vehicle_id=s.car.id,key=oldkey,actor=s.owner);s.db.commit();transfer(s)
    with pytest.raises(HTTPException):require_attachment_private(s.db,vehicle_id=s.car.id,key=oldkey,actor=s.buyer)
    newkey=f'tenant_{s.buyer.tenant_id}/vehicle_{s.car.id}/new.pdf'
    register_attachment(s.db,vehicle_id=s.car.id,key=newkey,actor=s.buyer);s.db.commit()
    require_attachment_private(s.db,vehicle_id=s.car.id,key=newkey,actor=s.buyer)


def test_same_owner_recovery_does_not_strip_profile_or_create_archive(data):
    s=data;ensure_vehicle_owner_assignment(s.db,vehicle=s.car,owner=s.owner);s.db.commit()
    assert s.car.notes==PRIVATE and s.db.query(m.VehicleOwnershipArchive).count()==0


def test_old_repair_evidence_is_hidden_from_buyer_but_preserved_for_original_parties(data):
    s=data;transfer(s)
    assert repair_photos.sessions(s.car.id,s.buyer,s.db)==[]
    with pytest.raises(HTTPException):repair_photos.session_or_404(s.db,s.buyer,s.repair.id)
    for actor in [s.owner,s.service,s.admin]:assert repair_photos.session_or_404(s.db,actor,s.repair.id).title==PRIVATE
    with pytest.raises(HTTPException) as error:repair_photos.session_or_404(s.db,s.service,s.repair.id,write=True)
    assert error.value.status_code==409


def test_private_prices_and_old_upcoming_free_text_are_not_in_buyer_summaries(data):
    s=data;transfer(s)
    assert analytics._build_scoped_query(s.db,current_user=s.buyer,vehicle_id=s.car.id).all()==[]
    assert PRIVATE not in str(reminders.get_reminders(s.buyer,s.db))
    assert analytics._build_scoped_query(s.db,current_user=s.admin,vehicle_id=None).one().price==917.25


@pytest.mark.parametrize('actor',['buyer','owner'])
def test_personal_export_respects_original_data_ownership(data, actor):
    s=data;transfer(s);user=getattr(s,actor)
    directory,zipped,_,_=export_current_customer_bundle(user,email=user.email,db=s.db,app_version='fixture')
    try:
        with ZipFile(zipped) as bundle: payload=json.loads(bundle.read('data/kompletni_export.json'))
        if actor=='buyer':
            assert PRIVATE not in json.dumps(payload)
            assert payload['service_records'][0]['description']=='Servisní záznam před převodem vozidla'
            assert payload['reservations']==[] and payload['service_intakes']==[]
        else:
            assert payload['vehicle_archives'][0]['profile']['notes']==PRIVATE
            assert payload['service_records'][0]['description']==PRIVATE
            assert payload['service_intakes'][0]['signature']==PRIVATE
    finally:cleanup_export_dir(directory)


def test_archive_http_serialization_and_authorization(data):
    s=data;archive=transfer(s)
    app=FastAPI();app.include_router(archives.router);app.include_router(records.router)
    app.dependency_overrides[get_db]=lambda:s.db
    app.dependency_overrides[get_current_user]=lambda:s.buyer
    with TestClient(app) as client:
        assert client.get(f'/vehicle-archives/{archive.id}').status_code==404
        response=client.get(f'/vehicles/{s.car.id}/records')
        assert response.status_code==200 and response.json()[0]['is_historical_summary']
        app.dependency_overrides[get_current_user]=lambda:s.owner
        response=client.get(f'/vehicle-archives/{archive.id}')
        assert response.status_code==200 and response.json()['records'][0]['description']==PRIVATE


def test_intake_requires_current_customer_and_explicit_service_permission(data):
    s=data
    payload=ServiceIntakeCreateV1(vehicle_id=s.car.id,customer_id=s.owner.id,work_description='Repair')
    with pytest.raises(HTTPException):service_intake.create_service_intake(payload,s.other_service,s.db)
    wrong=payload.model_copy(update={'customer_id':s.buyer.id})
    with pytest.raises(HTTPException) as error:service_intake.create_service_intake(wrong,s.service,s.db)
    assert error.value.status_code==409
    result=service_intake.create_service_intake(payload,s.service,s.db)
    assert result.tenant_id==s.owner.tenant_id and result.customer_id==s.owner.id


def test_erasure_removes_old_private_archive_and_evidence_not_new_owner_car(data, monkeypatch, tmp_path):
    s=data;transfer(s)
    from src.core import file_storage
    monkeypatch.setattr(file_storage,'DATA_DIR',tmp_path)
    monkeypatch.setattr(file_storage,'_config',lambda:None)
    ids=(s.owner.id,s.car.id,s.buyer.id)
    erase_account(s.db,s.owner);s.db.commit();s.db.expire_all()
    assert s.db.get(m.Customer,ids[0]) is None
    assert s.db.get(m.Vehicle,ids[1]).user_email==s.buyer.email
    assert s.db.get(m.Customer,ids[2])
    assert s.db.query(m.VehicleOwnershipArchive).count()==0
    assert s.db.query(m.VehicleRecordPrivacy).count()==0
    assert s.db.query(m.RepairPhotoSession).count()==0
    boundary=s.db.get(m.VehicleAttachmentPrivacy,s.key)
    assert boundary and boundary.owner_customer_id is None and boundary.author_customer_id is None
    with pytest.raises(HTTPException):require_attachment_private(s.db,vehicle_id=ids[1],key=s.key,actor=s.buyer)


def test_generated_pdf_and_chart_do_not_include_old_private_text(data, monkeypatch, tmp_path):
    from io import BytesIO
    from PyPDF2 import PdfReader
    s=data;transfer(s)
    monkeypatch.setattr('src.core.config.PDF_DIR',tmp_path/'reports')
    result=records.generate_service_records_pdf(s.car.id,s.buyer,s.db)
    text='\n'.join(page.extract_text() for page in PdfReader(BytesIO(result.body)).pages)
    assert PRIVATE not in text and '917.25' not in text and s.key not in text
    assert '120' in text and result.headers['cache-control']=='private, no-store'
    assert not (tmp_path/'reports').exists(), 'Sensitive reports stay in per-request memory'


def test_original_service_cannot_reshare_previous_customer_invoice_to_buyer(data):
    s=data;transfer(s)
    # An author can still read their evidence, but cannot attach it to a buyer's new record.
    require_attachment_private(s.db,vehicle_id=s.car.id,key=s.key,actor=s.service)
    with pytest.raises(HTTPException) as error:
        records._validate_record_attachment_references(s.record.attachments,vehicle_id=s.car.id,db=s.db,actor=s.service)
    assert error.value.status_code==403
    records._validate_record_attachment_references(s.record.attachments,vehicle_id=s.car.id,db=s.db,actor=s.admin,record_id=s.record.id)


def test_buyer_account_erasure_preserves_previous_owner_archive_without_reopening_vin(data,monkeypatch,tmp_path):
    from src.core import file_storage
    from src.modules.vehicle_hub.ownership import may_restore_vehicle_profile
    s=data;archive=transfer(s);archive_id=archive.id;car_id=s.car.id
    monkeypatch.setattr(file_storage,'DATA_DIR',tmp_path)
    monkeypatch.setattr(file_storage,'_config',lambda:None)
    s.car.notes='PRIVATE-BUYER-NOTE'
    s.db.add(m.ServiceRecord(tenant_id=s.buyer.tenant_id,vehicle_id=car_id,
        user_id=s.service.id,created_by_service_customer_id=s.service.id,description='PRIVATE-BUYER-REPAIR'))
    s.db.commit()
    erase_account(s.db,s.buyer);s.db.commit();s.db.expire_all()
    assert s.db.get(m.Vehicle,car_id), 'Erasing an account does not erase another person\'s archive'
    assert archives.archive_detail(archive_id,s.owner,s.db)['profile']['notes']==PRIVATE
    assert s.db.query(m.ServiceRecord).one().description==PRIVATE
    assert s.db.get(m.Vehicle,car_id).notes is None
    assert not may_restore_vehicle_profile(s.db,vehicle=s.db.get(m.Vehicle,car_id),customer=s.owner)
