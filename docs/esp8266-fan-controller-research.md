# ESP8266 Three-Fan Controller with DS1820 Temperature Sensor

*Design notes, 10 October 2026*

## Summary

- An ESP8266 board (Wemos D1 mini / NodeMCU) **can control three standard 4-pin PWM PC fans** and read all three tachometers. The fans need their own 12 V supply, and the ESP only provides the control signals.
- **PWM:** about 25 kHz, open-drain. The most robust option is one small NPN transistor or N-MOSFET per fan, which mimics a motherboard and inverts the signal; invert the duty cycle in software.
- **Tachometers:** these **can connect directly** to GPIOs. The output is open-collector, so a pull-up to **3.3 V** (internal or an external 10 kΩ) is all that's needed.
- **DS1820:** fits on the one remaining good pin, **GPIO2 (D4)**, with a 4.7 kΩ pull-up.
- **Pin budget:** with this setup the board is fully used. Any further peripherals point toward an ESP32.

---

## 1. Driving three 4-pin PWM fans

### Fan connector pinout

| Pin | Function | Typical wire colour | Notes |
|---|---|---|---|
| 1 | GND | Black | Must be common with ESP ground |
| 2 | +12 V | Yellow | Always on; speed is **not** set by voltage |
| 3 | Tach (sense) | Green | Open-collector, 2 pulses per revolution |
| 4 | PWM control | Blue | ~25 kHz (21–28 kHz), internal pull-up inside fan |

Wire colours vary by manufacturer, so always go by pin position.

### Power

