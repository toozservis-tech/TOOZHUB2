"""
Runtime řízení background jobů pro Developer Control Center (pause/resume).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from src.core.config import DATA_DIR
from src.core.file_storage import cached_file, persist_file
from threading import RLock

_state_lock = RLock()

JOBS_STATE_FILE = Path(DATA_DIR) / "control_center_job_state.json"


def _default_state() -> Dict[str, Any]:
    return {
        "paused": {},
        "updated_at": None,
    }


def load_jobs_state() -> Dict[str, Any]:
    cached_file(JOBS_STATE_FILE, refresh=True)
    if not JOBS_STATE_FILE.exists():
        return _default_state()
    try:
        payload = json.loads(JOBS_STATE_FILE.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Invalid job state")
        payload.setdefault("paused", {})
        if not isinstance(payload["paused"], dict):
            raise ValueError("Invalid paused job state")
        payload.setdefault("updated_at", None)
        return payload
    except (ValueError, OSError) as exc:
        raise RuntimeError("Nastavení automatických kontrol nelze bezpečně načíst.") from exc


def save_jobs_state(state: Dict[str, Any]) -> None:
    JOBS_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.utcnow().isoformat()
    persist_file(JOBS_STATE_FILE, json.dumps(state, ensure_ascii=False, indent=2).encode("utf-8"), replace=True)


def is_job_paused(job_name: str) -> bool:
    state = load_jobs_state()
    paused = state.get("paused", {})
    if not isinstance(paused, dict):
        return False
    return bool(paused.get(job_name))


def set_job_paused(job_name: str, paused: bool, actor_email: str | None = None, reason: str | None = None) -> Dict[str, Any]:
    with _state_lock:
        state = load_jobs_state()
        paused_map = state.setdefault("paused", {})
        if not isinstance(paused_map, dict):
            paused_map = {}
            state["paused"] = paused_map

        if paused:
            paused_map[job_name] = {
                "paused": True,
                "paused_at": datetime.utcnow().isoformat(),
                "paused_by": (actor_email or "").strip().lower() or None,
                "reason": (reason or "").strip() or None,
            }
        else:
            paused_map.pop(job_name, None)

        save_jobs_state(state)
        return state


def get_job_pause_metadata(job_name: str) -> Dict[str, Any]:
    state = load_jobs_state()
    paused_map = state.get("paused", {})
    if not isinstance(paused_map, dict):
        return {}
    raw = paused_map.get(job_name)
    return raw if isinstance(raw, dict) else {}
