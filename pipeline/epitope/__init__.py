"""Epitope hotspot parsing, mapping, and exporters."""

from pipeline.epitope.spec import HotspotSpec, ResidueRefAuth, ResidueRefCanonical, normalize_target_hotspots, parse_hotspot_token
from pipeline.epitope.mapping import MappingResult, build_residue_mapping, resolve_hotspots
from pipeline.epitope.exporters import export_boltzgen_binding, export_rfantibody_hotspots

__all__ = [
    "HotspotSpec",
    "ResidueRefAuth",
    "ResidueRefCanonical",
    "MappingResult",
    "build_residue_mapping",
    "resolve_hotspots",
    "normalize_target_hotspots",
    "parse_hotspot_token",
    "export_boltzgen_binding",
    "export_rfantibody_hotspots",
]
