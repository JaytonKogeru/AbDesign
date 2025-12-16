"""Result retrieval helpers."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from . import task_store


def _build_download_entry(task_id: str, label: str, path: Optional[str]) -> Optional[Dict[str, Any]]:
    if not path:
        return None

    file_path = Path(path)
    if not file_path.exists():
        return None

    return {
        "artifact": label,
        "url": f"/download/{task_id}/{label}",
        "filename": file_path.name,
        "size": file_path.stat().st_size,
    }


def get_result(task_id: str) -> Dict[str, Any]:
    """Return task status, summary, and available download links."""

    task = task_store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task_id not found")

    result_metadata = task.get("result_metadata") or {}
    downloads: List[Dict[str, Any]] = []

    for label in ("structure", "scores_csv", "scores_tsv"):
        entry = _build_download_entry(task_id, label, result_metadata.get(f"{label}_path", result_metadata.get(label)))
        if entry:
            downloads.append(entry)

    summary_score = result_metadata.get("summary_score")
    stats = result_metadata.get("stats") or {"top_score": summary_score, "rmsd": None}

    return {
        "task_id": task_id,
        "status": task.get("status", "unknown"),
        "summary_score": summary_score,
        "stats": stats,
        "downloads": downloads,
        "error": task.get("error"),
    }
