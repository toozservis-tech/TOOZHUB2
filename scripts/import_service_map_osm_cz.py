#!/usr/bin/env python3
"""
Import servisní mapy z OpenStreetMap (Overpass JSON) pro ČR.

Nepoužívá Google Maps ani Mapy.com jako zdroj katalogu – pouze Overpass API / JSON soubor.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.modules.vehicle_hub.database import SessionLocal
from src.modules.vehicle_hub.service_map.osm_importer import import_osm_overpass_json
from src.modules.vehicle_hub.service_map.regions_cz import (
    CZ_REGION_BBOXES,
    build_overpass_query,
    build_overpass_test_query,
    import_region_keys,
    region_keys,
    split_bbox,
)

USER_AGENT = "SpravaVozidel/1.0 toozservis.cz toozservis@gmail.com"
DEFAULT_OVERPASS_URL = "https://overpass-api.de/api/interpreter"
DEFAULT_FALLBACK_URLS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://z.overpass-api.de/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
]
RETRYABLE_HTTP = {406, 429, 500, 502, 503, 504}


def log(phase: str, message: str) -> None:
    print(f"[{phase}] {message}", flush=True)


def _default_overpass_url() -> str:
    return (os.getenv("OVERPASS_API_URL") or DEFAULT_OVERPASS_URL).strip()


def _collect_overpass_urls(args: argparse.Namespace, *, include_defaults: bool = True) -> list[str]:
    urls: list[str] = []
    primary = (args.overpass_url or _default_overpass_url()).strip()
    if primary:
        urls.append(primary)
    for item in args.overpass_fallback_url or []:
        u = str(item).strip()
        if u and u not in urls:
            urls.append(u)
    if include_defaults:
        for fallback in DEFAULT_FALLBACK_URLS:
            if fallback not in urls:
                urls.append(fallback)
    return urls


def _validate_overpass_payload(payload: Any, *, context: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        raise SystemExit(f"ERROR: {context}: odpověď není JSON objekt.")
    elements = payload.get("elements")
    if elements is None:
        raise SystemExit(f"ERROR: {context}: JSON nemá klíč 'elements'.")
    if not isinstance(elements, list):
        raise SystemExit(f"ERROR: {context}: 'elements' není pole.")
    return elements


def _load_json_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"ERROR: Soubor neexistuje: {path}")
    size = path.stat().st_size
    if size <= 0:
        raise SystemExit(f"ERROR: Soubor je prázdný (0 B): {path}")
    log("CONFIG", f"Načítám JSON soubor {path} ({size} B)")
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"ERROR: Nevalidní JSON v {path}: {exc}") from exc
    elements = _validate_overpass_payload(payload, context=str(path))
    log("JSON VALIDATED", f"{path.name}: {len(elements)} elements")
    return payload


def _merge_elements(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    unique: dict[tuple[str, int], dict[str, Any]] = {}
    for payload in payloads:
        for element in payload.get("elements") or []:
            if not isinstance(element, dict):
                continue
            eid = element.get("id")
            if eid is None:
                continue
            key = (str(element.get("type") or "node"), int(eid))
            unique[key] = element
    return {"elements": list(unique.values())}


def _fetch_overpass_once(
    url: str,
    query: str,
    *,
    connect_timeout: float,
    read_timeout: float,
) -> tuple[int, bytes]:
    log("FETCH START", f"endpoint={url} connect_timeout={connect_timeout}s read_timeout={read_timeout}s")
    resp = requests.post(
        url,
        data={"data": query},
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
        timeout=(connect_timeout, read_timeout),
    )
    status = int(resp.status_code)
    raw = resp.content
    log("FETCH DONE", f"endpoint={url} status={status} bytes={len(raw)}")
    return status, raw


def _fetch_overpass_with_retries(
    urls: list[str],
    query: str,
    *,
    connect_timeout: float,
    read_timeout: float,
    max_retries: int,
    context: str,
) -> dict[str, Any]:
    last_error = ""
    for url in urls:
        attempts = max(1, int(max_retries) + 1)
        for attempt in range(1, attempts + 1):
            try:
                status, raw = _fetch_overpass_once(
                    url,
                    query,
                    connect_timeout=connect_timeout,
                    read_timeout=read_timeout,
                )
                text = raw.decode("utf-8", errors="replace")
                if status in RETRYABLE_HTTP or not text.strip().startswith("{"):
                    snippet = text[:800]
                    last_error = f"HTTP {status} from {url}: {snippet}"
                    log("FETCH ERROR", last_error)
                    if attempt < attempts:
                        time.sleep(min(2.0 * attempt, 8.0))
                        continue
                    break
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError as exc:
                    snippet = text[:800]
                    raise SystemExit(
                        f"ERROR: {context}: nevalidní JSON z {url} (HTTP {status}).\n"
                        f"Prvních 800 znaků:\n{snippet}\n"
                        f"Doporučení: --overpass-url https://lz4.overpass-api.de/api/interpreter nebo --download-only + --file"
                    ) from exc
                _validate_overpass_payload(payload, context=context)
                return payload
            except requests.HTTPError as exc:
                body = (exc.response.text if exc.response is not None else str(exc))[:800]
                code = exc.response.status_code if exc.response is not None else 0
                last_error = f"HTTP {code} from {url}: {body}"
                log("FETCH ERROR", last_error)
                if code in RETRYABLE_HTTP and attempt < attempts:
                    time.sleep(min(2.0 * attempt, 8.0))
                    continue
                break
            except requests.RequestException as exc:
                last_error = f"Request error {url}: {exc}"
                log("FETCH ERROR", last_error)
                if attempt < attempts:
                    time.sleep(min(2.0 * attempt, 8.0))
                    continue
                break
    raise SystemExit(
        f"ERROR: Overpass fetch selhal ({context}).\n"
        f"Poslední chyba: {last_error}\n"
        f"Doporučení:\n"
        f"  --overpass-url https://lz4.overpass-api.de/api/interpreter\n"
        f"  --overpass-fallback-url https://overpass.openstreetmap.fr/api/interpreter\n"
        f"  --download-only --save-json /tmp/osm_import\n"
        f"  poté import přes --file /tmp/osm_import/<soubor>.json\n"
        f"Ruční stažení JSON na jiném stroji a scp na server je také OK."
    )


def _resolve_region(args: argparse.Namespace) -> tuple[str, str, float, float, float, float]:
    if args.region:
        key = args.region.strip().lower()
        if key not in CZ_REGION_BBOXES:
            raise SystemExit(f"Neznámý region '{key}'. Dostupné: {', '.join(region_keys())}")
        box = CZ_REGION_BBOXES[key]
        return key, str(box["label"]), float(box["south"]), float(box["west"]), float(box["north"]), float(box["east"])
    if args.bbox:
        parts = [float(x.strip()) for x in args.bbox.split(",")]
        if len(parts) != 4:
            raise SystemExit("--bbox musí být south,west,north,east")
        return "custom", "custom-bbox", parts[0], parts[1], parts[2], parts[3]
    raise SystemExit("Zadejte --region nebo --bbox pro fetch režim.")


def _save_json_path(save_json: Path | None, region_key: str) -> Path | None:
    if save_json is None:
        return None
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    if save_json.suffix.lower() == ".json":
        save_json.parent.mkdir(parents=True, exist_ok=True)
        return save_json
    save_json.mkdir(parents=True, exist_ok=True)
    return save_json / f"{region_key}_{ts}.json"


def _fetch_region_payload(
    args: argparse.Namespace,
    *,
    region_key: str,
    label: str,
    south: float,
    west: float,
    north: float,
    east: float,
) -> dict[str, Any]:
    urls = _collect_overpass_urls(args)
    log("REGION", f"{label} ({region_key}) bbox=({south},{west},{north},{east})")
    log("CONFIG", f"Overpass URLs: {', '.join(urls)}")

    tiles: list[tuple[float, float, float, float]] = [(south, west, north, east)]
    if args.split_bbox:
        grid = 2 if region_key in {"pardubicky", "stredocesky", "jihomoravsky", "moravskoslezsky"} else 2
        tiles = split_bbox(south, west, north, east, tiles=grid)
        log("CONFIG", f"split-bbox: {len(tiles)} dlaždic")

    payloads: list[dict[str, Any]] = []
    for idx, (ts, tw, tn, te) in enumerate(tiles, start=1):
        query = build_overpass_query(south=ts, west=tw, north=tn, east=te, timeout=int(args.read_timeout))
        if args.query_debug:
            print(f"--- QUERY {region_key} tile {idx}/{len(tiles)} ---", flush=True)
            print(query, flush=True)
        log("QUERY BUILT", f"tile {idx}/{len(tiles)} timeout={args.read_timeout}s")
        payload = _fetch_overpass_with_retries(
            urls,
            query,
            connect_timeout=args.connect_timeout,
            read_timeout=args.read_timeout,
            max_retries=args.max_retries,
            context=f"{label} tile {idx}",
        )
        count = len(payload.get("elements") or [])
        log("JSON VALIDATED", f"tile {idx}: {count} elements")
        if count == 0:
            log(
                "WARNING",
                f"Overpass returned 0 elements for {label} tile {idx} bbox=({ts},{tw},{tn},{te})",
            )
        payloads.append(payload)
        if len(tiles) > 1 and idx < len(tiles):
            time.sleep(max(0.0, float(args.sleep)))

    merged = _merge_elements(payloads) if len(payloads) > 1 else payloads[0]
    total = len(merged.get("elements") or [])
    if total == 0:
        log(
            "WARNING",
            f"Overpass returned 0 elements for region {label} ({region_key}) bbox=({south},{west},{north},{east})",
        )
    else:
        log("JSON VALIDATED", f"region {region_key}: merged {total} elements")
    return merged


def _print_stats(label: str, stats: dict[str, Any]) -> None:
    log("STATS", f"=== {label} ===")
    for key in (
        "import_batch_id",
        "elements_total",
        "inserted",
        "updated",
        "duplicates_suspected",
        "skipped_invalid",
        "protected_skipped",
    ):
        if key in stats:
            print(f"  {key}: {stats[key]}", flush=True)
    if stats.get("categories_count"):
        print("  categories_count:", flush=True)
        for cat, count in sorted(stats["categories_count"].items(), key=lambda item: (-item[1], item[0])):
            print(f"    {cat}: {count}", flush=True)
    log("DB VERIFY HINT", "sqlite3 /opt/toozhub2-staging/data/vehicles_staging.db \"SELECT source_type,COUNT(*) FROM service_locations GROUP BY source_type;\"")


def run_test_overpass(args: argparse.Namespace) -> int:
    urls = _collect_overpass_urls(args, include_defaults=False)
    query = build_overpass_test_query(timeout=min(25, int(args.read_timeout)))
    log("CONFIG", f"test-overpass URLs: {', '.join(urls)}")
    if args.query_debug:
        print(query, flush=True)
    try:
        payload = _fetch_overpass_with_retries(
            urls,
            query,
            connect_timeout=args.connect_timeout,
            read_timeout=min(30.0, float(args.read_timeout)),
            max_retries=args.max_retries,
            context="test-overpass",
        )
        count = len(payload.get("elements") or [])
        log("STATS", f"test-overpass PASS: {count} elements")
        return 0
    except SystemExit as exc:
        log("STATS", f"test-overpass FAIL: {exc}")
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Import OSM servisní mapy (ČR)")
    parser.add_argument("--file", type=Path, help="Overpass JSON soubor")
    parser.add_argument("--region", help=f"Kraj/bbox preset ({', '.join(region_keys())})")
    parser.add_argument("--bbox", help="south,west,north,east")
    parser.add_argument("--all-regions", action="store_true", help="Import postupně všechny kraje")
    parser.add_argument("--fetch-overpass", action="store_true", help="Stáhnout data z Overpass API")
    parser.add_argument("--download-only", action="store_true", help="Jen stáhnout JSON, neimportovat")
    parser.add_argument("--save-json", type=Path, help="Uložit stažený Overpass JSON (soubor nebo adresář)")
    parser.add_argument("--overpass-url", help="Primární Overpass endpoint")
    parser.add_argument(
        "--overpass-fallback-url",
        action="append",
        help="Fallback Overpass endpoint (lze opakovat)",
    )
    parser.add_argument("--query-debug", action="store_true", help="Vypsat Overpass query")
    parser.add_argument("--connect-timeout", type=float, default=15.0, help="Connect timeout (s)")
    parser.add_argument("--read-timeout", type=float, default=180.0, help="Read timeout (s)")
    parser.add_argument("--max-retries", type=int, default=2, help="Počet retry na endpoint")
    parser.add_argument("--timeout", type=int, default=None, help="Alias pro --read-timeout (legacy)")
    parser.add_argument("--batch-id", help="Vlastní import_batch_id")
    parser.add_argument("--dry-run", action="store_true", help="Jen validace, bez zápisu do DB")
    parser.add_argument("--sleep", type=float, default=8.0, help="Pauza mezi regiony/dlaždicemi (s)")
    parser.add_argument("--split-bbox", action="store_true", help="Velké regiony stáhnout po dlaždicích")
    parser.add_argument("--test-overpass", action="store_true", help="Malý Overpass test bez DB")
    args = parser.parse_args()

    if args.timeout is not None:
        args.read_timeout = float(args.timeout)

    log("CONFIG", f"cwd={Path.cwd()} OVERPASS_API_URL={os.getenv('OVERPASS_API_URL') or '(default)'}")

    if args.test_overpass:
        return run_test_overpass(args)

    jobs: list[tuple[str, dict[str, Any], str | None, Path | None]] = []

    if args.file:
        payload = _load_json_file(args.file)
        elements = payload.get("elements") or []
        if len(elements) == 0:
            log("WARNING", f"Soubor {args.file} obsahuje 0 elements – import pravděpodobně nic nepřidá.")
        batch_id = args.batch_id or f"osm-file-{uuid.uuid4().hex[:8]}"
        jobs.append((args.file.name, payload, batch_id, None))
    elif args.all_regions:
        if not args.fetch_overpass:
            raise SystemExit("Pro --all-regions použijte --fetch-overpass.")
        blocked_log = Path("/tmp/osm_import/blocked_regions.log")
        blocked_log.parent.mkdir(parents=True, exist_ok=True)
        for key in import_region_keys():
            if key == "svitavy_test":
                continue
            box = CZ_REGION_BBOXES[key]
            label = str(box["label"])
            try:
                payload = _fetch_region_payload(
                    args,
                    region_key=key,
                    label=label,
                    south=float(box["south"]),
                    west=float(box["west"]),
                    north=float(box["north"]),
                    east=float(box["east"]),
                )
            except SystemExit as exc:
                msg = f"BLOCKED region={key} label={label} reason={exc}"
                log("WARNING", msg)
                blocked_log.open("a", encoding="utf-8").write(msg + "\n")
                time.sleep(max(0.0, float(args.sleep)))
                continue
            out_path = _save_json_path(args.save_json, key)
            if out_path:
                out_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
                log("FETCH DONE", f"Uloženo: {out_path}")
            if not args.download_only and not args.dry_run:
                jobs.append((label, payload, args.batch_id or f"osm-cz-{key}-{uuid.uuid4().hex[:8]}", out_path))
            elif args.dry_run:
                jobs.append((label, payload, None, out_path))
            time.sleep(max(0.0, float(args.sleep)))
    elif args.fetch_overpass:
        key, label, south, west, north, east = _resolve_region(args)
        payload = _fetch_region_payload(args, region_key=key, label=label, south=south, west=west, north=north, east=east)
        out_path = _save_json_path(args.save_json, key)
        if out_path:
            out_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            log("FETCH DONE", f"Uloženo: {out_path}")
        if args.download_only:
            log("STATS", f"download-only hotovo: {len(payload.get('elements') or [])} elements → {out_path or '(not saved)'}")
            return 0
        batch_id = args.batch_id or f"osm-{key}-{uuid.uuid4().hex[:8]}"
        jobs.append((label, payload, batch_id, out_path))
    else:
        parser.error("Zadejte --file, --test-overpass, nebo (--region|--bbox|--all-regions) s --fetch-overpass")

    if args.dry_run:
        for label, payload, _bid, _path in jobs:
            count = len(payload.get("elements") or [])
            log("DRY-RUN", f"{label}: {count} elements (bez zápisu do DB)")
        return 0

    if args.download_only:
        return 0

    db = SessionLocal()
    try:
        for label, payload, batch_id, _path in jobs:
            count = len(payload.get("elements") or [])
            if count == 0:
                log("WARNING", f"Přeskakuji import {label}: 0 elements")
                continue
            log("IMPORT START", f"{label} batch_id={batch_id} elements={count}")
            stats = import_osm_overpass_json(db, payload, import_batch_id=batch_id)
            log("IMPORT DONE", f"{label} batch_id={stats.get('import_batch_id')}")
            _print_stats(label, stats)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
