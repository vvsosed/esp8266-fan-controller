# ESP8266 Three-Fan Controller with DS1820 Temperature Sensor

*Design notes, 10 October 2026*

## Summary

- An ESP8266 board (Wemos D1 mini / NodeMCU) **can control three standard 4-pin PWM PC fans** and read all three tachometers. The fans need their own 12 V supply, and the ESP only provides the control signals.
- **PWM:** about 25 kHz, open-drain. The most robust option is one small NPN transistor or N-MOSFET whose collector feeds all three fans' PWM lines, as a motherboard's PWM splitter does. It inverts the signal; invert the duty cycle in software.
- **Tachometers:** these **can connect directly** to GPIOs. The output is open-collector, so a pull-up to **3.3 V** (internal or an external 10 kΩ) is all that's needed.
- **DS18B20s:** both (radiator inlet and outlet) on **GPIO2 (D4)** with one 4.7 kΩ pull-up; a 1-Wire bus takes several sensors, told apart by their 64-bit ROM addresses.
- **Fans fully off:** most fans don't stop at 0 % PWM, so **GPIO16 (D0)** drives one high-side switch that cuts all three fans' 12 V. The switch is a P-MOSFET, driven through an NPN.
- **Flow meter:** a Hall-effect meter's pulses go to **GPIO13 (D7)**, through an inverting NPN because the meter runs on 12 V and its output swings that high.
- **Pin budget:** with one shared PWM driver, only D8 stays free, with its boot constraint. Anything more points toward an ESP32.

---

## 1. Driving three 4-pin PWM fans

### Fan connector pinout

| Pin | Function | Typical wire colour | Notes |
|---|---|---|---|
| 1 | GND | Black | Must be common with ESP ground |
| 2 | +12 V | Yellow | Speed is **not** set by voltage. Here it is switched off only to stop the fans (§5) |
| 3 | Tach (sense) | Green | Open-collector, 2 pulses per revolution |
| 4 | PWM control | Blue | ~25 kHz (21–28 kHz), internal pull-up inside fan |

Wire colours vary by manufacturer, so always go by pin position.

### Power

