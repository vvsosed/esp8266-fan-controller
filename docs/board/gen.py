"""Check the placement in data.py and draw it as SVG (top: parts; back: chains and wires)."""
import re, sys, html
from data import *

P = 2.54; M = 3.3; S = 10            # pitch mm, grid margin mm, SVG units per mm
BW, BH = 70.0, 50.1                  # board mm

def cr(h):
    m = re.fullmatch(r"([A-Z])(\d+)", h); return COLS.index(m[1]) + 1, int(m[2])
def xy(h, c=None):
    if c is None: c, r = cr(h)
    else: r = h
    return (M + (c - 1) * P) * S, (M + (r - 1) * P) * S

# ---------- checks ----------
def check():
    bad = []
    used = {}
    for ref, kind, val, pins, note in PARTS:
        for h in pins:
            if h not in HOLES: bad.append(f"{ref}: {h} is not a hole")
            if h in KEEP_OUT: bad.append(f"{ref}: {h} is a flash pin")
            if h in used: bad.append(f"{ref}: {h} already holds {used[h]}")
            used[h] = ref
    for net, chains in CHAINS.items():
        for ch in chains:
            for a, b in zip(ch, ch[1:]):
                (c1, r1), (c2, r2) = cr(a), cr(b)
                if abs(c1 - c2) + abs(r1 - r2) != 1: bad.append(f"chain {net}: {a}-{b} not adjacent")
            for h in ch:
                if h not in HOLES: bad.append(f"chain {net}: {h} is not a hole")
                if h in KEEP_OUT: bad.append(f"chain {net}: {h} is a flash pin")
    for a, b, net, note in WIRES:
        for h in (a, b):
            if h not in HOLES: bad.append(f"wire {net}: {h} is not a hole")
            if h in KEEP_OUT: bad.append(f"wire {net}: {h} is a flash pin")
            if h in STUBS and net.startswith("+12"): bad.append(f"wire {net}: {h} has an ESP-32 stub")
    # one hole, one net: collect nets per hole from parts, chains and wires
    nets = {}
    # one net under several names: an ESP pin and the wire that reaches it, a transistor pin and its net
    alias = {"IO14": "tach 3", "IO5": "tach 1", "IO4": "tach 2", "IO2": "DQ",
             "Q1 C": "PWM", "Q1 B": "Q1 base", "Q2 C": "gate", "Q2 B": "Q2 base", "Q4 C": "IO13", "Q4 B": "Q4 base"}
    def put(h, n):
        n = alias.get(n, n)
        if h in nets and nets[h] != n: bad.append(f"{h}: {nets[h]} and {n}")
        nets[h] = n
    for a, b, net, note in WIRES:
        put(a, net); put(b, net)
    for ref, kind, val, pins, note in PARTS:
        for h, n in pins.items():
            put(h, {"IO16": "IO16", "IO12": "IO12", "Q1 base": "Q1 base", "Q2 base": "Q2 base",
                    "G": "gate", "gate": "gate", "S": "+12 V", "D": "+12 V sw", "tach 1": "tach 1",
                    "tach 2": "tach 2", "tach 3": "tach 3"}.get(n, n) if ref not in ("Q1", "Q2", "Q4") else "GND" if n == "E" else f"{ref} {n}")
    for net, chains in CHAINS.items():
        for ch in chains:
            for h in ch: put(h, net)
    for h, n in nets.items():
        if h in STUBS and n.startswith("+12"): bad.append(f"{h}: {n} on an ESP-32 stub")
    return bad, nets

# ---------- drawing ----------
def hole_svg(h, cls=""):
    x, y = xy(h)
    r = 6 if h in RELAY_PADS else 4.5
    return f'<circle class="hole {cls}" cx="{x:.1f}" cy="{y:.1f}" r="{r}"/>'

