"""Konfigurace mapového podkladu pro frontend."""
from __future__ import annotations

from src.core.config import MAP_PROVIDER, MAP_TILE_URL, MAPY_COM_API_KEY


def build_map_tile_config() -> dict:
    provider = (MAP_PROVIDER or "osm_tiles").strip().lower()
    configured = False
    tile_url = None
    attribution = None

    if provider == "mapy_com" and MAPY_COM_API_KEY:
        tile_url = (
            f"https://api.mapy.cz/v1/maptiles/basic/256/{{z}}/{{x}}/{{y}}?apikey={MAPY_COM_API_KEY}"
        )
        attribution = "© Seznam.cz / Mapy.cz"
        configured = True
    elif provider == "custom_tiles" and MAP_TILE_URL:
        tile_url = MAP_TILE_URL
        attribution = "© Map tiles"
        configured = True
    elif provider in {"osm_tiles", "mapy_com", "custom_tiles"}:
        tile_url = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution = "© OpenStreetMap contributors"
        configured = True

    return {
        "provider": provider,
        "configured": configured,
        "tile_url": tile_url,
        "attribution": attribution,
        "fallback_message": (
            None
            if configured
            else "Mapa není nakonfigurovaná. Servisy lze zobrazit v seznamu."
        ),
    }
