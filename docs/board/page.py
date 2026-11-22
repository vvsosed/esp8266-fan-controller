"""Assemble the HTML page from data.py and gen.py."""
import html
from data import *
from gen import svg, check

E = html.escape

def tbl(head, rows, attrs=None):
    h = "".join(f"<th>{E(x)}</th>" for x in head)
    b = "".join(f"<tr{' ' + attrs[i] if attrs else ''}>" + "".join(f"<td>{x}</td>" for x in r) + "</tr>" for i, r in enumerate(rows))
    return f'<div class="tw"><table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'

def code(s): return f"<code>{E(s)}</code>"

PART_NAME = {"res": "resistor", "cap": "ceramic capacitor", "ecap": "electrolytic capacitor", "diode": "Schottky diode",
             "to92v": "NPN transistor", "to220": "P-channel MOSFET", "tact": "tactile switch", "hdr3": "3-pin header",
             "fan": "4-pin fan header", "term": "screw terminal", "module": "Wi-Fi module", "buck": "DC-DC buck module"}

parts_rows = []
for ref, kind, val, pins, note in PARTS:
    where = ", ".join(f"{code(h)} {E(n)}" for h, n in pins.items()) or "centre footprint"
    parts_rows.append([f"<b>{ref}</b>", f"{E(val)} {PART_NAME[kind]}", where, E(note)])

chain_rows = []
for net, chains in CHAINS.items():
    chain_rows.append([f'<span class="sw" style="background:{NET_COLOR.get(net, "#888")}"></span>{E(net)}',
                       "; ".join("–".join(code(h) for h in ch) for ch in chains)])

wire_attrs = [f'class="wrow" data-wire="{i}" data-net="{E(net)}" title="click to hide or show this wire"' for i, (a, b, net, note) in enumerate(WIRES)]
back_nets = [n for n in NET_COLOR if n in CHAINS or any(w[2] == n for w in WIRES)]
back_nets += sorted(({w[2] for w in WIRES} | set(CHAINS)) - set(back_nets))
wire_rows = [[f'<span class="sw" style="background:{NET_COLOR.get(net, "#888")}"></span>{E(net)}',
              code(a), code(b), E(note)] for a, b, net, note in WIRES]

bom = {}
for ref, kind, val, pins, note in PARTS:
    key = f"{val} {PART_NAME[kind]}"
    bom.setdefault(key, []).append(ref)
bom_rows = [[str(len(refs)), E(k), ", ".join(refs)] for k, refs in bom.items()]
bom_rows += [["1", "12 V supply", "sized for the fans plus 0.5 A"],
             ["", "hookup wire: 0.5 mm² for the 12 V paths, 0.25 mm² or wire-wrap wire for signals; tinned bare wire for the chains", ""]]

bad, nets = check()
assert not bad, bad

