"""Verification script to ensure upstream AbNumber is used instead of vendored copy."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import abnumber
from abnumber import Chain


REPO_ROOT = Path(__file__).resolve().parents[1]


def _label(position: Any) -> str:
    if position is None:
        return ""
    for attr in ("label", "to_str", "__str__"):
        value = getattr(position, attr, None)
        if callable(value):
            try:
                return str(value())
            except Exception:
                continue
        if value is not None:
            return str(value)
    return str(position)


def verify_package_source() -> None:
    version = getattr(abnumber, "__version__", "")
    if "vendored" in version.lower():
        raise SystemExit("abnumber version indicates vendored copy")

    abn_path = Path(abnumber.__file__).resolve()
    try:
        if abn_path.is_relative_to(REPO_ROOT):
            # Allow .venv or site-packages inside repo
            if "site-packages" not in abn_path.parts and ".venv" not in abn_path.parts:
                raise SystemExit(f"abnumber resolves inside repository (source): {abn_path}")
    except AttributeError:
        # Python < 3.9 fallback
        if REPO_ROOT in abn_path.parents:
             if "site-packages" not in abn_path.parts and ".venv" not in abn_path.parts:
                raise SystemExit(f"abnumber resolves inside repository (source): {abn_path}")

    print(f"abnumber version: {version}")
    print(f"abnumber location: {abn_path}")


def verify_chain_numbering() -> None:
    sequence = (
        "EVQLVESGGGLVQPGGSLRLSCAASGFTFSSYAMHWVRQAPGKGLEWVSAISWNSGSTYYADSVKGRFTISRDNAKNTL"
        "YLQMNSLRAEDTAVYYCARRRGVFDYWGQGTLVTVSS"
    )
    # Force use_anarcii=True
    chain = Chain(sequence, scheme="chothia", use_anarcii=True)

    # cdrs property might be missing in newer abnumber/anarcii, check for cdr*_seq instead
    cdrs = getattr(chain, "cdrs", None)
    if not cdrs:
        # Fallback check
        if getattr(chain, "cdr1_seq", None):
            cdrs = True
    
    if not cdrs:
        raise SystemExit("CDR annotations missing from Chain")

    numbering = getattr(chain, "numbering", getattr(chain, "positions", []))
    numbering_labels = [_label(pos) for pos in numbering]
    if not numbering_labels:
        raise SystemExit("Numbering labels missing from Chain")

    serialized = {
        "cdrs": bool(cdrs),
        "numbering_labels_preview": numbering_labels[:5],
        "numbering_length": len(numbering_labels),
    }
    print("Numbering + CDR check:", serialized)


if __name__ == "__main__":
    try:
        verify_package_source()
        verify_chain_numbering()
    except SystemExit as exc:
        print(exc)
        sys.exit(1)
