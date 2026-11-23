"""Where everything sits: schematic symbols, wires and labels; PCB placement, routes and silkscreen.

Schematic positions are in grid units of 1.27 mm (KiCad's default grid), so every pin lands on the
grid. Small helpers below fill the tables block by block; they are data, not logic.
"""
from schematic import Place

TITLE = {"title": "ESP8266 fan controller", "rev": "1.0", "date": "2026-11-22", "company": "",
         "comment1": "https://github.com/vvsosed/esp8266-fan-controller"}

G = 1.27


def g(x, y):
    return (round(x * G, 4), round(y * G, 4))


# ---------------------------------------------------------------- schematic
SCH_PARTS = {}        # ref -> Place
SCH_WIRES = []        # [points], mm
SCH_LABELS = []       # (net, at, rot)
SCH_POWER = []        # (net, at, rot)
SCH_FLAGS = []        # (at, rot)
SCH_JUNCTIONS = []    # at
SCH_TEXT = []         # (text, at)


def part(ref, x, y, rot=0, mirror=None):
    SCH_PARTS[ref] = Place(ref, g(x, y), rot, mirror)


def wire(*pts):
    SCH_WIRES.append([g(*p) for p in pts])


def label(net, x, y, rot=0):
    SCH_LABELS.append((net, g(x, y), rot))


def power(net, x, y, rot=0):
    SCH_POWER.append((net, g(x, y), rot))


def flag(x, y, rot=0):
    SCH_FLAGS.append((g(x, y), rot))


def junction(x, y):
    SCH_JUNCTIONS.append(g(x, y))


def text(s, x, y):
    SCH_TEXT.append((s, g(x, y)))


# -- 12 V input: terminal, fuse, reverse diode, buck ----------------------------------
text("12 V input", 10, 12)
part("J2", 14, 20, mirror="y")                 # pins face right: 1 = +12V_IN (18, 20), 2 = GND (18, 22)
wire((18, 20), (20, 20), (22, 20))
flag(20, 20)
label("+12V_IN", 20, 20, 270)
part("F1", 25, 20, 90)                         # pin 1 (22, 20), pin 2 (28, 20)
wire((28, 20), (32, 20), (36, 20), (40, 20), (48, 20))
wire((32, 20), (32, 16))
power("+12V", 32, 16)
flag(36, 20)
junction(32, 20)
junction(36, 20)
junction(40, 20)
part("D2", 40, 23, 270)                        # cathode up on the +12V rail, anode to ground
wire((40, 26), (40, 26))
power("GND", 40, 26)
wire((18, 22), (18, 26))
power("GND", 18, 26)
part("U2", 56, 22)                             # IN+ (48, 20), IN- (48, 24), OUT+ (64, 20), OUT- (64, 24)
wire((48, 24), (48, 28))
power("GND", 48, 28)
wire((64, 24), (64, 28))
power("GND", 64, 28)
wire((64, 20), (68, 20))
power("3V3", 68, 20)

# -- Fans: three headers, GND / +12V_SW / TACH / PWM ----------------------------------
text("Fans", 34, 34)
for ref, Y, tach in (("J3", 48, "TACH1"), ("J4", 62, "TACH2"), ("J5", 76, "TACH3")):
    part(ref, 60, Y)                           # pins face left at x 56: Y-2 GND, Y +12V_SW, Y+2 TACH, Y+4 PWM
    wire((56, Y - 2), (54, Y - 2), (54, Y - 6))
    power("GND", 54, Y - 6, 180)
    if ref == "J3":
        wire((56, Y), (50, Y), (46, Y), (46, Y - 6))
        flag(50, Y)
        junction(50, Y)
    else:
        wire((56, Y), (46, Y), (46, Y - 6))
    power("+12V_SW", 46, Y - 6)
    wire((56, Y + 2), (42, Y + 2))
    label(tach, 42, Y + 2, 180)
    wire((56, Y + 4), (42, Y + 4))
    label("PWM", 42, Y + 4, 180)

# -- Tach pull-ups ------------------------------------------------------------------
text("Tach pull-ups", 70, 36)
for ref, x, tach, drop in (("R7", 74, "TACH1", 52), ("R8", 80, "TACH2", 54), ("R4", 86, "TACH3", 56)):
    part(ref, x, 47, 180)                      # pin 2 (x, 44) to 3V3, pin 1 (x, 50): data.py lists the signal hole first
    wire((x, 50), (x, drop))
    label(tach, x, drop, 180)
