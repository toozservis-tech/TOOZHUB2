"""Store only each customer's selected public map place identifier."""
from alembic import op
revision = '20261103_0023'
down_revision = '20261103_0022'
branch_labels = None
depends_on = None

def upgrade():
    from src.modules.vehicle_hub.apple_garages import HomeGarage
    HomeGarage.__table__.create(op.get_bind(), checkfirst=True)

def downgrade():
    raise RuntimeError('Retain customer preferences; use a reviewed restore procedure.')
