import tempfile
from pathlib import Path

import pytest

pytest.importorskip("gemmi")

from pipeline.epitope.mapping import build_residue_mapping_v2, resolve_hotspots_v2
from pipeline.epitope.spec import ResidueRefAuth
from pipeline.epitope.standardize import standardize_structure


def test_mapping_v2_present_seq_id_and_label_seq_id() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        structure_path = Path("tests/data/hotspot_sample.pdb")
        standardized = standardize_structure(structure_path, Path(tmpdir))
        mapping = build_residue_mapping_v2(standardized)

        payload = mapping.to_dict()
        assert payload["mapping_schema_version"] == 2
        residues = [res for chain in payload["chains"] for res in chain["residues"]]
        present_seq_ids = [res["present_seq_id"] for res in residues]
        assert present_seq_ids == list(range(1, len(present_seq_ids) + 1))
        for res in residues:
            assert isinstance(res["mmcif_label"]["label_seq_id"], int)


def test_resolve_v2_insertion_code() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        structure_path = Path("tests/data/hotspot_sample.pdb")
        standardized = standardize_structure(structure_path, Path(tmpdir))
        mapping = build_residue_mapping_v2(standardized)
        hotspots = [ResidueRefAuth(chain="A", resi=55, ins="A")]

        result = resolve_hotspots_v2(hotspots, mapping)
        assert not result.unmatched
        assert result.resolved[0].present_seq_id["seq_id"] == 3


def test_scope_filtering() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        structure_path = Path("tests/data/het_scope_sample.pdb")
        standardized = standardize_structure(structure_path, Path(tmpdir))
        mapping = build_residue_mapping_v2(standardized)
        ligand_hotspot = [ResidueRefAuth(chain="A", resi=2, ins="")]

        protein_only = resolve_hotspots_v2(ligand_hotspot, mapping, scope="protein")
        assert protein_only.unmatched
        assert protein_only.unmatched[0]["reason"] == "filtered_by_scope"

        all_scope = resolve_hotspots_v2(ligand_hotspot, mapping, scope="all")
        assert not all_scope.unmatched
        assert all_scope.resolved[0].present_seq_id["seq_id"] == 2
