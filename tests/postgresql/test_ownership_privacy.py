"""Privacy snapshots and waiting writers on real isolated PostgreSQL."""
import json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from fastapi import HTTPException

from test_concurrent_vehicle_flows import fleet
from src.modules.vehicle_hub.models import Customer, Vehicle, VehicleOwnershipArchive, ServiceRecord
from src.modules.vehicle_hub.ownership import transfer_vehicle_to_new_owner
from src.modules.vehicle_hub.routers_v1 import vehicles, service_records, service_intake
from src.modules.vehicle_hub.routers_v1.schemas import ServiceRecordCreateV1, ServiceIntakeCreateV1


def test_snapshot_uses_latest_committed_original_after_lock_not_stale_vehicle(pg_db,fleet):
    with pg_db.sessions() as stale:
        car=stale.get(Vehicle,fleet['car'])
        with pg_db.sessions() as writer:
            writer.get(Vehicle,fleet['car']).notes='Original owner latest private note';writer.commit()
        car.notes='Uncommitted buyer replacement'
        transfer_vehicle_to_new_owner(stale,vehicle=car,new_owner=stale.get(Customer,fleet['buyer']))
        stale.commit()
        archive=stale.query(VehicleOwnershipArchive).one()
        assert json.loads(archive.profile_json)['notes']=='Original owner latest private note'
        assert car.notes is None


@pytest.mark.parametrize('operation',['profile','mileage','record','intake'])
def test_waiting_form_cannot_write_after_owner_transfer(pg_db,fleet,monkeypatch,operation):
    monkeypatch.setattr(service_records,'assert_module_ready',lambda *a,**kw:None)
    ready=Event();proceed=Event()
    def old_writer():
        with pg_db.sessions() as db:
            owner=db.get(Customer,fleet['owner']);service=db.get(Customer,fleet['service'])
            car=db.get(Vehicle,fleet['car']);ready.set();assert proceed.wait(5)
            try:
                if operation=='profile': vehicles._require_vehicle_management(car,owner,db)
                elif operation=='mileage': vehicles.record_vehicle_mileage(car.id,vehicles.VehicleMileageRecordV1(mileage_km=999),owner,db)
                elif operation=='record': service_records.create_service_record(car.id,ServiceRecordCreateV1(description='Old owner injection', performed_at=datetime(2026,1,1), category='SERVIS'),owner,db)
                else: service_intake.create_service_intake(ServiceIntakeCreateV1(vehicle_id=car.id,customer_id=owner.id),service,db)
            except HTTPException as exc:return exc.status_code
            return 200
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending=pool.submit(old_writer);assert ready.wait(5)
        with pg_db.sessions() as db:
            transfer_vehicle_to_new_owner(db,vehicle=db.get(Vehicle,fleet['car']),new_owner=db.get(Customer,fleet['buyer']))
            db.commit()
        proceed.set();assert pending.result(timeout=10)==403
    with pg_db.sessions() as db:
        assert db.query(ServiceRecord).count()==0
        assert db.query(VehicleOwnershipArchive).count()==1
        assert db.get(Vehicle,fleet['car']).current_mileage_km==200


def test_erasing_buyer_keeps_old_owner_archive_and_erasing_old_owner_keeps_buyer(pg_db,fleet,monkeypatch,tmp_path):
    from src.core import file_storage
    from src.modules.vehicle_hub.account_erasure import erase_account
    from src.modules.vehicle_hub.database import Base
    from src.modules.vehicle_hub.ownership import may_restore_vehicle_profile
    Base.metadata.create_all(pg_db.engine)
    monkeypatch.setattr(file_storage,'DATA_DIR',tmp_path)
    monkeypatch.setattr(file_storage,'_config',lambda:None)
    with pg_db.sessions() as db:
        owner=db.get(Customer,fleet['owner']);buyer=db.get(Customer,fleet['buyer']);car=db.get(Vehicle,fleet['car'])
        car.notes='First owner private profile'
        db.add(ServiceRecord(tenant_id=owner.tenant_id,vehicle_id=car.id,user_id=fleet['service'],description='First owner private repair'))
        db.commit()
        transfer_vehicle_to_new_owner(db,vehicle=car,new_owner=buyer);db.commit()
        archive_id=db.query(VehicleOwnershipArchive).one().id
        car.notes='Buyer private profile'
        db.add(ServiceRecord(tenant_id=buyer.tenant_id,vehicle_id=car.id,user_id=fleet['service'],description='Buyer private repair'))
        db.commit()
        erase_account(db,buyer);db.commit();db.expire_all()
        kept=db.get(Vehicle,fleet['car'])
        assert kept and kept.notes is None
        assert json.loads(db.get(VehicleOwnershipArchive,archive_id).profile_json)['notes']=='First owner private profile'
        assert db.query(ServiceRecord).one().description=='First owner private repair'
        assert not may_restore_vehicle_profile(db,vehicle=kept,customer=owner)
        erase_account(db,owner);db.commit();db.expire_all()
        assert db.query(ServiceRecord).count()==0
        assert db.query(VehicleOwnershipArchive).filter(VehicleOwnershipArchive.owner_customer_id.isnot(None)).count()==0
