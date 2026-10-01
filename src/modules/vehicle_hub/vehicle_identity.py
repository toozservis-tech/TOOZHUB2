"""One VIN across every ORM writer, including service and admin workflows.

The PostgreSQL transaction lock also covers a VIN that does not yet have a row.
No existing rows are merged or removed. SQL imports must be reviewed separately.
"""
import hashlib
import re

from fastapi import HTTPException
from sqlalchemy import event, inspect, select, text, update
from sqlalchemy.orm import Session


def normalize_vin(value):
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


@event.listens_for(Session, "before_flush")
def guard_vehicle_identity(session, flush_context, instances):
    from .models import Vehicle

    changed = [row for row in session.new.union(session.dirty)
               if isinstance(row, Vehicle) and row not in session.deleted
               and (row in session.new or inspect(row).attrs.vin.history.has_changes())]
    candidates = {}
    for row in changed:
        vin = normalize_vin(row.vin)
        row.vin = vin or None
        if not vin:
            continue
        if vin in candidates:
            raise HTTPException(409, "Vozidlo s tímto VIN již existuje. Nevytvářejte druhý profil.")
        candidates[vin] = row
    if not candidates:
        return

    connection = session.connection()
    dialect = connection.dialect.name
    if dialect == "postgresql":
        # Stable namespaced 64-bit keys, acquired in a common order for batches.
        for vin in sorted(candidates):
            lock_id = int.from_bytes(hashlib.sha256(("sv:vin:" + vin).encode()).digest()[:8], "big", signed=True)
            connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})
    elif dialect == "sqlite":
        # Acquire the SQLite writer lock before checking. A stale read snapshot
        # fails closed with SQLITE_BUSY instead of allowing a duplicate commit.
        connection.execute(update(Vehicle.__table__).where(text("1=0")).values(id=Vehicle.id))
    else:
        raise RuntimeError("Vehicle identity locking is not implemented for this database")

    # Read from the connection, not an identity map that predates a waiting lock.
    # Legacy VIN values may contain spaces, separators or lowercase letters.
    if dialect == "postgresql":
        from sqlalchemy import func
        normalized = func.regexp_replace(func.upper(Vehicle.vin), "[^A-Z0-9]", "", "g")
        query = select(Vehicle.id, Vehicle.vin).where(normalized.in_(candidates))
    else:
        query = select(Vehicle.id, Vehicle.vin).where(Vehicle.vin.is_not(None))
    for identity, stored_vin in connection.execute(query):
        row = candidates.get(normalize_vin(stored_vin))
        if row is not None and row.id != identity:
            # Never return the existing owner's identity or vehicle metadata.
            raise HTTPException(409, "Vozidlo s tímto VIN již existuje. Nevytvářejte druhý profil.")
