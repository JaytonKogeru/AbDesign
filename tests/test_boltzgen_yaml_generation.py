from pathlib import Path

from integrations import boltzgen
from integrations.boltzgen import (
    generate_boltzgen_yaml,
    generate_scaffold_yaml,
    generate_top_level_yaml,
    _validate_yaml_indices,
)
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
            resname3="ALA",
            category="protein",
        )
        for idx in range(1, 11)
    ]
    return MappingResultV2(residues=residues, standardized=standardized, generated_at="now")


def _cdr_payload():
    return {
        "status": "succeeded",
        "chain_id": "A",
        "cdr_mappings": [
            {
                "status": "mapped",
                "cdr_name": "H1",
                "label_seq_id_start": 1,
                "label_seq_id_end": 3,
            }
        ],
    }


def test_generate_scaffold_yaml(tmp_path: Path) -> None:
    mapping = _make_mapping(tmp_path)
    cdr_payload = _cdr_payload()

    scaffold_yaml = generate_scaffold_yaml(mapping.standardized, mapping, cdr_payload, tmp_path)
    payload = boltzgen.yaml.safe_load(scaffold_yaml.read_text())

    assert payload["path"] == str(mapping.standardized.standardized_path)
    assert payload["include"] == [{"chain": {"id": "T"}}]
    assert payload["design"] == [{"chain": {"id": "T", "res_index": "1..3"}}]
    assert payload["design_insertions"] == []
    assert payload.get("structure_groups") == []
    assert payload.get("exclude") == []


def test_generate_top_level_yaml_and_validation(tmp_path: Path) -> None:
    mapping = _make_mapping(tmp_path)
    cdr_payload = _cdr_payload()

    scaffold_yaml = generate_scaffold_yaml(mapping.standardized, mapping, cdr_payload, tmp_path)
    target_path = tmp_path / "target.cif"
    target_path.write_text("test")

    top_yaml = generate_top_level_yaml(
        [scaffold_yaml],
        target_path,
        [{"chain": {"id": "T", "binding": "1,2,3"}}],
        tmp_path / "design_spec.yaml",
    )

    top_payload = boltzgen.yaml.safe_load(top_yaml.read_text())
    assert top_payload["protocol"] == "nanobody-anything"
    assert len(top_payload["entities"]) == 2

    target_entity = top_payload["entities"][0]["file"]
    assert target_entity["path"] == str(target_path)
    assert "binding_types" in target_entity

    scaffold_entity = top_payload["entities"][1]["file"]
    assert scaffold_entity["path"] == str(scaffold_yaml)

    # validate scaffold indices through top-level YAML
    _validate_yaml_indices(top_yaml, mapping)


def test_generate_boltzgen_yaml_entrypoint(tmp_path: Path) -> None:
    mapping = _make_mapping(tmp_path)
    cdr_payload = _cdr_payload()

    target_path = tmp_path / "target.cif"
    target_path.write_text("test")

    output_yaml = generate_boltzgen_yaml(
        mapping.standardized,
        mapping,
        cdr_payload,
        target_path,
        tmp_path / "boltzgen_design.yaml",
    )

    payload = boltzgen.yaml.safe_load(Path(output_yaml).read_text())
    assert payload["protocol"] == "nanobody-anything"
    assert len(payload["entities"]) == 2

    scaffold_file = payload["entities"][1]["file"]
    scaffold_payload = boltzgen.yaml.safe_load(Path(scaffold_file["path"]).read_text())
    assert scaffold_payload["design"] == [{"chain": {"id": "T", "res_index": "1..3"}}]

    # ensure validation sees scaffold content
    _validate_yaml_indices(output_yaml, mapping)

