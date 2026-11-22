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
