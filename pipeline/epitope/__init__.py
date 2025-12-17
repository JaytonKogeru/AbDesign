"""Epitope hotspot parsing, mapping, and exporters."""

from pipeline.epitope.spec import HotspotSpec, ResidueRefAuth, ResidueRefCanonical, normalize_target_hotspots, parse_hotspot_token
from pipeline.epitope.mapping import MappingResultV2, build_residue_mapping_v2, resolve_hotspots_v2
from pipeline.epitope.exporters import export_boltzgen_binding, export_rfantibody_hotspots

__all__ = [
    "HotspotSpec",
    "ResidueRefAuth",
    "ResidueRefCanonical",
    "MappingResultV2",
    "build_residue_mapping_v2",
    "resolve_hotspots_v2",
    "normalize_target_hotspots",
    "parse_hotspot_token",
    "export_boltzgen_binding",
    "export_rfantibody_hotspots",
]
