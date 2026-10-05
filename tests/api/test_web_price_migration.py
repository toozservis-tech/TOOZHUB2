import json

import pytest

from scripts import migrate_web_prices as migration
from src.modules.vehicle_hub.routers_v1 import license_status


def test_price_migration_preserves_settings_and_future_changes(monkeypatch):
    original = {"comgate": {"merchant": {"value": "test-merchant"},
                            "price_basic_monthly_halers": {"value": 9900, "description": "Basic"}},
                "other": {"enabled": {"value": True}}}
    updated = migration.updated_settings(original)
    assert original["comgate"]["price_basic_monthly_halers"]["value"] == 9900
    assert updated["other"] == original["other"]
    assert updated["comgate"]["merchant"] == original["comgate"]["merchant"]
    assert updated["comgate"]["price_basic_monthly_halers"]["description"] == "Basic"
    monkeypatch.setattr(license_status, "load_runtime_settings", lambda: updated)
    monkeypatch.setenv("COMGATE_PRICE_BASIC_HALERS", "9900")
    assert license_status._load_comgate_config()["plans"] == {
        "basic": {"monthly": 14900, "yearly": 149000},
        "premium": {"monthly": 44900, "yearly": 449000},
    }
    updated["comgate"]["price_basic_monthly_halers"]["value"] = 15900
    assert migration.updated_settings(updated) is None


@pytest.mark.parametrize("payload", [[], None, {"comgate": []}, {"comgate": {"price_basic_monthly_halers": 12}}])
def test_invalid_settings_are_not_overwritten(payload):
    with pytest.raises(ValueError):
        migration.updated_settings(payload)


def test_migration_rejects_corrupt_file_without_writing(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    path.write_text("{broken")
    monkeypatch.setattr(migration, "cached_file", lambda *a, **kw: path)
    monkeypatch.setattr(migration, "persist_file", lambda *a, **kw: pytest.fail("must not write"))
    with pytest.raises(json.JSONDecodeError):
        migration.main()
