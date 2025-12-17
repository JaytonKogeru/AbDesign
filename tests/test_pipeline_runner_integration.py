import json
from pathlib import Path

from pipeline import runner
from pipeline.epitope.mapping import MappingResidueV2, MappingResultV2
from pipeline.epitope.spec import ResidueRefAuth
from pipeline.epitope.standardize import StandardizedStructure


def _make_mapping(tmp_path: Path) -> MappingResultV2:
    standardized = StandardizedStructure(
        input_path=tmp_path / "input.pdb",
        input_format="pdb",
        standardized_path=tmp_path / "standardized.cif",
        chain_id_map={"A": "T"},
    )
    residues = [
        MappingResidueV2(
            auth=ResidueRefAuth("A", idx),
            present_seq_id=idx,
            label_asym_id="T",
            label_seq_id=idx,
            resname3="GLY",
            category="protein",
        )
        for idx in range(1, 6)
    ]
    return MappingResultV2(residues=residues, standardized=standardized, generated_at="now")


def test_runner_invokes_adapters_with_paths(tmp_path, monkeypatch):
    scaffold_file = tmp_path / "input.pdb"
    scaffold_file.write_text("HEADER\nEND\n")
    target_file = tmp_path / "target.pdb"
    target_file.write_text("HEADER\nEND\n")

    mapping = _make_mapping(tmp_path)
    mapping_json = tmp_path / "mapping.json"
    mapping.write_json(mapping_json)

    target_mapping_json = tmp_path / "target_mapping.json"
    target_mapping_json.write_text(json.dumps(mapping.to_dict()))

    cdr_payload = {
        "status": "succeeded",
        "cdr_mappings": [
            {
                "cdr_name": "H1",
                "status": "mapped",
                "label_seq_id_start": 1,
                "label_seq_id_end": 3,
            }
        ],
    }

    cdr_json = tmp_path / "cdr.json"
    cdr_json.write_text(json.dumps(cdr_payload))

    normalization = {
        "scaffold_cdr_payload": cdr_payload,
        "scaffold_cdr_mapping_payload": cdr_payload,
        "scaffold_cdr_annotations_json": str(tmp_path / "cdr_annotations.json"),
        "scaffold_cdr_mappings_json": str(cdr_json),
        "scaffold_standardized_path": str(tmp_path / "standardized.pdb"),
        "scaffold_mapping_json": str(mapping_json),
        "scaffold_hlt_path": str(tmp_path / "scaffold_hlt.pdb"),
        "scaffold_chain_map_json": None,
        "boltzgen_yaml_path": None,
        "target_standardized_path": str(tmp_path / "target_standardized.cif"),
        "target_mapping_json": str(target_mapping_json),
        "target_hotspots_resolved_json": None,
    }

    for path_key in (
        "scaffold_cdr_annotations_json",
        "scaffold_standardized_path",
        "scaffold_hlt_path",
        "target_standardized_path",
    ):
        Path(normalization[path_key]).write_text("{}")

    monkeypatch.setattr(runner, "normalize_and_derive", lambda *args, **kwargs: normalization)

    rfa_calls = []
    bg_generate_calls = []
    bg_run_calls = []

    def _fake_run_rfa(task_dir, hlt_path, target_path, **kwargs):  # noqa: WPS430
        rfa_calls.append({"task_dir": task_dir, "hlt_path": hlt_path, "target_path": target_path, "kwargs": kwargs})
        design_pdb = Path(task_dir) / "rf_design.pdb"
        design_pdb.parent.mkdir(parents=True, exist_ok=True)
        design_pdb.write_text("MODEL\nENDMDL\n")
        return {"status": "succeeded", "design_pdbs": [str(design_pdb)]}

    def _fake_generate_boltzgen(scaffold, mapping_result, cdr_ranges, target_path, output_yaml_path, **kwargs):  # noqa: WPS430
        bg_generate_calls.append(
            {
                "scaffold": scaffold,
                "mapping_result": mapping_result,
                "cdr_ranges": cdr_ranges,
                "target_path": target_path,
                "output_yaml_path": output_yaml_path,
                "kwargs": kwargs,
            }
        )
        output_yaml_path = Path(output_yaml_path)
        output_yaml_path.write_text("protocol: nanobody-anything\nentities: []\n")
        return output_yaml_path

    def _fake_run_boltzgen(task_dir, yaml_path, **kwargs):  # noqa: WPS430
        bg_run_calls.append({"task_dir": task_dir, "yaml_path": yaml_path, "kwargs": kwargs})
        output_dir = Path(task_dir) / "boltzgen_output"
        output_dir.mkdir(parents=True, exist_ok=True)
        design_pdb = output_dir / "final_ranked_designs" / "design.pdb"
        design_pdb.parent.mkdir(parents=True, exist_ok=True)
        design_pdb.write_text("MODEL\nENDMDL\n")
        return {"status": "succeeded", "final_ranked_designs": [str(design_pdb)]}

    monkeypatch.setattr(runner, "run_rfantibody", _fake_run_rfa)
    monkeypatch.setattr(runner, "generate_boltzgen_yaml", _fake_generate_boltzgen)
    monkeypatch.setattr(runner, "run_boltzgen", _fake_run_boltzgen)

    result = runner.run_pipeline(
        "separate",
        {
            "files": {"scaffold_file": str(scaffold_file), "target_file": str(target_file)},
            "output_dir": tmp_path / "out",
            "integration": {
                "rfantibody": {"enabled": True, "use_docker": False},
                "boltzgen": {"enabled": True, "use_docker": False},
            },
        },
    )

    assert result.integration_outputs["rfantibody"]["status"] == "succeeded"
    assert result.integration_outputs["boltzgen"]["status"] == "succeeded"

    assert rfa_calls[0]["hlt_path"] == normalization["scaffold_hlt_path"]
    assert rfa_calls[0]["target_path"] == normalization["target_standardized_path"]
    assert rfa_calls[0]["kwargs"]["normalization"]["scaffold_mapping_json"] == normalization["scaffold_mapping_json"]

    assert bg_generate_calls[0]["mapping_result"].standardized.standardized_path == mapping.standardized.standardized_path
    assert bg_run_calls[0]["kwargs"]["mapping"] == normalization["scaffold_mapping_json"]
