"""Apply the approved October 2026 web price list once, without changing payments."""
from __future__ import annotations

import json
from copy import deepcopy

from src.core.file_storage import cached_file, persist_file
from src.server.runtime_settings import ADMIN_SETTINGS_FILE

REVISION = "web_prices_20261005"
PRICES = {
    "price_basic_monthly_halers": 14900,
    "price_basic_yearly_halers": 149000,
    "price_premium_monthly_halers": 44900,
    "price_premium_yearly_halers": 449000,
}


def updated_settings(payload: dict) -> dict | None:
    if not isinstance(payload, dict):
        raise ValueError("Invalid settings document; price migration aborted")
    for category in ("comgate", "migrations"):
        if category in payload and not isinstance(payload[category], dict):
            raise ValueError("Invalid settings category; price migration aborted")
    if payload.get("migrations", {}).get(REVISION, {}).get("value") is True:
        return None
    result = deepcopy(payload)
    comgate = result.setdefault("comgate", {})
    for key, value in PRICES.items():
        entry = comgate.setdefault(key, {})
        if not isinstance(entry, dict):
            raise ValueError("Invalid price setting; price migration aborted")
        entry.update(value=value, value_type="number")
    result.setdefault("migrations", {})[REVISION] = {
        "value": True, "value_type": "boolean",
        "description": "Web prices aligned with approved App Store prices on 2026-10-05",
    }
    return result


def main() -> None:
    # Refresh from durable storage; never replace unreadable existing settings.
    path = cached_file(ADMIN_SETTINGS_FILE, refresh=True)
    payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    result = updated_settings(payload)
    if result is not None:
        persist_file(ADMIN_SETTINGS_FILE, json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8"), replace=True)
        print("Approved web price list applied")


if __name__ == "__main__":
    main()
