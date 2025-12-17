"""Export helpers for hotspot interoperability."""
from __future__ import annotations

from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

from pipeline.epitope.mapping import ResolvedHotspotV2
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


def _extract_canonical_id(hotspot: ResidueRefCanonical | ResolvedHotspotV2 | Mapping[str, object]) -> Tuple[str, int]:
    if isinstance(hotspot, ResolvedHotspotV2):
        chain = str(hotspot.present_seq_id.get("chain"))
        seq_id = int(hotspot.present_seq_id.get("seq_id"))
        return chain, seq_id

    if isinstance(hotspot, ResidueRefCanonical):
        return hotspot.chain, int(hotspot.seq_id)

    present = hotspot.get("present_seq_id", {}) if isinstance(hotspot, Mapping) else {}
    return str(present.get("chain")), int(present.get("seq_id"))


def export_boltzgen_binding(
    resolved_canonical_hotspots: Iterable[ResidueRefCanonical | ResolvedHotspotV2 | Mapping[str, object]]
) -> Dict[str, List[Dict[str, Dict[str, str]]]]:
    """Convert canonical hotspots into BoltzGen binding dictionary using present_seq_id numbering."""

    per_chain: Dict[str, List[int]] = {}
    for hotspot in resolved_canonical_hotspots:
        chain, seq_id = _extract_canonical_id(hotspot)
        per_chain.setdefault(chain, []).append(seq_id)

    binding_types = []
    for chain, seq_ids in per_chain.items():
        seq_ids_sorted = sorted(seq_ids)
        binding_types.append({"chain": {"id": chain, "binding": ",".join(map(str, seq_ids_sorted))}})

    return {"binding_types": binding_types}
