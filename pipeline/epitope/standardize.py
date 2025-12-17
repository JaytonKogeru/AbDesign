"""Structure standardization utilities for hotspot processing."""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from pathlib import Path
from typing import Dict


class StructureStandardizationError(RuntimeError):
    """Raised when structure normalization fails."""


@dataclass(frozen=True)
class StandardizedStructure:
    input_path: Path
    input_format: str
    standardized_path: Path
    chain_id_map: Dict[str, str]


def _require_gemmi():
    try:  # pragma: no cover - import guard
        import gemmi  # noqa: WPS433
    except ModuleNotFoundError as exc:  # pragma: no cover - handled path
        raise StructureStandardizationError(
            "gemmi is required for structure standardization. Install with 'pip install gemmi>=0.6'."
        ) from exc
    return gemmi


def _detect_format(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".pdb", ".ent"}:
        return "pdb"
    if suffix in {".cif", ".mmcif"}:
        return "mmcif"
    raise StructureStandardizationError(
        f"Unsupported structure format for standardization: {path.suffix or 'unknown'}"
    )


def _extract_chain_map(doc) -> Dict[str, str]:
    block = doc.sole_block()
    loop = block.find_loop("_atom_site.auth_asym_id")
    if loop is None:
        raise StructureStandardizationError("standardized structure missing _atom_site loop for chain mapping")

    try:
        auth_idx = loop.tag_position("_atom_site.auth_asym_id")
        label_idx = loop.tag_position("_atom_site.label_asym_id")
    except KeyError as exc:  # noqa: BLE001
        raise StructureStandardizationError("standardized structure missing chain identifier columns") from exc

    mapping: Dict[str, str] = {}
    for row in loop:
        auth = row[auth_idx].strip()
        label = row[label_idx].strip()
        if auth and label and auth not in mapping:
            mapping[auth] = label
    if not mapping:
        raise StructureStandardizationError("no chain identifiers found in standardized structure")
    return mapping


def standardize_structure(input_path: Path, out_dir: Path) -> StandardizedStructure:
    """Read a PDB/mmCIF file and write a standardized mmCIF copy."""

    gemmi = _require_gemmi()
    input_path = Path(input_path)
    if not input_path.exists():
        raise StructureStandardizationError(f"structure file not found: {input_path}")

    input_format = _detect_format(input_path)

    try:
        structure = gemmi.read_structure(str(input_path))
    except Exception as exc:  # noqa: BLE001
        raise StructureStandardizationError(f"failed to parse structure {input_path}: {exc}") from exc

    if not structure:
        raise StructureStandardizationError(f"structure {input_path} contains no models")

    out_dir.mkdir(parents=True, exist_ok=True)
    standardized_path = out_dir / "standardized_target.cif"
    doc = structure.make_mmcif_document()
    doc.ensure_block().set_software_list([], generated=_dt.datetime.utcnow())
    doc.write_file(str(standardized_path))

    chain_map = _extract_chain_map(doc)

    return StandardizedStructure(
        input_path=input_path,
        input_format=input_format,
        standardized_path=standardized_path,
        chain_id_map=chain_map,
    )

