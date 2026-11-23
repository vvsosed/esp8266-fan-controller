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


    def test_terminal_wire_entry_faces_edge(self):
        """J2 takes its wires from the board's left edge. KiCad's Phoenix footprints put the pin-1 chamfer on the
        wire-entry face, so that chamfer must sit on the edge side of the pads, not toward the fuse."""
        j2 = self.fps["J2"]
        items = j2.GraphicalItems()
        fab = [d for d in (items[i].Cast() for i in range(len(items)))
               if d.GetClass() == "PCB_SHAPE" and d.GetLayer() == pcbnew.F_Fab and d.GetShape() == pcbnew.SHAPE_T_SEGMENT]
        chamfer = [d for d in fab if mm(abs(d.GetEnd().x - d.GetStart().x)) < 1.0 and mm(abs(d.GetEnd().y - d.GetStart().y)) < 1.0]
        self.assertEqual(len(chamfer), 1)
        mid_x = mm(chamfer[0].GetStart().x + chamfer[0].GetEnd().x) / 2
        self.assertLess(mid_x, mm(j2.FindPadByNumber("1").GetPosition().x))

    def test_no_front_track_crosses_castellations_between_pads(self):
        """Only a pad's own exit may cross the module's pad lines on the front: a track passing between two
        castellations is where solder from the module's edge bridges onto it."""
        pads = list(self.fps["U1"].Pads())
        groups = []
        for key in (lambda p: p.GetPosition().x, lambda p: p.GetPosition().y):
            by = {}
            for p in pads:
                by.setdefault(key(p), []).append(p)
            groups += [g for g in by.values() if len(g) >= 3]
        self.assertEqual(len(groups), 3)                                   # two columns and the bottom row
        tracks = self.board.Tracks()
        for t in (tracks[i].Cast() for i in range(len(tracks))):
            if t.GetClass() != "PCB_TRACK" or t.GetLayer() != pcbnew.F_Cu:
                continue
            a, b = t.GetStart(), t.GetEnd()
            for g in groups:
                column = len({p.GetPosition().x for p in g}) == 1
                c = g[0].GetPosition().x if column else g[0].GetPosition().y
                lo, hi = (a.x, b.x) if column else (a.y, b.y)
                if not min(lo, hi) < c < max(lo, hi):                      # an exit starts on the line: not a crossing
                    continue
                f = (c - lo) / (hi - lo)
                along = a.y + f * (b.y - a.y) if column else a.x + f * (b.x - a.x)
                spans = [((p.GetPosition().y, p.GetBoundingBox().GetHeight() / 2) if column
                          else (p.GetPosition().x, p.GetBoundingBox().GetWidth() / 2)) for p in g]
                if not min(s - h for s, h in spans) <= along <= max(s + h for s, h in spans):
                    continue                                               # beyond the row: it merely passes the module
                self.assertTrue(any(abs(along - s) <= h for s, h in spans), (t.GetNetname(), mm(c), mm(along)))


if __name__ == "__main__":
    unittest.main()
