"""Verify deployment entry points in fresh processes, without real data/network."""
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("entry", [
    "from src.modules.licensing import apple_store",
    "from src.modules.licensing.dependencies import require_feature",
    "from scripts.migrate_apple_billing import migrate",
    "from src.modules.vehicle_hub.routers_v1.auth import get_current_user",
])
def test_license_import_before_full_api(entry, tmp_path):
    root = Path(__file__).resolve().parents[2]
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{tmp_path / 'isolated.sqlite'}",
           "DATA_DIR_PATH": str(tmp_path / "data")}
    code = entry + "\n" + (
        "from src.modules.vehicle_hub.routers_v1 import api_router\n"
        "from fastapi import FastAPI\n"
        "app = FastAPI()\n"
        "app.include_router(api_router)\n"
        "paths = app.openapi()['paths']\n"
        "assert '/api/v1/vehicles' in paths\n"
        "assert '/api/v1/reminders/settings' in paths\n"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=root, env=env,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
