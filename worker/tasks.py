"""Background tasks executed by the worker process."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

from api import task_store

logger = logging.getLogger(__name__)


def run_pipeline(task_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Placeholder pipeline that writes dummy result artifacts.

    The function simulates parsing inputs, performing predictions, and writing
    outputs so downstream consumers can be integrated later without changing
    the scheduling flow.
    """

    task_store.update_task(task_id, status="started")
    task_dir = Path(payload["task_dir"])
    task_dir.mkdir(parents=True, exist_ok=True)

    try:
        predicted_results = {
            "task_id": task_id,
            "mode": payload["mode"],
            "user_params": payload.get("user_params", {}),
            "files": payload["files"],
        }
        results_path = task_dir / "prediction.json"
        results_path.write_text(json.dumps(predicted_results, indent=2))

        score = float(len(payload["files"])) * 0.1 + 0.9
        scores_path = task_dir / "scores.json"
        scores_path.write_text(json.dumps({"summary_score": score}, indent=2))

        task_store.update_task(
            task_id,
            status="succeeded",
            result_metadata={
                "results_path": str(results_path),
                "scores_path": str(scores_path),
                "summary_score": score,
            },
        )
        logger.info("Task %s completed with score %.2f", task_id, score)
        return {"results": str(results_path), "scores": str(scores_path), "summary_score": score}
    except Exception as exc:  # noqa: BLE001
        logger.exception("Task %s failed", task_id)
        task_store.update_task(task_id, status="failed", error=str(exc))
        raise

