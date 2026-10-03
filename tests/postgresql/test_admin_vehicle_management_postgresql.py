"""Private local PostgreSQL only: actual SQL migration, concurrency and reviewed merges."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from datetime import datetime
import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import insert, text
from sqlalchemy.exc import IntegrityError
from src.modules.vehicle_hub import models as m
from src.modules.vehicle_hub.ownership import ensure_vehicle_owner_assignment
from src.modules.vehicle_hub.vehicle_duplicates import merge_preview, merge_vehicles, duplicate_report
from src.modules.vehicle_hub.vehicle_deletion import deletion_preview, delete_reviewed_vehicle
from src.core.file_erasure import FileErasure


def upgrade(engine):
    path = Path(__file__).resolve().parents[2] / 'alembic/versions/20261002_0013_workshops_vehicle_identity.py'
    spec = importlib.util.spec_from_file_location('workshop_migration', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    with engine.begin() as connection, Operations.context(MigrationContext.configure(connection)):
        module.upgrade()


def fleet(pg_db, copies=3):
    with pg_db.sessions() as db:
        tenant=m.Tenant(name='Synthetic',license_key='workshop-test'); db.add(tenant); db.flush()
        owner=m.Customer(tenant_id=tenant.id,email='owner@example.invalid',role='user')
        admin=m.Customer(tenant_id=tenant.id,email='admin@example.invalid',role='developer_admin')
        db.add_all([owner,admin]); db.flush(); identities=[]
        for _ in range(copies):
            identity=db.execute(insert(m.Vehicle.__table__).values(tenant_id=tenant.id,user_email=owner.email,
                vin='tmb-jf73t2b9044629',plate='1AB2345')).inserted_primary_key[0]
            car=db.get(m.Vehicle,identity); ensure_vehicle_owner_assignment(db,vehicle=car,owner=owner); identities.append(identity)
        record=m.ServiceRecord(tenant_id=tenant.id,vehicle_id=identities[0],user_id=owner.id,
            performed_at=datetime(2026,1,1),description='Preserved original')
        db.add(record); db.commit()
        return identities,admin.id,record.id


def test_migration_idempotence_legacy_duplicates_and_chained_merge(pg_db):
    ids,admin,record=fleet(pg_db)
    upgrade(pg_db.engine); upgrade(pg_db.engine)
    with pg_db.sessions() as db:
        assert duplicate_report(db)['checked_vehicles']==3
        # Merge two rows whose claim belongs to a third, then the third into them.
        for source,target in [(ids[0],ids[1]),(ids[1],ids[2])]:
            preview=merge_preview(db,source,target)
            merge_vehicles(db,source_id=source,target_id=target,preview_token=preview['preview_token'],
                confirmed_identity=True,actor_id=admin,reason='Synthetic reviewed identity')
            db.commit()
        assert db.query(m.Vehicle).count()==1
        assert db.get(m.ServiceRecord,record).vehicle_id==ids[2]
        aliases=db.query(m.Vehicle).execution_options(include_merged_vehicles=True).filter(m.Vehicle.id.in_(ids[:2])).all()
        assert all(row.merged_into_id==ids[2] for row in aliases)
        assert db.get(m.VehicleVINClaim,'TMBJF73T2B9044629').vehicle_id==ids[2]
        assert db.query(m.DeveloperActionAuditLog).filter_by(action_type='vehicle.merge').count()==2
    # Every SQL writer remains guarded after consolidation, not just the ORM.
    with pytest.raises(IntegrityError), pg_db.engine.begin() as connection:
        connection.execute(insert(m.Vehicle.__table__).values(tenant_id=1,user_email='owner@example.invalid',nickname='Duplicate',vin='TMB JF73T2B9044629'))


def test_reviewed_vehicle_delete_with_real_foreign_keys_and_merged_archives(pg_db):
    ids,admin_id,record_id=fleet(pg_db,copies=3)
    upgrade(pg_db.engine)
    with pg_db.sessions() as db:
        merge=merge_preview(db,ids[0],ids[1])
        merge_vehicles(db,source_id=ids[0],target_id=ids[1],preview_token=merge['preview_token'],
            confirmed_identity=True,actor_id=admin_id,reason='Synthetic reviewed merge')
        db.commit()
        db.add(m.ServiceRecordAuditLog(tenant_id=1,service_record_id=record_id,vehicle_id=ids[0],
            action='update',previous_snapshot_json='{}'))
        db.add(m.VehicleORVScan(tenant_id=1,vehicle_id=ids[0],front_image_path='tenant_1/scan/front.jpg'))
        db.commit()
        preview=deletion_preview(db,ids[1])
        assert any(x['key']=='merged_profiles' and x['count']==1 for x in preview['items'])
        result=delete_reviewed_vehicle(db,ids[1],preview_token=preview['preview_token'],delete_related=True,
            actor=db.get(m.Customer,admin_id),reason='Synthetic reviewed removal')
        db.commit()
        assert result['files_pending']==1 and db.query(FileErasure).count()==1
        remaining=db.query(m.Vehicle).execution_options(include_merged_vehicles=True).all()
        assert [row.id for row in remaining]==[ids[2]]
        assert db.query(m.ServiceRecord).count()==0 and db.query(m.ServiceRecordAuditLog).count()==0
        assert db.query(m.VehicleORVScan).count()==0 and db.query(m.VehicleOwnership).count()==1
        assert db.query(m.Customer).count()==2
        assert db.query(m.DeveloperActionAuditLog).filter_by(action_type='vehicle.delete').count()==1


@pytest.mark.parametrize('delete_record_vehicle', [True, False])
def test_delete_with_legacy_history_preserves_the_other_vehicle_under_real_foreign_keys(pg_db, delete_record_vehicle):
    ids,admin_id,record_id=fleet(pg_db,copies=2)
    upgrade(pg_db.engine)
    with pg_db.sessions() as db:
        history=m.ServiceRecordAuditLog(tenant_id=1,service_record_id=record_id,vehicle_id=ids[1],
            action='update',previous_snapshot_json='{"description":"Preserved original"}')
        db.add(history);db.commit();history_id=history.id
        vehicle_id=ids[0] if delete_record_vehicle else ids[1]
        preview=deletion_preview(db,vehicle_id)
        assert preview['preserved_history_count']==(0 if delete_record_vehicle else 1)
        delete_reviewed_vehicle(db,vehicle_id,preview_token=preview['preview_token'],delete_related=delete_record_vehicle,
            actor=db.get(m.Customer,admin_id),reason='Reviewed synthetic legacy history')
        db.commit();db.expire_all()
        assert db.get(m.Vehicle,vehicle_id) is None
        assert db.get(m.Vehicle,ids[1] if delete_record_vehicle else ids[0])
        if delete_record_vehicle:
            assert db.get(m.ServiceRecord,record_id) is None
            assert db.get(m.ServiceRecordAuditLog,history_id) is None
        else:
            assert db.get(m.ServiceRecord,record_id).vehicle_id==ids[0]
            assert db.get(m.ServiceRecordAuditLog,history_id).vehicle_id==ids[0]
            assert db.get(m.ServiceRecordAuditLog,history_id).previous_snapshot_json=='{"description":"Preserved original"}'


def test_sql_unique_claim_parallel_writers_and_identity_update(pg_db):
    ids,_,_=fleet(pg_db, copies=1)
    with pg_db.sessions() as db: template=db.get(m.Vehicle,ids[0]); tenant=template.tenant_id; email=template.user_email
    upgrade(pg_db.engine)
    barrier=Barrier(5)
    def worker(index):
        with pg_db.engine.connect() as connection:
            transaction=connection.begin(); barrier.wait(timeout=5)
            try:
                connection.execute(insert(m.Vehicle.__table__).values(tenant_id=tenant,user_email=email,nickname='Fixture',vin='WVW-ZZZ1JZXW000001'))
                transaction.commit(); return 200
            except IntegrityError:
                transaction.rollback(); return 409
    with ThreadPoolExecutor(max_workers=5) as pool: results=list(pool.map(worker,range(5)))
    assert sorted(results)==[200,409,409,409,409]
    with pg_db.engine.begin() as connection:
        other=connection.execute(insert(m.Vehicle.__table__).values(tenant_id=tenant,user_email=email,nickname='Fixture',vin='WVWZZZ1JZXW000002')).inserted_primary_key[0]
    with pytest.raises(IntegrityError), pg_db.engine.begin() as connection:
        connection.execute(m.Vehicle.__table__.update().where(m.Vehicle.id==other).values(vin='wvw zzz1jzxw000001'))
    with pg_db.engine.begin() as connection:
        assert connection.scalar(text('SELECT count(*) FROM vehicles'))==3


def test_plate_without_vin_cannot_be_added_twice_by_orm(pg_db):
    ids,_,_=fleet(pg_db,copies=1)
    with pg_db.sessions() as db: template=db.get(m.Vehicle,ids[0]); tenant=template.tenant_id; email=template.user_email
    upgrade(pg_db.engine)
    with pg_db.sessions() as db:
        db.add(m.Vehicle(tenant_id=tenant,user_email=email,nickname='Fixture',plate='2BC 3456')); db.commit()
    from fastapi import HTTPException
    with pg_db.sessions() as db, pytest.raises(HTTPException) as error:
        db.add(m.Vehicle(tenant_id=tenant,user_email=email,nickname='Duplicate',plate='2bc-3456')); db.commit()
    assert error.value.status_code==409


def test_startup_migration_adds_missing_columns_without_touching_legacy_data(pg_db):
    ids,_,_=fleet(pg_db,copies=1)
    with pg_db.engine.begin() as connection:
        connection.execute(text('DROP TABLE vehicle_vin_claims'))
        for table in ['customers','service_registration_requests']:
            for column in ['workshop_same_as_registered','workshop_street','workshop_street_number','workshop_city','workshop_zip']:
                connection.execute(text(f'ALTER TABLE {table} DROP COLUMN {column}'))
        connection.execute(text('ALTER TABLE vehicles DROP COLUMN merged_into_id'))
        connection.execute(text('ALTER TABLE vehicles DROP COLUMN merged_vin'))
    from scripts.migrate_workshops_vehicle_identity import migrate
    migrate(pg_db.engine)
    migrate(pg_db.engine)
    with pg_db.sessions() as db:
        car=db.get(m.Vehicle,ids[0]);assert car.merged_into_id is None
        assert car.vin=='tmb-jf73t2b9044629' and car.plate=='1AB2345'
        assert db.get(m.VehicleVINClaim,'TMBJF73T2B9044629').vehicle_id==ids[0]
        assert db.query(m.Customer).filter_by(role='user').one().workshop_same_as_registered is None


@pytest.mark.parametrize('first',['old','buyer'])
def test_real_foreign_keys_and_private_erasure_after_cross_owner_merge(pg_db,monkeypatch,tmp_path,first):
    from src.modules.vehicle_hub.ownership import transfer_vehicle_to_new_owner
    from src.modules.vehicle_hub.account_erasure import erase_account
    from src.modules.vehicle_hub.database import Base
    from src.core import file_storage
    Base.metadata.create_all(pg_db.engine)
    monkeypatch.setattr(file_storage,'DATA_DIR',tmp_path);monkeypatch.setattr(file_storage,'_config',lambda:None)
    ids,admin,record=fleet(pg_db,copies=2)
    with pg_db.sessions() as db:
        old=db.get(m.Customer,db.get(m.ServiceRecord,record).user_id)
        tenant=m.Tenant(name='Buyer',license_key='fixture-buyer');db.add(tenant);db.flush()
        buyer=m.Customer(tenant_id=tenant.id,role='user',email='buyer@example.invalid');db.add(buyer);db.flush()
        transfer_vehicle_to_new_owner(db,vehicle=db.get(m.Vehicle,ids[1]),new_owner=buyer)
        db.get(m.Vehicle,ids[0]).notes='Private source';db.commit();old_id,buyer_id=old.id,buyer.id
    upgrade(pg_db.engine)
    with pg_db.sessions() as db:
        preview=merge_preview(db,*ids)
        merge_vehicles(db,source_id=ids[0],target_id=ids[1],preview_token=preview['preview_token'],confirmed_identity=True,actor_id=admin,reason='Reviewed original')
        db.commit()
        erase_account(db,db.get(m.Customer,old_id if first=='old' else buyer_id));db.commit();db.expire_all()
        main=db.query(m.Vehicle).filter_by(id=ids[1]).one()
        if first=='old':
            assert main.user_email=='buyer@example.invalid'
            assert db.query(m.Vehicle).execution_options(include_merged_vehicles=True).filter_by(id=ids[0]).count()==0
            assert db.get(m.ServiceRecord,record) is None
        else:
            assert main.user_email=='removed-account@invalid'
            assert db.get(m.ServiceRecord,record).description=='Preserved original'
