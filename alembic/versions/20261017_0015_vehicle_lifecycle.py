"""Add owner-reported lifecycle events without rewriting VINs or ownership."""
from alembic import op
revision = '20261017_0015'
down_revision = '20261017_0014'
branch_labels = None
depends_on = None


def upgrade():
    from src.modules.vehicle_hub import models  # register referenced tables
    from src.modules.vehicle_hub.vehicle_lifecycle_models import VehicleLifecycleEvent
    VehicleLifecycleEvent.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError('Owner lifecycle audit must be retained; use a reviewed restore procedure.')
