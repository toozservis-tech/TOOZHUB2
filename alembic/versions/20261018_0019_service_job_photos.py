"""Add immutable photo evidence to existing service jobs; leave all historical data untouched."""
from alembic import op
revision = "20261018_0019"
down_revision = "20261018_0018"
branch_labels = None
depends_on = None


def upgrade():
    from src.modules.vehicle_hub.service_job_models import ServiceJobPhoto
    ServiceJobPhoto.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError("Vehicle evidence photos must be retained; use a reviewed restore procedure.")
