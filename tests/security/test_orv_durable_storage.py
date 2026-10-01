"""No external calls: fake private object store and disposable database/documents."""
import base64
import hashlib
import io
from pathlib import Path

import httpx
import pytest
from fastapi import HTTPException
from PIL import Image
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from src.core import file_storage
from src.core.file_erasure import FileErasure, process_file_erasures
from src.modules.vehicle_hub import orv_scans
from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import Customer, Tenant, Vehicle, VehicleORVScan


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    engine = create_engine('sqlite:///' + str(tmp_path/'documents.sqlite'))
    event.listen(engine, 'connect', lambda conn, _: conn.execute('PRAGMA foreign_keys=ON'))
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    tenant = Tenant(name='Disposable ORV test', license_key='orv-storage-fixture')
    db.add(tenant); db.flush()
    user = Customer(tenant_id=tenant.id, email='document@example.invalid', role='user')
    db.add(user); db.commit()
    root = tmp_path/'private'; root.mkdir()
    monkeypatch.setattr(file_storage, 'DATA_DIR', root)
    monkeypatch.setattr(orv_scans, 'ORV_SCANS_DIR', root/'vehicle_orv_scans')
    monkeypatch.setattr(file_storage, '_config', lambda: ('https://storage.example.invalid/private/', {'apikey':'fixture'}))
    monkeypatch.setattr(orv_scans, '_extract_ocr_text', lambda *args: 'VIN: TMBJF73T2B9044629')
    objects = {}
    def upload(url, *, content, **kwargs):
        assert kwargs['headers']['Content-Type'] == 'image/jpeg'
        assert kwargs['headers']['x-upsert'] == 'false'
        objects[url] = content
        return httpx.Response(200, request=httpx.Request('POST', url))
    def download(url, **kwargs):
        return httpx.Response(200, content=objects[url], request=httpx.Request('GET',url))
    def remove(url, **kwargs):
        objects.pop(url, None)
        return httpx.Response(200, request=httpx.Request('DELETE',url))
    monkeypatch.setattr(file_storage.httpx, 'post', upload)
    monkeypatch.setattr(file_storage.httpx, 'get', download)
    monkeypatch.setattr(file_storage.httpx, 'delete', remove)
    yield db, factory, user, root, objects, upload
    db.close(); engine.dispose()


def scan(db, user):
    image = Image.new('RGB', (80,60), '#487068')
    buffer = io.BytesIO(); image.save(buffer, format='PNG')
    payload = base64.b64encode(buffer.getvalue()).decode()
    return orv_scans.create_orv_scan_record(db=db, current_user=user,
        front_image_base64=payload, back_image_base64=payload,
        front_image_mime_type='image/png', back_image_mime_type='image/png', source='fixture')


def test_both_sides_survive_empty_server_cache(fixture):
    db, _, user, root, objects, _ = fixture
    row = scan(db,user)
    assert row.status == 'review' and len(objects) == 2
    for relative, digest in [(row.front_image_path,row.front_image_hash),(row.back_image_path,row.back_image_hash)]:
        path = root/'vehicle_orv_scans'/relative
        original = path.read_bytes(); path.unlink()
        restored = file_storage.cached_file(path).read_bytes()
        assert restored == original
        assert hashlib.sha256(restored).hexdigest() == digest
    assert db.query(FileErasure).count() == 0


@pytest.mark.parametrize('failure', ['first_side','second_side','ocr'])
def test_failed_processing_never_claims_success_and_queues_exact_intended_paths(fixture, monkeypatch, failure):
    db, factory, user, root, objects, upload = fixture
    calls=[]
    def upload_then_fail(url, **kwargs):
        calls.append(url)
        response = upload(url, **kwargs) # Provider accepted, but the response was lost.
        if len(calls) == (1 if failure == 'first_side' else 2):
            raise httpx.ReadTimeout('fixture', request=httpx.Request('POST',url))
        return response
    if failure == 'ocr':
        monkeypatch.setattr(orv_scans, '_extract_ocr_text', lambda *args: (_ for _ in ()).throw(RuntimeError('fixture')))
    else:
        monkeypatch.setattr(file_storage.httpx, 'post', upload_then_fail)
    with pytest.raises((HTTPException,RuntimeError)): scan(db,user)
    row=db.query(VehicleORVScan).one()
    assert row.status == 'failed'
    assert row.front_image_path is None and row.back_image_path is None
    assert not row.front_captured and not row.back_captured
    assert db.query(FileErasure).count() == 2
    result=process_file_erasures(session_factory=factory)
    assert result == {'removed':2, 'retrying':0}
    assert not objects
    assert not list((root/'vehicle_orv_scans').rglob('*.jpg'))


