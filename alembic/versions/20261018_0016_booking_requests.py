"""Add service enquiries; do not rewrite existing reservations."""
from alembic import op
revision = '20261018_0016'
down_revision = '20261017_0015'
branch_labels = None
depends_on = None


def upgrade():
    from src.modules.vehicle_hub import models
    from src.modules.vehicle_hub.booking_request_models import BookingRequest, BookingRequestEvent
    BookingRequest.__table__.create(op.get_bind(), checkfirst=True)
    BookingRequestEvent.__table__.create(op.get_bind(), checkfirst=True)


def downgrade():
    raise RuntimeError('Retain booking history; use a reviewed restore procedure.')