def board_svg(layer):
    out = [f'<rect class="board" x="0" y="0" width="{BW*S}" height="{BH*S}" rx="12"/>']
    for c, r in ((0.67, 0.73), (26.33, 0.73), (0.67, 18.27), (26.33, 18.27)):
        x, y = xy(r, c); out.append(f'<circle class="mount" cx="{x:.1f}" cy="{y:.1f}" r="15"/>')
    # module outline and pads (top side)
    x0, _ = xy(1, 9.67); x1, _ = xy(1, 16.5); _, y1 = xy(9.7, 1)
    out.append(f'<rect class="module" x="{x0:.1f}" y="0" width="{x1-x0:.1f}" height="{y1:.1f}"/>')
    out.append(f'<rect class="antenna" x="{x0+40:.1f}" y="6" width="{x1-x0-80:.1f}" height="50" rx="4"/>')
    out.append(f'<text class="modlabel" x="{(x0+x1)/2:.1f}" y="{y1/2+60:.0f}" text-anchor="middle">ESP-12F</text>')
    for i, h in enumerate(["F3", "F4", "F5", "F6", "F7", "F8", "F9", "F10"]):
        px, py = x0 + 4, xy(3 + i * 2 / P, 1)[1]
        out.append(f'<rect class="pad" x="{px-8:.1f}" y="{py-5:.1f}" width="12" height="10"/>')
        hx, hy = xy(h); out.append(f'<path class="trace" d="M{px-4:.1f},{py:.1f} L{px-22:.1f},{py:.1f} L{hx+10:.1f},{hy:.1f} L{hx:.1f},{hy:.1f}"/>')
    for i, h in enumerate(["T3", "T4", "T5", "T6", "T7", "T8", "T9", "T10"]):
        px, py = x1 - 4, xy(3 + i * 2 / P, 1)[1]
        out.append(f'<rect class="pad" x="{px-4:.1f}" y="{py-5:.1f}" width="12" height="10"/>')
        hx, hy = xy(h); out.append(f'<path class="trace" d="M{px+4:.1f},{py:.1f} L{px+22:.1f},{py:.1f} L{hx-10:.1f},{hy:.1f} L{hx:.1f},{hy:.1f}"/>')
    for i, h in enumerate(["K13", "L13", "M13", "N13", "O13", "P13"]):
        px, py = xy(1, 11.2 + i * 2 / P)[0], y1 - 4
        out.append(f'<rect class="pad" x="{px-5:.1f}" y="{py-8:.1f}" width="10" height="12"/>')
        hx, hy = xy(h); out.append(f'<path class="trace" d="M{px:.1f},{py+4:.1f} L{hx:.1f},{hy:.1f}"/>')
    for h in sorted(HOLES):
        cls = "keep" if h in KEEP_OUT else "stub" if h in STUBS else ""
        out.append(hole_svg(h, cls))
    for h, name in PINS.items():
        x, y = xy(h); dx = 14 if h[0] == "F" else -14
        anchor = "start" if h[0] == "F" else "end"
        if h[0] in "FT":
            out.append(f'<text class="pin" x="{x+dx:.1f}" y="{y-5:.1f}" text-anchor="{anchor}">{name}</text>')
        else:
            out.append(f'<text class="pin" transform="translate({x+3.5:.1f},{y-9:.1f}) rotate(-90)">{name}</text>')
    # grid labels
    for i, c in enumerate(COLS):
        x, _ = xy(1, i + 1); out.append(f'<text class="grid" x="{x:.1f}" y="{BH*S+16}" text-anchor="middle">{c}</text>')
    for r in ROWS:
        _, y = xy(r, 1); out.append(f'<text class="grid" x="-8" y="{y+3.5:.1f}" text-anchor="end">{r}</text>')
    return out

