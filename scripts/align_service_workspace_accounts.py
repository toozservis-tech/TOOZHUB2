#!/usr/bin/env python3
"""
Údržba: zarovná účty mezi uživatelským portálem („garážová“ dílna) a skutečným servisním rozhraním.

- promote-service: nastaví `customers.role='service'` a `tenants.workspace_route_kind='service'`
  (např. oficiální servisní operátor jako info@toozservis.cz).
- demote-user-portal: `role='user'` a tenant `workspace_route_kind='user'` pro účet, který má být
  jen vstupní uživatelský workspace (bez servisní dílny v admin Sekci Servisy).

Spuštění z kořene aplikace s načtenou DB (viz .env jako u serveru):

  cd /opt/toozhub2/app && PYTHONPATH=. python3 scripts/align_service_workspace_accounts.py promote-service info@toozservis.cz

  PYTHONPATH=. python3 scripts/align_service_workspace_accounts.py demote-user-portal jiny@firma.cz
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import func  # noqa: E402

from src.modules.vehicle_hub.database import SessionLocal  # noqa: E402
from src.modules.vehicle_hub.models import Customer, Tenant  # noqa: E402
from src.modules.vehicle_hub.workspace_routing import ensure_tenant_workspace_slug  # noqa: E402


def _norm_email(email: str) -> str:
    return (email or "").strip().lower()


def promote_service(email: str) -> None:
    em = _norm_email(email)
    db = SessionLocal()
    try:
        c = db.query(Customer).filter(func.lower(Customer.email) == em).first()
        if not c:
            raise SystemExit(f"Zákazník {em!r} nenalezen.")
        tenant = db.query(Tenant).filter(Tenant.id == c.tenant_id).first()
        if not tenant:
            raise SystemExit(f"Tenant pro {em!r} nenalezen.")
        tenant.workspace_route_kind = "service"
        c.role = "service"
        seed = str((c.name or c.email or "").strip() or "service")
        ensure_tenant_workspace_slug(db, tenant, seed_label=seed, route_kind="service")
        db.commit()
        print(f"OK: {em} → role=service, tenant #{tenant.id} workspace_route_kind=service")
    finally:
        db.close()


def demote_user_portal(email: str) -> None:
    em = _norm_email(email)
    db = SessionLocal()
    try:
        c = db.query(Customer).filter(func.lower(Customer.email) == em).first()
        if not c:
            raise SystemExit(f"Zákazník {em!r} nenalezen.")
        tenant = db.query(Tenant).filter(Tenant.id == c.tenant_id).first()
        if not tenant:
            raise SystemExit(f"Tenant pro {em!r} nenalezen.")
        tenant.workspace_route_kind = "user"
        c.role = "user"
        seed = str((c.name or c.email or "").strip() or "user")
        ensure_tenant_workspace_slug(db, tenant, seed_label=seed, route_kind="user")
        db.commit()
        print(f"OK: {em} → role=user, tenant #{tenant.id} workspace_route_kind=user (admin Servisy jej už nevylistuje jako dílnu)")
    finally:
        db.close()


def main() -> None:
    p = argparse.ArgumentParser(description="Zarovnat service vs user portal účty v DB.")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_pro = sub.add_parser("promote-service", help="Účet jako servisní operátor + tenant service workspace.")
    p_pro.add_argument("email")

    p_de = sub.add_parser("demote-user-portal", help="Účet jako běžný uživatel + tenant user workspace (ne „Servis“ v adminu).")
    p_de.add_argument("email")

    args = p.parse_args()
    if args.cmd == "promote-service":
        promote_service(args.email)
    elif args.cmd == "demote-user-portal":
        demote_user_portal(args.email)
    else:
        p.error("Neznámý příkaz")


if __name__ == "__main__":
    main()