wire((74, 44), (74, 42), (80, 42))
wire((80, 42), (86, 42), (86, 44))
wire((80, 44), (80, 42))
junction(80, 42)
power("3V3", 80, 42)

# -- The module ---------------------------------------------------------------------
text("ESP-12F", 100, 44)
part("U1", 118, 72)                            # left pins at x 106, right pins at x 130, VCC (118, 56), GND (118, 86)
for y, net in ((60, "RST"), (64, "EN")):
    wire((106, y), (100, y))
    label(net, 100, y, 180)
for y, net in ((60, "IO0"), (62, "TX"), (64, "DQ"), (66, "RX"), (68, "TACH2"), (70, "TACH1"), (72, "IO12"),
               (74, "IO13"), (76, "TACH3"), (78, "IO15"), (80, "IO16")):
    wire((130, y), (136, y))
    label(net, 136, y)
wire((118, 56), (118, 52), (118, 50))
power("3V3", 118, 50)
wire((118, 52), (140, 52))
junction(118, 52)
part("C1", 143, 52, 90)                        # pin 1 (140, 52), pin 2 (146, 52)
wire((146, 52), (148, 52), (148, 48))
power("GND", 148, 48, 180)                     # up, clear of the switch block's IO16 label
wire((118, 86), (118, 90))
power("GND", 118, 90)

# -- Boot and reset: pull-ups, pull-down, the two buttons ----------------------------
text("Boot and reset", 100, 100)
for ref, x in (("R1", 104), ("R2", 124), ("R9", 136), ("R3", 170)):
    part(ref, x, 109, 180)                     # pin 2 (x, 106) to 3V3, pin 1 (x, 112)
    power("3V3", x, 106)
wire((100, 112), (104, 112), (112, 112), (112, 114))
junction(104, 112)
label("RST", 100, 112, 180)
part("SW1", 112, 118, 270)                     # pin 1 (112, 114), pin 2 (112, 122)
power("GND", 112, 122)
wire((120, 112), (124, 112))
label("EN", 120, 112, 180)
wire((132, 112), (136, 112), (144, 112), (144, 114))
junction(136, 112)
label("IO0", 132, 112, 180)
part("SW2", 144, 118, 270)
power("GND", 144, 122)
part("R11", 158, 115)                          # pin 1 (158, 112), pin 2 (158, 118)
wire((154, 112), (158, 112))
label("IO15", 154, 112, 180)
power("GND", 158, 118)
wire((166, 112), (170, 112))
label("IO16", 166, 112, 180)

# -- Serial header ------------------------------------------------------------------
text("Serial", 34, 106)
part("J1", 56, 116)                            # pins at x 52: 114 TX, 116 RX, 118 GND
wire((52, 114), (46, 114))
label("TX", 46, 114, 180)
wire((52, 116), (46, 116))
label("RX", 46, 116, 180)
wire((52, 118), (48, 118), (48, 122))
power("GND", 48, 122)

# -- PWM driver ---------------------------------------------------------------------
text("PWM driver", 34, 84)
part("Q1", 50, 94)                             # B (46, 94), C (52, 90), E (52, 98)
part("R5", 41, 94, 90)                         # pin 1 (38, 94), pin 2 (44, 94)
wire((44, 94), (45, 94), (46, 94))
label("Q1_B", 45, 94, 90)
label("IO12", 38, 94, 180)
wire((52, 90), (52, 86))
label("PWM", 52, 86)
wire((52, 98), (52, 100))
power("GND", 52, 100)

# -- 12 V switch --------------------------------------------------------------------
text("12 V switch", 150, 36)
part("Q2", 164, 60)                            # B (160, 60), C (166, 56), E (166, 64)
part("R6", 155, 60, 90)                        # pin 1 (152, 60), pin 2 (158, 60)
wire((158, 60), (159, 60), (160, 60))
label("Q2_B", 159, 60, 90)
label("IO16", 152, 60, 180)
wire((166, 64), (166, 66))
power("GND", 166, 66)
wire((166, 56), (166, 50), (170, 50), (174, 50), (180, 50))
label("GATE", 170, 50, 90)
junction(174, 50)
part("R12", 174, 47, 180)                      # pin 2 (174, 44) to +12V, pin 1 (174, 50): gate to source
wire((174, 44), (174, 42), (186, 42))
part("Q3", 184, 50, mirror="x")                # G (180, 50), S (186, 46) up, D (186, 54) down
wire((186, 46), (186, 42), (186, 40))
junction(186, 42)
power("+12V", 186, 40)
wire((186, 54), (186, 58), (194, 58), (202, 58), (202, 56))
junction(194, 58)
part("D1", 194, 61, 270)                       # cathode (194, 58) on +12V_SW, anode (194, 64) to ground
power("GND", 194, 64)
power("+12V_SW", 202, 56)

