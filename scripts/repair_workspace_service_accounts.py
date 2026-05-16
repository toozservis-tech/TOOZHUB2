#!/usr/bin/env python3
"""
Jednorázové opravy klasifikace účtů „servis vs. uživatelský tenant“ v produkční / dev DB.

Účel:
- **Operátor servisu** (např. info@…) → `role=service`, `tenants.workspace_route_kind='service'` (viditelné v adminu v sekci Servisy).
- **Pouze uživatelské rozhraní / garáž** (omylem `role=service` nebo přiřazený servisní tenant) → `role=user`, `workspace_route_kind='user'`
  (nebude v sekci Servisy po nasazení zpřesněného filtru v admin API).

Příklady:
  cd /opt/toozhub2/app
  /opt/toozhub2/.venv/bin/python scripts/repair_workspace_service_accounts.py \\
    --promote-operator info@toozservis.cz \\
    --demote-consumer zasilaci@toozservis.cz

Bez `--dry-run` zápis do DB; s `--dry-run` jen vypíše plánované změny.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.modules.vehicle_hub.database import SessionLocal  # noqa: E402
from src.modules.vehicle_hub.models import Customer, Tenant  # noqa: E402
from src.modules.vehicle_hub.ownership import get_customer_by_email  # noqa: E402


def _norm_email(raw: str | None) -> str | None:
    if not raw:
        return None
    s = str(raw).strip().lower()
    return s or None


def _apply_promote_operator(db, email: str, dry_run: bool) -> None:
    c = get_customer_by_email(db, email)
    if not c:
        print(f"[promote] CHYBÍ účet: {email}")
        return
    t = db.query(Tenant).filter(Tenant.id == c.tenant_id).first() if c.tenant_id else None
    print(f"[promote] {email}: role {c.role!r} -> 'service'; tenant #{c.tenant_id} kind {getattr(t, 'workspace_route_kind', None)!r} -> 'service'")
    if dry_run:
        return
    c.role = "service"
    db.add(c)
    if t:
        t.workspace_route_kind = "service"
        db.add(t)
    db.commit()


def _apply_demote_consumer(db, email: str, dry_run: bool) -> None:
    c = get_customer_by_email(db, email)
    if not c:
        print(f"[demote] CHYBÍ účet: {email}")
        return
    t = db.query(Tenant).filter(Tenant.id == c.tenant_id).first() if c.tenant_id else None
    print(f"[demote] {email}: role {c.role!r} -> 'user'; tenant #{c.tenant_id} kind {getattr(t, 'workspace_route_kind', None)!r} -> 'user'")
    if dry_run:
        return
    c.role = "user"
    db.add(c)
    if t:
        t.workspace_route_kind = "user"
        db.add(t)
    db.commit()


def main() -> int:
    p = argparse.ArgumentParser(description="Opravy role + workspace_route_kind pro servisní výpis v adminu.")
    p.add_argument("--promote-operator", dest="promote_operator", metavar="EMAIL", help="Účet reálného operátora servisu")
    p.add_argument("--demote-consumer", dest="demote_consumer", metavar="EMAIL", help="Účet pouze uživatelského rozhraní (ne servis v admin sekci)")
    p.add_argument("--dry-run", action="store_true", help="Nepřepisovat DB, jen vypsat záměr")
    args = p.parse_args()

    promo = _norm_email(args.promote_operator)
    demo = _norm_email(args.demote_consumer)

    if not promo and not demo:
        p.error("Zadejte alespoň jeden z parametrů --promote-operator nebo --demote-consumer.")

    db = SessionLocal()
    try:
        if promo:
            _apply_promote_operator(db, promo, args.dry_run)
        if demo:
            _apply_demote_consumer(db, demo, args.dry_run)
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
