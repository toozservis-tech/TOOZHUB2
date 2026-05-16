#!/usr/bin/env python3
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from src.modules.vehicle_hub.database import SessionLocal
from src.modules.vehicle_hub.models import LicensePaymentTransaction
from src.modules.vehicle_hub.routers_v1.license_status import _payload_hash, sanitize_comgate_payload


def main() -> int:
    db: Session = SessionLocal()
    updated = 0
    scanned = 0
    try:
        rows = db.query(LicensePaymentTransaction).order_by(LicensePaymentTransaction.id.asc()).all()
        for row in rows:
            scanned += 1
            raw = str(row.payload_json or "").strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            sanitized = sanitize_comgate_payload(payload)
            sanitized_json = json.dumps(sanitized, ensure_ascii=False, sort_keys=True, separators=(",", ":")) if sanitized else None
            payload_hash = _payload_hash(payload)
            if row.payload_json != sanitized_json or row.raw_provider_payload_hash != payload_hash:
                row.payload_json = sanitized_json
                row.raw_provider_payload_hash = payload_hash
                updated += 1
                db.add(row)
        db.commit()
        print(f"Scanned {scanned} payment rows, sanitized {updated}.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
