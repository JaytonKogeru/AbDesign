"""Run a lightweight self-test without API, Redis, or workers."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import List

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from pipeline.epitope.mapping import build_residue_mapping_v2, resolve_hotspots_v2
from pipeline.epitope.spec import parse_hotspot_token
from pipeline.epitope.standardize import standardize_structure
from scripts.verify_abnumber import verify_chain_numbering, verify_package_source


def _assert_mapping_fields(mapping_path: Path) -> int:
    payload = json.loads(mapping_path.read_text())
    if payload.get("mapping_schema_version") != 2:
        raise SystemExit("mapping_schema_version must be 2")

    residues = [res for chain in payload.get("chains", []) for res in chain.get("residues", [])]
    if not residues:
        raise SystemExit("no residues found in mapping_v2 output")
    for res in residues:
        if "present_seq_id" not in res or "mmcif_label" not in res:
            raise SystemExit("present_seq_id or mmcif_label missing from mapping_v2")
    return len(residues)


def _assert_resolved_fields(resolved_path: Path) -> List[str]:
    payload = json.loads(resolved_path.read_text())
    if payload.get("schema_version") != 2:
        raise SystemExit("resolved schema_version must be 2")
    if payload.get("unmatched"):
        raise SystemExit("selftest hotspots should resolve without unmatched entries")
    resolved_tokens = []
    for entry in payload.get("resolved", []):
        auth = entry.get("auth", {})
        present = entry.get("present_seq_id", {})
        label = entry.get("mmcif_label", {})
        resolved_tokens.append(
            f"{auth.get('chain')}:{auth.get('resi')}{auth.get('ins', '')} -> present {present.get('seq_id')} / label {label.get('label_seq_id')}"
        )
    return resolved_tokens


def main() -> None:
    verify_package_source()
    verify_chain_numbering()

    structure_path = Path("tests/data/hotspot_sample.pdb")
    hotspots = [parse_hotspot_token(token) for token in ["A:54", "A:55A"]]

    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        standardized = standardize_structure(structure_path, out_dir)
        mapping = build_residue_mapping_v2(standardized)
        mapping_path = out_dir / "target_residue_mapping_v2.json"
        mapping.write_json(mapping_path)

        resolved = resolve_hotspots_v2(hotspots, mapping)
        resolved_path = out_dir / "target_hotspots_resolved_v2.json"
        resolved.write_json(resolved_path)

        residue_count = _assert_mapping_fields(mapping_path)
        resolved_tokens = _assert_resolved_fields(resolved_path)

        print("Self-test summary:")
        print(f"  Residues parsed: {residue_count}")
        print("  Resolved hotspots:")
        for token in resolved_tokens:
            print(f"    - {token}")


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        print(exc)
        sys.exit(1)
