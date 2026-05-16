#!/usr/bin/env python3
"""
Odstraní z runtime DB testovací zákazníky (soft-smazání: is_deleted + přejmenování emailu),
ukázkový/demo účet z .env se **nepošle** (SPRAVA_VOZIDEL_DEMO_ACCOUNT_EMAIL / TOOZHUB_DEMO_ACCOUNT_EMAIL).

Cíle zákazníků (nejsou-li již smazaní):
  - e-mail končící na @example.com
  - e-mail začínající na e2e. (jakákoli doména)
  - staré adresy po recycle-ci (…@ci-released.invalid, deleted-ci-*@removed.invalid)

Dále smaže řádky service_registration_requests s @example.com.

Čisté SQL přes DATABASE_URL (bez ORM řádku Customer).

Další výjimky: env TEST_CLEANUP_KEEP_EMAILS=mail1@a.cz,mail2@… nebo přepínač --keep EMAIL (opakovatelně).

  cd /opt/toozhub2/app && ../.venv/bin/python scripts/remove_example_com_integration_users.py --dry-run
  ../.venv/bin/python scripts/remove_test_customers_keep_demo.py --dry-run   # alias
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_PROJECT = Path(__file__).resolve().parent.parent
if str(_PROJECT) not in sys.path:
    sys.path.insert(0, str(_PROJECT))

from sqlalchemy import create_engine, text

from src.core.config import DATABASE_URL
from src.core.env_aliases import env_prefer_new


def _emails_to_keep(cli_keep: list[str]) -> set[str]:
    """Normalizované e-maily, které se nesmí mazat."""
    keep: set[str] = set()
    demo = (env_prefer_new("SPRAVA_VOZIDEL_DEMO_ACCOUNT_EMAIL", "TOOZHUB_DEMO_ACCOUNT_EMAIL") or "").strip().lower()
    if demo:
        keep.add(demo)
    raw_extra = os.getenv("TEST_CLEANUP_KEEP_EMAILS", "")
    for part in raw_extra.split(","):
        p = part.strip().lower()
        if p:
            keep.add(p)
    for item in cli_keep:
        k = item.strip().lower()
        if k:
            keep.add(k)
    return keep


def _candidate_customer_sql() -> str:
    return """
        SELECT id, email FROM customers
        WHERE COALESCE(is_deleted, 0) = 0
          AND (
            lower(email) LIKE '%@example.com'
            OR lower(email) LIKE 'e2e.%'
            OR lower(email) LIKE '%@ci-released.invalid'
            OR lower(email) LIKE 'deleted-ci-%@removed.invalid'
          )
        ORDER BY id
    """


def run_cleanup(*, dry_run: bool, extra_keep: list[str]) -> int:
    keep = _emails_to_keep(extra_keep)
    if keep:
        print(f"Vynecháme ({len(keep)}): {', '.join(sorted(keep))}")

    engine = create_engine(DATABASE_URL)
    with engine.connect() as conn:
        raw_rows = conn.execute(text(_candidate_customer_sql())).mappings().all()
        cust_rows = [r for r in raw_rows if str(r["email"]).strip().lower() not in keep]

        req_rows = conn.execute(
            text(
                """
                SELECT id, email FROM service_registration_requests
                WHERE lower(email) LIKE '%@example.com'
                ORDER BY id
                """
            )
        ).mappings().all()

        print(f"Customers k označení jako smazané: {len(cust_rows)} (z nalezených kandidátů {len(raw_rows)})")
        print(f"Service registration requests ke smazání: {len(req_rows)}")

        if dry_run:
            for r in cust_rows[:50]:
                print(f"  [customer] id={r['id']} email={r['email']!r}")
            if len(cust_rows) > 50:
                print(f"  … a dalších {len(cust_rows) - 50}")
            for r in req_rows[:30]:
                print(f"  [svc_req] id={r['id']} email={r['email']!r}")
            return 0

    with engine.begin() as conn:
        if req_rows:
            conn.execute(
                text("DELETE FROM service_registration_requests WHERE lower(email) LIKE '%@example.com'")
            )
        for r in cust_rows:
            cid = int(r["id"])
            new_email = f"deleted-ci-{cid}@removed.invalid"
            conn.execute(
                text(
                    """
                    UPDATE customers
                    SET email = :ne,
                        is_deleted = 1,
                        is_disabled = 1
                    WHERE id = :id AND COALESCE(is_deleted, 0) = 0
                    """
                ),
                {"ne": new_email, "id": cid},
            )

    print(f"Hotovo: upraveno {len(cust_rows)} zákazníků, smazáno {len(req_rows)} žádostí registrace.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Odstranit testovací zákazníky, zachovat ukázkový účet z .env.")
    ap.add_argument("--dry-run", action="store_true", help="Jen vypsat dotčené řádky.")
    ap.add_argument(
        "--keep",
        action="append",
        default=[],
        metavar="EMAIL",
        help="E-mail(y) které nikdy nemazat (lze zopakovat).",
    )
    args = ap.parse_args()
    return run_cleanup(dry_run=args.dry_run, extra_keep=args.keep)


if __name__ == "__main__":
    raise SystemExit(main())
