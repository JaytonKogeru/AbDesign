"""Pydantic models for file upload requests and responses."""
from __future__ import annotations

import importlib.util
from typing import List, Optional

from pydantic import BaseModel, Field, validator

from api.config import get_settings

ALLOWED_EXTENSIONS = {"pdb", "cif"}
MAX_FILE_SIZE = get_settings().max_file_size

_fastapi_spec = importlib.util.find_spec("fastapi")
if _fastapi_spec:
    from fastapi import UploadFile
else:
    UploadFile = object  # type: ignore[misc]


class UploadRequest(BaseModel):
    """Request model representing an uploaded structure file."""

    file_name: str = Field(..., description="Original filename from the upload")
    file_size: int = Field(..., description="Size of the uploaded file in bytes")
    content: bytes = Field(..., description="Raw file content")

    @validator("file_name")
    def validate_extension(cls, value: str) -> str:  # noqa: D417
        extension = value.split(".")[-1].lower()
        if extension not in ALLOWED_EXTENSIONS:
            raise ValueError(f"Unsupported file extension: {extension}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}")
        return value

    @validator("file_size")
    def validate_file_size(cls, value: int) -> int:  # noqa: D417
        if value <= 0:
            raise ValueError("File is empty or size not provided")
        if value > MAX_FILE_SIZE:
            raise ValueError(f"File exceeds maximum size of {MAX_FILE_SIZE // (1024 * 1024)} MB")
        return value


class ParsedStructure(BaseModel):
    """Details extracted from the uploaded structure file."""

    chain_count: int = Field(..., description="Number of chains in the structure")
    atom_count: int = Field(..., description="Total atom count in the structure")


class UploadResponse(BaseModel):
    """Response model summarizing file storage and validation results."""

    task_id: str = Field(..., description="Server-generated identifier for the upload")
    original_name: str = Field(..., description="Filename supplied by the client")
    stored_path: str = Field(..., description="Location of the stored raw file")
    converted_path: Optional[str] = Field(None, description="Path to the normalized PDB output")
    conversion_log: List[str] = Field(default_factory=list, description="Log entries from conversion/normalization")
    parsed: Optional[ParsedStructure] = Field(None, description="Counts extracted during validation")


__all__ = [
    "ALLOWED_EXTENSIONS",
    "MAX_FILE_SIZE",
    "ParsedStructure",
    "UploadRequest",
    "UploadResponse",
    "UploadFile",
]