def parts_svg():
    out = []
    for ref, kind, val, pins, note in PARTS:
        hs = list(pins)
        if kind == "module": continue
        if kind in ("res", "diode"):
            (ax, ay), (bx, by) = xy(hs[0]), xy(hs[1])
            out.append(f'<path class="lead" d="M{ax:.1f},{ay:.1f} Q{(ax+bx)/2:.1f},{(ay+by)/2-18:.1f} {bx:.1f},{by:.1f}"/>')
            out.append(f'<circle class="part body" cx="{ax:.1f}" cy="{ay:.1f}" r="12"/>')
            if kind == "diode": out.append(f'<circle class="stripe" cx="{bx:.1f}" cy="{by:.1f}" r="5"/>')
            out.append(f'<text class="ref" x="{ax:.1f}" y="{ay+3.5:.1f}" text-anchor="middle">{ref}</text>')
        elif kind in ("cap", "ecap"):
            (ax, ay), (bx, by) = xy(hs[0]), xy(hs[1])
            cx, cy = (ax + bx) / 2, (ay + by) / 2
            if kind == "cap": out.append(f'<rect class="part body" x="{cx-9:.1f}" y="{cy-18:.1f}" width="18" height="36" rx="4"/>')
            else:
                out.append(f'<circle class="part body" cx="{cx:.1f}" cy="{cy:.1f}" r="25"/>')
                out.append(f'<text class="ref" x="{ax-12:.1f}" y="{ay-10:.1f}">+</text>')
            out.append(f'<text class="ref" x="{cx:.1f}" y="{cy+3.5:.1f}" text-anchor="middle">{ref}</text>')
        elif kind == "to92v":
            (ax, ay), (bx, by) = xy(hs[0]), xy(hs[2]); cx, cy = ax, (ay + by) / 2
            out.append(f'<path class="part body" d="M{cx-18:.1f},{cy-24:.1f} h26 v48 h-26 a10,24 0 0 1 0,-48 z"/>')   # 3.7 mm thick, round back 2.2 mm behind the leads
            out.append(f'<text class="ref" x="{cx:.1f}" y="{cy+3.5:.1f}" text-anchor="middle">{ref}</text>')
            for h, n in pins.items():
                x, y = xy(h); out.append(f'<text class="pinname" x="{x+14:.1f}" y="{y+3:.1f}">{n}</text>')
        elif kind == "buck":
            (ax, ay), (bx, by) = xy(hs[0]), xy(hs[3]); cx, cy = (ax + bx) / 2, (ay + by) / 2
            out.append(f'<rect class="part body" x="{cx-55:.1f}" y="{cy-85:.1f}" width="110" height="170" rx="4"/>')
            out.append(f'<text class="ref" x="{cx:.1f}" y="{cy+4:.1f}" text-anchor="middle">{ref} {val}</text>')
            out.append(f'<text class="pinname" x="{cx:.1f}" y="{cy+16:.1f}" text-anchor="middle">12 V → 3.3 V</text>')
            for h, n in zip(hs, ("IN+", "IN−", "OUT+", "OUT−")):
                x, y = xy(h); left = x < cx
                out.append(f'<rect class="pinsq" x="{x-5:.1f}" y="{y-5:.1f}" width="10" height="10"/>')
                out.append(f'<text class="pinname" x="{x + (11 if left else -11):.1f}" y="{y+3:.1f}" text-anchor="{"start" if left else "end"}">{n}</text>')
        elif kind == "to220":
            (ax, ay), (bx, by) = xy(hs[0]), xy(hs[2]); cx, cy = (ax + bx) / 2, ay
            out.append(f'<rect class="part body" x="{cx-50:.1f}" y="{cy-22:.1f}" width="100" height="44" rx="3"/>')
            ty = cy + 14 if list(pins.values())[0] == "S" else cy - 22
            out.append(f'<rect class="tab" x="{cx-50:.1f}" y="{ty:.1f}" width="100" height="8"/>')
            out.append(f'<text class="ref" x="{cx:.1f}" y="{cy+4:.1f}" text-anchor="middle">{ref} {val}</text>')
            for h, n in pins.items():
                x, y = xy(h); out.append(f'<text class="pinname" x="{x:.1f}" y="{y+17:.1f}" text-anchor="middle">{n}</text>')
        elif kind == "tact":
            xs = [xy(h)[0] for h in hs]; ys = [xy(h)[1] for h in hs]
            cx, cy = sum(xs) / 4, sum(ys) / 4
            out.append(f'<rect class="part body" x="{cx-30:.1f}" y="{cy-30:.1f}" width="60" height="60" rx="6"/>')
            out.append(f'<circle class="button" cx="{cx:.1f}" cy="{cy:.1f}" r="16"/>')
            out.append(f'<text class="ref" x="{cx:.1f}" y="{cy+40:.1f}" text-anchor="middle">{ref} {val}</text>')
        elif kind == "hdr3" and len({xy(h)[0] for h in hs}) == 1:   # a header standing in a column (J7)
            x = xy(hs[0])[0]; ys = [xy(h)[1] for h in hs]; cy = (ys[0] + ys[-1]) / 2
            out.append(f'<rect class="part body" x="{x-12.5:.1f}" y="{cy-38:.1f}" width="25" height="76" rx="3"/>')
            for h in pins:
                _, y = xy(h); out.append(f'<rect class="pinsq" x="{x-5:.1f}" y="{y-5:.1f}" width="10" height="10"/>')
            out.append(f'<text class="ref" x="{x-12.5:.1f}" y="{ys[-1]+24:.1f}" text-anchor="start">{ref} {val}</text>')
        elif kind in ("hdr3", "fan"):
            xs = [xy(h)[0] for h in hs]; y = xy(hs[0])[1]
            w = 102 if kind == "fan" else 76; hh = 58 if kind == "fan" else 25
            cx = (xs[0] + xs[-1]) / 2; top = y - 25 if kind == "fan" else y - hh / 2
            out.append(f'<rect class="part body" x="{cx-w/2:.1f}" y="{top:.1f}" width="{w}" height="{hh}" rx="3"/>')
            if kind == "fan": out.append(f'<rect class="part body" x="{xs[0]-8:.1f}" y="{top+hh-10:.1f}" width="{xs[2]-xs[0]+16:.1f}" height="8"/>')
            for h, n in pins.items():
                x, _ = xy(h); out.append(f'<rect class="pinsq" x="{x-5:.1f}" y="{y-5:.1f}" width="10" height="10"/>')
                if kind == "fan": out.append(f'<text class="pinname" transform="translate({x+3.5:.1f},{y-12:.1f}) rotate(-90)">{n}</text>')
            lbl = f"{ref} {val}" if kind == "fan" else f"{ref} {val}"
            ly = y + 24 if kind == "fan" else y - 18
            out.append(f'<text class="ref" x="{cx:.1f}" y="{ly:.1f}" text-anchor="middle">{lbl}</text>')
        elif kind == "term":
            (ax, ay), (bx, by) = xy(hs[0]), xy(hs[1]); cx, cy = ax, (ay + by) / 2
            out.append(f'<rect class="part body" x="{cx-38:.1f}" y="{cy-51:.1f}" width="76" height="102" rx="4"/>')
            for h, n in pins.items():
                x, y = xy(h); out.append(f'<circle class="screw" cx="{x:.1f}" cy="{y:.1f}" r="12"/>')
                out.append(f'<text class="pinname" x="{x+16:.1f}" y="{y+3:.1f}">{n}</text>')
            out.append(f'<text class="ref" x="{cx:.1f}" y="{cy+4:.1f}" text-anchor="middle">{ref}</text>')
    return out

