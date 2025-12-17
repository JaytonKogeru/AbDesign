"""Pipeline package for running prediction workflows."""

from .cdr import annotate_cdrs

__all__ = ["annotate_cdrs"]
