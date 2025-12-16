import unittest

from pipeline.epitope.exporters import export_boltzgen_binding, export_rfantibody_hotspots
from pipeline.epitope.mapping import ResolvedHotspot
from pipeline.epitope.spec import ResidueRefAuth, ResidueRefCanonical


class TestHotspotExporters(unittest.TestCase):
    def test_export_rfantibody_hotspots_with_chain_map(self) -> None:
        hotspots = [ResidueRefAuth(chain="A", resi=54), ResidueRefAuth(chain="B", resi=10, ins="A")]
        output = export_rfantibody_hotspots(hotspots, chain_map={"A": "T"})
        self.assertEqual(output, "ppi.hotspot_res=[T54,B10A]")

    def test_export_boltzgen_binding_from_resolved(self) -> None:
        resolved = [
            ResolvedHotspot(auth=ResidueRefAuth(chain="A", resi=54), canonical=ResidueRefCanonical(chain="A", seq_id=1)),
            ResolvedHotspot(auth=ResidueRefAuth(chain="A", resi=55), canonical=ResidueRefCanonical(chain="A", seq_id=3)),
            ResolvedHotspot(auth=ResidueRefAuth(chain="B", resi=10), canonical=ResidueRefCanonical(chain="B", seq_id=2)),
        ]
        output = export_boltzgen_binding(resolved)
        self.assertEqual(
            output,
            {"binding_types": [{"chain": {"id": "A", "binding": "1,3"}}, {"chain": {"id": "B", "binding": "2"}}]},
        )
