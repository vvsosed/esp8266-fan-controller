import pathlib
import sys
import tempfile
import unittest
from pathlib import Path

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from netlist import Part
from schematic import Place, Schematic, erc, exported_nets, load_symbol, pin_offsets
from sexp import find

TITLE = {"title": "test", "rev": "0", "date": "2026-11-22", "comment1": ""}
R_FP = "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal"


class SchematicTest(unittest.TestCase):
    def test_load_symbol_flattens_extends(self):
        s = load_symbol("RF_Module:ESP-12F")
        self.assertEqual(s[1], "RF_Module:ESP-12F")
        self.assertIsNone(find(s, "extends"))
        self.assertEqual(len(pin_offsets(s)), 22)
        self.assertEqual(pin_offsets(load_symbol("Device:R"))["1"], (0.0, 3.81, 270))

    def test_rotations_connect(self):
        # eight resistors, every rotation with and without mirror, each pin wired to a label; the exported netlist must see every pin
        sch = Schematic(TITLE)
        for i, (rot, mirror) in enumerate([(0, None), (90, None), (180, None), (270, None), (0, "x"), (0, "y"), (90, "x"), (90, "y")]):
            ref = f"R{i + 1}"
            part = Part(ref, "Device:R", R_FP, "10k", {"1": f"A{i}", "2": f"B{i}"})
            sch.add_part(part, Place(ref, (30 + 20 * i, 60), rot, mirror))
            for pin, net in part.pins.items():
                x, y = sch.pin(ref, pin)
                sch.add_wire([(x, y), (x, y + 2.54)])
                sch.add_label(net, (x, y + 2.54))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.kicad_sch"
            sch.write(p)
            nets = exported_nets(p)
            self.assertEqual(nets["A0"], {("R1", "1")})
            self.assertEqual(nets["B7"], {("R8", "2")})
            self.assertEqual(len(nets), 16, sorted(nets))

    def test_power_and_erc(self):
        sch = Schematic(TITLE)
        sch.add_part(Part("R1", "Device:R", R_FP, "10k", {"1": "3V3", "2": "GND"}), Place("R1", (50, 50)))
        sch.add_power("3V3", sch.pin("R1", "1"))
        sch.add_power("GND", sch.pin("R1", "2"), 180)
        sch.add_flag(sch.pin("R1", "1"))
        sch.add_flag(sch.pin("R1", "2"))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.kicad_sch"
            sch.write(p)
            self.assertEqual(erc(p), [])
            self.assertEqual(exported_nets(p), {"3V3": {("R1", "1")}, "GND": {("R1", "2")}})


if __name__ == "__main__":
    unittest.main()
