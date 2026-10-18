"""Test della classificazione sensori per la mappa (data/build.py)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data"))
from build import colore, marca  # noqa: E402


class TestMarca(unittest.TestCase):
    def test_autel(self):
        self.assertEqual(marca("VALVE TPMS MX UNIVERS. GOMMA/RUBBER"), "A")
        self.assertEqual(marca("VALVE TPMS MX UNIVERSAL.BLACK"), "A")
        self.assertEqual(marca("TPMS AUTEL 1SENS 315/433MHZ RUBBER"), "A")

    def test_mate_huf(self):
        self.assertEqual(marca("VALVE MATE MULTISENS TPMS MP1RUBBER"), "M")
        self.assertEqual(marca("VALVE MATE MULTIS.TPMS SC3FL00B BLA"), "M")
        self.assertEqual(marca("VALVE MULT.TPMS SC2732 MOTORCYCLE M"), "M")
        self.assertEqual(marca("VALVE TPMS HUF BLE METAL BLACK"), "M")
        self.assertEqual(marca("VALVE TPMS SI2024 METAL"), "M")
        self.assertEqual(marca("VALVE TPMS SI2048 BLACK"), "M")

    def test_altri(self):
        self.assertEqual(marca("VALVE TPMS BEA019 BLACK"), "X")
        self.assertEqual(marca("VALVE TPMS PS8608 RUBBER"), "X")
        self.assertEqual(marca("TPMS RETROFIT KIT P451 (CAMPER)"), "X")

    def test_kit_valvole_esclusi(self):
        self.assertIsNone(marca("REPLAC.KIT 4 VALVE AUTELRUBBER CLIP"))
        self.assertIsNone(marca("REPLAC.KIT 4 VALVE MATE RUBBER"))


class TestColore(unittest.TestCase):
    def test_vince_ultimo_ordine(self):
        self.assertEqual(colore({"I_1": ["2025-03-01", {"M": 8}], "I_2": ["2026-02-01", {"A": 4}]}), "A")
        self.assertEqual(colore({"I_1": ["2026-03-01", {"M": 8}], "I_2": ["2026-02-01", {"A": 4}]}), "M")

    def test_ordine_misto(self):
        self.assertEqual(colore({"I_1": ["2026-03-01", {"A": 8, "M": 4}]}), "A")
        self.assertEqual(colore({"I_1": ["2026-03-01", {"A": 4, "M": 4}]}), "M")

    def test_altri_non_cambiano_colore(self):
        self.assertEqual(colore({"I_1": ["2025-03-01", {"M": 4}], "I_2": ["2026-05-01", {"X": 4}]}), "M")
        self.assertEqual(colore({"I_1": ["2026-05-01", {"X": 4}]}), "X")


if __name__ == "__main__":
    unittest.main()
