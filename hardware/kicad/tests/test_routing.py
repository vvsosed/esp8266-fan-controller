import pathlib
import sys
import tempfile
import unittest
from pathlib import Path

import pcbnew

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import board
import gen


def mm(v):
    return v / 1e6


def drawings(b):
    d = b.Drawings()
    return [d[i].Cast() for i in range(len(d))]


def tracks(b):
    """Tracks and vias; the SWIG iterator behind GetTracks() is broken, so index the container."""
    t = b.Tracks()
    return [t[i].Cast() for i in range(len(t))]


class RoutingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp())
        gen.write_all(cls.dir, quick=True)
        cls.rep = board.drc(cls.dir / "fan_controller.kicad_pcb")
        cls.warn = board.drc(cls.dir / "fan_controller.kicad_pcb", severity="all")
        cls.board = pcbnew.LoadBoard(str(cls.dir / "fan_controller.kicad_pcb"))

    def test_drc_clean(self):
        self.assertEqual([v["description"] for v in self.rep["violations"]], [])
        self.assertEqual([v["description"] for v in self.rep["unconnected_items"]], [])
        self.assertEqual(self.rep["schematic_parity"], [])

    def test_widths(self):
        for t in tracks(self.board):
            if t.GetClass() != "PCB_TRACK":
                continue
            w, net = mm(t.GetWidth()), t.GetNetname()
            self.assertGreaterEqual(w, 0.3, net)
            if net in ("+12V_IN", "+12V", "+12V_SW"):
                self.assertGreaterEqual(w, 1.5, net)
            if net == "3V3":
                self.assertGreaterEqual(w, 0.5)

    def test_trunk_is_two_mm(self):
        widths = {mm(t.GetWidth()) for t in tracks(self.board) if t.GetClass() == "PCB_TRACK" and t.GetNetname() == "+12V_IN"}
        self.assertEqual(widths, {2.0})

    def test_labels_present_and_clear_of_parts(self):
        """Every pin label and marking is there, none is centred under a part, and the silk DRC finds nothing printed
        over other silk or over copper. (A label may overlap a courtyard's placement margin: that hides nothing.)"""
        texts = [t for t in drawings(self.board) if t.GetClass() == "PCB_TEXT" and t.GetLayer() == pcbnew.F_SilkS]
        words = {t.GetText() for t in texts}
        for w in ("GND", "12V", "FLOW", "3V3", "DQ", "TX", "RX", "RST", "FLASH", "Rev 1.0", "FAN 1", "FAN 2", "FAN 3"):
            self.assertTrue(any(w in x for x in words), w)
        for t in texts:
            centre = t.GetBoundingBox().GetCenter()
            for fp in self.board.GetFootprints():
                self.assertFalse(fp.GetCourtyard(pcbnew.F_CrtYd).BBox().Contains(centre), (t.GetText(), fp.GetReference()))

    def test_silk_legible(self):
        silk = [v["description"] + ": " + ", ".join(i["description"] for i in v["items"])
                for v in self.warn["violations"] if v["type"] in ("silk_overlap", "silk_over_copper")]
        self.assertEqual(silk, [])

    def test_parity_clean_at_all_severities(self):
        """The board matches the sheet in KiCad's own eyes: library ids, fields, BOM flags and the no-connect nets."""
        self.assertEqual(self.warn["schematic_parity"], [])

    def test_fan_pins_named_in_full(self):
        """Each fan pin carries its full name, centred over the pin just above the header body (the names are
        wider than the 2.54 mm pitch, so they sit in two staggered rows), and `FAN n` stands beside the header."""
        texts = [t for t in drawings(self.board) if t.GetClass() == "PCB_TEXT" and t.GetLayer() == pcbnew.F_SilkS]
        for n, ref in enumerate(("J3", "J4", "J5"), 1):
            fp = self.board.FindFootprintByReference(ref)
            cy = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
            top = mm(cy.GetTop())
            for num, name in zip("1234", ("GND", "+12V", "TACH", "PWM")):
                x = mm(fp.FindPadByNumber(num).GetPosition().x)
                near = [t for t in texts if t.GetText() == name and abs(mm(t.GetBoundingBox().GetCenter().x) - x) < 0.3]
                self.assertEqual(len(near), 1, (ref, name))
                bottom = mm(near[0].GetBoundingBox().GetBottom())
                self.assertTrue(top - 3.5 < bottom < top + 0.3, (ref, name, bottom, top))
            fan = [t for t in texts if t.GetText() == f"FAN {n}"]
            self.assertEqual(len(fan), 1, ref)
            c = fan[0].GetBoundingBox().GetCenter()
            self.assertTrue(cy.GetTop() < c.y < cy.GetBottom() and abs(mm(c.x) - mm(cy.GetLeft())) < 2.0, (ref, mm(c.x), mm(c.y)))


if __name__ == "__main__":
    unittest.main()
