from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from integrations.rfantibody import run_rfantibody


class DummyCompletedProcess(subprocess.CompletedProcess[str]):
    def __init__(self, args: list[str]):  # noqa: D401 - thin wrapper
        super().__init__(args=args, returncode=0, stdout="", stderr="")


@pytest.fixture
def fake_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    hlt = task_dir / "hlt.pdb"
    target = task_dir / "target.pdb"
    hlt.write_text("MODEL 1\nENDMDL\n")
    target.write_text("MODEL 1\nENDMDL\n")
    return task_dir, hlt, target


def test_run_rfantibody_prefers_user_params(monkeypatch: pytest.MonkeyPatch, fake_inputs: tuple[Path, Path, Path]):
    task_dir, hlt, target = fake_inputs

    captured_cmd: dict[str, list[str]] = {}

    def _fake_run(cmd, **_kwargs):  # noqa: WPS430
        captured_cmd["cmd"] = cmd
        return DummyCompletedProcess(cmd)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    normalization = {
        "target_hotspots_resolved_json": str(task_dir / "hotspots.json"),
        "scaffold_cdr_mappings_json": str(task_dir / "cdr.json"),
    }

    (task_dir / "hotspots.json").write_text(
        "{" "\"status\":\"succeeded\",\"hotspots\":[{\"chain\":\"T\",\"label_seq_id\":15}]}"
    )
    (task_dir / "cdr.json").write_text("{\"cdr_mappings\":[{\"cdr_name\":\"H3\",\"status\":\"mapped\",\"label_seq_id_start\":10,\"label_seq_id_end\":20}]}")

    user_params = {"hotspots": ["A:305"], "design_loops": ["H2:5-9"]}

    result = run_rfantibody(
        task_dir,
        hlt,
        target,
        hotspots_resolved=[{"chain": "B", "label_seq_id": 5}],
        normalization=normalization,
        user_params=user_params,
    )

    assert result["status"] == "succeeded"
    assert "--ppi.hotspot_res" in captured_cmd["cmd"]
    assert "A305" in captured_cmd["cmd"]
    assert "--antibody.design_loops" in captured_cmd["cmd"]
    assert "H2:5-9" in captured_cmd["cmd"]


def test_run_rfantibody_uses_normalization(monkeypatch: pytest.MonkeyPatch, fake_inputs: tuple[Path, Path, Path]):
    task_dir, hlt, target = fake_inputs

    captured_cmd: dict[str, list[str]] = {}

    def _fake_run(cmd, **_kwargs):  # noqa: WPS430
        captured_cmd["cmd"] = cmd
        return DummyCompletedProcess(cmd)

    monkeypatch.setattr(subprocess, "run", _fake_run)

    hotspots_json = task_dir / "hotspots.json"
    hotspots_json.write_text(
        "{" "\"status\":\"succeeded\",\"hotspots\":[{\"chain\":\"T\",\"label_seq_id\":305},{\"chain\":\"T\",\"present_seq_id\":456}]}"
    )

    cdr_json = task_dir / "cdr.json"
    cdr_json.write_text(
        "{" "\"cdr_mappings\":[{\"cdr_name\":\"H3\",\"status\":\"mapped\",\"label_seq_id_start\":1,\"label_seq_id_end\":9}]}"
    )

    normalization = {
        "target_hotspots_resolved_json": str(hotspots_json),
        "scaffold_cdr_mappings_json": str(cdr_json),
    }

    result = run_rfantibody(
        task_dir,
        hlt,
        target,
        normalization=normalization,
    )

    assert result["status"] == "succeeded"
    cmd = captured_cmd["cmd"]
    assert "T305,T456" in cmd
    assert "H3:1-9" in cmd
