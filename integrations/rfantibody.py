"""Adapters for integrating RFantibody workflows."""

from __future__ import annotations

import json
import logging
import shlex
import subprocess
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Union

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
    use_docker: Optional[bool] = None,
    docker_image: str = "rfantibody",
    timeout: int = 3600,
) -> Dict[str, object]:
    """Execute RFantibody RFdiffusion inference and collect outputs."""

    task_root = Path(task_dir).resolve()
    logs_dir = task_root / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    output_dir = task_root / "rfantibody_output"
    output_dir.mkdir(parents=True, exist_ok=True)

    hotspot_token = _format_hotspots(hotspots_resolved)
    design_loops_token = _format_design_loops(design_loops)

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
        container_cmd = [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{task_root}:/home",
            "-w",
            "/home",
            "--gpus",
            "all",
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

    result: Dict[str, object] = {
        "status": "succeeded" if completed.returncode == 0 else "failed",
        "returncode": completed.returncode,
        "command": exec_cmd,
        "stdout_log": str(stdout_path),
        "stderr_log": str(stderr_path),
        "output_dir": str(output_dir),
    }

    if completed.returncode != 0:
        result["reason"] = "RFantibody execution failed"
        LOGGER.error(
            "RFantibody inference failed with code %s. See %s", completed.returncode, stderr_path
        )
    else:
        result.update(_collect_outputs(output_dir))

    return result


def _format_hotspots(hotspots: Optional[Iterable[Dict[str, object]]]) -> str:
    tokens: List[str] = []
    for hotspot in hotspots or []:
        if isinstance(hotspot, str):
            tokens.append(hotspot)
            continue

        chain = hotspot.get("chain") or hotspot.get("chain_id") or hotspot.get("label_asym_id")
        chain = chain or hotspot.get("auth_asym_id") or "T"

        residue_id = (
            hotspot.get("label_seq_id")
            or hotspot.get("present_seq_id")
            or hotspot.get("auth_seq_id")
            or hotspot.get("seq_id")
        )

        if chain and residue_id is not None:
            tokens.append(f"{chain}{residue_id}")
    return ",".join(tokens)


def _format_design_loops(design_loops: Optional[Sequence[Union[str, Dict[str, object]]]]) -> str:
    if not design_loops:
        return ""

    tokens: List[str] = []
    for loop in design_loops:
        if isinstance(loop, str):
            tokens.append(loop)
            continue

        name = str(loop.get("cdr_name") or loop.get("name") or "loop")
        start = loop.get("label_seq_id_start") or loop.get("start")
        end = loop.get("label_seq_id_end") or loop.get("end")
        if start is None or end is None:
            continue
        tokens.append(f"{name}:{start}-{end}")

    return ",".join(tokens)


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
