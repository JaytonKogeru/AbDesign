import json
import tempfile
import unittest
from pathlib import Path

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

        self.assertIsNotNone(result.artifacts.target_residue_mapping)
        self.assertTrue(result.artifacts.target_residue_mapping.exists())
        self.assertIsNotNone(result.artifacts.target_hotspots_resolved)
        self.assertTrue(result.artifacts.target_hotspots_resolved.exists())

        summary_payload = json.loads(result.artifacts.summary_json.read_text())
        self.assertTrue(summary_payload["target_hotspots_input"])
        self.assertTrue(summary_payload["target_hotspots_resolved"]["resolved"])
        self.assertTrue(summary_payload["artifacts"]["target_hotspots_resolved"])

    def _get_tmp_dir(self) -> Path:
        return Path(tempfile.mkdtemp(prefix="hotspots-"))
