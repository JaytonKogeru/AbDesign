"""Utilities for storing uploaded files in temporary task-scoped directories."""
from __future__ import annotations

import importlib.util
import os
import secrets
import shutil
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Tuple

from . import schemas

_gemmi_spec = importlib.util.find_spec("gemmi")
if _gemmi_spec:
    import gemmi  # type: ignore
else:
    gemmi = None  # type: ignore


def generate_task_id() -> str:
    """Generate a unique task identifier."""

    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    random_token = secrets.token_hex(8)
    return f"task-{timestamp}-{random_token}"


def create_temp_directory(base_dir: os.PathLike | str, task_id: str) -> Path:
    """Create a task-specific temporary directory."""

    base_path = Path(base_dir)
    base_path.mkdir(parents=True, exist_ok=True)
    task_path = base_path / task_id
    task_path.mkdir(parents=True, exist_ok=True)
    return task_path


def _normalized_filename(original_name: str) -> str:
    suffix = Path(original_name).suffix
    return f"input{suffix}"


def save_file(content: bytes, destination_dir: Path, original_name: str) -> Path:
    """Write uploaded bytes to disk using a normalized filename."""

    destination = destination_dir / _normalized_filename(original_name)
    destination.write_bytes(content)
    return destination


def convert_to_pdb(source: Path, destination_dir: Path) -> Tuple[Path, List[str]]:
    """Normalize structures to PDB format when possible."""

    logs: List[str] = []
    source_suffix = source.suffix.lower()
    if source_suffix == ".pdb":
        logs.append("File already in PDB format; no conversion necessary.")
        return source, logs

    target = destination_dir / f"{source.stem}.pdb"
    if source_suffix == ".cif":
        if gemmi is None:
            logs.append("gemmi not available; unable to convert CIF to PDB. Using original file.")
            return source, logs

        try:
            structure = gemmi.read_structure(str(source))
            structure.remove_empty_models()
            structure.write_pdb(str(target))
            logs.append(f"Converted CIF to PDB using gemmi -> {target.name}.")
            return target, logs
        except Exception as exc:  # noqa: BLE001
            logs.append(f"Failed to convert CIF with gemmi: {exc}. Using original file.")
            return source, logs

    logs.append("Unrecognized extension for conversion; storing original file only.")
    return source, logs


def save_upload(request: schemas.UploadRequest, base_dir: os.PathLike | str = "/tmp/structure_uploads") -> schemas.UploadResponse:
    """Persist an upload to disk and normalize to PDB when possible."""

    task_id = generate_task_id()
    task_dir = create_temp_directory(base_dir, task_id)
    stored_path = save_file(request.content, task_dir, request.file_name)
    converted_path, conversion_log = convert_to_pdb(stored_path, task_dir)

    return schemas.UploadResponse(
        task_id=task_id,
        original_name=request.file_name,
        stored_path=str(stored_path),
        converted_path=str(converted_path) if converted_path else None,
        conversion_log=conversion_log,
    )


def store_and_validate_upload(request: schemas.UploadRequest, base_dir: os.PathLike | str = "/tmp/structure_uploads") -> schemas.UploadResponse:
    """Save an upload, normalize the file, then validate its contents."""

    from .validators import validate_and_update_response

    response = save_upload(request, base_dir=base_dir)
    return validate_and_update_response(response)


def cleanup_tasks(base_dir: os.PathLike | str, task_ids: Iterable[str]) -> None:
    """Remove task directories when they are no longer needed."""

    for task_id in task_ids:
        task_path = Path(base_dir) / task_id
        if task_path.exists():
            shutil.rmtree(task_path, ignore_errors=True)
