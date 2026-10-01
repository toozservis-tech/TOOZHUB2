"""File access stays bound to the authorized vehicle, including legacy metadata."""
from datetime import date
import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.modules.vehicle_hub.database import Base, get_db
from src.modules.vehicle_hub.models import Customer, Tenant, Vehicle, ServiceRecord
from src.modules.vehicle_hub.ownership import ensure_vehicle_owner_assignment
from src.modules.vehicle_hub.routers_v1 import service_records as records
from src.modules.vehicle_hub.routers_v1.auth import get_current_user


@pytest.fixture
def files(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path/'attachments.sqlite'}", connect_args={'check_same_thread':False})
    Base.metadata.create_all(engine)
    db=sessionmaker(bind=engine, autoflush=False)()
    rows=[]
    for index in range(2):
        tenant=Tenant(name=f'Fixture {index}', license_key=f'file-fixture-{index}')
        db.add(tenant);db.flush()
        user=Customer(email=f'fixture-{index}@example.invalid', role='user', tenant_id=tenant.id)
        db.add(user);db.flush()
        car=Vehicle(tenant_id=tenant.id,user_email=user.email,nickname=f'Fixture {index}',stk_valid_until=date(2030,1,1))
        db.add(car);db.flush()
        ensure_vehicle_owner_assignment(db,vehicle=car,owner=user)
        rows.append((user,car))
    db.commit()
    root=tmp_path/'attachments';root.mkdir()
    own_key=f'tenant_{rows[0][0].tenant_id}/vehicle_{rows[0][1].id}/own.txt'
    foreign_key=f'tenant_{rows[1][0].tenant_id}/vehicle_{rows[1][1].id}/foreign.txt'
    for key,data in [(own_key,b'OWN FILE'),(foreign_key,b'PRIVATE FOREIGN INVOICE')]:
        target=root/key;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    storage_reads=[]
    def cache(path): storage_reads.append(path);return path
    monkeypatch.setattr(records,'SERVICE_RECORD_ATTACHMENTS_DIR',root)
    monkeypatch.setattr(records,'cached_file',cache)
    monkeypatch.setattr(records,'assert_module_ready',lambda *args,**kwargs:None)
    state=SimpleNamespace(db=db,root=root,owner=rows[0][0],car=rows[0][1],foreign=rows[1][1],
        own_key=own_key,foreign_key=foreign_key,storage_reads=storage_reads)
    app=FastAPI();app.include_router(records.router,prefix='/api/v1')
    app.dependency_overrides[get_current_user]=lambda: state.owner
    app.dependency_overrides[get_db]=lambda: db
    with TestClient(app) as client:
        state.client=client;yield state
    db.close();engine.dispose()


def download(s,key):
    return s.client.get(f'/api/v1/vehicles/{s.car.id}/records/attachments/download',params={'key':key})


def test_download_cannot_escape_the_authorized_vehicle_with_parent_segments(files):
    s=files
    forged=f'tenant_{s.owner.tenant_id}/vehicle_{s.car.id}/../../{s.foreign_key}'
    response=download(s,forged)
    assert response.status_code == 403
    assert b'PRIVATE FOREIGN INVOICE' not in response.content
    assert s.storage_reads == [], 'Reject before reading local or remote storage'


@pytest.mark.parametrize('kind', ['foreign','absolute','backslash','parent','nested','empty_name','wrong_prefix','control','padded'])
def test_noncanonical_or_other_vehicle_keys_never_touch_storage(files,kind):
    s=files
    keys={
        'foreign': s.foreign_key,
        'absolute': str(s.root/s.own_key),
        'backslash': s.own_key.replace('/', '\\'),
        'parent': f'tenant_{s.owner.tenant_id}/vehicle_{s.car.id}/../vehicle_{s.foreign.id}/foreign.txt',
        'nested': f'tenant_{s.owner.tenant_id}/vehicle_{s.car.id}/extra/own.txt',
        'empty_name': f'tenant_{s.owner.tenant_id}/vehicle_{s.car.id}/',
        'wrong_prefix': f'wrong/vehicle_{s.car.id}/own.txt',
        'control': s.own_key+'\x00',
        'padded': ' '+s.own_key,
    }
    response=download(s,keys[kind])
    assert response.status_code==403,response.text
    assert s.storage_reads==[]


def test_correct_attachment_stays_downloadable(files):
    s=files;response=download(s,s.own_key)
    assert response.status_code==200
    assert response.content==b'OWN FILE'
    assert response.headers['cache-control']=='private, no-store'
    assert response.headers['x-content-type-options']=='nosniff'
    assert len(s.storage_reads)==1