- Use a 12 V DC supply rated for the combined fan current (each fan's label lists it, usually 0.1–0.5 A), plus some margin.
- Power the ESP board from the same supply through a small **buck converter to 5 V** feeding the board's 5 V/VIN pin.
- **Tie all grounds together.** This is required for both the PWM and tach signals to work.
- The fans' 12 V passes through a **high-side** switch driven by D0: a P-MOSFET ([§5](#5-wiring-per-channel)). Don't switch the fans' ground instead. A fan with its ground lifted floats toward 12 V, and so do its tach and PWM lines, which connect to 3.3 V GPIOs.

### PWM signal

- The fan pulls its own PWM pin up internally (to 3.3 V or 5 V depending on model). An **unconnected or undriven PWM pin means 100 % speed**, which is a useful fail-safe.
- **Recommended: one open-drain driver shared by all three fans**, as a 4-pin PWM splitter cable does on a motherboard
  - NPN (2N3904 / BC547): base → 1 kΩ → GPIO, emitter → GND, collector → pin 4 of every fan; **or**
  - Logic-level N-MOSFET (2N7000 / BSS138): gate → GPIO, source → GND, drain → pin 4 of every fan.
  - The driver only pulls the line low, so the fans' internal pull-ups just sit in parallel. The 4-wire fan spec caps each PWM input's sink current at 5 mA, so the stage sinks at most 15 mA; a 2N3904 with a 1 kΩ base resistor saturates at ten times that. A 5 V fan and a 3.3 V fan on one line settle between the two, which every PWM input must tolerate (5.25 V max).
  - This keeps a 5 V fan pull-up away from the 3.3 V GPIO.
  - The signal is **inverted** (GPIO high → fan line low), so the duty cycle is inverted in software.
  - The trade: one failed driver affects all three fans, and the fans can't run at different speeds. The firmware applies one duty to all three anyway.
- **Shortcut:** wiring the GPIO directly to pin 4 often works, but it relies on the ESP's protection diodes when a fan pulls up to 5 V. **Never do this on GPIO15** (see pin budget).
- **0 % duty does not always mean stopped.** Many fans fall back to a minimum speed (~20–30 %). To guarantee a fan is off, its 12 V line has to be switched on the high side. This design does that for all three fans at once from GPIO16 (D0).

### Software PWM on the ESP8266

- The ESP8266 has no hardware PWM; the Arduino core generates it with a timer interrupt.
- `analogWriteFreq(25000)` works. Duty-cycle accuracy is limited at that frequency and Wi-Fi activity adds some jitter, but fans tolerate this well. Running the CPU at 160 MHz can help.

### Pin budget and boot-strap constraints

1 PWM + 3 tach + 1 one-wire + 1 power switch + 1 flow meter = **7 signals**. Only five ESP8266 pins are fully free of restrictions: GPIO4, 5, 12, 13, 14, and all five are used (GPIO13 by the flow meter), which leaves only GPIO15 (D8) with its boot constraint.

| Pin | Boot requirement | Use here |
|---|---|---|
| GPIO15 (D8) | Must be **low** at boot (board has pull-down) | Free. Anything added here must not pull it high at boot: a fan's PWM pull-up would, and the board won't boot, so a fan goes here **through a transistor only**. |
| GPIO2 (D4) | Must be **high** at boot | 1-Wire bus. Its pull-up satisfies the boot condition. |
| GPIO0 (D3) | Must be **high** at boot; flash button | Left unused |
| GPIO16 (D0) | No interrupt support, no internal pull-up | Fans' 12 V switch (plain output). Unsuitable for tach. Must not be bridged to RST (the deep-sleep wake jumper), or driving it low resets the board |
| GPIO1/3 (TX/RX) | Serial | Left for USB serial |

- **Do not put tach lines on GPIO0 or GPIO2.** A fan holding its tach low at reset can stop the board from booting.
- With the transistor driver the fans run at **full speed during boot**, which is a safe default. The 12 V switch keeps this: the core sets every pin to input at startup, and the 10 kΩ pull-up on D0 then holds the switch on until the firmware drives it.

---

## 2. Tachometer inputs

**Direct connection is safe.** The tach output is open-collector: it only pulls the line to ground and never drives it high.

Pull-up options (always to **3.3 V**, never 12 V):

| Option | Parts | When to use |
|---|---|---|
| Internal pull-up (`INPUT_PULLUP`) | None | Short wires. The internal pull-up is weak (~30–100 kΩ), so noise can cause false counts. |
| External 10 kΩ to 3.3 V | 1 resistor per fan | **Recommended**, especially for wires longer than a few cm |

Optional extras:

- **~10 nF from pin to GND** if RPM readings jump around. A fan at 3000 RPM only gives about 100 pulses/s, so this filtering won't affect it.
- **1 kΩ series resistor** between the tach wire and the GPIO, as cheap protection against wiring mistakes.

**Verification test (do once per fan model):** power the fan with the ESP disconnected and measure tach to GND with a multimeter.

- **≈ 0 V / nothing meaningful:** genuine open-collector, so direct connection is fine.
- **Steady few volts or more:** the fan has its own pull-up (5 V or 12 V). Add a voltage divider or transistor before the GPIO.

**RPM calculation:** 2 pulses per revolution → RPM = pulses per second × 30.

---

## 3. DS1820 temperature sensor

- **Wiring:** VDD → 3.3 V, GND → GND, DQ → GPIO2 (D4), **4.7 kΩ pull-up from DQ to 3.3 V**.
- Use **normal power mode** (VDD connected). Parasite mode is unreliable at 3.3 V.
- For long cables (several metres), lower the pull-up to about 2.2 kΩ.
- **Why GPIO2 works:** the 1-Wire bus idles high and the sensor stays silent until addressed, so the high-at-boot requirement is always met.
- On most D1 mini / NodeMCU boards the **onboard LED is on GPIO2** and will flicker during reads. This is harmless.
- **Several sensors can share the same pin**; each has a unique 64-bit address. This design has two, at the radiator's inlet and outlet. The firmware reads them by address, stores each one's role, and the status page swaps the roles. Two sensors rarely agree to better than 0.5 °C, so the firmware also keeps an outlet offset, set from the page while the two are coupled at one temperature.
- **Variants:** the original DS1820 / DS18S20 reads in 0.5 °C steps. Many parts sold as "DS1820" are actually DS18B20 (up to 0.0625 °C). The DallasTemperature library handles both.
- **Non-blocking reads:** use `setWaitForConversion(false)` so a conversion (up to ~750 ms) doesn't stall the loop.

**Interaction with the tach counters:** 1-Wire is bit-banged and disables interrupts for tens of microseconds per bit. This doesn't lose tach pulses, because edge interrupts are latched in hardware and serviced as soon as interrupts are re-enabled; at ~100 pulses/s, two edges never fall inside one window. Software PWM may glitch briefly during a read, which the fans won't notice.

---

## 4. Final pin map

| Signal | GPIO | Board label | Hardware |
|---|---|---|---|
| PWM, fans 1–3 | GPIO12 | D6 | One NPN/MOSFET open-drain driver, collector to every fan's pin 4 |
| Fan 1 tach | GPIO5 | D1 | 10 kΩ to 3.3 V |
| Fan 2 tach | GPIO4 | D2 | 10 kΩ to 3.3 V |
| Fan 3 tach | GPIO14 | D5 | 10 kΩ to 3.3 V |
| DS18B20 DQ, inlet and outlet | GPIO2 | D4 | 4.7 kΩ to 3.3 V |
| Flow meter pulses | GPIO13 | D7 | Inverting NPN: 10 kΩ from the meter's 12 V-level output into the base, collector to the pin, 10 kΩ to 3.3 V. The meter's 12 V comes from before the fans' switch |
| Fans' 12 V switch | GPIO16 | D0 | NPN driver → P-MOSFET; 10 kΩ pull-up to 3.3 V |

GPIO15 (D8) is the only free pin. It must be low at boot.

---

## 5. Wiring per channel

**PWM driver (one for all three fans):**

```
                          ┌──── pin 4 (PWM) of fan 1
                          ├──── pin 4 (PWM) of fan 2   (each fan pulls the line up inside)
                          ├──── pin 4 (PWM) of fan 3
                          │
                          C
D6 (GPIO12) ──[ 1 kΩ ]─── B   NPN (2N3904 / BC547)
                          E
                          │
                         GND
```

**Tach input (repeat for each fan):**

```
3.3 V ──[ 10 kΩ ]──┬──────────── Fan pin 3 (TACH)
                   │
GPIO5 ──[ 1 kΩ ]───┘        optional: 10 nF from GPIO5 to GND
       (optional)
```

**DS1820:**

```
3.3 V ──┬──────────────── DS1820 VDD
        │
     [ 4.7 kΩ ]
        │
GPIO2 ──┴──────────────── DS1820 DQ
GND   ─────────────────── DS1820 GND
```

The second sensor's three leads go to the same three nets.

**Flow meter (Hall effect, YF-S401 or similar):**

The meter runs on 5–24 V and its signal wire swings between 0 V and roughly its supply, so it never goes to a GPIO directly. It is fed from the 12 V supply **before** the fans' switch, and one NPN turns its 12 V pulses into 3.3 V pulses on D7.

```
12 V ─────────────────────────────────────────────── Flow meter red (VCC, 5–24 V)
(from the supply, before the P-MOSFET)

3.3 V ──[ 10 kΩ ]──────────────────┐
                                   ├──────────────── D7 (GPIO13)
                                   C
Flow meter yellow ──[ 10 kΩ ]───── B   NPN (2N3904 / BC547)
(signal, swings 0 … 12 V)          E
                                   │
GND ───────────────────────────────┴──────────────── Flow meter black
```

- **How it works:** while the signal is low the NPN is off and the 10 kΩ pull-up holds D7 at 3.3 V. A pulse drives about 1.1 mA into the base ((12 V − 0.7 V) / 10 kΩ), far more than the 0.33 mA the collector has to sink, so the NPN saturates and pulls D7 to ground. D7 therefore idles high and dips once per pulse. The stage inverts the signal but not the count: the firmware counts falling edges, one per pulse.
- **Why 12 V:** the board's 3.3 V rail is below the meter's minimum supply, and a 5 V rail does not exist on the bare-module board. Taking the 12 V from the supply side of the P-MOSFET keeps the meter counting while the fans' rail is cut.
- **Pulse rate:** a YF-S401 gives about 5880 pulses per litre, so even 6 L/min is under 600 Hz. The 10 kΩ pull-up is fast enough for that with a few metres of cable.
- **If the count stays at zero** with water flowing, measure the yellow wire against GND: it should sit at either about 0 V or about 12 V and flip as the rotor turns slowly. If it never rises, the meter has a bare open-collector output with no pull-up inside; add 10 kΩ from yellow to red at the meter end.
- **Before connecting the meter:** D7's node should read 3.3 V. Touching the base resistor's free end to 12 V should drop it to about 0 V.
- **Wire colours** on the YF-S401 are red VCC, black GND, yellow signal. As with the fans, confirm them against the part's datasheet before plugging it in.

**12 V switch (one for all three fans)**

A P-MOSFET sits high-side, in the fans' +12 V line (see [§1](#power)). D0 switches it through an NPN driver, because the gate sits near 12 V, out of reach of D0's 3.3 V.

```
12 V ─────────────────────────────┬────────── S   P-MOSFET (IRF9540N / IRF4905 / IRF9Z34N)
                                  │
                              [ 10 kΩ ]
                                  │
                                  ├────────── G
                                  │
                                  │           D ──────┬──── pin 2 (+12 V) of fans 1, 2, 3
3.3 V ──[ 10 kΩ ]──┐              │                   │
                   │              C                  ─┴─  1N5819 / 1N4007
D0 ────────────────┴──[ 4.7 kΩ ]─ B   NPN             ▲   stripe (cathode) up, toward D
                                  E   2N3904 / BC547  │
                                  │                   │
GND ──────────────────────────────┴───────────────────┴──── supply −, ESP GND, pin 1 of fans 1, 2, 3
```

- **Fans on:** D0 is high, or undriven and held up by the 10 kΩ pull-up during boot and reset (it then sits at about 1.5 V, enough for the NPN). The NPN conducts and pulls the gate to GND, so Vgs ≈ −12 V and the MOSFET is on.
- **Fans off:** D0 is low. The NPN is off, the gate's 10 kΩ pulls it up to the source, and the MOSFET is off.
- **MOSFET orientation:** source goes to the 12 V supply, drain to the fans. Reversed, its built-in body diode passes 12 V all the time and the fans never stop.
- **MOSFET choice:** its gate sees the full −12 V, so pick one rated **Vgs ±20 V**, with Rds(on) specified at −10 V. The IRF9540N, IRF4905 and IRF9Z34N all qualify, and at 1 A they dissipate ~0.1 W without a heatsink. Small SMD parts such as the AO3401 are rated only ±12 V.
- **Pinouts:** pin order differs between part numbers. TO-220 IRF parts are G-D-S looking at the label; a 2N3904 is E-B-C looking at the flat face, and a BC547 is C-B-E. Check the datasheet.
- **The diode** clamps the negative spike from the wiring and motor inductance when the switch opens.
- **Known gap:** if the board itself loses power (e.g. a dead buck converter), the pull-up loses its 3.3 V too. The fans then stop instead of running at full speed.

**Power:**
- The 12 V supply feeds the buck converter input and the switch input: the MOSFET source.
- The same unswitched 12 V feeds the flow meter's VCC, so it counts while the fans are off.
- The switch output feeds all the fans' pin 2 lines: the MOSFET drain.
- The buck converter's 5 V output feeds the board's 5 V/VIN pin.
- All grounds are common.

---

## 6. Parts list

| Qty | Part | Notes |
|---|---|---|
| 1 | ESP8266 board (Wemos D1 mini or NodeMCU) | |
| 1 | 12 V DC supply | ≥ sum of fan currents + margin |
| 1 | Polyfuse MF-R250 | PCB version only: resettable fuse on the 12 V input, 2.5 A hold, radial, 5.1 mm pitch |
| 1 | 1N5401 diode | PCB version only: across the fused 12 V input, cathode to +12 V, so a reversed supply trips the fuse |
| 1 | Buck converter 12 V → 5 V | Feeds the board |
| 1 | NPN 2N3904 / BC547 (or 2N7000 / BSS138) | PWM driver, shared by the three fans |
| 1 | 1 kΩ resistor | NPN base resistor (not needed with a MOSFET) |
| 3 | 10 kΩ resistor | Tach pull-ups (optional with `INPUT_PULLUP`) |
| 3 | 1 kΩ resistor | Optional tach series protection |
| 3 | 10 nF capacitor | Optional tach filtering |
| 2 | DS18B20 | Temperature sensors, radiator inlet and outlet |
| 1 | 4.7 kΩ resistor | 1-Wire pull-up |
| 1 | Hall-effect flow meter, YF-S401 or similar | 5–24 V, 0.3–6 L/min, 1/4-inch fittings, about 5880 pulses per litre |
| 1 | NPN 2N3904 / BC547 | Flow meter level shifter on D7 |
| 2 | 10 kΩ resistor | Its base resistor and the D7 pull-up |
| 3 | 4-pin PC fan headers | 2.54 mm pitch, keyed |
| 1 | NPN 2N3904 / BC547 | 12 V switch driver on D0 |
| 1 | 4.7 kΩ resistor | Driver base resistor |
| 1 | 10 kΩ resistor | D0 pull-up to 3.3 V |
| 1 | 1N5819 or 1N4007 diode | Across the switched 12 V, cathode to fan pin 2 |
| 1 | P-MOSFET IRF9540N / IRF4905 / IRF9Z34N | 12 V switch; Vgs rating ±20 V |
| 1 | 10 kΩ resistor | MOSFET gate to source |

---

## 7. Firmware (Arduino core for ESP8266)

Libraries: **OneWire**, **DallasTemperature**.

The fan curve runs at 30 % up to 30 °C and ramps linearly to 100 % at 50 °C. If the sensor is missing or fails, the fans run at full speed.

```cpp
#include <OneWire.h>
#include <DallasTemperature.h>

// ---- Pins ----
const uint8_t PWM_PIN     = 12;            // D6 → one transistor → pin 4 of every fan
const uint8_t TACH_PIN[3] = {5, 4, 14};    // D1, D2, D5 ← fan pin 3 (pull-up to 3.3 V)
const uint8_t ONEWIRE_PIN = 2;             // D4 ← DS1820 DQ (4.7 kΩ to 3.3 V)

// ---- Fan curve ----
const int T_LOW = 30,   T_HIGH = 50;       // °C
const int PCT_MIN = 30, PCT_MAX = 100;     // %

// ---- Tach counting ----
volatile uint32_t pulses[3];
void IRAM_ATTR t0() { pulses[0]++; }
void IRAM_ATTR t1() { pulses[1]++; }
void IRAM_ATTR t2() { pulses[2]++; }
void (*isr[3])() = {t0, t1, t2};

OneWire oneWire(ONEWIRE_PIN);
DallasTemperature sensors(&oneWire);

void setFan(int pct) {                     // inverted by the transistor; one line feeds all three fans
  analogWrite(PWM_PIN, 255 - pct * 255 / 100);
}

void setup() {
  Serial.begin(115200);
  analogWriteFreq(25000);                  // 25 kHz per fan spec
  analogWriteRange(255);

  pinMode(PWM_PIN, OUTPUT);
  setFan(PCT_MAX);
  for (int i = 0; i < 3; i++) {
    pinMode(TACH_PIN[i], INPUT);           // use INPUT_PULLUP if no external resistor
    attachInterrupt(digitalPinToInterrupt(TACH_PIN[i]), isr[i], FALLING);
  }

  sensors.begin();
  sensors.setWaitForConversion(false);     // non-blocking conversions
  sensors.requestTemperatures();
}

void loop() {
  static uint32_t last = millis();
  uint32_t now = millis();
  if (now - last < 1000) return;
  uint32_t dt = now - last;
  last = now;

  float t = sensors.getTempCByIndex(0);
  sensors.requestTemperatures();           // start next conversion

  int pct = PCT_MAX;                       // sensor missing → full speed
  if (t != DEVICE_DISCONNECTED_C) {
    pct = constrain(map((long)t, T_LOW, T_HIGH, PCT_MIN, PCT_MAX), PCT_MIN, PCT_MAX);
  }

  Serial.printf("Temp %.1f °C -> %d %% |", t, pct);
  setFan(pct);
  for (int i = 0; i < 3; i++) {
    noInterrupts(); uint32_t p = pulses[i]; pulses[i] = 0; interrupts();
    Serial.printf(" Fan%d %u RPM", i + 1, (unsigned)(p * 30000UL / dt));
  }
  Serial.println();
}
```

---

## 8. Caveats checklist

- [ ] Grounds of 12 V supply, buck converter, ESP and fans are common
- [ ] Tach pull-ups go to **3.3 V**, never 12 V
- [ ] Each fan model's tach line verified as open-collector (multimeter test)
- [ ] Nothing wired to GPIO15 (D8), which is free here, pulls it high at boot
- [ ] No tach lines on GPIO0 / GPIO2
- [ ] PWM duty inverted in software when using the transistor driver
- [ ] Expect a minimum speed instead of a full stop at 0 % on many fans; the D0 switch cuts their 12 V instead
- [ ] 12 V switch is high-side: MOSFET source on the supply, drain to the fans
- [ ] P-MOSFET rated Vgs ±20 V
- [ ] D0 pulled **up** to 3.3 V with 10 kΩ
- [ ] D0 isn't bridged to RST
- [ ] DS18B20s powered from VDD (not parasite mode)
- [ ] The flow meter's output never reaches a GPIO directly: it swings to the meter's supply
- [ ] The flow meter is fed from the unswitched 12 V, not the fans' switched rail

---

## 9. Alternatives and next steps

- **ESPHome / Home Assistant:** the same hardware can be configured in YAML with an `esp8266_pwm` output at 25 kHz (`inverted: true` for the transistor driver) driving a speed fan, a `pulse_counter` sensor per tach pin, and a `dallas_temp` sensor on GPIO2.
- **ESP32:** worth switching if more peripherals are needed. It has hardware PWM (LEDC) at 25 kHz with clean timing, hardware pulse counters (PCNT) for the tachs, and far more free GPIOs.
