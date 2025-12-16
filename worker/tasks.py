"""Background tasks executed by the worker process."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict

from api import task_store
from pipeline.runner import run_pipeline as execute_pipeline

logger = logging.getLogger(__name__)


def run_pipeline(task_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Run the prediction pipeline for the given task.

    The worker delegates to :mod:`pipeline.runner` to keep algorithm-specific
    logic in a single place. This function is responsible for updating task
    status, marshalling inputs, and storing metadata about produced artifacts.
    """

    task_store.update_task(task_id, status="started")
    task_dir = Path(payload["task_dir"])
    task_dir.mkdir(parents=True, exist_ok=True)

    try:
        pipeline_inputs = {
            **payload,
            "output_dir": task_dir,
        }

        pipeline_result = execute_pipeline(payload["mode"], pipeline_inputs)

        summary_path = pipeline_result.artifacts.summary_json
        summary_payload = {
            "task_id": task_id,
            "mode": payload["mode"],
            "user_params": payload.get("user_params", {}),
            "files": payload.get("files", {}),
            "pipeline": {
                "alignment": pipeline_result.alignment,
                "binding_site_prediction": pipeline_result.binding_site_prediction,
                "scoring": pipeline_result.scoring,
                "config": pipeline_result.config,
            },
            "artifacts": {
                "structure": str(pipeline_result.artifacts.structure),
                "scores_csv": str(pipeline_result.artifacts.scores_csv),
                "scores_tsv": str(pipeline_result.artifacts.scores_tsv),
                "summary_json": str(summary_path),
            },
            "summary_score": pipeline_result.summary_score,
        }
        summary_path.write_text(json.dumps(summary_payload, indent=2))

        task_store.update_task(
            task_id,
            status="succeeded",
            result_metadata={
                "structure_path": str(pipeline_result.artifacts.structure),
                "scores_csv": str(pipeline_result.artifacts.scores_csv),
                "scores_tsv": str(pipeline_result.artifacts.scores_tsv),
                "summary_json": str(summary_path),
                "summary_score": pipeline_result.summary_score,
                "pipeline": summary_payload["pipeline"],
            },
        )
        logger.info("Task %s completed with score %.2f", task_id, pipeline_result.summary_score)
        return {
            "structure": str(pipeline_result.artifacts.structure),
            "scores_csv": str(pipeline_result.artifacts.scores_csv),
            "scores_tsv": str(pipeline_result.artifacts.scores_tsv),
            "summary_json": str(summary_path),
            "summary_score": pipeline_result.summary_score,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Task %s failed", task_id)
        task_store.update_task(task_id, status="failed", error=str(exc))
        raise
