"""Persist support cases separately from immutable access history."""
from alembic import op
revision = '20261105_0027'
down_revision = '20261105_0026'
branch_labels = None
depends_on = None

def upgrade():
    from scripts.migrate_admin_incidents import migrate_connection
    migrate_connection(op.get_bind())

def downgrade():
    raise RuntimeError('Support case history must be preserved; use a reviewed restore.')
