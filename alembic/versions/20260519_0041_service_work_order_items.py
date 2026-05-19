"""service work order items

Revision ID: 20260519_0041
Revises: 20260516_0041
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision = "20260519_0041"
down_revision = "20260516_0041"
branch_labels = None
depends_on = None


def _create_index_if_missing(table: str, name: str, columns: list[str]) -> None:
    bind = op.get_bind()
    indexes = {idx["name"] for idx in inspect(bind).get_indexes(table)}
    if name not in indexes:
        op.create_index(name, table, columns)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())
    if "service_work_order_items" not in tables:
        op.create_table(
            "service_work_order_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenants.id"), nullable=False),
            sa.Column("work_order_id", sa.Integer(), sa.ForeignKey("service_work_orders.id"), nullable=False),
            sa.Column("service_customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=False),
            sa.Column("vehicle_id", sa.Integer(), sa.ForeignKey("vehicles.id"), nullable=True),
            sa.Column("item_type", sa.String(length=32), nullable=False),
            sa.Column("name", sa.String(length=512), nullable=False),
            sa.Column("code", sa.String(length=128), nullable=True),
            sa.Column("quantity", sa.Float(), nullable=False, server_default="1"),
            sa.Column("unit", sa.String(length=32), nullable=False, server_default="ks"),
            sa.Column("vat_rate", sa.Float(), nullable=False, server_default="21"),
            sa.Column("purchase_price_without_vat", sa.Float(), nullable=True),
            sa.Column("sale_price_without_vat", sa.Float(), nullable=False, server_default="0"),
            sa.Column("discount_percent", sa.Float(), nullable=False, server_default="0"),
            sa.Column("mechanic_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True),
            sa.Column("source", sa.String(length=32), nullable=False, server_default="manual"),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
            sa.Column("deleted_by", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        )

    _create_index_if_missing("service_work_order_items", "ix_service_work_order_items_tenant_id", ["tenant_id"])
    _create_index_if_missing("service_work_order_items", "ix_service_work_order_items_work_order_id", ["work_order_id"])
    _create_index_if_missing("service_work_order_items", "ix_service_work_order_items_service_customer_id", ["service_customer_id"])
    _create_index_if_missing("service_work_order_items", "ix_service_work_order_items_vehicle_id", ["vehicle_id"])
    _create_index_if_missing("service_work_order_items", "ix_service_work_order_items_item_type", ["item_type"])
    _create_index_if_missing("service_work_order_items", "ix_service_work_order_items_code", ["code"])
    _create_index_if_missing("service_work_order_items", "ix_service_work_order_items_mechanic_id", ["mechanic_id"])
    _create_index_if_missing("service_work_order_items", "ix_service_work_order_items_source", ["source"])
    _create_index_if_missing("service_work_order_items", "ix_service_work_order_items_created_by", ["created_by"])
    _create_index_if_missing("service_work_order_items", "ix_service_work_order_items_deleted_at", ["deleted_at"])
    _create_index_if_missing("service_work_order_items", "ix_service_work_order_items_deleted_by", ["deleted_by"])
    _create_index_if_missing("service_work_order_items", "ix_service_work_order_items_created_at", ["created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "service_work_order_items" in inspector.get_table_names():
        op.drop_table("service_work_order_items")
