import unittest

from pipeline.epitope.exporters import export_boltzgen_binding, export_rfantibody_hotspots
from pipeline.epitope.mapping import ResolvedHotspotV2
from pipeline.epitope.spec import ResidueRefAuth


class TestHotspotExporters(unittest.TestCase):
    def test_export_rfantibody_hotspots_with_chain_map(self) -> None:
        hotspots = [ResidueRefAuth(chain="A", resi=54), ResidueRefAuth(chain="B", resi=10, ins="A")]
        output = export_rfantibody_hotspots(hotspots, chain_map={"A": "T"})
        self.assertEqual(output, "ppi.hotspot_res=[T54,B10A]")

    def test_export_boltzgen_binding_from_resolved(self) -> None:
        resolved = [
            ResolvedHotspotV2(
                auth=ResidueRefAuth(chain="A", resi=54),
                present_seq_id={"chain": "A", "seq_id": 1},
                mmcif_label={"label_asym_id": "A", "label_seq_id": 54},
            ),
            ResolvedHotspotV2(
                auth=ResidueRefAuth(chain="A", resi=55),
                present_seq_id={"chain": "A", "seq_id": 3},
                mmcif_label={"label_asym_id": "A", "label_seq_id": 55},
            ),
            ResolvedHotspotV2(
                auth=ResidueRefAuth(chain="B", resi=10),
                present_seq_id={"chain": "B", "seq_id": 2},
                mmcif_label={"label_asym_id": "B", "label_seq_id": 10},
            ),
        ]
        output = export_boltzgen_binding(resolved)
        self.assertEqual(
            output,
            {"binding_types": [{"chain": {"id": "A", "binding": "1,3"}}, {"chain": {"id": "B", "binding": "2"}}]},
        )
