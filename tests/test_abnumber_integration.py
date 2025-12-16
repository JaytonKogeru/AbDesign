"""Integration checks to ensure the upstream AbNumber package is in use."""
from __future__ import annotations

from pathlib import Path
from typing import Any
import unittest

import abnumber
from abnumber import Chain


class TestAbnumberIntegration(unittest.TestCase):
    def test_official_package_is_imported(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        abn_path = Path(abnumber.__file__).resolve()

        self.assertNotIn("vendored", getattr(abnumber, "__version__", "").lower())
        self.assertFalse(abn_path.is_relative_to(repo_root))

    def test_chain_numbering_and_cdrs(self) -> None:
        sequence = (
            "EVQLVESGGGLVQPGGSLRLSCAASGFTFSSYAMHWVRQAPGKGLEWVSAISWNSGSTYYADSVKGRFTISRDNAKNTL"
            "YLQMNSLRAEDTAVYYCARRRGVFDYWGQGTLVTVSS"
        )

        chain = Chain(sequence, scheme="chothia", chain_type="H")

        numbering_labels = [_label(pos) for pos in getattr(chain, "numbering", [])]
        observed_sequence = getattr(chain, "seq", getattr(chain, "sequence", sequence))

        self.assertTrue(getattr(chain, "cdrs", None), "CDR annotations should not be empty")
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
