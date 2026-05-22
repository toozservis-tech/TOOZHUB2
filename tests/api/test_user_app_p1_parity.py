"""
P1 frontend parity — user-app-next sidebar, license gating, tutorial hub wiring.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "web"


def _read(rel: str) -> str:
    return (WEB / rel).read_text(encoding="utf-8")


def test_user_app_next_sidebar_objednat_servis():
    assert "Objednat servis" in _read("user-app-next.js")


def test_user_app_next_sidebar_podpora():
    assert "Podpora" in _read("user-app-next.js")


def test_user_app_next_exports_can_access_feature():
    content = _read("user-app-next.js")
    assert "function canAccessFeature" in content
    assert "window.canAccessFeature = canAccessFeature" in content


def test_user_app_next_has_navigate_licensed_tab():
    assert "function navigateLicensedTab" in _read("user-app-next.js")


def test_user_app_next_licensed_tabs_use_switch_tab_not_bypass():
    content = _read("user-app-next.js")
    assert "if (name === 'reservations') return navigateLicensedTab('reservations', 'reservations');" in content
    assert "if (name === 'documents') return navigateLicensedTab('documents', 'documents');" in content
    assert "if (name === 'servicesDirectory') return navigateLicensedTab('servicesDirectory', 'servicesDirectory');" in content
    nav_block = re.search(
        r"function navigateLicensedTab\(tabName, featureKey\) \{.*?\n  \}",
        content,
        re.DOTALL,
    )
    assert nav_block is not None
    nav_fn = nav_block.group(0)
    assert "if (hasFn('switchTab')) return window.switchTab(tabName);" in nav_fn
    run_block = re.search(r"function runAction\(action, event\) \{.*?\n  \}", content, re.DOTALL)
    assert run_block is not None
    run_fn = run_block.group(0)
    for tab in ("documents", "servicesDirectory", "reservations"):
        assert f"navigateLicensedTab('{tab}'" in run_fn
        assert not re.search(
            rf"if \(name === '{tab}'\)[^\n]*STATE\.viewOverride[^\n]*return render\(\)",
            run_fn,
        )


def test_index_html_loads_tutorial_hub():
    content = _read("index.html")
    assert 'src="/web/tutorial-hub.js' in content


def test_index_html_does_not_load_missing_tutorial_engine():
    content = _read("index.html")
    engine_path = WEB / "tutorials" / "tutorial-engine.js"
    if not engine_path.is_file():
        assert "tutorial-engine.js" not in re.findall(
            r'<script[^>]+src="[^"]*tutorial-engine\.js[^"]*"', content, re.I
        )


def test_index_html_exports_sync_user_tab_url_history():
    content = _read("index.html")
    assert "function syncUserTabUrlHistory" in content
    assert "window.syncUserTabUrlHistory = syncUserTabUrlHistory;" in content


def test_index_html_license_ui_uses_effective_trial_plan():
    content = _read("index.html")
    assert "function getEffectiveLicensePlanKey" in content
    assert "license?.effective_plan" in content
    assert "Premium trial – zbývá" in content
    assert "effective_plan: lic.effective_plan || lic.plan || 'free'" in content


def test_index_html_sanitizes_runtime_sql_errors():
    content = _read("index.html")
    assert "function sanitizeUiErrorMessage" in content
    assert "sqlite" in content
    assert "no such column" in content
    assert "Funkci se nepodařilo načíst. Zkuste to prosím znovu nebo kontaktujte podporu." in content
    assert "showVinError(errorMsg)" in content
    assert "VIN se nepodařilo načíst: ' + errorMsg" not in content


def test_index_html_locked_feature_messages_are_specific():
    content = _read("index.html")
    assert "Tato funkce je dostupná v licenci Premium. Pro automatické načtení údajů z VIN" in content
    assert "Dokumenty a PDF exporty jsou dostupné od licence Basic." in content
    assert "Objednání servisu je dostupné od licence Basic." in content
    assert "Servisní partneři a mapa servisů jsou dostupní v licenci Premium." in content


def test_tutorial_hub_open_modal():
    assert "window.openHowToHubModal = function openHowToHubModal" in _read("tutorial-hub.js")


def test_tutorial_hub_close_modal():
    assert "window.closeHowToHubModal = function closeHowToHubModal" in _read("tutorial-hub.js")
