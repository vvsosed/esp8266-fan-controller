"""Writes a KiCad schematic from parts, placements, wires and labels.

Symbols come from KiCad's stock libraries (and the project library), flattened into the sheet's
lib_symbols the way the editor does. Positions are sheet millimetres, y down; library pin offsets
are y up, so `pin_xy()` flips, mirrors and rotates them to find where a placed pin's end lands.
"""
import copy
import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import ids
from sexp import Sym, dump, find, find_all, parse

SYMBOL_DIR = Path("/usr/share/kicad/symbols")
PROJECT_SYM = Path(__file__).resolve().parent / "fan_controller.kicad_sym"
KICAD_CLI = "kicad-cli"
POWER_LIB = {"GND": "power:GND", "3V3": "power:+3V3"}      # other nets starting with +12V use power:+12V
_LIBS = {}


def _lib(lib):
    if lib not in _LIBS:
        path = PROJECT_SYM if lib == "fan_controller" else SYMBOL_DIR / f"{lib}.kicad_sym"
        _LIBS[lib] = parse(path.read_text(encoding="utf-8"))
    return _LIBS[lib]


def _raw_symbol(lib, name):
    for s in find_all(_lib(lib), "symbol"):
        if s[1] == name:
            return s
    raise KeyError(f"{lib}:{name}")


def load_symbol(lib_id):
    """The flattened `(symbol "Lib:Name" ...)` node for a schematic's lib_symbols."""
    lib, name = lib_id.split(":")
    child = _raw_symbol(lib, name)
    ext = find(child, "extends")
    if ext:
        parent = copy.deepcopy(_raw_symbol(lib, ext[1]))
        parent_name = ext[1]
        own = {p[1]: p for p in find_all(child, "property")}
        node = [x for x in parent if not (isinstance(x, list) and x and x[0] == Sym("property") and x[1] in own)]
        # child properties go where the parent's were: after the header atoms and flags, before the sub-units
        first_unit = next(i for i, x in enumerate(node) if isinstance(x, list) and x and x[0] == Sym("symbol"))
        node[first_unit:first_unit] = [copy.deepcopy(own[k]) for k in own]
    else:
        node = copy.deepcopy(child)
        parent_name = name
    node[1] = lib_id
    for u in find_all(node, "symbol"):
        if u[1].startswith(parent_name + "_"):
            u[1] = name + u[1][len(parent_name):]
    return [x for x in node if not (isinstance(x, list) and x and x[0] == Sym("extends"))]


def pin_offsets(symbol):
    """pin number -> (x, y, angle) of the pin's connection point, library coordinates (y up)."""
    out = {}
    for u in find_all(symbol, "symbol"):
        for p in find_all(u, "pin"):
            at = find(p, "at")
            out[find(p, "number")[1]] = (float(at[1]), float(at[2]), int(float(at[3])))
    return out


def _properties(symbol):
    """property name -> (value, (x, y, angle), hidden) from a library symbol."""
    out = {}
    for p in find_all(symbol, "property"):
        at = find(p, "at")
        out[p[1]] = (p[2], (float(at[1]), float(at[2]), int(float(at[3]))), find(p, "hide") is not None)
    return out


@dataclass
class Place:
    ref: str
    at: tuple
    rot: int = 0
    mirror: str = None      # "x" or "y", as KiCad names them


