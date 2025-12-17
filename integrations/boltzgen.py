"""Adapters for boltzgen YAML generation, validation, and execution."""
from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence

try:  # pragma: no cover - optional dependency shim
    import yaml  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - fallback stub
    class _YamlStub:
        @staticmethod
        def safe_load(stream):
            try:
                return json.loads(stream)
            except Exception:
                return {}

        @staticmethod
        def safe_dump(data, sort_keys=False):
            return json.dumps(data, sort_keys=sort_keys)

    yaml = _YamlStub()

from pipeline.epitope.mapping import MappingResultV2

LOGGER = logging.getLogger(__name__)


def ensure_boltzgen_yaml(path: Path) -> Path:
    """Return the provided YAML path to satisfy import checks."""
    return Path(path)


def run_boltzgen(
    task_dir: Path | str,
    yaml_path: Path | str,
    protocol: str = "nanobody-anything",
    num_designs: int = 50,
    *,
    mapping: MappingResultV2 | None = None,
    use_docker: bool | None = None,
    docker_image: str = "boltzgen",
    timeout: int = 3600,
    retries: int = 1,
    cache_dir: Optional[Path] = None,
) -> Dict[str, object]:
    """Run BoltzGen against a prepared YAML specification.

    Parameters
    ----------
    task_dir:
        Working directory where logs and outputs will be written.
    yaml_path:
        Path to the BoltzGen YAML produced by :func:`generate_boltzgen_yaml`.
    protocol:
        BoltzGen protocol to use.
    num_designs:
        Number of designs to generate.
    mapping:
        Optional mapping used to validate ``label_seq_id`` ranges from the YAML.
    use_docker:
        When True, execute inside a Docker container; when False, run locally;
        when ``None`` defer to the caller's default environment.
    docker_image:
        Name of the BoltzGen image if Docker execution is requested.
    timeout:
        Timeout per attempt (seconds).
    retries:
        Number of additional attempts when execution fails.
    cache_dir:
        Host cache directory (e.g., Hugging Face cache) to mount into Docker to
        avoid re-downloading model weights.
    """

    task_root = Path(task_dir).resolve()
    logs_dir = task_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    output_dir = task_root / "boltzgen_output"
    output_dir.mkdir(parents=True, exist_ok=True)

    yaml_path = Path(yaml_path).resolve()
    if not yaml_path.exists():
        raise FileNotFoundError(f"BoltzGen YAML not found: {yaml_path}")

    _validate_yaml_indices(yaml_path, mapping)

    base_cmd = [
        "boltzgen",
        "run",
        str(yaml_path),
        "--output",
        str(output_dir),
        "--protocol",
        protocol,
        "--num_designs",
        str(num_designs),
    ]

    exec_cmd: Iterable[str]
    if use_docker:
        cache_dir = cache_dir or Path.home() / ".cache" / "huggingface"
        cache_dir.mkdir(parents=True, exist_ok=True)
        exec_cmd = [
            "docker",
            "run",
            "--rm",
            "--gpus",
            "all",
            "-v",
            f"{task_root}:/home/workdir",
            "-w",
            "/home/workdir",
            "-v",
            f"{cache_dir}:{cache_dir}",
            docker_image,
            *base_cmd,
        ]
    else:
        exec_cmd = base_cmd

    stdout_path = logs_dir / "boltzgen.stdout.log"
    stderr_path = logs_dir / "boltzgen.stderr.log"

    attempt = 0
    completed: subprocess.CompletedProcess[str] | None = None
    while attempt <= max(retries, 0):
        attempt += 1
        LOGGER.info("Running BoltzGen (attempt %s): %s", attempt, " ".join(exec_cmd))
        completed = subprocess.run(
            exec_cmd,
            cwd=str(task_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )
        stdout_path.write_text(completed.stdout)
        stderr_path.write_text(completed.stderr)
        if completed.returncode == 0:
            break
        LOGGER.warning("BoltzGen attempt %s failed with code %s", attempt, completed.returncode)

    result: Dict[str, object] = {
        "status": "succeeded" if completed and completed.returncode == 0 else "failed",
        "returncode": completed.returncode if completed else None,
        "command": list(exec_cmd),
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "output_dir": str(output_dir),
    }

    if completed and completed.returncode == 0:
        result.update(_collect_boltzgen_outputs(output_dir))
    else:
        result["reason"] = "BoltzGen execution failed"

    return result


def generate_boltzgen_yaml(
    standardized_scaffold,
    scaffold_mapping: MappingResultV2,
    cdr_label_ranges: Mapping[str, object] | None,
    target_standardized_path: Path | None,
    output_yaml_path: Path,
    protocol: str = "nanobody-anything",
) -> Path:
    """Generate scaffold-level YAML(s) plus a top-level design-spec for BoltzGen."""

    output_yaml_path = Path(output_yaml_path)
    output_yaml_path.parent.mkdir(parents=True, exist_ok=True)

    scaffold_entries: Sequence = (
        standardized_scaffold
        if isinstance(standardized_scaffold, Sequence) and not isinstance(standardized_scaffold, (str, bytes, bytearray))
        else [standardized_scaffold]
    )

    scaffold_yaml_paths: List[Path] = []
    for scaffold in scaffold_entries:
        scaffold_yaml_paths.append(
            generate_scaffold_yaml(scaffold, scaffold_mapping, cdr_label_ranges, output_yaml_path.parent)
        )

    binding_types = _binding_types_from_cdrs(scaffold_mapping, cdr_label_ranges)
    top_level_yaml = generate_top_level_yaml(
        scaffold_yaml_paths,
        target_standardized_path,
        binding_types,
        output_yaml_path,
        protocol=protocol,
    )

    return top_level_yaml


def generate_scaffold_yaml(
    standardized_scaffold,
    scaffold_mapping: MappingResultV2,
    cdr_label_ranges: Mapping[str, object] | None,
    out_dir: Path,
) -> Path:
    """Produce scaffold-level YAML aligned with BoltzGen examples."""

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    scaffold_name = Path(getattr(standardized_scaffold, "input_path", standardized_scaffold.standardized_path)).stem
    scaffold_yaml = out_dir / f"{scaffold_name}_scaffold.yaml"

    chain_id_value = cdr_label_ranges.get("chain_id") if cdr_label_ranges else None
    chain_id = str(chain_id_value) if chain_id_value is not None else None
    label_chain = scaffold_mapping.standardized.chain_id_map.get(chain_id, chain_id) if chain_id else None

    scaffold_payload: Dict[str, object] = {
        "path": str(standardized_scaffold.standardized_path),
        "include": [{"chain": {"id": label_chain}}] if label_chain else [],
        "design": _cdr_design_ranges(scaffold_mapping, cdr_label_ranges),
        "design_insertions": _cdr_insertions(cdr_label_ranges, scaffold_mapping),
        "structure_groups": [],
        "exclude": [],
        "reset_res_index": False,
    }

    scaffold_yaml.write_text(yaml.safe_dump(scaffold_payload, sort_keys=False))
    return scaffold_yaml


def generate_top_level_yaml(
    scaffold_yaml_paths: List[Path],
    target_standardized_path: Path | None,
    target_binding_types: List[Dict[str, object]],
    out_yaml: Path,
    *,
    protocol: str = "nanobody-anything",
) -> Path:
    entities: List[Dict[str, object]] = []

    if target_standardized_path:
        entities.append(
            {
                "file": {
                    "path": str(target_standardized_path),
                    "binding_types": {"epitope": target_binding_types or []},
                }
            }
        )

    for scaffold_yaml in scaffold_yaml_paths:
        entities.append({"file": {"path": str(scaffold_yaml)}})

    payload: Dict[str, object] = {"protocol": protocol, "entities": entities}
    out_yaml = Path(out_yaml)
    out_yaml.write_text(yaml.safe_dump(payload, sort_keys=False))
    return out_yaml


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


def _validate_yaml_indices(yaml_path: Path, mapping: MappingResultV2 | str | Path | dict | None) -> None:
    if mapping is None:
        return

    payload = yaml.safe_load(yaml_path.read_text()) or {}
    by_chain = _resolve_mapping_by_chain(mapping)
    if by_chain is None:
        return

    scaffolds = payload.get("scaffolds") or []
    if scaffolds:
        _validate_scaffold_entries(scaffolds, by_chain)

    entity_scaffolds = _scaffolds_from_entities(payload, yaml_path)
    if entity_scaffolds:
        _validate_scaffold_entries(entity_scaffolds, by_chain)


def _scaffolds_from_entities(payload: Mapping[str, object], yaml_path: Path) -> List[Mapping[str, object]]:
    scaffolds: List[Mapping[str, object]] = []
    entities = payload.get("entities")
    if not isinstance(entities, list):
        return scaffolds

    for entry in entities:
        file_info = entry.get("file") if isinstance(entry, Mapping) else None
        if not isinstance(file_info, Mapping):
            continue
        path_value = file_info.get("path")
        if not path_value:
            continue
        path = Path(path_value)
        if not path.is_absolute():
            path = yaml_path.parent / path
        if not path.exists() or path.suffix.lower() != ".yaml":
            continue
        scaffold_payload = yaml.safe_load(path.read_text()) or {}
        scaffolds.append(scaffold_payload)
    return scaffolds


def _validate_scaffold_entries(scaffolds: List[Mapping[str, object]], by_chain: Mapping[str, List[object]]) -> None:
    for scaffold in scaffolds:
        design_entries = scaffold.get("design", []) if isinstance(scaffold, Mapping) else []
        for design in design_entries:
            chain = design.get("chain", {}).get("id")
            res_index = design.get("chain", {}).get("res_index")
            if not chain or not res_index:
                continue
            _validate_range(res_index, chain, by_chain)
        insertions = scaffold.get("design_insertions", []) if isinstance(scaffold, Mapping) else []
        for insertion in insertions:
            chain = insertion.get("chain", {}).get("id")
            res_index = insertion.get("chain", {}).get("res_index")
            if not chain or not res_index:
                continue
            _validate_range(res_index, chain, by_chain)


def _resolve_mapping_by_chain(mapping: MappingResultV2 | str | Path | dict) -> Optional[Mapping[str, List[object]]]:
    if mapping is None:
        return None
    if isinstance(mapping, MappingResultV2):
        by_chain = dict(mapping.by_chain())
        for auth_chain, residues in mapping.by_chain().items():
            label_chain = mapping.standardized.chain_id_map.get(auth_chain)
            if label_chain:
                by_chain.setdefault(label_chain, residues)
        return by_chain
    if isinstance(mapping, (str, Path)):
        mapping_dict = json.loads(Path(mapping).read_text())
    elif isinstance(mapping, dict):
        mapping_dict = mapping
    else:
        raise ValueError("Unsupported mapping type for BoltzGen validation")

    by_chain: Dict[str, List[object]] = {}
    for chain_entry in mapping_dict.get("chains", []):
        auth_chain = chain_entry.get("auth_chain_id") or chain_entry.get("auth_chain")
        label_chain = chain_entry.get("label_asym_id") or chain_entry.get("label_chain_id")
        residues = []
        for residue in chain_entry.get("residues", []):
            label_seq = residue.get("mmcif_label", {}).get("label_seq_id")
            if label_seq is None:
                continue
            residues.append(SimpleNamespace(label_seq_id=int(label_seq)))
        if auth_chain:
            by_chain[auth_chain] = residues
        if label_chain:
            by_chain.setdefault(label_chain, residues)
    return by_chain


def _validate_range(expr: str, chain: str, mapping_by_chain: Mapping[str, List[object]]) -> None:
    if ".." not in expr:
        return

    parts = expr.split("..")
    try:
        start, end = int(parts[0]), int(parts[1])
    except ValueError:
        return

    residues = mapping_by_chain.get(chain)
    if not residues:
        raise ValueError(f"Chain {chain} not found in mapping for BoltzGen YAML validation")

    label_ids = [res.label_seq_id for res in residues]
    min_id, max_id = min(label_ids), max(label_ids)
    if start < min_id or end > max_id:
        raise ValueError(
            f"BoltzGen YAML res_index {expr} for chain {chain} exceeds label_seq_id range {min_id}-{max_id}"
        )


def _collect_boltzgen_outputs(output_dir: Path) -> Dict[str, object]:
    artifacts: Dict[str, object] = {}
    if not output_dir.exists():
        return artifacts

    final_designs = sorted(output_dir.glob("final_ranked_designs/*.pdb"))
    inverse_folded = sorted(output_dir.glob("intermediate_designs_inverse_folded/*.pdb"))
    metrics = sorted(output_dir.glob("**/*.csv"))

    if final_designs:
        artifacts["final_ranked_designs"] = [str(path) for path in final_designs]
    if inverse_folded:
        artifacts["inverse_folded_designs"] = [str(path) for path in inverse_folded]
    if metrics:
        artifacts["metrics_csv"] = [str(path) for path in metrics]

    summary_path = output_dir / "boltzgen_outputs.json"
    summary_path.write_text(yaml.safe_dump(artifacts, sort_keys=False))
    artifacts["summary_yaml"] = str(summary_path)
    return artifacts
