import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from api import results, storage, task_store
from worker.queue import get_queue
from worker.tasks import run_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Demo Submission API", version="0.1.0")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception on path %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "path": request.url.path},
    )


@app.get("/health")
async def health_check() -> Dict[str, str]:
    """Health check endpoint for uptime monitoring."""
    return {"status": "ok"}


@app.post("/submit")
async def submit(  # pylint: disable=too-many-arguments
    mode: str = Form(..., description="Submission mode: 'separate' or 'complex'"),
    vhh_file: Optional[UploadFile] = File(
        None, description="VHH component file for separate uploads"
    ),
    target_file: Optional[UploadFile] = File(
        None, description="Target component file for separate uploads"
    ),
    complex_file: Optional[UploadFile] = File(
        None, description="Combined complex file for complex mode"
    ),
    user_params: Optional[str] = Form(None, description="JSON string of user parameters"),
) -> Dict[str, Any]:
    """
    Accept a submission for processing and enqueue a background task.
    """

    normalized_mode = mode.strip().lower()
    if normalized_mode not in {"separate", "complex"}:
        raise HTTPException(status_code=400, detail="mode must be 'separate' or 'complex'")

    if normalized_mode == "separate":
        if not vhh_file or not target_file:
            raise HTTPException(
                status_code=400,
                detail="vhh_file and target_file are required when mode is 'separate'",
            )
    elif not complex_file:
        raise HTTPException(
            status_code=400,
            detail="complex_file is required when mode is 'complex'",
        )

    try:
        parsed_params = json.loads(user_params) if user_params else {}
    except json.JSONDecodeError as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Invalid user_params JSON: {exc}") from exc

    task_id = storage.generate_task_id()
    task_dir = storage.create_temp_directory("/tmp/submissions", task_id)

    async def _store_upload(upload: UploadFile, label: str) -> str:
        content = await upload.read()
        destination = task_dir / f"{label}-{upload.filename}"
        destination.write_bytes(content)
        return str(destination)

    file_manifest: Dict[str, str] = {}
    if vhh_file:
        file_manifest["vhh_file"] = await _store_upload(vhh_file, "vhh")
    if target_file:
        file_manifest["target_file"] = await _store_upload(target_file, "target")
    if complex_file:
        file_manifest["complex_file"] = await _store_upload(complex_file, "complex")

    payload = {
        "mode": normalized_mode,
        "files": file_manifest,
        "user_params": parsed_params,
        "task_dir": str(task_dir),
    }

    task_store.create_task(
        task_id,
        {
            "status": "queued",
            "payload": payload,
            "result_metadata": None,
            "error": None,
        },
    )

    queue = get_queue()
    job = queue.enqueue(run_pipeline, task_id, payload)

    logger.info(
        "Accepted submission %s in %s mode with files: %s", task_id, normalized_mode, list(file_manifest.keys())
    )

    return {
        "task_id": task_id,
        "job_id": job.id,
        "mode": normalized_mode,
        "received_files": list(file_manifest.keys()),
        "status": "queued",
    }


@app.get("/result/{task_id}")
async def get_result(task_id: str) -> Dict[str, Any]:
    """Return task status, scores, and download links."""
    logger.info("Fetching result metadata for task %s", task_id)
    return results.get_result(task_id)


@app.get("/download/{task_id}/{artifact}")
async def download_artifact(task_id: str, artifact: str) -> FileResponse:
    """Download a specific artifact for a task, restricted to known outputs."""

    task = task_store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="task_id not found")

    metadata = task.get("result_metadata") or {}
    allowed_paths = {
        "structure": metadata.get("structure_path"),
        "scores_csv": metadata.get("scores_csv"),
        "scores_tsv": metadata.get("scores_tsv"),
    }

    selected_path = allowed_paths.get(artifact)
    if not selected_path:
        raise HTTPException(status_code=404, detail="artifact not found")

    file_path = Path(selected_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="artifact file missing")

    media_types = {
        "structure": "chemical/x-pdb",
        "scores_csv": "text/csv",
        "scores_tsv": "text/tab-separated-values",
    }
    media_type = media_types.get(artifact, "application/octet-stream")

    return FileResponse(
        file_path,
        media_type=media_type,
        filename=file_path.name,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )
