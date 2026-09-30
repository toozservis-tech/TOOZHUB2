"""Repair exports use disposable files, no storage provider or real account."""
import hashlib
import io
from datetime import datetime
from types import SimpleNamespace as NS
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from PIL import Image, ImageDraw
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import Customer, Tenant, Vehicle, RepairPhotoSession, RepairEvidencePhoto
from src.modules.vehicle_hub.ownership import ensure_vehicle_owner_assignment
from src.modules.vehicle_hub.routers_v1 import repair_photos as api
from src.modules.vehicle_hub import repair_report


@pytest.fixture
def setup(tmp_path, monkeypatch):
    engine = create_engine('sqlite://')
    event.listen(engine, 'connect', lambda connection, _: connection.execute('PRAGMA foreign_keys=ON'))
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    tenant = Tenant(name='Photo test', license_key=str(uuid4()))
    db.add(tenant); db.flush()
    users = [Customer(tenant_id=tenant.id, email=role+'@example.invalid', name=role, role=role)
             for role in ['user', 'service', 'admin']]
    stranger = Customer(tenant_id=tenant.id, email='other@example.invalid', role='user')
    other_service = Customer(tenant_id=tenant.id, email='other-service@example.invalid', role='service')
    db.add_all([*users, stranger, other_service]); db.flush()
    vehicle = Vehicle(tenant_id=tenant.id, user_email=users[0].email, plate='TEST 123', brand='Škoda', model='Octavia')
    db.add(vehicle); db.flush()
    ensure_vehicle_owner_assignment(db, vehicle=vehicle, owner=users[0], assigned_by_customer_id=users[0].id)
    visit = RepairPhotoSession(vehicle_id=vehicle.id, service_id=users[1].id, title='Oprava laku a předání vozidla', client_id=str(uuid4()))
    db.add(visit); db.commit()
    root=tmp_path/'photos'; root.mkdir()
    monkeypatch.setattr(api,'PHOTO_ROOT',root)
    monkeypatch.setattr(repair_report,'cached_file',lambda path: path)
    yield db, users, stranger, other_service, visit, vehicle, root
    db.close(); engine.dispose()


def add_photo(setup, *, phase='before', note='Přední nárazník - původní stav.', source='camera', size=(1200,800)):
    db, users, _, _, visit, _, root=setup
    image=Image.new('RGB',size,'#edf5f2'); draw=ImageDraw.Draw(image)
    draw.rounded_rectangle((100,120,size[0]-100,size[1]-120),radius=40,fill='#366b62')
    draw.line((120,180,size[0]-160,size[1]-200),fill='#d9447b',width=16)
    stream=io.BytesIO(); image.save(stream,format='JPEG'); content=stream.getvalue()
    name=uuid4().hex+'.jpg'; (root/name).write_bytes(content)
    photo=RepairEvidencePhoto(session_id=visit.id,author_id=users[1].id,author_name='Zkušební servis',phase=phase,
        note=note,source=source,captured_at=datetime(2026,9,30,9,30),uploaded_at=datetime(2026,9,30,10),
        sha256=hashlib.sha256(content).hexdigest(),file_path=name,mime_type='image/jpeg',size_bytes=len(content),client_id=str(uuid4()))
    db.add(photo); db.commit()
    return photo


def test_report_access_is_owner_originating_service_or_admin(setup):
    db, users, stranger, other_service, visit, _, _=setup
    add_photo(setup)
    for allowed in users:
        response=api.repair_report(visit.id,user=allowed,db=db)
        assert response.body.startswith(b'%PDF-')
        assert response.headers['cache-control']=='private, no-store'
    for forbidden in [stranger,other_service]:
        with patch.object(repair_report,'build_repair_report') as renderer:
            with pytest.raises(HTTPException) as failure: api.repair_report(visit.id,user=forbidden,db=db)
            assert failure.value.status_code==403
            renderer.assert_not_called()


@pytest.mark.parametrize('failure',['missing','changed','path','size','invalid_image','phase'])
def test_report_refuses_partial_or_corrupted_evidence(setup,failure):
    db, users, _, _, visit, _, root=setup
    photo=add_photo(setup)
    if failure=='missing': (root/photo.file_path).unlink()
    if failure=='changed': (root/photo.file_path).write_bytes(b'corrupt')
    if failure=='path': photo.file_path='../outside.jpg'
    if failure=='size': photo.size_bytes+=1
    if failure=='phase': photo.phase='unknown'
    if failure=='invalid_image':
        content=b'not an image'; (root/photo.file_path).write_bytes(content)
        photo.sha256=hashlib.sha256(content).hexdigest(); photo.size_bytes=len(content)
    db.commit()
    with pytest.raises(HTTPException) as rejected: api.repair_report(visit.id,user=users[0],db=db)
    assert rejected.value.status_code in (404,409)


