from pathlib import Path

import pytest

from integrations.normalize import _validate_remarks


def test_validate_remarks_success(tmp_path):
    gemmi = pytest.importorskip("gemmi")
    pdb_path = tmp_path / "test.pdb"
    pdb_path.write_text(
        """
MODEL        1
ATOM      1  N   ALA A   1      11.104   8.551   2.169  1.00 20.00           N
ATOM      2  CA  ALA A   1      12.000   9.000   2.000  1.00 20.00           C
ENDMDL
END
""".strip()
    )
    remarks = ["REMARK PDBinfo-LABEL:    1 H1_start"]

    result = _validate_remarks(pdb_path, remarks)
    assert result["ok"] is True
    assert result["details"][0]["index"] == 1


def test_validate_remarks_failure(tmp_path):
    gemmi = pytest.importorskip("gemmi")
    pdb_path = tmp_path / "test.pdb"
    pdb_path.write_text(
        """
MODEL        1
ATOM      1  N   ALA A   1      11.104   8.551   2.169  1.00 20.00           N
ENDMDL
END
""".strip()
    )
    remarks = ["REMARK PDBinfo-LABEL:    5 H1_start"]

    result = _validate_remarks(pdb_path, remarks)
    assert result["ok"] is False
    assert result["details"][0]["reason"] == "index_out_of_range"
