import pathlib
import sys
import tempfile
import unittest
from pathlib import Path

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import gen
import netlist
from schematic import erc, exported_nets
from sexp import find_all, parse


class SheetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.path = gen.write_schematic(Path(tempfile.mkdtemp()) / "fan_controller.kicad_sch")

    def test_erc_clean(self):
        self.assertEqual(erc(self.path), [])

    def test_nets_match_netlist(self):
        self.assertEqual(exported_nets(self.path), netlist.NETS)

    def test_every_symbol_has_footprint(self):
        node = parse(self.path.read_text(encoding="utf-8"))
        for s in find_all(node, "symbol"):
            props = {p[1]: p[2] for p in find_all(s, "property")}
            if not props["Reference"].startswith("#"):
                self.assertTrue(props["Footprint"], props["Reference"])

    def test_committed_file_is_current(self):
        self.assertEqual(self.path.read_text(encoding="utf-8"), (HERE.parent / "fan_controller.kicad_sch").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
