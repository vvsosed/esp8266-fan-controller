"""Board geometry and the placement, as data. gen.py draws and tabulates it."""
import string

COLS = string.ascii_uppercase            # A..Z = 26 columns, 2.54 mm pitch
ROWS = range(1, 19)                      # 1..18

def holes():
    """Every plated hole on the diymore 5x7 ESP-12 board, from the photo."""
    h = set()
    for r in range(1, 13):               # left block A-F and right block T-Z
        for c in "ABCDEF" "TUVWXYZ":
            h.add(f"{c}{r}")
    for r in range(13, 19):              # bottom strip
        for c in "ABCDEF" "HIJKLMNOPQR" "TUVWXYZ":
            h.add(f"{c}{r}")
    for r in (15, 16, 17, 18):
        h.add(f"G{r}")
    for r in (16, 17, 18):
        h.add(f"S{r}")
    for x in ("A1", "Z1", "A18", "Z18",  # corner mounting holes
              "W10", "X10"):             # the relay's COM pad sits here, off grid
        h.discard(x)
    return h

HOLES = holes()
RELAY_PADS = ["U11", "U16", "Z11", "Z16"]   # relay footprint pads; U11/U16 sit 0.5 mm right of the grid

# Module pins -> the hole each one is routed to
PINS = {
    "F3": "RST", "F4": "ADC", "F5": "EN", "F6": "IO16", "F7": "IO14",
    "F8": "IO12", "F9": "IO13", "F10": "3V3",
    "T3": "TXD", "T4": "RXD", "T5": "IO5", "T6": "IO4", "T7": "IO0",
    "T8": "IO2", "T9": "IO15", "T10": "GND",
    "K13": "CS0", "L13": "MISO", "M13": "IO9", "N13": "IO10", "O13": "MOSI", "P13": "SCLK",
}
KEEP_OUT = ["K13", "L13", "M13", "N13", "O13", "P13"]   # flash SPI: never solder
# Holes with a trace to a bare pad of the unused ESP-32 footprint on the back
STUBS = ([f"F{r}" for r in range(2, 13)] + [f"T{r}" for r in range(2, 16)]
         + ["H13", "H14"] + [f"{c}13" for c in "JKLMNOPQR"])

