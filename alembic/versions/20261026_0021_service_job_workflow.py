"""Guided workshop intake and evidence phases."""
from alembic import op
revision = '20261026_0021'
down_revision = '20261025_0020'
branch_labels = None
depends_on = None

def upgrade():
    from sqlalchemy import inspect, text
    conn = op.get_bind()
    for table, name, definition in [('service_jobs', 'workflow_version', 'INTEGER NOT NULL DEFAULT 0'), ('service_job_photos', 'stage', 'VARCHAR(32)')]:
        if name not in {column['name'] for column in inspect(conn).get_columns(table)}:
            conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {definition}'))

def downgrade():
    raise RuntimeError('Workshop evidence must be retained; use a reviewed restore procedure.')
