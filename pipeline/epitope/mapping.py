"""Residue mapping utilities for translating auth indices to canonical numbering."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Mapping, MutableMapping, Optional, Sequence, Tuple

try:  # pragma: no cover - optional dependency
    from Bio.PDB import MMCIFParser, PDBParser
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    MMCIFParser = None
    PDBParser = None

from pipeline.epitope.spec import ResidueRefAuth, ResidueRefCanonical

_STANDARD_RESIDUES = {
    "ALA": "A",
    "ARG": "R",
    "ASN": "N",
    "ASP": "D",
    "CYS": "C",
    "GLN": "Q",
    "GLU": "E",
    "GLY": "G",
    "HIS": "H",
    "ILE": "I",
    "LEU": "L",
    "LYS": "K",
    "MET": "M",
    "PHE": "F",
    "PRO": "P",
    "SER": "S",
    "THR": "T",
    "TRP": "W",
    "TYR": "Y",
    "VAL": "V",
    "SEC": "U",
    "PYL": "O",
}


@dataclass(frozen=True)
class MappingResidue:
    auth: ResidueRefAuth
    canonical: ResidueRefCanonical
    resname3: str
    resname1: Optional[str]

    def to_dict(self) -> Dict[str, object]:
        return {
            "auth": asdict(self.auth),
            "canonical": asdict(self.canonical),
            "resname3": self.resname3,
            "resname1": self.resname1,
        }


@dataclass
class MappingResult:
    residues: List[MappingResidue]

    def __post_init__(self) -> None:
        self._by_auth: Dict[Tuple[str, int, str], MappingResidue] = {
            (res.auth.chain, res.auth.resi, res.auth.ins): res for res in self.residues
        }

    def get(self, ref: ResidueRefAuth) -> Optional[MappingResidue]:
        return self._by_auth.get((ref.chain, ref.resi, ref.ins))

    def by_chain(self) -> Mapping[str, List[MappingResidue]]:
        chains: MutableMapping[str, List[MappingResidue]] = {}
        for residue in self.residues:
            chains.setdefault(residue.auth.chain, []).append(residue)
        return chains

    def to_dict(self) -> Dict[str, object]:
        return {"residues": [residue.to_dict() for residue in self.residues]}

    def write_json(self, path: Path) -> None:
        import json

        path.write_text(json.dumps(self.to_dict(), indent=2))


@dataclass(frozen=True)
class ResolvedHotspot:
    auth: ResidueRefAuth
    canonical: ResidueRefCanonical
    resname3: Optional[str] = None
    resname1: Optional[str] = None

    def to_dict(self) -> Dict[str, object]:
        return {
            "auth": asdict(self.auth),
            "canonical": asdict(self.canonical),
            "resname3": self.resname3,
            "resname1": self.resname1,
        }


@dataclass
class ResolveResult:
    resolved: List[ResolvedHotspot]
    errors: List[str]

    def to_dict(self) -> Dict[str, object]:
        return {
            "resolved": [hotspot.to_dict() for hotspot in self.resolved],
            "errors": self.errors,
        }

    def write_json(self, path: Path) -> None:
        import json

        path.write_text(json.dumps(self.to_dict(), indent=2))


class MappingError(RuntimeError):
    """Raised when mapping cannot be completed."""


_DEF_PARSER_OPTIONS = {"QUIET": True}


def build_residue_mapping(structure_path: Path) -> MappingResult:
    """Build mapping between auth numbering and canonical indices for a structure."""

    structure_path = Path(structure_path)
    if not structure_path.exists():
        raise MappingError(f"structure file not found: {structure_path}")
    records = _extract_residue_records(structure_path)

    residues: List[MappingResidue] = []
    chain_counters: Dict[str, int] = {}
    for chain, resseq, insertion, resname in records:
        chain_counters[chain] = chain_counters.get(chain, 0) + 1
        canonical_ref = ResidueRefCanonical(chain=chain, seq_id=chain_counters[chain])
        auth_ref = ResidueRefAuth(chain=chain, resi=resseq, ins=insertion)
        residues.append(
            MappingResidue(
                auth=auth_ref,
                canonical=canonical_ref,
                resname3=resname,
                resname1=_STANDARD_RESIDUES.get(resname),
            )
        )
    return MappingResult(residues)


def resolve_hotspots(auth_hotspots: Sequence[ResidueRefAuth], mapping: MappingResult) -> ResolveResult:
    resolved: List[ResolvedHotspot] = []
    errors: List[str] = []
    chain_map = mapping.by_chain()

    for hotspot in auth_hotspots:
        mapping_residue = mapping.get(hotspot)
        if mapping_residue:
            resolved.append(
                ResolvedHotspot(
                    auth=hotspot,
                    canonical=mapping_residue.canonical,
                    resname3=mapping_residue.resname3,
                    resname1=mapping_residue.resname1,
                )
            )
            continue

        chain_residues = chain_map.get(hotspot.chain)
        if chain_residues:
            available = ", ".join(_format_auth_token(res.auth) for res in chain_residues[:25])
            if len(chain_residues) > 25:
                available += ", ..."
            errors.append(
                f"Hotspot {_format_auth_token(hotspot)} not found on chain {hotspot.chain}. Available residues: {available}"
            )
        else:
            available_chains = ", ".join(sorted(chain_map.keys())) or "none"
            errors.append(
                f"Chain {hotspot.chain} not present in structure for hotspot {_format_auth_token(hotspot)}. Available chains: {available_chains}"
            )

    return ResolveResult(resolved=resolved, errors=errors)


def _select_parser(structure_path: Path):
    if PDBParser is None:
        return None

    suffix = structure_path.suffix.lower()
    if suffix in {".cif", ".mmcif"}:
        return MMCIFParser(**_DEF_PARSER_OPTIONS) if MMCIFParser else None
    return PDBParser(**_DEF_PARSER_OPTIONS)


def _format_auth_token(ref: ResidueRefAuth) -> str:
    suffix = ref.ins or ""
    return f"{ref.chain}:{ref.resi}{suffix}"


def _extract_residue_records(structure_path: Path) -> List[Tuple[str, int, str, str]]:
    parser = _select_parser(structure_path)

    if parser:
        return _extract_with_biopython(structure_path, parser)

    if structure_path.suffix.lower() not in {".pdb", ".ent", ""}:
        raise MappingError("Biopython is required to parse non-PDB structures for hotspot mapping")

    return _extract_from_pdb_lines(structure_path)


def _extract_with_biopython(structure_path: Path, parser) -> List[Tuple[str, int, str, str]]:
    try:
        structure = parser.get_structure("target", str(structure_path))
        model = structure[0]
    except Exception as exc:  # noqa: BLE001
        raise MappingError(f"structure {structure_path} does not contain model 0") from exc

    records: List[Tuple[str, int, str, str]] = []
    for chain in model:
        for residue in chain:
            hetero_flag, resseq, insertion = residue.id
            if hetero_flag.strip():
                continue
            resname = residue.get_resname().strip()
            if resname not in _STANDARD_RESIDUES:
                continue
            records.append((chain.id, int(resseq), (insertion or "").strip(), resname))
    return records


def _extract_from_pdb_lines(structure_path: Path) -> List[Tuple[str, int, str, str]]:
    records: List[Tuple[str, int, str, str]] = []
    seen: set[Tuple[str, int, str]] = set()
    with structure_path.open() as handle:
        for line in handle:
            if not line.startswith("ATOM"):
                continue
            resname = line[17:20].strip()
            if resname not in _STANDARD_RESIDUES:
                continue
            chain = line[21].strip()
            resseq_str = line[22:26].strip()
            insertion = line[26].strip()
            if not chain or not resseq_str:
                continue
            try:
                resseq = int(resseq_str)
            except ValueError:
                continue
            key = (chain, resseq, insertion)
            if key in seen:
                continue
            seen.add(key)
            records.append((chain, resseq, insertion, resname))
    return records
