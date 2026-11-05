"""durable private notification receipts, encrypted devices and push outbox"""
from alembic import op
revision='20261105_0029'
down_revision='20261105_0028'
branch_labels=None
depends_on=None

def upgrade():
    from scripts.migrate_notification_delivery import migrate_connection
    migrate_connection(op.get_bind())

def downgrade():
    raise RuntimeError('Notification history is retained. Roll back application code without deleting delivery history.')
