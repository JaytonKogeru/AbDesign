"""Residue mapping utilities for translating auth indices to canonical numbering."""
from __future__ import annotations

import datetime as _dt
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence, Tuple

from pipeline.epitope.standardize import StandardizedStructure, standardize_structure
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

_SCOPE_ALLOWED = {
    "protein": {"protein"},
    "polymer": {"protein", "nucleic"},
    "all": {"protein", "nucleic", "hetero", "water", "unknown"},
}


class MappingError(RuntimeError):
    """Raised when mapping cannot be completed."""


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
        path.write_text(json.dumps(self.to_dict(), indent=2))


@dataclass(frozen=True)
class MappingResidueV2:
    auth: ResidueRefAuth
    present_seq_id: int
    label_asym_id: str
    label_seq_id: int
    resname3: str
    category: str

    def to_dict(self) -> Dict[str, object]:
        payload = {
            "auth": asdict(self.auth),
            "present_seq_id": self.present_seq_id,
            "mmcif_label": {"label_asym_id": self.label_asym_id, "label_seq_id": self.label_seq_id},
            "resname3": self.resname3,
            "entity_type": self.category,
        }
        return payload


@dataclass
class MappingResultV2:
    residues: List[MappingResidueV2]
    standardized: StandardizedStructure
    generated_at: str

    def __post_init__(self) -> None:
        self._by_auth: Dict[Tuple[str, int, str], MappingResidueV2] = {
            (res.auth.chain, res.auth.resi, res.auth.ins): res for res in self.residues
        }

    def get(self, ref: ResidueRefAuth) -> Optional[MappingResidueV2]:
        return self._by_auth.get((ref.chain, ref.resi, ref.ins))

    def by_chain(self) -> Mapping[str, List[MappingResidueV2]]:
        chains: MutableMapping[str, List[MappingResidueV2]] = {}
        for residue in self.residues:
            chains.setdefault(residue.auth.chain, []).append(residue)
        return chains

    def to_dict(self) -> Dict[str, object]:
        chains: List[Dict[str, object]] = []
        chain_residues = self.by_chain()
        for chain_id, residues in chain_residues.items():
            label_asym_id = residues[0].label_asym_id if residues else self.standardized.chain_id_map.get(chain_id, chain_id)
            chains.append(
                {
                    "auth_chain_id": chain_id,
                    "label_asym_id": label_asym_id,
                    "residues": [res.to_dict() for res in residues],
                }
            )

        return {
            "mapping_schema_version": 2,
            "generated_at": self.generated_at,
            "source_structure": {
                "input_path": str(self.standardized.input_path),
                "input_format": self.standardized.input_format,
                "standardized_path": str(self.standardized.standardized_path),
                "standardized_format": "mmcif",
            },
            "id_schemes": {
                "input_hotspot": "pdb_auth",
                "canonical": "present_seq_id",
                "mmcif_label": "label_seq_id",
            },
            "chains": chains,
        }

    def write_json(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2))


@dataclass
class ResolvedHotspotV2:
    auth: ResidueRefAuth
    present_seq_id: Dict[str, object]
    mmcif_label: Dict[str, object]

    def to_dict(self) -> Dict[str, object]:
        return {
            "auth": asdict(self.auth),
            "present_seq_id": self.present_seq_id,
            "mmcif_label": self.mmcif_label,
        }


@dataclass
class ResolveResultV2:
    input_hotspots: List[str]
    normalized_auth: List[ResidueRefAuth]
    resolved: List[ResolvedHotspotV2]
    unmatched: List[Dict[str, object]]

    def to_dict(self) -> Dict[str, object]:
        return {
            "schema_version": 2,
            "input_hotspots": self.input_hotspots,
            "normalized_auth": [asdict(ref) for ref in self.normalized_auth],
            "resolved": [res.to_dict() for res in self.resolved],
            "unmatched": self.unmatched,
        }

    def write_json(self, path: Path) -> None:
        path.write_text(json.dumps(self.to_dict(), indent=2))


def _require_gemmi():
    try:  # pragma: no cover - import guard
        import gemmi  # noqa: WPS433
    except ModuleNotFoundError as exc:  # pragma: no cover - handled path
        raise MappingError("gemmi is required for hotspot mapping. Install with 'pip install gemmi>=0.6'.") from exc
    return gemmi


def _monomer_category(resname: str) -> str:
    gemmi = _require_gemmi()
    try:
        monomer_type = gemmi.find_monomer_type(resname)
    except Exception:  # noqa: BLE001
        return "unknown"

    from gemmi import MonomerType  # type: ignore  # noqa: WPS433

    protein_types = {getattr(MonomerType, name, None) for name in ("PeptideL", "PeptideD", "Peptide")}
    nucleic_types = {getattr(MonomerType, name, None) for name in ("DNA", "RNA", "DNA_RNA")}
    hetero_types = {getattr(MonomerType, name, None) for name in ("Saccharide", "Lipid", "NonPolymer", "Ion")}

    if monomer_type in protein_types:
        return "protein"
    if monomer_type in nucleic_types:
        return "nucleic"
    if monomer_type == getattr(MonomerType, "Water", object()):
        return "water"
    if monomer_type in hetero_types:
        return "hetero"
    return "unknown"