# -- Flow meter ---------------------------------------------------------------------
text("Flow meter", 174, 70)
part("J7", 220, 88)                            # pins at x 216: 86 +12V, 88 GND, 90 FLOW
wire((216, 86), (214, 86), (214, 78))
power("+12V", 214, 78)
wire((216, 88), (210, 88), (210, 84))
power("GND", 210, 84, 180)
wire((216, 90), (210, 90), (206, 90))
label("FLOW", 210, 90, 270)
part("R13", 203, 90, 270)                      # pin 1 (206, 90) FLOW, pin 2 (200, 90) Q4 base
part("Q4", 194, 90, mirror="y")                # B (198, 90), C (192, 86), E (192, 94)
wire((198, 90), (199, 90), (200, 90))
label("Q4_B", 199, 90, 90)
wire((192, 86), (192, 82))
junction(192, 82)
part("R14", 192, 79, 180)                      # pin 2 (192, 76) to 3V3, pin 1 (192, 82)
power("3V3", 192, 76)
wire((192, 82), (186, 82))
label("IO13", 186, 82, 180)
wire((192, 94), (192, 98))
power("GND", 192, 98)

# -- Temperature sensors ------------------------------------------------------------
text("DS18B20 sensors", 197, 100)
part("J6", 220, 112)                           # pins at x 216: 110 3V3, 112 DQ, 114 GND
wire((216, 110), (212, 110), (212, 106))
power("3V3", 212, 106)
wire((216, 112), (206, 112), (202, 112))
junction(206, 112)
label("DQ", 202, 112, 180)
part("R10", 206, 109, 180)                     # pin 2 (206, 106) to 3V3, pin 1 (206, 112): 1-Wire pull-up
power("3V3", 206, 106)
wire((216, 114), (212, 114), (212, 118))
power("GND", 212, 118)
part("J8", 220, 126)                           # pins at x 216: 124 3V3, 126 DQ, 128 GND
wire((216, 124), (208, 124), (208, 120))
power("3V3", 208, 120)
wire((216, 126), (202, 126))
label("DQ", 202, 126, 180)
wire((216, 128), (212, 128), (212, 132))
power("GND", 212, 132)

# -- Mounting holes -----------------------------------------------------------------
text("Mounting", 174, 114)
for i, x in enumerate((176, 182, 188, 194), 1):
    part(f"H{i}", x, 122)                      # pad pin at (x, 124)
    wire((x, 124), (x, 126))
wire((176, 126), (182, 126), (188, 126), (190, 126), (194, 126))
junction(182, 126)
junction(188, 126)
junction(190, 126)
power("GND", 182, 126)
flag(190, 126, 180)

# ---------------------------------------------------------------- PCB
# Millimetres, origin at the board's top-left corner, y down. Rotations are KiCad's: degrees
# counter-clockwise as seen from the front. All parts sit on the front.
BOARD = (70.0, 50.0)
HOLES = {"H1": (4.0, 4.0), "H2": (66.0, 4.0), "H3": (4.0, 46.0), "H4": (66.0, 46.0)}
MODULE_KEEPOUT = (24.0, -15.0, 46.0, 20.5)      # x1, y1, x2, y2: the ESP-12F and 3 mm beside it; y1 covers the antenna overhang
ZONE_INSET = 1.0

