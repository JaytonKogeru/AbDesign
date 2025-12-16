"""CDR annotation helpers powered by the upstream AbNumber package.

The vendored subset of AbNumber previously shipped with this repository is
insufficient for accurate numbering. This module relies on the upstream
``abnumber`` distribution (installed with the ``[anarci]`` extra) and converts
its results into JSON/CSV artifacts while keeping the output field names stable
for API consumers.
"""
from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from abnumber import Chain
from Bio.PDB import MMCIFParser, PDBParser, PPBuilder

LOGGER = logging.getLogger(__name__)


@dataclass
class CDRArtifacts:
    """Paths to the serialized CDR annotations."""

    json_path: Path
    csv_path: Path


def annotate_cdrs(
    structure_path: Path,
    output_dir: Path,
    scheme: str = "chothia",
    chain_type: str = "H",
    chain_id: Optional[str] = None,
) -> Mapping[str, Any]:
    """Annotate CDRs for a VHH chain using upstream AbNumber.

    The returned payload is serialized to ``cdr_annotations.json`` and
    ``cdr_annotations.csv`` to preserve compatibility with existing consumers.
    Numbering labels are stringified (e.g., ``52A``) so that insertion positions
    remain stable in the JSON/CSV outputs.
    """

    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "cdr_annotations.json"
    csv_path = output_dir / "cdr_annotations.csv"

    try:
        sequence = _extract_sequence(structure_path, chain_id)
    except ValueError as exc:  # noqa: BLE001
        payload: Dict[str, Any] = {
            "status": "failed",
            "reason": str(exc),
            "scheme": scheme,
            "chain_type": chain_type,
            "sequence": None,
            "cdrs": {},
            "numbering": [],
        }
        json_path.write_text(json.dumps(payload, indent=2))
        csv_path.write_text("name,start,end,length,sequence\n")
        return payload

    cdr_segments: List[Dict[str, Any]] = []
    numbering_labels: List[str] = []
    try:
        chain = Chain(sequence, scheme=scheme, chain_type=chain_type)

        numbering_labels = [_position_label(pos) for pos in getattr(chain, "numbering", [])]
        cdr_segments = _collect_cdrs(chain)

        payload = {
            "status": "succeeded",
            "scheme": scheme,
            "chain_type": chain_type,
            "sequence": sequence,
            "numbering": numbering_labels,
            "cdrs": cdr_segments,
        }
    except Exception as exc:  # noqa: BLE001
        payload = {
            "status": "failed",
            "reason": str(exc),
            "scheme": scheme,
            "chain_type": chain_type,
            "sequence": sequence,
            "cdrs": [],
            "numbering": [],
        }

    json_path.write_text(json.dumps(payload, indent=2))
    _write_cdr_csv(csv_path, cdr_segments)

    return payload


def _extract_sequence(structure_path: Path, chain_id: Optional[str]) -> str:
    parser = _select_parser(structure_path)
    structure = parser.get_structure("query", str(structure_path))

    chain = _select_chain(structure, chain_id)
    peptides = PPBuilder().build_peptides(chain)
    if not peptides:
        raise ValueError(f"No polypeptide chains found in {structure_path}")

    sequence = str(peptides[0].get_sequence())
    if not sequence:
        raise ValueError(f"Empty sequence extracted from {structure_path}")
    return sequence


def _select_parser(structure_path: Path):
    suffix = structure_path.suffix.lower()
    if suffix == ".cif":
        return MMCIFParser(QUIET=True)
    return PDBParser(QUIET=True)


def _select_chain(structure, chain_id: Optional[str]):
    chains = list(structure.get_chains())
    if not chains:
        raise ValueError("No chains found in structure")

    if chain_id:
        for chain in chains:
            if chain.id.strip() == chain_id:
                return chain
        raise ValueError(f"Chain {chain_id} not found in structure")

    if len(chains) > 1:
        LOGGER.warning("Multiple chains present; defaulting to first chain %s", chains[0].id)
    return chains[0]


def _position_label(position: Any) -> str:
    """Convert AbNumber position objects to stable string labels."""

    if position is None:
        return ""
    for attr in ("label", "to_str", "__str__"):
        value = getattr(position, attr, None)
        if callable(value):
            try:
                return str(value())
            except Exception:  # noqa: BLE001
                continue
        if value is not None:
            return str(value)
    return str(position)


def _collect_cdrs(chain: Any) -> List[Dict[str, Any]]:
    segments: List[Dict[str, Any]] = []

    cdr_map: Mapping[str, Any] = {}
    cdr_attr = getattr(chain, "cdrs", None)
    if isinstance(cdr_attr, Mapping):
        cdr_map = cdr_attr
    elif isinstance(cdr_attr, Iterable):
        try:
            cdr_map = {seg.name if hasattr(seg, "name") else f"cdr{idx}": seg for idx, seg in enumerate(cdr_attr, start=1)}
        except Exception:  # noqa: BLE001
            cdr_map = {}

    if not cdr_map:
        # Fall back to attribute-based accessors when the structure is not a mapping.
        for name in ("cdr1", "cdr2", "cdr3"):
            seq_value = getattr(chain, f"{name}_seq", None)
            if seq_value:
                cdr_map[name.upper()] = {"sequence": str(seq_value), "positions": []}

    for name, region in cdr_map.items():
        region_seq = _extract_region_sequence(region)
        positions = _extract_region_positions(region)

        start_label = positions[0]["position"] if positions else None
        end_label = positions[-1]["position"] if positions else None

        segments.append(
            {
                "name": name if isinstance(name, str) else str(name),
                "sequence": region_seq,
                "positions": positions,
                "start": start_label,
                "end": end_label,
                "length": len(region_seq),
            }
        )

    return segments


def _extract_region_sequence(region: Any) -> str:
    for attr in ("seq", "sequence", "aa_sequence"):
        value = getattr(region, attr, None)
        if value:
            return str(value)
    if isinstance(region, str):
        return region
    return ""


def _extract_region_positions(region: Any) -> List[Dict[str, str]]:
    positions: List[Dict[str, str]] = []
    residues = getattr(region, "residues", None)
    if residues is None:
        residues = getattr(region, "residue_numbers", None)

    if residues is None:
        return positions

    for residue in residues:
        label = None
        aa = None
        if hasattr(residue, "position"):
            label = _position_label(getattr(residue, "position"))
        if hasattr(residue, "aa"):
            aa = getattr(residue, "aa")
        positions.append({"position": label or "", "aa": aa or ""})
    return positions


def _write_cdr_csv(destination: Path, cdr_segments: Iterable[Mapping[str, Any]]) -> None:
    with destination.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["name", "start", "end", "length", "sequence"],
        )
        writer.writeheader()
        for segment in cdr_segments:
            writer.writerow(
                {
                    "name": segment.get("name"),
                    "start": segment.get("start"),
                    "end": segment.get("end"),
                    "length": segment.get("length"),
                    "sequence": segment.get("sequence"),
                }
            )
