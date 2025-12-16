import unittest
from pathlib import Path

from pipeline.epitope.mapping import build_residue_mapping, resolve_hotspots
from pipeline.epitope.spec import ResidueRefAuth


class TestHotspotMapping(unittest.TestCase):
    def test_build_residue_mapping_canonicalizes_indices(self) -> None:
        mapping = build_residue_mapping(Path("tests/data/hotspot_sample.pdb"))
        residues = mapping.residues
        self.assertEqual(len(residues), 3)
        self.assertEqual(residues[0].auth.resi, 54)
        self.assertEqual(residues[0].canonical.seq_id, 1)
        self.assertEqual(residues[1].auth.resi, 55)
        self.assertEqual(residues[1].canonical.seq_id, 2)
        self.assertEqual(residues[2].auth.ins, "A")
        self.assertEqual(residues[2].canonical.seq_id, 3)

    def test_resolve_hotspots_success_and_failure_messages(self) -> None:
        mapping = build_residue_mapping(Path("tests/data/hotspot_sample.pdb"))
        hotspots = [ResidueRefAuth(chain="A", resi=54, ins=""), ResidueRefAuth(chain="A", resi=999, ins="")]
        result = resolve_hotspots(hotspots, mapping)

        self.assertEqual(len(result.resolved), 1)
        self.assertEqual(result.resolved[0].canonical.seq_id, 1)
        self.assertTrue(result.errors)
        self.assertIn("999", result.errors[0])
        self.assertIn("A:54", ",".join(res.auth.token() for res in mapping.residues))

    def test_resolve_hotspots_handles_missing_chain(self) -> None:
        mapping = build_residue_mapping(Path("tests/data/hotspot_sample.pdb"))
        hotspots = [ResidueRefAuth(chain="B", resi=10, ins="")]
        result = resolve_hotspots(hotspots, mapping)

        self.assertFalse(result.resolved)
        self.assertIn("Chain B", result.errors[0])
        self.assertIn("Available chains", result.errors[0])
