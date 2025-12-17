"""Utilities for standardizing structures and deriving downstream artifacts."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from pipeline.cdr import annotate_cdrs
from pipeline.epitope.mapping import MappingResidueV2, MappingResultV2, build_residue_mapping_v2
from pipeline.epitope.standardize import standardize_structure

LOGGER = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency
    from Bio import pairwise2
    from Bio.Data.IUPACData import protein_letters_3to1_extended as _AA_MAP
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    pairwise2 = None
    _AA_MAP = {}


def normalize_and_derive(
    scaffold_path: str,
    target_path: str,
    output_dir: str,
    numbering_scheme: str = "chothia",
    chain_role_map: Optional[Dict[str, str]] = None,
) -> Dict[str, object]:
    """Standardize structures and derive mapping/CDR annotations."""

    chain_role_map = chain_role_map or {}
    output_root = Path(output_dir)
    scaffold_dir = output_root / "scaffold"
    target_dir = output_root / "target"
    scaffold_dir.mkdir(parents=True, exist_ok=True)
    target_dir.mkdir(parents=True, exist_ok=True)

    scaffold_standardized = standardize_structure(Path(scaffold_path), scaffold_dir)
    scaffold_mapping = build_residue_mapping_v2(scaffold_standardized)
    scaffold_mapping_path = scaffold_dir / "mapping.json"
    scaffold_mapping.write_json(scaffold_mapping_path)

    scaffold_cdr_dir = scaffold_dir / "cdr"
    cdr_payload = annotate_cdrs(
        Path(scaffold_path),
        scaffold_cdr_dir,
        scheme=numbering_scheme,
        chain_id=chain_role_map.get("scaffold"),
    )
    scaffold_cdr_json = scaffold_cdr_dir / "cdr_annotations.json"

    cdr_mapping_path = scaffold_dir / "cdr_label_mapping.json"
    cdr_mapping_payload = _map_cdrs_to_standardized(
        cdr_payload,
        scaffold_mapping,
        chain_id=chain_role_map.get("scaffold"),
    )
    cdr_mapping_path.write_text(json.dumps(cdr_mapping_payload, indent=2))

    artifacts: Dict[str, object] = {
        "scaffold_standardized": str(scaffold_standardized.standardized_path),
        "scaffold_mapping": scaffold_mapping,
        "scaffold_mapping_json": str(scaffold_mapping_path),
        "scaffold_cdr_annotations": str(scaffold_cdr_json),
        "scaffold_cdr_mappings_json": str(cdr_mapping_path),
        "scaffold_hlt_path": None,
        "boltzgen_yaml": None,
        "target_standardized": None,
        "target_mapping": None,
        "target_mapping_json": None,
        "target_hotspots_resolved": None,
    }

    if target_path:
        target_standardized = standardize_structure(Path(target_path), target_dir)
        target_mapping = build_residue_mapping_v2(target_standardized)
        target_mapping_path = target_dir / "mapping.json"
        target_mapping.write_json(target_mapping_path)

        artifacts.update(
            {
                "target_standardized": str(target_standardized.standardized_path),
                "target_mapping": target_mapping,
                "target_mapping_json": str(target_mapping_path),
            }
        )

    return artifacts


def _map_cdrs_to_standardized(
    cdr_payload: Dict[str, object],
    mapping: MappingResultV2,
    chain_id: Optional[str] = None,
) -> Dict[str, object]:
    if not cdr_payload or cdr_payload.get("status") != "succeeded":
        reason = cdr_payload.get("reason", "cdr annotation unavailable") if isinstance(cdr_payload, dict) else "cdr annotation unavailable"
        return {"status": "failed", "reason": reason, "cdr_mappings": []}

    chain_sequences = _chain_sequences(mapping)
    target_chain_id = chain_id or next(iter(chain_sequences), None)
    if not target_chain_id:
        return {"status": "failed", "reason": "no chains available in standardized structure", "cdr_mappings": []}

    chain_info = chain_sequences.get(target_chain_id)
    if chain_info is None:
        available = ", ".join(sorted(chain_sequences)) or "none"
        return {
            "status": "failed",
            "reason": f"chain {target_chain_id} not found in standardized structure (available: {available})",
            "cdr_mappings": [],
        }

    mappings: List[Dict[str, object]] = []
    for segment in cdr_payload.get("cdrs", []):
        mapped = _map_segment_to_chain(segment, chain_info["sequence"], chain_info["residues"])
        mappings.append(mapped)

    return {"status": "succeeded", "chain_id": target_chain_id, "cdr_mappings": mappings}


def _chain_sequences(mapping: MappingResultV2) -> Dict[str, Dict[str, object]]:
    chains: Dict[str, Dict[str, object]] = {}
    for chain_id, residues in mapping.by_chain().items():
        sorted_residues = sorted(residues, key=lambda res: res.present_seq_id)
        sequence = "".join(_three_to_one(res.resname3) for res in sorted_residues)
        chains[chain_id] = {"sequence": sequence, "residues": sorted_residues}
    return chains


def _three_to_one(resname: str) -> str:
    if not resname:
        return "X"
    res_upper = resname.upper()
    try:
        return _AA_MAP.get(res_upper, _AA_MAP.get(res_upper.title(), "X"))
    except Exception:  # noqa: BLE001
        return "X"


def _map_segment_to_chain(
    segment: Dict[str, object],
    chain_sequence: str,
    residues: Sequence[MappingResidueV2],
) -> Dict[str, object]:
    sequence = str(segment.get("sequence") or "")
    name = segment.get("name")
    if not sequence:
        return {
            "cdr_name": name,
            "status": "failed",
            "reason": "empty CDR sequence",
            "cdr_sequence": sequence,
        }

    start_idx = _locate_subsequence(chain_sequence, sequence)
    if start_idx is None:
        return {
            "cdr_name": name,
            "status": "failed",
            "reason": "cdr sequence could not be aligned to scaffold chain",
            "cdr_sequence": sequence,
        }

    end_idx = start_idx + len(sequence) - 1
    if end_idx >= len(residues):
        return {
            "cdr_name": name,
            "status": "failed",
            "reason": "aligned indices exceed residue list",
            "cdr_sequence": sequence,
        }

    start_res = residues[start_idx]
    end_res = residues[end_idx]

    return {
        "cdr_name": name,
        "cdr_sequence": sequence,
        "label_seq_id_start": start_res.label_seq_id,
        "label_seq_id_end": end_res.label_seq_id,
        "absolute_start": start_res.present_seq_id,
        "absolute_end": end_res.present_seq_id,
        "status": "mapped",
    }


def _locate_subsequence(chain_sequence: str, query: str) -> Optional[int]:
    if not chain_sequence:
        return None

    if pairwise2:
        try:
            alignments = pairwise2.align.localms(chain_sequence, query, 2, -1, -5, -0.5)  # type: ignore[arg-type]
            if alignments:
                best = max(alignments, key=lambda aln: aln[2])
                return best[3]
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("pairwise2 alignment failed; falling back to substring search: %s", exc)

    idx = chain_sequence.find(query)
    return idx if idx >= 0 else None
