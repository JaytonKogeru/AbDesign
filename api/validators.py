"""Validation helpers for uploaded structure files."""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Tuple

from . import schemas

_fastapi_spec = importlib.util.find_spec("fastapi")
if _fastapi_spec:
    from fastapi import HTTPException, status
else:
    class HTTPException(Exception):
        def __init__(self, status_code: int, detail: str):
            self.status_code = status_code
            self.detail = detail
            super().__init__(detail)

    class status:  # type: ignore[no-redef]
        HTTP_400_BAD_REQUEST = 400

_bio_spec = importlib.util.find_spec("Bio")
if _bio_spec:
    from Bio.PDB import MMCIFParser, PDBParser
else:
    MMCIFParser = None  # type: ignore
    PDBParser = None  # type: ignore

_mdtraj_spec = importlib.util.find_spec("mdtraj")
if _mdtraj_spec:
    import mdtraj  # type: ignore
else:
    mdtraj = None  # type: ignore

_py3dmol_spec = importlib.util.find_spec("py3Dmol")
if _py3dmol_spec:
    import py3Dmol  # type: ignore  # noqa: F401


def _raise_bad_request(message: str) -> None:
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


def _load_structure(path: Path):
    suffix = path.suffix.lower()
    if suffix == ".pdb" and PDBParser is not None:
        parser = PDBParser(QUIET=True)
        return parser.get_structure("uploaded", str(path))
    if suffix == ".cif" and MMCIFParser is not None:
        parser = MMCIFParser(QUIET=True)
        return parser.get_structure("uploaded", str(path))
    _raise_bad_request("Unsupported structure format or missing parser dependencies.")


def _count_atoms_with_mdtraj(path: Path) -> Tuple[int, int]:
    if mdtraj is None:
        return 0, 0
    try:
        traj = mdtraj.load(str(path))
        chain_count = len({atom.residue.chain.id for atom in traj.topology.atoms})
        atom_count = traj.n_atoms
        return chain_count, atom_count
    except Exception:  # noqa: BLE001
        return 0, 0


def validate_structure_file(path: Path) -> schemas.ParsedStructure:
    """Validate that the saved structure file is readable and contains atoms and chains."""

    if not path.exists() or not path.is_file():
        _raise_bad_request("Uploaded file is missing or unreadable from disk.")

    try:
        structure = _load_structure(path)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        _raise_bad_request(f"Unable to parse structure file: {exc}")

    chain_count = len(list(structure.get_chains()))
    atom_count = len(list(structure.get_atoms()))

    if chain_count == 0 or atom_count == 0:
        mdtraj_chain_count, mdtraj_atom_count = _count_atoms_with_mdtraj(path)
        chain_count = max(chain_count, mdtraj_chain_count)
        atom_count = max(atom_count, mdtraj_atom_count)

    if chain_count == 0 or atom_count == 0:
        _raise_bad_request("Structure file parsed but no chains/atoms detected.")

    return schemas.ParsedStructure(chain_count=chain_count, atom_count=atom_count)


def validate_and_update_response(response: schemas.UploadResponse) -> schemas.UploadResponse:
    """Populate response data with parsed structure details, raising 400 on failure."""

    target_path = response.converted_path or response.stored_path
    parsed = validate_structure_file(Path(target_path))
    response.parsed = parsed
    return response
