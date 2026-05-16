"""Tests for storage resolution helpers (vehicle photos)."""
from pathlib import Path
from unittest.mock import patch

from src.modules.vehicle_hub.vehicle_photo_assets import resolve_storage_file


def test_resolve_storage_file_permission_denied_returns_none(tmp_path: Path) -> None:
    (tmp_path / "tenants" / "1" / "vehicles" / "1").mkdir(parents=True)
    f = tmp_path / "tenants" / "1" / "vehicles" / "1" / "x.jpg"
    f.write_bytes(b"x")
    key = "tenants/1/vehicles/1/x.jpg"
    with patch.object(Path, "is_file", side_effect=PermissionError(13, "denied")):
        assert resolve_storage_file(tmp_path, key) is None
