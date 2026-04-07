"""
Admin API router pro Správa vozidel
Přístupné pouze pro developer_admin/admin role
"""
from fastapi import APIRouter, Depends, HTTPException, Request as FastAPIRequest
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import text, inspect, func
from typing import List, Optional, Dict, Any
from datetime import datetime, date, timezone, timedelta
from pydantic import BaseModel, EmailStr
from pathlib import Path
from copy import deepcopy
import os
import json
import sqlite3
import shutil
import zipfile
import ipaddress
import secrets
import string

from src.core.auth import get_current_user_email, security
from src.core.rbac import is_admin, is_developer_admin
from src.core.security import hash_password
from src.core.config import (
    DATA_DIR,
    ENVIRONMENT,
    HOST,
    PORT,
    JWT_EXPIRE_MINUTES,
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_FROM,
    ALLOWED_ORIGINS,
)
from src.modules.vehicle_hub.database import get_db, DB_URL, engine
from src.modules.vehicle_hub.models import (
    Customer,
    Vehicle,
    VehicleOwnership,
    ServiceRecord,
    Reservation,
    Reminder,
    ServiceRegistrationRequest,
    License,
    LicenseSubscription,
    LicensePaymentTransaction,
    EmailNotificationLog,
    SecurityAccessLog,
    PushSubscription,
    DeveloperActionAuditLog,
    SecurityBlockedIp,
    SystemNotification,
)
from src.modules.vehicle_hub.account_state import (
    ensure_customer_account_state_schema,
    customer_is_deleted,
    customer_is_disabled,
    customer_session_version,
    increment_customer_session_version,
)
from src.modules.vehicle_hub.ownership import (
    ensure_vehicle_owner_assignment,
    get_primary_vehicle_owner,
)
from src.modules.vehicle_hub.tenant_provisioning import (
    create_dedicated_tenant,
    ensure_default_license_for_tenant,
)
from src.modules.vehicle_hub.routers_v1.reminders import apply_reminder_completion_update
from src.server.runtime_settings import ADMIN_SETTINGS_FILE
from src.server.control_center_jobs import (
    is_job_paused,
    set_job_paused,
    get_job_pause_metadata,
)
try:
    from src.modules.licensing.service import (
        upgrade_license_plan,
        get_license_status as get_tenant_license_status,
    )
    LICENSE_MANAGEMENT_AVAILABLE = True
except Exception:
    upgrade_license_plan = None
    get_tenant_license_status = None
    LICENSE_MANAGEMENT_AVAILABLE = False

router = APIRouter(prefix="/admin-api", tags=["admin"])
ADMIN_ROLES = {"developer_admin", "admin"}
EDITABLE_ROLES = {"user", "service", "admin", "developer_admin"}
ONLINE_WINDOW_SECONDS = max(30, int(os.getenv("ADMIN_USER_ONLINE_WINDOW_SEC", "300")))
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONTROL_CENTER_BACKUP_DIR = PROJECT_ROOT / "backups" / "control_center"
CONTROL_CENTER_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
CONTROL_CENTER_LOG_DIR = PROJECT_ROOT / "logs"
CONTROL_CENTER_DANGEROUS_CONFIRM = "PROCEED_RESTORE"
CONTROL_CENTER_CLEANUP_CONFIRM = "PROCEED_CLEANUP"
JOB_NAME_ALIASES = {
    "license.subscription.cycle": "license.subscription.cycle",
    "payments.resync": "license.subscription.cycle",
    "reminders.notification.check": "reminders.notification.check",
    "reminders.check": "reminders.notification.check",
}

# Import pro admin tenants endpoints
try:
    from src.modules.vehicle_hub.models import Tenant, Instance
    TENANTS_AVAILABLE = True
except ImportError:
    TENANTS_AVAILABLE = False
    Tenant = None
    Instance = None

try:
    from src.modules.ai_features.models import UsageAnalytics
    USAGE_ANALYTICS_AVAILABLE = True
except ImportError:
    UsageAnalytics = None
    USAGE_ANALYTICS_AVAILABLE = False


def get_db_file_path() -> Optional[Path]:
    raw = str(DB_URL or "")
    if raw.startswith("sqlite:///"):
        return Path(raw.replace("sqlite:///", ""))
    return None


def _primary_owner_join_sql(
    *,
    vehicle_alias: str = "v",
    selector_alias: str = "vo_primary",
    ownership_alias: str = "vo",
    owner_alias: str = "owner_customer",
) -> str:
    return f"""
        LEFT JOIN (
            SELECT vehicle_id, MIN(id) AS ownership_id
            FROM vehicle_ownerships
            WHERE is_active = 1 AND is_primary = 1
            GROUP BY vehicle_id
        ) {selector_alias} ON {selector_alias}.vehicle_id = {vehicle_alias}.id
        LEFT JOIN vehicle_ownerships {ownership_alias} ON {ownership_alias}.id = {selector_alias}.ownership_id
        LEFT JOIN customers {owner_alias} ON {owner_alias}.id = {ownership_alias}.customer_id
    """


def _customer_vehicle_count_join_sql(*, customer_alias: str = "c", join_alias: str = "vehicle_counts") -> str:
    return f"""
        LEFT JOIN (
            SELECT customer_id, COUNT(DISTINCT vehicle_id) AS vehicles_count
            FROM vehicle_ownerships
            WHERE is_active = 1
            GROUP BY customer_id
        ) {join_alias} ON {join_alias}.customer_id = {customer_alias}.id
    """


def _vehicle_ids_owned_by_customer(db: Session, customer_id: int) -> List[int]:
    rows = (
        db.query(VehicleOwnership.vehicle_id)
        .filter(
            VehicleOwnership.customer_id == customer_id,
            VehicleOwnership.is_active.is_(True),
        )
        .all()
    )
    return [int(vehicle_id) for (vehicle_id,) in rows if vehicle_id is not None]


def _sync_vehicle_user_email_display_for_customer(db: Session, customer_id: int, display_email: str) -> int:
    """
    Deprecated compatibility sync for UI fields.
    Ownership logic must use vehicle_ownerships, not Vehicle.user_email.
    """
    vehicle_ids = _vehicle_ids_owned_by_customer(db, customer_id)
    if not vehicle_ids:
        return 0
    return (
        db.query(Vehicle)
        .filter(Vehicle.id.in_(vehicle_ids))
        .update({Vehicle.user_email: display_email}, synchronize_session=False)
    )


def _reassign_vehicle_primary_owner(
    db: Session,
    *,
    vehicle: Vehicle,
    owner: Customer,
    assigned_by_customer_id: Optional[int],
) -> None:
    now = datetime.utcnow()
    (
        db.query(VehicleOwnership)
        .filter(
            VehicleOwnership.vehicle_id == vehicle.id,
            VehicleOwnership.is_active.is_(True),
            VehicleOwnership.is_primary.is_(True),
            VehicleOwnership.customer_id != owner.id,
        )
        .update(
            {
                VehicleOwnership.is_active: False,
                VehicleOwnership.is_primary: False,
                VehicleOwnership.revoked_at: now,
                VehicleOwnership.updated_at: now,
            },
            synchronize_session=False,
        )
    )
    ensure_vehicle_owner_assignment(
        db,
        vehicle=vehicle,
        owner=owner,
        assigned_by_customer_id=assigned_by_customer_id,
    )
    vehicle.tenant_id = owner.tenant_id
    vehicle.user_email = owner.email


def _json_serialize_for_audit(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        return json.dumps({"raw": str(value)}, ensure_ascii=False)


def log_developer_action(
    db: Session,
    *,
    developer_email: str,
    request: Optional[FastAPIRequest],
    action_type: str,
    target_resource: str,
    parameters: Optional[Dict[str, Any]] = None,
    result: str = "success",
    status_code: Optional[int] = None,
) -> None:
    """
    Zápis immutable audit logu vývojářských akcí.
    Nikdy nevyhazuje výjimku ven.
    """
    try:
        actor = get_customer_by_email(db, developer_email)
        if not actor:
            return
        entry = DeveloperActionAuditLog(
            developer_id=actor.id,
            developer_email=(developer_email or "").strip().lower() or None,
            action_type=action_type,
            target_resource=target_resource,
            parameters_json=_json_serialize_for_audit(parameters or {}),
            result=result,
            status_code=status_code,
            request_ip=get_client_ip(request) if request else None,
            created_at=datetime.utcnow(),
        )
        db.add(entry)
        db.commit()
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        print(f"[ADMIN_AUDIT] Failed to persist audit action '{action_type}': {exc}")


def _safe_json_load(value: Any) -> Dict[str, Any]:
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


PAYMENT_SUCCESS_PROVIDER_STATUSES = {"PAID", "CONFIRMED"}
PAYMENT_SUCCESS_EVENT_TYPES = {
    "payment_paid",
    "payment_confirmed",
    "subscription_renewal_paid",
    "paid_confirmed",
    "renewal_paid",
}
PAYMENT_FAILURE_MARKERS = ("fail", "error", "declin", "cancel", "denied", "timeout")
COUNT_TEST_PAYMENTS_AS_PAID = ENVIRONMENT != "production"


def _coerce_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    normalized = str(value or "").strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return None


def _extract_payment_test_flag(payload: Dict[str, Any]) -> Optional[bool]:
    if not payload:
        return None

    stack: List[tuple[Dict[str, Any], int]] = [(payload, 0)]
    while stack:
        current, depth = stack.pop()
        for raw_key, raw_value in current.items():
            key = str(raw_key or "").strip().lower()
            if key in {"test", "is_test", "test_mode", "sandbox", "sandbox_mode"}:
                coerced = _coerce_bool(raw_value)
                if coerced is not None:
                    return coerced
            if key in {"environment", "env", "mode"}:
                normalized = str(raw_value or "").strip().lower()
                if any(marker in normalized for marker in ("test", "sandbox")):
                    return True
                if any(marker in normalized for marker in ("live", "prod", "production")):
                    return False
            if depth < 2 and isinstance(raw_value, dict):
                stack.append((raw_value, depth + 1))
    return None


def _infer_payment_environment(
    *,
    payload_json: Any,
    provider_status: Any,
    event_type: Any,
) -> str:
    payload = _safe_json_load(payload_json)
    test_flag = _extract_payment_test_flag(payload)
    if test_flag is not None:
        return "TEST" if test_flag else "LIVE"

    combined = " ".join(
        [
            str(provider_status or "").strip().lower(),
            str(event_type or "").strip().lower(),
        ]
    )
    if "test" in combined or "sandbox" in combined:
        return "TEST"
    return "LIVE"


def _is_payment_successful(provider_status: Any, event_type: Any) -> bool:
    status = str(provider_status or "").strip().upper()
    event = str(event_type or "").strip().lower()
    return status in PAYMENT_SUCCESS_PROVIDER_STATUSES or event in PAYMENT_SUCCESS_EVENT_TYPES


def _is_payment_failed(provider_status: Any, event_type: Any) -> bool:
    status = str(provider_status or "").strip().lower()
    event = str(event_type or "").strip().lower()
    return any(marker in status for marker in PAYMENT_FAILURE_MARKERS) or any(
        marker in event for marker in PAYMENT_FAILURE_MARKERS
    )


def _payment_refund_status(provider_status: Any, event_type: Any) -> str:
    status = str(provider_status or "").strip().lower()
    event = str(event_type or "").strip().lower()
    return "refunded" if ("refund" in status or "refund" in event) else "none"


def _payment_needs_attention(provider_status: Any, event_type: Any) -> bool:
    status = str(provider_status or "").strip().lower()
    if _payment_refund_status(provider_status, event_type) == "refunded":
        return True
    return _is_payment_failed(provider_status, event_type) or "pending" in status or "created" in status


def _payment_counts_as_paid(*, environment: str, is_successful: bool) -> bool:
    if not is_successful:
        return False
    return environment == "LIVE" or COUNT_TEST_PAYMENTS_AS_PAID


def _collect_paid_state_by_tenant(db: Session, tenant_ids: List[int]) -> Dict[int, Dict[str, Any]]:
    normalized_tenant_ids = [int(tid) for tid in tenant_ids if tid is not None]
    if not normalized_tenant_ids:
        return {}

    state: Dict[int, Dict[str, Any]] = {
        tenant_id: {
            "has_paid": False,
            "last_paid_at": None,
            "live_paid_count": 0,
            "test_paid_count": 0,
        }
        for tenant_id in normalized_tenant_ids
    }

    rows = (
        db.query(
            LicensePaymentTransaction.tenant_id,
            LicensePaymentTransaction.provider_status,
            LicensePaymentTransaction.event_type,
            LicensePaymentTransaction.payload_json,
            LicensePaymentTransaction.created_at,
        )
        .filter(LicensePaymentTransaction.tenant_id.in_(normalized_tenant_ids))
        .order_by(LicensePaymentTransaction.created_at.desc(), LicensePaymentTransaction.id.desc())
        .all()
    )

    for tenant_id, provider_status, event_type, payload_json, created_at in rows:
        if tenant_id not in state:
            continue
        environment = _infer_payment_environment(
            payload_json=payload_json,
            provider_status=provider_status,
            event_type=event_type,
        )
        is_successful = _is_payment_successful(provider_status, event_type)
        if is_successful:
            if environment == "LIVE":
                state[tenant_id]["live_paid_count"] += 1
            else:
                state[tenant_id]["test_paid_count"] += 1
        if _payment_counts_as_paid(environment=environment, is_successful=is_successful):
            state[tenant_id]["has_paid"] = True
            if state[tenant_id]["last_paid_at"] is None and created_at is not None:
                state[tenant_id]["last_paid_at"] = created_at

    return state


def _format_bytes(value: int) -> str:
    size = float(max(0, value))
    units = ["B", "KB", "MB", "GB", "TB"]
    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _directory_usage(path: Path) -> Dict[str, Any]:
    total_bytes = 0
    file_count = 0
    if path.exists():
        for item in path.rglob("*"):
            if item.is_file():
                file_count += 1
                try:
                    total_bytes += item.stat().st_size
                except OSError:
                    continue
    return {
        "path": str(path),
        "exists": path.exists(),
        "file_count": file_count,
        "total_bytes": total_bytes,
        "total_human": _format_bytes(total_bytes),
    }


def _list_backup_entries() -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for backup_dir in sorted(CONTROL_CENTER_BACKUP_DIR.glob("*"), reverse=True):
        if not backup_dir.is_dir():
            continue
        manifest_path = backup_dir / "manifest.json"
        if manifest_path.exists():
            try:
                manifest = _safe_json_load(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                manifest = {}
        else:
            manifest = {}
        db_file = backup_dir / "vehicles.db"
        entries.append(
            {
                "backup_id": backup_dir.name,
                "created_at": manifest.get("created_at"),
                "created_by": manifest.get("created_by"),
                "db_exists": db_file.exists(),
                "db_size_bytes": db_file.stat().st_size if db_file.exists() else 0,
                "db_size_human": _format_bytes(db_file.stat().st_size if db_file.exists() else 0),
                "include_data_dir": bool(manifest.get("include_data_dir", False)),
                "manifest": manifest,
            }
        )
    return entries


def _create_sqlite_backup(source_db: Path, target_db: Path) -> None:
    target_db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(f"file:{source_db}?mode=ro", uri=True) as src_conn:
        with sqlite3.connect(str(target_db)) as dst_conn:
            src_conn.backup(dst_conn)


def _restore_sqlite_backup(source_db: Path, target_db: Path) -> None:
    engine.dispose()
    with sqlite3.connect(f"file:{source_db}?mode=ro", uri=True) as src_conn:
        with sqlite3.connect(str(target_db)) as dst_conn:
            src_conn.backup(dst_conn)


def _tail_file_lines(path: Path, limit: int = 120) -> List[str]:
    if not path.exists() or not path.is_file():
        return []
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as handle:
            lines = handle.readlines()
        return [line.rstrip("\n") for line in lines[-max(1, limit):]]
    except Exception:
        return []


def _collect_old_log_files(days: int) -> List[Path]:
    cutoff = datetime.utcnow() - timedelta(days=max(1, days))
    candidates: List[Path] = []
    if not CONTROL_CENTER_LOG_DIR.exists():
        return candidates
    for file_path in CONTROL_CENTER_LOG_DIR.glob("*"):
        if not file_path.is_file():
            continue
        try:
            mtime = datetime.utcfromtimestamp(file_path.stat().st_mtime)
        except OSError:
            continue
        if mtime < cutoff:
            candidates.append(file_path)
    return sorted(candidates, key=lambda item: item.stat().st_mtime if item.exists() else 0)


def _collect_old_backup_dirs(days: int) -> List[Path]:
    cutoff = datetime.utcnow() - timedelta(days=max(1, days))
    candidates: List[Path] = []
    if not CONTROL_CENTER_BACKUP_DIR.exists():
        return candidates
    for backup_dir in CONTROL_CENTER_BACKUP_DIR.iterdir():
        if not backup_dir.is_dir():
            continue
        try:
            mtime = datetime.utcfromtimestamp(backup_dir.stat().st_mtime)
        except OSError:
            continue
        if mtime < cutoff:
            candidates.append(backup_dir)
    return sorted(candidates, key=lambda item: item.stat().st_mtime if item.exists() else 0)


def _common_table_columns(conn: sqlite3.Connection, table_name: str) -> List[str]:
    main_cols = [row[1] for row in conn.execute(f"PRAGMA main.table_info({table_name})").fetchall()]
    backup_cols = {row[1] for row in conn.execute(f"PRAGMA backupdb.table_info({table_name})").fetchall()}
    return [col for col in main_cols if col in backup_cols]


def _upsert_rows_from_backup(
    conn: sqlite3.Connection,
    *,
    table_name: str,
    where_sql: str,
    params: tuple[Any, ...],
) -> int:
    columns = _common_table_columns(conn, table_name)
    if not columns:
        return 0

    col_csv = ", ".join(columns)
    rows = conn.execute(
        f"SELECT {col_csv} FROM backupdb.{table_name} WHERE {where_sql}",
        params,
    ).fetchall()
    if not rows:
        return 0

    placeholders = ", ".join(["?"] * len(columns))
    updatable_columns = [col for col in columns if col != "id"]
    if updatable_columns:
        update_sql = ", ".join([f"{col}=excluded.{col}" for col in updatable_columns])
        sql = (
            f"INSERT INTO {table_name} ({col_csv}) VALUES ({placeholders}) "
            f"ON CONFLICT(id) DO UPDATE SET {update_sql}"
        )
    else:
        sql = f"INSERT OR IGNORE INTO {table_name} ({col_csv}) VALUES ({placeholders})"

    conn.executemany(sql, rows)
    return len(rows)


def _attached_sqlite_has_table(conn: sqlite3.Connection, schema_name: str, table_name: str) -> bool:
    row = conn.execute(
        f"SELECT name FROM {schema_name}.sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _legacy_backup_vehicle_ids_by_email(conn: sqlite3.Connection, *, owner_email: str) -> List[int]:
    normalized_email = str(owner_email or "").strip().lower()
    if not normalized_email:
        return []
    vehicle_rows = conn.execute(
        "SELECT id FROM backupdb.vehicles WHERE lower(user_email) = lower(?)",
        (normalized_email,),
    ).fetchall()
    return [int(row["id"]) for row in vehicle_rows if row["id"] is not None]


def _backup_vehicle_ids_for_customer_scope(
    conn: sqlite3.Connection,
    *,
    customer_id: int,
    owner_email: str,
) -> List[int]:
    """
    Ownership-first restore helper.

    Primárně používá explicitní vehicle_ownerships ze snapshotu. Pokud jsou
    ownership tabulky v záloze chybějící nebo prázdné, použije legacy emailový
    bridge jen jako compat fallback pro staré / napůl migrované snapshoty.
    """
    if _attached_sqlite_has_table(conn, "backupdb", "vehicle_ownerships"):
        ownership_rows = conn.execute(
            """
            SELECT DISTINCT vehicle_id
            FROM backupdb.vehicle_ownerships
            WHERE customer_id = ?
              AND COALESCE(is_active, 1) = 1
            """,
            (customer_id,),
        ).fetchall()
        vehicle_ids = [int(row["vehicle_id"]) for row in ownership_rows if row["vehicle_id"] is not None]
        if vehicle_ids:
            return vehicle_ids
    return _legacy_backup_vehicle_ids_by_email(conn, owner_email=owner_email)


def _backup_owner_ids_for_vehicle_scope(
    conn: sqlite3.Connection,
    *,
    vehicle_id: int,
    owner_email: str,
) -> List[int]:
    """
    Ownership-first restore helper for vehicle scope.

    Pokud snapshot obsahuje ownership rows, bere je jako autoritu. Legacy email
    bridge použije jen jako fallback pro staré snapshoty nebo snapshoty bez
    backfillnutých ownership vazeb.
    """
    if _attached_sqlite_has_table(conn, "backupdb", "vehicle_ownerships"):
        owner_rows = conn.execute(
            """
            SELECT DISTINCT customer_id
            FROM backupdb.vehicle_ownerships
            WHERE vehicle_id = ?
            """,
            (vehicle_id,),
        ).fetchall()
        owner_ids = [int(row["customer_id"]) for row in owner_rows if row["customer_id"] is not None]
        if owner_ids:
            return owner_ids

    normalized_email = str(owner_email or "").strip().lower()
    if not normalized_email:
        return []
    customer_rows = conn.execute(
        "SELECT id FROM backupdb.customers WHERE lower(email) = lower(?)",
        (normalized_email,),
    ).fetchall()
    return [int(row["id"]) for row in customer_rows if row["id"] is not None]


def _restore_user_scope_from_backup(
    *,
    backup_db_file: Path,
    target_db_file: Path,
    user_id: int,
) -> Dict[str, int]:
    restored: Dict[str, int] = {}
    with sqlite3.connect(str(target_db_file)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("ATTACH DATABASE ? AS backupdb", (str(backup_db_file),))
        try:
            user_row = conn.execute(
                "SELECT id, email FROM backupdb.customers WHERE id = ?",
                (user_id,),
            ).fetchone()
            if not user_row:
                raise ValueError(f"Uživatel {user_id} v záloze neexistuje")

            user_email = str(user_row["email"] or "").strip().lower()
            restored["customers"] = _upsert_rows_from_backup(
                conn,
                table_name="customers",
                where_sql="id = ?",
                params=(user_id,),
            )

            vehicle_ids: List[int] = []
            if _attached_sqlite_has_table(conn, "backupdb", "vehicle_ownerships"):
                vehicle_ids = _backup_vehicle_ids_for_customer_scope(
                    conn,
                    customer_id=user_id,
                    owner_email=user_email,
                )
                restored["vehicle_ownerships"] = _upsert_rows_from_backup(
                    conn,
                    table_name="vehicle_ownerships",
                    where_sql="customer_id = ?",
                    params=(user_id,),
                )
            else:
                # Deprecated fallback for snapshots from legacy user_email ownership era.
                vehicle_ids = _legacy_backup_vehicle_ids_by_email(conn, owner_email=user_email)
                restored["vehicle_ownerships"] = 0

            if vehicle_ids:
                placeholders = ", ".join(["?"] * len(vehicle_ids))
                restored["vehicles"] = _upsert_rows_from_backup(
                    conn,
                    table_name="vehicles",
                    where_sql=f"id IN ({placeholders})",
                    params=tuple(vehicle_ids),
                )
            else:
                restored["vehicles"] = 0
            restored["reminders"] = _upsert_rows_from_backup(
                conn,
                table_name="reminders",
                where_sql="customer_id = ?",
                params=(user_id,),
            )
            restored["reservations"] = _upsert_rows_from_backup(
                conn,
                table_name="reservations",
                where_sql="customer_id = ?",
                params=(user_id,),
            )
            restored["push_subscriptions"] = _upsert_rows_from_backup(
                conn,
                table_name="push_subscriptions",
                where_sql="customer_id = ?",
                params=(user_id,),
            )
            restored["security_access_logs"] = _upsert_rows_from_backup(
                conn,
                table_name="security_access_logs",
                where_sql="customer_id = ? OR lower(user_email) = lower(?)",
                params=(user_id, user_email),
            )
            restored["email_notification_logs"] = _upsert_rows_from_backup(
                conn,
                table_name="email_notification_logs",
                where_sql="customer_id = ? OR lower(email) = lower(?)",
                params=(user_id, user_email),
            )

            if vehicle_ids:
                placeholders = ", ".join(["?"] * len(vehicle_ids))
                restored["service_records"] = _upsert_rows_from_backup(
                    conn,
                    table_name="service_records",
                    where_sql=f"vehicle_id IN ({placeholders})",
                    params=tuple(vehicle_ids),
                )
            else:
                restored["service_records"] = 0

            conn.commit()
            return restored
        finally:
            conn.execute("DETACH DATABASE backupdb")


def _restore_vehicle_scope_from_backup(
    *,
    backup_db_file: Path,
    target_db_file: Path,
    vehicle_id: int,
) -> Dict[str, int]:
    restored: Dict[str, int] = {}
    with sqlite3.connect(str(target_db_file)) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("ATTACH DATABASE ? AS backupdb", (str(backup_db_file),))
        try:
            vehicle_row = conn.execute(
                "SELECT id, user_email FROM backupdb.vehicles WHERE id = ?",
                (vehicle_id,),
            ).fetchone()
            if not vehicle_row:
                raise ValueError(f"Vozidlo {vehicle_id} v záloze neexistuje")

            if _attached_sqlite_has_table(conn, "backupdb", "vehicle_ownerships"):
                owner_ids = _backup_owner_ids_for_vehicle_scope(
                    conn,
                    vehicle_id=vehicle_id,
                    owner_email=str(vehicle_row["user_email"] or ""),
                )
                if owner_ids:
                    placeholders = ", ".join(["?"] * len(owner_ids))
                    restored["customers"] = _upsert_rows_from_backup(
                        conn,
                        table_name="customers",
                        where_sql=f"id IN ({placeholders})",
                        params=tuple(owner_ids),
                    )
                else:
                    restored["customers"] = 0
                restored["vehicle_ownerships"] = _upsert_rows_from_backup(
                    conn,
                    table_name="vehicle_ownerships",
                    where_sql="vehicle_id = ?",
                    params=(vehicle_id,),
                )
            else:
                # Deprecated fallback for snapshots from legacy user_email ownership era.
                owner_email = str(vehicle_row["user_email"] or "").strip().lower()
                if owner_email:
                    owner_ids = _backup_owner_ids_for_vehicle_scope(
                        conn,
                        vehicle_id=vehicle_id,
                        owner_email=owner_email,
                    )
                    if owner_ids:
                        placeholders = ", ".join(["?"] * len(owner_ids))
                        restored["customers"] = _upsert_rows_from_backup(
                            conn,
                            table_name="customers",
                            where_sql=f"id IN ({placeholders})",
                            params=tuple(owner_ids),
                        )
                    else:
                        restored["customers"] = 0
                else:
                    restored["customers"] = 0
                restored["vehicle_ownerships"] = 0

            restored["vehicles"] = _upsert_rows_from_backup(
                conn,
                table_name="vehicles",
                where_sql="id = ?",
                params=(vehicle_id,),
            )
            restored["service_records"] = _upsert_rows_from_backup(
                conn,
                table_name="service_records",
                where_sql="vehicle_id = ?",
                params=(vehicle_id,),
            )
            restored["reminders"] = _upsert_rows_from_backup(
                conn,
                table_name="reminders",
                where_sql="vehicle_id = ?",
                params=(vehicle_id,),
            )
            restored["reservations"] = _upsert_rows_from_backup(
                conn,
                table_name="reservations",
                where_sql="vehicle_id = ?",
                params=(vehicle_id,),
            )
            conn.commit()
            return restored
        finally:
            conn.execute("DETACH DATABASE backupdb")


# ============= DEPENDENCIES =============

def require_developer_admin(
    email: str = Depends(get_current_user_email),
    request: FastAPIRequest = None,
    db: Session = Depends(get_db)
):
    """Ověří, že uživatel má roli developer_admin nebo admin."""
    ensure_customer_account_state_schema(db)
    customer = db.query(Customer).filter(Customer.email == email).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")
    if customer_is_deleted(customer) or customer_is_disabled(customer):
        raise HTTPException(status_code=403, detail="Účet je neaktivní")
    
    if not is_admin(customer.role):
        raise HTTPException(
            status_code=403,
            detail="Přístup odepřen. Vyžadována role developer_admin nebo admin."
        )

    if request and request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
        try:
            log_developer_action(
                db,
                developer_email=email,
                request=request,
                action_type=f"http.{request.method.lower()}",
                target_resource=str(request.url.path),
                parameters={
                    "query": str(request.url.query or ""),
                },
                result="requested",
                status_code=None,
            )
        except Exception:
            # Audit selhání nesmí zablokovat funkční flow.
            pass
    
    return email


def require_control_center_admin(
    email: str = Depends(get_current_user_email),
    request: FastAPIRequest = None,
    db: Session = Depends(get_db)
):
    """
    Přísný přístup pouze pro roli developer_admin (Control Center).
    """
    ensure_customer_account_state_schema(db)
    customer = db.query(Customer).filter(Customer.email == email).first()
    if not customer:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")
    if customer_is_deleted(customer) or customer_is_disabled(customer):
        raise HTTPException(status_code=403, detail="Účet je neaktivní")

    if not is_developer_admin(customer.role):
        raise HTTPException(
            status_code=403,
            detail="Přístup odepřen. Tato sekce je dostupná pouze pro roli developer_admin."
        )

    if request and request.method.upper() in {"POST", "PUT", "PATCH", "DELETE"}:
        try:
            log_developer_action(
                db,
                developer_email=email,
                request=request,
                action_type=f"http.{request.method.lower()}",
                target_resource=str(request.url.path),
                parameters={"query": str(request.url.query or "")},
                result="requested",
                status_code=None,
            )
        except Exception:
            pass

    return email


def get_customer_by_email(db: Session, email: str, *, include_deleted: bool = False) -> Optional[Customer]:
    """Najde uživatele case-insensitive podle emailu."""
    ensure_customer_account_state_schema(db)
    normalized = email.strip().lower()
    query = db.query(Customer).filter(func.lower(Customer.email) == normalized)
    if not include_deleted:
        query = query.filter(func.coalesce(Customer.is_deleted, False) == False)  # noqa: E712
    return query.first()


def resolve_tenant_id_for_create(
    db: Session,
    acting_admin: Customer,
    explicit_tenant_id: Optional[int],
) -> int:
    """
    Určí tenant pro nově vytvářený záznam.
    Priorita:
    1) explicitní tenant_id z requestu
    2) tenant přihlášeného admina
    3) první tenant v databázi (fallback)
    """
    if explicit_tenant_id is not None:
        if explicit_tenant_id <= 0:
            raise HTTPException(status_code=400, detail="tenant_id musí být kladné číslo")
        if TENANTS_AVAILABLE:
            tenant = db.query(Tenant).filter(Tenant.id == explicit_tenant_id).first()
            if not tenant:
                raise HTTPException(status_code=404, detail=f"Tenant {explicit_tenant_id} neexistuje")
        return explicit_tenant_id

    if acting_admin.tenant_id:
        return acting_admin.tenant_id

    if TENANTS_AVAILABLE:
        tenant = db.query(Tenant).order_by(Tenant.id.asc()).first()
        if tenant:
            return tenant.id

    raise HTTPException(
        status_code=400,
        detail="Nelze určit tenant_id pro nový záznam. Zadejte tenant_id explicitně."
    )


def validate_role_value(role: str) -> str:
    normalized_role = role.strip().lower()
    if normalized_role not in EDITABLE_ROLES:
        allowed = ", ".join(sorted(EDITABLE_ROLES))
        raise HTTPException(status_code=400, detail=f"Neplatná role '{role}'. Povolené role: {allowed}")
    return normalized_role


def normalize_license_plan(plan: Optional[str]) -> Optional[str]:
    if plan is None:
        return None
    normalized_plan = str(plan).strip().lower()
    if not normalized_plan:
        return None
    allowed_plans = {"free", "basic", "premium"}
    if normalized_plan not in allowed_plans:
        allowed = ", ".join(sorted(allowed_plans))
        raise HTTPException(status_code=400, detail=f"Neplatný plán licence '{plan}'. Povolené plány: {allowed}")
    return normalized_plan


def normalize_license_status(status: Optional[str]) -> Optional[str]:
    if status is None:
        return None
    normalized = str(status).strip().lower()
    if not normalized:
        return None
    allowed = {"active", "inactive", "expired", "suspended"}
    if normalized not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Neplatný status licence '{status}'. Povolené: {', '.join(sorted(allowed))}",
        )
    return normalized


def normalize_broadcast_severity(value: Optional[str]) -> str:
    normalized = str(value or "info").strip().lower()
    allowed = {"info", "warning", "critical"}
    if normalized not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Neplatná severity '{value}'. Povolené: {', '.join(sorted(allowed))}",
        )
    return normalized


def normalize_notification_target(
    target_type: Optional[str],
    target_value: Optional[str],
) -> tuple[str, Optional[str]]:
    normalized_type = str(target_type or "all").strip().lower()
    allowed = {"all", "tenant", "plan", "user"}
    if normalized_type not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Neplatný target_type '{target_type}'. Povolené: {', '.join(sorted(allowed))}",
        )

    normalized_value = str(target_value or "").strip()
    if normalized_type == "all":
        return "all", None
    if not normalized_value:
        raise HTTPException(status_code=400, detail="target_value je povinný pro zvolený target_type")
    if normalized_type == "plan":
        normalized_value = normalize_license_plan(normalized_value) or "free"
    if normalized_type in {"tenant", "user"}:
        try:
            normalized_value = str(int(normalized_value))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="target_value musí být číselné ID")
    return normalized_type, normalized_value


