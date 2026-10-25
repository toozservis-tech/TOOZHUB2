"""Retain workshop work before customer consent."""
from alembic import op
revision = '20261025_0020'
down_revision = '20261018_0019'
branch_labels = None
depends_on = None


def upgrade():
    from sqlalchemy import inspect, text
    from src.modules.vehicle_hub.service_job_models import ServiceJobDocument
    conn = op.get_bind()
    columns = {c['name'] for c in inspect(conn).get_columns('service_jobs')}
    for name, kind in [('access_request_id', 'INTEGER REFERENCES service_access_requests(id)'),
                       ('consent_published_at', 'TIMESTAMP'), ('completion_price', 'FLOAT')]:
        if name not in columns:
            conn.execute(text(f'ALTER TABLE service_jobs ADD COLUMN {name} {kind}'))
    conn.execute(text('CREATE INDEX IF NOT EXISTS ix_service_jobs_access_request_id ON service_jobs (access_request_id)'))
    ServiceJobDocument.__table__.create(conn, checkfirst=True)


def downgrade():
    raise RuntimeError('Workshop evidence must be retained; use a reviewed restore procedure.')
