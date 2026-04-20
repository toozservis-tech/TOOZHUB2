"""
Read-only workspace DB checks + optional non-destructive slug repair.

Used by scripts and tests; does not change routing architecture.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session

from .models import Customer, Tenant
from .workspace_routing import ensure_tenant_workspace_slug, resolve_workspace_route_kind_for_customer


@dataclass
class WorkspaceSanityReport:
    duplicate_slug_groups: list[dict[str, Any]]
    empty_slug_rows: list[dict[str, Any]]
    invalid_route_kind_rows: list[dict[str, Any]]
    route_kind_counts: dict[str, int]

    @property
    def has_duplicate_slugs(self) -> bool:
        return len(self.duplicate_slug_groups) > 0

    @property
    def has_empty_slugs(self) -> bool:
        return len(self.empty_slug_rows) > 0

    @property
    def route_kinds_valid(self) -> bool:
        return len(self.invalid_route_kind_rows) == 0


def collect_workspace_sanity_report(db: Session) -> WorkspaceSanityReport:
    dup_sql = text(
        """
        SELECT workspace_route_kind, workspace_slug, COUNT(*) AS cnt
        FROM tenants
        WHERE workspace_slug IS NOT NULL AND TRIM(workspace_slug) != ''
        GROUP BY workspace_route_kind, workspace_slug
        HAVING COUNT(*) > 1
        """
    )
    duplicate_slug_groups = [dict(r._mapping) for r in db.execute(dup_sql)]

    empty_sql = text(
        """
        SELECT id, workspace_slug, workspace_route_kind
        FROM tenants
        WHERE workspace_slug IS NULL OR TRIM(workspace_slug) = ''
        """
    )
    empty_slug_rows = [dict(r._mapping) for r in db.execute(empty_sql)]

    kinds_sql = text(
        """
        SELECT workspace_route_kind, COUNT(*) AS cnt
        FROM tenants
        GROUP BY workspace_route_kind
        """
    )
    route_kind_counts: dict[str, int] = {}
    invalid_route_kind_rows: list[dict[str, Any]] = []
    for r in db.execute(kinds_sql):
        row = dict(r._mapping)
        k = row.get("workspace_route_kind")
        key = (k or "").strip().lower() if k is not None else ""
        route_kind_counts[str(k) if k is not None else "NULL"] = int(row["cnt"] or 0)
        if key not in {"user", "service"}:
            invalid_route_kind_rows.append(row)

    return WorkspaceSanityReport(
        duplicate_slug_groups=duplicate_slug_groups,
        empty_slug_rows=empty_slug_rows,
        invalid_route_kind_rows=invalid_route_kind_rows,
        route_kind_counts=route_kind_counts,
    )


def repair_empty_workspace_slugs(db: Session) -> int:
    """Backfill missing slugs via ensure_tenant_workspace_slug. Returns number of tenants touched."""
    touched = 0
    q = (
        db.query(Tenant)
        .filter(or_(Tenant.workspace_slug.is_(None), func.trim(Tenant.workspace_slug) == ""))
        .order_by(Tenant.id.asc())
    )
    for tenant in q.all():
        owner = (
            db.query(Customer)
            .filter(Customer.tenant_id == tenant.id)
            .order_by(Customer.id.asc())
            .first()
        )
        rk = resolve_workspace_route_kind_for_customer(owner) if owner else "user"
        seed = str(tenant.name or (owner.email if owner else None) or (owner.name if owner else None) or "workspace")
        ensure_tenant_workspace_slug(db, tenant, seed_label=seed, route_kind=rk)
        touched += 1
    if touched:
        db.commit()
    return touched


def normalize_invalid_tenant_route_kinds(db: Session) -> int:
    """
    Set workspace_route_kind to user|service only, inferred from first customer in tenant.
    Returns number of rows updated.
    """
    updated = 0
    tenants = db.query(Tenant).all()
    for tenant in tenants:
        raw = (tenant.workspace_route_kind or "").strip().lower()
        if raw in {"user", "service"}:
            continue
        owner = (
            db.query(Customer)
            .filter(Customer.tenant_id == tenant.id)
            .order_by(Customer.id.asc())
            .first()
        )
        tenant.workspace_route_kind = resolve_workspace_route_kind_for_customer(owner) if owner else "user"
        updated += 1
    if updated:
        db.commit()
    return updated
