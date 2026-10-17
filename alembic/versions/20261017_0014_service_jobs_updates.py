"""Durable workshop timelines and ownership-scoped in-app inbox.

Additive only: no existing profiles, history, permissions or records rewritten.
"""
from alembic import op
import sqlalchemy as sa

revision = '20261017_0014'
down_revision = '20261002_0013'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    # Standalone pre-deploy processes have not loaded the API router/models.
    # Register canonical FK targets BEFORE compiling any new table's DDL.
    from src.modules.vehicle_hub.models import Tenant, ServiceAccessRequest, VehicleOwnership, Vehicle, Customer
    # Explicit table set: never runtime create_all or unrelated schema changes.
    from src.modules.vehicle_hub.vehicle_update_models import VehicleUpdate, VehicleUpdateReceipt
    from src.modules.vehicle_hub.service_job_models import ServiceJob, ServiceJobEvent
    for model in (ServiceJob, ServiceJobEvent, VehicleUpdate, VehicleUpdateReceipt):
        model.__table__.create(bind, checkfirst=True)
    # Preserve outstanding decisions created by older clients. Only still-valid
    # requests for the current primary owner are backfilled; no grant is made.
    request = ServiceAccessRequest.__table__
    owner = VehicleOwnership.__table__
    vehicle = Vehicle.__table__
    service = Customer.__table__
    updates = VehicleUpdate.__table__
    if sa.inspect(bind).has_table(request.name):
        already_published = sa.exists(sa.select(updates.c.id).where(
            updates.c.source_type == request.name, updates.c.source_id == request.c.id,
            updates.c.event_type == 'access_request.created'))
        candidates = sa.select(vehicle.c.tenant_id, request.c.vehicle_id,
            request.c.owner_customer_id, owner.c.id,
            sa.func.coalesce(owner.c.owned_from, owner.c.assigned_at), request.c.service_customer_id,
            sa.literal('access_request.created'), sa.literal('Servis žádá o přístup k vozidlu'),
            sa.literal('Zkontrolujte žádost a rozhodněte o přístupu v sekci Servisy.'),
            sa.literal(request.name), request.c.id,
            sa.literal('access-request:migration:') + sa.cast(request.c.id, sa.String),
            request.c.requested_at).select_from(request.join(vehicle, vehicle.c.id == request.c.vehicle_id)
                .join(owner, sa.and_(owner.c.vehicle_id == vehicle.c.id,
                    owner.c.customer_id == request.c.owner_customer_id,
                    owner.c.is_active.is_(True), owner.c.is_primary.is_(True)))
                .join(service, service.c.id == request.c.service_customer_id)).where(
                    request.c.status == 'pending', sa.func.lower(sa.func.trim(service.c.role)) == 'service',
                    service.c.is_deleted.is_not(True), service.c.is_disabled.is_not(True), ~already_published)
        bind.execute(updates.insert().from_select(['tenant_id', 'vehicle_id', 'recipient_id', 'ownership_id',
            'ownership_started_at', 'actor_id', 'event_type', 'title', 'message', 'source_type', 'source_id',
            'dedupe_key', 'occurred_at'], candidates))


def downgrade():
    raise RuntimeError('Archived workshop progress must be retained; use a reviewed restore procedure.')
