"""Personal invitation attribution and separate additive reward ledger."""
from alembic import op
revision = '20261103_0024'
down_revision = '20261103_0023'
branch_labels = None
depends_on = None

def upgrade():
    from scripts.migrate_referrals import migrate_connection
    migrate_connection(op.get_bind())

def downgrade():
    raise RuntimeError('Preserve reward and attribution history; use a reviewed restore.')
