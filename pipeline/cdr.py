"""Utilities for annotating CDR regions using AbNumber."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, MutableMapping

import gemmi

from abnumber import Chain


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
    """Parse chain sequences from a PDB or CIF structure file."""

    if not structure.exists():
        raise FileNotFoundError(structure)

    try:
        parsed = gemmi.read_structure(str(structure))
    except Exception as exc:  # noqa: BLE001
        raise SequenceParsingError(f"Failed to read structure {structure}: {exc}") from exc

    if not parsed:
        raise SequenceParsingError(f"Unable to parse structure {structure}")

    model = parsed[0]
    sequences: MutableMapping[str, List[str]] = {}
    for chain in model:
        if chain.get_polymer_type() != gemmi.PolymerType.PeptideL:
            continue
        chain_id = chain.name or "?"
        sequence = _sequence_from_chain(chain)
        if sequence:
            sequences[chain_id] = sequence

    return sequences


def _sequence_from_chain(chain: gemmi.Chain) -> str:
    residues: List[str] = []
    seen_positions: set[tuple[int, str]] = set()
    for residue in chain:
        if not residue.is_amino_acid():
            continue
        seqid = residue.seqid
        residue_key = (seqid.num, seqid.icode)
        if residue_key in seen_positions:
            continue
        seen_positions.add(residue_key)

        aa = gemmi.find_aa(residue.name)
        residues.append(aa.one_letter_code if aa else "X")

    return "".join(residues)


__all__ = ["annotate_cdrs", "CDRAnnotationResult", "ChainAnnotation", "SequenceParsingError"]
