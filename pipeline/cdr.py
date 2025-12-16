"""Utilities for annotating CDR regions using AbNumber."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, MutableMapping, Tuple

from third_party.abnumber import Chain

_THREE_TO_ONE = {
    "ALA": "A",
    "ARG": "R",
    "ASN": "N",
    "ASP": "D",
    "CYS": "C",
    "GLN": "Q",
    "GLU": "E",
    "GLY": "G",
    "HIS": "H",
    "ILE": "I",
    "LEU": "L",
    "LYS": "K",
    "MET": "M",
    "PHE": "F",
    "PRO": "P",
    "SER": "S",
    "THR": "T",
    "TRP": "W",
    "TYR": "Y",
    "VAL": "V",
}


@dataclass
class ChainAnnotation:
    """CDR annotation for a single chain."""

    chain_id: str
    sequence: str
    cdrs: List[Dict[str, object]]
    numbering: List[Dict[str, object]]


@dataclass
class CDRAnnotationResult:
    """Wrapper object for CDR annotations."""

    scheme: str
    chains: List[ChainAnnotation]


class SequenceParsingError(RuntimeError):
    """Raised when sequences cannot be extracted from a structure."""


class NoChainsFoundError(RuntimeError):
    """Raised when no chains are detected during parsing."""


def annotate_cdrs(structure_path: Path | str, scheme: str = "chothia") -> CDRAnnotationResult:
    """Annotate CDR regions for chains in the given structure file."""

    structure = Path(structure_path)
    sequences = _extract_sequences(structure)
    if not sequences:
        raise NoChainsFoundError(f"No chains found in {structure}")

    chain_annotations: List[ChainAnnotation] = []
    for chain_id, sequence in sequences.items():
        chain = Chain(sequence, scheme=scheme, chain_type="H")
        cdr_entries = [
            {
                "name": name,
                "start": values["start"],
                "end": values["end"],
                "sequence": values["sequence"],
            }
            for name, values in chain.cdrs.items()
        ]
        numbering = [
            {"position": position, "residue": residue} for position, residue in chain.numbering
        ]
        chain_annotations.append(
            ChainAnnotation(
                chain_id=chain_id,
                sequence=sequence,
                cdrs=cdr_entries,
                numbering=numbering,
            )
        )

    return CDRAnnotationResult(scheme=scheme, chains=chain_annotations)


def _extract_sequences(structure: Path) -> Mapping[str, str]:
    """Parse chain sequences from a PDB-like structure file."""

    if not structure.exists():
        raise FileNotFoundError(structure)

    raw_sequences: MutableMapping[str, List[str]] = {}
    seen_residues: set[Tuple[str, str]] = set()

    for line in _iter_structure_lines(structure):
        if not line.startswith("ATOM"):
            continue
        if len(line) < 26:
            continue
        chain_id = line[21].strip() or "?"
        res_name = line[17:20].strip().upper()
        res_seq = line[22:26].strip()

        residue_key = (chain_id, res_seq)
        if residue_key in seen_residues:
            continue
        seen_residues.add(residue_key)

        amino_acid = _THREE_TO_ONE.get(res_name, "X")
        raw_sequences.setdefault(chain_id, []).append(amino_acid)

    return {cid: "".join(residues) for cid, residues in raw_sequences.items()}


def _iter_structure_lines(structure: Path) -> Iterable[str]:
    content = structure.read_text().splitlines()
    for line in content:
        yield line.rstrip("\n")


__all__ = ["annotate_cdrs", "CDRAnnotationResult", "ChainAnnotation", "SequenceParsingError"]
