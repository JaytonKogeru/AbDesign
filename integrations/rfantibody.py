"""Adapters for integrating RFantibody workflows."""

from __future__ import annotations

import json
import logging
import shlex
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Union

LOGGER = logging.getLogger(__name__)


def ensure_rfantibody_available() -> bool:
    """Lightweight probe to check RFantibody integration availability."""
    try:
        import importlib  # noqa: WPS433

        importlib.import_module("rfantibody")
    except ModuleNotFoundError:
        return False
    return True


def run_rfantibody(
    task_dir: Union[str, Path],
    hlt_path: Union[str, Path],
    target_path: Union[str, Path],
    hotspots_resolved: Optional[Iterable[Dict[str, object]]] = None,
    design_loops: Optional[Sequence[Union[str, Dict[str, object]]]] = None,
    num_designs: int = 20,
    *,
    user_params: Optional[Dict[str, Any]] = None,
    normalization: Optional[Dict[str, Any]] = None,
    use_docker: Optional[bool] = None,
    docker_image: str = "rfantibody",
    timeout: int = 3600,
    retries: int = 1,
    cache_dir: Path | None = None,
) -> Dict[str, object]:
    """Execute RFantibody RFdiffusion inference and collect outputs."""

    task_root = Path(task_dir).resolve()
    logs_dir = task_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    output_dir = task_root / "rfantibody_output"
    output_dir.mkdir(parents=True, exist_ok=True)

    normalization = normalization or {}
    user_params = user_params or {}

    hotspot_source: Any = user_params.get("hotspots")
    design_loop_source: Any = user_params.get("design_loops")

    hotspot_source = hotspot_source or _load_json(
        normalization.get("target_hotspots_resolved_json")
        or normalization.get("target_hotspots_resolved")
    )
    hotspot_source = hotspot_source or hotspots_resolved

    cdr_mapping_json = _load_json(
        normalization.get("scaffold_cdr_mappings_json")
        or normalization.get("cdr_label_mappings")
    )

    if design_loop_source is None:
        design_loop_source = design_loops

    hotspot_token = _format_hotspots_for_rf(hotspot_source, cdr_mapping_json)
    design_loops_token = _format_design_loops_for_rf(design_loop_source, cdr_mapping_json)

    base_cmd = [
        "python",
        "scripts/rfdiffusion_inference.py",
        "--antibody.framework_pdb",
        str(hlt_path),
        "--target_pdb",
        str(target_path),
        "--num_designs",
        str(num_designs),
        "--outdir",
        str(output_dir),
    ]

    if hotspot_token:
        base_cmd.extend(["--ppi.hotspot_res", hotspot_token])
    if design_loops_token:
        base_cmd.extend(["--antibody.design_loops", design_loops_token])

    if use_docker:
        cache_dir = cache_dir or Path.home() / ".cache" / "huggingface"
        cache_dir.mkdir(parents=True, exist_ok=True)
        container_cmd = [
            "docker",
            "run",
            "--rm",
            "--gpus",
            "all",
            "-v",
            f"{task_root}:/home",
            "-v",
            f"{cache_dir}:{cache_dir}",
            "-w",
            "/home",
            docker_image,
            "bash",
            "-lc",
            _quote_for_shell(["poetry", "run", *base_cmd]),
        ]
        exec_cmd = container_cmd
    else:
        exec_cmd = base_cmd

    LOGGER.info("Running RFantibody command: %s", " ".join(map(shlex.quote, exec_cmd)))

    stdout_path = logs_dir / "rfantibody.stdout.log"
    stderr_path = logs_dir / "rfantibody.stderr.log"

    attempt = 0
    completed: subprocess.CompletedProcess[str] | None = None
    while attempt <= max(retries, 0):
        attempt += 1
        LOGGER.info("Running RFantibody (attempt %s): %s", attempt, " ".join(map(shlex.quote, exec_cmd)))
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
        LOGGER.warning("RFantibody attempt %s failed with code %s", attempt, completed.returncode)

    result: Dict[str, object] = {
        "status": "succeeded" if completed and completed.returncode == 0 else "failed",
        "returncode": completed.returncode if completed else None,
        "command": exec_cmd,
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "output_dir": str(output_dir),
    }

    if completed and completed.returncode == 0:
        result.update(_collect_outputs(output_dir))
    else:
        result["reason"] = "RFantibody execution failed"
        LOGGER.error(
            "RFantibody inference failed with code %s. See %s",
            completed.returncode if completed else "?",
            stderr_path,
        )

    return result


