"""Durable file removal, queued in the same transaction as the owning record.

Never walk or empty a storage bucket. Only validated, exact private file paths
are accepted. Rollback cancels erasure; a failed provider call remains retryable.
"""
from datetime import datetime, timedelta
from pathlib import Path
import hashlib
import json
import secrets
import re

import httpx
from sqlalchemy import Column, DateTime, Integer, String, Text, inspect

from src.core import file_storage
from src.modules.vehicle_hub.database import Base, SessionLocal

PRIVATE_DIRECTORIES = frozenset({
    "vehicle_photos", "private_repair_photos", "vehicle_orv_scans",
    "service_record_attachments", "service_workspace_docs",
})


class FileErasure(Base):
    __tablename__ = "private_file_erasure_queue"
    path = Column(String, primary_key=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    next_attempt_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    attempts = Column(Integer, nullable=False, default=0)


class AccountErasureReceipt(Base):
    __tablename__ = "account_erasure_receipts"
    token_digest = Column(String(64), primary_key=True)
    paths_json = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True, index=True)


def create_receipt(db, paths: list[str]) -> str:
    token = db.info.pop("requested_erasure_receipt", None) or secrets.token_urlsafe(32)
    db.add(AccountErasureReceipt(token_digest=hashlib.sha256(token.encode()).hexdigest(),
        paths_json=json.dumps(sorted(set(paths))), completed_at=None if paths else datetime.utcnow()))
    return token


def receipt_status(db, token: str) -> dict | None:
    row = db.get(AccountErasureReceipt, hashlib.sha256(token.encode()).hexdigest())
    if row is None or (row.completed_at and row.completed_at < datetime.utcnow() - timedelta(days=30)):
        return None
    paths = json.loads(row.paths_json)
    pending = db.query(FileErasure).filter(FileErasure.path.in_(paths)).count() if paths else 0
    if not pending and row.completed_at is None:
        row.completed_at = datetime.utcnow()
        row.paths_json = "[]"
    return {"completed": pending == 0, "files_pending": pending,
            "message": "Odstranění účtu a soukromých souborů je dokončeno." if not pending else
                "Účet je odstraněný. Dokončujeme odstranění soukromých souborů; při výpadku úložiště pokus automaticky opakujeme."}


def private_path(directory: str, raw: str | None) -> Path | None:
    if not raw:
        return None
    if directory not in PRIVATE_DIRECTORIES:
        raise ValueError("Unknown private directory")
    root = file_storage.DATA_DIR.resolve()
    base = root / directory
    path = Path(str(raw).replace("\\", "/"))
    # Older document uploads saved absolute paths. Only remap that known layout.
    if path.is_absolute() and directory == "service_workspace_docs" and directory in path.parts:
        path = Path(path.name)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Invalid private file path")
    candidate = (base / path).resolve()
    if base not in candidate.parents or candidate.is_dir():
        raise ValueError("Private file is outside its directory")
    return candidate


def enqueue_file_erasure(db, directory: str, raw: str | None) -> bool:
    path = private_path(directory, raw)
    if path is None:
        return False
    relative = path.relative_to(file_storage.DATA_DIR.resolve()).as_posix()
    # Flush is intentional: pending duplicate paths must be visible in this transaction.
    db.flush()
    if db.get(FileErasure, relative) is None:
        db.add(FileErasure(path=relative))
        db.flush()
        return True
    return False


def erase_private_file(relative: str) -> None:
    parts = Path(relative).parts
    if len(parts) < 2:
        raise ValueError("Invalid private file path")
    path = private_path(parts[0], Path(*parts[1:]).as_posix())
    object_key = file_storage._key(path)
    config = file_storage._config()
    if config:
        base, headers = config
        # Storage API removal also removes the underlying object, unlike SQL deletion.
        response = httpx.delete(base + object_key, headers=headers, timeout=20)
        missing = False
        if response.status_code in (400, 404):
            try:
                body = response.json()
                missing = body.get("error") in ("not_found", "Not Found") or str(body.get("statusCode")) == "404"
            except (ValueError, AttributeError):
                pass
        if not missing:
            response.raise_for_status()
    path.unlink(missing_ok=True)


def recover_abandoned_document_uploads(*, session_factory=SessionLocal, now=None, limit=10) -> int:
    """Only unfinished upload intents, never reviewed/confirmed documents.

    A process can die between storing either side and committing OCR results.
    Keep its exact paths available for recovery, then expire it after 24 hours.
    Active uploads hold the row lock and are skipped.
    """
    from src.modules.vehicle_hub.models import VehicleORVScan
    now = now or datetime.utcnow()
    with session_factory() as db:
        if not inspect(db.connection()).has_table(VehicleORVScan.__tablename__):
            return 0
        rows = (db.query(VehicleORVScan).filter(VehicleORVScan.status == "processing",
                    VehicleORVScan.vehicle_id.is_(None),
                    VehicleORVScan.front_image_path.like("%/front\\_%.jpg", escape="\\"),
                    VehicleORVScan.created_at < now - timedelta(hours=24))
                .order_by(VehicleORVScan.created_at).limit(max(0, min(limit, 100)))
                .with_for_update(skip_locked=True).all())
        recovered = 0
        for row in rows:
            # Legacy files were not created with this durable-intent protocol.
            # Do not infer permission to remove them merely from an old status.
            prefix = f"tenant_{row.tenant_id}/scan_{row.id}/"
            if not all(re.fullmatch(re.escape(prefix + side + "_") + r"[a-f0-9]{32}\.jpg", path or "")
                       for side, path in (("front", row.front_image_path), ("back", row.back_image_path))):
                continue
            enqueue_file_erasure(db, "vehicle_orv_scans", row.front_image_path)
            enqueue_file_erasure(db, "vehicle_orv_scans", row.back_image_path)
            row.front_image_path = row.back_image_path = None
            row.front_captured = row.back_captured = False
            row.status = "failed"
            recovered += 1
        db.commit()
        return recovered


def process_file_erasures(*, session_factory=SessionLocal, limit=10, now=None) -> dict:
    now = now or datetime.utcnow()
    recover_abandoned_document_uploads(session_factory=session_factory, now=now, limit=limit)
    result = {"removed": 0, "retrying": 0}
    for _ in range(max(0, min(limit, 100))):
        with session_factory() as db:
            row = (db.query(FileErasure).filter(FileErasure.next_attempt_at <= now)
                   .order_by(FileErasure.created_at).with_for_update(skip_locked=True).first())
            if row is None:
                break
            try:
                erase_private_file(row.path)
            except Exception:
                # Do not persist/log filenames, server responses, or credentials.
                row.attempts += 1
                row.next_attempt_at = now + timedelta(seconds=min(3600, 60 * 2 ** min(row.attempts, 6)))
                result["retrying"] += 1
            else:
                db.delete(row)
                result["removed"] += 1
            db.commit()
    with session_factory() as db:
        receipts = db.query(AccountErasureReceipt).filter(AccountErasureReceipt.completed_at.is_(None)).limit(100).all()
        for receipt in receipts:
            paths = json.loads(receipt.paths_json)
            if not db.query(FileErasure.path).filter(FileErasure.path.in_(paths)).first():
                receipt.completed_at = now
                receipt.paths_json = "[]"
        db.query(AccountErasureReceipt).filter(AccountErasureReceipt.completed_at < now - timedelta(days=30)).delete(synchronize_session=False)
        db.commit()
    return result
