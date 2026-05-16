"""
Admin-only živý náhled posledních záznamů z nginx access logu (IP, UA, volitelně GeoIP).

Úmyslně neauditujeme každý poll — endpoint může být volaný často a logování každé odpovědi by zbytečně zahlcovalo audit.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import inspect as sql_inspect
from sqlalchemy.orm import Session

from src.core.config import (
    GEOIP_CITY_DATABASE_PATH,
    GOACCESS_REPORT_META_PATH,
    NGINX_ACCESS_LOG_PATH,
)
from src.modules.vehicle_hub.database import get_db
from src.modules.vehicle_hub.models import Customer, SecurityAccessLog
from src.server.admin_api import require_developer_admin

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin-traffic-live"])

# Apache combined / nginx default "combined" ($remote_addr může být i IPv6 bez hranatých závorek v některých zapojeních)
_COMBINED_RE = re.compile(
    r'^(?P<ip>\S+)\s+\S+\s+\S+\s+\[(?P<time_local>[^\]]+)\]\s+'
    r'"(?P<request>[^"]*)"\s+(?P<status>\d+)\s+(?P<bytes>\d+|-)\s+'
    r'"(?P<referrer>[^"]*)"\s+"(?P<ua>[^"]*)"\s*$'
)

_geo_reader: Any = None
_geo_reader_init_done: bool = False

_PRAGUE_TZ = ZoneInfo("Europe/Prague")

# Pro režim „jen zajímavé návštěvy“ (ménš šumu než surový log)
_INTERESTING_SKIP_PATHS = frozenset(
    {
        "/health",
        "/api/health",
        "/favicon.ico",
        "/robots.txt",
        "/sitemap.xml",
        "/.well-known/security.txt",
        "/admin-api/traffic/live/snapshot",
    }
)
_INTERESTING_SKIP_SUFFIXES = (
    ".js",
    ".mjs",
    ".css",
    ".map",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".json",
)
_INTERESTING_SKIP_PREFIXES = (
    "/static/",
    "/assets/",
    "/_next/",
    "/media/",
)

_DEVICE_LABEL_CZ = {
    "desktop": "počítač",
    "mobile": "mobil",
    "tablet": "tablet",
    "bot": "bot / nástroj",
    "other": "jiné zařízení",
}


class BrowserInfo(BaseModel):
    family: str = ""
    device: str = "desktop"  # desktop | mobile | tablet | bot | other


class LocationInfo(BaseModel):
    country: Optional[str] = None
    country_name: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    approximate: bool = Field(default=True, description="Odhad z GeoIP / HTTP služby, ne přesná adresa.")


def _read_meta_source_log() -> Optional[str]:
    p = Path(GOACCESS_REPORT_META_PATH)
    if not p.is_file():
        return None
    try:
        meta = json.loads(p.read_text(encoding="utf-8"))
        s = str(meta.get("source_log") or "").strip()
        return s or None
    except Exception:  # noqa: BLE001
        return None


def _resolve_access_log_path() -> Optional[Path]:
    """Stejná preference jako skript GoAccess: NGINX_ACCESS_LOG → výchozí cesty → meta.source_log."""
    if NGINX_ACCESS_LOG_PATH is not None:
        cand = NGINX_ACCESS_LOG_PATH.expanduser()
        try:
            if cand.is_file() and os.access(cand, os.R_OK):
                return cand.resolve()
        except OSError:
            pass

    for raw in ("/var/log/nginx/access.log", "/var/log/nginx/hub.access.log"):
        cand = Path(raw)
        try:
            if cand.is_file() and os.access(cand, os.R_OK):
                return cand.resolve()
        except OSError:
            continue

    from_meta = _read_meta_source_log()
    if from_meta:
        cand = Path(from_meta).expanduser()
        try:
            if cand.is_file() and os.access(cand, os.R_OK):
                return cand.resolve()
        except OSError:
            pass

    return None


def _read_last_complete_lines(path: Path, *, max_lines: int, max_scan_bytes: int) -> list[str]:
    max_lines = max(1, min(max_lines, 5000))
    with path.open("rb") as f:
        f.seek(0, os.SEEK_END)
        size = f.tell()
        if size == 0:
            return []
        chunk_sz = min(max_scan_bytes, size)
        f.seek(-chunk_sz, os.SEEK_END)
        raw = f.read(chunk_sz)
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if chunk_sz < size and lines:
        lines = lines[1:]
    return lines[-max_lines:]


def _parse_request(req: str) -> tuple[str, str]:
    req = (req or "").strip()
    if not req:
        return "", ""
    parts = req.split(maxsplit=2)
    method = parts[0] if parts else ""
    path = parts[1] if len(parts) > 1 else ""
    return method, path


def _classify_user_agent(ua: str) -> BrowserInfo:
    s = (ua or "").strip()
    low = s.lower()
    if not s:
        return BrowserInfo(family="(prázdný)", device="other")

    bot_tokens = (
        "bot",
        "crawler",
        "spider",
        "slurp",
        "mediapartners-google",
        "facebookexternalhit",
        "pingdom",
        "uptime",
        "curl/",
        "wget/",
        "python-requests",
        "axios/",
        "go-http-client",
        "okhttp",
    )
    if any(t in low for t in bot_tokens):
        return BrowserInfo(family="bot / nástroj", device="bot")

    mobile = "mobile" in low or "iphone" in low or "android" in low
    tablet = "ipad" in low or "tablet" in low

    family = "Neznámý"
    if "edg/" in low or "edga/" in low or "edgios/" in low:
        family = "Edge"
    elif "opr/" in low or "opera" in low:
        family = "Opera"
    elif "chrome/" in low and "chromium" not in low:
        family = "Chrome"
    elif "firefox/" in low:
        family = "Firefox"
    elif "safari/" in low and "chrome" not in low:
        family = "Safari"

    if tablet:
        dev = "tablet"
    elif mobile and "android" in low and "like mac" not in low:
        dev = "mobile"
    elif "iphone" in low or ("android" in low and "mobile" in low):
        dev = "mobile"
    elif mobile:
        dev = "mobile"
    else:
        dev = "desktop"

    return BrowserInfo(family=family, device=dev)


def _get_geo_reader() -> Any:
    global _geo_reader, _geo_reader_init_done
    if _geo_reader_init_done:
        return _geo_reader
    _geo_reader_init_done = True
    path = GEOIP_CITY_DATABASE_PATH
    if path is None or not path.is_file():
        _geo_reader = None
        return None
    try:
        import geoip2.database  # type: ignore[import-not-found]

        _geo_reader = geoip2.database.Reader(str(path))
        return _geo_reader
    except Exception as exc:  # noqa: BLE001
        logger.warning("[traffic-live] GeoIP Reader: %s", exc)
        _geo_reader = None
        return None


def _parse_time_local_to_utc(value: str) -> Optional[datetime]:
    """Nginx combined time, např. 15/May/2026:12:00:00 +0000."""
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%d/%b/%Y:%H:%M:%S %z")
    except ValueError:
        return None


def _where_geo_human(loc: Optional[dict[str, Any]]) -> str:
    if not loc:
        return "místo nelze určit"
    cname = str(loc.get("country_name") or loc.get("country") or "").strip()
    if cname == "Privátní / lokální síť":
        return cname
    city = loc.get("city")
    region = loc.get("region")
    parts = [p for p in (city, region, cname) if p]
    return ", ".join(parts) if parts else "místo nelze určit"


def _referrer_human(referrer: str) -> tuple[str, str]:
    """
    Krátký a dlouhý popis odkud přišel HTTP odkaz (Referer).
    Vrací (krátký_label, detail_pro_title).
    """
    ref = (referrer or "").strip()
    if ref in {"", "-"}:
        return "přímo / bez odkazu", ""
    detail = ref[:500]
    try:
        p = urlparse(ref)
        host = (p.netloc or "").lower()
        if host.startswith("www."):
            host = host[4:]
        if host:
            path_bit = (p.path or "").strip("/")
            if path_bit and len(path_bit) < 48:
                return host, f"{ref}"
            return host, f"{ref}"
        return "externí odkaz", detail
    except Exception:  # noqa: BLE001
        return "odkudsi", detail


def _is_interesting_visit(row: dict[str, Any]) -> bool:
    br = row.get("browser") or {}
    if br.get("device") == "bot":
        return False
    method = str(row.get("method") or "").upper()
    if method == "HEAD":
        return False
    path = str(row.get("path") or "").split("?")[0].strip() or "/"
    low = path.lower()
    if path in _INTERESTING_SKIP_PATHS or low in _INTERESTING_SKIP_PATHS:
        return False
    for suf in _INTERESTING_SKIP_SUFFIXES:
        if low.endswith(suf):
            return False
    for pref in _INTERESTING_SKIP_PREFIXES:
        if low.startswith(pref):
            return False
    return True


def _attach_summary(row: dict[str, Any]) -> dict[str, Any]:
    br = row.get("browser") or {}
    family = str(br.get("family") or "neznámý prohlížeč")
    dev_key = str(br.get("device") or "other")
    dev_cz = _DEVICE_LABEL_CZ.get(dev_key, dev_key)
    who = f"{family} · {dev_cz}"

    dt = _parse_time_local_to_utc(str(row.get("time_local") or ""))
    if dt is not None:
        prague = dt.astimezone(_PRAGUE_TZ)
        when_prague = prague.strftime("%d.%m.%Y %H:%M:%S")
        when_iso = dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        when_prague = str(row.get("time_local") or "")
        when_iso = ""

    where = _where_geo_human(row.get("location"))
    ref_short, ref_detail = _referrer_human(str(row.get("referrer") or ""))

    method = str(row.get("method") or "")
    path = str(row.get("path") or "")
    status = row.get("status")
    what = f"{method} {path}".strip()
    if len(what) > 120:
        what = what[:117] + "…"

    row["summary"] = {
        "when_prague": when_prague,
        "when_iso_utc": when_iso,
        "who": who,
        "ip": str(row.get("ip") or ""),
        "where": where,
        "from_link": ref_short,
        "from_link_detail": ref_detail,
        "what": what,
        "status": int(status) if status is not None else None,
    }
    return row


def _lookup_location(ip: str) -> Optional[LocationInfo]:
    ip = (ip or "").strip()
    if not ip:
        return None

    reader = _get_geo_reader()
    if reader is not None:
        try:
            resp = reader.city(ip)
            city_name = resp.city.name
            cc = resp.country.iso_code
            cname = resp.country.name
            lat = resp.location.latitude
            lon = resp.location.longitude
            reg = None
            if resp.subdivisions:
                reg = resp.subdivisions[0].name
            return LocationInfo(
                country=cc,
                country_name=cname,
                city=city_name,
                region=reg,
                latitude=float(lat) if lat is not None else None,
                longitude=float(lon) if lon is not None else None,
                approximate=True,
            )
        except Exception:  # noqa: BLE001
            pass

    try:
        from src.server.security_tracking import is_http_ip_geolookup_enabled, lookup_ip_location
    except Exception:  # noqa: BLE001
        return None
    if not is_http_ip_geolookup_enabled():
        return None
    geo = lookup_ip_location(ip)
    if not geo:
        return None
    if geo.get("source") == "private":
        return LocationInfo(
            country=None,
            country_name="Privátní / lokální síť",
            city=None,
            region=None,
            latitude=None,
            longitude=None,
            approximate=True,
        )

    city = geo.get("city")
    region = geo.get("region") or geo.get("regionName")
    country = geo.get("country")
    lat = geo.get("latitude") or geo.get("lat")
    lon = geo.get("longitude") or geo.get("lon")

    return LocationInfo(
        country=None,
        country_name=str(country) if country else None,
        city=str(city) if city else None,
        region=str(region) if region else None,
        latitude=float(lat) if lat is not None else None,
        longitude=float(lon) if lon is not None else None,
        approximate=True,
    )


def _parse_combined_line(line: str) -> Optional[dict[str, Any]]:
    line = line.strip()
    if not line:
        return None
    m = _COMBINED_RE.match(line)
    if not m:
        return None
    status = int(m.group("status"))
    bs_raw = m.group("bytes")
    try:
        bytes_sent = int(bs_raw) if bs_raw.isdigit() else 0
    except ValueError:
        bytes_sent = 0
    method, path = _parse_request(m.group("request"))
    ua = m.group("ua")
    browser = _classify_user_agent(ua)
    ip = m.group("ip")
    loc = _lookup_location(ip)
    return {
        "time_local": m.group("time_local"),
        "ip": ip,
        "method": method,
        "path": path,
        "status": status,
        "bytes_sent": bytes_sent,
        "referrer": m.group("referrer"),
        "user_agent_raw": ua,
        "browser": browser.model_dump(),
        "location": loc.model_dump() if loc else None,
    }


@router.get("/traffic/live/snapshot")
def traffic_live_snapshot(
    _: str = Depends(require_developer_admin),
    limit: int = Query(40, ge=1, le=200),
    interesting_only: bool = Query(
        True,
        description="Omezit na návštěvy stránek/API; vynechat statiky, běžné boty, HEAD a health.",
    ),
) -> dict[str, Any]:
    log_path = _resolve_access_log_path()
    if log_path is None:
        raise HTTPException(
            status_code=503,
            detail="Nepodařilo se najít čitelný nginx access log (NGINX_ACCESS_LOG nebo /var/log/nginx/...).",
        )

    scan_lines = (
        min(max(limit * 30, 300), 25000)
        if interesting_only
        else min(max(limit * 6, 120), 8000)
    )
    lines = _read_last_complete_lines(
        log_path, max_lines=scan_lines, max_scan_bytes=min(3 * 1024 * 1024, 12 * 1024 * 1024)
    )
    items: list[dict[str, Any]] = []
    for line in reversed(lines):
        parsed = _parse_combined_line(line)
        if not parsed:
            continue
        if interesting_only and not _is_interesting_visit(parsed):
            continue
        items.append(_attach_summary(parsed))
        if len(items) >= limit:
            break
    items.reverse()

    maxmind_ok = _get_geo_reader() is not None
    from src.server.security_tracking import is_http_ip_geolookup_enabled

    http_geo_ok = is_http_ip_geolookup_enabled()
    geo_effective = maxmind_ok or http_geo_ok

    geoip_hint: Optional[str] = None
    if not geo_effective:
        geoip_hint = (
            "Geolokace je vypnutá: nastavte ENABLE_IP_GEOLOOKUP=1 (výchozí stav), "
            "nebo použijte MaxMind (GEOIP_CITY_DATABASE_PATH nebo soubor data/GeoLite2-City.mmdb)."
        )

    return {
        "ok": True,
        "source_log": str(log_path),
        "visit_filter": "interesting" if interesting_only else "all",
        "geo_maxmind": maxmind_ok,
        "geo_http_lookup": http_geo_ok,
        "geoip_configured": geo_effective,
        "geoip_hint": geoip_hint,
        "items": items,
    }


def _db_ts_to_prague_iso(dt: Optional[datetime]) -> tuple[str, str]:
    if dt is None:
        return "", ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    iso = dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    prg = dt.astimezone(_PRAGUE_TZ).strftime("%d.%m.%Y %H:%M:%S")
    return prg, iso


def _security_row_to_visit_payload(r: SecurityAccessLog, names: dict[int, str]) -> dict[str, Any]:
    prg, iso = _db_ts_to_prague_iso(r.created_at)
    loc_parts = [p for p in (r.city, r.region, r.country) if p]
    where = ", ".join(loc_parts) if loc_parts else (r.source or "—")
    ua = r.user_agent or ""
    if len(ua) > 140:
        ua = ua[:137] + "…"
    event_label = "Přihlášení" if r.event_type == "login_success" else "API / aktivita"
    who_display = r.user_email
    if r.customer_id and r.customer_id in names:
        disp = names[r.customer_id].strip()
        if disp:
            who_display = f"{disp} ({r.user_email})" if r.user_email else disp
    return {
        "id": r.id,
        "event_type": r.event_type,
        "event_label": event_label,
        "when_prague": prg,
        "when_iso_utc": iso,
        "who_email": r.user_email,
        "who_display": who_display,
        "customer_id": r.customer_id,
        "endpoint": r.endpoint,
        "ip": r.ip_address,
        "where": where,
        "user_agent_short": ua or None,
    }


@router.get("/traffic/app-visits")
def traffic_app_visits(
    _: str = Depends(require_developer_admin),
    db: Session = Depends(get_db),
    limit: int = Query(80, ge=1, le=400),
) -> dict[str, Any]:
    """
    Přehled „kdo – odkud – kdy“ z aplikace: záznamy z autentizované aktivity (`api_activity`, `login_success`)
    v tabulce `security_access_logs` (IP geolokace stejně jako u bezpečnostního logu).
    """
    if not sql_inspect(db.bind).has_table("security_access_logs"):
        return {
            "ok": True,
            "source": "security_access_logs",
            "items": [],
            "note": "Tabulka security_access_logs v DB není k dispozici.",
        }

    rows = (
        db.query(SecurityAccessLog)
        .filter(SecurityAccessLog.event_type.in_(("api_activity", "login_success")))
        .order_by(SecurityAccessLog.created_at.desc(), SecurityAccessLog.id.desc())
        .limit(limit)
        .all()
    )
    cust_ids = {r.customer_id for r in rows if r.customer_id}
    names: dict[int, str] = {}
    if cust_ids:
        for c in db.query(Customer).filter(Customer.id.in_(cust_ids)).all():
            nm = (c.name or "").strip()
            names[c.id] = nm or (c.email or "")

    items = [_security_row_to_visit_payload(r, names) for r in rows]
    return {
        "ok": True,
        "source": "security_access_logs",
        "hint": (
            "Údaje vznikají z přihlášených požadavků (JWT). Neanonymní návštěvníci bez přihlášení "
            "jsou jen v tabulce z nginx logu níže."
        ),
        "items": items,
    }