def _load_json(path_or_obj: Any) -> Any:
    if path_or_obj is None:
        return None
    if isinstance(path_or_obj, (str, Path)):
        try:
            return json.loads(Path(path_or_obj).read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            LOGGER.warning("Failed to load JSON from %s", path_or_obj)
            return None
    return path_or_obj


def _format_hotspots_for_rf(hotspots_input: Any, mapping: Any = None) -> str:
    tokens: List[str] = []
    if not hotspots_input:
        return ""

    if isinstance(hotspots_input, dict) and hotspots_input.get("status") == "succeeded":
        for hotspot in hotspots_input.get("hotspots", []):
            chain = hotspot.get("chain") or hotspot.get("label_asym_id")
            residue_id = hotspot.get("label_seq_id") or hotspot.get("present_seq_id") or hotspot.get("auth_resi")
            if chain and residue_id is not None:
                tokens.append(f"{chain}{residue_id}")
        return ",".join(tokens)

    if isinstance(hotspots_input, (list, tuple)):
        for hotspot in hotspots_input:
            if isinstance(hotspot, str):
                tokens.append(hotspot.replace(":", ""))
                continue

            chain = hotspot.get("chain") or hotspot.get("auth_chain") or hotspot.get("chain_id") or "T"
            residue_id = (
                hotspot.get("resi")
                or hotspot.get("label_seq_id")
                or hotspot.get("present_seq_id")
                or hotspot.get("auth_seq_id")
                or hotspot.get("seq_id")
            )
            if chain and residue_id is not None:
                tokens.append(f"{chain}{residue_id}")
    return ",".join(tokens)


def _format_design_loops_for_rf(design_loops_input: Any, cdr_mapping_json: Any = None) -> str:
    if design_loops_input:
        if isinstance(design_loops_input, str):
            return design_loops_input
        if isinstance(design_loops_input, (list, tuple)):
            normalized: List[str] = []
            for loop in design_loops_input:
                if isinstance(loop, str):
                    normalized.append(loop)
                    continue
                name = str(loop.get("cdr_name") or loop.get("name") or "loop")
                start = loop.get("label_seq_id_start") or loop.get("start")
                end = loop.get("label_seq_id_end") or loop.get("end")
                if start is not None and end is not None:
                    normalized.append(f"{name}:{start}-{end}")
            return ",".join(normalized)

    if cdr_mapping_json:
        tokens: List[str] = []
        for cdr in cdr_mapping_json.get("cdr_mappings", []):
            if cdr.get("status") == "mapped":
                name = cdr.get("cdr_name")
                start = cdr.get("label_seq_id_start")
                end = cdr.get("label_seq_id_end")
                if name and start is not None and end is not None:
                    tokens.append(f"{name}:{start}-{end}")
        return ",".join(tokens)

    return ""


def _quote_for_shell(parts: Sequence[str]) -> str:
    return " ".join(shlex.quote(part) for part in parts)


def _collect_outputs(output_dir: Path) -> Dict[str, object]:
    artifacts: Dict[str, object] = {}
    if not output_dir.exists():
        return artifacts

    designs = sorted(output_dir.glob("*.pdb"))
    metrics = sorted(output_dir.glob("*.csv"))
    if designs:
        artifacts["design_pdbs"] = [str(path) for path in designs]
    if metrics:
        artifacts["metrics_csv"] = [str(path) for path in metrics]

    summary_path = output_dir / "rfantibody_outputs.json"
    summary_path.write_text(json.dumps(artifacts, indent=2))
    artifacts["summary_json"] = str(summary_path)
    return artifacts
