"""Private two-way administrator conversations and explicit receipts."""
from alembic import op
revision='20261105_0028'
down_revision='20261105_0027'
branch_labels=None
depends_on=None

def upgrade():
    from scripts.migrate_admin_messages import migrate_connection
    migrate_connection(op.get_bind())

def downgrade():
    raise RuntimeError('Message history must be preserved; use a reviewed restore.')
