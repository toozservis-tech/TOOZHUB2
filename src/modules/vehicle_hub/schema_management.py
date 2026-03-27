"""
Deterministic schema checks for active modules.
No runtime create_all/ALTER TABLE in request flow.
"""
from __future__ import annotations

from typing import Dict, Iterable, List, Mapping

from fastapi import HTTPException
from sqlalchemy import inspect
from sqlalchemy.orm import Session


MODULE_REQUIREMENTS: Dict[str, Dict[str, object]] = {
    "vehicles": {
        "tables": {"vehicles", "vehicle_ownerships"},
        "columns": {"vehicles": {"photo_path", "current_mileage_km", "last_stk_mileage_km", "mileage_checked_at"}},
    },
    "service_records": {
        "tables": {"service_records", "service_record_audit_logs"},
        "columns": {"service_records": {"is_deleted", "deleted_at", "deleted_by_user_id", "deletion_reason", "snapshot_hash"}},
    },
    "reminders": {
        "tables": {"reminders"},
        "columns": {"reminders": {"notify_at", "last_notified_at", "notification_method", "is_manual", "is_completed"}},
    },
    "service_workspace": {
        "tables": {"service_customer_links", "service_customer_invites", "service_vehicle_access", "service_document_ingestions"},
    },
    "reservations": {
        "tables": {"reservations", "service_vehicle_access"},
        "columns": {"reservations": {"source_platform"}},
    },
    "subscriptions": {
        "tables": {"licenses", "license_subscriptions", "license_payment_transactions"},
        "columns": {"license_subscriptions": {"credit_balance_halers"}},
    },
    "push": {
        "tables": {"push_subscriptions"},
    },
    "system_notifications": {
        "tables": {"system_notifications"},
    },
    "security": {
        "tables": {"customer_security_settings", "security_access_logs", "security_blocked_ips"},
    },
    "admin_audit": {
        "tables": {"developer_action_audit_logs"},
    },
}


def _table_names(db: Session) -> set[str]:
    inspector = inspect(db.bind)
    return set(inspector.get_table_names())


def _column_names(db: Session, table_name: str) -> set[str]:
    inspector = inspect(db.bind)
    return {str(col.get("name")) for col in inspector.get_columns(table_name) if col.get("name")}


def module_schema_report(db: Session, module_name: str) -> dict:
    requirements = MODULE_REQUIREMENTS.get(module_name, {})
    required_tables = set(requirements.get("tables") or set())
    required_columns: Mapping[str, Iterable[str]] = requirements.get("columns") or {}

    tables = _table_names(db)
    missing_tables = sorted(table for table in required_tables if table not in tables)
    missing_columns: List[str] = []

    for table_name, columns in required_columns.items():
        if table_name not in tables:
            for column in columns:
                missing_columns.append(f"{table_name}.{column}")
            continue
        existing_columns = _column_names(db, table_name)
        for column in columns:
            if column not in existing_columns:
                missing_columns.append(f"{table_name}.{column}")

    available = not missing_tables and not missing_columns
    return {
        "module": module_name,
        "available": available,
        "missing_tables": missing_tables,
        "missing_columns": sorted(missing_columns),
    }


def assert_module_ready(db: Session, module_name: str, *, detail_prefix: str) -> None:
    report = module_schema_report(db, module_name)
    if report["available"]:
        return
    problems = []
    if report["missing_tables"]:
        problems.append("tabulky: " + ", ".join(report["missing_tables"]))
    if report["missing_columns"]:
        problems.append("sloupce: " + ", ".join(report["missing_columns"]))
    raise HTTPException(
        status_code=503,
        detail=f"{detail_prefix}. Chybí { '; '.join(problems) }. Spusťte migrace.",
    )


def get_capabilities(db: Session) -> dict:
    modules = {
        name: module_schema_report(db, name)
        for name in sorted(MODULE_REQUIREMENTS.keys())
    }
    return {
        "modules": modules,
    }
