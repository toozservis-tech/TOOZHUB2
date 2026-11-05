"""Targeted service events and explicitly addressed administrator replies."""
from alembic import op
revision='20261105_0030'
down_revision='20261105_0029'
branch_labels=None
depends_on=None

def upgrade():
    from scripts.migrate_reverse_notifications import migrate_connection
    migrate_connection(op.get_bind())

def downgrade():
    raise RuntimeError('Retain schema and history. Stop dispatch and apply a forward compatibility fix.')
