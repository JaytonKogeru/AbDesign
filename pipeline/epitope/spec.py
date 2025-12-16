"""Data structures and parsers for target hotspots."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List


@dataclass(frozen=True)
class ResidueRefAuth:
    """Reference to a residue using PDB auth identifiers."""

    chain: str
    resi: int
    ins: str = ""

    def token(self) -> str:
        suffix = self.ins or ""
        return f"{self.chain}:{self.resi}{suffix}".strip()


@dataclass(frozen=True)
class ResidueRefCanonical:
    """Reference to a residue using canonical 1-based sequence numbering."""

    chain: str
    seq_id: int


@dataclass
class HotspotSpec:
    """Container describing hotspot inputs and resolution status."""

    input: List[ResidueRefAuth]
    resolved: List[Any]
    errors: List[str]


def parse_hotspot_token(token: str) -> ResidueRefAuth:
    """Parse a hotspot token in the ``A:305`` or ``A:52A`` format."""

    if not isinstance(token, str):
        raise ValueError("hotspot token must be a string like 'A:305'")

    if token.count(":") != 1:
        raise ValueError("hotspot token must contain a single ':' separating chain and residue, e.g. 'A:305'")

    chain_part, res_part = token.split(":")
    chain = chain_part.strip()
    if not chain:
        raise ValueError("chain identifier in hotspot token cannot be empty")

    res_part = res_part.strip()
    if not res_part:
        raise ValueError("residue portion of hotspot token cannot be empty")

    number_str = res_part[:-1] if res_part[-1:].isalpha() else res_part
    insertion = res_part[-1] if res_part[-1:].isalpha() else ""

    try:
        resi = int(number_str)
    except ValueError as exc:  # noqa: BLE001
        raise ValueError("residue index must be an integer, e.g. '305' or '52A'") from exc

    if insertion and len(insertion) != 1:
        raise ValueError("insertion code must be a single character")

    return ResidueRefAuth(chain=chain, resi=resi, ins=insertion)


def _parse_hotspot_object(obj: Any) -> ResidueRefAuth:
    if not isinstance(obj, dict):
        raise ValueError("hotspot entries must be strings or dict objects")

    if "chain" not in obj or "resi" not in obj:
        raise ValueError("hotspot dict must include 'chain' and 'resi' fields")

    chain = obj.get("chain")
    resi = obj.get("resi")
    ins = obj.get("ins") or ""

    if not isinstance(chain, str) or not chain:
        raise ValueError("hotspot chain must be a non-empty string")

    if not isinstance(resi, int):
        raise ValueError("hotspot resi must be an integer")

    if not isinstance(ins, str):
        raise ValueError("hotspot insertion code must be a string")
    if len(ins) > 1:
        raise ValueError("hotspot insertion code must be at most one character")

    return ResidueRefAuth(chain=chain, resi=resi, ins=ins)


def normalize_target_hotspots(raw: Any) -> List[ResidueRefAuth]:
    """Normalize raw hotspot input into :class:`ResidueRefAuth` objects."""

    if raw is None:
        raise ValueError("target_hotspots must be provided as a list of strings or objects")

    if not isinstance(raw, list):
        raise ValueError("target_hotspots must be a list of tokens like 'A:305' or dict entries")

    normalized: List[ResidueRefAuth] = []
    seen = set()
    for entry in raw:
        if isinstance(entry, str):
            parsed = parse_hotspot_token(entry.strip())
        else:
            parsed = _parse_hotspot_object(entry)

        key = (parsed.chain, parsed.resi, parsed.ins)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(parsed)

    return normalized