def back_svg():
    """Chains grouped per net, each wire in its own group, so the page can hide them by net or one at a time."""
    out = []
    for net, chains in CHAINS.items():
        col = NET_COLOR.get(net, "#888")
        out.append(f'<g class="net" data-net="{html.escape(net)}">')
        for ch in chains:
            pts = " ".join(f"{xy(h)[0]:.1f},{xy(h)[1]:.1f}" for h in ch)
            out.append(f'<polyline class="chain" points="{pts}" stroke="{col}"/>')
        out.append('</g>')
    for i, (a, b, net, note) in enumerate(WIRES):
        (ax, ay), (bx, by) = xy(a), xy(b)
        col = NET_COLOR.get(net, "#888"); w = 5 if "thick" in note else 3
        dx, dy = bx - ax, by - ay; mx, my = (ax + bx) / 2 - dy * 0.12, (ay + by) / 2 + dx * 0.12
        lw = len(net) * 4.6 + 10                      # label chip width for the 8 px font
        out.append(f'<g class="net" data-net="{html.escape(net)}" data-wire="{i}">')
        out.append(f'<path class="wire" d="M{ax:.1f},{ay:.1f} Q{mx:.1f},{my:.1f} {bx:.1f},{by:.1f}" stroke="{col}" stroke-width="{w}"/>')
        out.append(f'<g class="lbl" tabindex="0" role="button" aria-label="hide or show the {html.escape(net)} wire {a} to {b}">'
                   f'<rect x="{mx-lw/2:.1f}" y="{my-7:.1f}" width="{lw:.1f}" height="14" rx="7" stroke="{col}"/>'
                   f'<text class="wirelbl" x="{mx:.1f}" y="{my+3:.1f}" text-anchor="middle">{html.escape(net)}</text></g>')
        out.append('</g>')
    return out

def svg(layer):
    body = board_svg(layer)
    body += parts_svg() if layer == "top" else back_svg()
    w = BW * S + 20
    return (f'<svg class="brd" viewBox="-30 -10 {w+30:.0f} {BH*S+40:.0f}" xmlns="http://www.w3.org/2000/svg" role="img" '
            f'aria-label="{layer} view">' + "\n".join(body) + "</svg>")

if __name__ == "__main__":
    bad, nets = check()
    for b in bad: print("CHECK:", b)
    print("checks:", "ok" if not bad else f"{len(bad)} problems")
    open("top.svg", "w").write(svg("top")); open("back.svg", "w").write(svg("back"))
    print("holes", len(HOLES), "parts", len(PARTS), "wires", len(WIRES))
