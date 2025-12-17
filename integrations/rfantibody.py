"""Adapters for integrating RFantibody workflows."""
from __future__ import annotations


def ensure_rfantibody_available() -> bool:
    """Lightweight probe to check RFantibody integration availability."""

    try:
        import importlib  # noqa: WPS433

        importlib.import_module("rfantibody")
    except ModuleNotFoundError:
        return False
    return True