def test_abrupt_stop_keeps_committed_inventory(fixture, monkeypatch):
    db, factory, user, _, objects, upload = fixture
    def interrupted(url, **kwargs):
        upload(url, **kwargs)
        raise KeyboardInterrupt('simulated process stop')
    monkeypatch.setattr(file_storage.httpx, 'post', interrupted)
    with pytest.raises(KeyboardInterrupt): scan(db,user)
    db.rollback()
    with factory() as observer:
        row=observer.query(VehicleORVScan).one()
        assert row.status == 'processing'
        assert row.front_image_path and row.back_image_path
        assert row.initiated_by_customer_id == user.id
        assert len(objects) == 1


@pytest.mark.parametrize('status',['processing','failed'])
def test_incomplete_scan_cannot_be_used_to_claim_verified_document(fixture,status):
    db, _, user, _, _, _ = fixture
    row=VehicleORVScan(tenant_id=user.tenant_id,initiated_by_customer_id=user.id,status=status)
    car=Vehicle(tenant_id=user.tenant_id,user_email=user.email,plate='TEST')
    db.add_all([row,car]); db.commit()
    with pytest.raises(HTTPException) as rejected:
        orv_scans.apply_orv_scan_to_vehicle(db=db,vehicle=car,current_user=user,scan_id=row.id,
            orv_number=None,use_owner_data=False,data_trust_state='verified_by_user',create_payload={})
    assert rejected.value.status_code == 409
    assert car.orv_front_image_path is None


def test_reused_database_ids_never_reuse_storage_paths():
    a=orv_scans._scan_image_path(tenant_id=1,scan_id=1,side='front')
    b=orv_scans._scan_image_path(tenant_id=1,scan_id=1,side='front')
    assert a != b and a.endswith('.jpg') and b.endswith('.jpg')


def test_only_abandoned_unfinished_scans_are_recovered(fixture):
    from datetime import datetime, timedelta
    from src.core.file_erasure import recover_abandoned_document_uploads
    db, factory, user, _, _, _ = fixture
    now=datetime.utcnow()
    rows=[]
    for status, age in [('processing',25),('processing',1),('review',25),('confirmed',25),('processing',30)]:
        row=VehicleORVScan(tenant_id=user.tenant_id,initiated_by_customer_id=user.id,status=status,
            created_at=now-timedelta(hours=age),front_captured=True,back_captured=True,
            front_image_path=f'fixture/{status}-{age}-front.jpg',back_image_path=f'fixture/{status}-{age}-back.jpg')
        db.add(row); db.flush()
        if age != 30:  # Legacy incomplete inventory must remain untouched.
            row.front_image_path=orv_scans._scan_image_path(tenant_id=user.tenant_id,scan_id=row.id,side='front')
            row.back_image_path=orv_scans._scan_image_path(tenant_id=user.tenant_id,scan_id=row.id,side='back')
        rows.append(row)
    db.commit()
    assert recover_abandoned_document_uploads(session_factory=factory, now=now) == 1
    db.expire_all()
    assert rows[0].status == 'failed' and rows[0].front_image_path is None
    assert all(row.front_image_path is not None for row in rows[1:])
    assert db.query(FileErasure).count() == 2
    assert recover_abandoned_document_uploads(session_factory=factory, now=now) == 0


def test_confirmed_scan_cannot_be_moved_or_copied_to_another_vehicle(fixture):
    db, _, user, _, _, _ = fixture
    row = scan(db, user)
    original = Vehicle(tenant_id=user.tenant_id,user_email=user.email,vin='TMBJF73T2B9044629')
    other = Vehicle(tenant_id=user.tenant_id,user_email=user.email,vin='TMBEFF654V7529422')
    db.add_all([original, other]); db.commit()
    def attach(vehicle):
        orv_scans.apply_orv_scan_to_vehicle(db=db,vehicle=vehicle,current_user=user,scan_id=row.id,
            orv_number=None,use_owner_data=False,data_trust_state='verified_by_user',create_payload={'vin':vehicle.vin})
    attach(original); db.commit()
    original_path = original.orv_front_image_path
    attach(original); db.commit() # explicit save/retry on the same vehicle remains supported
    with pytest.raises(HTTPException) as rejected:
        attach(other)
    assert rejected.value.status_code == 409
    db.rollback()
    assert row.vehicle_id == original.id
    assert original.orv_front_image_path == original_path
    assert other.orv_front_image_path is None
