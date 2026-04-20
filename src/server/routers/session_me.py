"""
GET /api/me — session context for SPA routing (JWT/session is source of truth).
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.auth import get_current_customer_optional
from src.core.branding import APP_DISPLAY_NAME
from src.modules.vehicle_hub.audit_log import write_global_audit_log
from src.modules.vehicle_hub.database import get_db
from src.modules.vehicle_hub.models import Customer, Tenant
from src.modules.vehicle_hub.workspace_routing import (
    build_default_app_path,
    ensure_tenant_workspace_slug,
    map_account_type,
    resolve_workspace_route_kind_for_customer,
)

router = APIRouter(tags=["session"])


class ApiMeAnonymousResponse(BaseModel):
    authenticated: Literal[False] = False
    app_name: str = APP_DISPLAY_NAME


class ApiMeAuthenticatedResponse(BaseModel):
    authenticated: Literal[True] = True
    app_name: str = APP_DISPLAY_NAME
    account_type: str
    account_id: int = Field(description="Interní ID zákaznického účtu (Customer.id)")
    display_name: Optional[str] = None
    email: str
    account_slug: str
    tenant_id: int
    workspace_route_kind: str = Field(description="user|service namespace for slug uniqueness")
    default_app_path: str
    role: str
    license_plan: Optional[str] = None
    license_status: Optional[str] = None
    permissions: dict[str, Any] = Field(default_factory=dict)


def _normalize_assert_route(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    x = str(raw).strip().lower()
    if x in {"u", "user"}:
        return "user"
    if x in {"s", "service"}:
        return "service"
    return None


def _expected_route_kind_from_role(role: str) -> str:
    r = str(role or "").strip().lower()
    if r == "service":
        return "service"
    return "user"


def _normalize_tenant_workspace_route_kind(tenant: Tenant, customer: Customer) -> None:
    """Coerce legacy/invalid workspace_route_kind to user|service from the authenticated account."""
    raw = (getattr(tenant, "workspace_route_kind", None) or "").strip().lower()
    if raw in {"user", "service"}:
        return
    tenant.workspace_route_kind = resolve_workspace_route_kind_for_customer(customer)


@router.get("/api/me")
def api_me(
    request: Request,
    db: Session = Depends(get_db),
    customer: Optional[Customer] = Depends(get_current_customer_optional),
    assert_route: Optional[str] = Query(None, description="Expected workspace path: u|s|user|service"),
    assert_slug: Optional[str] = Query(None, description="Workspace slug from browser URL"),
) -> dict[str, Any]:
    if not customer:
        return ApiMeAnonymousResponse().model_dump()

    tenant = db.query(Tenant).filter(Tenant.id == customer.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=500, detail="Tenant nenalezen")

    _normalize_tenant_workspace_route_kind(tenant, customer)
    rk = resolve_workspace_route_kind_for_customer(customer)
    ensure_tenant_workspace_slug(
        db,
        tenant,
        seed_label=str(tenant.name or customer.name or customer.email or "workspace"),
        route_kind=rk,
    )
    db.commit()
    db.refresh(tenant)

    lic_plan: Optional[str] = None
    lic_status: Optional[str] = None
    try:
        from src.modules.licensing.service import get_license_status

        lic = get_license_status(db, int(customer.tenant_id), user_email=customer.email)
        lic_plan = str(lic.get("plan") or "") or None
        lic_status = str(lic.get("status") or "") or None
    except Exception:
        pass

    assert_kind = _normalize_assert_route(assert_route)
    slug_cmp = (assert_slug or "").strip().lower()
    if assert_kind and slug_cmp:
        expected_kind = _expected_route_kind_from_role(str(customer.role or ""))
        if assert_kind != expected_kind:
            write_global_audit_log(
                db,
                entity_type="workspace_route",
                entity_id=customer.tenant_id,
                action="workspace_route_denied",
                actor_user_id=customer.id,
                actor_role=str(customer.role or ""),
                tenant_id=customer.tenant_id,
                metadata={
                    "reason": "route_kind_role_mismatch",
                    "assert_route": assert_kind,
                    "expected_route_kind": expected_kind,
                    "asserted_slug": slug_cmp,
                    "resolved_slug": str(tenant.workspace_slug or ""),
                    "path": str(request.url.path),
                    "result": "denied",
                },
            )
            db.commit()
            raise HTTPException(
                status_code=403,
                detail={
                    "reason": "workspace_route_mismatch",
                    "default_app_path": build_default_app_path(db, customer, tenant),
                },
            )

        resolved = str(tenant.workspace_slug or "").strip().lower()
        if slug_cmp != resolved:
            write_global_audit_log(
                db,
                entity_type="workspace_route",
                entity_id=customer.tenant_id,
                action="workspace_route_denied",
                actor_user_id=customer.id,
                actor_role=str(customer.role or ""),
                tenant_id=customer.tenant_id,
                metadata={
                    "reason": "slug_mismatch",
                    "assert_route": assert_kind,
                    "asserted_slug": slug_cmp,
                    "resolved_slug": resolved,
                    "path": str(request.url.path),
                    "result": "denied",
                },
            )
            db.commit()
            raise HTTPException(
                status_code=403,
                detail={
                    "reason": "workspace_slug_mismatch",
                    "default_app_path": build_default_app_path(db, customer, tenant),
                },
            )

    default_path = build_default_app_path(db, customer, tenant)
    body = ApiMeAuthenticatedResponse(
        authenticated=True,
        account_type=map_account_type(str(customer.role or "")),
        account_id=int(customer.id),
        display_name=customer.name,
        email=str(customer.email or ""),
        account_slug=str(tenant.workspace_slug or ""),
        tenant_id=int(customer.tenant_id),
        workspace_route_kind=rk,
        default_app_path=default_path,
        role=str(customer.role or "user"),
        license_plan=lic_plan,
        license_status=lic_status,
        permissions={},
    )
    return body.model_dump()
