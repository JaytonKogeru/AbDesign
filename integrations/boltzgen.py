"""Adapters for boltzgen YAML generation and validation."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Mapping, MutableMapping

import yaml

from pipeline.epitope.mapping import MappingResultV2

LOGGER = logging.getLogger(__name__)


def ensure_boltzgen_yaml(path: Path) -> Path:
    """Return the provided YAML path to satisfy import checks."""
    return Path(path)


def generate_boltzgen_yaml(
    standardized_scaffold,
    scaffold_mapping: MappingResultV2,
    cdr_label_ranges: Mapping[str, object] | None,
    target_standardized_path: Path | None,
    output_yaml_path: Path,
    protocol: str = "nanobody-anything",
) -> Path:
    """Generate a BoltzGen design YAML using label_seq_id indices."""

    output_yaml_path = Path(output_yaml_path)
    output_yaml_path.parent.mkdir(parents=True, exist_ok=True)

    scaffold_entry: Dict[str, object] = {
        "file": str(standardized_scaffold.standardized_path),
        "design": _cdr_design_ranges(scaffold_mapping, cdr_label_ranges),
        "design_insertions": _cdr_insertions(cdr_label_ranges, scaffold_mapping),
    }

    payload: Dict[str, object] = {"protocol": protocol, "scaffolds": [scaffold_entry]}

    if target_standardized_path:
        payload["target"] = {
            "file": str(target_standardized_path),
            "binding_types": _binding_types_from_cdrs(scaffold_mapping, cdr_label_ranges),
        }

    output_yaml_path.write_text(yaml.safe_dump(payload, sort_keys=False))
    return output_yaml_path


def _cdr_design_ranges(
    scaffold_mapping: MappingResultV2, cdr_label_ranges: Mapping[str, object] | None
) -> List[Dict[str, Dict[str, str]]]:
    if not cdr_label_ranges or cdr_label_ranges.get("status") != "succeeded":
        return []

    chain_id_value = cdr_label_ranges.get("chain_id")
    if chain_id_value is None:
        return []

    chain_id = str(chain_id_value)
    label_chain = scaffold_mapping.standardized.chain_id_map.get(chain_id, chain_id)

    design: List[Dict[str, Dict[str, str]]] = []
    for cdr in cdr_label_ranges.get("cdr_mappings", []):
        if cdr.get("status") != "mapped":
            continue

        start = cdr.get("label_seq_id_start")
        end = cdr.get("label_seq_id_end")
        if start is None or end is None:
            continue

        start_idx, end_idx = sorted((int(start), int(end)))
        design.append({"chain": {"id": label_chain, "res_index": f"{start_idx}..{end_idx}"}})

    return design


def _cdr_insertions(
    cdr_label_ranges: Mapping[str, object] | None, mapping: MappingResultV2
) -> List[Dict[str, Dict[str, object]]]:
    if not cdr_label_ranges or cdr_label_ranges.get("status") != "succeeded":
        return []

    chain_id_value = cdr_label_ranges.get("chain_id")
    if chain_id_value is None:
        return []

    chain_id = str(chain_id_value)
    label_chain = mapping.standardized.chain_id_map.get(chain_id, chain_id)

    insertions: List[Dict[str, Dict[str, object]]] = []
    for cdr in cdr_label_ranges.get("cdr_mappings", []):
        if cdr.get("status") != "mapped":
            continue

        if "insertion_length" not in cdr:
            continue

        insertion = cdr.get("insertion_length")
        if not isinstance(insertion, Mapping):
            continue

        num_res = insertion.get("num_residues")
        if num_res is None:
            continue

        start = cdr.get("label_seq_id_start")
        end = cdr.get("label_seq_id_end")
        if start is None or end is None:
            continue

        start_idx, end_idx = sorted((int(start), int(end)))
        insertions.append(
            {
                "chain": {
                    "id": label_chain,
                    "res_index": f"{start_idx}..{end_idx}",
                    "num_residues": str(num_res),
                }
            }
        )

    return insertions


def _binding_types_from_cdrs(
    mapping: MappingResultV2, cdr_label_ranges: Mapping[str, object] | None
) -> List[Dict[str, Dict[str, str]]]:
    if not cdr_label_ranges or cdr_label_ranges.get("status") != "succeeded":
        return []

    chain_id_value = cdr_label_ranges.get("chain_id")
    if chain_id_value is None:
        return []

    chain_id = str(chain_id_value)
    label_chain = mapping.standardized.chain_id_map.get(chain_id, chain_id)

    binding: MutableMapping[str, List[int]] = {}
    for cdr in cdr_label_ranges.get("cdr_mappings", []):
        if cdr.get("status") != "mapped":
            continue

        start = cdr.get("label_seq_id_start")
        end = cdr.get("label_seq_id_end")
        if start is None or end is None:
            continue

        start_idx, end_idx = sorted((int(start), int(end)))
        binding.setdefault(label_chain, []).extend(range(start_idx, end_idx + 1))

    binding_types: List[Dict[str, Dict[str, str]]] = []
    for chain, indices in binding.items():
        indices_sorted = sorted(set(indices))
        binding_types.append({"chain": {"id": chain, "binding": ",".join(map(str, indices_sorted))}})

    return binding_types
