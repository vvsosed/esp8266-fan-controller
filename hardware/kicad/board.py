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


def _point(board, pt, net):
    """A route point: (x, y) in mm, or "REF.PAD" for a pad centre, which must belong to `net`."""
    if isinstance(pt, str):
        ref, num = pt.split(".")
        fp = board.FindFootprintByReference(ref)
        pad = fp.FindPadByNumber(num) if fp else None
        if pad is None:
            raise KeyError(pt)
        if pad.GetNetname() != net:
            raise ValueError(f"{pt} is on {pad.GetNetname() or 'no net'}, not {net}")
        return pad.GetPosition()
    return at(*pt)


def add_tracks(board, layout, netinfo):
    """layout.ROUTES: (net, layer, points[, width]); layout.VIAS: (net, (x, y)). Width from layout.WIDTH, else 0.3."""
    layers = {"F.Cu": pcbnew.F_Cu, "B.Cu": pcbnew.B_Cu}
    for route in layout.ROUTES:
        net, layer, points = route[:3]
        width = route[3] if len(route) > 3 else layout.WIDTH.get(net, layout.TRACK_WIDTH)
        pts = [_point(board, p, net) for p in points]
        for a, b in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(a)
            t.SetEnd(b)
            t.SetWidth(mm(width))
            t.SetLayer(layers[layer])
            t.SetNet(netinfo[net])
            board.Add(t)
    for net, (x, y) in layout.VIAS:
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(at(x, y))
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        try:
            v.SetWidth(mm(layout.VIA[0]))
        except TypeError:                                      # KiCad 10 takes the layer too
            v.SetWidth(pcbnew.PADSTACK.ALL_LAYERS, mm(layout.VIA[0]))
        v.SetDrill(mm(layout.VIA[1]))
        v.SetNet(netinfo[net])
        board.Add(v)


KIID_SEED = 1       # pcbnew draws every item's identifier from one generator; seeded, the file comes out the same each run


def build(parts, nets, layout):
    for name in sorted({p.footprint for p in parts.values()}):   # warm pcbnew's footprint cache first: a library load
        load_footprint(name)                                       # draws identifiers too, and only on the first load
    pcbnew.KIID.SeedGenerator(KIID_SEED)
    board = pcbnew.CreateEmptyBoard()
    _settings(board)
    netinfo = {}
    for name in sorted(nets):
        netinfo[name] = pcbnew.NETINFO_ITEM(board, name)
        board.Add(netinfo[name])
    _outline(board, layout.BOARD)
    for ref, part in parts.items():
        _place(board, part, layout.PCB_PARTS[ref], netinfo, layout.REF_AT.get(ref, "above"))
    add_tracks(board, layout, netinfo)
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


def drc(path, severity="error"):
    """kicad-cli's DRC report as a dict: 'violations', 'unconnected_items', 'schematic_parity'. severity "all" adds warnings."""
    out = Path(path).with_suffix(".drc.json")
    subprocess.run([KICAD_CLI, "pcb", "drc", "--format", "json", "--schematic-parity", "--refill-zones", "--severity-" + severity,
                    "-o", str(out), str(path)], check=False, capture_output=True, text=True)
    rep = json.loads(out.read_text(encoding="utf-8"))
    out.unlink()
    return rep
