"""Allow private work before an invited customer has registered; retain all rows."""
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect, text
from src.modules.vehicle_hub.database import engine


def upgrade_connection(conn):
    columns = {c['name']: c for c in inspect(conn).get_columns('service_jobs')}
    changes = [name for name in ('owner_id', 'ownership_id', 'ownership_started_at')
               if not columns[name]['nullable']]
    if changes:
        op = Operations(MigrationContext.configure(conn))
        with op.batch_alter_table('service_jobs') as batch:
            for name in changes:
                batch.alter_column(name, existing_type=columns[name]['type'], nullable=True)


def migrate(bind=None):
    with (bind or engine).connect() as conn:
        sqlite = conn.dialect.name == 'sqlite'
        foreign_keys = conn.exec_driver_sql('PRAGMA foreign_keys').scalar() if sqlite else None
        conn.commit()
        try:
            if sqlite:
                conn.exec_driver_sql('PRAGMA foreign_keys=OFF')
                conn.commit()
            with conn.begin():
                if sqlite:
                    conn.exec_driver_sql('BEGIN IMMEDIATE')
                    if conn.exec_driver_sql('PRAGMA foreign_key_check').first():
                        raise RuntimeError('Migration refused: existing invalid foreign key relationship.')
                upgrade_connection(conn)
                if sqlite and conn.exec_driver_sql('PRAGMA foreign_key_check').first():
                    raise RuntimeError('Migration refused: invalid foreign key relationship.')
        finally:
            if sqlite:
                conn.rollback()
                conn.exec_driver_sql(f'PRAGMA foreign_keys={1 if foreign_keys else 0}')
                conn.commit()


if __name__ == '__main__':
    migrate()
    print('Private work before registration ready; existing history retained.')
