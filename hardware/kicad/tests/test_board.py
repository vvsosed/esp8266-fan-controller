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
import layout
import netlist


def mm(v):
    return v / 1e6


class BoardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = Path(tempfile.mkdtemp())
        gen.write_all(cls.dir, quick=True)
        cls.board = pcbnew.LoadBoard(str(cls.dir / "fan_controller.kicad_pcb"))
        cls.fps = {fp.GetReference(): fp for fp in cls.board.GetFootprints()}

    def test_outline_and_holes(self):
        drawings = self.board.Drawings()                      # indexed: this SWIG build's iterator is broken
        edge = [drawings[i].Cast() for i in range(len(drawings)) if drawings[i].GetLayer() == pcbnew.Edge_Cuts]
        self.assertEqual(len(edge), 1)
        self.assertEqual((mm(edge[0].GetStart().x), mm(edge[0].GetStart().y)), (0.0, 0.0))
        self.assertEqual((mm(edge[0].GetEnd().x), mm(edge[0].GetEnd().y)), layout.BOARD)
        for ref, (x, y) in layout.HOLES.items():
            fp = self.fps[ref]
            self.assertEqual((mm(fp.GetPosition().x), mm(fp.GetPosition().y)), (x, y))
            self.assertEqual(next(iter(fp.Pads())).GetNetname(), "GND")

    def test_antenna_overhangs(self):
        u1 = self.fps["U1"]
        cy = u1.GetCourtyard(pcbnew.F_CrtYd).BBox()
        self.assertLessEqual(mm(cy.GetTop()), -6.0)
        self.assertTrue(all(mm(p.GetPosition().y) >= 1.0 for p in u1.Pads()))

    def test_module_keepout(self):
        x1, y1, x2, y2 = layout.MODULE_KEEPOUT
        for ref, fp in self.fps.items():
            if ref == "U1":
                continue
            b = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
            self.assertFalse(mm(b.GetLeft()) < x2 and mm(b.GetRight()) > x1 and mm(b.GetTop()) < y2 and mm(b.GetBottom()) > y1, ref)
        self.assertTrue(any(z.GetIsRuleArea() and z.GetDoNotAllowZoneFills() for z in self.board.Zones()))

    def test_fan_headers_same_way(self):
        rots = []
        for ref in ("J3", "J4", "J5"):
            pads = {p.GetNumber(): p.GetPosition() for p in self.fps[ref].Pads()}
            self.assertLess(pads["1"].x, pads["4"].x, ref)
            self.assertEqual(pads["1"].y, pads["4"].y, ref)
            self.assertGreaterEqual(mm(pads["1"].y), 42.0, ref)
            rots.append(self.fps[ref].GetOrientationDegrees())
        self.assertEqual(len(set(rots)), 1)

    def test_q3_tab_clear(self):
        b = self.fps["Q3"].GetCourtyard(pcbnew.F_CrtYd).BBox()
        band = (mm(b.GetLeft()), mm(b.GetBottom()), mm(b.GetRight()), mm(b.GetBottom()) + 3.0)   # the tab side is +y
        for ref, fp in self.fps.items():
            if ref == "Q3":
                continue
            c = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
            self.assertFalse(mm(c.GetLeft()) < band[2] and mm(c.GetRight()) > band[0] and mm(c.GetTop()) < band[3] and mm(c.GetBottom()) > band[1], ref)

    def test_drc_no_placement_errors(self):
        rep = board.drc(self.dir / "fan_controller.kicad_pcb")
        self.assertEqual([v["type"] for v in rep["violations"]], [])     # unconnected items are allowed until the routing task
        self.assertEqual(rep["schematic_parity"], [])

    def test_pads_have_nets(self):
        for ref, part in netlist.PARTS.items():
            for pad in self.fps[ref].Pads():
                want = part.pins.get(pad.GetNumber())
                if want:
                    self.assertEqual(pad.GetNetname(), want, (ref, pad.GetNumber()))


if __name__ == "__main__":
    unittest.main()
