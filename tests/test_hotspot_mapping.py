import tempfile
import unittest
from pathlib import Path

import pytest

pytest.importorskip("gemmi")

from pipeline.epitope.mapping import build_residue_mapping_v2, resolve_hotspots_v2
from pipeline.epitope.spec import ResidueRefAuth
from pipeline.epitope.standardize import standardize_structure


class TestHotspotMapping(unittest.TestCase):
    def test_build_residue_mapping_v2_canonicalizes_indices(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            standardized = standardize_structure(Path("tests/data/hotspot_sample.pdb"), Path(tmpdir))
            mapping = build_residue_mapping_v2(standardized)

        residues = mapping.residues
        self.assertEqual(len(residues), 3)
        self.assertEqual([res.auth.resi for res in residues], [54, 55, 55])
        self.assertEqual([res.present_seq_id for res in residues], [1, 2, 3])
        self.assertEqual(residues[2].auth.ins, "A")
        self.assertTrue(all("label_seq_id" in res.to_dict()["mmcif_label"] for res in residues))

    def test_resolve_hotspots_v2_reports_unmatched_with_hints(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            standardized = standardize_structure(Path("tests/data/hotspot_sample.pdb"), Path(tmpdir))
            mapping = build_residue_mapping_v2(standardized)

        hotspots = [ResidueRefAuth(chain="A", resi=54, ins=""), ResidueRefAuth(chain="A", resi=999, ins="")]
        result = resolve_hotspots_v2(hotspots, mapping)

        self.assertEqual(len(result.resolved), 1)
        self.assertEqual(result.resolved[0].present_seq_id["seq_id"], 1)
        self.assertEqual(len(result.unmatched), 1)
        self.assertEqual(result.unmatched[0]["reason"], "not_found_in_structure")
        self.assertIn("hint", result.unmatched[0])

    def test_resolve_hotspots_v2_handles_missing_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            standardized = standardize_structure(Path("tests/data/hotspot_sample.pdb"), Path(tmpdir))
            mapping = build_residue_mapping_v2(standardized)

        hotspots = [ResidueRefAuth(chain="B", resi=10, ins="")]
        result = resolve_hotspots_v2(hotspots, mapping)

        self.assertFalse(result.resolved)
        self.assertEqual(result.unmatched[0]["reason"], "not_found_in_structure")
        self.assertIn("available chains", result.unmatched[0]["hint"].lower())
