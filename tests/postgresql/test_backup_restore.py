"""An actual pg_dump/pg_restore roundtrip with related data and private files.

This proves the fixture restore mechanics, NOT production backup coverage,
retention, RPO/RTO, Supabase Storage recovery or key escrow.
"""
from datetime import date
import hashlib
import json
from pathlib import Path
import shutil
from uuid import uuid4

from fastapi import HTTPException
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from src.core import file_storage
from src.core.security import create_access_token
from src.core.session_revocation import revoke_tokens, require_active_token
from src.modules.vehicle_hub.database import Base
from src.modules.vehicle_hub.models import Customer, Tenant, Vehicle, ServiceRecord, RepairPhotoSession, RepairEvidencePhoto
from src.modules.vehicle_hub.ownership import ensure_vehicle_owner_assignment, release_vehicle_owner_assignment, user_owns_vehicle
from src.modules.vehicle_hub.service_access import create_or_update_vehicle_service_link, service_can_read_vehicle


def snapshot(engine):
    result = {}
    with engine.connect() as connection:
        for table in Base.metadata.sorted_tables:
            rows = [json.dumps(dict(row._mapping),sort_keys=True,default=str) for row in connection.execute(select(table))]
            result[table.name] = {'rows':len(rows), 'sha256':hashlib.sha256('\n'.join(sorted(rows)).encode()).hexdigest()}
    return result


def test_database_and_private_files_restore_with_permissions_and_logout(pg_db, monkeypatch):
    source=pg_db.cluster.root / ('files-'+pg_db.name); source.mkdir(mode=0o700)
    monkeypatch.setattr(file_storage,'DATA_DIR',source)
    token=create_access_token({'sub':'owner@example.invalid','jti':uuid4().hex})
    with pg_db.sessions() as db:
        tenant=Tenant(name='Synthetic backup only',license_key=uuid4().hex); db.add(tenant); db.flush()
        owner=Customer(tenant_id=tenant.id,email='owner@example.invalid',role='user')
        service=Customer(tenant_id=tenant.id,email='service@example.invalid',role='service')
        db.add_all([owner,service]); db.flush()
        car=Vehicle(tenant_id=tenant.id,user_email=owner.email,nickname='Fixture',stk_valid_until=date(2030,1,1))
        db.add(car); db.flush(); ensure_vehicle_owner_assignment(db,vehicle=car,owner=owner)
        grant=create_or_update_vehicle_service_link(db,tenant_id=tenant.id,service_customer_id=service.id,
            owner_customer_id=owner.id,vehicle_id=car.id,approved_by_customer_id=owner.id,source_type='direct_user_grant')
        visit=RepairPhotoSession(vehicle_id=car.id,service_id=service.id,title='Fixture',client_id=str(uuid4()))
        db.add(visit); db.flush()
        # Generated fixture bytes, not photographs or invoice data from a customer.
        photo=b'fixture evidence bytes'; name=uuid4().hex+'.fixture'
        file_storage.persist_file(source/'private_repair_photos'/name,photo)
        evidence=RepairEvidencePhoto(session_id=visit.id,author_id=service.id,author_name='Fixture Service',
            phase='before',note='Synthetic',source='library',sha256=hashlib.sha256(photo).hexdigest(),
            file_path=name,mime_type='application/octet-stream',size_bytes=len(photo),client_id=str(uuid4()))
        invoice=Path(f'service_attachments/tenant_{tenant.id}/vehicle_{car.id}/fixture.txt')
        file_storage.persist_file(source/invoice,b'SYNTHETIC INVOICE - NO CUSTOMER DATA')
        db.add_all([evidence,ServiceRecord(tenant_id=tenant.id,vehicle_id=car.id,description='Fixture repair',
            attachments=json.dumps([{'path':invoice.as_posix()}]),created_by_service_customer_id=service.id,service_access_link_id=grant.id)])
        release_vehicle_owner_assignment(db,vehicle=car,owner=owner)
        db.commit(); revoke_tokens(db,[token])
        identities=(owner.id,service.id,car.id,tenant.id)
    before=snapshot(pg_db.engine)
    dump=pg_db.cluster.root/(pg_db.name+'.dump')
    pg_db.cluster.run('pg_dump','--format=custom','--no-owner','--no-privileges','--file',dump,pg_db.name)
    dump.chmod(0o600)
    restored_name='restore_'+uuid4().hex
    pg_db.cluster.run('createdb','--template=template0',restored_name)
    pg_db.cluster.run('pg_restore','--exit-on-error','--single-transaction','--no-owner','--no-privileges','--dbname',restored_name,dump)
    restored=create_engine(pg_db.cluster.url(restored_name),hide_parameters=True)
    target=pg_db.cluster.root/('restored-files-'+pg_db.name); target.mkdir(mode=0o700)
    manifest={}
    for path in source.rglob('*'):
        if path.is_file():
            relative=path.relative_to(source); destination=target/relative
            destination.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            shutil.copyfile(path,destination); destination.chmod(0o600)
            manifest[relative.as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    try:
        assert snapshot(restored)==before
        for relative,digest in manifest.items(): assert hashlib.sha256((target/relative).read_bytes()).hexdigest()==digest
        with sessionmaker(bind=restored)() as db:
            owner=db.get(Customer,identities[0]);service=db.get(Customer,identities[1]);car=db.get(Vehicle,identities[2])
            assert not user_owns_vehicle(db,owner,car)
            assert not service_can_read_vehicle(db,service,car.id)
            assert db.query(ServiceRecord).count()==db.query(RepairEvidencePhoto).count()==1
            with pytest.raises(HTTPException) as error: require_active_token(db,token)
            assert error.value.status_code==401
            # Restored sequences allow the next write; no duplicate primary key.
            next_tenant=Tenant(name='After restore',license_key=uuid4().hex);db.add(next_tenant);db.commit()
            assert next_tenant.id>identities[3]
        report={'tables':before,'files':manifest,'dump_sha256':hashlib.sha256(dump.read_bytes()).hexdigest(),
            'fixture_only':True,'source_database':pg_db.name,'restore_database':restored_name}
        (pg_db.cluster.root/'restore-manifest.json').write_text(json.dumps(report,indent=2))
    finally:
        restored.dispose()
