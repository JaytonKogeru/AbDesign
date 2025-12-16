import unittest

from pipeline.epitope.spec import normalize_target_hotspots, parse_hotspot_token


class TestHotspotParsing(unittest.TestCase):
    def test_parse_hotspot_token_with_insertion(self) -> None:
        ref = parse_hotspot_token("A:52A")
        self.assertEqual(ref.chain, "A")
        self.assertEqual(ref.resi, 52)
        self.assertEqual(ref.ins, "A")

    def test_parse_hotspot_token_without_insertion(self) -> None:
        ref = parse_hotspot_token("B:305")
        self.assertEqual(ref.chain, "B")
        self.assertEqual(ref.resi, 305)
        self.assertEqual(ref.ins, "")

    def test_parse_hotspot_token_invalid_format(self) -> None:
        with self.assertRaises(ValueError):
            parse_hotspot_token("A305")

    def test_normalize_target_hotspots_mixed_inputs(self) -> None:
        raw = ["A:54", {"chain": "A", "resi": 55, "ins": "A"}, "A:54"]
        normalized = normalize_target_hotspots(raw)
        self.assertEqual([(ref.chain, ref.resi, ref.ins) for ref in normalized], [("A", 54, ""), ("A", 55, "A")])

    def test_normalize_target_hotspots_invalid_entry(self) -> None:
        with self.assertRaises(ValueError):
            normalize_target_hotspots([{"chain": "", "resi": "bad"}])