PCB_PARTS = {
    # the module, antenna past the top edge
    "U1": (35.0, 5.0, 0),
    # 12 V input, left edge
    "J2": (5.4, 11.0, 270),          # pad 1 (+) at (5.4, 11), pad 2 (-) at (5.4, 16.08); the wire openings, the footprint's +y face, toward the left edge
    "F1": (13.5, 19.0, 90),          # pad 1 (13.5, 21.55) from J2, pad 2 (13.5, 16.45) the fused +12V
    "J7": (3.5, 22.5, 0),            # flow: 12V, GND, FLOW down the edge
    "C1": (20.7, 21.5, 270),         # below the pull-ups, the closest free spot to the VCC pad
    # pull-ups of the module's left-hand pins, in the gap between F1 and the module
    "R1": (17.5, 10.0, 270),         # RST
    "R2": (20.7, 10.0, 270),         # EN
    "R4": (18.5, 31.0, 270),         # TACH3, with the flow stage
    "SW1": (15.9, 2.0, 0),           # RST, top-left corner next to the module's RST pad
    # flow input stage, bottom-left
    "Q4": (6.5, 36.0, 90),
    "R13": (11.0, 38.62, 90),        # pin 1 (bottom) FLOW, pin 2 (top) Q4 base
    "R14": (14.5, 31.0, 270),
    # 3.3 V regulator under the module, IN pads on the left
    "U2": (35.0, 27.5, 0),
    # PWM driver below the regulator
    "R5": (27.5, 36.0, 0),
    "Q1": (38.5, 36.9, 0),           # clear of the PWM bus below, so its GND pad gets a proper pour around it
    # fans along the bottom edge, pin 1 left, latch toward the edge
    "J3": (11.0, 46.0, 0),
    "J4": (30.5, 46.0, 0),
    "J5": (50.0, 46.0, 0),
    # top-right: FLASH button, the pull-ups of the module's right-hand pins, serial header
    "SW2": (47.6, 2.0, 0),
    "R8": (47.9, 10.0, 270),         # TACH2: the lower module pad takes the nearer resistor, so the two tach tracks don't cross
    "R7": (51.3, 10.0, 270),         # TACH1
    "R9": (54.7, 10.0, 270),         # IO0
    "R10": (58.1, 10.0, 270),        # DQ
    "R11": (61.5, 10.0, 270),        # IO15 pull-down
    "J1": (67.2, 9.0, 0),
    "J6": (67.2, 20.0, 0),
    "J8": (67.2, 30.0, 0),
    # reverse diode on the +12V trunk, then the 12 V switch, right-middle, Q3's tab toward the fans
    "D2": (48.0, 21.8, 0),           # cathode (band) at the left pad
    "Q2": (47.6, 31.0, 90),
    "D1": (53.46, 30.5, 0),          # cathode at the left pad, straight above Q3's drain; its K mark clears R12's pad
    "R3": (63.7, 37.6, 270),         # IO16 pull-up, standing (P2.54): pin 1 (top) IO16, pin 2 (63.7, 40.14) 3V3; below J8's pin labels
    "R6": (60.4, 33.5, 270),         # pin 1 (top) IO16, pin 2 Q2 base; half a millimetre below D1's courtyard
    "R12": (61.5, 26.5, 180),        # gate pull-up: pin 1 (right) GATE, pin 2 (53.88, 26.5) +12V, off the trunk; body clear of D1's K mark
    "Q3": (56.0, 35.5, 180),         # G (56, 35.5), D (53.46, 35.5), S (50.92, 35.5)
}
PCB_PARTS.update({ref: (x, y, 0) for ref, (x, y) in HOLES.items()})

# (text, at, rotation, size mm[, side "F"/"B"[, justify "L"/"R"]]); centred unless told otherwise
SILK = [
    ("fan-controller", (21.8, 35.5), 90, 1.0), ("Rev 1.0", (23.4, 35.5), 90, 0.8),
    ("https://github.com/vvsosed/esp8266-fan-controller", (35.0, 13.0), 0, 0.8, "B"),     # under the module: no pads there
    ("RST", (11.0, 4.25), 0, 0.8), ("FLASH", (59.0, 4.25), 0, 0.8),
    ("+", (8.2, 7.4), 0, 0.8), ("-", (8.2, 19.7), 0, 0.8),              # beside the terminal's top (+) and bottom (-) corners
    ("S", (50.92, 33.0), 0, 0.8), ("D", (53.46, 33.0), 0, 0.8), ("G", (56.0, 33.0), 0, 0.8),
]
for n, x in ((1, 11.0), (2, 30.5), (3, 50.0)):
    for i, name in enumerate(("G", "+", "T", "P")):
        SILK.append((name, (x + 2.54 * i, 41.3), 0, 0.9))
    SILK.append((f"FAN {n}", (x + 3.81, 40.0), 0, 0.8))
for i, name in enumerate(("TX", "RX", "GND")):
    SILK.append((name, (65.7, 9.0 + 2.54 * i), 0, 0.8, "F", "R"))     # right edges 0.2 mm short of the header bodies (x 65.93)
