#!/usr/bin/env python3
"""
Jednorázová migrace servisních licencí: service_basic / service_premium → service_full.

Spusť z adresáře app/:
  python scripts/migrate_service_license_two_tier.py
"""
from __future__ import annotations

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine, text  # noqa: E402
from src.core.config import DATABASE_URL  # noqa: E402


def main() -> None:
    engine = create_engine(DATABASE_URL, future=True)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE licenses
                SET plan = 'service_full', updated_at = CURRENT_TIMESTAMP
                WHERE plan IN ('service_basic', 'service_premium')
                """
            )
        )
        conn.execute(
            text(
                """
                UPDATE license_subscriptions
                SET plan_current = 'service_full', updated_at = CURRENT_TIMESTAMP
                WHERE plan_current IN ('service_basic', 'service_premium')
                """
            )
        )
    print("OK: service_basic/service_premium → service_full")


if __name__ == "__main__":
    main()