def test_historical_tenant_directory_remains_available_after_vehicle_transfer(files):
    s=files
    historical=f'tenant_12345/vehicle_{s.car.id}/historical.txt'
    path=s.root/historical;path.parent.mkdir(parents=True);path.write_bytes(b'OWN HISTORICAL INVOICE')
    response=download(s,historical)
    assert response.status_code==200 and response.content==b'OWN HISTORICAL INVOICE'


@pytest.mark.parametrize('directory', [False,True])
def test_symlink_to_other_vehicle_is_rejected_before_storage(files,directory):
    s=files
    if directory:
        prefix=s.root/'tenant_555';prefix.mkdir()
        (prefix/f'vehicle_{s.car.id}').symlink_to((s.root/s.foreign_key).parent,target_is_directory=True)
        key=f'tenant_555/vehicle_{s.car.id}/foreign.txt'
    else:
        key=f'tenant_{s.owner.tenant_id}/vehicle_{s.car.id}/link.txt'
        (s.root/key).symlink_to(s.root/s.foreign_key)
    assert download(s,key).status_code==403
    assert s.storage_reads==[]


def record_body(attachments):
    return {'performed_at':'2026-10-01T09:00:00','description':'Fixture repair','category':'JINE',
            'attachments':json.dumps(attachments)}


@pytest.mark.parametrize('field',['storage_key','path'])
@pytest.mark.parametrize('method',['post','put'])
def test_foreign_attachment_references_cannot_be_saved_on_own_record(files,field,method):
    s=files;url=f'/api/v1/vehicles/{s.car.id}/records'
    if method=='put':
        original=ServiceRecord(vehicle_id=s.car.id,tenant_id=s.owner.tenant_id,user_id=s.owner.id,
                               description='Original fixture',category='JINE')
        s.db.add(original);s.db.commit();url+=f'/{original.id}'
    response=s.client.request(method,url,json=record_body([{field:s.foreign_key}]))
    assert response.status_code==422,response.text
    assert s.storage_reads==[]
    if method=='put':
        s.db.refresh(original);assert original.attachments is None and original.description=='Original fixture'
    else: assert s.db.query(ServiceRecord).count()==0


def test_correct_reference_can_be_attached_and_retrieved(files):
    s=files
    response=s.client.post(f'/api/v1/vehicles/{s.car.id}/records',json=record_body([{'storage_key':s.own_key}]))
    assert response.status_code==200,response.text
    assert s.storage_reads==[], 'Saving metadata must not download files'
    assert s.db.get(ServiceRecord,response.json()['id']).attachments is not None
    assert download(s,s.own_key).content==b'OWN FILE'


def test_legacy_foreign_metadata_cannot_read_another_invoice_during_summary_refresh(files,monkeypatch):
    s=files
    original=ServiceRecord(vehicle_id=s.car.id,tenant_id=s.owner.tenant_id,user_id=s.owner.id,
        description='Legacy fixture',category='JINE',attachments=json.dumps([{'storage_key':s.foreign_key,'parsed_summary':{}}]))
    s.db.add(original);s.db.commit()
    def unexpected(*args,**kwargs): raise AssertionError('Foreign file reached parser')
    monkeypatch.setattr(records,'_extract_text_from_file',unexpected)
    response=s.client.get(f'/api/v1/vehicles/{s.car.id}/records/{original.id}')
    assert response.status_code==200,response.text
    assert b'PRIVATE FOREIGN INVOICE' not in response.content
    assert s.storage_reads==[]
    assert json.loads(response.json()['attachments'])[0]['parsed_summary']=={}


def test_own_document_summary_still_refreshes_using_bound_vehicle(files,monkeypatch):
    s=files
    original=ServiceRecord(vehicle_id=s.car.id,tenant_id=s.owner.tenant_id,user_id=s.owner.id,
        description='Fixture repair',category='JINE',attachments=json.dumps([{'storage_key':s.own_key,'parsed_summary':{}}]))
    s.db.add(original);s.db.commit()
    parsed=[]
    def parse(*,content,**kwargs): parsed.append(content);return 'Fixture text',None,'text'
    monkeypatch.setattr(records,'_extract_text_from_file',parse)
    monkeypatch.setattr(records,'_parse_document_payload',lambda **kwargs:{'supplier_name':'Fixture supplier'})
    monkeypatch.setattr(records,'_build_service_report_payload',lambda *args,**kwargs:{'supplier_name':'Fixture supplier'})
    response=s.client.get(f'/api/v1/vehicles/{s.car.id}/records/{original.id}')
    assert response.status_code==200,response.text
    assert parsed==[b'OWN FILE']
    assert json.loads(response.json()['attachments'])[0]['parsed_summary']['supplier_name']=='Fixture supplier'
