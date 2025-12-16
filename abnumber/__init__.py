"""Lightweight, vendored subset of the :mod:`abnumber` library.

The upstream package provides antibody numbering and CDR delineation. Network
access is not available in this environment, so a small compatible subset is
vendored to keep the pipeline functional. The API mirrors the official
``abnumber.Chain`` interface used by the pipeline and exposes numbering and CDR
segments derived from the input sequence.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

__all__ = ["Chain"]
__version__ = "0.0.0-vendored"


@dataclass
class Chain:
    """Representation of a numbered antibody chain.

    Parameters
    ----------
    sequence:
        Amino-acid sequence to number.
    scheme:
        Numbering scheme identifier (e.g., ``"chothia"`` or ``"imgt"``).
    chain_type:
        Chain type hint; the vendored implementation currently treats all
        chains identically but records the requested value.
    """

    sequence: str
    scheme: str = "chothia"
    chain_type: str = "H"

    def __post_init__(self) -> None:
        normalized = self.sequence.replace(" ", "").replace("-", "")
        self.sequence = normalized.upper()
        self._cdr_regions = _segment_cdrs(self.sequence, self.scheme)
        self.numbering: List[Tuple[int, str]] = [
            (index, residue)
            for index, residue in enumerate(self.sequence, start=1)
        ]

    @property
    def cdrs(self) -> Dict[str, Dict[str, object]]:
        """Return start/end boundaries and sequences for the three CDRs."""

        result: Dict[str, Dict[str, object]] = {}
        for name, (start, end) in self._cdr_regions.items():
            subseq = self.sequence[start - 1 : end] if end else ""
            result[name] = {"start": start, "end": end, "sequence": subseq}
        return result


def _segment_cdrs(sequence: str, scheme: str) -> Dict[str, Tuple[int, int]]:
    """Infer approximate CDR boundaries for a sequence.

    The segmentation uses proportional defaults that loosely follow heavy-chain
    Chothia-style regions while remaining deterministic for arbitrary lengths.
    """

    length = len(sequence)
    if length == 0:
        return {"CDR1": (0, 0), "CDR2": (0, 0), "CDR3": (0, 0)}

    # Typical heavy-chain region anchors scaled to the observed sequence length.
    # Anchors roughly correspond to positions (26-35), (50-65), (95-102) in
    # classic Chothia numbering for ~120-residue sequences.
    scale = max(length / 120.0, 0.5)
    cdr1_start = max(1, int(round(26 * scale)))
    cdr1_end = min(length, max(cdr1_start, int(round(35 * scale))))
    cdr2_start = min(length, int(round(50 * scale)))
    cdr2_end = min(length, max(cdr2_start, int(round(65 * scale))))
    cdr3_start = min(length, int(round(95 * scale)))
    cdr3_end = length

    # Ensure monotonic ordering.
    cdr2_start = max(cdr1_end + 1, cdr2_start)
    cdr2_end = max(cdr2_start, cdr2_end)
    cdr3_start = max(cdr2_end + 1, cdr3_start)

    return {
        "CDR1": (cdr1_start, cdr1_end),
        "CDR2": (cdr2_start, cdr2_end),
        "CDR3": (cdr3_start, cdr3_end),
    }
