# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Single-sketch Arduino firmware for an ESP8266 (Wemos D1 mini / NodeMCU) that drives three 4-pin PWM PC fans from one DS1820 temperature reading, prints each fan's RPM over serial, and serves a status page over Wi-Fi. There is no build system, test suite or CI: verification is "it compiles" plus reading the serial output and the status page on real hardware.

The Arduino IDE requires the sketch file name to match its folder, so `fan_controller.ino` cannot be renamed or moved without renaming the directory too.

## Commands

```bash
./build.sh                                # compile (args pass through to arduino-cli compile; add -v for full output)
./build.sh --upload                       # compile + flash
arduino-cli upload .                      # flash last build
arduino-cli monitor -p $PORT --config baudrate=115200
./build.sh -e                             # export .bin to ./build/<fqbn>/
./build.sh --clean
arduino-cli board list                    # find $PORT
```

Build through `./build.sh`, not bare `arduino-cli compile`. It writes the gitignored `git_hash.h` (`#define GIT_HASH "<git describe --always --dirty>"`) and then execs `arduino-cli compile "$@" .`. The sketch falls back to `GIT_HASH "unknown"` via `__has_include` when the header is absent. Don't rename it to `version.h`: the ESP8266 SDK has its own `version.h` on the include path, which wins `__has_include`, leaving `GIT_HASH` undefined. `FW_VERSION` at the top of the sketch is bumped by hand. Both appear in the status page footer.

These flagless forms depend on a `sketch.yaml` created by `arduino-cli board attach -p $PORT -b $FQBN .`. **`sketch.yaml` is not in the repo**, so on a fresh checkout either run `board attach` first or pass `-b $FQBN` (and `-p $PORT` for upload) on every command. Typical FQBN: `esp8266:esp8266:d1_mini:xtal=160,baud=921600`.

Prerequisites (once per machine): ESP8266 core from `https://arduino.esp8266.com/stable/package_esp8266com_index.json`, plus `arduino-cli lib install OneWire DallasTemperature WiFiManager@2.0.17` (tzapu). The serial monitor holds the port — close it before uploading. README.md has the full Manjaro/Arch setup and a troubleshooting table.

## Architecture

Everything lives in `fan_controller.ino`: a 1-second cooperative loop (early-returns until 1000 ms have elapsed; never blocks).

- **Index-parallel arrays.** `PWM_PIN[i]`, `TACH_PIN[i]`, `pulses[i]` and `isr[i]` all describe fan `i`. Adding or reordering a fan means touching all four, including the hand-written `t0/t1/t2` ISRs, which exist one-per-fan because `attachInterrupt` takes no argument.
- **PWM duty is inverted** (`255 - pct*255/100`). Each GPIO drives an NPN/MOSFET open-drain stage, mimicking a motherboard, so GPIO high pulls the fan's PWM line low. A fan wired directly to a GPIO instead needs the non-inverted form.
- **Failure modes default to full speed.** A missing sensor (`DEVICE_DISCONNECTED_C`) forces `PCT_FAILSAFE` (100 %, deliberately separate from the user-settable `curve.pctMax`), and an undriven fan PWM pin is pulled up internally by the fan, so fans also run full-speed during boot and reset.
- **Temperature is one cycle stale by design.** `setWaitForConversion(false)` plus "read, then request next" keeps the 750 ms DS1820 conversion off the loop.
- **A failed temperature read is retried once.** On the ESP8266, OneWire's bit-timing functions run from flash (its `IRAM_ATTR` placement is ESP32-only). Serving a web page evicts them from the instruction cache, and a cache miss mid-slot blows the DS18B20's 15 µs read window, so ~1 in 3 reads after a page load returned -127. The failed try reloads the cache and the retry succeeds. Don't remove it as redundant.
- **RPM = pulses × 30000 / dt_ms** (2 pulses per revolution). `dt` is measured, not assumed, so the reading stays correct if a cycle runs long. Counters are snapshot-and-cleared inside `noInterrupts()`.
- **The fan curve** is the `curve` struct (`tLow`/`tHigh` °C, `pctMin`/`pctMax` %), linearly mapped and clamped. It is set from the status page (`POST /curve`) and persisted with the core `EEPROM` library (one flash sector, written only on Save; a magic word guards the layout, so bump `CURVE_MAGIC` if `Curve` changes). `DEFAULT_CURVE` is used on first boot, on a bad/missing EEPROM record, and by the page's Defaults button. Every curve, loaded or posted, goes through `validCurve()`; its `tLow < tHigh` rule is what keeps `map()` from dividing by zero.
- **Wi-Fi is WiFiManager in non-blocking mode.** `wm.process()` and `MDNS.update()` sit *above* the 1 s gate in `loop()` so they run every pass; fan regulation continues while the setup AP is up. The only long block is `autoConnect()` in `setup()` (≤ `CONNECT_TIMEOUT_S`, fans already at `PCT_FAILSAFE`); `/wifi` scans and network saves also stall the loop for a few seconds, which is harmless because PWM is timer-driven and `dt` is measured.
  - There is one web server: WiFiManager's `wm.server`. It is used both for the setup AP (config portal) and on the LAN (`startWebPortal()`, started by the edge check in `loop()` once connected). Our routes go in `addRoutes()` via `setWebServerCallback`, which WiFiManager calls *before* registering its own, so our `/` shadows its menu. `handleRoot()` redirects to `/wifi` while `wm.getConfigPortalActive()` (setup AP) and otherwise sends a static page (the curve form) whose script polls `/status.json` (`handleStatus()`, built from the `last*` globals the 1 s block fills). The page must not auto-reload, or it would wipe the form while the user types. `/status.json` is named so because WiFiManager already owns `/status`.
  - Portal timeout (`PORTAL_TIMEOUT_S`) is set only when a network is already saved, and its callback restarts the board to retry it. First-time setup never times out.
  - Double reset uses RTC user memory block 0 (survives RST, not power loss) and only counts `REASON_EXT_SYS_RST`, so crashes and `ESP.restart()` don't trigger it. No GPIOs are involved.

## Hardware constraints that bind the code

`docs/esp8266-fan-controller-research.md` is the design rationale — read §4 (pin map) and §8 (caveats) before changing pins. The pin choices are forced, not stylistic:

- **GPIO15 (D8) must be low at boot**, so it is only usable as a PWM output *through a transistor*; a directly wired fan pulls it high and the board will not boot.
- **GPIO2 (D4) must be high at boot**, which the 1-Wire 4.7 kΩ pull-up satisfies — hence the DS1820 lives there, and tach lines must never go on GPIO0 or GPIO2.
- **GPIO16 (D0) has no interrupt support**, so it cannot carry a tach signal.
- All 7 signals use the only unrestricted pins (GPIO4/5/12/13/14) plus GPIO15/GPIO2. The board is pin-full: further peripherals mean moving to an ESP32.
- Tach pull-ups go to **3.3 V only**, never 12 V. Fans need a separate 12 V supply with grounds tied common.

Note: §7 of the research doc contains a copy of the firmware. `fan_controller.ino` is the source of truth; the doc copy may drift.
