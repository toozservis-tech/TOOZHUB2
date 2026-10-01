"""Distinguish customer-approved contact links from legacy automatic links."""
from alembic import op
from src.modules.vehicle_hub.service_contact_consent import migrate_contact_consent

revision = '20261001_0012'
down_revision = '20261001_0011'
branch_labels = None
depends_on = None


def upgrade():
    migrate_contact_consent(op.get_bind())


def downgrade():
    raise RuntimeError('Consent evidence requires a reviewed, non-destructive rollback.')
