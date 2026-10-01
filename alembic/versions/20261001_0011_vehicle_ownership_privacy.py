"""Preserve private originals separately from subsequent vehicle owners."""
from alembic import op
from src.modules.vehicle_hub.models import (
    VehicleOwnershipArchive, VehicleRecordPrivacy, VehicleRepairPrivacy, VehicleAttachmentPrivacy,
)
revision = '20261001_0011'
down_revision = '20260927_0010'
branch_labels = None
depends_on = None


def upgrade():
    for model in (VehicleOwnershipArchive, VehicleRecordPrivacy, VehicleRepairPrivacy, VehicleAttachmentPrivacy):
        model.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError('Private ownership archives require a reviewed, non-destructive rollback.')
