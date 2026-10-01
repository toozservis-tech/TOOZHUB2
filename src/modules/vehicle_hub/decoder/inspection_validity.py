"""Current STK expiry from the official RSV API, never inferred from mileage history.

The public tachometer list includes emissions and identification-only checks.
Only the explicit registry expiry for the requested VIN may replace a saved date.
"""
from dataclasses import dataclass
from datetime import date, datetime
import json
import re
import time

import requests
from src.core import config

REGISTRY_URL = "https://api.dataovozidlech.cz/api/vehicletechnicaldata/v2"
MAX_RESPONSE_BYTES = 256 * 1024


@dataclass(frozen=True)
class InspectionValidity:
    status: str
    valid_until: date | None = None

    def response_fields(self) -> dict:
        return {
            "stk_valid_until": self.valid_until,
            "stk_validity_status": self.status,
            "stk_validity_source": "dataovozidlech.cz" if self.valid_until else None,
        }


def parse_registry_expiry(payload: object, vin: str) -> InspectionValidity:
    if not isinstance(payload, dict) or type(payload.get("Status")) is not int or payload["Status"] != 1:
        return InspectionValidity("unavailable")
    data = payload.get("Data")
    if not isinstance(data, dict) or not isinstance(data.get("VIN"), str):
        return InspectionValidity("invalid_response")
    if data["VIN"].strip().upper() != vin:
        return InspectionValidity("invalid_response")
    # Do NOT fall back to InspectionDate / EvidencniProhlidkaDne / emissions.
    raw = data.get("PravidelnaTechnickaProhlidkaDo")
    if raw is None or raw == "":
        return InspectionValidity("not_available")
    if not isinstance(raw, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?)?", raw):
        return InspectionValidity("invalid_response")
    try:
        # Validate the whole date/time, preserving its calendar day, not shifting UTC.
        parsed = datetime.fromisoformat(raw).date() if "T" in raw else date.fromisoformat(raw)
        if parsed.year < 1900:  # Reject provider sentinel dates such as 0001-01-01.
            return InspectionValidity("invalid_response")
        return InspectionValidity("verified", parsed)
    except ValueError:
        return InspectionValidity("invalid_response")


def fetch_inspection_validity(vin: str) -> InspectionValidity:
    key = str(config.STK_REGISTRY_API_KEY or config.DATAOVO_API_KEY or "").strip()
    if not key:
        return InspectionValidity("not_configured")
    # Never send the registry key or VIN to an environment-supplied alternate host.
    if config.DATAOVO_API_BASE_URL != REGISTRY_URL:
        return InspectionValidity("not_configured")
    if not re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", vin):
        return InspectionValidity("invalid_response")
    try:
        with requests.Session() as session:
            session.trust_env = False
            with session.get(REGISTRY_URL, params={"vin": vin},
                             headers={"api_key": key, "Accept": "application/json"},
                             timeout=(3, 6), allow_redirects=False, stream=True) as response:
                if response.status_code != 200:
                    return InspectionValidity("unavailable")
                body = bytearray()
                deadline = time.monotonic() + 10
                for chunk in response.iter_content(chunk_size=16384):
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES or time.monotonic() > deadline:
                        return InspectionValidity("unavailable")
                return parse_registry_expiry(json.loads(body), vin)
    except (requests.RequestException, ValueError, UnicodeError):
        # Preserve successful mileage import; never log credentials, VIN or raw payload.
        return InspectionValidity("unavailable")
