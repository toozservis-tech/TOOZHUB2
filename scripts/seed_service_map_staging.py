#!/usr/bin/env python3
"""Staging seed pro servisní mapu – Svitavy + Pardubický kraj. Nespouštět na produkci bez potvrzení."""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.modules.vehicle_hub.database import SessionLocal
from src.modules.vehicle_hub.models import ServiceLocation
from src.modules.vehicle_hub.service_map.constants import (
    CATEGORY_AUTOSERVIS,
    CATEGORY_PNEUSERVIS,
    CATEGORY_SME,
    CATEGORY_STK,
    CATEGORY_TRUCK,
    SOURCE_STAGING_SEED,
)
from src.modules.vehicle_hub.service_map.normalize import normalize_service_name

SEED_ROWS = [
    {
        "source_external_id": "svitavy-autoservis-1",
        "name": "Autoservis Svitavy – demo",
        "category": CATEGORY_AUTOSERVIS,
        "lat": 49.7559,
        "lng": 16.4683,
        "city": "Svitavy",
        "address_text": "Gorkého, Svitavy",
        "phone": "+420777111222",
    },
    {
        "source_external_id": "svitavy-pneuservis-1",
        "name": "Pneuservis Svitavy – demo",
        "category": CATEGORY_PNEUSERVIS,
        "lat": 49.7582,
        "lng": 16.4710,
        "city": "Svitavy",
        "address_text": "Olomoucká, Svitavy",
        "phone": "+420777222333",
    },
    {
        "source_external_id": "svitavy-stk-1",
        "name": "STK Svitavy – demo",
        "category": CATEGORY_STK,
        "lat": 49.7535,
        "lng": 16.4620,
        "city": "Svitavy",
        "address_text": "Kpt. Jaroše, Svitavy",
        "phone": "+420777333444",
    },
    {
        "source_external_id": "svitavy-sme-1",
        "name": "Emisní stanice Svitavy – demo",
        "category": CATEGORY_SME,
        "lat": 49.7540,
        "lng": 16.4655,
        "city": "Svitavy",
        "address_text": "Kpt. Jaroše, Svitavy",
        "phone": "+420777444555",
    },
    {
        "source_external_id": "pardubice-truck-1",
        "name": "Servis nákladních vozidel Pardubicko – demo",
        "category": CATEGORY_TRUCK,
        "lat": 50.0343,
        "lng": 15.7812,
        "city": "Pardubice",
        "address_text": "Průmyslová, Pardubice",
        "phone": "+420777555666",
    },
]


def main() -> None:
    env = os.getenv("ENVIRONMENT", os.getenv("APP_ENV", "")).strip().lower()
    if env in {"production", "prod"}:
        print("REFUSED: seed nelze spustit v produkčním prostředí.")
        sys.exit(1)

    db = SessionLocal()
    now = datetime.utcnow()
    created = 0
    try:
        for row in SEED_ROWS:
            existing = (
                db.query(ServiceLocation)
                .filter(
                    ServiceLocation.source_type == SOURCE_STAGING_SEED,
                    ServiceLocation.source_external_id == row["source_external_id"],
                )
                .first()
            )
            if existing:
                continue
            db.add(
                ServiceLocation(
                    source_type=SOURCE_STAGING_SEED,
                    source_external_id=row["source_external_id"],
                    name=row["name"],
                    normalized_name=normalize_service_name(row["name"]),
                    category=row["category"],
                    lat=row["lat"],
                    lng=row["lng"],
                    address_text=row["address_text"],
                    city=row["city"],
                    phone=row.get("phone"),
                    verification_status="imported",
                    confidence_score=0.5,
                    last_imported_at=now,
                    is_active=True,
                )
            )
            created += 1
        db.commit()
        print(f"Service map seed hotovo: {created} nových záznamů.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
