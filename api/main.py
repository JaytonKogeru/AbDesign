import json
import logging
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from api import results, storage, task_store
from api.config import get_settings
from worker.queue import get_queue
from worker.tasks import run_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

settings = get_settings()
API_KEY_HEADER = "X-API-Key"
RATE_LIMIT_WINDOW_SECONDS = 60
_rate_limit_registry: Dict[str, List[float]] = defaultdict(list)

app = FastAPI(title="Demo Submission API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):  # type: ignore[override]
    start_time = time.perf_counter()
    response = await call_next(request)
    elapsed = (time.perf_counter() - start_time) * 1000
    logger.info(
        "%s %s -> %s in %.2f ms",
        request.method,
        request.url.path,
        response.status_code,
        elapsed,
    )
    return response


def _enforce_rate_limit(identifier: str) -> None:
    now = time.monotonic()
    window_start = now - RATE_LIMIT_WINDOW_SECONDS
    recent = [ts for ts in _rate_limit_registry[identifier] if ts >= window_start]
    if len(recent) >= settings.rate_limit_per_minute:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    recent.append(now)
    _rate_limit_registry[identifier] = recent


async def enforce_api_key(request: Request) -> str:
    provided_key = request.headers.get(API_KEY_HEADER, "")
    if settings.api_key and provided_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")

    identifier = provided_key or (request.client.host if request.client else "anonymous")
    if settings.rate_limit_per_minute > 0:
        _enforce_rate_limit(identifier)
    return identifier


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
    _: str = Depends(enforce_api_key),
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
    task_dir = storage.create_temp_directory(settings.storage_root, task_id)

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

    queue = get_queue(settings.queue_name)
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