def generate_temporary_password(length: int = 14) -> str:
    safe_length = max(10, min(length, 40))
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(safe_length))


def build_deleted_alias_email(user_id: int) -> str:
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    return f"deleted+{user_id}.{stamp}@deleted.toozhub.local"


def resolve_job_name(job_name_raw: str) -> str:
    normalized = str(job_name_raw or "").strip().lower()
    if not normalized:
        raise HTTPException(status_code=400, detail="job_name je povinný")
    resolved = JOB_NAME_ALIASES.get(normalized)
    if not resolved:
        raise HTTPException(status_code=400, detail="Nepodporovaný job_name")
    return resolved


def safe_count_query(db: Session, query_str: str, params: Dict[str, Any] = None) -> int:
    """Bezpečné provedení COUNT dotazu - vrací 0 při chybě"""
    try:
        result = db.execute(text(query_str), params or {})
        return result.scalar() or 0
    except Exception as e:
        print(f"⚠️ Warning: Query failed: {query_str}, Error: {e}")
        return 0


def get_user_id_from_email(email: str, db: Session) -> Optional[int]:
    """Získá ID uživatele podle emailu"""
    user = db.query(Customer).filter(Customer.email == email).first()
    return user.id if user else None


def get_client_ip(request: FastAPIRequest) -> Optional[str]:
    """Získá IP adresu klienta"""
    if request.client:
        return request.client.host
    return None


def to_iso_datetime(value: Any) -> Optional[str]:
    """Bezpečný převod datetime/date/string hodnot na ISO string."""
    if value is None:
        return None
    if isinstance(value, str):
        text_value = value.strip()
        if not text_value:
            return None
        # SQLite často vrací datetime jako "YYYY-MM-DD HH:MM:SS(.ms)".
        candidate = text_value
        if " " in candidate and "T" not in candidate:
            candidate = candidate.replace(" ", "T", 1)
        try:
            datetime.fromisoformat(candidate.replace("Z", "+00:00"))
            return candidate
        except ValueError:
            return text_value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def is_online_by_last_seen(last_seen_at: Optional[str]) -> bool:
    """
    Urci online stav z casu posledni aktivity.
    """
    if not last_seen_at:
        return False
    try:
        parsed = datetime.fromisoformat(str(last_seen_at).replace("Z", "+00:00"))
    except ValueError:
        return False

    if parsed.tzinfo is not None:
        parsed_utc = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    else:
        parsed_utc = parsed

    return (datetime.utcnow() - parsed_utc).total_seconds() <= ONLINE_WINDOW_SECONDS


def build_vehicle_label(nickname: Optional[str], brand: Optional[str], model: Optional[str], plate: Optional[str], fallback_id: Optional[int] = None) -> str:
    if nickname:
        return nickname
    brand_model = " ".join([part for part in [brand, model] if part]).strip()
    if brand_model:
        return brand_model
    if plate:
        return plate
    if fallback_id:
        return f"Vozidlo #{fallback_id}"
    return "Neznámé vozidlo"


def build_location_line(city: Optional[str], region: Optional[str], country: Optional[str]) -> Optional[str]:
    parts = [part for part in [city, region, country] if part]
    return ", ".join(parts) if parts else None


def infer_setting_value_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, (dict, list)):
        return "json"
    return "string"


def normalize_setting_value(value: Any, value_type: str) -> Any:
    normalized_type = (value_type or "").strip().lower()
    if normalized_type == "boolean":
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)
    if normalized_type == "number":
        if isinstance(value, str):
            text_value = value.strip()
            if text_value == "":
                return 0
            if "." in text_value:
                try:
                    return float(text_value)
                except ValueError:
                    return 0
            try:
                return int(text_value)
            except ValueError:
                try:
                    return float(text_value)
                except ValueError:
                    return 0
        return value
    if normalized_type == "json" and isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value
    return value


def _default_env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _default_env_int(name: str, default: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return default


def get_default_admin_settings() -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Výchozí konfigurace administrace (uložená jako JSON)."""
    comgate_basic_monthly = max(0, _default_env_int("COMGATE_PRICE_BASIC_HALERS", 9900))
    comgate_premium_monthly = max(0, _default_env_int("COMGATE_PRICE_PREMIUM_HALERS", 29900))
    comgate_basic_yearly = max(0, _default_env_int("COMGATE_PRICE_BASIC_YEARLY_HALERS", comgate_basic_monthly * 10))
    comgate_premium_yearly = max(0, _default_env_int("COMGATE_PRICE_PREMIUM_YEARLY_HALERS", comgate_premium_monthly * 10))

    return {
        "general": {
            "app_name": {"value": "Správa vozidel", "value_type": "string", "description": "Název aplikace"},
            "app_version": {"value": "2.2.0", "value_type": "string", "description": "Verze aplikace"},
            "app_description": {"value": "Správa vozidel a servisních záznamů", "value_type": "string", "description": "Popis aplikace"},
            "maintenance_mode": {"value": False, "value_type": "boolean", "description": "Zapnout režim údržby"},
        },
        "security": {
            "jwt_expiration_hours": {"value": max(1, int(JWT_EXPIRE_MINUTES / 60)), "value_type": "number", "description": "Jak dlouho je token platný"},
            "session_timeout_minutes": {"value": 60, "value_type": "number", "description": "Automatické odhlášení po nečinnosti"},
            "max_login_attempts": {"value": 5, "value_type": "number", "description": "Počet pokusů před zablokováním"},
            "password_min_length": {"value": 6, "value_type": "number", "description": "Minimální počet znaků"},
            "password_require_uppercase": {"value": False, "value_type": "boolean", "description": "Heslo musí obsahovat velká písmena"},
            "password_require_numbers": {"value": True, "value_type": "boolean", "description": "Heslo musí obsahovat čísla"},
        },
        "database": {
            "backup_enabled": {"value": True, "value_type": "boolean", "description": "Povolit automatické zálohování"},
            "backup_frequency_hours": {"value": 24, "value_type": "number", "description": "Jak často se má zálohovat"},
            "backup_retention_days": {"value": 30, "value_type": "number", "description": "Kolik dní uchovávat zálohy"},
            "backup_path": {"value": str(DATA_DIR / "backups"), "value_type": "string", "description": "Složka pro ukládání záloh"},
        },
        "server": {
            "host": {"value": HOST, "value_type": "string", "description": "IP adresa nebo hostname"},
            "port": {"value": PORT, "value_type": "number", "description": "Port serveru"},
            "cors_enabled": {"value": True, "value_type": "boolean", "description": "Povolit Cross-Origin Resource Sharing"},
            "cors_origins": {"value": ALLOWED_ORIGINS, "value_type": "json", "description": "JSON pole povolených originů"},
            "rate_limit_enabled": {"value": True, "value_type": "boolean", "description": "Omezit počet požadavků"},
            "rate_limit_per_minute": {"value": 100, "value_type": "number", "description": "Maximální počet požadavků za minutu"},
        },
        "email": {
            "smtp_enabled": {"value": bool(SMTP_HOST), "value_type": "boolean", "description": "Zapnout odesílání e-mailů"},
            "smtp_host": {"value": SMTP_HOST, "value_type": "string", "description": "Adresa SMTP serveru"},
            "smtp_port": {"value": SMTP_PORT, "value_type": "number", "description": "Port SMTP serveru"},
            "smtp_user": {"value": SMTP_USER, "value_type": "string", "description": "Uživatelské jméno"},
            "smtp_from": {"value": SMTP_FROM, "value_type": "string", "description": "E-mailová adresa odesílatele"},
        },
        "logging": {
            "log_level": {"value": "INFO", "value_type": "string", "description": "Minimální úroveň logů"},
            "log_file_enabled": {"value": True, "value_type": "boolean", "description": "Ukládat logy do souboru"},
            "log_file_path": {"value": str(Path(__file__).parent.parent.parent / "logs"), "value_type": "string", "description": "Složka pro ukládání logů"},
            "log_rotation_days": {"value": 7, "value_type": "number", "description": "Po kolika dnech rotovat logy"},
        },
        "ui": {
            "theme": {"value": "light", "value_type": "string", "description": "Vzhled aplikace"},
            "primary_color": {"value": "#6366f1", "value_type": "string", "description": "Hex kód primární barvy"},
            "items_per_page": {"value": 24, "value_type": "number", "description": "Výchozí počet položek v seznamech"},
        },
        "api": {
            "api_docs_enabled": {"value": ENVIRONMENT != "production", "value_type": "boolean", "description": "Zobrazit Swagger dokumentaci"},
            "api_rate_limit": {"value": 120, "value_type": "number", "description": "Maximální počet API požadavků za minutu"},
        },
        "comgate": {
            "enabled": {"value": _default_env_bool("COMGATE_ENABLED", False), "value_type": "boolean", "description": "Aktivovat Comgate platby"},
            "merchant": {"value": os.getenv("COMGATE_MERCHANT", ""), "value_type": "string", "description": "Comgate Merchant ID"},
            "secret": {"value": os.getenv("COMGATE_SECRET", ""), "value_type": "string", "description": "Comgate Secret"},
            "test_mode": {"value": _default_env_bool("COMGATE_TEST_MODE", True), "value_type": "boolean", "description": "Testovací režim Comgate"},
            "currency": {"value": (os.getenv("COMGATE_CURRENCY", "CZK") or "CZK").strip().upper(), "value_type": "string", "description": "Měna plateb"},
            "method": {"value": (os.getenv("COMGATE_METHOD", "ALL") or "ALL").strip().upper(), "value_type": "string", "description": "Platební metoda (ALL/CARD/BANK)"},
            "subscription_method": {"value": (os.getenv("COMGATE_SUBSCRIPTION_METHOD", "CARD") or "CARD").strip().upper(), "value_type": "string", "description": "Metoda pro předplatné (doporučeno CARD)"},
            "test_one_time_fallback": {"value": _default_env_bool("COMGATE_TEST_ONE_TIME_FALLBACK", True), "value_type": "boolean", "description": "V testu povolit fallback bez recurring"},
            "lang": {"value": (os.getenv("COMGATE_LANG", "cs") or "cs").strip().lower(), "value_type": "string", "description": "Jazyk platební brány"},
            "country": {"value": (os.getenv("COMGATE_COUNTRY", "CZ") or "CZ").strip().upper(), "value_type": "string", "description": "Země platební brány"},
            "create_url": {"value": (os.getenv("COMGATE_CREATE_URL", "https://payments.comgate.cz/v1.0/create") or "https://payments.comgate.cz/v1.0/create").strip(), "value_type": "string", "description": "Comgate create endpoint"},
            "status_url": {"value": (os.getenv("COMGATE_STATUS_URL", "https://payments.comgate.cz/v1.0/status") or "https://payments.comgate.cz/v1.0/status").strip(), "value_type": "string", "description": "Comgate status endpoint"},
            "recurring_url": {"value": (os.getenv("COMGATE_RECURRING_URL", "https://payments.comgate.cz/v2.0/recurring") or "https://payments.comgate.cz/v2.0/recurring").strip(), "value_type": "string", "description": "Comgate recurring endpoint"},
            "price_basic_monthly_halers": {"value": comgate_basic_monthly, "value_type": "number", "description": "BASIC měsíčně (v haléřích)"},
            "price_basic_yearly_halers": {"value": comgate_basic_yearly, "value_type": "number", "description": "BASIC ročně (v haléřích)"},
            "price_premium_monthly_halers": {"value": comgate_premium_monthly, "value_type": "number", "description": "PREMIUM měsíčně (v haléřích)"},
            "price_premium_yearly_halers": {"value": comgate_premium_yearly, "value_type": "number", "description": "PREMIUM ročně (v haléřích)"},
            "subscription_grace_days": {"value": max(1, _default_env_int("COMGATE_SUBSCRIPTION_GRACE_DAYS", 7)), "value_type": "number", "description": "Délka grace periody po neúspěšné obnově"},
            "subscription_notify_days": {"value": str(os.getenv("COMGATE_SUBSCRIPTION_NOTIFY_DAYS", "14,7,1") or "14,7,1").strip(), "value_type": "string", "description": "Dny upozornění před expirací (CSV)"},
        },
        "system": {
            "autostart_enabled": {"value": False, "value_type": "boolean", "description": "Spustit aplikaci při startu PC"},
        },
    }


def load_admin_settings() -> Dict[str, Dict[str, Dict[str, Any]]]:
    defaults = get_default_admin_settings()
    if not ADMIN_SETTINGS_FILE.exists():
        return defaults

    try:
        with open(ADMIN_SETTINGS_FILE, "r", encoding="utf-8") as handle:
            stored = json.load(handle)
    except Exception:
        return defaults

    if not isinstance(stored, dict):
        return defaults

    merged = deepcopy(defaults)
    for category, entries in stored.items():
        if not isinstance(entries, dict):
            continue
        merged.setdefault(category, {})
        for key, payload in entries.items():
            if not isinstance(payload, dict):
                continue
            value = payload.get("value")
            default_payload = merged.get(category, {}).get(key, {})
            value_type = payload.get("value_type") or default_payload.get("value_type") or infer_setting_value_type(value)
            description = payload.get("description", default_payload.get("description"))
            merged[category][key] = {
                "value": value,
                "value_type": value_type,
                "description": description,
            }

    return merged


def save_admin_settings(settings: Dict[str, Dict[str, Dict[str, Any]]]) -> None:
    ADMIN_SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(ADMIN_SETTINGS_FILE, "w", encoding="utf-8") as handle:
        json.dump(settings, handle, ensure_ascii=False, indent=2)


# ============= SCHEMAS =============

class StatsOverview(BaseModel):
    total_users: int
    total_vehicles: int
    total_services: int
    total_records: int
    total_reservations: int = 0
    total_reminders: int = 0


class UserSummary(BaseModel):
    id: int
    email: str
    name: Optional[str] = None
    role: str
    tenant_id: Optional[int] = None
    city: Optional[str] = None
    phone: Optional[str] = None
    created_at: Optional[datetime] = None
    vehicles_count: int = 0
    last_ip_address: Optional[str] = None
    last_location: Optional[str] = None
    last_seen_at: Optional[str] = None
    is_online: bool = False
    license_plan: Optional[str] = None
    license_status: Optional[str] = None
    has_paid: bool = False
    last_paid_at: Optional[str] = None
    is_disabled: bool = False
    is_deleted: bool = False
    session_version: int = 0


class VehicleSummary(BaseModel):
    id: int
    user_email: str
    nickname: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    plate: Optional[str] = None
    vin: Optional[str] = None
    created_at: Optional[datetime] = None
    service_count: int = 0


# ============= CRUD SCHEMAS =============

class UserCreate(BaseModel):
    email: EmailStr
    name: Optional[str] = None
    password: str
    role: str = "user"
    tenant_id: Optional[int] = None
    ico: Optional[str] = None
    dic: Optional[str] = None
    phone: Optional[str] = None
    street: Optional[str] = None
    street_number: Optional[str] = None
    city: Optional[str] = None
    zip: Optional[str] = None
    license_plan: Optional[str] = None

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    name: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None
    ico: Optional[str] = None
    dic: Optional[str] = None
    phone: Optional[str] = None
    street: Optional[str] = None
    street_number: Optional[str] = None
    city: Optional[str] = None
    zip: Optional[str] = None
    license_plan: Optional[str] = None

class VehicleCreate(BaseModel):
    user_email: EmailStr
    nickname: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    plate: Optional[str] = None
    vin: Optional[str] = None
    tenant_id: Optional[int] = None

class VehicleUpdate(BaseModel):
    user_email: Optional[EmailStr] = None
    nickname: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    year: Optional[int] = None
    plate: Optional[str] = None
    vin: Optional[str] = None

class ServiceCreate(BaseModel):
    email: EmailStr
    name: str
    city: Optional[str] = None
    phone: Optional[str] = None
    ico: Optional[str] = None
    password: str
    tenant_id: Optional[int] = None

class ServiceUpdate(BaseModel):
    email: Optional[EmailStr] = None
    name: Optional[str] = None
    city: Optional[str] = None
    phone: Optional[str] = None
    ico: Optional[str] = None
    password: Optional[str] = None


class ServiceRegistrationDecision(BaseModel):
    review_note: Optional[str] = None


class ServiceRegistrationRequestItem(BaseModel):
    id: int
    status: str
    email: str
    ico: str
    service_name: str
    responsible_person: str
    phone: str
    dic: Optional[str] = None
    street: str
    street_number: Optional[str] = None
    city: str
    zip: str
    registration_purpose: str
    created_at: datetime
    reviewed_at: Optional[datetime] = None
    reviewed_by_customer_id: Optional[int] = None
    review_note: Optional[str] = None
    approved_customer_id: Optional[int] = None
    approved_tenant_id: Optional[int] = None

class RecordCreate(BaseModel):
    vehicle_id: int
    user_id: Optional[int] = None
    performed_at: datetime
    mileage: Optional[int] = None
    description: str
    price: Optional[float] = None
    category: Optional[str] = None
    note: Optional[str] = None

class RecordUpdate(BaseModel):
    vehicle_id: Optional[int] = None
    user_id: Optional[int] = None
    performed_at: Optional[datetime] = None
    mileage: Optional[int] = None
    description: Optional[str] = None
    price: Optional[float] = None
    category: Optional[str] = None
    note: Optional[str] = None


class ReminderUpdate(BaseModel):
    vehicle_id: Optional[int] = None
    type: Optional[str] = None
    text: Optional[str] = None
    due_date: Optional[date] = None
    is_manual: Optional[bool] = None
    is_completed: Optional[bool] = None


class ReservationUpdate(BaseModel):
    service_id: Optional[int] = None
    vehicle_id: Optional[int] = None
    service_type: Optional[str] = None
    note: Optional[str] = None
    start_datetime: Optional[datetime] = None
    end_datetime: Optional[datetime] = None
    status: Optional[str] = None


class SettingUpdateItem(BaseModel):
    category: str
    key: str
    value: Any
    value_type: Optional[str] = None
    description: Optional[str] = None


class SettingsUpdatePayload(BaseModel):
    settings: List[SettingUpdateItem]


class DbInfoResponse(BaseModel):
    db_path: str
    table_count: int
    tables: List[str]
    total_size_kb: Optional[float] = None


class TenantListItem(BaseModel):
    id: int
    name: str
    license_key: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class InstanceListItem(BaseModel):
    id: int
    device_id: Optional[str] = None
    app_version: Optional[str] = None
    last_seen_at: datetime
    
    class Config:
        from_attributes = True


class SecurityBlockIpRequest(BaseModel):
    ip_address: str
    reason: Optional[str] = None
    expires_in_minutes: Optional[int] = None


class SecurityUnblockIpRequest(BaseModel):
    ip_address: str
    reason: Optional[str] = None


class BackupCreateRequest(BaseModel):
    include_data_dir: bool = True


class BackupRestoreRequest(BaseModel):
    backup_id: str
    scope: str = "full"  # full | user | vehicle
    user_id: Optional[int] = None
    vehicle_id: Optional[int] = None
    confirm_text: str


class InternalCommandRequest(BaseModel):
    command: str


class UserStateActionRequest(BaseModel):
    reason: Optional[str] = None


class UserPasswordResetRequest(BaseModel):
    new_password: Optional[str] = None
    generate_random: bool = True
    reason: Optional[str] = None


class UserLicenseUpdateRequest(BaseModel):
    plan: Optional[str] = None
    status: Optional[str] = None
    valid_to: Optional[datetime] = None
    source: Optional[str] = None
    reason: Optional[str] = None


class BroadcastNotificationRequest(BaseModel):
    message: str
    title: Optional[str] = None
    severity: Optional[str] = "info"  # info | warning | critical
    target_type: Optional[str] = "all"  # all | tenant | plan | user
    target_value: Optional[str] = None
    expires_in_hours: Optional[int] = None


class JobStateRequest(BaseModel):
    job_name: str
    reason: Optional[str] = None


class StorageCleanupRequest(BaseModel):
    confirm_text: str
    delete_old_logs_days: Optional[int] = 30
    delete_old_backups_days: Optional[int] = 30


# ============= ENDPOINTS =============

@router.get("/overview", response_model=StatsOverview)
def get_overview(
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Vrátí přehled statistik celé databáze - pouze pro developer_admin"""
    try:
        total_users = safe_count_query(db, "SELECT COUNT(*) FROM customers")
        total_vehicles = safe_count_query(db, "SELECT COUNT(*) FROM vehicles")
        total_services = safe_count_query(db, "SELECT COUNT(*) FROM customers WHERE role = 'service'")
        total_records = safe_count_query(db, "SELECT COUNT(*) FROM service_records")
        total_reservations = safe_count_query(db, "SELECT COUNT(*) FROM reservations")
        total_reminders = safe_count_query(db, "SELECT COUNT(*) FROM reminders")
        
        return StatsOverview(
            total_users=total_users,
            total_vehicles=total_vehicles,
            total_services=total_services,
            total_records=total_records,
            total_reservations=total_reservations,
            total_reminders=total_reminders
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání statistik: {str(e)}")


@router.get("/users", response_model=List[UserSummary])
def get_all_users(
    limit: int = 50,
    offset: int = 0,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Vrátí seznam všech uživatelů s počtem vozidel - pouze pro developer_admin"""
    try:
        ensure_customer_account_state_schema(db)
        security_logs_available = inspect(db.bind).has_table("security_access_logs")
        licenses_available = inspect(db.bind).has_table("licenses")
        payments_available = inspect(db.bind).has_table("license_payment_transactions")
        license_plan_sql = (
            "(SELECT l.plan FROM licenses l WHERE l.tenant_id = c.tenant_id LIMIT 1)"
            if licenses_available
            else "NULL"
        )
        license_status_sql = (
            "(SELECT l.status FROM licenses l WHERE l.tenant_id = c.tenant_id LIMIT 1)"
            if licenses_available
            else "NULL"
        )
        has_paid_sql = (
            """
            (
                SELECT CASE WHEN EXISTS (
                    SELECT 1
                    FROM license_payment_transactions tx
                    WHERE tx.tenant_id = c.tenant_id
                      AND (
                        UPPER(COALESCE(tx.provider_status, '')) IN ('PAID', 'CONFIRMED')
                        OR LOWER(COALESCE(tx.event_type, '')) IN ('payment_paid', 'payment_confirmed', 'subscription_renewal_paid')
                      )
                ) THEN 1 ELSE 0 END
            )
            """
            if payments_available
            else "0"
        )
        last_paid_at_sql = (
            """
            (
                SELECT MAX(tx.created_at)
                FROM license_payment_transactions tx
                WHERE tx.tenant_id = c.tenant_id
                  AND (
                    UPPER(COALESCE(tx.provider_status, '')) IN ('PAID', 'CONFIRMED')
                    OR LOWER(COALESCE(tx.event_type, '')) IN ('payment_paid', 'payment_confirmed', 'subscription_renewal_paid')
                  )
            )
            """
            if payments_available
            else "NULL"
        )

        if security_logs_available:
            result = db.execute(text(f"""
                SELECT
                    c.id as id,
                    c.email as email,
                    c.name as name,
                    c.role as role,
                    c.tenant_id as tenant_id,
                    c.city as city,
                    c.phone as phone,
                    c.created_at as created_at,
                    COALESCE(c.is_disabled, 0) as is_disabled,
                    COALESCE(c.is_deleted, 0) as is_deleted,
                    COALESCE(c.session_version, 0) as session_version,
                    COALESCE(vehicle_counts.vehicles_count, 0) as vehicles_count,
                    (
                        SELECT sal.ip_address
                        FROM security_access_logs sal
                        WHERE lower(sal.user_email) = lower(c.email)
                          AND sal.event_type IN ('login_success', 'api_activity', 'support_contact_submitted')
                        ORDER BY sal.created_at DESC
                        LIMIT 1
                    ) as last_ip_address,
                    (
                        SELECT sal.city
                        FROM security_access_logs sal
                        WHERE lower(sal.user_email) = lower(c.email)
                          AND sal.event_type IN ('login_success', 'api_activity', 'support_contact_submitted')
                        ORDER BY sal.created_at DESC
                        LIMIT 1
                    ) as last_city,
                    (
                        SELECT sal.region
                        FROM security_access_logs sal
                        WHERE lower(sal.user_email) = lower(c.email)
                          AND sal.event_type IN ('login_success', 'api_activity', 'support_contact_submitted')
                        ORDER BY sal.created_at DESC
                        LIMIT 1
                    ) as last_region,
                    (
                        SELECT sal.country
                        FROM security_access_logs sal
                        WHERE lower(sal.user_email) = lower(c.email)
                          AND sal.event_type IN ('login_success', 'api_activity', 'support_contact_submitted')
                        ORDER BY sal.created_at DESC
                        LIMIT 1
                    ) as last_country,
                    (
                        SELECT sal.created_at
                        FROM security_access_logs sal
                        WHERE lower(sal.user_email) = lower(c.email)
                          AND sal.event_type IN ('login_success', 'api_activity', 'support_contact_submitted')
                        ORDER BY sal.created_at DESC
                        LIMIT 1
                    ) as last_seen_at,
                    {license_plan_sql} as license_plan,
                    {license_status_sql} as license_status,
                    {has_paid_sql} as has_paid,
                    {last_paid_at_sql} as last_paid_at
                FROM customers c
                {_customer_vehicle_count_join_sql(customer_alias="c", join_alias="vehicle_counts")}
                WHERE COALESCE(c.is_deleted, 0) = 0
                GROUP BY c.id, c.email, c.name, c.role, c.tenant_id, c.city, c.phone, c.created_at, c.is_disabled, c.is_deleted, c.session_version, vehicle_counts.vehicles_count
                ORDER BY c.created_at DESC
                LIMIT :limit OFFSET :offset
            """), {"limit": limit, "offset": offset})
        else:
            result = db.execute(text(f"""
                SELECT
                    c.id as id,
                    c.email as email,
                    c.name as name,
                    c.role as role,
                    c.tenant_id as tenant_id,
                    c.city as city,
                    c.phone as phone,
                    c.created_at as created_at,
                    COALESCE(c.is_disabled, 0) as is_disabled,
                    COALESCE(c.is_deleted, 0) as is_deleted,
                    COALESCE(c.session_version, 0) as session_version,
                    COALESCE(vehicle_counts.vehicles_count, 0) as vehicles_count,
                    {license_plan_sql} as license_plan,
                    {license_status_sql} as license_status,
                    {has_paid_sql} as has_paid,
                    {last_paid_at_sql} as last_paid_at
                FROM customers c
                {_customer_vehicle_count_join_sql(customer_alias="c", join_alias="vehicle_counts")}
                WHERE COALESCE(c.is_deleted, 0) = 0
                GROUP BY c.id, c.email, c.name, c.role, c.tenant_id, c.city, c.phone, c.created_at, c.is_disabled, c.is_deleted, c.session_version, vehicle_counts.vehicles_count
                ORDER BY c.created_at DESC
                LIMIT :limit OFFSET :offset
            """), {"limit": limit, "offset": offset})

        rows = result.fetchall()
        payment_state_by_tenant: Dict[int, Dict[str, Any]] = {}
        if payments_available:
            tenant_ids = []
            for row in rows:
                row_map = dict(row._mapping) if hasattr(row, "_mapping") else {}
                tenant_id = row_map.get("tenant_id")
                if tenant_id is not None:
                    tenant_ids.append(int(tenant_id))
            payment_state_by_tenant = _collect_paid_state_by_tenant(db, tenant_ids)

        users = []
        for row in rows:
            data = dict(row._mapping) if hasattr(row, "_mapping") else {}
            created_at = data.get("created_at")
            if security_logs_available:
                last_ip_address = data.get("last_ip_address")
                last_location = build_location_line(data.get("last_city"), data.get("last_region"), data.get("last_country"))
                last_seen_at = to_iso_datetime(data.get("last_seen_at"))
                license_plan = (data.get("license_plan") or "free")
                license_status = (data.get("license_status") or "active")
            else:
                last_ip_address = None
                last_location = None
                last_seen_at = None
                license_plan = (data.get("license_plan") or "free")
                license_status = (data.get("license_status") or "active")

            is_online = is_online_by_last_seen(last_seen_at)
            tenant_id = data.get("tenant_id")
            tenant_payment_state = payment_state_by_tenant.get(int(tenant_id)) if tenant_id is not None else None
            has_paid_value = bool(data.get("has_paid"))
            last_paid_at_value = data.get("last_paid_at")
            if tenant_payment_state:
                has_paid_value = bool(tenant_payment_state.get("has_paid", has_paid_value))
                if has_paid_value:
                    last_paid_at_value = tenant_payment_state.get("last_paid_at") or last_paid_at_value
                else:
                    last_paid_at_value = None

            users.append(UserSummary(
                id=data.get("id"),
                email=data.get("email"),
                name=data.get("name"),
                role=data.get("role"),
                tenant_id=data.get("tenant_id"),
                city=data.get("city"),
                phone=data.get("phone"),
                created_at=created_at,
                vehicles_count=data.get("vehicles_count") or 0,
                last_ip_address=last_ip_address,
                last_location=last_location,
                last_seen_at=last_seen_at,
                is_online=is_online,
                license_plan=license_plan,
                license_status=license_status,
                has_paid=has_paid_value,
                last_paid_at=to_iso_datetime(last_paid_at_value),
                is_disabled=bool(data.get("is_disabled")),
                is_deleted=bool(data.get("is_deleted")),
                session_version=int(data.get("session_version") or 0),
            ))
        
        return users
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání uživatelů: {str(e)}")


@router.post("/users")
def create_user(
    user_data: UserCreate,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Vytvoření nového uživatele"""
    try:
        acting_admin = get_customer_by_email(db, email)
        if not acting_admin:
            raise HTTPException(status_code=404, detail="Admin účet nenalezen")

        target_email = str(user_data.email).strip().lower()
        target_role = validate_role_value(user_data.role)
        selected_plan = normalize_license_plan(user_data.license_plan)
        if selected_plan and (not LICENSE_MANAGEMENT_AVAILABLE or not upgrade_license_plan):
            raise HTTPException(status_code=503, detail="Správa licencí není momentálně dostupná")
        if user_data.tenant_id is not None:
            tenant_id = resolve_tenant_id_for_create(db, acting_admin, user_data.tenant_id)
        else:
            tenant_id = create_dedicated_tenant(
                db,
                owner_email=target_email,
                owner_name=user_data.name,
            ).id

        # Zkontrolovat, zda email již existuje
        existing = get_customer_by_email(db, target_email)
        if existing:
            raise HTTPException(status_code=400, detail="Uživatel s tímto emailem již existuje")
        
        # Hash hesla
        password_hash_value = hash_password(user_data.password)
        
        # Vytvořit uživatele
        new_user = Customer(
            tenant_id=tenant_id,
            email=target_email,
            name=user_data.name,
            password_hash=password_hash_value,
            role=target_role,
            ico=user_data.ico,
            dic=user_data.dic,
            phone=user_data.phone,
            street=user_data.street,
            street_number=user_data.street_number,
            city=user_data.city,
            zip=user_data.zip,
            created_at=datetime.utcnow()
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        ensure_default_license_for_tenant(db, new_user.tenant_id)
        if selected_plan:
            upgrade_license_plan(db, new_user.tenant_id, selected_plan)
        
        return {
            "id": new_user.id,
            "email": new_user.email,
            "tenant_id": new_user.tenant_id,
            "role": new_user.role,
            "license_plan": selected_plan or "free",
            "message": "Uživatel byl vytvořen",
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při vytváření uživatele: {str(e)}")


@router.patch("/users/{user_id}")
def update_user(
    user_id: int,
    user_data: UserUpdate,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Úprava uživatele"""
    try:
        ensure_customer_account_state_schema(db)
        user = db.query(Customer).filter(Customer.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Uživatel nenalezen")
        if customer_is_deleted(user):
            raise HTTPException(status_code=400, detail="Smazaný účet nelze upravovat")

        selected_plan = normalize_license_plan(user_data.license_plan)
        if selected_plan and (not LICENSE_MANAGEMENT_AVAILABLE or not upgrade_license_plan):
            raise HTTPException(status_code=503, detail="Správa licencí není momentálně dostupná")
        
        # Aktualizovat pole
        if user_data.email is not None:
            new_email = str(user_data.email).strip().lower()
            # Zkontrolovat, zda nový email neexistuje
            existing = db.query(Customer).filter(
                func.lower(Customer.email) == new_email,
                Customer.id != user_id
            ).first()
            if existing:
                raise HTTPException(status_code=400, detail="Uživatel s tímto emailem již existuje")
            user.email = new_email
            _sync_vehicle_user_email_display_for_customer(db, user.id, new_email)
        
        if user_data.name is not None:
            user.name = user_data.name
        
        if user_data.role is not None:
            user.role = validate_role_value(user_data.role)

        if user_data.ico is not None:
            user.ico = user_data.ico
        if user_data.dic is not None:
            user.dic = user_data.dic
        if user_data.phone is not None:
            user.phone = user_data.phone
        if user_data.street is not None:
            user.street = user_data.street
        if user_data.street_number is not None:
            user.street_number = user_data.street_number
        if user_data.city is not None:
            user.city = user_data.city
        if user_data.zip is not None:
            user.zip = user_data.zip
        
        if user_data.password is not None:
            user.password_hash = hash_password(user_data.password)
            increment_customer_session_version(user)
        
        db.commit()

        updated_license = None
        if selected_plan:
            updated_license = upgrade_license_plan(db, user.tenant_id, selected_plan)

        return {
            "message": "Uživatel byl upraven",
            "license_plan": (updated_license or {}).get("plan", selected_plan),
            "license_status": (updated_license or {}).get("status"),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při úpravě uživatele: {str(e)}")


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Bezpečné smazání uživatele (soft-delete + invalidace session)."""
    try:
        ensure_customer_account_state_schema(db)
        actor = get_customer_by_email(db, email)
        user = db.query(Customer).filter(Customer.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Uživatel nenalezen")

        if actor and actor.id == user.id:
            raise HTTPException(status_code=400, detail="Nelze smazat aktuálně přihlášený admin účet.")

        if customer_is_deleted(user):
            return {"message": f"Účet {user.email} je již smazaný.", "soft_deleted": True}

        previous_email = (user.email or "").strip().lower()
        deleted_alias = build_deleted_alias_email(user.id)

        # Deprecated compatibility sync: display alias on Vehicle.user_email.
        # Ownership logic uses vehicle_ownerships and remains intact.
        _sync_vehicle_user_email_display_for_customer(db, user.id, deleted_alias)

        user.email = deleted_alias
        user.name = user.name or f"Deleted user #{user.id}"
        user.is_deleted = True
        user.is_disabled = True
        user.deleted_at = datetime.utcnow()
        user.disabled_at = datetime.utcnow()
        increment_customer_session_version(user)
        db.commit()

        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="user.delete",
            target_resource=f"user:{user_id}",
            parameters={
                "previous_email": previous_email,
                "deleted_alias": deleted_alias,
                "by": email.lower(),
            },
            result="success",
            status_code=200,
        )

        return {
            "message": f"Uživatel {previous_email} byl bezpečně smazán",
            "soft_deleted": True,
            "deleted_alias_email": deleted_alias,
            "session_version": customer_session_version(user),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při mazání uživatele: {str(e)}")


@router.get("/users/{user_id}/vehicles", response_model=List[VehicleSummary])
def get_user_vehicles(
    user_id: int,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Vrátí všechna vozidla daného uživatele - pouze pro developer_admin"""
    try:
        # Získat email uživatele podle ID
        user = db.query(Customer).filter(Customer.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Uživatel nenalezen")
        
        
        # Načíst vozidla uživatele podle explicitního ownership source-of-truth.
        vehicles_result = db.execute(text(f"""
            SELECT 
                v.id,
                COALESCE(owner_customer.email, v.user_email) as user_email,
                v.nickname,
                v.brand,
                v.model,
                v.year,
                v.plate,
                v.vin,
                v.created_at,
                COUNT(sr.id) as service_count
            FROM vehicles v
            LEFT JOIN service_records sr ON sr.vehicle_id = v.id
            {_primary_owner_join_sql(vehicle_alias="v", selector_alias="uvo_primary", ownership_alias="uvo", owner_alias="owner_customer")}
            WHERE uvo.customer_id = :user_id
              AND uvo.is_active = 1
            GROUP BY v.id, owner_customer.email, v.user_email, v.nickname, v.brand, v.model, v.year, v.plate, v.vin, v.created_at
            ORDER BY v.created_at DESC
        """), {"user_id": user_id})
        
        vehicles = []
        for row in vehicles_result:
            created_at = row[8]
            vehicles.append(VehicleSummary(
                id=row[0],
                user_email=row[1],
                nickname=row[2],
                brand=row[3],
                model=row[4],
                year=row[5],
                plate=row[6],
                vin=row[7],
                created_at=created_at,
                service_count=row[9] or 0
            ))
        
        return vehicles
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání vozidel: {str(e)}")


@router.get("/users/{user_id}/detail")
def get_user_detail(
    user_id: int,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """
    Detail uživatele pro admin dashboard.
    Vrací kompletní profil + navazující seznamy (vozidla, připomínky, rezervace, záznamy).
    """
    try:
        user = db.query(Customer).filter(Customer.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Uživatel nenalezen")
        normalized_email = (user.email or "").strip().lower()

        vehicle_rows = db.execute(text(f"""
            SELECT
                v.id,
                v.nickname,
                v.brand,
                v.model,
                v.year,
                v.plate,
                v.vin,
                v.engine,
                v.notes,
                v.stk_valid_until,
                v.insurance_provider,
                v.insurance_valid_until,
                v.created_at,
                COUNT(sr.id) as service_count
            FROM vehicles v
            LEFT JOIN service_records sr ON sr.vehicle_id = v.id
            {_primary_owner_join_sql(vehicle_alias="v", selector_alias="udv_primary", ownership_alias="udv_ownership", owner_alias="udv_owner")}
            WHERE udv_ownership.customer_id = :customer_id
              AND udv_ownership.is_active = 1
            GROUP BY
                v.id, v.nickname, v.brand, v.model, v.year, v.plate, v.vin, v.engine, v.notes,
                v.stk_valid_until, v.insurance_provider, v.insurance_valid_until, v.created_at
            ORDER BY v.created_at DESC
        """), {"customer_id": user_id})

        vehicles: List[Dict[str, Any]] = []
        for row in vehicle_rows:
            vehicle_id = row[0]
            vehicle_label = build_vehicle_label(row[1], row[2], row[3], row[5], vehicle_id)
            vehicles.append({
                "id": vehicle_id,
                "nickname": row[1],
                "brand": row[2],
                "model": row[3],
                "year": row[4],
                "plate": row[5],
                "vin": row[6],
                "engine": row[7],
                "notes": row[8],
                "stk_valid_until": to_iso_datetime(row[9]),
                "insurance_provider": row[10],
                "insurance_valid_until": to_iso_datetime(row[11]),
                "created_at": to_iso_datetime(row[12]),
                "service_count": row[13] or 0,
                "label": vehicle_label,
            })

        reminder_rows = db.execute(text("""
            SELECT
                r.id,
                r.vehicle_id,
                r.type,
                r.text,
                r.due_date,
                r.is_manual,
                r.is_completed,
                r.created_at,
                v.nickname,
                v.brand,
                v.model,
                v.plate
            FROM reminders r
            LEFT JOIN vehicles v ON v.id = r.vehicle_id
            WHERE r.customer_id = :customer_id
            ORDER BY
                CASE WHEN r.due_date IS NULL THEN 1 ELSE 0 END,
                r.due_date ASC,
                r.created_at DESC
        """), {"customer_id": user_id})

        reminders: List[Dict[str, Any]] = []
        for row in reminder_rows:
            vehicle_id = row[1]
            reminders.append({
                "id": row[0],
                "vehicle_id": vehicle_id,
                "type": row[2],
                "text": row[3],
                "due_date": to_iso_datetime(row[4]),
                "is_manual": bool(row[5]) if row[5] is not None else False,
                "is_completed": bool(row[6]) if row[6] is not None else False,
                "created_at": to_iso_datetime(row[7]),
                "vehicle_label": build_vehicle_label(row[8], row[9], row[10], row[11], vehicle_id),
            })

        reservation_rows = db.execute(text("""
            SELECT
                rs.id,
                rs.service_id,
                rs.vehicle_id,
                rs.service_type,
                rs.note,
                rs.start_datetime,
                rs.end_datetime,
                rs.status,
                rs.created_at,
                svc.name as service_name,
                svc.email as service_email,
                v.nickname,
                v.brand,
                v.model,
                v.plate
            FROM reservations rs
            LEFT JOIN customers svc ON svc.id = rs.service_id
            LEFT JOIN vehicles v ON v.id = rs.vehicle_id
            WHERE rs.customer_id = :customer_id
            ORDER BY rs.start_datetime DESC, rs.created_at DESC
        """), {"customer_id": user_id})

        reservations: List[Dict[str, Any]] = []
        for row in reservation_rows:
            vehicle_id = row[2]
            reservations.append({
                "id": row[0],
                "service_id": row[1],
                "vehicle_id": vehicle_id,
                "service_type": row[3],
                "note": row[4],
                "start_datetime": to_iso_datetime(row[5]),
                "end_datetime": to_iso_datetime(row[6]),
                "status": row[7],
                "created_at": to_iso_datetime(row[8]),
                "service_name": row[9],
                "service_email": row[10],
                "vehicle_label": build_vehicle_label(row[11], row[12], row[13], row[14], vehicle_id),
            })

        record_rows = db.execute(text("""
            SELECT
                sr.id,
                sr.vehicle_id,
                sr.user_id,
                sr.performed_at,
                sr.mileage,
                sr.description,
                sr.price,
                sr.note,
                sr.category,
                sr.created_by_ai,
                v.nickname,
                v.brand,
                v.model,
                v.plate
            FROM service_records sr
            JOIN vehicles v ON v.id = sr.vehicle_id
            JOIN vehicle_ownerships vo
              ON vo.vehicle_id = v.id
             AND vo.customer_id = :customer_id
             AND vo.is_active = 1
            ORDER BY sr.performed_at DESC
        """), {"customer_id": user_id})

        records: List[Dict[str, Any]] = []
        for row in record_rows:
            vehicle_id = row[1]
            records.append({
                "id": row[0],
                "vehicle_id": vehicle_id,
                "user_id": row[2],
                "performed_at": to_iso_datetime(row[3]),
                "mileage": row[4],
                "description": row[5],
                "price": row[6],
                "note": row[7],
                "category": row[8],
                "created_by_ai": bool(row[9]) if row[9] is not None else False,
                "vehicle_label": build_vehicle_label(row[10], row[11], row[12], row[13], vehicle_id),
            })

        ip_history: List[Dict[str, Any]] = []

        security_logs_available = inspect(db.bind).has_table("security_access_logs")
        if security_logs_available:
            try:
                ip_rows = db.execute(text("""
                    SELECT
                        ip_address,
                        user_agent,
                        created_at,
                        event_type,
                        city,
                        region,
                        country,
                        timezone,
                        isp,
                        source,
                        latitude,
                        longitude,
                        details
                    FROM security_access_logs
                    WHERE (customer_id = :customer_id OR lower(user_email) = :user_email)
                      AND ip_address IS NOT NULL
                      AND TRIM(ip_address) != ''
                    ORDER BY created_at DESC
                    LIMIT 20
                """), {"customer_id": user_id, "user_email": (user.email or "").strip().lower()})

                for row in ip_rows:
                    location_label = build_location_line(row[4], row[5], row[6])
                    details_payload: Dict[str, Any] = {}
                    if row[12]:
                        try:
                            parsed = json.loads(row[12])
                            if isinstance(parsed, dict):
                                details_payload = parsed
                        except Exception:
                            details_payload = {}

                    latitude = row[10]
                    longitude = row[11]
                    geo_accuracy = details_payload.get("geo_accuracy_m")
                    geo_source = details_payload.get("geo_source") or row[9]
                    if not location_label and latitude is not None and longitude is not None:
                        location_label = f"GPS {float(latitude):.5f}, {float(longitude):.5f}"

                    maps_url = None
                    if latitude is not None and longitude is not None:
                        maps_url = f"https://www.openstreetmap.org/?mlat={latitude}&mlon={longitude}#map=16/{latitude}/{longitude}"
                    ip_history.append({
                        "ip_address": row[0],
                        "user_agent": row[1],
                        "timestamp": to_iso_datetime(row[2]),
                        "event_type": row[3],
                        "city": row[4],
                        "region": row[5],
                        "country": row[6],
                        "timezone": row[7],
                        "isp": row[8],
                        "source": row[9],
                        "geo_source": geo_source,
                        "latitude": latitude,
                        "longitude": longitude,
                        "geo_accuracy_m": geo_accuracy,
                        "maps_url": maps_url,
                        "location_label": location_label,
                    })
            except Exception:
                ip_history = []

        # Fallback na starsi usage_analytics tabulku, pokud nejsou security logy.
        if not ip_history and USAGE_ANALYTICS_AVAILABLE:
            try:
                ip_rows = db.execute(text("""
                    SELECT ip_address, user_agent, timestamp
                    FROM usage_analytics
                    WHERE lower(user_email) = :user_email
                      AND ip_address IS NOT NULL
                      AND TRIM(ip_address) != ''
                    ORDER BY timestamp DESC
                    LIMIT 10
                """), {"user_email": (user.email or "").strip().lower()})

                for row in ip_rows:
                    ip_history.append({
                        "ip_address": row[0],
                        "user_agent": row[1],
                        "timestamp": to_iso_datetime(row[2]),
                        "event_type": "legacy_activity",
                        "city": None,
                        "region": None,
                        "country": None,
                        "timezone": None,
                        "isp": None,
                        "source": "usage_analytics",
                        "location_label": None,
                    })
            except Exception:
                ip_history = []

        address_parts = [part for part in [user.street, user.street_number] if part]
        address_line = " ".join(address_parts) if address_parts else None
        city_line_parts = [part for part in [user.zip, user.city] if part]
        city_line = " ".join(city_line_parts) if city_line_parts else None

        last_activity_at = None
        if ip_history:
            last_activity_at = ip_history[0].get("timestamp")
        elif records:
            last_activity_at = records[0].get("performed_at")
        elif reminders:
            last_activity_at = reminders[0].get("created_at")
        elif reservations:
            last_activity_at = reservations[0].get("created_at")

        license_plan = "free"
        license_status = "active"
        license_limit = None
        license_vehicle_count = None
        licenses_table_available = inspect(db.bind).has_table("licenses")
        subscriptions_table_available = inspect(db.bind).has_table("license_subscriptions")
        payments_table_available = inspect(db.bind).has_table("license_payment_transactions")
        license_row = (
            db.query(License).filter(License.tenant_id == user.tenant_id).first()
            if licenses_table_available
            else None
        )
        subscription_row = (
            db.query(LicenseSubscription)
            .filter(LicenseSubscription.tenant_id == user.tenant_id)
            .first()
            if subscriptions_table_available
            else None
        )
        if LICENSE_MANAGEMENT_AVAILABLE and get_tenant_license_status:
            try:
                license_payload = get_tenant_license_status(db, user.tenant_id, user.email)
                license_plan = license_payload.get("plan") or "free"
                license_status = license_payload.get("status") or "active"
                license_limit = license_payload.get("vehicles_limit")
                license_vehicle_count = license_payload.get("vehicles_current")
            except Exception:
                pass

        payment_rows = (
            db.query(LicensePaymentTransaction)
            .filter(LicensePaymentTransaction.tenant_id == user.tenant_id)
            .order_by(LicensePaymentTransaction.created_at.desc(), LicensePaymentTransaction.id.desc())
            .limit(10)
            .all()
            if payments_table_available
            else []
        )

        has_paid = False
        first_paid_at = None
        latest_paid_at = None
        live_payments_count = 0
        test_payments_count = 0
        live_paid_count = 0
        test_paid_count = 0
        failed_payments_count = 0
        refunded_payments_count = 0
        recent_payments: List[Dict[str, Any]] = []
        for tx in payment_rows:
            provider_status = str(tx.provider_status or "").strip().upper()
            event_type = str(tx.event_type or "").strip().lower()
            payment_environment = _infer_payment_environment(
                payload_json=tx.payload_json,
                provider_status=provider_status,
                event_type=event_type,
            )
            is_successful = _is_payment_successful(provider_status, event_type)
            is_failed = _is_payment_failed(provider_status, event_type)
            refund_status = _payment_refund_status(provider_status, event_type)
            is_counted_paid = _payment_counts_as_paid(
                environment=payment_environment,
                is_successful=is_successful,
            )
            tx_created = to_iso_datetime(tx.created_at)
            if payment_environment == "LIVE":
                live_payments_count += 1
            else:
                test_payments_count += 1
            if is_successful:
                if payment_environment == "LIVE":
                    live_paid_count += 1
                else:
                    test_paid_count += 1
            if is_failed:
                failed_payments_count += 1
            if refund_status == "refunded":
                refunded_payments_count += 1

            if is_counted_paid:
                has_paid = True
                if tx_created:
                    latest_paid_at = latest_paid_at or tx_created
                    first_paid_at = tx_created

            recent_payments.append(
                {
                    "id": tx.id,
                    "provider": tx.provider,
                    "trans_id": tx.trans_id,
                    "ref_id": tx.ref_id,
                    "provider_status": tx.provider_status,
                    "event_type": tx.event_type,
                    "payment_environment": payment_environment,
                    "is_successful": is_successful,
                    "is_failed": is_failed,
                    "amount_halers": tx.amount_halers,
                    "currency": tx.currency,
                    "payment_timestamp": tx_created,
                    "refund_status": refund_status,
                }
            )

        latest_license_admin_action = (
            db.query(DeveloperActionAuditLog)
            .filter(
                DeveloperActionAuditLog.target_resource.in_(
                    [f"user:{user_id}", f"tenant:{user.tenant_id}"]
                ),
                DeveloperActionAuditLog.action_type.in_(
                    ["license.change", "license.override", "user.create"]
                ),
            )
            .order_by(DeveloperActionAuditLog.created_at.desc(), DeveloperActionAuditLog.id.desc())
            .first()
        )

        source_of_activation = "manual"
        if has_paid:
            source_of_activation = "payment"
        if latest_license_admin_action:
            action = str(latest_license_admin_action.action_type or "").strip().lower()
            if action in {"license.change", "license.override"}:
                source_of_activation = "developer_override"
            elif action == "user.create":
                source_of_activation = "trial_or_manual"

        presence_row = None
        if security_logs_available:
            presence_row = db.execute(
                text(
                    """
                    SELECT
                        (
                            SELECT MAX(s1.created_at)
                            FROM security_access_logs s1
                            WHERE lower(s1.user_email) = :user_email
                              AND s1.event_type IN ('api_activity', 'login_success', 'support_contact_submitted')
                        ) AS last_seen_at,
                        (
                            SELECT MAX(s2.created_at)
                            FROM security_access_logs s2
                            WHERE lower(s2.user_email) = :user_email
                              AND s2.event_type = 'login_success'
                        ) AS last_login_at,
                        (
                            SELECT COUNT(DISTINCT COALESCE(s3.ip_address, '') || '|' || COALESCE(s3.user_agent, ''))
                            FROM security_access_logs s3
                            WHERE lower(s3.user_email) = :user_email
                              AND s3.created_at >= :window_start
                              AND s3.event_type IN ('api_activity', 'login_success')
                        ) AS active_session_count
                    """
                ),
                {
                    "window_start": datetime.utcnow() - timedelta(seconds=ONLINE_WINDOW_SECONDS),
                    "user_email": normalized_email,
                },
            ).fetchone()

        presence_last_seen = to_iso_datetime(presence_row[0] if presence_row else None)
        presence_last_login = to_iso_datetime(presence_row[1] if presence_row else None)
        active_session_count = int(presence_row[2] or 0) if presence_row else 0
        is_online = is_online_by_last_seen(presence_last_seen)

        activation_date = to_iso_datetime(license_row.valid_from if license_row else None)
        expiration_date = to_iso_datetime(license_row.valid_to if license_row else None)
        if not expiration_date:
            expiration_date = to_iso_datetime(subscription_row.current_period_end if subscription_row else None)
        next_renewal_date = to_iso_datetime(subscription_row.next_charge_at if subscription_row else None)
        purchase_date = first_paid_at or activation_date

        return {
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "role": user.role,
                "tenant_id": user.tenant_id,
                "ico": user.ico,
                "dic": user.dic,
                "phone": user.phone,
                "street": user.street,
                "street_number": user.street_number,
                "city": user.city,
                "zip": user.zip,
                "address_line": address_line,
                "city_line": city_line,
                "notify_email": bool(user.notify_email) if user.notify_email is not None else False,
                "notify_sms": bool(user.notify_sms) if user.notify_sms is not None else False,
                "notify_stk": bool(user.notify_stk) if user.notify_stk is not None else False,
                "notify_oil": bool(user.notify_oil) if user.notify_oil is not None else False,
                "notify_general": bool(user.notify_general) if user.notify_general is not None else False,
                "license_plan": license_plan,
                "license_status": license_status,
                "is_disabled": bool(getattr(user, "is_disabled", False)),
                "is_deleted": bool(getattr(user, "is_deleted", False)),
                "session_version": customer_session_version(user),
                "last_login_at": to_iso_datetime(getattr(user, "last_login_at", None)),
                "last_seen_at": to_iso_datetime(getattr(user, "last_seen_at", None)),
                "created_at": to_iso_datetime(user.created_at),
            },
            "stats": {
                "vehicles_count": len(vehicles),
                "reminders_count": len(reminders),
                "reservations_count": len(reservations),
                "records_count": len(records),
                "license_limit": license_limit,
                "license_vehicle_count": license_vehicle_count,
            },
            "meta": {
                "last_ip_address": ip_history[0]["ip_address"] if ip_history else None,
                "last_location": ip_history[0].get("location_label") if ip_history else None,
                "last_activity_at": last_activity_at,
                "ip_history": ip_history,
            },
            "insight": {
                "license": {
                    "current_plan": (license_row.plan if license_row else license_plan) or "free",
                    "status": (license_row.status if license_row else license_status) or "active",
                    "purchase_date": purchase_date,
                    "activation_date": activation_date,
                    "expiration_date": expiration_date,
                    "next_renewal_date": next_renewal_date,
                    "source_of_activation": source_of_activation,
                    "vehicles_limit": license_row.vehicles_limit if license_row else license_limit,
                },
                "payments_summary": {
                    "has_paid": has_paid,
                    "count": len(recent_payments),
                    "first_paid_at": first_paid_at,
                    "last_paid_at": latest_paid_at,
                    "count_live": live_payments_count,
                    "count_test": test_payments_count,
                    "live_paid_count": live_paid_count,
                    "test_paid_count": test_paid_count,
                    "failed_count": failed_payments_count,
                    "refund_count": refunded_payments_count,
                    "has_live_paid": live_paid_count > 0,
                    "has_test_paid": test_paid_count > 0,
                    "paid_counting_mode": "live_only" if not COUNT_TEST_PAYMENTS_AS_PAID else "live_and_test",
                    "provider": subscription_row.provider if subscription_row else None,
                },
                "payments": recent_payments,
                "presence": {
                    "online_status": "ONLINE" if is_online else "OFFLINE",
                    "last_seen_at": presence_last_seen or to_iso_datetime(getattr(user, "last_seen_at", None)),
                    "last_login_at": presence_last_login or to_iso_datetime(getattr(user, "last_login_at", None)),
                    "active_session_count": active_session_count,
                },
            },
            "panels": {
                "vehicles": vehicles,
                "reminders": reminders,
                "reservations": reservations,
                "records": records,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání detailu uživatele: {str(e)}")


@router.get("/services", response_model=List[UserSummary])
def get_all_services(
    limit: int = 50,
    offset: int = 0,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Vrátí seznam servisních účtů (role='service') - pouze pro developer_admin"""
    try:
        ensure_customer_account_state_schema(db)
        result = db.execute(text(f"""
            SELECT 
                c.id,
                c.email,
                c.name,
                c.role,
                c.tenant_id,
                c.city,
                c.phone,
                c.created_at,
                COALESCE(c.is_disabled, 0) as is_disabled,
                COALESCE(c.is_deleted, 0) as is_deleted,
                COALESCE(c.session_version, 0) as session_version,
                COALESCE(vehicle_counts.vehicles_count, 0) as vehicles_count
            FROM customers c
            {_customer_vehicle_count_join_sql(customer_alias="c", join_alias="vehicle_counts")}
            WHERE c.role = 'service'
              AND COALESCE(c.is_deleted, 0) = 0
            ORDER BY c.created_at DESC
            LIMIT :limit OFFSET :offset
        """), {"limit": limit, "offset": offset})
        
        services = []
        for row in result:
            created_at = row[7]
            services.append(UserSummary(
                id=row[0],
                email=row[1],
                name=row[2],
                role=row[3],
                tenant_id=row[4],
                city=row[5],
                phone=row[6],
                created_at=created_at,
                vehicles_count=int(row[11] or 0),
                is_disabled=bool(row[8]),
                is_deleted=bool(row[9]),
                session_version=int(row[10] or 0),
            ))
        
        return services
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání servisů: {str(e)}")


@router.post("/services")
def create_service(
    service_data: ServiceCreate,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Vytvoření nového servisu"""
    try:
        acting_admin = get_customer_by_email(db, email)
        if not acting_admin:
            raise HTTPException(status_code=404, detail="Admin účet nenalezen")

        target_email = str(service_data.email).strip().lower()
        if service_data.tenant_id is not None:
            tenant_id = resolve_tenant_id_for_create(db, acting_admin, service_data.tenant_id)
        else:
            tenant_id = create_dedicated_tenant(
                db,
                owner_email=target_email,
                owner_name=service_data.name,
            ).id

        # Zkontrolovat, zda email již existuje
        existing = get_customer_by_email(db, target_email)
        if existing:
            raise HTTPException(status_code=400, detail="Servis s tímto emailem již existuje")
        
        # Hash hesla
        password_hash_value = hash_password(service_data.password)
        
        # Vytvořit servis
        new_service = Customer(
            tenant_id=tenant_id,
            email=target_email,
            name=service_data.name,
            password_hash=password_hash_value,
            role="service",
            city=service_data.city,
            phone=service_data.phone,
            ico=service_data.ico,
            created_at=datetime.utcnow()
        )
        db.add(new_service)
        db.commit()
        db.refresh(new_service)

        ensure_default_license_for_tenant(db, new_service.tenant_id)
        
        return {
            "id": new_service.id,
            "email": new_service.email,
            "tenant_id": new_service.tenant_id,
            "message": "Servis byl vytvořen",
        }
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při vytváření servisu: {str(e)}")


@router.patch("/services/{service_id}")
def update_service(
    service_id: int,
    service_data: ServiceUpdate,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Úprava servisu"""
    try:
        service = db.query(Customer).filter(Customer.id == service_id).first()
        if not service:
            raise HTTPException(status_code=404, detail="Servis nenalezen")
        
        if service.role != "service":
            raise HTTPException(status_code=400, detail="Zadaný uživatel není servis")
        
        # Aktualizovat pole
        if service_data.email is not None:
            new_email = str(service_data.email).strip().lower()
            existing = db.query(Customer).filter(
                func.lower(Customer.email) == new_email,
                Customer.id != service_id
            ).first()
            if existing:
                raise HTTPException(status_code=400, detail="Servis s tímto emailem již existuje")
            service.email = new_email
            _sync_vehicle_user_email_display_for_customer(db, service.id, new_email)
        
        if service_data.name is not None:
            service.name = service_data.name
        
        if service_data.city is not None:
            service.city = service_data.city
        
        if service_data.phone is not None:
            service.phone = service_data.phone
        
        if service_data.ico is not None:
            service.ico = service_data.ico
        
        if service_data.password is not None:
            service.password_hash = hash_password(service_data.password)
        
        db.commit()
        return {"message": "Servis byl upraven"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při úpravě servisu: {str(e)}")


@router.delete("/services/{service_id}")
def delete_service(
    service_id: int,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Smazání servisu"""
    try:
        service = db.query(Customer).filter(Customer.id == service_id).first()
        if not service:
            raise HTTPException(status_code=404, detail="Servis nenalezen")
        
        if service.role != "service":
            raise HTTPException(status_code=400, detail="Zadaný uživatel není servis")

        vehicles_count = (
            db.query(func.count(func.distinct(VehicleOwnership.vehicle_id)))
            .filter(
                VehicleOwnership.customer_id == service.id,
                VehicleOwnership.is_active.is_(True),
            )
            .scalar()
            or 0
        )
        if vehicles_count > 0:
            raise HTTPException(
                status_code=400,
                detail=f"Servis má přiřazeno {vehicles_count} vozidel. Nejprve změňte vlastníka nebo vozidla smažte.",
            )
        
        service_email = service.email
        db.delete(service)
        db.commit()
        
        return {"message": f"Servis {service_email} byl smazán"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při mazání servisu: {str(e)}")


@router.get("/service-registration-requests", response_model=List[ServiceRegistrationRequestItem])
def list_service_registration_requests(
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    """
    Seznam žádostí o registraci servisního účtu.
    """
    try:
        query = db.query(ServiceRegistrationRequest)
        normalized_status = (status or "").strip().lower()
        if normalized_status:
            if normalized_status not in {"pending", "approved", "rejected"}:
                raise HTTPException(status_code=400, detail="Neplatný status. Použijte pending/approved/rejected.")
            query = query.filter(ServiceRegistrationRequest.status == normalized_status)

        requests = (
            query.order_by(ServiceRegistrationRequest.created_at.desc())
            .offset(max(0, offset))
            .limit(max(1, min(limit, 500)))
            .all()
        )

        return [
            ServiceRegistrationRequestItem(
                id=row.id,
                status=row.status,
                email=row.email,
                ico=row.ico,
                service_name=row.service_name,
                responsible_person=row.responsible_person,
                phone=row.phone,
                dic=row.dic,
                street=row.street,
                street_number=row.street_number,
                city=row.city,
                zip=row.zip,
                registration_purpose=row.registration_purpose,
                created_at=row.created_at,
                reviewed_at=row.reviewed_at,
                reviewed_by_customer_id=row.reviewed_by_customer_id,
                review_note=row.review_note,
                approved_customer_id=row.approved_customer_id,
                approved_tenant_id=row.approved_tenant_id,
            )
            for row in requests
        ]
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání žádostí: {str(e)}")


@router.post("/service-registration-requests/{request_id}/approve")
def approve_service_registration_request(
    request_id: int,
    payload: ServiceRegistrationDecision,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    """
    Schválí žádost o servisní registraci a vytvoří aktivní servisní účet.
    """
    try:
        reviewer = get_customer_by_email(db, email)
        if not reviewer:
            raise HTTPException(status_code=404, detail="Developer/Admin účet nebyl nalezen")

        req = db.query(ServiceRegistrationRequest).filter(ServiceRegistrationRequest.id == request_id).first()
        if not req:
            raise HTTPException(status_code=404, detail="Žádost nebyla nalezena")
        if req.status != "pending":
            raise HTTPException(status_code=400, detail=f"Žádost není ve stavu pending (aktuálně: {req.status})")

        existing_customer = get_customer_by_email(db, req.email)
        if existing_customer:
            raise HTTPException(status_code=400, detail="Účet s tímto emailem už existuje. Žádost nelze schválit.")

        normalized_ico = "".join(ch for ch in str(req.ico or "") if ch.isdigit())
        if normalized_ico:
            existing_service_same_ico = (
                db.query(Customer)
                .filter(
                    Customer.role == "service",
                    Customer.ico == normalized_ico,
                    func.lower(Customer.email) != req.email.strip().lower(),
                )
                .first()
            )
            if existing_service_same_ico:
                raise HTTPException(
                    status_code=400,
                    detail="Toto IČO je už použito u jiného servisního účtu. Schválení bylo zablokováno.",
                )

        dedicated_tenant = create_dedicated_tenant(
            db,
            owner_email=req.email,
            owner_name=req.service_name,
        )

        new_service = Customer(
            tenant_id=dedicated_tenant.id,
            email=req.email.strip().lower(),
            password_hash=req.password_hash,
            name=req.service_name,
            ico=normalized_ico or req.ico,
            dic=req.dic,
            street=req.street,
            street_number=req.street_number,
            city=req.city,
            zip=req.zip,
            phone=req.phone,
            role="service",
            created_at=datetime.utcnow(),
        )
        db.add(new_service)
        db.flush()

        ensure_default_license_for_tenant(db, dedicated_tenant.id)

        req.status = "approved"
        req.reviewed_by_customer_id = reviewer.id
        req.reviewed_at = datetime.utcnow()
        req.review_note = (payload.review_note or "").strip() or "Schváleno developerem."
        req.approved_customer_id = new_service.id
        req.approved_tenant_id = dedicated_tenant.id

        db.commit()
        db.refresh(new_service)
        db.refresh(req)

        return {
            "message": "Žádost byla schválena a servisní účet vytvořen.",
            "request_id": req.id,
            "service_customer_id": new_service.id,
            "tenant_id": dedicated_tenant.id,
            "email": new_service.email,
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při schvalování žádosti: {str(e)}")


@router.post("/service-registration-requests/{request_id}/reject")
def reject_service_registration_request(
    request_id: int,
    payload: ServiceRegistrationDecision,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    """
    Zamítne žádost o servisní registraci.
    """
    try:
        reviewer = get_customer_by_email(db, email)
        if not reviewer:
            raise HTTPException(status_code=404, detail="Developer/Admin účet nebyl nalezen")

        req = db.query(ServiceRegistrationRequest).filter(ServiceRegistrationRequest.id == request_id).first()
        if not req:
            raise HTTPException(status_code=404, detail="Žádost nebyla nalezena")
        if req.status != "pending":
            raise HTTPException(status_code=400, detail=f"Žádost není ve stavu pending (aktuálně: {req.status})")

        req.status = "rejected"
        req.reviewed_by_customer_id = reviewer.id
        req.reviewed_at = datetime.utcnow()
        req.review_note = (payload.review_note or "").strip() or "Žádost byla zamítnuta."
        req.approved_customer_id = None
        req.approved_tenant_id = None

        db.commit()
        db.refresh(req)

        return {
            "message": "Žádost byla zamítnuta.",
            "request_id": req.id,
            "status": req.status,
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při zamítání žádosti: {str(e)}")


@router.get("/vehicles")
def get_all_vehicles(
    limit: int = 50,
    offset: int = 0,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Vrátí seznam všech vozidel - pouze pro developer_admin"""
    try:
        result = db.execute(text(f"""
            SELECT 
                v.id,
                COALESCE(owner_customer.email, v.user_email) as user_email,
                v.nickname,
                v.brand,
                v.model,
                v.year,
                v.plate,
                v.vin,
                v.created_at,
                COUNT(sr.id) as service_count,
                owner_customer.name as owner_name,
                owner_customer.id as owner_id,
                v.tenant_id
            FROM vehicles v
            LEFT JOIN service_records sr ON sr.vehicle_id = v.id
            {_primary_owner_join_sql(vehicle_alias="v", selector_alias="gav_primary", ownership_alias="gav_ownership", owner_alias="owner_customer")}
            GROUP BY v.id, owner_customer.email, v.user_email, v.nickname, v.brand, v.model, v.year, v.plate, v.vin, v.created_at, owner_customer.name, owner_customer.id, v.tenant_id
            ORDER BY v.created_at DESC
            LIMIT :limit OFFSET :offset
        """), {"limit": limit, "offset": offset})
        
        vehicles = []
        for row in result:
            created_at = row[8]
            vehicles.append({
                "id": row[0],
                "user_email": row[1],
                "nickname": row[2],
                "brand": row[3],
                "model": row[4],
                "year": row[5],
                "plate": row[6],
                "vin": row[7],
                "created_at": to_iso_datetime(created_at),
                "service_count": row[9] or 0,
                "owner_name": row[10],
                "owner_id": row[11],
                "tenant_id": row[12],
            })
        
        return vehicles
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání vozidel: {str(e)}")


@router.post("/vehicles")
def create_vehicle(
    vehicle_data: VehicleCreate,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Vytvoření nového vozidla"""
    try:
        actor = get_customer_by_email(db, email)
        target_email = str(vehicle_data.user_email).strip().lower()
        # Zkontrolovat, zda uživatel existuje
        user = get_customer_by_email(db, target_email)
        if not user:
            raise HTTPException(status_code=404, detail="Uživatel nenalezen")

        if vehicle_data.tenant_id is not None and vehicle_data.tenant_id != user.tenant_id:
            raise HTTPException(
                status_code=400,
                detail=f"tenant_id vozidla ({vehicle_data.tenant_id}) neodpovídá tenantu vlastníka ({user.tenant_id})",
            )
        
        # Vytvořit vozidlo
        new_vehicle = Vehicle(
            tenant_id=user.tenant_id,
            user_email=user.email,
            nickname=vehicle_data.nickname,
            brand=vehicle_data.brand,
            model=vehicle_data.model,
            year=vehicle_data.year,
            plate=vehicle_data.plate,
            vin=vehicle_data.vin,
            created_at=datetime.utcnow()
        )
        db.add(new_vehicle)
        db.flush()
        _reassign_vehicle_primary_owner(
            db,
            vehicle=new_vehicle,
            owner=user,
            assigned_by_customer_id=actor.id if actor else user.id,
        )
        db.commit()
        db.refresh(new_vehicle)
        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="vehicle.create",
            target_resource=f"vehicle:{new_vehicle.id}",
            parameters={
                "vehicle_id": new_vehicle.id,
                "tenant_id": new_vehicle.tenant_id,
                "owner_customer_id": user.id,
                "owner_email": user.email,
            },
            result="success",
            status_code=200,
        )
        
        return {"id": new_vehicle.id, "tenant_id": new_vehicle.tenant_id, "message": "Vozidlo bylo vytvořeno"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při vytváření vozidla: {str(e)}")


@router.patch("/vehicles/{vehicle_id}")
def update_vehicle(
    vehicle_id: int,
    vehicle_data: VehicleUpdate,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Úprava vozidla"""
    try:
        actor = get_customer_by_email(db, email)
        vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
        if not vehicle:
            raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
        
        # Aktualizovat pole
        if vehicle_data.user_email is not None:
            target_email = str(vehicle_data.user_email).strip().lower()
            user = get_customer_by_email(db, target_email)
            if not user:
                raise HTTPException(status_code=404, detail="Uživatel nenalezen")
            _reassign_vehicle_primary_owner(
                db,
                vehicle=vehicle,
                owner=user,
                assigned_by_customer_id=actor.id if actor else user.id,
            )
        
        if vehicle_data.nickname is not None:
            vehicle.nickname = vehicle_data.nickname
        
        if vehicle_data.brand is not None:
            vehicle.brand = vehicle_data.brand
        
        if vehicle_data.model is not None:
            vehicle.model = vehicle_data.model
        
        if vehicle_data.year is not None:
            vehicle.year = vehicle_data.year
        
        if vehicle_data.plate is not None:
            vehicle.plate = vehicle_data.plate
        
        if vehicle_data.vin is not None:
            vehicle.vin = vehicle_data.vin
        
        db.commit()
        primary_owner = get_primary_vehicle_owner(db, vehicle)
        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="vehicle.update",
            target_resource=f"vehicle:{vehicle.id}",
            parameters={
                "vehicle_id": vehicle.id,
                "tenant_id": vehicle.tenant_id,
                "owner_customer_id": primary_owner.id if primary_owner else None,
                "owner_email": primary_owner.email if primary_owner else None,
            },
            result="success",
            status_code=200,
        )
        return {"message": "Vozidlo bylo upraveno"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při úpravě vozidla: {str(e)}")


@router.delete("/vehicles/{vehicle_id}")
def delete_vehicle(
    vehicle_id: int,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Smazání vozidla"""
    try:
        vehicle = db.query(Vehicle).filter(Vehicle.id == vehicle_id).first()
        if not vehicle:
            raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
        primary_owner = get_primary_vehicle_owner(db, vehicle)
        db.delete(vehicle)
        db.commit()
        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="vehicle.delete",
            target_resource=f"vehicle:{vehicle_id}",
            parameters={
                "vehicle_id": vehicle_id,
                "tenant_id": vehicle.tenant_id,
                "owner_customer_id": primary_owner.id if primary_owner else None,
                "owner_email": primary_owner.email if primary_owner else None,
            },
            result="success",
            status_code=200,
        )
        
        return {"message": "Vozidlo bylo smazáno"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při mazání vozidla: {str(e)}")


@router.get("/records")
def get_all_records(
    limit: int = 50,
    offset: int = 0,
    user_id: Optional[int] = None,
    vehicle_id: Optional[int] = None,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """
    Vrátí kompletní seznam všech servisních záznamů
    Dostupné jen pro developer_admin
    """
    try:
        query = """
            SELECT 
                sr.id,
                sr.vehicle_id,
                sr.user_id,
                sr.performed_at,
                sr.mileage,
                sr.description,
                sr.price,
                sr.note,
                sr.category,
                sr.performed_at as created_at,
                v.nickname as vehicle_nickname,
                v.brand as vehicle_brand,
                v.model as vehicle_model,
                v.plate as vehicle_plate,
                c.email as user_email,
                c.name as user_name
            FROM service_records sr
            LEFT JOIN vehicles v ON v.id = sr.vehicle_id
            LEFT JOIN customers c ON c.id = sr.user_id
            WHERE 1=1
        """
        params = {}
        
        if user_id:
            query += " AND sr.user_id = :user_id"
            params["user_id"] = user_id
        
        if vehicle_id:
            query += " AND sr.vehicle_id = :vehicle_id"
            params["vehicle_id"] = vehicle_id
        
        query += " ORDER BY sr.performed_at DESC LIMIT :limit OFFSET :offset"
        params["limit"] = limit
        params["offset"] = offset
        
        result = db.execute(text(query), params)
        
        records = []
        for row in result:
            performed_at = row[3]
            created_at = row[9]
            records.append({
                "id": row[0],
                "vehicle_id": row[1],
                "user_id": row[2],
                "performed_at": to_iso_datetime(performed_at),
                "mileage": row[4],
                "description": row[5],
                "price": row[6],
                "note": row[7],
                "category": row[8],
                "created_at": to_iso_datetime(created_at),
                "vehicle_nickname": row[10],
                "vehicle_brand": row[11],
                "vehicle_model": row[12],
                "vehicle_plate": row[13],
                "user_email": row[14],
                "user_name": row[15]
            })
        
        # Celkový počet
        count_query = "SELECT COUNT(*) FROM service_records WHERE 1=1"
        count_params = {}
        if user_id:
            count_query += " AND user_id = :user_id"
            count_params["user_id"] = user_id
        if vehicle_id:
            count_query += " AND vehicle_id = :vehicle_id"
            count_params["vehicle_id"] = vehicle_id
        
        total_count = safe_count_query(db, count_query, count_params)
        
        return {
            "records": records,
            "total": total_count,
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "records": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
            "error": f"Chyba při načítání záznamů: {str(e)}"
        }


@router.get("/audit")
def get_audit_log(
    limit: int = 50,
    offset: int = 0,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """
    Vrátí poslední aktivity (reservations, reminders jako audit log)
    Dostupné jen pro developer_admin
    """
    try:
        # Kombinace reservations a reminders jako "audit log"
        # SQLite nepodporuje CONCAT, použít || pro concatenaci
        query = """
            SELECT 
                'reservation' as type,
                r.id,
                r.created_at as timestamp,
                c.email as actor_email,
                'CREATE_RESERVATION' as action,
                r.vehicle_id as entity_id,
                r.service_id as related_id,
                ('Rezervace pro vozidlo ' || COALESCE(v.nickname, '?')) as details
            FROM reservations r
            LEFT JOIN vehicles v ON v.id = r.vehicle_id
            LEFT JOIN customers c ON c.id = r.customer_id
            WHERE 1=1
            
            UNION ALL
            
            SELECT 
                'reminder' as type,
                rem.id,
                rem.created_at as timestamp,
                c.email as actor_email,
                'CREATE_REMINDER' as action,
                rem.vehicle_id as entity_id,
                NULL as related_id,
                rem.text as details
            FROM reminders rem
            LEFT JOIN customers c ON c.id = rem.customer_id
            WHERE 1=1
            
            ORDER BY timestamp DESC
            LIMIT :limit OFFSET :offset
        """
        
        result = db.execute(text(query), {"limit": limit, "offset": offset})
        
        logs = []
        for row in result:
            timestamp = row[2]
            logs.append({
                "id": row[1],
                "timestamp": to_iso_datetime(timestamp),
                "actor_email": row[3],
                "action": row[4],
                "entity_type": row[0],
                "entity_id": row[5],
                "details": row[7]
            })
        
        return {
            "logs": logs,
            "total": len(logs),
            "limit": limit,
            "offset": offset
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "logs": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
            "error": f"Chyba při načítání audit logu: {str(e)}"
        }


@router.post("/records")
def create_record(
    record_data: RecordCreate,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Vytvoření nového servisního záznamu"""
    try:
        # Zkontrolovat, zda vozidlo existuje
        vehicle = db.query(Vehicle).filter(Vehicle.id == record_data.vehicle_id).first()
        if not vehicle:
            raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
        
        resolved_user_id = record_data.user_id

        # Pokud je zadán user_id, zkontrolovat, zda existuje
        if resolved_user_id:
            user = db.query(Customer).filter(Customer.id == resolved_user_id).first()
            if not user:
                raise HTTPException(status_code=404, detail="Uživatel nenalezen")
            if user.tenant_id != vehicle.tenant_id:
                raise HTTPException(
                    status_code=400,
                    detail="Uživatel záznamu musí být ze stejného tenantu jako vozidlo",
                )
        else:
            # Pokud není zadán user_id, použít aktuálního admina
            current_user = get_customer_by_email(db, email)
            if current_user and current_user.tenant_id == vehicle.tenant_id:
                resolved_user_id = current_user.id
            else:
                resolved_user_id = None
        
        # Vytvořit záznam
        new_record = ServiceRecord(
            tenant_id=vehicle.tenant_id,
            vehicle_id=record_data.vehicle_id,
            user_id=resolved_user_id,
            performed_at=record_data.performed_at,
            mileage=record_data.mileage,
            description=record_data.description,
            price=record_data.price,
            category=record_data.category,
            note=record_data.note
        )
        db.add(new_record)
        db.commit()
        db.refresh(new_record)
        
        return {"id": new_record.id, "tenant_id": new_record.tenant_id, "message": "Servisní záznam byl vytvořen"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při vytváření záznamu: {str(e)}")


@router.patch("/records/{record_id}")
def update_record(
    record_id: int,
    record_data: RecordUpdate,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Úprava servisního záznamu"""
    try:
        record = db.query(ServiceRecord).filter(ServiceRecord.id == record_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="Záznam nenalezen")
        
        # Aktualizovat pole
        if record_data.vehicle_id is not None:
            vehicle = db.query(Vehicle).filter(Vehicle.id == record_data.vehicle_id).first()
            if not vehicle:
                raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
            record.vehicle_id = record_data.vehicle_id
            record.tenant_id = vehicle.tenant_id
        
        if record_data.user_id is not None:
            user = db.query(Customer).filter(Customer.id == record_data.user_id).first()
            if not user:
                raise HTTPException(status_code=404, detail="Uživatel nenalezen")
            if user.tenant_id != record.tenant_id:
                raise HTTPException(
                    status_code=400,
                    detail="Uživatel záznamu musí být ze stejného tenantu jako servisní záznam",
                )
            record.user_id = record_data.user_id
        
        if record_data.performed_at is not None:
            record.performed_at = record_data.performed_at
        
        if record_data.mileage is not None:
            record.mileage = record_data.mileage
        
        if record_data.description is not None:
            record.description = record_data.description
        
        if record_data.price is not None:
            record.price = record_data.price
        
        if record_data.category is not None:
            record.category = record_data.category
        
        if record_data.note is not None:
            record.note = record_data.note
        
        db.commit()
        return {"message": "Záznam byl upraven"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při úpravě záznamu: {str(e)}")


@router.delete("/records/{record_id}")
def delete_record(
    record_id: int,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Smazání servisního záznamu"""
    try:
        record = db.query(ServiceRecord).filter(ServiceRecord.id == record_id).first()
        if not record:
            raise HTTPException(status_code=404, detail="Záznam nenalezen")
        
        db.delete(record)
        db.commit()
        
        return {"message": "Záznam byl smazán"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při mazání záznamu: {str(e)}")


# ============= REMINDERS CRUD (ADMIN) =============

@router.patch("/reminders/{reminder_id}")
def update_reminder_admin(
    reminder_id: int,
    reminder_data: ReminderUpdate,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Úprava připomínky administrátorem."""
    try:
        reminder = db.query(Reminder).filter(Reminder.id == reminder_id).first()
        if not reminder:
            raise HTTPException(status_code=404, detail="Připomínka nenalezena")

        if reminder_data.vehicle_id is not None:
            if reminder_data.vehicle_id <= 0:
                raise HTTPException(status_code=400, detail="vehicle_id musí být kladné číslo")
            vehicle = db.query(Vehicle).filter(Vehicle.id == reminder_data.vehicle_id).first()
            if not vehicle:
                raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
            reminder.vehicle_id = reminder_data.vehicle_id

        if reminder_data.type is not None:
            reminder.type = reminder_data.type.strip().upper() if reminder_data.type else reminder.type
        if reminder_data.text is not None:
            reminder.text = reminder_data.text
        if reminder_data.due_date is not None:
            reminder.due_date = reminder_data.due_date
        if reminder_data.is_manual is not None:
            reminder.is_manual = reminder_data.is_manual
        if reminder_data.is_completed is not None:
            apply_reminder_completion_update(reminder, reminder_data.is_completed)

        db.commit()
        return {"message": "Připomínka byla upravena adminem"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při úpravě připomínky: {str(e)}")


@router.delete("/reminders/{reminder_id}")
def delete_reminder_admin(
    reminder_id: int,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Smazání připomínky administrátorem."""
    try:
        reminder = db.query(Reminder).filter(Reminder.id == reminder_id).first()
        if not reminder:
            raise HTTPException(status_code=404, detail="Připomínka nenalezena")

        db.delete(reminder)
        db.commit()
        return {"message": "Připomínka byla smazána adminem"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při mazání připomínky: {str(e)}")


# ============= RESERVATIONS CRUD (ADMIN) =============

@router.patch("/reservations/{reservation_id}")
def update_reservation_admin(
    reservation_id: int,
    reservation_data: ReservationUpdate,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Úprava rezervace administrátorem."""
    try:
        reservation = db.query(Reservation).filter(Reservation.id == reservation_id).first()
        if not reservation:
            raise HTTPException(status_code=404, detail="Rezervace nenalezena")

        if reservation_data.service_id is not None:
            service = db.query(Customer).filter(Customer.id == reservation_data.service_id).first()
            if not service:
                raise HTTPException(status_code=404, detail="Servis nenalezen")
            reservation.service_id = reservation_data.service_id

        if reservation_data.vehicle_id is not None:
            vehicle = db.query(Vehicle).filter(Vehicle.id == reservation_data.vehicle_id).first()
            if not vehicle:
                raise HTTPException(status_code=404, detail="Vozidlo nenalezeno")
            reservation.vehicle_id = reservation_data.vehicle_id

        if reservation_data.service_type is not None:
            reservation.service_type = reservation_data.service_type
        if reservation_data.note is not None:
            reservation.note = reservation_data.note
        if reservation_data.start_datetime is not None:
            reservation.start_datetime = reservation_data.start_datetime
        if reservation_data.end_datetime is not None:
            reservation.end_datetime = reservation_data.end_datetime
        if reservation_data.status is not None:
            normalized_status = reservation_data.status.strip().upper()
            allowed_statuses = {"PENDING", "CONFIRMED", "CANCELLED", "COMPLETED"}
            if normalized_status not in allowed_statuses:
                raise HTTPException(
                    status_code=400,
                    detail=f"Neplatný status '{reservation_data.status}'. Povolené: {', '.join(sorted(allowed_statuses))}"
                )
            reservation.status = normalized_status

        db.commit()
        return {"message": "Rezervace byla upravena adminem"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při úpravě rezervace: {str(e)}")


@router.delete("/reservations/{reservation_id}")
def delete_reservation_admin(
    reservation_id: int,
    request: FastAPIRequest,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Smazání rezervace administrátorem."""
    try:
        reservation = db.query(Reservation).filter(Reservation.id == reservation_id).first()
        if not reservation:
            raise HTTPException(status_code=404, detail="Rezervace nenalezena")

        db.delete(reservation)
        db.commit()
        return {"message": "Rezervace byla smazána adminem"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při mazání rezervace: {str(e)}")


# ============= SYSTEM TOOLS =============

@router.post("/reindex")
def reindex_database(
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Přeindexování databáze - pro SQLite není potřeba, vrací úspěch"""
    try:
        # SQLite automaticky udržuje indexy, takže tato operace není nutná
        # Pro kompatibilitu s TOOZ_SERVICE_HUB vracíme úspěch
        return {"message": "Databáze je již indexovaná (SQLite)", "success": True}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při indexování: {str(e)}")


@router.post("/repair")
def repair_database(
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Oprava databáze - pro SQLite není potřeba, vrací úspěch"""
    try:
        # SQLite automaticky udržuje integritu, takže tato operace není nutná
        # Pro kompatibilitu s TOOZ_SERVICE_HUB vracíme úspěch
        return {"message": "Databáze je v pořádku (SQLite)", "success": True}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při opravě: {str(e)}")


@router.get("/db-info", response_model=DbInfoResponse)
def get_db_info(
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Informace o databázi"""
    try:
        from src.modules.vehicle_hub.database import DB_URL
        
        # Získat seznam tabulek
        inspector = inspect(db.bind)
        tables = inspector.get_table_names()
        
        # Získat cestu k databázi
        db_path = str(DB_URL).replace("sqlite:///", "")
        if os.path.exists(db_path):
            size_bytes = os.path.getsize(db_path)
            size_kb = round(size_bytes / 1024, 2)
        else:
            size_kb = None
        
        return DbInfoResponse(
            db_path=db_path,
            table_count=len(tables),
            tables=tables,
            total_size_kb=size_kb
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při získávání informací: {str(e)}")


@router.get("/settings")
def get_admin_settings(
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    """Vrátí uložená nastavení administrace."""
    try:
        settings = load_admin_settings()
        return {"settings": settings}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání nastavení: {str(e)}")


@router.put("/settings")
def update_admin_settings(
    payload: SettingsUpdatePayload,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    """Uloží dávku nastavení administrace."""
    try:
        settings = load_admin_settings()
        updated_count = 0

        for item in payload.settings:
            category = (item.category or "").strip()
            key = (item.key or "").strip()
            if not category or not key:
                continue

            settings.setdefault(category, {})
            current = settings[category].get(key, {})
            value_type = (item.value_type or current.get("value_type") or infer_setting_value_type(item.value)).strip().lower()
            value = normalize_setting_value(item.value, value_type)
            description = item.description if item.description is not None else current.get("description")

            settings[category][key] = {
                "value": value,
                "value_type": value_type,
                "description": description,
            }
            updated_count += 1

        save_admin_settings(settings)
        return {"message": f"Nastavení uloženo ({updated_count} položek)", "settings": settings}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při ukládání nastavení: {str(e)}")


@router.post("/settings/init-defaults")
def init_default_admin_settings(
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    """Inicializuje výchozí nastavení administrace."""
    try:
        defaults = get_default_admin_settings()
        save_admin_settings(defaults)
        return {"message": "Výchozí nastavení byla vytvořena", "settings": defaults}
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při inicializaci výchozích nastavení: {str(e)}")


# ============= DEVELOPER CONTROL CENTER =============

@router.get("/control-center/capabilities")
def get_control_center_capabilities(
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """Mapa dostupných modulů Developer Control Center."""
    return {
        "modules": [
            "system_health",
            "user_management",
            "user_account_actions",
            "vehicle_management",
            "license_management",
            "payment_management",
            "user_license_payment_insight",
            "user_presence",
            "database_tools",
            "backup_restore",
            "system_logs",
            "security_monitor",
            "api_monitor",
            "webhook_monitor",
            "storage_manager",
            "storage_cleanup",
            "email_monitor",
            "background_jobs",
            "background_jobs_pause_resume",
            "system_notifications",
            "command_console",
            "debug_tools",
        ]
    }


@router.get("/control-center/health")
def get_control_center_health(
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """Komplexní health panel pro Developer Control Center."""
    try:
        db_status = "ok"
        db_error = None
        try:
            db.execute(text("SELECT 1")).scalar()
        except Exception as exc:
            db_status = "error"
            db_error = str(exc)

        settings = load_admin_settings()
        comgate_settings = settings.get("comgate", {})
        smtp_settings = settings.get("email", {})

        payment_enabled = bool(comgate_settings.get("enabled", {}).get("value", False))
        payment_merchant = bool(str(comgate_settings.get("merchant", {}).get("value", "")).strip())

        smtp_host_configured = bool(str(smtp_settings.get("smtp_host", {}).get("value", SMTP_HOST or "")).strip())
        smtp_from_configured = bool(str(smtp_settings.get("smtp_from", {}).get("value", SMTP_FROM or "")).strip())
        email_status = "ok" if (smtp_host_configured and smtp_from_configured) else "warning"

        api_threshold = datetime.utcnow() - timedelta(minutes=15)
        recent_api_activity = (
            db.query(SecurityAccessLog)
            .filter(
                SecurityAccessLog.event_type == "api_activity",
                SecurityAccessLog.created_at >= api_threshold,
            )
            .count()
        )

        webhook_log_file = CONTROL_CENTER_LOG_DIR / "licensing_webhook.log"
        webhook_recent_count = len(_tail_file_lines(webhook_log_file, 200))

        data_usage = _directory_usage(DATA_DIR)
        logs_usage = _directory_usage(CONTROL_CENTER_LOG_DIR)
        backups_usage = _directory_usage(CONTROL_CENTER_BACKUP_DIR)

        db_path = get_db_file_path()
        db_file_size = 0
        if db_path and db_path.exists():
            db_file_size = db_path.stat().st_size

        return {
            "components": {
                "api": {"status": "ok"},
                "database": {"status": db_status, "error": db_error},
                "payment_gateway": {
                    "status": "ok" if (payment_enabled and payment_merchant) else "warning",
                    "enabled": payment_enabled,
                    "merchant_configured": payment_merchant,
                },
                "email_service": {
                    "status": email_status,
                    "smtp_host_configured": smtp_host_configured,
                    "smtp_from_configured": smtp_from_configured,
                },
                "background_jobs": {
                    "status": "ok",
                    "reminders_worker_enabled": os.getenv("ENABLE_REMINDER_NOTIFICATION_WORKER", "1") in {"1", "true", "True"},
                    "license_worker_enabled": os.getenv("ENABLE_LICENSE_SUBSCRIPTION_WORKER", "1") in {"1", "true", "True"},
                    "reminders_worker_paused": is_job_paused("reminders.notification.check"),
                    "license_worker_paused": is_job_paused("license.subscription.cycle"),
                },
                "api_monitor": {
                    "status": "ok",
                    "recent_api_activity_15m": recent_api_activity,
                },
                "webhook_monitor": {
                    "status": "ok" if webhook_log_file.exists() else "warning",
                    "log_file_exists": webhook_log_file.exists(),
                    "recent_events_tail_count": webhook_recent_count,
                },
            },
            "storage": {
                "database_bytes": db_file_size,
                "database_human": _format_bytes(db_file_size),
                "data_dir": data_usage,
                "logs_dir": logs_usage,
                "backups_dir": backups_usage,
            },
            "timestamp": datetime.utcnow().isoformat(),
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání health panelu: {str(e)}")


@router.get("/control-center/payments")
def get_control_center_payments(
    limit: int = 100,
    offset: int = 0,
    status: Optional[str] = None,
    user_email: Optional[str] = None,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """Payment management feed (Comgate + interní transakce)."""
    try:
        query = """
            SELECT
                tx.id,
                tx.tenant_id,
                tx.provider,
                tx.trans_id,
                tx.ref_id,
                tx.plan,
                tx.billing_period,
                tx.amount_halers,
                tx.currency,
                tx.event_type,
                tx.provider_status,
                tx.payload_json,
                tx.created_at,
                tx.updated_at,
                (
                    SELECT c.email
                    FROM customers c
                    WHERE c.tenant_id = tx.tenant_id
                    ORDER BY c.id ASC
                    LIMIT 1
                ) as account_email
            FROM license_payment_transactions tx
            WHERE 1=1
        """
        params: Dict[str, Any] = {"limit": max(1, min(limit, 500)), "offset": max(0, offset)}

        normalized_status = (status or "").strip().upper()
        if normalized_status:
            query += " AND UPPER(COALESCE(tx.provider_status, '')) = :status"
            params["status"] = normalized_status

        normalized_email = (user_email or "").strip().lower()
        if normalized_email:
            query += """
                AND EXISTS (
                    SELECT 1 FROM customers c2
                    WHERE c2.tenant_id = tx.tenant_id
                      AND lower(c2.email) = :user_email
                )
            """
            params["user_email"] = normalized_email

        query += " ORDER BY tx.created_at DESC, tx.id DESC LIMIT :limit OFFSET :offset"

        rows = db.execute(text(query), params).fetchall()
        today = datetime.utcnow().date()
        summary = {
            "all": {
                "count": 0,
                "paid_count": 0,
                "failed_count": 0,
                "refund_count": 0,
                "attention_count": 0,
                "paid_today_halers": 0,
            },
            "live": {
                "count": 0,
                "paid_count": 0,
                "failed_count": 0,
                "refund_count": 0,
                "attention_count": 0,
                "paid_today_halers": 0,
            },
            "test": {
                "count": 0,
                "paid_count": 0,
                "failed_count": 0,
                "refund_count": 0,
                "attention_count": 0,
                "paid_today_halers": 0,
            },
        }
        items = []
        for row in rows:
            provider_status = str(row[10] or "")
            event_type = str(row[9] or "")
            payload_json = row[11]
            environment = _infer_payment_environment(
                payload_json=payload_json,
                provider_status=provider_status,
                event_type=event_type,
            )
            is_successful = _is_payment_successful(provider_status, event_type)
            is_failed = _is_payment_failed(provider_status, event_type)
            refund_status = _payment_refund_status(provider_status, event_type)
            needs_attention = _payment_needs_attention(provider_status, event_type)

            created_at_value = row[12]
            created_at = to_iso_datetime(created_at_value)
            created_at_dt = created_at_value if isinstance(created_at_value, datetime) else None
            if created_at_dt is None and isinstance(created_at_value, str):
                try:
                    created_at_dt = datetime.fromisoformat(created_at_value.replace("Z", "+00:00"))
                except ValueError:
                    created_at_dt = None

            for bucket_name in ("all", environment.lower()):
                bucket = summary[bucket_name]
                bucket["count"] += 1
                if is_successful:
                    bucket["paid_count"] += 1
                if is_failed:
                    bucket["failed_count"] += 1
                if refund_status == "refunded":
                    bucket["refund_count"] += 1
                if needs_attention:
                    bucket["attention_count"] += 1
                if (
                    is_successful
                    and created_at_dt is not None
                    and created_at_dt.date() == today
                ):
                    bucket["paid_today_halers"] += int(row[7] or 0)

            items.append(
                {
                    "id": row[0],
                    "tenant_id": row[1],
                    "provider": row[2],
                    "trans_id": row[3],
                    "ref_id": row[4],
                    "plan": row[5],
                    "billing_period": row[6],
                    "amount_halers": row[7],
                    "currency": row[8],
                    "event_type": row[9],
                    "provider_status": row[10],
                    "payment_environment": environment,
                    "is_successful": is_successful,
                    "is_failed": is_failed,
                    "refund_status": refund_status,
                    "created_at": created_at,
                    "updated_at": to_iso_datetime(row[13]),
                    "account_email": row[14],
                }
            )

        return {
            "items": items,
            "count": len(items),
            "limit": params["limit"],
            "offset": params["offset"],
            "summary": summary,
            "source": {
                "table": "license_payment_transactions",
                "db_file": str(get_db_file_path() or ""),
                "live_detection": "payload_json.test / payload_json.environment",
            },
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání plateb: {str(e)}")


@router.post("/control-center/payments/resync")
def resync_control_center_payments(
    request: FastAPIRequest,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """Spustí synchronizační cyklus plateb/licencí."""
    try:
        from src.modules.vehicle_hub.routers_v1.license_status import process_license_subscription_jobs

        result = process_license_subscription_jobs(db=db)
        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="payments.resync",
            target_resource="license_subscription_jobs",
            parameters={},
            result="success",
            status_code=200,
        )
        return {"message": "Platební resync dokončen", "result": result}
    except Exception as e:
        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="payments.resync",
            target_resource="license_subscription_jobs",
            parameters={"error": str(e)},
            result="failed",
            status_code=500,
        )
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při resync plateb: {str(e)}")


@router.get("/control-center/user-insight/{user_id}")
def get_user_license_payment_insight(
    user_id: int,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """Detail licence + plateb + online status konkrétního uživatele."""
    try:
        ensure_customer_account_state_schema(db)
        user = db.query(Customer).filter(Customer.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="Uživatel nenalezen")

        license_row = db.query(License).filter(License.tenant_id == user.tenant_id).first()
        subscription_row = (
            db.query(LicenseSubscription)
            .filter(LicenseSubscription.tenant_id == user.tenant_id)
            .first()
        )

        payment_rows = (
            db.query(LicensePaymentTransaction)
            .filter(LicensePaymentTransaction.tenant_id == user.tenant_id)
            .order_by(LicensePaymentTransaction.created_at.desc())
            .limit(25)
            .all()
        )

        latest_license_admin_action = (
            db.query(DeveloperActionAuditLog)
            .filter(
                DeveloperActionAuditLog.target_resource.in_(
                    [f"user:{user_id}", f"tenant:{user.tenant_id}"]
                ),
                DeveloperActionAuditLog.action_type.in_(
                    ["license.change", "license.override", "user.create"]
                ),
            )
            .order_by(DeveloperActionAuditLog.created_at.desc(), DeveloperActionAuditLog.id.desc())
            .first()
        )

        presence_row = db.execute(
            text(
                """
                SELECT
                    (
                        SELECT MAX(s1.created_at)
                        FROM security_access_logs s1
                        WHERE lower(s1.user_email) = :user_email
                          AND s1.event_type IN ('api_activity', 'login_success', 'support_contact_submitted')
                    ) AS last_seen_at,
                    (
                        SELECT MAX(s2.created_at)
                        FROM security_access_logs s2
                        WHERE lower(s2.user_email) = :user_email
                          AND s2.event_type = 'login_success'
                    ) AS last_login_at,
                    (
                        SELECT COUNT(DISTINCT COALESCE(s3.ip_address, '') || '|' || COALESCE(s3.user_agent, ''))
                        FROM security_access_logs s3
                        WHERE lower(s3.user_email) = :user_email
                          AND s3.created_at >= :window_start
                          AND s3.event_type IN ('api_activity', 'login_success')
                    ) AS active_session_count
                """
            ),
            {
                "window_start": datetime.utcnow() - timedelta(seconds=ONLINE_WINDOW_SECONDS),
                "user_email": user.email.lower(),
            },
        ).fetchone()

        last_seen_at = to_iso_datetime(presence_row[0] if presence_row else None)
        is_online = is_online_by_last_seen(last_seen_at)

        payments_payload = []
        has_paid = False
        first_paid_at: Optional[str] = None
        latest_paid_at: Optional[str] = None
        live_payments_count = 0
        test_payments_count = 0
        live_paid_count = 0
        test_paid_count = 0
        failed_payments_count = 0
        refunded_payments_count = 0
        for tx in payment_rows:
            provider_status = str(tx.provider_status or "").strip().upper()
            event_type = str(tx.event_type or "").strip().lower()
            payment_environment = _infer_payment_environment(
                payload_json=tx.payload_json,
                provider_status=provider_status,
                event_type=event_type,
            )
            is_successful = _is_payment_successful(provider_status, event_type)
            is_failed = _is_payment_failed(provider_status, event_type)
            refund_status = _payment_refund_status(provider_status, event_type)
            is_counted_paid = _payment_counts_as_paid(
                environment=payment_environment,
                is_successful=is_successful,
            )

            if payment_environment == "LIVE":
                live_payments_count += 1
            else:
                test_payments_count += 1
            if is_successful:
                if payment_environment == "LIVE":
                    live_paid_count += 1
                else:
                    test_paid_count += 1
            if is_failed:
                failed_payments_count += 1
            if refund_status == "refunded":
                refunded_payments_count += 1

            if is_counted_paid:
                has_paid = True
                tx_created = to_iso_datetime(tx.created_at)
                if tx_created:
                    latest_paid_at = latest_paid_at or tx_created
                    first_paid_at = tx_created

            payments_payload.append(
                {
                    "id": tx.id,
                    "provider": tx.provider,
                    "trans_id": tx.trans_id,
                    "ref_id": tx.ref_id,
                    "plan": tx.plan,
                    "billing_period": tx.billing_period,
                    "amount_halers": tx.amount_halers,
                    "currency": tx.currency,
                    "event_type": tx.event_type,
                    "provider_status": tx.provider_status,
                    "payment_environment": payment_environment,
                    "is_successful": is_successful,
                    "is_failed": is_failed,
                    "payment_timestamp": to_iso_datetime(tx.created_at),
                    "refund_status": refund_status,
                }
            )

        source_of_activation = "manual"
        if has_paid:
            source_of_activation = "payment"
        if latest_license_admin_action:
            action = str(latest_license_admin_action.action_type or "").strip().lower()
            if action in {"license.change", "license.override"}:
                source_of_activation = "developer_override"
            elif action == "user.create":
                source_of_activation = "trial_or_manual"

        activation_date = to_iso_datetime(license_row.valid_from if license_row else None)
        expiration_date = to_iso_datetime(license_row.valid_to if license_row else None)
        if not expiration_date:
            expiration_date = to_iso_datetime(subscription_row.current_period_end if subscription_row else None)

        next_renewal_date = to_iso_datetime(subscription_row.next_charge_at if subscription_row else None)
        purchase_date = first_paid_at or activation_date

        return {
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "role": user.role,
                "tenant_id": user.tenant_id,
                "is_disabled": bool(getattr(user, "is_disabled", False)),
                "is_deleted": bool(getattr(user, "is_deleted", False)),
                "session_version": customer_session_version(user),
            },
            "license": {
                "current_plan": license_row.plan if license_row else "free",
                "status": license_row.status if license_row else "active",
                "purchase_date": purchase_date,
                "activation_date": activation_date,
                "expiration_date": expiration_date,
                "next_renewal_date": next_renewal_date,
                "source_of_activation": source_of_activation,
                "valid_from": activation_date,
                "valid_to": expiration_date,
                "vehicles_limit": license_row.vehicles_limit if license_row else None,
            },
            "subscription": {
                "status": subscription_row.status if subscription_row else "legacy_manual",
                "provider": subscription_row.provider if subscription_row else None,
                "billing_period": subscription_row.billing_period if subscription_row else None,
                "plan_current": subscription_row.plan_current if subscription_row else None,
                "current_period_start": to_iso_datetime(subscription_row.current_period_start if subscription_row else None),
                "current_period_end": to_iso_datetime(subscription_row.current_period_end if subscription_row else None),
                "next_charge_at": to_iso_datetime(subscription_row.next_charge_at if subscription_row else None),
                "last_payment_at": to_iso_datetime(subscription_row.last_payment_at if subscription_row else None),
            },
            "presence": {
                "online_status": "ONLINE" if is_online else "OFFLINE",
                "last_seen_at": last_seen_at,
                "last_login_at": to_iso_datetime(presence_row[1] if presence_row else None),
                "active_session_count": int(presence_row[2] or 0) if presence_row else 0,
            },
            "payments_summary": {
                "has_paid": has_paid,
                "first_paid_at": first_paid_at,
                "last_paid_at": latest_paid_at,
                "provider": subscription_row.provider if subscription_row else None,
                "count": len(payments_payload),
                "count_live": live_payments_count,
                "count_test": test_payments_count,
                "live_paid_count": live_paid_count,
                "test_paid_count": test_paid_count,
                "failed_count": failed_payments_count,
                "refund_count": refunded_payments_count,
                "has_live_paid": live_paid_count > 0,
                "has_test_paid": test_paid_count > 0,
                "paid_counting_mode": "live_only" if not COUNT_TEST_PAYMENTS_AS_PAID else "live_and_test",
            },
            "payments": payments_payload,
        }
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání user insight: {str(e)}")


def _load_user_for_control_action(db: Session, user_id: int) -> Customer:
    ensure_customer_account_state_schema(db)
    user = db.query(Customer).filter(Customer.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Uživatel nenalezen")
    return user


@router.post("/control-center/users/{user_id}/disable")
def disable_user_account(
    user_id: int,
    payload: UserStateActionRequest,
    request: FastAPIRequest,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    user = _load_user_for_control_action(db, user_id)
    if customer_is_deleted(user):
        raise HTTPException(status_code=400, detail="Účet je již smazaný")

    user.is_disabled = True
    user.disabled_at = datetime.utcnow()
    increment_customer_session_version(user)
    db.commit()

    log_developer_action(
        db,
        developer_email=email,
        request=request,
        action_type="user.disable",
        target_resource=f"user:{user_id}",
        parameters={"reason": payload.reason},
        result="success",
        status_code=200,
    )
    return {
        "message": f"Účet {user.email} byl pozastaven",
        "user_id": user.id,
        "is_disabled": True,
        "session_version": customer_session_version(user),
    }


@router.post("/control-center/users/{user_id}/enable")
def enable_user_account(
    user_id: int,
    payload: UserStateActionRequest,
    request: FastAPIRequest,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    user = _load_user_for_control_action(db, user_id)
    if customer_is_deleted(user):
        raise HTTPException(status_code=400, detail="Smazaný účet nelze znovu aktivovat")

    user.is_disabled = False
    user.disabled_at = None
    increment_customer_session_version(user)
    db.commit()

    log_developer_action(
        db,
        developer_email=email,
        request=request,
        action_type="user.enable",
        target_resource=f"user:{user_id}",
        parameters={"reason": payload.reason},
        result="success",
        status_code=200,
    )
    return {
        "message": f"Účet {user.email} byl aktivován",
        "user_id": user.id,
        "is_disabled": False,
        "session_version": customer_session_version(user),
    }


@router.post("/control-center/users/{user_id}/force-logout")
def force_logout_user_account(
    user_id: int,
    payload: UserStateActionRequest,
    request: FastAPIRequest,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    user = _load_user_for_control_action(db, user_id)
    increment_customer_session_version(user)
    db.commit()

    log_developer_action(
        db,
        developer_email=email,
        request=request,
        action_type="user.force_logout",
        target_resource=f"user:{user_id}",
        parameters={"reason": payload.reason},
        result="success",
        status_code=200,
    )
    return {
        "message": f"Aktivní relace uživatele {user.email} byly ukončeny",
        "user_id": user.id,
        "session_version": customer_session_version(user),
    }


@router.post("/control-center/users/{user_id}/reset-password")
def reset_user_password_admin(
    user_id: int,
    payload: UserPasswordResetRequest,
    request: FastAPIRequest,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    user = _load_user_for_control_action(db, user_id)
    if customer_is_deleted(user):
        raise HTTPException(status_code=400, detail="Smazanému účtu nelze resetovat heslo")

    generated = False
    new_password = (payload.new_password or "").strip()
    if payload.generate_random or not new_password:
        new_password = generate_temporary_password()
        generated = True

    try:
        user.password_hash = hash_password(new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    increment_customer_session_version(user)
    db.commit()

    log_developer_action(
        db,
        developer_email=email,
        request=request,
        action_type="user.password_reset",
        target_resource=f"user:{user_id}",
        parameters={"generated_random": generated, "reason": payload.reason},
        result="success",
        status_code=200,
    )
    return {
        "message": f"Heslo uživatele {user.email} bylo resetováno",
        "user_id": user.id,
        "temporary_password": new_password if generated else None,
        "generated_random": generated,
        "session_version": customer_session_version(user),
    }


@router.post("/control-center/users/{user_id}/license")
def update_user_license_admin(
    user_id: int,
    payload: UserLicenseUpdateRequest,
    request: FastAPIRequest,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    user = _load_user_for_control_action(db, user_id)
    plan = normalize_license_plan(payload.plan)
    status = normalize_license_status(payload.status)
    source = (payload.source or "").strip().lower() or "developer_override"

    if plan and (not LICENSE_MANAGEMENT_AVAILABLE or not upgrade_license_plan):
        raise HTTPException(status_code=503, detail="Správa licencí není momentálně dostupná")

    ensure_default_license_for_tenant(db, user.tenant_id)
    license_row = db.query(License).filter(License.tenant_id == user.tenant_id).first()
    if not license_row:
        raise HTTPException(status_code=500, detail="Licence tenantu nebyla nalezena")

    if plan:
        upgrade_license_plan(db, user.tenant_id, plan)
        db.refresh(license_row)

    if status:
        license_row.status = status
    if payload.valid_to is not None:
        license_row.valid_to = payload.valid_to
    db.commit()
    db.refresh(license_row)

    log_developer_action(
        db,
        developer_email=email,
        request=request,
        action_type="license.override",
        target_resource=f"user:{user_id}",
        parameters={
            "tenant_id": user.tenant_id,
            "plan": plan,
            "status": status,
            "valid_to": to_iso_datetime(payload.valid_to),
            "source": source,
            "reason": payload.reason,
        },
        result="success",
        status_code=200,
    )
    return {
        "message": "Licence byla aktualizována",
        "user_id": user.id,
        "tenant_id": user.tenant_id,
        "license": {
            "plan": license_row.plan,
            "status": license_row.status,
            "valid_from": to_iso_datetime(license_row.valid_from),
            "valid_to": to_iso_datetime(license_row.valid_to),
            "vehicles_limit": license_row.vehicles_limit,
            "source": source,
        },
    }


@router.get("/control-center/presence")
def get_users_presence(
    limit: int = 200,
    offset: int = 0,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """User online/offline monitoring (odvozené ze security logů)."""
    try:
        ensure_customer_account_state_schema(db)
        window_start = datetime.utcnow() - timedelta(seconds=ONLINE_WINDOW_SECONDS)
        rows = db.execute(
            text(
                """
                SELECT
                    c.id,
                    c.email,
                    c.name,
                    c.role,
                    c.tenant_id,
                    (
                        SELECT MAX(s1.created_at)
                        FROM security_access_logs s1
                        WHERE lower(s1.user_email) = lower(c.email)
                          AND s1.event_type IN ('api_activity', 'login_success', 'support_contact_submitted')
                    ) AS last_seen_at,
                    (
                        SELECT MAX(s2.created_at)
                        FROM security_access_logs s2
                        WHERE lower(s2.user_email) = lower(c.email)
                          AND s2.event_type = 'login_success'
                    ) AS last_login_at,
                    (
                        SELECT COUNT(DISTINCT COALESCE(s3.ip_address, '') || '|' || COALESCE(s3.user_agent, ''))
                        FROM security_access_logs s3
                        WHERE lower(s3.user_email) = lower(c.email)
                          AND s3.created_at >= :window_start
                          AND s3.event_type IN ('api_activity', 'login_success')
                    ) AS active_session_count
                FROM customers c
                WHERE COALESCE(c.is_deleted, 0) = 0
                ORDER BY c.created_at DESC
                LIMIT :limit OFFSET :offset
                """
            ),
            {
                "window_start": window_start,
                "limit": max(1, min(limit, 500)),
                "offset": max(0, offset),
            },
        ).fetchall()

        items = []
        for row in rows:
            last_seen_at = to_iso_datetime(row[5])
            is_online = is_online_by_last_seen(last_seen_at)
            items.append(
                {
                    "user_id": row[0],
                    "email": row[1],
                    "name": row[2],
                    "role": row[3],
                    "tenant_id": row[4],
                    "online_status": "ONLINE" if is_online else "OFFLINE",
                    "last_seen_at": last_seen_at,
                    "last_login_at": to_iso_datetime(row[6]),
                    "active_session_count": int(row[7] or 0),
                }
            )

        return {
            "items": items,
            "online_window_seconds": ONLINE_WINDOW_SECONDS,
            "count": len(items),
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání online/offline stavu: {str(e)}")


@router.get("/control-center/security-monitor")
def get_security_monitor(
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """Bezpečnostní monitor: failed loginy, blokace IP, rate-limit události."""
    try:
        since_24h = datetime.utcnow() - timedelta(hours=24)
        since_7d = datetime.utcnow() - timedelta(days=7)

        failed_24h = (
            db.query(SecurityAccessLog)
            .filter(
                SecurityAccessLog.event_type == "login_failed",
                SecurityAccessLog.created_at >= since_24h,
            )
            .count()
        )

        rate_limited_24h = (
            db.query(SecurityAccessLog)
            .filter(
                SecurityAccessLog.event_type == "login_rate_limited",
                SecurityAccessLog.created_at >= since_24h,
            )
            .count()
        )

        suspicious_rows = db.execute(
            text(
                """
                SELECT
                    ip_address,
                    COUNT(*) as failed_count
                FROM security_access_logs
                WHERE event_type = 'login_failed'
                  AND created_at >= :since_24h
                  AND ip_address IS NOT NULL
                GROUP BY ip_address
                ORDER BY failed_count DESC
                LIMIT 20
                """
            ),
            {"since_24h": since_24h},
        ).fetchall()

        blocked_ips = (
            db.query(SecurityBlockedIp)
            .order_by(SecurityBlockedIp.blocked_at.desc())
            .limit(200)
            .all()
        )

        latest_events = (
            db.query(SecurityAccessLog)
            .filter(SecurityAccessLog.created_at >= since_7d)
            .order_by(SecurityAccessLog.created_at.desc())
            .limit(120)
            .all()
        )

        return {
            "summary": {
                "failed_logins_24h": failed_24h,
                "rate_limited_24h": rate_limited_24h,
                "blocked_ips_active": sum(1 for item in blocked_ips if item.is_active),
            },
            "top_failed_ips": [
                {"ip_address": row[0], "failed_count": int(row[1] or 0)}
                for row in suspicious_rows
            ],
            "blocked_ips": [
                {
                    "ip_address": item.ip_address,
                    "reason": item.reason,
                    "is_active": bool(item.is_active),
                    "blocked_at": to_iso_datetime(item.blocked_at),
                    "expires_at": to_iso_datetime(item.expires_at),
                    "blocked_by_email": item.blocked_by_email,
                    "unblocked_at": to_iso_datetime(item.unblocked_at),
                    "unblocked_by_email": item.unblocked_by_email,
                }
                for item in blocked_ips
            ],
            "latest_events": [
                {
                    "id": item.id,
                    "event_type": item.event_type,
                    "user_email": item.user_email,
                    "ip_address": item.ip_address,
                    "endpoint": item.endpoint,
                    "created_at": to_iso_datetime(item.created_at),
                }
                for item in latest_events
            ],
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání security monitoru: {str(e)}")


@router.post("/control-center/security/block-ip")
def block_ip_address(
    payload: SecurityBlockIpRequest,
    request: FastAPIRequest,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """Manuální blokace IP adresy (anti-abuse zásah)."""
    ip_text = str(payload.ip_address or "").strip()
    try:
        normalized_ip = str(ipaddress.ip_address(ip_text))
    except ValueError:
        raise HTTPException(status_code=400, detail="Neplatný formát IP adresy")

    actor = get_customer_by_email(db, email)
    expires_at = None
    if payload.expires_in_minutes and payload.expires_in_minutes > 0:
        expires_at = datetime.utcnow() + timedelta(minutes=min(payload.expires_in_minutes, 60 * 24 * 30))

    try:
        entry = db.query(SecurityBlockedIp).filter(SecurityBlockedIp.ip_address == normalized_ip).first()
        if not entry:
            entry = SecurityBlockedIp(
                ip_address=normalized_ip,
                reason=(payload.reason or "").strip() or None,
                blocked_by_customer_id=actor.id if actor else None,
                blocked_by_email=email.lower(),
                blocked_at=datetime.utcnow(),
                expires_at=expires_at,
                is_active=True,
            )
            db.add(entry)
        else:
            entry.reason = (payload.reason or "").strip() or entry.reason
            entry.blocked_by_customer_id = actor.id if actor else entry.blocked_by_customer_id
            entry.blocked_by_email = email.lower()
            entry.blocked_at = datetime.utcnow()
            entry.expires_at = expires_at
            entry.is_active = True
            entry.unblocked_at = None
            entry.unblocked_by_customer_id = None
            entry.unblocked_by_email = None

        db.commit()
        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="security.block_ip",
            target_resource=f"ip:{normalized_ip}",
            parameters={"reason": payload.reason, "expires_at": to_iso_datetime(expires_at)},
            result="success",
            status_code=200,
        )
        return {
            "message": f"IP adresa {normalized_ip} byla zablokována",
            "ip_address": normalized_ip,
            "expires_at": to_iso_datetime(expires_at),
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="security.block_ip",
            target_resource=f"ip:{normalized_ip}",
            parameters={"error": str(e)},
            result="failed",
            status_code=500,
        )
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při blokaci IP: {str(e)}")


@router.post("/control-center/security/unblock-ip")
def unblock_ip_address(
    payload: SecurityUnblockIpRequest,
    request: FastAPIRequest,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """Zrušení blokace IP adresy."""
    ip_text = str(payload.ip_address or "").strip()
    try:
        normalized_ip = str(ipaddress.ip_address(ip_text))
    except ValueError:
        raise HTTPException(status_code=400, detail="Neplatný formát IP adresy")

    actor = get_customer_by_email(db, email)
    try:
        entry = (
            db.query(SecurityBlockedIp)
            .filter(
                SecurityBlockedIp.ip_address == normalized_ip,
                SecurityBlockedIp.is_active.is_(True),
            )
            .first()
        )
        if not entry:
            raise HTTPException(status_code=404, detail="Aktivní blokace pro tuto IP neexistuje")

        entry.is_active = False
        entry.unblocked_at = datetime.utcnow()
        entry.unblocked_by_customer_id = actor.id if actor else None
        entry.unblocked_by_email = email.lower()
        if payload.reason:
            existing_reason = (entry.reason or "").strip()
            suffix = f" | unblock: {payload.reason.strip()}"
            entry.reason = f"{existing_reason}{suffix}" if existing_reason else f"unblock: {payload.reason.strip()}"

        db.commit()
        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="security.unblock_ip",
            target_resource=f"ip:{normalized_ip}",
            parameters={"reason": payload.reason},
            result="success",
            status_code=200,
        )
        return {"message": f"IP adresa {normalized_ip} byla odblokována", "ip_address": normalized_ip}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="security.unblock_ip",
            target_resource=f"ip:{normalized_ip}",
            parameters={"error": str(e)},
            result="failed",
            status_code=500,
        )
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při odblokování IP: {str(e)}")


@router.get("/control-center/backups")
def list_control_center_backups(
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """Seznam dostupných backup snapshotů."""
    return {"items": _list_backup_entries()}


@router.post("/control-center/backups/create")
def create_control_center_backup(
    payload: BackupCreateRequest,
    request: FastAPIRequest,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """Vytvoří snapshot databáze (+ volitelně data dir) pro restore operace."""
    db_file = get_db_file_path()
    if not db_file or not db_file.exists():
        raise HTTPException(status_code=400, detail="Aktuální databáze není dostupná pro backup")

    backup_id = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_dir = CONTROL_CENTER_BACKUP_DIR / backup_id
    backup_dir.mkdir(parents=True, exist_ok=True)

    try:
        backup_db = backup_dir / "vehicles.db"
        _create_sqlite_backup(db_file, backup_db)

        copied_data = []
        if payload.include_data_dir and DATA_DIR.exists():
            data_snapshot_root = backup_dir / "data"
            data_snapshot_root.mkdir(parents=True, exist_ok=True)
            for name in [
                "uploads",
                "vehicle_photos",
                "service_workspace_docs",
                "service_record_attachments",
                "images",
                "pdfs",
            ]:
                src = DATA_DIR / name
                if src.exists():
                    dst = data_snapshot_root / name
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                    copied_data.append(name)

        manifest = {
            "backup_id": backup_id,
            "created_at": datetime.utcnow().isoformat(),
            "created_by": email.lower(),
            "db_file": str(backup_db.name),
            "db_size_bytes": backup_db.stat().st_size if backup_db.exists() else 0,
            "include_data_dir": bool(payload.include_data_dir),
            "data_dirs": copied_data,
        }
        (backup_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="backup.create",
            target_resource=f"backup:{backup_id}",
            parameters=manifest,
            result="success",
            status_code=200,
        )
        return {"message": "Backup byl vytvořen", "backup": manifest}
    except Exception as e:
        shutil.rmtree(backup_dir, ignore_errors=True)
        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="backup.create",
            target_resource=f"backup:{backup_id}",
            parameters={"error": str(e)},
            result="failed",
            status_code=500,
        )
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při vytváření backupu: {str(e)}")


@router.get("/control-center/backups/{backup_id}/download")
def download_control_center_backup(
    backup_id: str,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """Download ZIP snapshotu."""
    backup_dir = CONTROL_CENTER_BACKUP_DIR / backup_id
    if not backup_dir.exists() or not backup_dir.is_dir():
        raise HTTPException(status_code=404, detail="Backup nenalezen")

    zip_path = backup_dir / f"{backup_id}.zip"
    if not zip_path.exists():
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for file_path in backup_dir.rglob("*"):
                if file_path == zip_path:
                    continue
                if file_path.is_file():
                    archive.write(file_path, arcname=str(file_path.relative_to(backup_dir)))

    return FileResponse(
        path=str(zip_path),
        media_type="application/zip",
        filename=f"sprava-vozidel-backup-{backup_id}.zip",
    )


@router.post("/control-center/backups/restore")
def restore_control_center_backup(
    payload: BackupRestoreRequest,
    request: FastAPIRequest,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """
    Restore operace:
    - full: kompletní DB snapshot
    - user: částečný restore dat uživatele
    - vehicle: částečný restore dat vozidla
    """
    if (payload.confirm_text or "").strip().upper() != CONTROL_CENTER_DANGEROUS_CONFIRM:
        raise HTTPException(
            status_code=400,
            detail=f"Pro restore je nutné potvrzení textem '{CONTROL_CENTER_DANGEROUS_CONFIRM}'",
        )

    normalized_scope = (payload.scope or "").strip().lower()
    if normalized_scope not in {"full", "user", "vehicle"}:
        raise HTTPException(status_code=400, detail="scope musí být full | user | vehicle")

    backup_dir = CONTROL_CENTER_BACKUP_DIR / payload.backup_id
    backup_db_file = backup_dir / "vehicles.db"
    target_db_file = get_db_file_path()
    if not backup_db_file.exists():
        raise HTTPException(status_code=404, detail="DB snapshot pro zvolený backup nebyl nalezen")
    if not target_db_file or not target_db_file.exists():
        raise HTTPException(status_code=400, detail="Cílová databáze není dostupná")

    action_target = f"backup:{payload.backup_id}:{normalized_scope}"
    try:
        pre_restore_id = datetime.utcnow().strftime("pre_restore_%Y%m%d_%H%M%S")
        pre_restore_dir = CONTROL_CENTER_BACKUP_DIR / pre_restore_id
        pre_restore_dir.mkdir(parents=True, exist_ok=True)
        _create_sqlite_backup(target_db_file, pre_restore_dir / "vehicles.db")
        (pre_restore_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "backup_id": pre_restore_id,
                    "created_at": datetime.utcnow().isoformat(),
                    "created_by": email.lower(),
                    "reason": "automatic pre-restore snapshot",
                    "source_restore": payload.backup_id,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        restored_counts: Dict[str, int] = {}
        if normalized_scope == "full":
            _restore_sqlite_backup(backup_db_file, target_db_file)
            restored_counts = {"database": 1}

            data_snapshot_dir = backup_dir / "data"
            if data_snapshot_dir.exists():
                for subdir in data_snapshot_dir.iterdir():
                    if not subdir.is_dir():
                        continue
                    target_subdir = DATA_DIR / subdir.name
                    if target_subdir.exists():
                        shutil.rmtree(target_subdir, ignore_errors=True)
                    shutil.copytree(subdir, target_subdir, dirs_exist_ok=True)
        elif normalized_scope == "user":
            if not payload.user_id:
                raise HTTPException(status_code=400, detail="Pro scope=user je povinné user_id")
            restored_counts = _restore_user_scope_from_backup(
                backup_db_file=backup_db_file,
                target_db_file=target_db_file,
                user_id=int(payload.user_id),
            )
        else:
            if not payload.vehicle_id:
                raise HTTPException(status_code=400, detail="Pro scope=vehicle je povinné vehicle_id")
            restored_counts = _restore_vehicle_scope_from_backup(
                backup_db_file=backup_db_file,
                target_db_file=target_db_file,
                vehicle_id=int(payload.vehicle_id),
            )

        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="backup.restore",
            target_resource=action_target,
            parameters={
                "scope": normalized_scope,
                "backup_id": payload.backup_id,
                "user_id": payload.user_id,
                "vehicle_id": payload.vehicle_id,
                "restored_counts": restored_counts,
            },
            result="success",
            status_code=200,
        )
        return {
            "message": "Restore dokončen",
            "scope": normalized_scope,
            "backup_id": payload.backup_id,
            "pre_restore_backup_id": pre_restore_id,
            "restored_counts": restored_counts,
        }
    except HTTPException:
        raise
    except Exception as e:
        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="backup.restore",
            target_resource=action_target,
            parameters={"error": str(e)},
            result="failed",
            status_code=500,
        )
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při restore: {str(e)}")


@router.get("/control-center/system-logs")
def get_control_center_system_logs(
    lines: int = 120,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """Tail systémových logů."""
    safe_lines = max(20, min(lines, 500))
    log_files = [
        CONTROL_CENTER_LOG_DIR / "server.log",
        CONTROL_CENTER_LOG_DIR / "uvicorn.log",
        CONTROL_CENTER_LOG_DIR / "volume_backup.log",
        CONTROL_CENTER_LOG_DIR / "licensing_webhook.log",
    ]
    payload = []
    for file_path in log_files:
        payload.append(
            {
                "file": str(file_path),
                "exists": file_path.exists(),
                "tail": _tail_file_lines(file_path, safe_lines),
            }
        )
    return {"logs": payload, "lines": safe_lines}


@router.get("/control-center/webhook-monitor")
def get_control_center_webhook_monitor(
    lines: int = 200,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """Monitor webhook událostí (licensing webhook log)."""
    log_file = CONTROL_CENTER_LOG_DIR / "licensing_webhook.log"
    tail = _tail_file_lines(log_file, max(20, min(lines, 1000)))

    success_count = 0
    failed_count = 0
    for line in tail:
        normalized = line.lower()
        if "success=true" in normalized:
            success_count += 1
        if "success=false" in normalized or "error=" in normalized:
            failed_count += 1

    return {
        "file": str(log_file),
        "exists": log_file.exists(),
        "tail_count": len(tail),
        "success_count": success_count,
        "failed_count": failed_count,
        "tail": tail,
    }


@router.get("/control-center/storage")
def get_control_center_storage(
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """Storage manager přehled."""
    db_file = get_db_file_path()
    db_size = db_file.stat().st_size if db_file and db_file.exists() else 0
    return {
        "database": {
            "path": str(db_file) if db_file else None,
            "exists": bool(db_file and db_file.exists()),
            "size_bytes": db_size,
            "size_human": _format_bytes(db_size),
        },
        "directories": {
            "data": _directory_usage(DATA_DIR),
            "logs": _directory_usage(CONTROL_CENTER_LOG_DIR),
            "backups": _directory_usage(CONTROL_CENTER_BACKUP_DIR),
        },
    }


@router.get("/control-center/storage/cleanup-preview")
def get_control_center_storage_cleanup_preview(
    logs_days: int = 30,
    backups_days: int = 30,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    old_logs = _collect_old_log_files(logs_days)
    old_backups = _collect_old_backup_dirs(backups_days)
    logs_bytes = sum(path.stat().st_size for path in old_logs if path.exists())
    backups_bytes = sum(
        sum(file_path.stat().st_size for file_path in backup_dir.rglob("*") if file_path.is_file())
        for backup_dir in old_backups
        if backup_dir.exists()
    )
    return {
        "confirm_text_required": CONTROL_CENTER_CLEANUP_CONFIRM,
        "logs_days": max(1, logs_days),
        "backups_days": max(1, backups_days),
        "old_logs_count": len(old_logs),
        "old_logs_bytes": logs_bytes,
        "old_logs_human": _format_bytes(logs_bytes),
        "old_backups_count": len(old_backups),
        "old_backups_bytes": backups_bytes,
        "old_backups_human": _format_bytes(backups_bytes),
        "sample_old_logs": [str(path) for path in old_logs[:20]],
        "sample_old_backups": [str(path) for path in old_backups[:20]],
    }


@router.post("/control-center/storage/cleanup")
def run_control_center_storage_cleanup(
    payload: StorageCleanupRequest,
    request: FastAPIRequest,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    if (payload.confirm_text or "").strip().upper() != CONTROL_CENTER_CLEANUP_CONFIRM:
        raise HTTPException(
            status_code=400,
            detail=f"Pro cleanup je nutné potvrzení textem '{CONTROL_CENTER_CLEANUP_CONFIRM}'",
        )

    logs_days = max(1, int(payload.delete_old_logs_days or 30))
    backups_days = max(1, int(payload.delete_old_backups_days or 30))
    old_logs = _collect_old_log_files(logs_days)
    old_backups = _collect_old_backup_dirs(backups_days)

    deleted_logs = 0
    deleted_backups = 0
    reclaimed_bytes = 0
    errors: List[str] = []

    for file_path in old_logs:
        try:
            if file_path.exists():
                reclaimed_bytes += file_path.stat().st_size
                file_path.unlink()
                deleted_logs += 1
        except Exception as exc:
            errors.append(f"log:{file_path} -> {exc}")

    for backup_dir in old_backups:
        try:
            if backup_dir.exists():
                dir_bytes = sum(file_path.stat().st_size for file_path in backup_dir.rglob("*") if file_path.is_file())
                reclaimed_bytes += dir_bytes
                shutil.rmtree(backup_dir, ignore_errors=False)
                deleted_backups += 1
        except Exception as exc:
            errors.append(f"backup:{backup_dir} -> {exc}")

    result = {
        "deleted_logs": deleted_logs,
        "deleted_backups": deleted_backups,
        "reclaimed_bytes": reclaimed_bytes,
        "reclaimed_human": _format_bytes(reclaimed_bytes),
        "errors": errors,
    }
    log_developer_action(
        db,
        developer_email=email,
        request=request,
        action_type="storage.cleanup",
        target_resource="storage",
        parameters={"logs_days": logs_days, "backups_days": backups_days, "result": result},
        result="success" if not errors else "partial",
        status_code=200,
    )
    return {
        "message": "Storage cleanup dokončen",
        **result,
    }


@router.get("/control-center/api-monitor")
def get_control_center_api_monitor(
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """API monitor: nejaktivnější endpointy za 24h."""
    since_24h = datetime.utcnow() - timedelta(hours=24)
    rows = db.execute(
        text(
            """
            SELECT
                COALESCE(endpoint, 'unknown') AS endpoint,
                COUNT(*) AS hits
            FROM security_access_logs
            WHERE event_type = 'api_activity'
              AND created_at >= :since_24h
            GROUP BY endpoint
            ORDER BY hits DESC
            LIMIT 50
            """
        ),
        {"since_24h": since_24h},
    ).fetchall()
    return {
        "items": [{"endpoint": row[0], "hits": int(row[1] or 0)} for row in rows],
        "window_hours": 24,
    }


@router.get("/control-center/email-monitor")
def get_control_center_email_monitor(
    limit: int = 120,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """Email monitor (odeslané/failed notifikace)."""
    safe_limit = max(20, min(limit, 500))
    since_24h = datetime.utcnow() - timedelta(hours=24)
    sent_24h = (
        db.query(EmailNotificationLog)
        .filter(
            EmailNotificationLog.sent_at >= since_24h,
            EmailNotificationLog.status == "sent",
        )
        .count()
    )
    failed_24h = (
        db.query(EmailNotificationLog)
        .filter(
            EmailNotificationLog.sent_at >= since_24h,
            EmailNotificationLog.status == "failed",
        )
        .count()
    )
    rows = (
        db.query(EmailNotificationLog)
        .order_by(EmailNotificationLog.sent_at.desc())
        .limit(safe_limit)
        .all()
    )
    return {
        "summary": {
            "sent_24h": sent_24h,
            "failed_24h": failed_24h,
        },
        "items": [
            {
                "id": row.id,
                "tenant_id": row.tenant_id,
                "customer_id": row.customer_id,
                "email": row.email,
                "subject": row.subject,
                "notification_type": row.notification_type,
                "entity_id": row.entity_id,
                "status": row.status,
                "error_message": row.error_message,
                "sent_at": to_iso_datetime(row.sent_at),
            }
            for row in rows
        ],
    }


@router.get("/control-center/debug-tools")
def get_control_center_debug_tools(
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """Debug tools snapshot (read-only diagnostika runtime)."""
    return {
        "runtime": {
            "environment": ENVIRONMENT,
            "host": HOST,
            "port": PORT,
            "jwt_expire_minutes": JWT_EXPIRE_MINUTES,
            "allowed_origins": ALLOWED_ORIGINS,
        },
        "tables": inspect(db.bind).get_table_names(),
        "settings_file": str(ADMIN_SETTINGS_FILE),
        "settings_file_exists": ADMIN_SETTINGS_FILE.exists(),
    }


@router.get("/control-center/jobs")
def get_control_center_jobs(
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """Background job control status."""
    reminder_env_enabled = os.getenv("ENABLE_REMINDER_NOTIFICATION_WORKER", "1") in {"1", "true", "True"}
    license_env_enabled = os.getenv("ENABLE_LICENSE_SUBSCRIPTION_WORKER", "1") in {"1", "true", "True"}

    jobs = []
    for name, env_enabled, interval in [
        (
            "license.subscription.cycle",
            license_env_enabled,
            max(300, int(os.getenv("LICENSE_SUBSCRIPTION_WORKER_INTERVAL_SEC", "3600"))),
        ),
        (
            "reminders.notification.check",
            reminder_env_enabled,
            max(60, int(os.getenv("REMINDER_NOTIFICATION_WORKER_INTERVAL_SEC", "300"))),
        ),
    ]:
        paused = is_job_paused(name)
        pause_meta = get_job_pause_metadata(name)
        jobs.append(
            {
                "name": name,
                "env_enabled": env_enabled,
                "is_paused": paused,
                "state": "paused" if paused else ("running" if env_enabled else "disabled"),
                "effective_enabled": bool(env_enabled and not paused),
                "interval_seconds": interval,
                "paused_at": pause_meta.get("paused_at"),
                "paused_by": pause_meta.get("paused_by"),
                "pause_reason": pause_meta.get("reason"),
            }
        )

    return {
        "jobs": jobs
    }


@router.post("/control-center/jobs/run")
def run_control_center_job(
    payload: Dict[str, Any],
    request: FastAPIRequest,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """Manuální spuštění interního jobu."""
    job_name = resolve_job_name(str(payload.get("job_name") or ""))
    force_run = bool(payload.get("force"))

    try:
        if is_job_paused(job_name) and not force_run:
            raise HTTPException(
                status_code=409,
                detail=f"Job '{job_name}' je pozastaven. Použijte force=true nebo jej obnovte.",
            )

        if job_name == "license.subscription.cycle":
            from src.modules.vehicle_hub.routers_v1.license_status import process_license_subscription_jobs

            result = process_license_subscription_jobs(db=db)
        elif job_name == "reminders.notification.check":
            from src.modules.vehicle_hub.routers_v1.reminders import check_and_send_reminder_notifications

            result = check_and_send_reminder_notifications(db=db)
        else:
            raise HTTPException(status_code=400, detail="Nepodporovaný job_name")

        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="jobs.run",
            target_resource=job_name,
            parameters={},
            result="success",
            status_code=200,
        )
        return {"message": f"Job '{job_name}' dokončen", "result": result}
    except HTTPException:
        raise
    except Exception as e:
        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="jobs.run",
            target_resource=job_name,
            parameters={"error": str(e)},
            result="failed",
            status_code=500,
        )
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při spuštění jobu: {str(e)}")


@router.post("/control-center/jobs/pause")
def pause_control_center_job(
    payload: JobStateRequest,
    request: FastAPIRequest,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    job_name = resolve_job_name(payload.job_name)
    set_job_paused(job_name, True, actor_email=email, reason=payload.reason)
    log_developer_action(
        db,
        developer_email=email,
        request=request,
        action_type="jobs.pause",
        target_resource=job_name,
        parameters={"reason": payload.reason},
        result="success",
        status_code=200,
    )
    return {"message": f"Job '{job_name}' byl pozastaven", "job_name": job_name, "paused": True}


@router.post("/control-center/jobs/resume")
def resume_control_center_job(
    payload: JobStateRequest,
    request: FastAPIRequest,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    job_name = resolve_job_name(payload.job_name)
    set_job_paused(job_name, False, actor_email=email, reason=payload.reason)
    log_developer_action(
        db,
        developer_email=email,
        request=request,
        action_type="jobs.resume",
        target_resource=job_name,
        parameters={"reason": payload.reason},
        result="success",
        status_code=200,
    )
    return {"message": f"Job '{job_name}' byl obnoven", "job_name": job_name, "paused": False}


@router.get("/control-center/notifications")
def list_control_center_notifications(
    limit: int = 100,
    offset: int = 0,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(SystemNotification)
        .order_by(SystemNotification.created_at.desc(), SystemNotification.id.desc())
        .offset(max(0, offset))
        .limit(max(1, min(limit, 500)))
        .all()
    )
    return {
        "items": [
            {
                "id": row.id,
                "target_type": row.target_type,
                "target_value": row.target_value,
                "title": row.title,
                "message": row.message,
                "severity": row.severity,
                "starts_at": to_iso_datetime(row.starts_at),
                "expires_at": to_iso_datetime(row.expires_at),
                "is_active": bool(row.is_active),
                "created_by_email": row.created_by_email,
                "created_at": to_iso_datetime(row.created_at),
            }
            for row in rows
        ],
        "count": len(rows),
    }


@router.post("/control-center/notifications/broadcast")
def broadcast_system_notification(
    payload: BroadcastNotificationRequest,
    request: FastAPIRequest,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """
    Interní broadcast (bez OS shell commandů): uloží oznámení do append-only logu.
    Frontend může log číst a zobrazovat.
    """
    message = str(payload.message or "").strip()
    if len(message) < 3:
        raise HTTPException(status_code=400, detail="Zpráva musí mít alespoň 3 znaky")

    severity = normalize_broadcast_severity(payload.severity)
    target_type, target_value = normalize_notification_target(payload.target_type, payload.target_value)
    expires_at = None
    if payload.expires_in_hours is not None:
        safe_hours = max(1, min(int(payload.expires_in_hours), 24 * 180))
        expires_at = datetime.utcnow() + timedelta(hours=safe_hours)

    notifications_file = DATA_DIR / "system_notifications.jsonl"
    notifications_file.parent.mkdir(parents=True, exist_ok=True)
    actor = get_customer_by_email(db, email)
    event = {
        "timestamp": datetime.utcnow().isoformat(),
        "title": (payload.title or "").strip() or None,
        "message": message,
        "severity": severity,
        "target_type": target_type,
        "target_value": target_value,
        "expires_at": to_iso_datetime(expires_at),
        "created_by": email.lower(),
    }
    with open(notifications_file, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")

    notification_row = SystemNotification(
        target_type=target_type,
        target_value=target_value,
        title=(payload.title or "").strip() or None,
        message=message,
        severity=severity,
        starts_at=datetime.utcnow(),
        expires_at=expires_at,
        is_active=True,
        created_by_customer_id=actor.id if actor else None,
        created_by_email=email.lower(),
    )
    db.add(notification_row)
    db.commit()
    db.refresh(notification_row)

    log_developer_action(
        db,
        developer_email=email,
        request=request,
        action_type="notifications.broadcast",
        target_resource="system_notifications",
        parameters={
            "message": message,
            "title": event.get("title"),
            "severity": severity,
            "target_type": target_type,
            "target_value": target_value,
            "expires_at": to_iso_datetime(expires_at),
        },
        result="success",
        status_code=200,
    )
    return {
        "message": "Broadcast uložen",
        "event": event,
        "notification_id": notification_row.id,
    }


@router.get("/control-center/audit-actions")
def get_developer_action_audit(
    limit: int = 200,
    offset: int = 0,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """Immutable audit log developer akcí."""
    rows = (
        db.query(DeveloperActionAuditLog)
        .order_by(DeveloperActionAuditLog.created_at.desc(), DeveloperActionAuditLog.id.desc())
        .offset(max(0, offset))
        .limit(max(1, min(limit, 500)))
        .all()
    )
    return {
        "items": [
            {
                "id": row.id,
                "developer_id": row.developer_id,
                "developer_email": row.developer_email,
                "action_type": row.action_type,
                "target_resource": row.target_resource,
                "parameters_json": row.parameters_json,
                "result": row.result,
                "status_code": row.status_code,
                "request_ip": row.request_ip,
                "created_at": to_iso_datetime(row.created_at),
            }
            for row in rows
        ],
        "count": len(rows),
    }


@router.post("/control-center/commands/execute")
def execute_internal_control_command(
    payload: InternalCommandRequest,
    request: FastAPIRequest,
    email: str = Depends(require_control_center_admin),
    db: Session = Depends(get_db),
):
    """
    Command console bez OS shell přístupu.
    Podporované interní příkazy:
      - system.health
      - broadcast "text"
      - license.recheck USER_ID
      - jobs.run JOB_NAME
      - jobs.pause JOB_NAME
      - jobs.resume JOB_NAME
      - payments.resync
      - logs.tail
    """
    command = (payload.command or "").strip()
    if not command:
        raise HTTPException(status_code=400, detail="Příkaz je prázdný")

    def _ok(result: Dict[str, Any]) -> Dict[str, Any]:
        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="command.execute",
            target_resource=command,
            parameters={"command": command},
            result="success",
            status_code=200,
        )
        return {"ok": True, "command": command, "result": result}

    try:
        normalized = command.strip()
        normalized_lc = normalized.lower()

        if normalized_lc == "system.health":
            result = get_control_center_health(email=email, db=db)
            return _ok(result)

        if normalized_lc.startswith("broadcast "):
            message = normalized[len("broadcast "):].strip().strip('"').strip("'")
            result = broadcast_system_notification(
                payload=BroadcastNotificationRequest(message=message),
                request=request,
                email=email,
                db=db,
            )
            return _ok(result)

        if normalized_lc.startswith("license.recheck "):
            user_id_text = normalized[len("license.recheck "):].strip()
            if not user_id_text.isdigit():
                raise HTTPException(status_code=400, detail="license.recheck vyžaduje USER_ID")
            result = get_user_license_payment_insight(
                user_id=int(user_id_text),
                email=email,
                db=db,
            )
            return _ok(result)

        if normalized_lc.startswith("jobs.run "):
            job_name = normalized[len("jobs.run "):].strip()
            result = run_control_center_job(
                payload={"job_name": job_name},
                request=request,
                email=email,
                db=db,
            )
            return _ok(result)

        if normalized_lc.startswith("jobs.pause "):
            job_name = normalized[len("jobs.pause "):].strip()
            result = pause_control_center_job(
                payload=JobStateRequest(job_name=job_name),
                request=request,
                email=email,
                db=db,
            )
            return _ok(result)

        if normalized_lc.startswith("jobs.resume "):
            job_name = normalized[len("jobs.resume "):].strip()
            result = resume_control_center_job(
                payload=JobStateRequest(job_name=job_name),
                request=request,
                email=email,
                db=db,
            )
            return _ok(result)

        if normalized_lc == "payments.resync":
            result = resync_control_center_payments(
                request=request,
                email=email,
                db=db,
            )
            return _ok(result)

        if normalized_lc == "logs.tail":
            result = get_control_center_system_logs(lines=80, email=email, db=db)
            return _ok(result)

        raise HTTPException(status_code=400, detail="Nepodporovaný příkaz")
    except HTTPException:
        raise
    except Exception as e:
        log_developer_action(
            db,
            developer_email=email,
            request=request,
            action_type="command.execute",
            target_resource=command,
            parameters={"error": str(e)},
            result="failed",
            status_code=500,
        )
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Command failed: {str(e)}")


# ============= TENANTS & INSTANCES (Multi-tenant) =============

@router.get("/tenants", response_model=List[TenantListItem])
def list_tenants(
    limit: int = 50,
    offset: int = 0,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Vrátí seznam všech tenants - pouze pro developer_admin"""
    if not TENANTS_AVAILABLE:
        raise HTTPException(status_code=501, detail="Tenants modely nejsou dostupné")
    
    try:
        tenants = db.query(Tenant).order_by(Tenant.created_at.desc()).offset(offset).limit(limit).all()
        return [TenantListItem(
            id=t.id,
            name=t.name,
            license_key=t.license_key,
            created_at=t.created_at
        ) for t in tenants]
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání tenants: {str(e)}")


@router.get("/tenants/{tenant_id}/instances", response_model=List[InstanceListItem])
def list_instances(
    tenant_id: int,
    limit: int = 50,
    offset: int = 0,
    email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db)
):
    """Vrátí seznam instancí pro daného tenanta - pouze pro developer_admin"""
    if not TENANTS_AVAILABLE:
        raise HTTPException(status_code=501, detail="Instances modely nejsou dostupné")
    
    try:
        # Zkontrolovat, zda tenant existuje
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant nenalezen")
        
        instances = db.query(Instance).filter(
            Instance.tenant_id == tenant_id
        ).order_by(Instance.last_seen_at.desc()).offset(offset).limit(limit).all()
        
        return [InstanceListItem(
            id=i.id,
            device_id=i.device_id,
            app_version=i.app_version,
            last_seen_at=i.last_seen_at
        ) for i in instances]
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Chyba při načítání instancí: {str(e)}")
