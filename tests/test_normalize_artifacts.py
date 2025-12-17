import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from integrations import normalize


class DummyStandardized:
    def __init__(self, path: Path, chain_map=None):
        self.standardized_path = path
        self.chain_id_map = chain_map or {"A": "A"}


class DummyResidue:
    def __init__(self, label_seq_id: int, present_seq_id: int, resname3: str = "ALA"):
        self.label_seq_id = label_seq_id
        self.present_seq_id = present_seq_id
        self.resname3 = resname3
        self.label_asym_id = "A"
        self.auth = SimpleNamespace(chain="A")


class DummyMapping:
    def __init__(self, path: Path):
        self.standardized = SimpleNamespace(chain_id_map={"A": "A"})
        self._path = path
        self.residues = [DummyResidue(i + 1, i + 1) for i in range(8)]

    def by_chain(self):
        return {"A": self.residues}

    def write_json(self, path: Path):
        payload = {
            "chains": [
                {
                    "auth_chain_id": "A",
                    "residues": [
                        {"mmcif_label": {"label_seq_id": res.label_seq_id}} for res in self.residues
                    ],
                }
            ]
        }
        path.write_text(json.dumps(payload))


@pytest.fixture(autouse=True)
def patch_dependencies(monkeypatch, tmp_path):
    standardized_path = tmp_path / "standardized.pdb"
    standardized_path.write_text("MODEL\nENDMDL\n")

    def fake_standardize(path, out_dir):
        return DummyStandardized(standardized_path)

    def fake_build_mapping(standardized):
        return DummyMapping(tmp_path / "mapping.json")

    def fake_annotate(scaffold_path, out_dir, scheme=None, chain_id=None):
        out_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "status": "succeeded",
            "chain_id": "A",
            "cdrs": [
                {"name": "H1", "sequence": "AAA"},
            ],
        }
        (out_dir / "cdr_annotations.json").write_text(json.dumps(payload))
        return payload

    def fake_generate_boltzgen_yaml(standardized, mapping, cdr_payload, target_path, out_yaml_path):
        out_yaml_path.write_text("protocol: test")
        return out_yaml_path

    def fake_generate_hlt(*args, **kwargs):
        hlt_path = args[3]
        Path(hlt_path).write_text("HEADER\nEND\n")
        return hlt_path

    monkeypatch.setattr(normalize, "standardize_structure", fake_standardize)
    monkeypatch.setattr(normalize, "build_residue_mapping_v2", fake_build_mapping)
    monkeypatch.setattr(normalize, "annotate_cdrs", fake_annotate)
    monkeypatch.setattr(normalize, "generate_boltzgen_yaml", fake_generate_boltzgen_yaml)
    monkeypatch.setattr(normalize, "generate_hlt", fake_generate_hlt)
    yield


def test_normalize_and_derive_artifacts_are_jsonable(tmp_path):
    scaffold = tmp_path / "input.pdb"
    scaffold.write_text("HEADER\nEND\n")

    artifacts = normalize.normalize_and_derive(str(scaffold), None, str(tmp_path / "out"))

    assert isinstance(artifacts["scaffold_mapping_json"], str)
    assert Path(artifacts["scaffold_mapping_json"]).exists()
    assert isinstance(artifacts["scaffold_cdr_annotations"], str)
    assert Path(artifacts["scaffold_cdr_annotations"]).exists()

    for value in artifacts.values():
        assert isinstance(value, (str, type(None), dict, list, int, float, bool))