def _collect_residue_rows(standardized_path: Path) -> List[Tuple[str, int, str, str, int, str]]:
    gemmi = _require_gemmi()
    try:
        block = gemmi.cif.read_file(str(standardized_path)).sole_block()
    except Exception as exc:  # noqa: BLE001
        raise MappingError(f"failed to parse standardized structure {standardized_path}: {exc}") from exc

    loop = block.find_loop("_atom_site.label_seq_id")
    if loop is None:
        raise MappingError("standardized structure missing _atom_site loop for residue extraction")

    try:
        label_seq_idx = loop.tag_position("_atom_site.label_seq_id")
        label_asym_idx = loop.tag_position("_atom_site.label_asym_id")
        auth_asym_idx = loop.tag_position("_atom_site.auth_asym_id")
        auth_seq_idx = loop.tag_position("_atom_site.auth_seq_id")
        ins_idx = loop.tag_position("_atom_site.pdbx_PDB_ins_code")
        resname_idx = loop.tag_position("_atom_site.label_comp_id")
    except KeyError as exc:  # noqa: BLE001
        raise MappingError("standardized structure missing required atom site columns") from exc

    seen: set[Tuple[str, int, str]] = set()
    rows: List[Tuple[str, int, str, str, int, str]] = []
    for row in loop:
        auth_chain = row[auth_asym_idx].strip()
        label_asym = row[label_asym_idx].strip()
        resname = row[resname_idx].strip()
        ins_raw = row[ins_idx].strip()
        ins = "" if ins_raw in {"?", "."} else ins_raw

        try:
            label_seq = int(row[label_seq_idx])
            auth_seq = int(row[auth_seq_idx])
        except ValueError as exc:  # noqa: BLE001
            raise MappingError("non-integer residue identifier encountered in standardized structure") from exc

        key = (auth_chain, auth_seq, ins)
        if key in seen:
            continue
        seen.add(key)
        rows.append((auth_chain, auth_seq, ins, label_asym, label_seq, resname))

    if not rows:
        raise MappingError("no residues found in standardized structure")
    return rows


def build_residue_mapping_v2(standardized: StandardizedStructure) -> MappingResultV2:
    rows = _collect_residue_rows(standardized.standardized_path)
    chain_counters: Dict[str, int] = {}
    residues: List[MappingResidueV2] = []

    for auth_chain, auth_seq, ins, label_asym, label_seq, resname in rows:
        chain_counters[auth_chain] = chain_counters.get(auth_chain, 0) + 1
        category = _monomer_category(resname)
        residues.append(
            MappingResidueV2(
                auth=ResidueRefAuth(chain=auth_chain, resi=auth_seq, ins=ins),
                present_seq_id=chain_counters[auth_chain],
                label_asym_id=label_asym,
                label_seq_id=label_seq,
                resname3=resname,
                category=category,
            )
        )

    return MappingResultV2(
        residues=residues,
        standardized=standardized,
        generated_at=_dt.datetime.utcnow().isoformat() + "Z",
    )


def resolve_hotspots_v2(
    auth_hotspots: Sequence[ResidueRefAuth], mapping: MappingResultV2, scope: str = "protein"
) -> ResolveResultV2:
    if scope not in _SCOPE_ALLOWED:
        raise ValueError("hotspot_residue_scope must be one of 'protein', 'polymer', or 'all'")

    resolved: List[ResolvedHotspotV2] = []
    unmatched: List[Dict[str, object]] = []
    chain_map = mapping.by_chain()
    input_tokens = [ref.token() for ref in auth_hotspots]

    for hotspot in auth_hotspots:
        mapping_residue = mapping.get(hotspot)
        if mapping_residue is None:
            unmatched.append(_missing_residue_payload(hotspot, chain_map))
            continue

        if mapping_residue.category not in _SCOPE_ALLOWED[scope]:
            unmatched.append(
                {
                    "auth": asdict(hotspot),
                    "reason": "filtered_by_scope",
                    "hint": "Hotspot outside allowed scope; set hotspot_residue_scope='all' or 'polymer' to include it.",
                }
            )
            continue

        resolved.append(
            ResolvedHotspotV2(
                auth=hotspot,
                present_seq_id={"chain": hotspot.chain, "seq_id": mapping_residue.present_seq_id},
                mmcif_label={"label_asym_id": mapping_residue.label_asym_id, "label_seq_id": mapping_residue.label_seq_id},
            )
        )

    return ResolveResultV2(
        input_hotspots=input_tokens,
        normalized_auth=list(auth_hotspots),
        resolved=resolved,
        unmatched=unmatched,
    )


def _missing_residue_payload(hotspot: ResidueRefAuth, chain_map: Mapping[str, List[MappingResidueV2]]):
    chain_residues = chain_map.get(hotspot.chain)
    if chain_residues:
        auth_ids = [res.auth.resi for res in chain_residues]
        hint = f"available auth resi range: {min(auth_ids)}-{max(auth_ids)}; check insertion codes"
    else:
        available_chains = ", ".join(sorted(chain_map.keys())) or "none"
        hint = f"available chains: {available_chains}"
    return {
        "auth": asdict(hotspot),
        "reason": "not_found_in_structure",
        "hint": hint,
    }


def build_residue_mapping(structure_path: Path) -> MappingResult:
    standardized = standardize_structure(structure_path, Path(structure_path).parent)
    mapping_v2 = build_residue_mapping_v2(standardized)
    return mapping_v1_from_v2(mapping_v2)


def mapping_v1_from_v2(mapping_v2: MappingResultV2) -> MappingResult:
    residues: List[MappingResidue] = []
    for res in mapping_v2.residues:
        if res.resname3 not in _STANDARD_RESIDUES:
            continue
        residues.append(
            MappingResidue(
                auth=res.auth,
                canonical=ResidueRefCanonical(chain=res.auth.chain, seq_id=res.present_seq_id),
                resname3=res.resname3,
                resname1=_STANDARD_RESIDUES.get(res.resname3),
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


def _format_auth_token(ref: ResidueRefAuth) -> str:
    suffix = ref.ins or ""
    return f"{ref.chain}:{ref.resi}{suffix}"

