"""
Admin-only přehled návštěvnosti (GoAccess / nginx access log).
"""
from __future__ import annotations

import hashlib
import json
import logging
import subprocess
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from sqlalchemy.orm import Session

from src.core.config import (
    APP_ROOT,
    GOACCESS_REPORT_HTML_PATH,
    GOACCESS_REPORT_META_PATH,
    GOACCESS_REPORT_SCRIPT_PATH,
)
from src.modules.vehicle_hub.audit_log import write_global_audit_log
from src.modules.vehicle_hub.database import get_db
from src.modules.vehicle_hub.models import Customer
from src.server.admin_api import get_user_id_from_email, require_developer_admin
from src.server.security_tracking import extract_client_ip

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin-api", tags=["admin-traffic"])


def _resolve_report_script() -> Optional[Path]:
    candidates = (
        Path(GOACCESS_REPORT_SCRIPT_PATH),
        APP_ROOT / "scripts" / "admin_generate_traffic_report.sh",
    )
    for p in candidates:
        try:
            r = p.resolve()
            if r.is_file():
                return r
        except OSError:
            continue
    return None


def _ip_hash_for_audit(request: Request) -> Optional[str]:
    raw = extract_client_ip(request) or (request.client.host if request.client else None) or ""
    raw = str(raw).strip()
    if not raw:
        return None
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _read_meta() -> Optional[dict[str, Any]]:
    p = Path(GOACCESS_REPORT_META_PATH)
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _audit_traffic(
    db: Session,
    *,
    admin_email: str,
    request: Request,
    action: str,
    extra: Optional[dict[str, Any]] = None,
) -> None:
    uid = get_user_id_from_email(admin_email, db)
    c = db.query(Customer).filter(Customer.email == admin_email).first()
    role = str(c.role) if c else None
    meta = dict(extra or {})
    meta["path"] = str(request.url.path)
    try:
        write_global_audit_log(
            db,
            entity_type="traffic_analytics",
            entity_id=None,
            action=action,
            actor_user_id=uid,
            actor_role=role,
            metadata=meta,
            ip=_ip_hash_for_audit(request),
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("[traffic] audit selhal: %s", exc)


@router.get("/traffic/report/status")
def traffic_report_status(_: str = Depends(require_developer_admin)):
    meta = _read_meta()
    html_path = Path(GOACCESS_REPORT_HTML_PATH)
    out = {
        "report_exists": html_path.is_file() and html_path.stat().st_size > 0,
        "report_path": str(html_path),
        "meta": meta,
    }
    return JSONResponse(out)


@router.get("/traffic/report")
def traffic_report_html(
    request: Request,
    admin_email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    p = Path(GOACCESS_REPORT_HTML_PATH)
    if not p.is_file() or p.stat().st_size == 0:
        detail_html = (
            "<!DOCTYPE html><html><head><meta charset='utf-8'><title>Návštěvnost</title></head><body>"
            "<p><strong>Přehled není k dispozici.</strong></p>"
            "<p>Spusťte <code>scripts/admin_generate_traffic_report.sh</code>, tlačítko „Obnovit přehled“, "
            "nebo systemd timer <code>sprava-vozidel-goaccess-report.timer</code>.</p>"
            "</body></html>"
        )
        _audit_traffic(
            db,
            admin_email=admin_email,
            request=request,
            action="traffic_report_view_missing",
            extra={"result": "missing"},
        )
        return HTMLResponse(content=detail_html, status_code=404)

    _audit_traffic(
        db,
        admin_email=admin_email,
        request=request,
        action="traffic_report_view",
        extra={"result": "ok", "bytes": p.stat().st_size},
    )
    try:
        body = p.read_bytes()
    except OSError as exc:
        logger.warning("[traffic] read report: %s", exc)
        raise HTTPException(status_code=503, detail="Report se nepodařilo přečíst.") from exc

    return Response(
        content=body,
        media_type="text/html; charset=utf-8",
        headers={"Cache-Control": "no-store"},
    )


@router.post("/traffic/report/regenerate")
def traffic_report_regenerate(
    request: Request,
    admin_email: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
):
    script = _resolve_report_script()
    if script is None:
        logger.error(
            "[traffic] chybí skript generátoru (kontrolovány: %s, %s)",
            Path(GOACCESS_REPORT_SCRIPT_PATH),
            APP_ROOT / "scripts" / "admin_generate_traffic_report.sh",
        )
        raise HTTPException(
            status_code=503,
            detail="Generátor na serveru chybí. Nasadte soubor scripts/admin_generate_traffic_report.sh do adresáře aplikace.",
        )

    _audit_traffic(
        db,
        admin_email=admin_email,
        request=request,
        action="traffic_report_regenerate_requested",
        extra={"script": str(script.name)},
    )

    try:
        proc = subprocess.run(
            ["/bin/bash", str(script)],
            cwd=str(APP_ROOT),
            capture_output=True,
            text=True,
            timeout=300,
            shell=False,
        )
    except subprocess.TimeoutExpired:
        logger.warning("[traffic] regenerate timeout")
        raise HTTPException(status_code=504, detail="Generování trvalo příliš dlouho.") from None
    except OSError as exc:
        logger.warning("[traffic] regenerate exec: %s", exc)
        raise HTTPException(status_code=503, detail="Generování se nepodařilo spustit.") from exc

    if proc.returncode != 0:
        logger.warning("[traffic] regenerate exit %s", proc.returncode)

    meta = _read_meta() or {}
    if not meta.get("ok"):
        hint = str(meta.get("error") or "Neznámá chyba generátoru.")
        raise HTTPException(status_code=503, detail=f"Přehled se nepodařilo vytvořit: {hint}")

    html_path = Path(GOACCESS_REPORT_HTML_PATH)
    if not html_path.is_file() or html_path.stat().st_size == 0:
        raise HTTPException(
            status_code=503,
            detail="Přehled byl označen jako vygenerovaný, ale soubor chybí.",
        )

    uid = get_user_id_from_email(admin_email, db)
    c = db.query(Customer).filter(Customer.email == admin_email).first()
    try:
        write_global_audit_log(
            db,
            entity_type="traffic_analytics",
            entity_id=None,
            action="traffic_report_regenerated",
            actor_user_id=uid,
            actor_role=str(c.role) if c else None,
            metadata={
                "source_log": meta.get("source_log"),
                "report_path": str(html_path),
                "generated_at": meta.get("generated_at"),
            },
            ip=_ip_hash_for_audit(request),
        )
        db.commit()
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("[traffic] audit po regenerate: %s", exc)

    return {
        "ok": True,
        "report_path": str(html_path),
        "generated_at": meta.get("generated_at"),
        "source_log": meta.get("source_log"),
    }


# Živý náhled z access logu — stejný router jako GoAccess, aby nasazení vždy zaregistrovalo obě části.
from src.server.admin_traffic_live import router as _traffic_live_inner_router  # noqa: E402

router.include_router(_traffic_live_inner_router)
