"""Recipient-confirmed vehicle sale invitations."""
from alembic import op
revision = '20261104_0025'
down_revision = '20261103_0024'
branch_labels = None
depends_on = None

def upgrade():
    from scripts.migrate_vehicle_transfers import migrate_connection
    migrate_connection(op.get_bind())

def downgrade():
    raise RuntimeError('Preserve ownership decisions; use a reviewed restore.')
