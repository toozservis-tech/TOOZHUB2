"""service work order csv imports

Revision ID: 20260520_0042
Revises: 20260519_0041
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision = "20260520_0042"
down_revision = "20260519_0041"
branch_labels = None
depends_on = None


def _create_index_if_missing(table: str, name: str, columns: list[str]) -> None:
    bind = op.get_bind()
    indexes = {idx["name"] for idx in inspect(bind).get_indexes(table)}
    if name not in indexes:
        op.create_index(name, table, columns)


def _column_names(table: str) -> set[str]:
    return {col["name"] for col in inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "service_work_order_items" in tables and "note" not in _column_names("service_work_order_items"):
        op.add_column("service_work_order_items", sa.Column("note", sa.Text(), nullable=True))

    if "service_work_order_csv_imports" not in tables:
        op.create_table(
            "service_work_order_csv_imports",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("service_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
            sa.Column("work_order_id", sa.Integer(), sa.ForeignKey("service_work_orders.id"), nullable=False),
            sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id"), nullable=True),
            sa.Column("filename", sa.String(length=255), nullable=True),
            sa.Column("delimiter", sa.String(length=8), nullable=False),
            sa.Column("rows_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("imported_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("duplicate_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error_rows_json", sa.Text(), nullable=True),
            sa.Column("mapping_json", sa.Text(), nullable=True),
            sa.Column("file_sha256", sa.String(length=64), nullable=False),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )

    _create_index_if_missing("service_work_order_csv_imports", "ix_service_work_order_csv_imports_tenant_id", ["tenant_id"])
    _create_index_if_missing("service_work_order_csv_imports", "ix_service_work_order_csv_imports_service_id", ["service_id"])
    _create_index_if_missing("service_work_order_csv_imports", "ix_service_work_order_csv_imports_work_order_id", ["work_order_id"])
    _create_index_if_missing("service_work_order_csv_imports", "ix_service_work_order_csv_imports_vehicle_id", ["vehicle_id"])
    _create_index_if_missing("service_work_order_csv_imports", "ix_service_work_order_csv_imports_file_sha256", ["file_sha256"])
    _create_index_if_missing("service_work_order_csv_imports", "ix_service_work_order_csv_imports_created_by", ["created_by"])
    _create_index_if_missing("service_work_order_csv_imports", "ix_service_work_order_csv_imports_created_at", ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "service_work_order_csv_imports" in inspector.get_table_names():
        op.drop_table("service_work_order_csv_imports")
