import pathlib
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import gen

FILES = ("fan_controller.kicad_sch", "fan_controller.kicad_pcb", "fan_controller.kicad_pro")


class GenTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.full, cls.quick = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
        gen.write_all(cls.full)                       # with the exports (about 20 s), shared by the tests below
        gen.write_all(cls.quick, quick=True)

    def test_deterministic(self):
        for name in FILES:
            self.assertEqual((self.full / name).read_bytes(), (self.quick / name).read_bytes(), name)

    def test_committed_files_current(self):
        """The committed project files and every file in out/ are what gen.py writes today; rerun it after a change."""
        stale = [name for name in FILES if (self.full / name).read_bytes() != (HERE.parent / name).read_bytes()]
        for f in sorted((self.full / "out").iterdir()):
            c = HERE.parent / "out" / f.name
            if f.is_file() and not (c.is_file() and c.read_bytes() == f.read_bytes()):
                stale.append("out/" + f.name)
        self.assertEqual(stale, [])

    def test_outputs_exist(self):
        out = HERE.parent / "out"
        for name in ("schematic.pdf", "bom.csv", "gerbers.zip", "board-top.png", "board-bottom.png", "erc.txt", "drc.txt"):
            self.assertTrue((out / name).stat().st_size > 0, name)
        names = zipfile.ZipFile(out / "gerbers.zip").namelist()
        self.assertTrue(any(n.endswith(("-F_Cu.gtl", "-F_Cu.gbr")) for n in names), names)    # Protel or KiCad extensions
        self.assertTrue(any(n.endswith(".drl") for n in names), names)
        self.assertTrue(any(n.endswith(".gbrjob") for n in names), names)
        self.assertIn("MF-R250", (out / "bom.csv").read_text())


if __name__ == "__main__":
    unittest.main()
