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
    def test_deterministic(self):
        a, b = Path(tempfile.mkdtemp()), Path(tempfile.mkdtemp())
        gen.write_all(a, quick=True)
        gen.write_all(b, quick=True)
        for name in FILES:
            self.assertEqual((a / name).read_bytes(), (b / name).read_bytes(), name)

    def test_committed_files_current(self):
        a = Path(tempfile.mkdtemp())
        gen.write_all(a, quick=True)
        for name in FILES:
            self.assertEqual((a / name).read_bytes(), (HERE.parent / name).read_bytes(), name)

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
