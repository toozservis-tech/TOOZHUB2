"""Additive migration; preserves all existing jobs as legacy workflows."""
from sqlalchemy import inspect, text
from src.modules.vehicle_hub.database import engine

def migrate(bind=None):
    with (bind or engine).begin() as conn:
        for table, name, definition in [('service_jobs', 'workflow_version', 'INTEGER NOT NULL DEFAULT 0'), ('service_job_photos', 'stage', 'VARCHAR(32)')]:
            if name not in {column['name'] for column in inspect(conn).get_columns(table)}:
                conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {definition}'))

if __name__ == '__main__':
    migrate()
    print('Guided service workflow schema ready.')
