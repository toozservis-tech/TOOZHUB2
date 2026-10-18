"""Add immutable Google Play purchase bindings and reconciliation queue."""
from alembic import op
revision = "20261018_0018"
down_revision = "20261018_0017"
branch_labels = None
depends_on = None


def upgrade():
    from scripts.migrate_google_billing import migrate_connection
    migrate_connection(op.get_bind())


def downgrade():
    raise RuntimeError("Purchase ownership must be retained; use a reviewed restore procedure.")