- Use a 12 V DC supply rated for the combined fan current (each fan's label lists it, usually 0.1–0.5 A), plus some margin.
- Power the ESP board from the same supply through a small **buck converter to 5 V** feeding the board's 5 V/VIN pin.
- **Tie all grounds together.** This is required for both the PWM and tach signals to work.

### PWM signal

- The fan pulls its own PWM pin up internally (to 3.3 V or 5 V depending on model). An **unconnected or undriven PWM pin means 100 % speed**, which is a useful fail-safe.
- **Recommended: open-drain driver per fan**
  - NPN (2N3904 / BC547): base → 1 kΩ → GPIO, emitter → GND, collector → fan pin 4; **or**
  - Logic-level N-MOSFET (2N7000 / BSS138): gate → GPIO, source → GND, drain → fan pin 4.
  - This keeps a 5 V fan pull-up away from the 3.3 V GPIO.
  - The signal is **inverted** (GPIO high → fan line low), so the duty cycle is inverted in software.
- **Shortcut:** wiring the GPIO directly to pin 4 often works, but it relies on the ESP's protection diodes when a fan pulls up to 5 V. **Never do this on GPIO15** (see pin budget).
- **0 % duty does not always mean stopped.** Many fans fall back to a minimum speed (~20–30 %). To guarantee a fan is off, its 12 V line has to be switched with a high-side MOSFET.

### Software PWM on the ESP8266

- The ESP8266 has no hardware PWM; the Arduino core generates it with a timer interrupt.
- `analogWriteFreq(25000)` works. Duty-cycle accuracy is limited at that frequency and Wi-Fi activity adds some jitter, but fans tolerate this well. Running the CPU at 160 MHz can help.

### Pin budget and boot-strap constraints

3 PWM + 3 tach + 1 one-wire = **7 signals**. Only five ESP8266 pins are fully free of restrictions: GPIO4, 5, 12, 13, 14.

| Pin | Boot requirement | Use here |
|---|---|---|
| GPIO15 (D8) | Must be **low** at boot (board has pull-down) | PWM output **through a transistor only**. A fan wired directly would pull it high and the board won't boot. |
| GPIO2 (D4) | Must be **high** at boot | 1-Wire bus. Its pull-up satisfies the boot condition. |
| GPIO0 (D3) | Must be **high** at boot; flash button | Left unused |
| GPIO16 (D0) | No interrupt support | Unsuitable for tach |
| GPIO1/3 (TX/RX) | Serial | Left for USB serial |

- **Do not put tach lines on GPIO0 or GPIO2.** A fan holding its tach low at reset can stop the board from booting.
- With transistor drivers the fans run at **full speed during boot**, which is a safe default.

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
- **Several sensors can share the same pin** (e.g. one per fan zone); each has a unique 64-bit address.
- **Variants:** the original DS1820 / DS18S20 reads in 0.5 °C steps. Many parts sold as "DS1820" are actually DS18B20 (up to 0.0625 °C). The DallasTemperature library handles both.
- **Non-blocking reads:** use `setWaitForConversion(false)` so a conversion (up to ~750 ms) doesn't stall the loop.

**Interaction with the tach counters:** 1-Wire is bit-banged and disables interrupts for tens of microseconds per bit. This doesn't lose tach pulses, because edge interrupts are latched in hardware and serviced as soon as interrupts are re-enabled; at ~100 pulses/s, two edges never fall inside one window. Software PWM may glitch briefly during a read, which the fans won't notice.

---

## 4. Final pin map

| Signal | GPIO | Board label | Hardware |
|---|---|---|---|
| Fan 1 PWM | GPIO12 | D6 | NPN/MOSFET open-drain |
| Fan 2 PWM | GPIO13 | D7 | NPN/MOSFET open-drain |
| Fan 3 PWM | GPIO15 | D8 | NPN/MOSFET open-drain (**mandatory** on this pin) |
| Fan 1 tach | GPIO5 | D1 | 10 kΩ to 3.3 V |
| Fan 2 tach | GPIO4 | D2 | 10 kΩ to 3.3 V |
| Fan 3 tach | GPIO14 | D5 | 10 kΩ to 3.3 V |
| DS1820 DQ | GPIO2 | D4 | 4.7 kΩ to 3.3 V |

---

## 5. Wiring per channel

**PWM driver (repeat for each fan):**

```
                    Fan pin 4 (PWM, pulled up inside the fan)
                          │
                          C
GPIO12 ──[ 1 kΩ ]──────── B   NPN (2N3904 / BC547)
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

**Power:** 12 V supply → all fan pin 2 lines and buck converter input; buck 5 V output → board 5 V/VIN; all grounds common.

---

## 6. Parts list

| Qty | Part | Notes |
|---|---|---|
| 1 | ESP8266 board (Wemos D1 mini or NodeMCU) | |
| 1 | 12 V DC supply | ≥ sum of fan currents + margin |
| 1 | Buck converter 12 V → 5 V | Feeds the board |
| 3 | NPN 2N3904 / BC547 (or 2N7000 / BSS138) | PWM drivers |
| 3 | 1 kΩ resistor | NPN base resistors (not needed with MOSFETs) |
| 3 | 10 kΩ resistor | Tach pull-ups (optional with `INPUT_PULLUP`) |
| 3 | 1 kΩ resistor | Optional tach series protection |
| 3 | 10 nF capacitor | Optional tach filtering |
| 1 | DS1820 / DS18B20 | Temperature sensor |
| 1 | 4.7 kΩ resistor | 1-Wire pull-up |
| 3 | 4-pin PC fan headers | 2.54 mm pitch, keyed |

---

## 7. Firmware (Arduino core for ESP8266)

Libraries: **OneWire**, **DallasTemperature**.

The fan curve runs at 30 % up to 30 °C and ramps linearly to 100 % at 50 °C. If the sensor is missing or fails, the fans run at full speed.

```cpp
#include <OneWire.h>
#include <DallasTemperature.h>

// ---- Pins ----
const uint8_t PWM_PIN[3]  = {12, 13, 15};  // D6, D7, D8 → transistor → fan pin 4
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

void setFan(int i, int pct) {              // inverted by the transistor
  analogWrite(PWM_PIN[i], 255 - pct * 255 / 100);
}

void setup() {
  Serial.begin(115200);
  analogWriteFreq(25000);                  // 25 kHz per fan spec
  analogWriteRange(255);

  for (int i = 0; i < 3; i++) {
    pinMode(PWM_PIN[i], OUTPUT);
    pinMode(TACH_PIN[i], INPUT);           // use INPUT_PULLUP if no external resistor
    attachInterrupt(digitalPinToInterrupt(TACH_PIN[i]), isr[i], FALLING);
    setFan(i, PCT_MAX);
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
  for (int i = 0; i < 3; i++) {
    setFan(i, pct);
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
- [ ] GPIO15 drives a transistor, never a fan directly
- [ ] No tach lines on GPIO0 / GPIO2
- [ ] PWM duty inverted in software when using transistor drivers
- [ ] Expect a minimum speed instead of a full stop at 0 % on many fans
- [ ] DS1820 powered from VDD (not parasite mode)

---

## 9. Alternatives and next steps

- **ESPHome / Home Assistant:** the same hardware can be configured in YAML with an `esp8266_pwm` output at 25 kHz (`inverted: true` for the transistor drivers) driving a speed fan, a `pulse_counter` sensor per tach pin, and a `dallas_temp` sensor on GPIO2.
- **ESP32:** worth switching if more peripherals are needed. It has hardware PWM (LEDC) at 25 kHz with clean timing, hardware pulse counters (PCNT) for the tachs, and far more free GPIOs.
