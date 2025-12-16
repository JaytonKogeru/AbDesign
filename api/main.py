import logging
import uuid
from typing import Any, Dict, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse

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
) -> Dict[str, Any]:
    """
    Accept a submission for processing. Depending on the mode, either
    component files or a single complex file must be provided.
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

    task_id = str(uuid.uuid4())
    received_files = [
        name
        for name, file in (
            ("vhh_file", vhh_file),
            ("target_file", target_file),
            ("complex_file", complex_file),
        )
        if file is not None
    ]

    logger.info("Accepted submission %s in %s mode with files: %s", task_id, mode, received_files)

    return {
        "task_id": task_id,
        "mode": normalized_mode,
        "received_files": received_files,
        "status": "accepted",
    }


@app.get("/result/{task_id}")
async def get_result(task_id: str) -> Dict[str, Any]:
    """Return task status and placeholder result metadata."""
    logger.info("Fetching result metadata for task %s", task_id)
    return {
        "task_id": task_id,
        "status": "processing",
        "metadata": {
            "message": "Result generation in progress",
            "estimated_seconds_remaining": 120,
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )
