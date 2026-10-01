"""Technical document lookup. Only the official host and explicitly selected fields.

No owner data, arbitrary QR URLs, raw provider payloads or credentials leave this
boundary. Registry data does not confer ownership or service access to a vehicle.
"""
import json
import re
import time
from datetime import date

import requests
from fastapi import HTTPException
from pydantic import BaseModel, Field, model_validator

from src.core import config
from .inspection_validity import REGISTRY_URL, MAX_RESPONSE_BYTES, parse_registry_expiry


class RegistryLookupRequest(BaseModel):
    vin: str | None = Field(default=None, max_length=17)
    orv: str | None = Field(default=None, max_length=9)

    @model_validator(mode="after")
    def validate_identifier(self):
        if bool(self.vin) == bool(self.orv):
            raise ValueError("Zadejte VIN nebo číslo ORV.")
        if self.vin and not re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", self.vin):
            raise ValueError("Neplatný VIN.")
        if self.orv and not re.fullmatch(r"[A-Z]{2,3}[0-9]{6}", self.orv):
            raise ValueError("Neplatné číslo ORV.")
        return self


class RegistryVehicle(BaseModel):
    vin: str
    source: str = "dataovozidlech.cz"
    orv_number: str | None = None
    plate: str | None = None
    brand: str | None = None
    model: str | None = None
    type_label: str | None = None
    fuel: str | None = None
    engine_power_kw: str | None = None
    engine_displacement_cc: str | None = None
    engine_code: str | None = None
    production_year: int | None = None
    first_registration_date: str | None = None
    category: str | None = None
    stk_valid_until: date | None = None


def technical_fields(payload: object, query: RegistryLookupRequest) -> RegistryVehicle:
    if not isinstance(payload, dict) or type(payload.get("Status")) is not int or payload["Status"] != 1:
        raise HTTPException(404, "Registr vozidlo nenašel. Zkontrolujte VIN nebo číslo ORV.")
    data = payload.get("Data")
    if not isinstance(data, dict):
        raise HTTPException(502, "Registr nevrátil jednoznačné vozidlo.")

    def value(key):
        raw = data.get(key)
        if not isinstance(raw, (str, int, float)) or isinstance(raw, bool):
            return None
        text = str(raw).strip()
        return text if text and len(text) <= 200 and not any(ord(c) < 32 for c in text) else None

    vin, orv = value("VIN"), value("CisloOrv")
    if not vin or not re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", vin):
        raise HTTPException(502, "Registr nevrátil platný VIN.")
    if (query.vin and query.vin != vin) or (query.orv and query.orv != orv):
        raise HTTPException(502, "Vozidlo z registru neodpovídá zadanému dokladu.")
    year = data.get("RokVyroby")
    year = int(year) if str(year).isdigit() and 1900 <= int(year) <= 2100 else None
    first = value("DatumPrvniRegistrace")
    try:
        first = date.fromisoformat(first[:10]).isoformat() if first else None
    except ValueError:
        first = None
    power = value("MotorMaxVykon")
    power_match = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*(?:/\s*\d+)?", power or "")
    return RegistryVehicle(
        vin=vin, orv_number=orv, plate=value("RegistracniZnacka"),
        brand=value("TovarniZnacka"), model=value("ObchodniOznaceni"),
        type_label=value("Typ"), fuel=value("Palivo"),
        engine_power_kw=power_match.group(1) if power_match else None,
        engine_displacement_cc=value("MotorZdvihObjem"), engine_code=value("MotorTyp"),
        production_year=year, first_registration_date=first, category=value("Kategorie"),
        stk_valid_until=parse_registry_expiry(payload, vin).valid_until,
    )


def lookup_document(query: RegistryLookupRequest) -> RegistryVehicle:
    key = str(config.STK_REGISTRY_API_KEY or config.DATAOVO_API_KEY or "").strip()
    if not key or config.DATAOVO_API_BASE_URL != REGISTRY_URL:
        raise HTTPException(503, "Načtení z registru není nyní dostupné. Údaje z dokladu můžete doplnit ručně.")
    try:
        with requests.Session() as session:
            session.trust_env = False
            with session.get(REGISTRY_URL, params=query.model_dump(exclude_none=True),
                             headers={"api_key": key, "Accept": "application/json"},
                             timeout=(3, 8), allow_redirects=False, stream=True) as response:
                if response.status_code == 429:
                    raise HTTPException(429, "Registr je vytížený. Zkuste načtení za minutu.")
                if response.status_code != 200:
                    raise HTTPException(503, "Registr nyní neodpovídá. Rozpracované údaje zůstávají zachované.")
                body = bytearray()
                deadline = time.monotonic() + 12
                for chunk in response.iter_content(chunk_size=16384):
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES or time.monotonic() > deadline:
                        raise HTTPException(502, "Odpověď registru se nepodařilo bezpečně načíst.")
                return technical_fields(json.loads(body), query)
    except (requests.RequestException, ValueError, UnicodeError):
        raise HTTPException(503, "Registr nyní neodpovídá. Rozpracované údaje zůstávají zachované.") from None
