"""The controller's netlist, derived from the perfboard plan in docs/board/data.py.

`docs/board/gen.py`'s `check()` resolves every hole of the perfboard to a net; this module maps each
part's holes to KiCad pin numbers, renames the nets, splits the 12 V input for the fuse and adds the
fuse, the reverse-polarity diode and the mounting holes. Schematic and PCB are both built from
`PARTS` and `NETS`, so a circuit change is made in data.py and flows to all three.
"""
import importlib.util
import sys
from dataclasses import dataclass
from pathlib import Path

BOARD_DIR = Path(__file__).resolve().parents[2] / "docs" / "board"


def _load_perfboard():
    """docs/board/gen.py, under a name that cannot clash with this directory's gen.py."""
    sys.path.insert(0, str(BOARD_DIR))
    try:
        spec = importlib.util.spec_from_file_location("perfboard_gen", BOARD_DIR / "gen.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        sys.path.remove(str(BOARD_DIR))
    return mod


PERFBOARD = _load_perfboard()


@dataclass(frozen=True)
class Part:
    ref: str
    lib_id: str
    footprint: str
    value: str
    pins: dict          # KiCad pin number -> net name, None = no connect


POWER_NETS = ("+12V_IN", "+12V", "+12V_SW", "3V3", "GND")

NET_NAME = {"3V3": "3V3", "GND": "GND", "+12 V": "+12V", "+12 V sw": "+12V_SW", "PWM": "PWM",
            "tach 1": "TACH1", "tach 2": "TACH2", "tach 3": "TACH3", "DQ": "DQ", "IO16": "IO16", "IO12": "IO12",
            "gate": "GATE", "Q1 base": "Q1_B", "Q2 base": "Q2_B", "IO13": "IO13", "flow": "FLOW", "Q4 base": "Q4_B",
            "RST": "RST", "IO0": "IO0", "TX": "TX", "RX": "RX", "EN": "EN", "IO15": "IO15"}

VALUE = {"10 kΩ": "10k", "4.7 kΩ": "4.7k", "1 kΩ": "1k", "100 nF": "100n"}

MODULE_PIN = {"RST": "1", "ADC": "2", "EN": "3", "IO16": "4", "IO14": "5", "IO12": "6", "IO13": "7", "3V3": "8",
              "CS0": "9", "MISO": "10", "IO9": "11", "IO10": "12", "MOSI": "13", "SCLK": "14", "GND": "15",
              "IO15": "16", "IO2": "17", "IO0": "18", "IO4": "19", "IO5": "20", "RXD": "21", "TXD": "22"}

# kind -> (symbol, footprint, KiCad pin number for each hole in data.py's order)
KIND = {
    "res": ("Device:R", "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P7.62mm_Horizontal", ["1", "2"]),
    "cap": ("Device:C", "Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P2.50mm", ["1", "2"]),
    "diode": ("Diode:1N5819", "Diode_THT:D_DO-41_SOD81_P7.62mm_Horizontal", ["2", "1"]),     # anode hole first
    "to92v": ("Transistor_BJT:2N3904", "Package_TO_SOT_THT:TO-92_Inline_Wide", ["3", "2", "1"]),   # C, B, E
    "to220": ("Transistor_FET:IRF9540N", "Package_TO_SOT_THT:TO-220-3_Vertical", ["3", "2", "1"]),   # S, D, G
    "tact": ("Switch:SW_Push", "Button_Switch_THT:SW_PUSH_6mm", ["1", "1", "2", "2"]),
    "hdr3": ("Connector_Generic:Conn_01x03", "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical", ["1", "2", "3"]),
    "fan": ("Connector_Generic:Conn_01x04", "Connector_Molex:Molex_KK-254_AE-6410-04A_1x04_P2.54mm_Vertical", ["1", "2", "3", "4"]),
    "term": ("Connector:Screw_Terminal_01x02", "TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal", ["1", "2"]),
    "buck": ("fan_controller:Mini-360", "fan_controller:Mini-360", ["1", "2", "3", "4"]),
}
FOOTPRINT = {"R3": "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P2.54mm_Vertical"}   # standing: the only one that fits below J8's labels

ADDED = [
    Part("F1", "Device:Polyfuse", "fan_controller:Polyfuse_Radial_P5.1mm", "MF-R250", {"1": "+12V_IN", "2": "+12V"}),
    Part("D2", "Diode:1N5401", "Diode_THT:D_DO-201AD_P12.70mm_Horizontal", "1N5401", {"1": "+12V", "2": "GND"}),
] + [Part(f"H{i}", "Mechanical:MountingHole_Pad", "MountingHole:MountingHole_3.2mm_M3_DIN965_Pad", "M3", {"1": "GND"})
     for i in range(1, 5)]


def build():
    """(parts by reference, net -> {(ref, pin)}) for the whole board."""
    bad, hole_net = PERFBOARD.check()
    if bad:
        raise ValueError("docs/board/data.py has problems: " + "; ".join(bad))
    parts = {}
    for ref, kind, val, holes, _note in PERFBOARD.PARTS:
        if kind == "module":
            lib_id, fp = "RF_Module:ESP-12F", "RF_Module:ESP-12E"
            pins = {MODULE_PIN[name]: NET_NAME[hole_net[h]] if h in hole_net else None for h, name in PERFBOARD.PINS.items()}
        else:
            lib_id, fp, numbers = KIND[kind]
            fp = FOOTPRINT.get(ref, fp)
            pins = {}
            for h, number in zip(holes, numbers):
                if h not in hole_net:
                    raise KeyError(f"{ref}: hole {h} has no net")
                net = NET_NAME[hole_net[h]]
                if pins.get(number, net) != net:
                    raise ValueError(f"{ref}: pin {number} on {pins[number]} and {net}")
                pins[number] = net
        if ref == "J2":
            pins["1"] = "+12V_IN"
        parts[ref] = Part(ref, lib_id, fp, VALUE.get(val, val), dict(sorted(pins.items(), key=lambda kv: int(kv[0]))))
    for p in ADDED:
        parts[p.ref] = p
    nets = {}
    for p in parts.values():
        for number, net in p.pins.items():
            if net is not None:
                nets.setdefault(net, set()).add((p.ref, number))
    return parts, nets


PARTS, NETS = build()
