import types

import pytest

from integrations import normalize


def test_locate_subsequence_with_alignment_and_ambiguity(monkeypatch):
    # mock pairwise2 with deterministic alignments
    class DummyAlign:
        @staticmethod
        def localms(seq1, seq2, *args, **kwargs):
            # two alignments with similar normalized scores to trigger ambiguity
            # tuples: (seqA, seqB, score, start, end, ...)
            return [
                (seq1, seq2, 8.0, 2, 0, 0),
                (seq1, seq2, 7.7, 5, 0, 0),
            ]

    dummy_pairwise2 = types.SimpleNamespace(align=DummyAlign())
    monkeypatch.setattr(normalize, "pairwise2", dummy_pairwise2)

    locate = normalize._locate_subsequence("AAAAAVVVVV", "VVVV")
    assert locate is not None
    assert locate["ambiguous"] is True
    assert locate["start"] == 2
    assert locate["score"] >= 1.5


def test_locate_subsequence_threshold(monkeypatch):
    class DummyAlign:
        @staticmethod
        def localms(seq1, seq2, *args, **kwargs):
            return [(seq1, seq2, 1.0, 0, 0, 0)]  # normalized score below threshold

    dummy_pairwise2 = types.SimpleNamespace(align=DummyAlign())
    monkeypatch.setattr(normalize, "pairwise2", dummy_pairwise2)

    locate = normalize._locate_subsequence("AAAAA", "VVVV")
    assert locate is None


def test_map_segment_to_chain_uses_alignment_score(monkeypatch):
    # disable pairwise2 to trigger substring path
    monkeypatch.setattr(normalize, "pairwise2", None)

    class Residue:
        def __init__(self, label_seq_id, present_seq_id, resname3="ALA"):
            self.label_seq_id = label_seq_id
            self.present_seq_id = present_seq_id
            self.resname3 = resname3

    residues = [Residue(i + 1, i + 1) for i in range(10)]
    segment = {"name": "H1", "sequence": "AAA"}

    mapped = normalize._map_segment_to_chain(segment, "AAAAAAAAAA", residues)
    assert mapped["status"] == "mapped"
    assert mapped["alignment_score"] >= 3
    assert mapped["ambiguous"] is False
