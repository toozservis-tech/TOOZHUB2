"""Additive pre-deploy migration. Existing jobs remain published and unchanged."""
from sqlalchemy import inspect, text
from src.modules.vehicle_hub.database import engine
from src.modules.vehicle_hub.service_job_models import ServiceJobDocument


def migrate(bind=None):
    with (bind or engine).begin() as conn:
        columns = {c['name'] for c in inspect(conn).get_columns('service_jobs')}
        for name, kind in [('access_request_id', 'INTEGER REFERENCES service_access_requests(id)'),
                           ('consent_published_at', 'TIMESTAMP'), ('completion_price', 'FLOAT')]:
            if name not in columns:
                conn.execute(text(f'ALTER TABLE service_jobs ADD COLUMN {name} {kind}'))
        conn.execute(text('CREATE INDEX IF NOT EXISTS ix_service_jobs_access_request_id ON service_jobs (access_request_id)'))
        ServiceJobDocument.__table__.create(conn, checkfirst=True)


if __name__ == '__main__':
    migrate()
    print('Private workshop consent schema ready; existing history retained.')