PAGE = f"""<title>Fan Controller Board Layout</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Source+Sans+3:ital,wght@0,400;0,600;0,700;1,400&family=Source+Code+Pro:wght@400;600&display=swap">
<style>
/* Layout: one reading column, the two board drawings full width, tables scroll sideways on phones. */
:root {{ --bg:#f5f4ee; --fg:#1f2a24; --muted:#5d6b63; --accent:#2f6f4e; --line:#d8d5c9; --card:#fdfdfa; --warn:#b54708;
  --sans:"Source Sans 3", "Segoe UI", system-ui, sans-serif; --mono:"Source Code Pro", ui-monospace, Menlo, monospace }}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{ --bg:#141916; --fg:#e6ebe6; --muted:#9ba89f; --accent:#86c9a2; --line:#2a332d; --card:#1b221d; --warn:#f0a35e; color-scheme:dark }} }}
:root[data-theme="dark"] {{ --bg:#141916; --fg:#e6ebe6; --muted:#9ba89f; --accent:#86c9a2; --line:#2a332d; --card:#1b221d; --warn:#f0a35e; color-scheme:dark }}
body {{ background:var(--bg); color:var(--fg); font:16px/1.5 var(--sans); padding-left:max(16px, env(safe-area-inset-left, 0px)); padding-right:max(16px, env(safe-area-inset-right, 0px)); padding-block:24px 48px }}
main {{ max-width:1100px; margin:0 auto; display:grid; gap:28px }}
h1 {{ font-size:2rem; line-height:1.15; margin:0; text-wrap:balance }}
h2 {{ font-size:1.3rem; margin:0 0 8px; color:var(--accent) }}
h3 {{ font-size:1.05rem; margin:14px 0 4px }}
p, li {{ max-width:68ch }} p {{ margin:6px 0 }}
.lede {{ color:var(--muted); font-size:1.05rem }}
.eyebrow {{ text-transform:uppercase; letter-spacing:.08em; font-size:.75rem; color:var(--muted); font-weight:600 }}
code {{ font:0.9em var(--mono); background:color-mix(in srgb, var(--fg) 8%, transparent); padding:1px 5px; border-radius:4px; white-space:nowrap }}
pre {{ font:0.85rem/1.4 var(--mono); background:var(--card); border:1px solid var(--line); border-radius:8px; padding:12px 14px; overflow-x:auto }}
.tw {{ overflow-x:auto; border:1px solid var(--line); border-radius:8px; background:var(--card) }}
table {{ border-collapse:collapse; width:100%; font-size:.95rem }}
th, td {{ text-align:left; vertical-align:top; padding:7px 10px; border-bottom:1px solid var(--line) }}
th {{ font-size:.75rem; text-transform:uppercase; letter-spacing:.06em; color:var(--muted) }}
tbody tr:last-child td {{ border-bottom:0 }}
.sw {{ display:inline-block; width:12px; height:12px; border-radius:3px; margin-right:6px; vertical-align:-1px }}
.fig {{ background:var(--card); border:1px solid var(--line); border-radius:10px; padding:10px }}
.fig svg {{ width:100%; height:auto; display:block }}
.legend {{ display:flex; flex-wrap:wrap; gap:6px 18px; font-size:.9rem; color:var(--muted); margin-top:8px }}
.legend span.k {{ display:inline-block; width:12px; height:12px; border-radius:50%; vertical-align:-1px; margin-right:5px; border:2px solid #8a7a44; background:#f1e5b8 }}
.warn {{ border-left:4px solid var(--warn); padding:6px 12px; background:color-mix(in srgb, var(--warn) 9%, transparent); border-radius:0 8px 8px 0 }}
.cols {{ display:grid; grid-template-columns:repeat(auto-fit, minmax(280px, 1fr)); gap:16px 28px }} .cols > * {{ min-width:0 }}
ol, ul {{ padding-left:22px; margin:6px 0 }}
/* board drawing */
.board {{ fill:#2f6f4e; stroke:#1b4a33; stroke-width:2 }}
.mount {{ fill:var(--card); stroke:#1b4a33; stroke-width:1.5 }}
.module {{ fill:#3a7a58; stroke:#dfe9e3; stroke-width:1.5; stroke-dasharray:6 4 }}
.antenna {{ fill:none; stroke:#dfe9e3; stroke-width:1 }}
.modlabel {{ fill:#dfe9e3; font:16px var(--sans) }}
.pad {{ fill:#d6c18a }} .trace {{ fill:none; stroke:#d6c18a; stroke-width:1.5 }}
.hole {{ fill:#f1e5b8; stroke:#8a7a44; stroke-width:1.5 }}
.hole.keep {{ fill:#e03131; stroke:#7a1010 }} .hole.stub {{ stroke:#f3c623; stroke-width:3 }}
.pin {{ fill:#fff; font:9px var(--mono) }} .grid {{ fill:var(--fg); font:600 10px var(--mono) }}
.part.body {{ fill:#eef0ec; fill-opacity:.95; stroke:#343a40; stroke-width:1.5 }}
.lead {{ fill:none; stroke:#343a40; stroke-width:1.5 }} .stripe {{ fill:#343a40 }}
.ref {{ fill:#212529; font:700 10px var(--sans) }} .pinname {{ fill:#212529; font:8px var(--sans) }}
.tab {{ fill:#adb5bd }} .button {{ fill:#495057 }} .pinsq {{ fill:#343a40 }} .screw {{ fill:#adb5bd; stroke:#343a40 }}
.buck {{ fill:#eef0ec; stroke:#343a40 }} .chain {{ fill:none; stroke-width:6; stroke-linecap:round; opacity:.9 }}
.wire {{ fill:none; stroke-linecap:round; opacity:.85 }} .wirelbl {{ fill:#111; font:600 8px var(--sans); pointer-events:none }}
.lbl {{ cursor:pointer }} .lbl rect {{ fill:#fff; fill-opacity:.92; stroke-width:1 }} .lbl:hover rect, .lbl:focus-visible rect {{ stroke-width:2.5 }} .lbl:focus {{ outline:none }}
g.net.off {{ display:none }} g.net.woff .wire {{ display:none }} g.net.woff .lbl {{ opacity:.4 }} g.net.woff .lbl rect {{ stroke-dasharray:3 2 }}
.nets {{ display:flex; flex-wrap:wrap; gap:6px; margin-top:10px }}
.chip {{ font:inherit; font-size:.85rem; line-height:1.2; padding:4px 10px; border:1px solid var(--line); border-radius:999px; background:var(--card); color:var(--fg); cursor:pointer }}
.chip.off {{ opacity:.45; text-decoration:line-through }} .chip:focus-visible {{ outline:2px solid var(--accent); outline-offset:1px }}
tr.wrow {{ cursor:pointer }} tr.wrow.off td {{ opacity:.4 }}
@media (prefers-reduced-motion: reduce) {{ * {{ scroll-behavior:auto }} }}
</style>
<main>
<header>
  <div class="eyebrow">diymore 5 × 7 cm ESP-12 prototype board · ESP8266 fan controller</div>
  <h1>Fan Controller Board Layout</h1>
  <p class="lede">Where every part of the three-fan controller goes on the board, and which holes to bridge and wire on the back. The grid is 26 columns (A–Z, left to right) by 18 rows (1–18, top to bottom), 2.54 mm apart; A1 is the top-left corner by the mounting hole, so <code>F3</code> is the hole the board labels RST.</p>
</header>

<section>
  <h2>What this plan assumes</h2>
  <ul>
    <li><b>A bare ESP-12F module</b> on the centre footprint, not the D1 mini. The board has no regulator, no USB and no boot-strap resistors, so this plan adds them: pull-ups on EN, RST and IO0, a pull-down on IO15, two buttons, a serial header, and a Mini-360 buck module trimmed to 3.3 V. The firmware and its pins stay as they are.</li>
    <li><b>Every hole is isolated.</b> Each module pin is routed to exactly one hole, the one beside its label: F3–F10 on the left, T3–T10 on the right, K13–P13 under the module for the six flash pins. Nothing else on the board is connected to anything.</li>
    <li><b>The back carries an unused ESP-32 footprint.</b> Its bare pads are tied to the holes drawn with a yellow ring (column F rows 2–12, column T rows 2–15, H13, H14 and J13–R13). The plan keeps 12 V off those holes and uses insulated wire wherever a wire crosses the back of the module area.</li>
  </ul>
</section>

<section>
  <h2>Top side: parts</h2>
  <div class="fig">{svg("top")}</div>
  <div class="legend"><span><span class="k"></span>plated hole</span><span><span class="k" style="background:#e03131;border-color:#7a1010"></span>flash pin, never solder</span><span><span class="k" style="border-color:#f3c623;border-width:3px"></span>has a stub to an ESP-32 pad on the back</span><span>Standing resistors and the diode are drawn as a disc on the hole that takes the lower lead, with the bent upper lead arcing to its hole.</span><span>Q3 is seen from above: the grey strip is its metal tab (drain), facing the fan headers. Its printed face looks at the module, so read from the module side its legs are G, D, S left to right, the datasheet's 1-2-3, which on the grid is K, J, I.</span></div>
  <p>Larger pads at U11, U16, Z11 and Z16 plus the one between W10 and X10 belong to the unused relay footprint. They are ordinary pads: the ground ring runs through Z11 and Z16 and row 16 through U16, and Z11 also takes the Mini-360's OUT− pin. U11 is where a bulk capacitor would go if one is ever needed; the COM pad stays bare under the module.</p>
</section>

<section>
  <h2>Back side: chains and wires</h2>
  <p>Drawn as seen from the top, through the board, so left stays left. A <b>chain</b> is tinned bare wire or a run of solder bridges between neighbouring holes; a <b>wire</b> is insulated hookup wire. The Mini-360 sits on the top side over W5–Z11, so only its four pins show here.</p>
  <p>Click a wire's label on the drawing to hide that wire; the label stays, dimmed, so another click brings it back. The buttons below hide or show every wire and chain of a net, and a row of the wires table further down toggles its wire too.</p>
  <div class="fig">{svg("back")}</div>
  <div class="nets" id="nets" aria-label="nets">{"".join(f'<button type="button" class="chip" data-net="{E(n)}" aria-pressed="true"><span class="sw" style="background:{NET_COLOR.get(n, "#888")}"></span>{E(n)}</button>' for n in back_nets)}<button type="button" class="chip" data-all="1">All</button><button type="button" class="chip" data-none="1">None</button></div>
</section>

<section>
  <h2>Parts and where they go</h2>
  {tbl(["Ref", "Part", "Holes", "Note"], parts_rows)}
  <h3>Shopping count</h3>
  {tbl(["Qty", "Part", "Refs"], bom_rows)}
</section>

<section>
  <h2>Chains on the back</h2>
  <p>Neighbouring holes joined with bare wire or solder. Ground forms a ring: column A, row 16 and column Z, plus row 12 on the right (T12–Z12), tied to the module's GND pin at T10. 3.3 V runs down column E on the left, fed from F10, and on the right from the Mini-360's OUT+ at W11 along V11–V8 to U8–U5; the 0.25 mm² wire along row 11 joins the two sides. The flow header's ground runs under J2's body, D14–C14–B14, to the terminal's own GND pin at B15; the outlet header's ground at Y3 joins the Z ring.</p>
  {tbl(["Net", "Chains"], chain_rows)}
</section>

<section>
  <h2>Wires on the back</h2>
  <p>"Thick" means 0.5 mm² for the 12 V paths. Everything else can be thin wire-wrap wire. A wire that lands on a hole which already holds a lead is soldered to that joint. O17 takes two thick wires, from J14 and on to Fan 1, and T8 two thin ones, the DQ lines from both sensor headers. C13 is covered by J2 on the top side, so its wire to W5 goes in before the terminal does. The IO13 wire runs up column F from Q4's collector at F13 to the module pin at F9, over the F10–F12 pads.</p>
  {tbl(["Net", "From", "To", "Note"], wire_rows, wire_attrs)}
</section>

<section class="cols">
  <div>
    <h2>Power</h2>
    <p>12 V comes in at J2 and goes two ways: a thick wire to I15, bridged to the MOSFET's source at I14, for the fans, and another across the back to the Mini-360's IN+ at W5. Both of the module's GND pins sit in the Z ground ring. Its OUT+ at W11 heads the right 3.3 V chain down to V8 and U8, where the tach pull-ups hang, and a 0.25 mm² wire along row 11, just below the module, carries it to F11, C1 and the module's 3V3 pin. The flow meter is the third 12 V branch: one bridge from C13 to its header pin at D13, on the terminal's side of the MOSFET, so it keeps counting while the fans are switched off. Its pulses come back swinging to 12 V and reach IO13 only through R13 and Q4, which invert them against R14's pull-up; the firmware counts edges, so the inversion costs nothing. Nothing on this board needs 5 V.</p>
    <p>The Mini-360 is trimmed to <b>3.3 V</b> on the bench before it is soldered in: its trimmer can be anywhere up to the input voltage, and the ESP-12F dies above 3.6 V. Its pads are 15.24 × 9.144 mm apart, six pitches along but 1.5 mm wider than W–Z across, so it stands on four short wire stubs rather than straight header pins, as its note says. There is no bulk capacitor on 3.3 V: the module's own output ceramic does that job 15 mm from the ESP's pins, and C1 sits right under its 3V3 pin, with the F12–T11 wire as its only ground. If the board ever resets during Wi-Fi bursts, a 100 µF electrolytic goes in at U11 (+) and U12, with one bridge U11–V11; the V11/V12 holes themselves are too close to the Mini-360's body for a 5 mm can.</p>
    <h2>Order of work</h2>
    <ol>
      <li>Chains on the back first, while the board is bare: the ground ring as tinned 0.5 mm bare wire, not bridges alone, because the fans' return current flows through it; then row 12 on the right, the two 3.3 V columns, the +12 V sw bus O17–Q17, the flow header's ground run D14–B15, T3–T2 and the RX run. Leave the W11–V11 bridge open for now, and the W11→F11 wire until step 5. Before the Z column: hold the Mini-360 over W5–Z11, component side up, IN end up, and check that the two pads over column Z read 0 Ω to each other. If the tied pair is over W, turn it round and swap the feeds as its note says.</li>
      <li>The ESP-12F on its footprint. Check each pad for bridges with a loupe.</li>
      <li>Resistors, C1, D1, the transistors, then the switches and headers. Kapton over H13–P13, H14 and H15–L15 goes down before Q3, and R12's upper lead gets its sleeve; lean R12 toward H15, since Q4 stands in the next hole. The thick wire from C13 to W5 goes in before the terminal, because J2 covers C13. J7 stands flush against J2's body: terminal first, then the header.</li>
      <li>The Mini-360: feed it 12 V on clip leads and turn its trimmer until OUT reads 3.3 V. Solder a stiff wire stub into each of its four pads, bend them 0.76 mm inward to meet the holes, and solder it in. Put 12 V on J2, check that W11 reads 3.3 V, and only then bridge W11–V11; the W11→F11 wire follows with the others.</li>
      <li>Wires last, shortest first. Tie the long ones under the module down with a dab of hot glue.</li>
    </ol>
  </div>
  <div>
    <h2>Before the first power-up</h2>
    <ul>
      <li>Q3 checked with a multimeter before soldering, printed face toward you, legs down. Short the three legs together first to discharge the gate. Diode mode, red probe on the middle leg and black on the right leg, reads about 0.5 V; swapped, it reads open. The left leg reads open to both. The tab reads 0 Ω to the middle leg. That confirms G-D-S whatever a pinout picture says.</li>
      <li>No continuity between 3V3 and GND, nor between +12 V and GND.</li>
      <li>G15 to H15 reads 10 kΩ, not 0 Ω, and H15 to J14 reads open: R12's upper lead is clear of Q3's tab.</li>
      <li>W11 reads 3.3 V with 12 V on J2 before the W11–V11 bridge and the W11→F11 wire are made; after them, U8, V8 and F10 read 3.3 V too.</li>
      <li>With 3.3 V applied: EN, RST and IO0 read 3.3 V, IO15 reads 0 V, IO2 reads 3.3 V. So do IO13 at F9 and the outlet header's W3.</li>
      <li>With 12 V on J2: the flow header's D13 reads 12 V, D14 and D15 read 0 V. Touch D15 to D13 for a moment and F9 falls to 0 V: that is what every pulse from the meter does.</li>
      <li>Before the first flash, D0 (IO16) reads about 1.5 V, not 3.3 V: R3 and R6 form a divider onto Q2's base. Once the firmware runs, the pin sits at 3.3 V or 0 V. The fan +12 V pins read 12 V: the switch defaults to on.</li>
    </ul>
    <h2>Bridges that would hurt</h2>
    <p>Pairs of neighbouring holes worth a second look with the loupe, because solder between them does more than stop the board working.</p>
    <ul>
      <li><b>E4–F4</b>: 3.3 V onto the ADC pin, rated for 1 V.</li>
      <li><b>E6–F6</b>, <b>E8–F8</b>: IO16 or IO12 tied hard to 3.3 V across its resistor; the pin fights the rail every time the firmware drives it low.</li>
      <li><b>C11–D11</b>, <b>E12–E13</b>: across R6 or R5, a GPIO straight onto a transistor base.</li>
      <li><b>D10–D11</b>: IO0 to IO16; <b>D10–E10</b>: IO0 held high, so FLASH stops working.</li>
      <li><b>V11–V12</b>, <b>W11–W12</b>: 3.3 V into the row-12 ground chain, a short across the Mini-360's output. <b>W17–W16</b> is the same short at the sensor header.</li>
      <li><b>H15–H16</b>, <b>I15–I16</b>: raw 12 V to ground. <b>O17–O16</b>, <b>P17–P16</b>, <b>Q17–Q16</b>: the switched rail to ground, through Q3 as soon as power is applied.</li>
      <li><b>D13–E13</b>: raw 12 V onto IO12 through R5's lead hole, the end of the ESP. <b>D13–D14</b>: 12 V to ground at the flow header. <b>E13–E14</b>: IO12 onto Q4's base. <b>F12–F13</b>: IO13 held at ground, so the flow count stays at zero; harmless at boot.</li>
      <li><b>W3–W4</b> with <b>W4–W5</b>: 12 V from the Mini-360's input onto the outlet sensor's 3.3 V pin, two bridges apart.</li>
    </ul>
    <h2>First flash</h2>
    <p>The D1 mini's USB and auto-reset are gone, so the first flash goes through a 3.3 V USB-serial adapter on J1: adapter RX to J1 TX, adapter TX to J1 RX, grounds joined. Power the board from its own 12 V supply, not from the adapter.</p>
    <ol>
      <li>Hold FLASH (SW2), tap RST (SW1), release FLASH.</li>
      <li><code>./build.sh --upload -p /dev/ttyUSB0</code> with the usual D1 mini FQBN; the ESP-12F has the same 4 MB flash.</li>
      <li>Tap RST. From then on the browser OTA page works as before.</li>
    </ol>
    <div class="warn"><p>Two taps on RST within the double-reset window open the setup AP, exactly as on the D1 mini.</p></div>
  </div>
</section>
</main>
"""

