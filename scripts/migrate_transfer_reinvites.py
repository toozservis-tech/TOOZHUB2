"""Keep prior invitation decisions when a seller creates a replacement invitation."""
from sqlalchemy import inspect
from alembic.migration import MigrationContext
from alembic.operations import Operations


def migrate_connection(connection):
    table = 'vehicle_transfer_invitations'
    schema = inspect(connection)
    if not schema.has_table(table):
        from scripts.migrate_vehicle_transfers import migrate_connection as initial
        initial(connection)
        return
    obsolete = [c for c in schema.get_unique_constraints(table) if c['column_names'] == ['archive_id']]
    if not obsolete: return
    operations = Operations(MigrationContext.configure(connection))
    if connection.dialect.name == 'sqlite':
        with operations.batch_alter_table(table, naming_convention={'uq': 'uq_%(table_name)s_%(column_0_name)s'}) as batch:
            for constraint in obsolete:
                batch.drop_constraint(constraint['name'] or 'uq_vehicle_transfer_invitations_archive_id', type_='unique')
    else:
        for constraint in obsolete:
            operations.drop_constraint(constraint['name'], table, type_='unique')
    if not any(i['column_names'] == ['archive_id'] for i in inspect(connection).get_indexes(table)):
        operations.create_index('ix_vehicle_transfer_invitations_archive_id', table, ['archive_id'])


def migrate(bind=None):
    from sqlalchemy import text
    if bind is None:
        from src.modules.vehicle_hub.database import engine
        bind = engine
    with bind.begin() as connection:
        if connection.dialect.name == 'postgresql':
            connection.execute(text("SET LOCAL lock_timeout = '10s'"))
            connection.execute(text("SET LOCAL statement_timeout = '60s'"))
            connection.execute(text("SELECT pg_advisory_xact_lock(hashtextextended('sv:schema:vehicle-transfers', 0))"))
        migrate_connection(connection)


if __name__ == '__main__':
    migrate()
    print('Replacement transfer invitations ready; original decisions retained.')