for y0 in (20.0, 30.0):                                 # J6, J8
    for i, name in enumerate(("3V3", "DQ", "GND")):
        SILK.append((name, (65.7, y0 + 2.54 * i), 0, 0.8, "F", "R"))
for i, name in enumerate(("12V", "GND", "FLOW")):
    SILK.append((name, (5.8, 22.5 + 2.54 * i), 0, 0.8, "F", "L"))

# ---- copper. A route is (net, layer, points[, width]); a point is (x, y) or "REF.PAD" (the pad centre, checked
# against the net). Widths per net, else TRACK_WIDTH. Vias are (net, (x, y)), VIA = (diameter, drill).
TRACK_WIDTH = 0.3
WIDTH = {"+12V_IN": 2.0, "+12V": 2.0, "+12V_SW": 2.0, "3V3": 0.5, "GND": 1.5}
VIA = (0.8, 0.4)
ROUTES = [
    # ---- 12 V in: J2 to the fuse; the fused 12 V to the flow header on the back, under the input track
    ("+12V_IN", "F.Cu", ["J2.1", (8.9, 11.0), (8.9, 18.9), (11.55, 21.55), "F1.1"]),
    ("+12V", "B.Cu", ["F1.2", (11.0, 18.95), (5.0, 18.95), "J7.1"], 1.5),
    # the +12V trunk: up between the pull-ups, under the module's bottom pads, to the reverse diode, down to Q3's source
    ("+12V", "F.Cu", ["F1.2", (13.5, 14.0), (23.0, 14.0), (23.0, 20.0), (48.0, 20.0), "D2.1", (50.92, 24.72), "Q3.3"]),
    ("+12V", "F.Cu", [(27.38, 20.0), "U2.1"]),
    ("+12V", "F.Cu", [(50.92, 26.5), "R12.2"], 1.5),
    # the switched 12 V: D1 straight above Q3's drain; from the drain down to the fan row on the back, spurs up to the headers
    ("+12V_SW", "F.Cu", ["D1.1", "Q3.2"]),
    ("+12V_SW", "B.Cu", ["Q3.2", (53.46, 43.6), (13.54, 43.6), "J3.2"]),
    ("+12V_SW", "B.Cu", [(33.04, 43.6), "J4.2"], 1.5),
    ("+12V_SW", "B.Cu", [(52.54, 43.6), "J5.2"], 1.5),
    # the module's GND pad sits in the keep-out, where the pours don't fill: down to a via, under the trunk on the back, out to the pours
    ("GND", "F.Cu", ["U1.15", (42.6, 17.9)], 0.5),
    ("GND", "B.Cu", [(42.6, 17.9), (40.0, 20.5), (40.0, 21.8)], 0.5),
    # ---- module right side: serial between the FLASH button's pad rows, the tach lines under the button, the rest as a staircase
    ("TX", "F.Cu", ["U1.22", (44.4, 1.5), (46.5, 3.6), (56.5, 3.6), (60.5, 7.6), (65.8, 7.6), "J1.1"]),
    ("RX", "F.Cu", ["U1.21", (44.4, 3.5), (45.5, 4.6), (56.5, 4.6), (60.5, 8.6), (63.3, 8.6), (66.24, 11.54), "J1.2"]),
    ("TACH1", "F.Cu", ["U1.20", (44.4, 5.5), (45.6, 6.7), (47.25, 8.35), (49.65, 8.35), "R7.1"]),   # (45.6, 6.7): the J3 branch's via
    ("TACH2", "F.Cu", ["U1.19", (44.4, 7.5), (46.9, 10.0), "R8.1"]),
    ("IO0", "F.Cu", ["U1.18", (44.4, 9.5), (47.1, 12.2), (52.5, 12.2), "R9.1"]),
    ("IO0", "B.Cu", ["R9.1", (55.6, 9.1), (55.6, 2.0), "SW2.1", (47.6, 2.0)]),
    ("DQ", "F.Cu", ["U1.17", (44.4, 11.5), (46.5, 13.6), (56.0, 13.6), (58.1, 11.5), "R10.1"]),
    ("IO15", "F.Cu", ["U1.16", (44.4, 13.5), (45.9, 15.0), (60.0, 15.0), (61.5, 13.5), "R11.1"]),
    # 3V3: the regulator's output crosses under the trunk to the pull-up row, then on to the sensor headers and R3
    ("3V3", "B.Cu", ["U2.3", (44.5, 21.05), (44.5, 18.5), (45.38, 17.62), "R8.2"]),
    ("3V3", "F.Cu", ["R8.2", "R7.2", "R9.2", "R10.2", (59.78, 19.3), (66.5, 19.3), "J6.1"]),
    ("3V3", "F.Cu", ["J6.1", (68.7, 21.5), (68.7, 28.5), "J8.1", (68.7, 31.5), (68.7, 38.64), (67.2, 40.14), "R3.2"]),
    ("DQ", "F.Cu", ["J6.2", (65.7, 24.04), (65.7, 31.04), "J8.2"]),
    ("DQ", "B.Cu", ["R10.1", (59.8, 8.3), (63.6, 8.3), (65.3, 10.0), (65.3, 20.6), "J6.2"]),
    # the module's VCC: a via beside the pad, then on the back down and under the regulator to its output
    ("3V3", "F.Cu", ["U1.8", (28.4, 14.6), (29.3, 14.6)]),
    ("3V3", "B.Cu", [(29.3, 14.6), (29.3, 23.0), (30.8, 24.5), (40.9, 24.5), (42.47, 22.93), "U2.3"]),
    # ---- module left side. RST round the west of the button; EN straight to its pull-up
    ("RST", "F.Cu", ["U1.1", (22.9, 1.5), "SW1.1", (15.9, 2.0), (14.4, 3.5), (14.4, 8.5), (15.9, 10.0), "R1.1"]),
    ("EN", "F.Cu", ["U1.3", (24.2, 5.5), (24.2, 7.9), (23.5, 8.6), (21.9, 8.6), (20.7, 9.8), "R2.1"]),
    # IO16 goes east on the back, under the module and the pull-up bodies, down the right edge to R3, then to R6
    ("IO16", "F.Cu", ["U1.4", (25.3, 7.5)]),
    ("IO16", "B.Cu", [(25.3, 7.5), (26.3, 8.5), (26.3, 11.5), (27.3, 12.5), (62.4, 12.5), (64.4, 14.5), (64.4, 36.9), (63.7, 37.6), "R3.1"]),
    ("IO16", "F.Cu", ["R3.1", "R6.1"]),
    # TACH3, IO12 and IO13 drop to the back beside the module and run south in three lanes
    ("TACH3", "F.Cu", ["U1.5", (22.6, 9.5)]),
    ("TACH3", "B.Cu", [(22.6, 9.5), (22.6, 26.5), (8.0, 26.5)]),
    ("TACH3", "F.Cu", ["R4.1", (18.5, 26.5)]),
    ("TACH3", "F.Cu", [(8.0, 26.5), (8.0, 48.4), (55.08, 48.4), "J5.3"]),
    ("IO12", "F.Cu", ["U1.6", (25.3, 11.5)]),
    ("IO12", "B.Cu", [(25.3, 11.5), (25.7, 11.9), (25.7, 36.0), "R5.1"]),
    ("IO13", "F.Cu", ["U1.7", (24.7, 13.5)]),
    ("IO13", "B.Cu", [(24.7, 13.5), (24.7, 14.5), (23.5, 15.7), (23.5, 29.6), (7.8, 29.6), "Q4.3"]),
    ("IO13", "B.Cu", ["R14.1", (14.5, 29.6)]),
    # the left 3V3 group: pull-ups, C1, down to R4 and R14, and from R4 on the back to the regulator's output
    ("3V3", "B.Cu", ["R1.2", "R2.2"]),
    ("3V3", "F.Cu", ["R2.2", "C1.1", (22.0, 22.8), (22.0, 36.0), (19.38, 38.62), "R4.2", "R14.2"]),
    ("3V3", "B.Cu", ["R4.2", (19.7, 37.4), (32.4, 37.4), (33.5, 36.3), (33.5, 25.6), (34.6, 24.5)]),
    # flow stage
    ("FLOW", "B.Cu", ["J7.3", (3.5, 37.6), (4.5, 38.62), "R13.1"]),
    ("Q4_B", "B.Cu", ["Q4.2", (8.0, 31.96), (10.0, 31.96), "R13.2"]),
    # PWM driver and bus (front, above the fan row), the tach lines dropping under it through vias
    ("Q1_B", "B.Cu", ["R5.2", (35.37, 35.75), (40.0, 35.75), (41.04, 36.79), "Q1.2"]),
    ("PWM", "F.Cu", ["Q1.3", (43.58, 40.6)]),
    ("PWM", "F.Cu", [(18.62, 40.6), (57.62, 40.6)]),
    ("PWM", "F.Cu", ["J3.4", (18.62, 40.6)]),
    ("PWM", "F.Cu", ["J4.4", (38.12, 40.6)]),
    ("PWM", "F.Cu", ["J5.4", (57.62, 40.6)]),
    ("TACH1", "F.Cu", ["J3.3", (16.08, 41.75)]),
    ("TACH1", "B.Cu", [(16.08, 41.75), (16.08, 30.6)]),
    ("TACH1", "F.Cu", [(16.08, 30.6), (16.08, 21.0), (19.2, 17.88), (19.2, 16.3)]),
    # the J3 branch crosses the module on the back: on the front it would pass between two castellations, where solder bridges
    ("TACH1", "B.Cu", [(19.2, 16.3), (19.2, 4.5), (43.4, 4.5), (45.6, 6.7)]),
    ("TACH2", "F.Cu", ["J4.3", (35.58, 41.75)]),
    ("TACH2", "B.Cu", [(35.58, 41.75), (37.0, 40.33), (37.0, 39.3)]),
    ("TACH2", "F.Cu", [(37.0, 39.3), (37.0, 22.3)]),
    ("TACH2", "B.Cu", [(37.0, 22.3), (37.0, 14.3)]),
    ("TACH2", "F.Cu", [(37.0, 14.3), (37.0, 9.0), (37.5, 8.5), (41.6, 8.5), "U1.19"]),
    # the 12 V switch: gate net on the back round the reverse diode, Q2's base on the front under Q3
    ("GATE", "B.Cu", ["Q2.3", (49.12, 24.4), (60.1, 24.4), (61.5, 25.8), "R12.1"]),
    ("GATE", "F.Cu", ["R12.1", (58.9, 28.1), (58.9, 32.6), "Q3.1"]),
    ("Q2_B", "F.Cu", ["Q2.2", (49.1, 29.96), (49.1, 36.6), (50.5, 38.0), (59.0, 38.0), (60.4, 39.4), "R6.2"]),
]
VIAS = [
    ("GND", (42.6, 17.9)), ("GND", (40.0, 21.8)),
    ("3V3", (29.3, 14.6)),
    ("IO16", (25.3, 7.5)), ("TACH3", (22.6, 9.5)), ("TACH3", (8.0, 26.5)), ("TACH3", (18.5, 26.5)),
    ("IO12", (25.3, 11.5)), ("IO13", (24.7, 13.5)),
    ("TACH1", (16.08, 41.75)), ("TACH1", (16.08, 30.6)), ("TACH1", (19.2, 16.3)), ("TACH1", (45.6, 6.7)),
    ("TACH2", (35.58, 41.75)), ("TACH2", (37.0, 39.3)), ("TACH2", (37.0, 22.3)), ("TACH2", (37.0, 14.3)),
    ("GND", (27.4, 27.5)), ("GND", (31.5, 30.0)), ("GND", (26.9, 34.5)), ("GND", (24.0, 33.0)), ("GND", (35.25, 31.5)), ("GND", (40.0, 39.3)),
]

# Reference designators on the silkscreen: "above" (centred over the courtyard), "hide", or (x, y, rotation)
REF_AT = {
    "U1": (35.0, 18.5, 0), "U2": "above", "J2": (12.5, 8.8, 0), "J7": "above", "F1": "above",
    "SW1": (11.0, 6.0, 0), "SW2": (59.0, 6.0, 0), "C1": "above",
    "R4": (20.6, 34.81, 90), "Q4": (6.15, 37.65, 0),
    "R5": (31.31, 38.1, 0), "Q1": (45.6, 36.9, 0),
    "D2": (63.6, 21.3, 0), "Q2": (50.6, 26.5, 0), "D1": (57.27, 30.5, 0), "R12": (57.7, 26.5, 0), "R3": (67.2, 38.4, 0), "R6": (60.4, 42.8, 0), "Q3": (57.9, 33.0, 0),
    "J1": (67.2, 16.5, 0), "J6": (67.2, 17.6, 0), "J8": (67.2, 27.6, 0),
    "J3": "hide", "J4": "hide", "J5": "hide", "H1": "hide", "H2": "hide", "H3": "hide", "H4": "hide",
}
