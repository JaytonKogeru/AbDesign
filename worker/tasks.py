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
        cdr_summary = _build_cdr_summary(pipeline_result.cdr_annotation)
        summary_payload = {
            "task_id": task_id,
            "mode": payload["mode"],
            "user_params": payload.get("user_params", {}),
            "files": payload.get("files", {}),
            "numbering_scheme": pipeline_result.numbering_scheme,
            "pipeline": {
                "numbering_scheme": pipeline_result.numbering_scheme,
                "alignment": pipeline_result.alignment,
                "binding_site_prediction": pipeline_result.binding_site_prediction,
                "scoring": pipeline_result.scoring,
                "cdr_annotation": pipeline_result.cdr_annotation,
                "target_hotspots_input": pipeline_result.target_hotspots_input,
                "target_hotspots_resolved": pipeline_result.target_hotspots_resolved.to_dict()
                if pipeline_result.target_hotspots_resolved
                else None,
                "target_mapping_file": str(pipeline_result.target_mapping_file)
                if pipeline_result.target_mapping_file
                else None,
                "target_hotspots_resolved_v2": pipeline_result.target_hotspots_resolved_v2.to_dict()
                if pipeline_result.target_hotspots_resolved_v2
                else None,
                "target_mapping_file_v2": str(pipeline_result.target_mapping_file_v2)
                if pipeline_result.target_mapping_file_v2
                else None,
                "config": pipeline_result.config,
            },
            "artifacts": {
                "structure": str(pipeline_result.artifacts.structure),
                "scores_csv": str(pipeline_result.artifacts.scores_csv),
                "scores_tsv": str(pipeline_result.artifacts.scores_tsv),
                "summary_json": str(summary_path),
                "cdr_json": str(pipeline_result.artifacts.cdr_json) if pipeline_result.artifacts.cdr_json else None,
                "cdr_csv": str(pipeline_result.artifacts.cdr_csv) if pipeline_result.artifacts.cdr_csv else None,
                "target_residue_mapping": str(pipeline_result.artifacts.target_residue_mapping)
                if pipeline_result.artifacts.target_residue_mapping
                else None,
                "target_hotspots_resolved": str(pipeline_result.artifacts.target_hotspots_resolved)
                if pipeline_result.artifacts.target_hotspots_resolved
                else None,
                "target_residue_mapping_v2": str(pipeline_result.artifacts.target_residue_mapping_v2)
                if pipeline_result.artifacts.target_residue_mapping_v2
                else None,
                "target_hotspots_resolved_v2": str(pipeline_result.artifacts.target_hotspots_resolved_v2)
                if pipeline_result.artifacts.target_hotspots_resolved_v2
                else None,
            },
            "cdr_summary": cdr_summary,
            "summary_score": pipeline_result.summary_score,
            "cdr_annotation": pipeline_result.cdr_annotation,
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
                "cdr_json": str(pipeline_result.artifacts.cdr_json),
                "cdr_csv": str(pipeline_result.artifacts.cdr_csv),
                "summary_score": pipeline_result.summary_score,
                "cdr_json": str(pipeline_result.artifacts.cdr_json) if pipeline_result.artifacts.cdr_json else None,
                "cdr_csv": str(pipeline_result.artifacts.cdr_csv) if pipeline_result.artifacts.cdr_csv else None,
                "pipeline": summary_payload["pipeline"],
                "numbering_scheme": pipeline_result.numbering_scheme,
                "cdr_summary": cdr_summary,
                "target_residue_mapping": str(pipeline_result.artifacts.target_residue_mapping)
                if pipeline_result.artifacts.target_residue_mapping
                else None,
                "target_hotspots_resolved": str(pipeline_result.artifacts.target_hotspots_resolved)
                if pipeline_result.artifacts.target_hotspots_resolved
                else None,
                "target_residue_mapping_v2": str(pipeline_result.artifacts.target_residue_mapping_v2)
                if pipeline_result.artifacts.target_residue_mapping_v2
                else None,
                "target_hotspots_resolved_v2": str(pipeline_result.artifacts.target_hotspots_resolved_v2)
                if pipeline_result.artifacts.target_hotspots_resolved_v2
                else None,
            },
        )
        logger.info("Task %s completed with score %.2f", task_id, pipeline_result.summary_score)
        return {
            "structure": str(pipeline_result.artifacts.structure),
            "scores_csv": str(pipeline_result.artifacts.scores_csv),
            "scores_tsv": str(pipeline_result.artifacts.scores_tsv),
            "summary_json": str(summary_path),
            "cdr_json": str(pipeline_result.artifacts.cdr_json),
            "cdr_csv": str(pipeline_result.artifacts.cdr_csv),
            "summary_score": pipeline_result.summary_score,
            "cdr_json": str(pipeline_result.artifacts.cdr_json) if pipeline_result.artifacts.cdr_json else None,
            "cdr_csv": str(pipeline_result.artifacts.cdr_csv) if pipeline_result.artifacts.cdr_csv else None,
            "target_residue_mapping": str(pipeline_result.artifacts.target_residue_mapping)
            if pipeline_result.artifacts.target_residue_mapping
            else None,
            "target_hotspots_resolved": str(pipeline_result.artifacts.target_hotspots_resolved)
            if pipeline_result.artifacts.target_hotspots_resolved
            else None,
            "target_residue_mapping_v2": str(pipeline_result.artifacts.target_residue_mapping_v2)
            if pipeline_result.artifacts.target_residue_mapping_v2
            else None,
            "target_hotspots_resolved_v2": str(pipeline_result.artifacts.target_hotspots_resolved_v2)
            if pipeline_result.artifacts.target_hotspots_resolved_v2
            else None,
        }
    except Exception as exc:  # noqa: BLE001
        logger.exception("Task %s failed", task_id)
        task_store.update_task(task_id, status="failed", error=str(exc))
        raise


def _build_cdr_summary(annotation: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "scheme": annotation.get("scheme"),
        "chains": [
            {
                "chain_id": chain.get("chain_id"),
                "cdrs": chain.get("cdrs", []),
            }
            for chain in annotation.get("chains", [])
        ],
    }
