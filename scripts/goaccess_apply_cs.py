#!/usr/bin/env python3
"""
České popisky ve statickém HTML z GoAccess — pouze cílené náhravy uvnitř JSON řetězců,
aby se nerozbil minifikovaný JS (např. getTotalLength, getDataByKey).
"""
from __future__ import annotations

import sys
from pathlib import Path

# Přesné dílčí řetězce z výstupu GoAccess; pořadí: nejdelší první.
_SAFE_FRAGMENTS: tuple[tuple[str, str], ...] = (
    (
        '"desc": "Top not found URLs sorted by hits [, avgts, cumts, maxts, mthd, proto]"',
        '"desc": "Nejčastější nenalezené URL podle zásahů (hits, časy, metoda, protokol)"',
    ),
    (
        '"desc": "Top requests sorted by hits [, avgts, cumts, maxts, mthd, proto]"',
        '"desc": "Nejčastější požadavky podle zásahů (hits, časy, metoda, protokol)"',
    ),
    (
        '"desc": "Top static requests sorted by hits [, avgts, cumts, maxts, mthd, proto]"',
        '"desc": "Nejčastější statické požadavky podle zásahů (hits, časy, metoda, protokol)"',
    ),
    (
        '"desc": "Data sorted by hour [, avgts, cumts, maxts]"',
        '"desc": "Údaje podle hodiny (průměr / max. časy odezvy)"',
    ),
    (
        '"desc": "Top Browsers sorted by hits [, avgts, cumts, maxts]"',
        '"desc": "Nejčastější prohlížeče podle zásahů"',
    ),
    (
        '"desc": "Top HTTP Status Codes sorted by hits [, avgts, cumts, maxts]"',
        '"desc": "Nejčastější HTTP kódy podle zásahů"',
    ),
    (
        '"desc": "Top Operating Systems sorted by hits [, avgts, cumts, maxts]"',
        '"desc": "Nejčastější operační systémy podle zásahů"',
    ),
    (
        '"desc": "Top Referring Sites sorted by hits [, avgts, cumts, maxts]"',
        '"desc": "Časté odkazující weby podle zásahů"',
    ),
    (
        '"desc": "Top visitor hosts sorted by hits [, avgts, cumts, maxts]"',
        '"desc": "Častí návštěvní hostitelé podle zásahů"',
    ),
    (
        '"desc": "Hits having the same IP, date and agent are a unique visit."',
        '"desc": "Stejná IP, datum a prohlížeč se počítají jako jedna návštěva (zjednodušeně)."',
    ),
    (
        '"head": "Unique visitors per day - Including spiders"',
        '"head": "Unikátní návštěvníci za den (včetně automatických skenerů)"',
    ),
    (
        '"head": "Visitor Hostnames and IPs"',
        '"head": "Názvy hostitelů a IP adresy"',
    ),
    ('"head": "Not Found URLs (404s)"', '"head": "Nenalezené adresy URL (chyby 404)"'),
    ('"head": "Overall Analyzed Requests"', '"head": "Celkový přehled HTTP požadavků"'),
    ('"head": "Requested Files (URLs)"', '"head": "Nejčastější soubory a URL"'),
    ('"head": "HTTP Status Codes"', '"head": "HTTP stavové kódy"'),
    ('"head": "Operating Systems"', '"head": "Operační systémy"'),
    ('"head": "Static Requests"', '"head": "Statické požadavky"'),
    ('"head": "Time Distribution"', '"head": "Rozložení v čase"'),
    ('"head": "Referring Sites"', '"head": "Odkazující weby"'),
    ('"head": "Browsers"', '"head": "Prohlížeče"'),
    ('"thead": "Overall Analyzed Requests"', '"thead": "Celkový přehled HTTP požadavků"'),
    ('"label": "Total Requests"', '"label": "Požadavky celkem"'),
    ('"label": "Valid Requests"', '"label": "Platné požadavky"'),
    ('"label": "Failed Requests"', '"label": "Neplatné požadavky"'),
    ('"label": "Log Parsing Time"', '"label": "Čas zpracování logu"'),
    ('"label": "Unique Visitors"', '"label": "Unikátní návštěvníci"'),
    ('"label": "Requested Files"', '"label": "Požadované soubory"'),
    ('"label": "Excl. IP Hits"', '"label": "Vynechané IP zásahy"'),
    ('"label": "Static Files"', '"label": "Statické soubory"'),
    ('"label": "Log Size"', '"label": "Velikost logu"'),
    ('"label": "Hits/Visitors"', '"label": "Zásahy / návštěvníci"'),
    ('"label": "Tx. Amount"', '"label": "Přenesená data"'),
    ('"label": "Referrers"', '"label": "Odkazující stránky"'),
    ('"label": "Not Found"', '"label": "Nenalezeno (404)"'),
    ('"metaLabel": "Total"', '"metaLabel": "Celkem"'),
    ('"label": "Method"', '"label": "HTTP metoda"'),
    ('"label": "Protocol"', '"label": "Protokol"'),
    ('"label": "Visitors"', '"label": "Návštěvníci"'),
    ('"label": "Hits"', '"label": "Zásahy"'),
    ('"label": "Data"', '"label": "Datum"'),
)


def apply_cs(html: str) -> str:
    out = html.replace("lang='en'", "lang='cs'", 1)
    out = out.replace(
        "<title>Server&nbsp;Statistics</title>",
        "<title>Správa vozidel — návštěvnost</title>",
        1,
    )
    for en, cs in sorted(_SAFE_FRAGMENTS, key=lambda x: len(x[0]), reverse=True):
        if en in out:
            out = out.replace(en, cs)
    return out


def main() -> int:
    paths = [Path(p) for p in sys.argv[1:]]
    if not paths:
        print("Usage: goaccess_apply_cs.py <report.html> [more.html ...]", file=sys.stderr)
        return 2
    for path in paths:
        raw = path.read_text(encoding="utf-8", errors="replace")
        path.write_text(apply_cs(raw), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
