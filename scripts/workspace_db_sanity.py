#!/usr/bin/env python3
"""
Production sanity: workspace slugs and route kinds (read + optional repair).

Usage:
  python3 scripts/workspace_db_sanity.py
  python3 scripts/workspace_db_sanity.py --repair-slugs
  python3 scripts/workspace_db_sanity.py --normalize-route-kinds
  python3 scripts/workspace_db_sanity.py --report-license-route-align
  python3 scripts/workspace_db_sanity.py --repair-license-route-align
  python3 scripts/workspace_db_sanity.py --repair-license-route-align --dry-run
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from src.modules.vehicle_hub.database import SessionLocal  # noqa: E402
from src.modules.vehicle_hub.workspace_sanity import (  # noqa: E402
    collect_license_workspace_mismatch_report,
    collect_workspace_sanity_report,
    normalize_invalid_tenant_route_kinds,
    repair_empty_workspace_slugs,
    repair_service_license_route_kinds,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Workspace DB sanity checks")
    parser.add_argument("--repair-slugs", action="store_true", help="Fill empty workspace_slug via ensure_tenant_workspace_slug")
    parser.add_argument(
        "--normalize-route-kinds",
        action="store_true",
        help="Rewrite invalid workspace_route_kind to user|service from first tenant customer",
    )
    parser.add_argument(
        "--report-license-route-align",
        action="store_true",
        help="Report tenants where workspace_route_kind conflicts with licences.plan (service_* vs user)",
    )
    parser.add_argument(
        "--repair-license-route-align",
        action="store_true",
        help="Set workspace_route_kind='service' where licences.plan starts with service_ but rk is not service",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="With --repair-license-route-align: only list tenant IDs that would be updated",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        report = collect_workspace_sanity_report(db)
        print("=== WORKSPACE SANITY ===")
        print("duplicate_slug_groups:", report.duplicate_slug_groups or "none")
        print("empty_slug_rows:", report.empty_slug_rows or "none")
        print("invalid_route_kind_rows:", report.invalid_route_kind_rows or "none")
        print("route_kind_counts:", report.route_kind_counts)

        if args.normalize_route_kinds:
            n = normalize_invalid_tenant_route_kinds(db)
            print(f"--normalize-route-kinds: updated {n} tenant(s)")
        if args.report_license_route_align or args.repair_license_route_align:
            lic_rep = collect_license_workspace_mismatch_report(db)
            print("=== LICENSE ↔ WORKSPACE_ROUTE_KIND ===")
            print("mismatch_count:", lic_rep.get("mismatch_count"))
            print(
                "auto_fixable_non_service_route_with_service_license_count:",
                lic_rep.get("auto_fixable_non_service_route_with_service_license_count"),
            )
            rows = lic_rep.get("rows") or []
            if rows:
                for row in rows:
                    print(row)
            else:
                print("rows: (none)")
        if args.repair_license_route_align:
            rr = repair_service_license_route_kinds(db, dry_run=args.dry_run)
            print(
                "--repair-license-route-align:",
                f"dry_run={rr.get('dry_run')} updated_count={rr.get('updated_count')}",
            )
            print("tenant_ids:", rr.get("tenant_ids"))
        if args.repair_slugs:
            n = repair_empty_workspace_slugs(db)
            print(f"--repair-slugs: repaired {n} tenant(s)")

        report2 = collect_workspace_sanity_report(db)
        ok = not report2.has_duplicate_slugs and not report2.has_empty_slugs and report2.route_kinds_valid
        print("=== AFTER (if repairs ran) ===")
        print("duplicate_slug_groups:", report2.duplicate_slug_groups or "none")
        print("empty_slug_rows:", report2.empty_slug_rows or "none")
        print("invalid_route_kind_rows:", report2.invalid_route_kind_rows or "none")
        return 0 if ok else 2
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
