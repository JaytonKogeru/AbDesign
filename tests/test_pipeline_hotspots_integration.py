import json
import json
import json
import tempfile
import unittest
from pathlib import Path

import pytest

pytest.importorskip("gemmi")

from pipeline.runner import run_pipeline


class TestPipelineHotspotsIntegration(unittest.TestCase):
    def test_pipeline_produces_hotspot_artifacts(self) -> None:
        output_dir = Path(self._get_tmp_dir()) / "outputs"
        structure_path = Path("tests/data/hotspot_sample.pdb").resolve()
        inputs = {
            "mode": "separate",
            "output_dir": output_dir,
            "files": {"target_file": str(structure_path)},
            "user_params": {"target_hotspots": ["A:54", "A:55A"]},
        }

        result = run_pipeline("separate", inputs)

        mapping_path = result.artifacts.target_residue_mapping_path
        resolved_path = result.artifacts.target_hotspots_resolved_path

        self.assertIsNotNone(mapping_path)
        self.assertTrue(mapping_path.exists())
        self.assertIsNotNone(resolved_path)
        self.assertTrue(resolved_path.exists())

        mapping_payload = json.loads(mapping_path.read_text())
        self.assertEqual(mapping_payload.get("mapping_schema_version"), 2)
        residues = [res for chain in mapping_payload.get("chains", []) for res in chain.get("residues", [])]
        self.assertTrue(residues)
        self.assertIn("present_seq_id", residues[0])
        self.assertIn("mmcif_label", residues[0])

        resolved_payload = json.loads(resolved_path.read_text())
        self.assertEqual(resolved_payload.get("schema_version"), 2)
        self.assertTrue(resolved_payload.get("resolved"))
        first_resolved = resolved_payload["resolved"][0]
        self.assertIn("present_seq_id", first_resolved)
        self.assertIn("mmcif_label", first_resolved)

        summary_payload = json.loads(result.artifacts.summary_json.read_text())
        self.assertTrue(summary_payload["target_hotspots_input"])
        self.assertTrue(summary_payload["target_hotspots_resolved"]["resolved"])
        self.assertIn("target_hotspots_resolved_path", summary_payload["artifacts"])
        self.assertNotIn("target_hotspots_resolved_v2", summary_payload["artifacts"])

    def _get_tmp_dir(self) -> Path:
        return Path(tempfile.mkdtemp(prefix="hotspots-"))
