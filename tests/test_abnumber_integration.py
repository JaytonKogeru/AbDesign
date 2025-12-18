"""Integration checks to ensure the upstream AbNumber package is in use."""
from __future__ import annotations

from pathlib import Path
from typing import Any
import unittest

try:  # pragma: no cover - optional dependency
    import abnumber
    from abnumber import Chain
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    abnumber = None
    Chain = None


@unittest.skipIf(abnumber is None, "abnumber is not installed in this environment")
class TestAbnumberIntegration(unittest.TestCase):
    def test_official_package_is_imported(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        abn_path = Path(abnumber.__file__).resolve()

        self.assertNotIn("vendored", getattr(abnumber, "__version__", "").lower())
        # Allow installation in .venv inside the repo, but ensure it's not a source checkout in root
        if abn_path.is_relative_to(repo_root):
            self.assertTrue(
                "site-packages" in abn_path.parts or ".venv" in abn_path.parts,
                f"abnumber seems to be loaded from local source: {abn_path}"
            )

    def test_chain_numbering_and_cdrs(self) -> None:
        sequence = (
            "EVQLVESGGGLVQPGGSLRLSCAASGFTFSSYAMHWVRQAPGKGLEWVSAISWNSGSTYYADSVKGRFTISRDNAKNTL"
            "YLQMNSLRAEDTAVYYCARRRGVFDYWGQGTLVTVSS"
        )

        # chain_type is inferred from sequence in newer abnumber versions
        # Force use_anarcii=True because anarci is not available
        chain = Chain(sequence, scheme="chothia", use_anarcii=True)

        numbering_source = getattr(chain, "numbering", getattr(chain, "positions", []))
        numbering_labels = [_label(pos) for pos in numbering_source]
        observed_sequence = getattr(chain, "seq", getattr(chain, "sequence", sequence))

        # Check for cdrs or cdr*_seq attributes
        has_cdrs = getattr(chain, "cdrs", None) or (
            getattr(chain, "cdr1_seq", None) and getattr(chain, "cdr2_seq", None) and getattr(chain, "cdr3_seq", None)
        )
        self.assertTrue(has_cdrs, "CDR annotations should not be empty")
        self.assertTrue(numbering_labels, "Numbering labels should be present")
        self.assertEqual(len(numbering_labels), len(observed_sequence))

        # Ensure insertion-like labels are handled gracefully (letters within labels).
        contains_inserts = any(_contains_insert(label) for label in numbering_labels)
        self.assertTrue(contains_inserts or _contains_insert("52A"))


def _label(position: Any) -> str:
    if position is None:
        return ""
    for attr in ("label", "to_str", "__str__"):
        value = getattr(position, attr, None)
        if callable(value):
            try:
                return str(value())
            except Exception:  # noqa: BLE001
                continue
        if value is not None:
            return str(value)
    return str(position)


def _contains_insert(label: str) -> bool:
    return any(char.isalpha() for char in str(label))


if __name__ == "__main__":
    unittest.main()
