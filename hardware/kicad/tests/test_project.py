import json
import pathlib
import sys
import tempfile
import unittest
from pathlib import Path

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import ids
from project import write_project
from sexp import Sym, find, find_all, parse


class ProjectTest(unittest.TestCase):
    def test_footprints_load(self):
        import pcbnew
        lib = str(HERE.parent / "fan_controller.pretty")
        fp = pcbnew.FootprintLoad(lib, "Mini-360")
        self.assertIsNotNone(fp)
        pos = sorted((round(p.GetPosition().x / 1e6, 3), round(p.GetPosition().y / 1e6, 3), p.GetNumber()) for p in fp.Pads())
        self.assertEqual(pos, [(-7.62, -4.572, "1"), (-7.62, 4.572, "2"), (7.62, -4.572, "3"), (7.62, 4.572, "4")])
        self.assertEqual({p.GetDrillSize().x for p in fp.Pads()}, {1200000})
        f = pcbnew.FootprintLoad(lib, "Polyfuse_Radial_P5.1mm")
        self.assertIsNotNone(f)
        self.assertEqual(sorted(round(p.GetPosition().x / 1e6, 2) for p in f.Pads()), [-2.55, 2.55])

    def test_symbol_pins(self):
        node = parse((HERE.parent / "fan_controller.kicad_sym").read_text(encoding="utf-8"))
        sym = next(s for s in find_all(node, "symbol") if s[1] == "Mini-360")
        pins = {find(p, "number")[1]: (find(p, "name")[1], p[1]) for u in find_all(sym, "symbol") for p in find_all(u, "pin")}
        self.assertEqual(pins, {"1": ("IN+", Sym("power_in")), "2": ("IN-", Sym("passive")),
                                "3": ("OUT+", Sym("power_out")), "4": ("OUT-", Sym("passive"))})

    def test_project_files(self):
        with tempfile.TemporaryDirectory() as d:
            write_project(Path(d))
            pro = json.loads((Path(d) / "fan_controller.kicad_pro").read_text())
            self.assertEqual(pro["net_settings"]["classes"][0]["clearance"], 0.25)
            self.assertEqual(pro["board"]["design_settings"]["rules"]["min_copper_edge_clearance"], 0.5)
            self.assertIn('(name "fan_controller")', (Path(d) / "fp-lib-table").read_text())
            self.assertIn('(name "fan_controller")', (Path(d) / "sym-lib-table").read_text())

    def test_ids_deterministic(self):
        self.assertEqual(ids.sym("R1"), ids.sym("R1"))
        self.assertNotEqual(ids.sym("R1"), ids.sym("R2"))
        self.assertTrue(ids.path("R1").startswith("/" + str(ids.ROOT) + "/"))
        self.assertNotEqual(ids.other("wire", 1), ids.other("wire", 2))


if __name__ == "__main__":
    unittest.main()
