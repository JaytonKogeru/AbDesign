"""Resolve hotspot tokens against a structure without running the API."""
from __future__ import annotations

import argparse
from pathlib import Path

from pipeline.epitope.mapping import build_residue_mapping, resolve_hotspots
from pipeline.epitope.spec import normalize_target_hotspots


def main() -> None:
    parser = argparse.ArgumentParser(description="Resolve hotspot tokens to canonical numbering")
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
        help="Destination directory for mapping/resolution JSON files (defaults to structure directory)",
    )
    args = parser.parse_args()

    structure_path = Path(args.structure)
    output_dir = Path(args.output_dir) if args.output_dir else structure_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)

    auth_hotspots = normalize_target_hotspots(args.hotspot)
    mapping_result = build_residue_mapping(structure_path)
    mapping_path = output_dir / "target_residue_mapping.json"
    mapping_result.write_json(mapping_path)

    resolve_result = resolve_hotspots(auth_hotspots, mapping_result)
    resolved_path = output_dir / "target_hotspots_resolved.json"
    resolve_result.write_json(resolved_path)

    if resolve_result.errors:
        print("Encountered errors while resolving hotspots:\n" + "\n".join(resolve_result.errors))
    else:
        print("Resolved hotspots:")
        for hotspot in resolve_result.resolved:
            print(
                f"  {hotspot.auth.chain}:{hotspot.auth.resi}{hotspot.auth.ins or ''} -> "
                f"{hotspot.canonical.chain}:{hotspot.canonical.seq_id} ({hotspot.resname3})"
            )

    print(f"Mapping written to {mapping_path}")
    print(f"Resolved hotspots written to {resolved_path}")


if __name__ == "__main__":
    main()