# ---- Components (top side). kind decides the drawing. ----
# res/diode: standing, lead in the first hole, body above it, far lead bent into the second
# to92v: three pins down a column; to220: three pins along a row; tact: four pins
# buck: the Mini-360 on four holes, IN+ IN− OUT+ OUT− in that order
PARTS = [
    ("U1", "module", "ESP-12F", {}, "Solder on the footprint, antenna toward the top edge"),
    ("R1", "res", "10 kΩ", {"F3": "RST", "E3": "3V3"}, "RST pull-up"),
    ("R2", "res", "10 kΩ", {"F5": "EN", "E5": "3V3"}, "EN (CH_PD) pull-up; the module won't start without it"),
    ("R3", "res", "10 kΩ", {"F6": "IO16", "E6": "3V3"}, "IO16 pull-up: keeps the 12 V switch on during boot and reset"),
    ("R4", "res", "10 kΩ", {"F7": "IO14", "E7": "3V3"}, "Fan 3 tach pull-up"),
    ("R5", "res", "1 kΩ", {"E13": "IO12", "E12": "Q1 base"}, "PWM base resistor, standing below C1; IO12 reaches E13 by wire"),
    ("R6", "res", "4.7 kΩ", {"D11": "IO16", "C11": "Q2 base"}, "Switch base resistor; IO16 reaches D11 by wire. Kept away from the RST button: a RST–IO16 bridge would reset the board every time the fans switch off"),
    ("R7", "res", "10 kΩ", {"T5": "IO5", "U5": "3V3"}, "Fan 1 tach pull-up"),
    ("R8", "res", "10 kΩ", {"T6": "IO4", "U6": "3V3"}, "Fan 2 tach pull-up"),
    ("R9", "res", "10 kΩ", {"T7": "IO0", "U7": "3V3"}, "IO0 pull-up: boots from flash"),
    ("R10", "res", "4.7 kΩ", {"T8": "IO2", "U8": "3V3"}, "1-Wire pull-up; also holds IO2 high at boot"),
    ("R11", "res", "10 kΩ", {"T9": "IO15", "U10": "GND"}, "IO15 pull-down: boots from flash"),
    ("R12", "res", "10 kΩ", {"G15": "gate", "H15": "+12 V"}, "MOSFET gate to source, standing in G15 one hole clear of Q3's body; the gate reaches G15 by wire from L14. Its bent upper lead drops into H15 right at Q3's rear corner, where the metal tab (drain) is: slide a sleeve of insulation over that lead, bring it into H15 slanting in from the G side, and keep it off the tab. A touch there joins drain to source and quietly defeats the switch"),
    ("C1", "cap", "100 nF", {"F11": "3V3", "F12": "GND"}, "Ceramic, 2.54 mm pitch, right under the module's 3V3 pin; a 5 mm-pitch part would lean on R5 below it"),
    ("U2", "buck", "Mini-360", {"W5": "+12 V", "Z5": "GND", "W11": "3V3", "Z11": "GND"},
     "DSN Mini-360 3 A buck (MP2307), trimmed to 3.3 V on the bench before it goes in. IN end toward the top edge: IN+ in W5, IN− in Z5, OUT+ in W11, OUT− in Z11, so both GND pins sit in the Z ground ring. Check that before the ring is soldered: component side up, IN end up, the two pads that read 0 Ω to each other are the grounds and must be over column Z. If they are over W, turn the module round: IN+ is then at W11 and OUT+ at W5, so feed 12 V to W11 and start the 3.3 V chain from W5 (W5–V5–U5) instead. Its pads are 15.24 mm apart along the module, six pitches, which fits W5–W11, but 9.144 mm across, where W to Z is 7.62 mm: each pad sits 0.76 mm outside its hole, too far for straight header pins. Solder a stiff wire stub (a resistor lead offcut) into each pad, bend each pair 0.76 mm inward and drop the four stubs into the holes. The relay's bare COM pad under it (between W10 and X10) stays empty. Don't touch the trimmer once the ESP-12F is powered"),
    ("D1", "diode", "1N5819", {"P16": "GND", "P17": "+12 V sw"}, "Standing in P16 on the ground row, between the Fan 2 and Fan 3 headers; the stripe end (cathode) bends into P17 on the +12 V sw bus"),
    ("Q1", "to92v", "2N3904", {"Y13": "C", "Y14": "B", "Y15": "E"}, "PWM driver. C-B-E from top to bottom, C in Y13: a 2N3904 reads E-B-C with its flat face toward you and the legs down, and with the flat face toward the board's right edge that order runs from the bottom edge up"),
    ("Q2", "to92v", "2N3904", {"V13": "C", "V14": "B", "V15": "E"}, "12 V switch driver; same orientation as Q1, C in V13"),
    ("Q3", "to220", "IRF9540N", {"I14": "S", "J14": "D", "K14": "G"}, "Standing upright, printed face toward the module, metal tab (drain) toward the fan headers. Seen from the printed face with the legs down the legs are 1 G, 2 D, 3 S left to right, as the datasheet numbers them; turned to face the module that puts S in I14 and G in K14. So the flash pin K13 only ever has the 10 kΩ-fed gate beside it, never the raw 12 V, and the tab stands over row 15, where nothing it could touch would be harmed. Leave 3 mm of lead under the body. Before it goes in, lay Kapton over H15–L15 behind it and over H13–P13 and H14 in front: the flash pins and the stubs that its bare leads would otherwise face. Keep it upright; folded toward the fan headers, its tab would lie on the row-16 ground ring"),
    ("SW1", "tact", "RST", {"D2": "RST", "D5": "RST", "B2": "GND", "B5": "GND"}, "6 × 6 mm tact; two taps open the setup AP. Its pins that are joined inside the switch are the pair 6.5 mm apart: set those along the column, D2–D5 and B2–B5, so pressing it joins D to B. Turned 90°, it would hold RST at ground for good"),
    ("SW2", "tact", "FLASH", {"D7": "IO0", "D10": "IO0", "B7": "GND", "B10": "GND"}, "6 × 6 mm tact under the RST button, joined pairs along the column again, D7–D10 and B7–B10; hold it while tapping RST for the first serial flash"),
    ("J1", "hdr3", "serial", {"T2": "TX", "U2": "RX", "V2": "GND"}, "3-pin header; TX is the module's TXD and goes to the adapter's RX"),
    ("J2", "term", "12 V in", {"B13": "+12 V", "B15": "GND"}, "5.08 mm screw terminal, wire entry toward the left edge"),
    ("J3", "fan", "Fan 1", {"D18": "GND", "E18": "+12 V sw", "F18": "tach 1", "G18": "PWM"}, "4-pin fan header, latch toward the bottom edge, pin 1 (GND) on the left. A genuine Molex 47053 housing has a locator peg behind pin 2 that misses this grid: clip it, or use the peg-less clones. The plug hangs about 10 mm past the edge"),
    ("J4", "fan", "Fan 2", {"K18": "GND", "L18": "+12 V sw", "M18": "tach 2", "N18": "PWM"}, "4-pin fan header, same orientation as Fan 1"),
    ("J5", "fan", "Fan 3", {"R18": "GND", "S18": "+12 V sw", "T18": "tach 3", "U18": "PWM"}, "4-pin fan header"),
    ("J6", "hdr3", "DS18B20", {"W17": "3V3", "X17": "DQ", "Y17": "GND"}, "3-pin header for the sensor lead: VDD, DQ, GND left to right. Mark pin 1: a reversed plug swaps the sensor's supply. GND sits in Y17, the pin nearest the Z18 mounting hole, so a screw head that reaches it does no harm; a nylon screw or an M3 socket-head screw there keeps clear of it anyway"),
]

