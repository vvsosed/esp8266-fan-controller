"""The PCB through pcbnew: outline, holes, footprints, ground zones, silkscreen; and the DRC runner."""
import json
import subprocess
from pathlib import Path

import pcbnew

import ids
import project

FOOTPRINT_DIR = Path("/usr/share/kicad/footprints")
PROJECT_FP = Path(__file__).resolve().parent / "fan_controller.pretty"
KICAD_CLI = "kicad-cli"
SHEET = "fan_controller.kicad_sch"


def mm(v):
    return pcbnew.FromMM(v)


def at(x, y):
    return pcbnew.VECTOR2I_MM(x, y)


def load_footprint(lib_fp):
    lib, name = lib_fp.split(":")
    d = PROJECT_FP if lib == "fan_controller" else FOOTPRINT_DIR / f"{lib}.pretty"
    fp = pcbnew.FootprintLoad(str(d), name)
    if fp is None:
        raise FileNotFoundError(lib_fp)
    return fp


def _settings(board):
    ds = board.GetDesignSettings()
    ds.SetCopperLayerCount(2)
    r = project.RULES
    ds.m_MinClearance = mm(r["clearance"])
    ds.m_TrackMinWidth = mm(r["min_track"])
    ds.m_ViasMinSize = mm(r["via"])
    ds.m_MinThroughDrill = mm(r["drill"])
    ds.m_CopperEdgeClearance = mm(r["edge"])
    nc = ds.m_NetSettings.GetDefaultNetclass()
    nc.SetClearance(mm(r["clearance"]))
    nc.SetTrackWidth(mm(r["track"]))
    nc.SetViaDiameter(mm(r["via"]))
    nc.SetViaDrill(mm(r["drill"]))


def _outline(board, size):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_RECT)
    s.SetStart(at(0, 0))
    s.SetEnd(at(*size))
    s.SetLayer(pcbnew.Edge_Cuts)
    s.SetWidth(mm(0.1))
    board.Add(s)


def _place(board, part, place, netinfo, ref_at="above"):
    x, y, rot = place
    fp = load_footprint(part.footprint)
    fp.SetReference(part.ref)
    fp.SetValue(part.value)
    fp.SetPosition(at(x, y))
    fp.SetOrientationDegrees(rot)
    fp.SetPath(pcbnew.KIID_PATH(ids.path(part.ref)))
    fp.SetSheetfile(SHEET)
    fp.SetSheetname("Root")
    for pad in fp.Pads():
        net = part.pins.get(pad.GetNumber())
        if net:
            pad.SetNet(netinfo[net])
    _reference(fp, ref_at)
    board.Add(fp)
    return fp


def _reference(fp, spec):
    """The reference designator: 0.8 mm text, centred above the courtyard unless the layout says otherwise."""
    r = fp.Reference()
    r.SetTextSize(pcbnew.VECTOR2I(mm(0.8), mm(0.8)))
    r.SetTextThickness(mm(0.15))
    r.SetKeepUpright(False)
    if spec == "hide":
        r.SetVisible(False)
        return
    if spec == "above":
        fp.BuildCourtyardCaches()
        cy = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
        r.SetPosition(pcbnew.VECTOR2I(cy.GetCenter().x, cy.GetTop() - mm(0.6)))
        r.SetTextAngleDegrees(0)
        return
    x, y, rot = spec
    r.SetPosition(at(x, y))
    r.SetTextAngleDegrees(rot)


def _rect(zone, x1, y1, x2, y2):
    o = zone.Outline()
    o.NewOutline()
    for px, py in ((x1, y1), (x2, y1), (x2, y2), (x1, y2)):
        o.Append(mm(px), mm(py))


def _zones(board, layout, gnd):
    w, h = layout.BOARD
    i = layout.ZONE_INSET
    for layer, name in ((pcbnew.F_Cu, "GND top"), (pcbnew.B_Cu, "GND bottom")):
        z = pcbnew.ZONE(board)
        z.SetLayer(layer)
        z.SetNet(gnd)
        z.SetZoneName(name)
        z.SetMinThickness(mm(0.25))
        _rect(z, i, i, w - i, h - i)
        board.Add(z)
    keep = pcbnew.ZONE(board)
    keep.SetIsRuleArea(True)
    keep.SetDoNotAllowZoneFills(True)
    keep.SetDoNotAllowTracks(False)
    keep.SetDoNotAllowVias(False)
    keep.SetDoNotAllowPads(False)
    keep.SetDoNotAllowFootprints(False)
    keep.SetLayerSet(pcbnew.LSET.AllCuMask(2))
    keep.SetZoneName("ESP-12F keep-out")
    _rect(keep, *layout.MODULE_KEEPOUT)
    board.Add(keep)


def _silk(board, items):
    for item in items:
        text, (x, y), rot, size = item[:4]
        side = item[4] if len(item) > 4 else "F"
        justify = item[5] if len(item) > 5 else None
        t = pcbnew.PCB_TEXT(board)
        t.SetText(text)
        t.SetPosition(at(x, y))
        t.SetLayer(pcbnew.F_SilkS if side == "F" else pcbnew.B_SilkS)
        t.SetMirrored(side == "B")
        t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
        t.SetTextThickness(mm(max(0.15, size * 0.15)))
        t.SetTextAngleDegrees(rot)
        if justify == "L":
            t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_LEFT)
        elif justify == "R":
            t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_RIGHT)
        board.Add(t)


def build(parts, nets, layout):
    board = pcbnew.CreateEmptyBoard()
    _settings(board)
    netinfo = {}
    for name in sorted(nets):
        netinfo[name] = pcbnew.NETINFO_ITEM(board, name)
        board.Add(netinfo[name])
    _outline(board, layout.BOARD)
    for ref, part in parts.items():
        _place(board, part, layout.PCB_PARTS[ref], netinfo, layout.REF_AT.get(ref, "above"))
    _zones(board, layout, netinfo["GND"])
    _silk(board, layout.SILK)
    tb = board.GetTitleBlock()
    tb.SetTitle(layout.TITLE["title"])
    tb.SetRevision(layout.TITLE["rev"])
    tb.SetDate(layout.TITLE["date"])
    tb.SetComment(0, layout.TITLE["comment1"])
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    return board


def save(board, path):
    pcbnew.SaveBoard(str(path), board)


def drc(path):
    """kicad-cli's DRC report as a dict: 'violations', 'unconnected_items', 'schematic_parity'."""
    out = Path(path).with_suffix(".drc.json")
    subprocess.run([KICAD_CLI, "pcb", "drc", "--format", "json", "--schematic-parity", "--refill-zones", "--severity-error",
                    "-o", str(out), str(path)], check=False, capture_output=True, text=True)
    rep = json.loads(out.read_text(encoding="utf-8"))
    out.unlink()
    return rep
