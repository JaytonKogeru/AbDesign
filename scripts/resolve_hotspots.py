"""Resolve hotspot tokens against a structure without running the API."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

from pipeline.epitope.mapping import build_residue_mapping_v2, resolve_hotspots_v2
from pipeline.epitope.spec import normalize_target_hotspots
from pipeline.epitope.standardize import standardize_structure


def _default_output_dir() -> Path:
    return Path.cwd() / "resolve_hotspots_outputs"


def _format_unmatched(unmatched: List[dict]) -> str:
    lines = []
    for entry in unmatched:
        auth = entry.get("auth", {})
        token = f"{auth.get('chain', '?')}:{auth.get('resi', '?')}{auth.get('ins', '')}"
        reason = entry.get("reason", "unknown")
        hint = entry.get("hint")
        detail = f"{token} -> {reason}"
        if hint:
            detail += f" (hint: {hint})"
        lines.append(detail)
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve hotspot tokens to canonical numbering (v2 schema)")
    parser.add_argument("--structure", required=True, help="Path to target structure (PDB/mmCIF)")
    parser.add_argument(
        "--hotspot",
        action="append",
        required=True,
        help="Hotspot token such as A:305. Can be provided multiple times.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Destination directory for mapping/resolution JSON files (defaults to a local outputs directory)",
    )
    parser.add_argument(
        "--scope",
        choices=["protein", "polymer", "all"],
        default="protein",
        help="Residue categories to include when resolving hotspots (default: protein)",
    )
    args = parser.parse_args()

    structure_path = Path(args.structure)
    output_dir = Path(args.output_dir) if args.output_dir else _default_output_dir()
    output_dir.mkdir(parents=True, exist_ok=True)

    auth_hotspots = normalize_target_hotspots(args.hotspot)
    standardized = standardize_structure(structure_path, output_dir)
    mapping_result = build_residue_mapping_v2(standardized)
    mapping_path = output_dir / "target_residue_mapping.json"
    mapping_result.write_json(mapping_path)

    resolve_result = resolve_hotspots_v2(auth_hotspots, mapping_result, scope=args.scope)
    resolved_path = output_dir / "target_hotspots_resolved.json"
    resolve_result.write_json(resolved_path)

    if resolve_result.unmatched:
        print("Encountered unmatched hotspots; see hints below.")
        print(_format_unmatched(resolve_result.unmatched))
        print(f"Mapping written to {mapping_path}")
        print(f"Resolved hotspots written to {resolved_path}")
        raise SystemExit(1)

    print("Resolved hotspots:")
    for hotspot in resolve_result.resolved:
        auth = hotspot.auth
        present_seq = hotspot.present_seq_id.get("seq_id")
        label_seq = hotspot.mmcif_label.get("label_seq_id")
        print(
            f"  {auth.chain}:{auth.resi}{auth.ins or ''} -> present {present_seq} / mmcif label {label_seq}"
        )

    print(f"Mapping written to {mapping_path}")
    print(f"Resolved hotspots written to {resolved_path}")


if __name__ == "__main__":
    main()
