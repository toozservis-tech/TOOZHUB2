"""Recipient inbox folders and an append-only state-change history.

Purely additive. Existing read markers, event content and repair history are
untouched. An event without a folder row remains in the original inbox.
"""
from alembic import op

revision = "20261018_0017"
down_revision = "20261018_0016"
branch_labels = None
depends_on = None


def upgrade():
    from src.modules.vehicle_hub.models import Customer, Vehicle, VehicleOwnership, Tenant
    from src.modules.vehicle_hub.vehicle_update_models import (
        VehicleUpdate, VehicleUpdateInboxState, VehicleUpdateInboxAction)
    bind = op.get_bind()
    for model in (VehicleUpdateInboxState, VehicleUpdateInboxAction):
        model.__table__.create(bind, checkfirst=True)


def downgrade():
    raise RuntimeError("Inbox history must be retained; use a reviewed restore procedure.")
