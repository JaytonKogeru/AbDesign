"""Result retrieval helpers."""
from __future__ import annotations

from typing import Any, Dict

from fastapi import HTTPException

from api import task_store


def get_result(task_id: str) -> Dict[str, Any]:
    """Fetch stored task results or raise if missing."""

    task = task_store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task_id not found")

    return {
        "task_id": task_id,
        "status": task.get("status", "unknown"),
        "result_metadata": task.get("result_metadata"),
        "error": task.get("error"),
    }
