"""Allow replacement invitations while preserving rejected/cancelled/expired history."""
from alembic import op
revision = '20261105_0026'
down_revision = '20261104_0025'
branch_labels = None
depends_on = None

def upgrade():
    from scripts.migrate_transfer_reinvites import migrate_connection
    migrate_connection(op.get_bind())

def downgrade():
    raise RuntimeError('Preserve invitation decisions; use a reviewed restore.')
