import json
from pathlib import Path

from pipeline import runner


def test_run_pipeline_uses_serialized_artifact_names(tmp_path, monkeypatch):
    output_dir = tmp_path / "out"
    scaffold_file = tmp_path / "input.pdb"
    scaffold_file.write_text("HEADER\nEND\n")

    cdr_payload = {"status": "succeeded", "cdr_mappings": []}
    normalization_payload = {
        "scaffold_cdr_payload": cdr_payload,
        "scaffold_cdr_mapping_payload": cdr_payload,
        "scaffold_cdr_annotations_json": str(tmp_path / "cdr_annotations.json"),
        "scaffold_cdr_mappings_json": str(tmp_path / "cdr_mapping.json"),
        "scaffold_standardized_path": str(tmp_path / "standardized.pdb"),
        "scaffold_mapping_json": str(tmp_path / "mapping.json"),
        "scaffold_hlt_path": None,
        "scaffold_chain_map_json": None,
        "boltzgen_yaml_path": None,
        "target_standardized_path": None,
        "target_mapping_json": None,
        "target_hotspots_resolved_json": None,
    }

    for key in ("scaffold_cdr_annotations_json", "scaffold_cdr_mappings_json", "scaffold_standardized_path", "scaffold_mapping_json"):
        Path(normalization_payload[key]).write_text("{}")

    monkeypatch.setattr(runner, "normalize_and_derive", lambda *args, **kwargs: normalization_payload)

    result = runner.run_pipeline(
        "separate",
        {
            "files": {"scaffold_file": str(scaffold_file)},
            "output_dir": output_dir,
        },
    )

    artifacts = result.artifacts
    assert artifacts.scaffold_standardized_path == Path(normalization_payload["scaffold_standardized_path"])
    assert artifacts.cdr_json == Path(normalization_payload["scaffold_cdr_annotations_json"])
    assert artifacts.target_residue_mapping_path is None
    assert json.loads(artifacts.summary_json.read_text())["artifacts"]["target_residue_mapping_path"] is None