def test_oversized_report_is_rejected_before_loading_files(setup):
    db, users, _, _, visit, vehicle, root=setup
    photo=add_photo(setup)
    with patch.object(repair_report,'cached_file') as storage:
        with pytest.raises(HTTPException) as rejected:
            repair_report.build_repair_report(visit,vehicle,[photo]*101,root)
        assert rejected.value.status_code==422
        storage.assert_not_called()


def test_report_supports_empty_documentation_without_inventing_evidence(setup):
    db, users, _, _, visit, _, _=setup
    assert api.repair_report(visit.id,user=users[0],db=db).body.startswith(b'%PDF-')


def test_all_phases_unicode_and_literal_markup_render_without_losing_files(setup):
    db, users, _, _, visit, _, root=setup
    for phase in ['before','during','after']:
        add_photo(setup,phase=phase,note='Žluťoučký kůň <script> & kontrola. '+('Delší poznámka. '*80))
    originals={p.name:p.read_bytes() for p in root.iterdir()}
    response=api.repair_report(visit.id,user=users[0],db=db)
    assert response.body.startswith(b'%PDF-')
    assert {p.name:p.read_bytes() for p in root.iterdir()}==originals


def test_upload_retry_preserves_exact_photo_and_rejects_changed_payload(setup,monkeypatch):
    import base64
    from src.modules.vehicle_hub.models import VehicleServiceLink
    db, users, _, _, visit, vehicle, root=setup
    db.add(VehicleServiceLink(tenant_id=vehicle.tenant_id,service_customer_id=users[1].id,
        owner_customer_id=users[0].id,vehicle_id=vehicle.id,status='approved',scope_create_service_record=True))
    db.commit()
    monkeypatch.setattr(api,'persist_file',lambda path, content: path.write_bytes(content))
    image=Image.new('RGB',(100,80),'#406b62'); buffer=io.BytesIO(); image.save(buffer,format='JPEG')
    content=buffer.getvalue()
    payload=api.PhotoCreate(phase='during',note='Kontrola po rozebrání',source='camera',
        client_id=uuid4(),file_content_base64=base64.b64encode(content).decode())
    first=api.upload(visit.id,payload,user=users[1],db=db)
    retry=api.upload(visit.id,payload,user=users[1],db=db)
    assert retry['id']==first['id']
    assert db.query(RepairEvidencePhoto).count()==1
    assert next(root.iterdir()).read_bytes()==content
    assert first['sha256']==hashlib.sha256(content).hexdigest()
    for changes in [{'note':'Jiný obsah'}, {'captured_at':datetime(2026,9,30,10)}]:
        changed=payload.model_copy(update=changes)
        with pytest.raises(HTTPException) as conflict: api.upload(visit.id,changed,user=users[1],db=db)
        assert conflict.value.status_code==409
    assert db.query(RepairEvidencePhoto).count()==1
    assert len(list(root.iterdir()))==1


def test_owner_cannot_add_service_evidence_and_revoked_service_cannot_add_more(setup,monkeypatch):
    from src.modules.vehicle_hub.models import VehicleServiceLink
    db, users, _, _, visit, vehicle, _=setup
    payload=api.PhotoCreate(phase='after',source='library',client_id=uuid4(),file_content_base64='YWJj')
    link=VehicleServiceLink(tenant_id=vehicle.tenant_id,service_customer_id=users[1].id,
        owner_customer_id=users[0].id,vehicle_id=vehicle.id,status='revoked',scope_create_service_record=True)
    db.add(link); db.commit()
    with patch.object(api,'persist_file') as storage:
        for user in users[:2]:
            with pytest.raises(HTTPException) as refused: api.upload(visit.id,payload,user=user,db=db)
            assert refused.value.status_code==403
        storage.assert_not_called()
    # Previous documentation stays readable by its author and the vehicle owner.
    add_photo(setup)
    assert api.repair_report(visit.id,user=users[1],db=db).body.startswith(b'%PDF-')


def test_parallel_report_has_retry_and_does_not_exhaust_server_memory(setup):
    db, users, _, _, visit, _, _=setup
    with repair_report._REPORT_SLOT:
        with pytest.raises(HTTPException) as busy: api.repair_report(visit.id,user=users[0],db=db)
        assert busy.value.status_code==503
        assert busy.value.headers['Retry-After']=='5'
    assert api.repair_report(visit.id,user=users[0],db=db).body.startswith(b'%PDF-')
