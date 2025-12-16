"""Minimal AbNumber-compatible utilities for CDR annotation.

This lightweight implementation mirrors the small subset of the
`abnumber` API that the pipeline relies upon. It is intentionally
simple yet deterministic so unit tests remain stable even without
external dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


def _segment_cdrs(sequence: str) -> Dict[str, Tuple[int, int]]:
    """Split a sequence into three contiguous CDR-like regions.

    The boundaries are heuristic and only aim to provide repeatable
    slices for downstream reporting. CDR1 is capped at eight residues,
    CDR2 follows with up to eight residues, and CDR3 consumes the rest
    of the sequence.
    """

    length = len(sequence)
    if length == 0:
        return {"CDR1": (0, 0), "CDR2": (0, 0), "CDR3": (0, 0)}

    cdr1_end = min(length, 8)
    cdr2_end = min(length, cdr1_end + 8)
    cdr3_end = length

    cdr1_start = 1
    cdr2_start = min(cdr1_end + 1, length) if length > cdr1_end else cdr1_end
    cdr3_start = min(cdr2_end + 1, length) if length > cdr2_end else cdr2_end

    return {
        "CDR1": (cdr1_start, cdr1_end),
        "CDR2": (cdr2_start, cdr2_end),
        "CDR3": (cdr3_start, cdr3_end),
    }


@dataclass
class Chain:
    """A pared-down representation of an antibody chain."""

    sequence: str
    scheme: str = "chothia"
    chain_type: str = "H"

    def __post_init__(self) -> None:
        self.sequence = self.sequence.replace(" ", "").upper()
        self._cdr_regions = _segment_cdrs(self.sequence)
        self.numbering: List[Tuple[int, str]] = [
            (index, residue) for index, residue in enumerate(self.sequence, start=1)
        ]

    @property
    def cdrs(self) -> Dict[str, Dict[str, object]]:
        """Return start/end boundaries and sequences for the three CDRs."""

        result: Dict[str, Dict[str, object]] = {}
        for name, (start, end) in self._cdr_regions.items():
            if start == 0 and end == 0:
                subseq = ""
            else:
                subseq = self.sequence[start - 1 : end]
            result[name] = {"start": start, "end": end, "sequence": subseq}
        return result


__all__ = ["Chain"]
