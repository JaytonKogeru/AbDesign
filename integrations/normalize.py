"""Utilities for standardizing structures and deriving downstream artifacts."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from integrations.boltzgen import generate_boltzgen_yaml
from pipeline.cdr import annotate_cdrs
from pipeline.epitope.mapping import MappingResidueV2, MappingResultV2, build_residue_mapping_v2
from pipeline.epitope.standardize import StandardizedStructure, standardize_structure

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

    hlt_path = scaffold_dir / "scaffold.HLT.pdb"
    chain_map_path = hlt_path.with_suffix(".chain_map.json")
    try:
        generate_hlt(
            scaffold_standardized,
            scaffold_mapping,
            cdr_mapping_payload,
            hlt_path,
            chain_role_map or {},
        )
        hlt_chain_map = chain_map_path
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("HLT generation failed: %s", exc)
        hlt_chain_map = None

    artifacts: Dict[str, object] = {
        "scaffold_standardized": str(scaffold_standardized.standardized_path),
        "scaffold_mapping": scaffold_mapping,
        "scaffold_mapping_json": str(scaffold_mapping_path),
        "scaffold_cdr_annotations": str(scaffold_cdr_json),
        "scaffold_cdr_mappings_json": str(cdr_mapping_path),
        "scaffold_hlt_path": str(hlt_path) if hlt_path.exists() else None,
        "scaffold_chain_map_json": str(chain_map_path) if hlt_chain_map and chain_map_path.exists() else None,
        "boltzgen_yaml": None,
        "target_standardized": None,
        "target_mapping": None,
        "target_mapping_json": None,
        "target_hotspots_resolved": None,
    }

    target_standardized = None
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

    try:
        boltzgen_yaml_path = scaffold_dir / "boltzgen.yaml"
        boltz_yaml = generate_boltzgen_yaml(
            scaffold_standardized,
            scaffold_mapping,
            cdr_mapping_payload,
            target_standardized.standardized_path if target_standardized else None,
            boltzgen_yaml_path,
        )
        artifacts["boltzgen_yaml"] = str(boltz_yaml)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("BoltzGen YAML generation failed: %s", exc)

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


def generate_hlt(
    standardized_scaffold: StandardizedStructure,
    scaffold_mapping: MappingResultV2,
    cdr_annotations: Dict[str, object],
    output_hlt_path: Path,
    chain_role_map: Optional[Dict[str, str]] = None,
) -> Path:
    """Generate an HLT PDB with RFantibody-compatible REMARKs.

    The resulting PDB re-chains the scaffold and target into the canonical
    Heavy/Light/Target order and embeds ``PDBinfo-LABEL`` REMARK lines to mark
    CDR start/end indices using absolute residue positions in the written file.
    A ``chain_map.json`` is written alongside the PDB to trace the original
    chain identifiers.
    """

    gemmi = _require_gemmi()
    output_hlt_path = Path(output_hlt_path)
    output_hlt_path.parent.mkdir(parents=True, exist_ok=True)

    structure = gemmi.read_structure(str(standardized_scaffold.standardized_path))
    if not structure:
        raise RuntimeError("standardized scaffold contains no models")

    chain_role_map = chain_role_map or {}
    orig_chains: List[str] = [chain.name for chain in structure[0]]
    chain_name_map = _assign_chain_names(orig_chains, chain_role_map)
    reverse_chain_map = {new: orig for orig, new in chain_name_map.items()}

    new_structure = gemmi.Structure()
    new_structure.cell = structure.cell
    new_structure.spacegroup_hm = structure.spacegroup_hm

    for model in structure:
        new_model = gemmi.Model(model.name)
        for orig_chain_name in _ordered_chains(orig_chains, chain_name_map):
            chain = model[orig_chain_name]
            new_chain = chain.clone()
            new_chain.name = chain_name_map[orig_chain_name]
            new_model.add_chain(new_chain)
        new_structure.add_model(new_model)

    new_structure.write_pdb(str(output_hlt_path))
    chain_map_path = output_hlt_path.with_suffix(".chain_map.json")
    chain_map_path.write_text(json.dumps(chain_name_map, indent=2))

    absolute_by_label, absolute_by_present = _absolute_index_maps(
        new_structure, reverse_chain_map, scaffold_mapping
    )
    remark_lines = _format_cdr_remarks(cdr_annotations, absolute_by_label, absolute_by_present)
    if remark_lines:
        _inject_remarks(output_hlt_path, remark_lines)

    return output_hlt_path


def _require_gemmi():
    try:  # pragma: no cover - import guard
        import gemmi  # noqa: WPS433
    except ModuleNotFoundError as exc:  # pragma: no cover - handled path
        raise RuntimeError("gemmi is required for HLT generation. Install with 'pip install gemmi>=0.6'.") from exc
    return gemmi


def _normalize_role(value: str) -> Optional[str]:
    normalized = value.lower()
    if normalized in {"h", "heavy"}:
        return "H"
    if normalized in {"l", "light"}:
        return "L"
    if normalized in {"t", "target"}:
        return "T"
    return None


def _assign_chain_names(chain_names: Sequence[str], chain_role_map: Dict[str, str]) -> Dict[str, str]:
    roles: Dict[str, str] = {}

    for key, value in chain_role_map.items():
        role_from_key = _normalize_role(str(key))
        if role_from_key:
            roles[str(value)] = role_from_key
            continue

        role_from_value = _normalize_role(str(value))
        if role_from_value:
            roles[str(key)] = role_from_value

    mapping: Dict[str, str] = {}
    used_roles: set[str] = set()

    for chain in chain_names:
        if chain in roles:
            mapping[chain] = roles[chain]
            used_roles.add(roles[chain])

    unassigned_chains = [c for c in chain_names if c not in mapping]
    for role in ("H", "L", "T"):
        if role in used_roles or not unassigned_chains:
            continue
        chain = unassigned_chains.pop(0)
        mapping[chain] = role
        used_roles.add(role)

    available_letter = ord("A")
    for chain in unassigned_chains:
        while chr(available_letter) in used_roles:
            available_letter += 1
        mapping[chain] = chr(available_letter)
        used_roles.add(mapping[chain])
        available_letter += 1

    return mapping


def _ordered_chains(chain_names: Sequence[str], chain_name_map: Dict[str, str]) -> List[str]:
    prioritized = {"H": 0, "L": 1, "T": 2}
    return sorted(chain_names, key=lambda name: (prioritized.get(chain_name_map.get(name, ""), 3), chain_names.index(name)))


def _absolute_index_maps(
    structure, reverse_chain_map: Dict[str, str], mapping: MappingResultV2
) -> tuple[Dict[tuple[str, int], int], Dict[str, Dict[int, int]]]:
    mapping_by_label = {(res.label_asym_id, res.label_seq_id): res for res in mapping.residues}

    absolute_by_label: Dict[tuple[str, int], int] = {}
    absolute_by_present: Dict[str, Dict[int, int]] = {}
    absolute_idx = 1

    for chain in structure[0]:
        orig_name = reverse_chain_map.get(chain.name, chain.name)
        for residue in chain:
            seq_id = residue.seqid.num
            absolute_by_label[(orig_name, seq_id)] = absolute_idx

            mapping_res = mapping_by_label.get((orig_name, seq_id))
            if mapping_res:
                chain_map = absolute_by_present.setdefault(mapping_res.auth.chain, {})
                chain_map[mapping_res.present_seq_id] = absolute_idx

            absolute_idx += 1

    return absolute_by_label, absolute_by_present


def _format_cdr_remarks(
    cdr_annotations: Dict[str, object],
    absolute_by_label: Dict[tuple[str, int], int],
    absolute_by_present: Dict[str, Dict[int, int]],
) -> List[str]:
    if not cdr_annotations or cdr_annotations.get("status") != "succeeded":
        return []

    chain_id = cdr_annotations.get("chain_id")
    if not chain_id:
        return []

    lines: List[str] = []
    for cdr in cdr_annotations.get("cdr_mappings", []):
        if cdr.get("status") != "mapped":
            continue

        start_abs = _lookup_absolute_index(cdr.get("label_seq_id_start"), chain_id, absolute_by_label, absolute_by_present)
        end_abs = _lookup_absolute_index(cdr.get("label_seq_id_end"), chain_id, absolute_by_label, absolute_by_present)

        if start_abs is None or end_abs is None:
            continue

        cdr_name = cdr.get("cdr_name") or "CDR"
        lines.append(f"REMARK PDBinfo-LABEL: {start_abs:4d} {cdr_name}_start")
        lines.append(f"REMARK PDBinfo-LABEL: {end_abs:4d} {cdr_name}_end")

    return lines


def _lookup_absolute_index(
    label_seq_id: Optional[int],
    chain_id: str,
    absolute_by_label: Dict[tuple[str, int], int],
    absolute_by_present: Dict[str, Dict[int, int]],
) -> Optional[int]:
    if label_seq_id is None:
        return None

    direct = absolute_by_label.get((chain_id, label_seq_id))
    if direct is not None:
        return direct

    present_map = absolute_by_present.get(chain_id)
    if present_map:
        return present_map.get(label_seq_id)

    return None


def _inject_remarks(output_hlt_path: Path, remark_lines: List[str]) -> None:
    original = output_hlt_path.read_text().splitlines()
    updated = []
    if original:
        updated.append(original[0])
        updated.extend(remark_lines)
        updated.extend(original[1:])
    else:
        updated = remark_lines

    output_hlt_path.write_text("\n".join(updated) + "\n")
