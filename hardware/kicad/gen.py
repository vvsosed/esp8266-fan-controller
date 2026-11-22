"""Generate the KiCad project: schematic, board, checks and fab outputs.

    python3 gen.py            # everything, into this directory
    python3 gen.py --quick    # no exports, just the files and the checks

Change the circuit in docs/board/data.py, the geometry in layout.py; never edit the generated files.
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import layout                      # noqa: E402
import netlist                     # noqa: E402
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


def main(argv):
    sch = write_schematic()
    problems = check_schematic(sch)
    for p in problems:
        print(p)
    print(f"schematic: {len(netlist.PARTS)} parts, {len(netlist.NETS)} nets, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
