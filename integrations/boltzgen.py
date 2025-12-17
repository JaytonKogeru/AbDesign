"""Adapters for boltzgen YAML generation and validation."""
from __future__ import annotations

from pathlib import Path


def ensure_boltzgen_yaml(path: Path) -> Path:
    """Return the provided YAML path to satisfy import checks."""

    return Path(path)
