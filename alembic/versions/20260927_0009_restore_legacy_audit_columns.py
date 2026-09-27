"""Complete audit columns in databases restored from pre-migration backups."""
from alembic import op
import sqlalchemy as sa

revision = "20260927_0009"
down_revision = "20260927_0008"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())
    table = "service_record_audit_logs"
    columns = {column["name"] for column in inspector.get_columns(table)}
    for column in (
        sa.Column("new_snapshot_json", sa.Text(), nullable=True),
        sa.Column("snapshot_hash", sa.String(), nullable=True),
        sa.Column("change_reason", sa.Text(), nullable=True),
    ):
        if column.name not in columns:
            op.add_column(table, column)
    indexes = {index["name"] for index in inspector.get_indexes(table)}
    if "ix_service_record_audit_logs_snapshot_hash" not in indexes:
        op.create_index("ix_service_record_audit_logs_snapshot_hash", table, ["snapshot_hash"])


def downgrade():
    raise RuntimeError("A reviewed manual rollback is required; restored audit history must not be deleted.")
