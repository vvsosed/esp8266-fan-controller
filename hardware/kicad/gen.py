"""Generate the KiCad project: schematic, board, checks and fab outputs.

    python3 gen.py            # everything, into this directory
    python3 gen.py --quick    # no exports, just the files and the checks

Change the circuit in docs/board/data.py, the geometry in layout.py; never edit the generated files.
"""
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import board                       # noqa: E402
import layout                      # noqa: E402
import netlist                     # noqa: E402
import project                     # noqa: E402
from schematic import Schematic, erc, exported_nets   # noqa: E402

UPRIGHT = ("Device:R", "Device:C", "Device:Polyfuse")     # pins along y in the library; "Diode:" parts lie along x


def field_positions(lib_id, place):
    """(Reference at, Value at, justify): beside a two-pin part or a transistor, not on its body."""
    G = layout.G
    x, y = place.at
    if lib_id.startswith(UPRIGHT) or lib_id.startswith("Diode:"):
        vertical = (place.rot in (0, 180)) == lib_id.startswith(UPRIGHT)
        if vertical:
            return (x + 2 * G, y - G), (x + 2 * G, y + G), "left"
        return (x, y - 2 * G), (x, y + 2 * G), None
    if lib_id.startswith("Transistor_"):
        dx = 5 * G if lib_id.startswith("Transistor_FET") else 4 * G
        if place.mirror == "y":
            return (x - dx, y - G), (x - dx, y + G), "right"
        return (x + dx, y - G), (x + dx, y + G), "left"
    return None, None, None


def write_schematic(out=HERE / "fan_controller.kicad_sch"):
    sch = Schematic(layout.TITLE)
    for ref, part in netlist.PARTS.items():
        place = layout.SCH_PARTS[ref]
        ref_at, value_at, justify = field_positions(part.lib_id, place)
        sch.add_part(part, place, value_at=value_at, ref_at=ref_at, justify=justify)
    for net, at, rot in layout.SCH_POWER:
        sch.add_power(net, at, rot)
    for at, rot in layout.SCH_FLAGS:
        sch.add_flag(at, rot)
    for net, at, rot in layout.SCH_LABELS:
        sch.add_label(net, at, rot)
    for pts in layout.SCH_WIRES:
        sch.add_wire(pts)
    for at in layout.SCH_JUNCTIONS:
        sch.add_junction(at)
    for s, at in layout.SCH_TEXT:
        sch.add_text(s, at)
    for ref, part in netlist.PARTS.items():
        for number, net in part.pins.items():
            if net is None:
                sch.add_no_connect(sch.pin(ref, number))
    sch.write(out)
    return out


def check_schematic(path):
    """ERC errors and the difference between the sheet's nets and the derived netlist."""
    problems = [f"ERC {v['type']}: {v['description']} at {v.get('items', [{}])[0].get('pos')}" for v in erc(path)]
    nets = exported_nets(path)
    for net in sorted(set(nets) | set(netlist.NETS)):
        a, b = nets.get(net, set()), netlist.NETS.get(net, set())
        if a != b:
            problems.append(f"net {net}: sheet has {sorted(a - b)} extra, misses {sorted(b - a)}")
    return problems


def write_board(out=HERE / "fan_controller.kicad_pcb"):
    b = board.build(netlist.PARTS, netlist.NETS, layout)
    board.save(b, out)
    return out


GERBER_LAYERS = "F.Cu,B.Cu,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts"
OUTPUTS = ("schematic.pdf", "schematic.svg", "bom.csv", "gerbers.zip", "board-top.png", "board-bottom.png", "board-copper.svg",
           "erc.txt", "drc.txt")
# kicad-cli stamps its outputs with the time it ran; the title block's date goes there instead, so a rerun gives the same bytes
STAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:[+-]\d{2}:\d{2}|Z)?|(?<=date )\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}")
PDF_STAMP = re.compile(rb"D:\d{4}:\d{2}:\d{2}:\d{2}:\d{2}:\d{2}")


def _cli(*args):
    r = subprocess.run([board.KICAD_CLI, *map(str, args)], capture_output=True, text=True)
    if r.returncode != 0:
        noise = ("assert", "property.h", "Debug:")
        raise RuntimeError("kicad-cli " + " ".join(map(str, args[:3])) + " failed:\n"
                           + "\n".join(l for l in (r.stdout + r.stderr).splitlines() if not any(n in l for n in noise)))


def _undate(path):
    date = layout.TITLE["date"]
    if path.suffix == ".pdf":
        pdf = PDF_STAMP.sub(("D:" + date.replace("-", ":") + ":00:00:00").encode(), path.read_bytes())    # same length: offsets hold
        path.write_bytes(pdf)
        return
    text = path.read_text(encoding="utf-8", errors="surrogateescape")
    path.write_text(STAMP.sub(date, text), encoding="utf-8", errors="surrogateescape")


