"""A document is bound once even when two vehicle forms are saved concurrently."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from fastapi import HTTPException
from sqlalchemy import text

from src.modules.vehicle_hub.models import Customer, Tenant, Vehicle, VehicleORVScan
from src.modules.vehicle_hub.orv_scans import apply_orv_scan_to_vehicle


def test_one_orv_scan_cannot_be_attached_to_two_vehicles_concurrently(pg_db):
    with pg_db.sessions() as db:
        tenant = Tenant(name='Synthetic ORV binding', license_key='orv-binding-concurrency')
        db.add(tenant); db.flush()
        user = Customer(tenant_id=tenant.id,email='orv-binding@example.invalid',role='user')
        db.add(user); db.flush()
        vehicles = [Vehicle(tenant_id=tenant.id,user_email=user.email,nickname=f'Synthetic {i}') for i in range(2)]
        row = VehicleORVScan(tenant_id=tenant.id,initiated_by_customer_id=user.id,status='review',
            front_image_path='synthetic-front.jpg',back_image_path='synthetic-back.jpg')
        db.add_all(vehicles + [row]); db.commit()
        vehicle_ids = [car.id for car in vehicles]; user_id = user.id; scan_id = row.id
    barrier = Barrier(2)
    def attach(index):
        with pg_db.sessions() as db:
            user = db.get(Customer,user_id); vehicle = db.get(Vehicle,vehicle_ids[index])
            # Deliberately preload stale identity-map state to exercise populate_existing.
            cached = db.get(VehicleORVScan,scan_id)
            assert cached.vehicle_id is None
            pid = db.scalar(text('SELECT pg_backend_pid()'))
            barrier.wait(timeout=5)
            try:
                apply_orv_scan_to_vehicle(db=db,vehicle=vehicle,current_user=user,scan_id=scan_id,
                    orv_number=None,use_owner_data=False,data_trust_state='verified_by_user',create_payload={})
                db.commit(); return pid,200,vehicle.id
            except HTTPException as error:
                db.rollback(); return pid,error.status_code,vehicle.id
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attach,range(2)))
    assert len({item[0] for item in results}) == 2
    assert sorted(item[1] for item in results) == [200,409]
    winner = next(item[2] for item in results if item[1] == 200)
    with pg_db.sessions() as db:
        row = db.get(VehicleORVScan,scan_id)
        assert row.vehicle_id == winner
        attached = db.query(Vehicle).filter(Vehicle.orv_front_image_path.is_not(None)).all()
        assert [car.id for car in attached] == [winner]
