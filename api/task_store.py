"""Simple JSON-based task state persistence for demo workloads."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


STATE_FILE = Path(os.getenv("TASK_STATE_FILE", "/tmp/task_state.json"))


def _load_state() -> Dict[str, Any]:
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text())
    except json.JSONDecodeError:
        return {}


def _write_state(state: Dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def create_task(task_id: str, payload: Dict[str, Any]) -> None:
    state = _load_state()
    state[task_id] = payload
    _write_state(state)


def update_task(task_id: str, **updates: Any) -> None:
    state = _load_state()
    if task_id not in state:
        state[task_id] = {}
    state[task_id].update(updates)
    _write_state(state)


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    state = _load_state()
    return state.get(task_id)

