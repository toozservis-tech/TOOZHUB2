#!/usr/bin/env python3
"""Alias na remove_example_com_integration_users.py — stejný příkaz a výjimky (demo z .env)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_ORIG = _HERE / "remove_example_com_integration_users.py"

_spec = importlib.util.spec_from_file_location("remove_example_com_integration_users", _ORIG)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"Nelze načíst {_ORIG}")
_mod = importlib.util.module_from_spec(_spec)
sys.modules["remove_example_com_integration_users"] = _mod
_spec.loader.exec_module(_mod)

if __name__ == "__main__":
    raise SystemExit(_mod.main())