def _screen(place, px, py):
    """Library offset -> sheet offset: y flips, then KiCad rotates counter-clockwise on screen and mirrors last."""
    dx, dy = px, -py
    for _ in range((place.rot // 90) % 4):
        dx, dy = dy, -dx
    if place.mirror == "x":
        dy = -dy
    elif place.mirror == "y":
        dx = -dx
    return dx, dy


def pin_xy(place, offset):
    dx, dy = _screen(place, offset[0], offset[1])
    return (round(place.at[0] + dx, 4), round(place.at[1] + dy, 4))


def _fmt(v):
    s = f"{v:.4f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def _at(x, y, rot=0):
    return [Sym("at"), Sym(_fmt(x)), Sym(_fmt(y)), Sym(str(rot))]


def _font(size=1.27):
    return [Sym("effects"), [Sym("font"), [Sym("size"), Sym(_fmt(size)), Sym(_fmt(size))]]]


def _prop(name, value, at, hide=False, justify=None):
    node = [Sym("property"), name, value, _at(*at)]
    if hide:
        node.append([Sym("hide"), Sym("yes")])
    eff = _font()
    if justify:
        eff.append([Sym("justify"), Sym(justify)])
    node.append(eff)
    return node


class Schematic:
    def __init__(self, title):
        self.title = title
        self.lib_symbols = {}        # lib_id -> flattened node
        self.places = {}             # ref -> (Place, lib_id)
        self.items = []              # body items in order
        self.counts = {}

    def _n(self, kind):
        self.counts[kind] = self.counts.get(kind, 0) + 1
        return self.counts[kind]

    def _symbol(self, lib_id):
        if lib_id not in self.lib_symbols:
            self.lib_symbols[lib_id] = load_symbol(lib_id)
        return self.lib_symbols[lib_id]

    def _instance(self, lib_id, ref, value, footprint, place, in_bom, hidden_ref=False, props=None):
        symbol = self._symbol(lib_id)
        libprops = _properties(symbol)
        node = [Sym("symbol"), [Sym("lib_id"), lib_id], _at(place.at[0], place.at[1], place.rot)]
        if place.mirror:
            node.append([Sym("mirror"), Sym(place.mirror)])
        node += [[Sym("unit"), Sym("1")], [Sym("exclude_from_sim"), Sym("no")], [Sym("in_bom"), Sym("yes" if in_bom else "no")],
                 [Sym("on_board"), Sym("yes")], [Sym("dnp"), Sym("no")], [Sym("uuid"), ids.sym(ref)]]
        values = {"Reference": ref, "Value": value, "Footprint": footprint, "Datasheet": libprops.get("Datasheet", ("", None, True))[0],
                  "Description": libprops.get("Description", ("", None, True))[0]}
        for name in ("Reference", "Value", "Footprint", "Datasheet", "Description"):
            lp = libprops.get(name)
            at = pin_xy(place, lp[1]) if lp else place.at
            hide = (lp[2] if lp else True) or (name == "Reference" and hidden_ref)
            if props and name in props:
                at = props[name]
            node.append(_prop(name, values[name], at, hide))
        for number in sorted(pin_offsets(symbol), key=lambda n: (len(n), n)):
            node.append([Sym("pin"), number, [Sym("uuid"), ids.other("pin:" + ref, int(number) if number.isdigit() else 0)]])
        node.append([Sym("instances"), [Sym("project"), "fan_controller", [Sym("path"), "/" + str(ids.ROOT), [Sym("reference"), ref], [Sym("unit"), Sym("1")]]]])
        self.items.append(node)

    def add_part(self, part, place, value_at=None, ref_at=None):
        self.places[part.ref] = (place, part.lib_id)
        props = {}
        if value_at:
            props["Value"] = value_at
        if ref_at:
            props["Reference"] = ref_at
        self._instance(part.lib_id, part.ref, part.value, part.footprint, place, True, props=props)

    def add_power(self, net, at, rot=0):
        lib_id = POWER_LIB.get(net, "power:+12V")
        ref = f"#PWR{self._n('pwr'):03d}"
        self._instance(lib_id, ref, net, "", Place(ref, at, rot), False, hidden_ref=True)

    def add_flag(self, at):
        ref = f"#FLG{self._n('flg'):03d}"
        self._instance("power:PWR_FLAG", ref, "PWR_FLAG", "", Place(ref, at, 0), False, hidden_ref=True)

    def add_label(self, net, at, rot=0, shape="bidirectional"):
        """A global label: its net is named plainly (a local label's would be "/NET" on the board too)."""
        eff = _font()
        eff.append([Sym("justify"), Sym("right" if rot == 180 else "left")])
        self.items.append([Sym("global_label"), net, [Sym("shape"), Sym(shape)], _at(at[0], at[1], rot), eff,
                           [Sym("uuid"), ids.other("label", self._n("label"))]])

    def add_wire(self, pts):
        for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
            if (x1, y1) == (x2, y2):
                continue
            self.items.append([Sym("wire"), [Sym("pts"), [Sym("xy"), Sym(_fmt(x1)), Sym(_fmt(y1))], [Sym("xy"), Sym(_fmt(x2)), Sym(_fmt(y2))]],
                               [Sym("stroke"), [Sym("width"), Sym("0")], [Sym("type"), Sym("default")]],
                               [Sym("uuid"), ids.other("wire", self._n("wire"))]])

    def add_junction(self, at):
        self.items.append([Sym("junction"), _at(at[0], at[1])[:3], [Sym("diameter"), Sym("0")], [Sym("color"), Sym("0"), Sym("0"), Sym("0"), Sym("0")],
                           [Sym("uuid"), ids.other("junction", self._n("junction"))]])

    def add_no_connect(self, at):
        self.items.append([Sym("no_connect"), _at(at[0], at[1])[:3], [Sym("uuid"), ids.other("nc", self._n("nc"))]])

    def add_text(self, text, at, size=2.0, bold=True):
        font = [Sym("font"), [Sym("size"), Sym(_fmt(size)), Sym(_fmt(size))]]
        if bold:
            font.append([Sym("bold"), Sym("yes")])
        self.items.append([Sym("text"), text, [Sym("exclude_from_sim"), Sym("no")], _at(at[0], at[1]),
                           [Sym("effects"), font, [Sym("justify"), Sym("left"), Sym("bottom")]], [Sym("uuid"), ids.other("text", self._n("text"))]])

    def pin(self, ref, number):
        place, lib_id = self.places[ref]
        return pin_xy(place, pin_offsets(self._symbol(lib_id))[number])

    def node(self):
        t = self.title
        tb = [Sym("title_block"), [Sym("title"), t.get("title", "")], [Sym("date"), t.get("date", "")], [Sym("rev"), t.get("rev", "")],
              [Sym("company"), t.get("company", "")]]
        if t.get("comment1"):
            tb.append([Sym("comment"), Sym("1"), t["comment1"]])
        libs = [Sym("lib_symbols")] + [self.lib_symbols[k] for k in sorted(self.lib_symbols)]
        return ([Sym("kicad_sch"), [Sym("version"), Sym("20250114")], [Sym("generator"), "eeschema"], [Sym("generator_version"), "9.0"],
                 [Sym("uuid"), str(ids.ROOT)], [Sym("paper"), "A4"], tb, libs] + self.items
                + [[Sym("sheet_instances"), [Sym("path"), "/", [Sym("page"), "1"]]], [Sym("embedded_fonts"), Sym("no")]])

    def write(self, path):
        path = Path(path)
        path.write_text(dump(self.node()) + "\n", encoding="utf-8")
        run([KICAD_CLI, "sch", "upgrade", str(path)])


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"{' '.join(cmd)} failed ({r.returncode}):\n{r.stdout}\n{r.stderr[-2000:]}")
    return r


def erc(path):
    """Error-level ERC violations of a schematic, as kicad-cli reports them."""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "erc.json"
        subprocess.run([KICAD_CLI, "sch", "erc", "--format", "json", "--severity-error", "-o", str(out), str(path)], capture_output=True, text=True)
        rep = json.loads(out.read_text())
    return [v for sheet in rep.get("sheets", []) for v in sheet.get("violations", [])]


def exported_nets(path):
    """net name -> {(ref, pin)} from kicad-cli's netlist export, power symbols and unconnected pins dropped."""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "net.net"
        run([KICAD_CLI, "sch", "export", "netlist", "--format", "kicadsexpr", "-o", str(out), str(path)])
        node = parse(out.read_text(encoding="utf-8"))
    nets = {}
    for net in find_all(find(node, "nets"), "net"):
        name = find(net, "name")[1]
        if name.startswith("unconnected-"):
            continue
        pins = {(find(n, "ref")[1], find(n, "pin")[1]) for n in find_all(net, "node") if not find(n, "ref")[1].startswith("#")}
        if pins:
            nets[name] = pins
    return nets