# ---- Back side: bare-wire chains (adjacent holes, bridged) and insulated wires ----
CHAINS = {
    "3V3": [["F10", "E10"], ["F10", "F11"], ["E3", "E4", "E5", "E6", "E7", "E8", "E9", "E10"],
            ["U5", "U6", "U7", "U8"], ["U8", "V8"], ["W11", "V11", "V10", "V9", "V8"]],
    "GND": [[f"A{r}" for r in range(2, 17)],
            [f"{c}16" for c in COLS],
            [f"Z{r}" for r in range(2, 17)],
            ["T12", "U12", "V12", "W12", "X12", "Y12", "Z12"],
            ["T10", "U10"], ["T10", "T11", "T12"],
            ["B5", "A5"], ["B7", "A7"], ["V2", "W2", "X2", "Y2", "Z2"], ["B15", "A15"],
            ["D18", "D17", "D16"], ["K18", "K17", "K16"], ["R18", "R17", "R16"], ["Y17", "Y16"],
            ["V15", "V16"], ["Y15", "Y16"]],
    "TX": [["T3", "T2"]],
    "RX": [["T4", "U4", "U3", "U2"]],
    "gate": [["K14", "L14"]],
    "+12 V": [["I14", "I15"], ["I15", "H15"], ["B13", "C13"]],
    "+12 V sw": [["O17", "P17"], ["P17", "Q17"]],
}

# Insulated wires: (from, to, net, note).
WIRES = [
    ("D5", "F3", "RST", "thin"),
    ("T7", "D7", "IO0", "thin, under the module"),
    ("W11", "F11", "3V3", "0.25 mm², along row 11 just below the module; it carries the ESP's current"),
    ("F12", "T11", "GND", "thin, under the module; C1's only ground, keep it"),
    ("F6", "D11", "IO16", "thin"),
    ("C11", "V14", "Q2 base", "thin, under the module"),
    ("F8", "E13", "IO12", "thin"),
    ("E12", "Y14", "Q1 base", "thin, under the module"),
    ("V13", "L14", "gate", "thin"),
    ("L14", "G15", "gate", "thin, under Q3"),
    ("B13", "I15", "+12 V", "thick"),
    ("C13", "W5", "+12 V", "thick, across the back under the module"),
    ("J14", "O17", "+12 V sw", "thick; O17 also takes the Fan 1 wire, twist the two ends together"),
    ("O17", "E18", "+12 V sw", "thick"),
    ("P17", "L18", "+12 V sw", "thick"),
    ("Q17", "S18", "+12 V sw", "thick"),
    ("Y13", "U18", "PWM", "thin"),
    ("U18", "N18", "PWM", "thin"),
    ("N18", "G18", "PWM", "thin"),
    ("F18", "T5", "tach 1", "thin, under the module"),
    ("M18", "T6", "tach 2", "thin, under the module"),
    ("T18", "F7", "tach 3", "thin, under the module"),
    ("X17", "T8", "DQ", "thin"),
    ("W17", "V8", "3V3", "thin"),
]

NET_COLOR = {
    "3V3": "#d9480f", "GND": "#1c7ed6", "+12 V": "#c92a2a", "+12 V sw": "#e8590c",
    "PWM": "#2b8a3e", "tach 1": "#5f3dc4", "tach 2": "#7048e8", "tach 3": "#9775fa",
    "DQ": "#0b7285", "IO16": "#a61e4d", "IO12": "#2f9e44", "gate": "#862e9c", "Q1 base": "#5c940d", "Q2 base": "#d6336c",
    "RST": "#495057", "IO0": "#495057", "TX": "#868e96", "RX": "#868e96",
}