# Plain string, not an f-string: the braces are JavaScript.
SCRIPT = """<script>
(() => {
  const svg = document.querySelector('svg[aria-label="back view"]');
  if (!svg) return;
  const chips = [...document.querySelectorAll('#nets .chip[data-net]')];
  const rows = [...document.querySelectorAll('tr.wrow')];
  const offNets = new Set(), offWires = new Set();
  const apply = () => {
    svg.querySelectorAll('g.net').forEach(g => {
      g.classList.toggle('off', offNets.has(g.dataset.net));
      g.classList.toggle('woff', g.dataset.wire !== undefined && offWires.has(g.dataset.wire));
    });
    chips.forEach(c => { const off = offNets.has(c.dataset.net); c.classList.toggle('off', off); c.setAttribute('aria-pressed', String(!off)); });
    rows.forEach(r => r.classList.toggle('off', offNets.has(r.dataset.net) || offWires.has(r.dataset.wire)));
  };
  const flip = (set, key) => { if (set.has(key)) set.delete(key); else set.add(key); apply(); };
  chips.forEach(c => c.addEventListener('click', () => flip(offNets, c.dataset.net)));
  document.querySelector('#nets [data-all]').addEventListener('click', () => { offNets.clear(); offWires.clear(); apply(); });
  document.querySelector('#nets [data-none]').addEventListener('click', () => { chips.forEach(c => offNets.add(c.dataset.net)); apply(); });
  svg.querySelectorAll('g.net[data-wire] .lbl').forEach(l => {
    const id = l.closest('g.net').dataset.wire;
    l.addEventListener('click', e => { e.stopPropagation(); flip(offWires, id); });
    l.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); flip(offWires, id); } });
  });
  rows.forEach(r => r.addEventListener('click', () => flip(offWires, r.dataset.wire)));
})();
</script>
"""
PAGE += SCRIPT
open("board.html", "w", encoding="utf-8").write(PAGE)
print("board.html", len(PAGE), "bytes")