def check(out):
    """ERC errors, the sheet's nets against the derived netlist, DRC errors, open connections and schematic parity.
    Writes out/erc.txt and out/drc.txt (every severity, to read); returns the problems, empty when all is clean."""
    out = Path(out)
    o = out / "out"
    o.mkdir(exist_ok=True)
    sch, pcb = out / "fan_controller.kicad_sch", out / "fan_controller.kicad_pcb"
    problems = check_schematic(sch)
    rep = board.drc(pcb)
    problems += [f"DRC {v['type']}: {v['description']} at {v['items'][0]['pos']}" for v in rep["violations"]]
    problems += ["open: " + " <-> ".join(i["description"] for i in v["items"]) for v in rep["unconnected_items"]]
    problems += [f"parity {v['type']}: {v['description']}" for v in rep["schematic_parity"]]
    _cli("sch", "erc", "--format", "report", "--severity-all", "-o", o / "erc.txt", sch)
    _cli("pcb", "drc", "--format", "report", "--schematic-parity", "--refill-zones", "--severity-all", "-o", o / "drc.txt", pcb)
    _undate(o / "erc.txt")
    _undate(o / "drc.txt")
    return problems


def export(out):
    """The fab files into out/: Gerbers + drill (zipped, fixed timestamps), BOM, PDF and SVG schematic, renders, copper SVG."""
    out = Path(out)
    o = out / "out"
    g = o / "gerbers"
    shutil.rmtree(g, ignore_errors=True)
    g.mkdir(parents=True)
    sch, pcb = out / "fan_controller.kicad_sch", out / "fan_controller.kicad_pcb"
    _cli("sch", "export", "pdf", "-o", o / "schematic.pdf", sch)
    with tempfile.TemporaryDirectory() as d:                                  # the SVG export names its file after the sheet
        _cli("sch", "export", "svg", "-o", d, sch)
        shutil.move(next(Path(d).glob("*.svg")), o / "schematic.svg")
    _cli("sch", "export", "bom", "-o", o / "bom.csv", "--fields", "Reference,Value,Footprint,${QUANTITY}",
         "--labels", "Refs,Value,Footprint,Qty", "--group-by", "Value,Footprint", "--exclude-dnp", sch)
    _cli("pcb", "export", "gerbers", "-o", str(g) + "/", "--layers", GERBER_LAYERS, "--subtract-soldermask", pcb)
    _cli("pcb", "export", "drill", "-o", str(g) + "/", "--format", "excellon", "--excellon-units", "mm",
         "--generate-map", "--map-format", "gerberx2", pcb)
    for f in g.iterdir():
        _undate(f)
    y, m, d = (int(v) for v in layout.TITLE["date"].split("-"))
    with zipfile.ZipFile(o / "gerbers.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(g.iterdir()):
            z.writestr(zipfile.ZipInfo(f.name, (y, m, d, 0, 0, 0)), f.read_bytes(), zipfile.ZIP_DEFLATED)
    for side in ("top", "bottom"):             # basic quality: the ray-traced "high" differs in a few pixels on every run
        _cli("pcb", "render", "--side", side, "--quality", "basic", "--width", "1600", "--height", "1200",
             "-o", o / f"board-{side}.png", pcb)
    _cli("pcb", "export", "svg", "--layers", "F.Cu,B.Cu,F.SilkS,Edge.Cuts", "--page-size-mode", "2", "--exclude-drawing-sheet",
         "-o", o / "board-copper.svg", pcb)
    for name in ("schematic.pdf", "schematic.svg", "board-copper.svg"):
        _undate(o / name)


def write_all(out=HERE, quick=False):
    """Project files, schematic and board into `out`, then the checks and, unless quick, the fab exports.
    Returns the problems the checks found (empty = clean)."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    project.write_project(out)
    if out.resolve() != HERE:                                  # the project's own library next to the files
        shutil.copy(HERE / "fan_controller.kicad_sym", out)
        shutil.copytree(HERE / "fan_controller.pretty", out / "fan_controller.pretty", dirs_exist_ok=True)
    write_schematic(out / "fan_controller.kicad_sch")
    write_board(out / "fan_controller.kicad_pcb")
    problems = check(out)
    if not quick:
        export(out)
    return problems


def main(argv):
    quick = "--quick" in argv
    problems = write_all(HERE, quick)
    for p in problems:
        print(p)
    state = "clean" if not problems else f"{len(problems)} problem{'s' if len(problems) > 1 else ''}"
    print(f"{len(netlist.PARTS)} parts, {len(netlist.NETS)} nets: {state}" + ("" if quick else "; fab files in out/"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
