"""Export helpers for hotspot interoperability."""
from __future__ import annotations

from typing import Dict, Iterable, List, Mapping, Sequence

from pipeline.epitope.mapping import ResolvedHotspot
from pipeline.epitope.spec import ResidueRefAuth, ResidueRefCanonical


def export_rfantibody_hotspots(auth_hotspots: Sequence[ResidueRefAuth], chain_map: Mapping[str, str] | None = None) -> str:
    """Return RFantibody-formatted hotspot string."""

    def _map_chain(chain: str) -> str:
        if chain_map:
            return chain_map.get(chain, chain)
        return chain

    tokens: List[str] = []
    for hotspot in auth_hotspots:
        mapped_chain = _map_chain(hotspot.chain)
        suffix = hotspot.ins or ""
        tokens.append(f"{mapped_chain}{hotspot.resi}{suffix}")
    return f"ppi.hotspot_res=[{','.join(tokens)}]"


def export_boltzgen_binding(resolved_canonical_hotspots: Iterable[ResidueRefCanonical | ResolvedHotspot]) -> Dict[str, List[Dict[str, Dict[str, str]]]]:
    """Convert canonical hotspots into BoltzGen binding dictionary."""

    per_chain: Dict[str, List[int]] = {}
    for hotspot in resolved_canonical_hotspots:
        canonical_ref = hotspot.canonical if isinstance(hotspot, ResolvedHotspot) else hotspot
        per_chain.setdefault(canonical_ref.chain, []).append(int(canonical_ref.seq_id))

    binding_types = []
    for chain, seq_ids in per_chain.items():
        seq_ids_sorted = sorted(seq_ids)
        binding_types.append({"chain": {"id": chain, "binding": ",".join(map(str, seq_ids_sorted))}})

    return {"binding_types": binding_types}
