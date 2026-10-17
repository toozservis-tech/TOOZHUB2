"""Pending pre-upgrade requests must remain visible without duplicating notices."""
from test_service_jobs import ctx
from src.modules.vehicle_hub.models import ServiceAccessRequest
from src.modules.vehicle_hub.vehicle_update_models import VehicleUpdate
from scripts.migrate_service_updates import migrate


def test_additive_migration_backfills_only_current_pending_requests_once(ctx):
    db, owner, service, stranger, vehicle, assignment, link = ctx
    # Simulate the old application: Core insert does not run the new ORM writer.
    db.execute(ServiceAccessRequest.__table__.insert(), [
        dict(tenant_id=vehicle.tenant_id, vehicle_id=vehicle.id,
            service_customer_id=service.id, owner_customer_id=owner.id, status='pending'),
        dict(tenant_id=vehicle.tenant_id, vehicle_id=vehicle.id,
            service_customer_id=service.id, owner_customer_id=stranger.id, status='pending'),
        dict(tenant_id=vehicle.tenant_id, vehicle_id=vehicle.id,
            service_customer_id=service.id, owner_customer_id=owner.id, status='rejected')])
    db.commit()
    assert db.query(VehicleUpdate).count() == 0
    db.commit()
    migrate(db.get_bind())
    migrate(db.get_bind())
    db.expire_all()
    rows = db.query(VehicleUpdate).all()
    assert len(rows) == 1
    assert rows[0].recipient_id == owner.id and rows[0].ownership_id == assignment.id
    assert db.query(ServiceAccessRequest).filter_by(status='pending').count() == 2
    assert link.status == 'approved'  # Migration never changes permissions.
