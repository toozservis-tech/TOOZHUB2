"""Service invoices: optional service_record / work_order link; vehicle_mileage.service_record_id.

Revision ID: 20260513_0038
Revises: 20260513_0037
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision = "20260513_0038"
down_revision = "20260513_0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "service_invoices" in tables:
        cols = {c["name"] for c in inspector.get_columns("service_invoices")}
        if "service_record_id" not in cols:
            op.add_column(
                "service_invoices",
                sa.Column("service_record_id", sa.Integer(), nullable=True),
            )
            op.create_index(
                "ix_service_invoices_service_record_id",
                "service_invoices",
                ["service_record_id"],
            )
            op.create_foreign_key(
                "fk_service_invoices_service_record_id",
                "service_invoices",
                "service_records",
                ["service_record_id"],
                ["id"],
            )
        if "work_order_id" not in cols:
            op.add_column(
                "service_invoices",
                sa.Column("work_order_id", sa.Integer(), nullable=True),
            )
            op.create_index(
                "ix_service_invoices_work_order_id",
                "service_invoices",
                ["work_order_id"],
            )
            op.create_foreign_key(
                "fk_service_invoices_work_order_id",
                "service_invoices",
                "service_work_orders",
                ["work_order_id"],
                ["id"],
            )

    if "vehicle_mileage" in tables:
        mcols = {c["name"] for c in inspector.get_columns("vehicle_mileage")}
        if "service_record_id" not in mcols:
            op.add_column(
                "vehicle_mileage",
                sa.Column("service_record_id", sa.Integer(), nullable=True),
            )
            op.create_index(
                "ix_vehicle_mileage_service_record_id",
                "vehicle_mileage",
                ["service_record_id"],
            )
            op.create_foreign_key(
                "fk_vehicle_mileage_service_record_id",
                "vehicle_mileage",
                "service_records",
                ["service_record_id"],
                ["id"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "vehicle_mileage" in tables:
        mcols = {c["name"] for c in inspector.get_columns("vehicle_mileage")}
        if "service_record_id" in mcols:
            op.drop_constraint("fk_vehicle_mileage_service_record_id", "vehicle_mileage", type_="foreignkey")
            op.drop_index("ix_vehicle_mileage_service_record_id", table_name="vehicle_mileage")
            op.drop_column("vehicle_mileage", "service_record_id")

    if "service_invoices" in tables:
        cols = {c["name"] for c in inspector.get_columns("service_invoices")}
        if "work_order_id" in cols:
            op.drop_constraint("fk_service_invoices_work_order_id", "service_invoices", type_="foreignkey")
            op.drop_index("ix_service_invoices_work_order_id", table_name="service_invoices")
            op.drop_column("service_invoices", "work_order_id")
        if "service_record_id" in cols:
            op.drop_constraint("fk_service_invoices_service_record_id", "service_invoices", type_="foreignkey")
            op.drop_index("ix_service_invoices_service_record_id", table_name="service_invoices")
            op.drop_column("service_invoices", "service_record_id")
