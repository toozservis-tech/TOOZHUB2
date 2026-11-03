"""Private workshop jobs may precede registration of their future owner."""
from alembic import op

revision = '20261103_0022'
down_revision = '20261026_0021'
branch_labels = None
depends_on = None


def upgrade():
    from scripts.migrate_service_job_preregistration import upgrade_connection
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        # SQLite requires FK checks disabled outside the batch rebuild transaction.
        with op.get_context().autocommit_block():
            was_enabled = bind.exec_driver_sql("PRAGMA foreign_keys").scalar()
            bind.exec_driver_sql("PRAGMA foreign_keys=OFF")
            try:
                bind.exec_driver_sql("BEGIN IMMEDIATE")
                try:
                    if bind.exec_driver_sql("PRAGMA foreign_key_check").first():
                        raise RuntimeError("Migration refused: existing invalid foreign key relationship.")
                    upgrade_connection(bind)
                    if bind.exec_driver_sql("PRAGMA foreign_key_check").first():
                        raise RuntimeError("Migration refused: invalid foreign key relationship.")
                    bind.exec_driver_sql("COMMIT")
                except BaseException:
                    bind.exec_driver_sql("ROLLBACK")
                    raise
            finally:
                bind.exec_driver_sql(f"PRAGMA foreign_keys={1 if was_enabled else 0}")
    else:
        upgrade_connection(bind)


def downgrade():
    raise RuntimeError('Keep private workshop evidence; use a reviewed restore procedure.')
