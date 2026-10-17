# fan_controller

ESP8266 firmware that drives three 4-pin PWM PC fans from a DS1820 temperature reading, reports each fan's RPM over serial, and serves a status page over Wi-Fi.

Hardware design, wiring and parts list: see [`docs/esp8266-fan-controller-research.md`](docs/esp8266-fan-controller-research.md).

---

## Quick reference

Run all commands from inside the sketch folder.

| Task | Command |
|---|---|
| Compile | `arduino-cli compile .` |
| Compile + flash | `arduino-cli compile --upload .` |
| Flash last build | `arduino-cli upload .` |
| Serial monitor | `arduino-cli monitor -p $PORT --config baudrate=115200` |
| Export `.bin` to `./build` | `arduino-cli compile -e .` |
| Clean rebuild | `arduino-cli compile --clean .` |
| Find connected boards | `arduino-cli board list` |
| Update cores/libraries | `arduino-cli update && arduino-cli upgrade` |

These short forms work after the one-time `board attach` step in [Setup](#4-attach-board-and-port-to-the-sketch). Without it, add `-b $FQBN` (and `-p $PORT` for upload).

---

## Project layout

```
fan_controller/
├── fan_controller.ino   # firmware (folder and .ino names must match)
├── sketch.yaml          # default board + port, created by `board attach`; not committed
├── README.md
├── CLAUDE.md            # guidance for Claude Code
├── .gitignore
├── docs/
│   └── esp8266-fan-controller-research.md   # hardware design, wiring, parts list
└── build/               # only if you export binaries (-e); not committed
```

---

## Hardware summary

| Signal | GPIO | Board label | Notes |
|---|---|---|---|
| Fan 1 / 2 / 3 PWM | 12 / 13 / 15 | D6 / D7 / D8 | Through NPN/MOSFET open-drain (inverted in firmware) |
| Fan 1 / 2 / 3 tach | 5 / 4 / 14 | D1 / D2 / D5 | 10 kΩ pull-up to **3.3 V** |
| DS1820 data | 2 | D4 | 4.7 kΩ pull-up to 3.3 V |

Fans run on a separate 12 V supply. All grounds must be common.

---

## Setup (once per machine, Manjaro / Arch)

### 1. Install Arduino CLI and get serial port access

```bash
sudo pacman -S arduino-cli
sudo usermod -aG uucp $USER   # log out and back in afterwards
groups                        # should now list uucp
```

### 2. Install the ESP8266 core

```bash
arduino-cli config init
arduino-cli config add board_manager.additional_urls \
  https://arduino.esp8266.com/stable/package_esp8266com_index.json
arduino-cli core update-index
arduino-cli core install esp8266:esp8266
```

### 3. Install libraries

```bash
arduino-cli lib install OneWire DallasTemperature WiFiManager@2.0.17
```

### 4. Attach board and port to the sketch

Set the board and port for your hardware:

```bash
export FQBN=esp8266:esp8266:d1_mini:xtal=160,baud=921600   # NodeMCU: esp8266:esp8266:nodemcuv2:...
export PORT=/dev/ttyUSB0                                   # check with: arduino-cli board list
```

| FQBN option | Meaning |
|---|---|
| `xtal=160` | CPU at 160 MHz (smoother software PWM) |
| `baud=921600` | Upload speed; use `115200` if uploads fail |
| `wipe=all` | Erase the entire flash on upload (use only when needed) |

List every option your board supports:

```bash
arduino-cli board details -b esp8266:esp8266:d1_mini
```

Save board and port into `sketch.yaml` so later commands need no flags:

```bash
arduino-cli board attach -p $PORT -b $FQBN .
```

### 5. Resolve `.local` names (for `http://fan-controller.local/`)

The board announces itself over mDNS. Linux resolves `.local` names only when the Avahi daemon runs and `nss-mdns` is hooked into name lookup. Manjaro usually ships both packages with the daemon disabled.

```bash
sudo pacman -S --needed avahi nss-mdns
grep '^hosts' /etc/nsswitch.conf      # must contain: mdns_minimal [NOTFOUND=return] before resolve
sudo systemctl enable --now avahi-daemon
getent hosts fan-controller.local     # once the board is on Wi-Fi: prints its IP
```

If the `hosts:` line lacks `mdns_minimal`, edit it to look like this:

```
hosts: mymachines mdns_minimal [NOTFOUND=return] resolve [!UNAVAIL=return] files myhostname dns
```

Run the `sudo` lines in a normal terminal. Claude Code's `!` prefix can't answer the password prompt.

---

## Everyday tasks

### Compile

```bash
arduino-cli compile .            # add -v for full compiler output
```

The build summary at the end shows flash and RAM usage.

### Flash

```bash
arduino-cli compile --upload .   # compile and flash in one step
arduino-cli upload .             # flash the last build without recompiling
```

Close the serial monitor first, because it holds the port.

### Serial monitor

```bash
arduino-cli monitor -p $PORT --config baudrate=115200
```

Exit with `Ctrl+C`. Expected output, once per second:

```
Temp 27.4 °C -> 30 % | Fan1 840 RPM Fan2 812 RPM Fan3 865 RPM
```

A burst of garbage right after reset is normal: the ESP8266 bootloader prints at 74880 baud.

Lines starting with `*wm:` come from WiFiManager. Once the board joins your router it prints where to find the [status page](#wi-fi):

```
Web UI: http://192.168.1.42/  (http://fan-controller.local/)
```

### Get the compiled binary

By default, builds go to the cache at `~/.cache/arduino/sketches/<HASH>/fan_controller.ino.bin` (older CLI versions use `/tmp/arduino/sketches/<HASH>/`).

```bash
arduino-cli compile -e .                  # copy binaries to ./build/<fqbn>/
arduino-cli compile --output-dir ./out .  # copy binaries to a directory of your choice
arduino-cli compile --show-properties . | grep '^build.path'   # print the cache path
```

To always export binaries:

```bash
arduino-cli config set sketch.always_export_binaries true
```

### Flash a `.bin` with esptool directly

This is useful for flashing a saved build without the sketch.

```bash
sudo pacman -S esptool
esptool.py --port $PORT --baud 460800 write_flash 0x0 build/*/fan_controller.ino.bin
```

### Erase the flash completely

Use this before flashing if the board behaves oddly after flashing other firmware.

```bash
esptool.py --port $PORT erase_flash
# or, through Arduino CLI, during upload:
arduino-cli upload -b $FQBN,wipe=all -p $PORT .
```

### Identify the chip and flash size

```bash
esptool.py --port $PORT flash_id
```

### Change the fan curve

Edit the constants at the top of `fan_controller.ino`, then compile and flash:

```cpp
const int T_LOW = 30,   T_HIGH = 50;     // °C: ramp starts / reaches max
const int PCT_MIN = 30, PCT_MAX = 100;   // % duty at T_LOW / T_HIGH
```

---

## Wi-Fi

Your network's name and password are never in the source. WiFiManager stores them in the ESP's own flash.

### First-time setup

1. Flash the board. With no network saved, it starts an access point named `FanController-XXXXXX` (the chip ID).
2. Join it from a phone or laptop. The password is `AP_PASS` in `fan_controller.ino` (default `fancontrol`).
3. A setup page opens by itself (otherwise browse to `http://192.168.4.1/`). Pick your network, enter its password, Save.
4. The access point shuts down and the board joins your router. Serial prints the `Web UI:` line.

The fans keep following the temperature the whole time the access point is up.

### Status page

Open `http://fan-controller.local/` (needs [mDNS on your PC](#5-resolve-local-names-for-httpfan-controllerlocal)) or the IP from serial. It shows the temperature, fan duty and each fan's RPM, refreshing every 2 s, plus links to:

| Page | Use |
|---|---|
| `/wifi` | Switch to a different network |
| `/info` | Chip details, and **Erase WiFi config** to forget the network (the board reboots into setup) |

### Getting back into setup

- **Automatically:** if the saved network can't be reached at boot, the board tries for 20 s (fans at 100 %), then opens the setup access point for 3 minutes, then restarts and tries again. The access point stays up while a device is joined to it.
- **Double reset:** press RST, then press it again within 10 s. The setup access point opens with the same 3-minute timeout. Unplugging power doesn't count; it must be the RST button.

The timeouts are `CONNECT_TIMEOUT_S` and `PORTAL_TIMEOUT_S` at the top of `fan_controller.ino`.

### Security

- `AP_PASS` is committed in the source, so change it before flashing if the repo is shared. It must be at least 8 characters.
- The status and Wi-Fi pages on your LAN have no login. Anyone on your network can open them and change or erase the Wi-Fi settings.

---

## Maintenance

```bash
arduino-cli update && arduino-cli upgrade   # refresh indexes, upgrade core + libraries
arduino-cli core list                       # installed cores and versions
arduino-cli lib list                        # installed libraries
arduino-cli cache clean                     # wipe the build cache
arduino-cli version
```

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `Permission denied: /dev/ttyUSB0` | Not in `uucp` group yet. Run the `usermod` command from Setup, then log out and back in |
| Board missing from `board list` | Charge-only USB cable; check `dmesg -w` while plugging in (expect `ch341` or `cp210x`). If `brltty` is installed it can grab CH340 adapters: `sudo pacman -Rns brltty` |
| `Timed out waiting for packet header` | Lower upload speed (`baud=115200`). If it persists, hold FLASH and tap RESET to enter the bootloader manually |
| `Port busy` / upload fails right away | Serial monitor still open; close it |
| Board doesn't boot with hardware attached | GPIO15 pulled high (fan wired directly instead of through a transistor), or GPIO0/GPIO2 held low |
| Fans always at 100 % | Sensor not found (`-127 °C` in the log): check the DS1820 wiring and 4.7 kΩ pull-up. Also check whether a fan is wired directly without a transistor: then the PWM is not inverted and `setFan()` needs `analogWrite(pin, pct * 255 / 100)` |
| Occasional single `-127 °C` reading, fans jump to 100 % for a second | The firmware already retries a failed read once, because web traffic can disturb 1-Wire timing on the ESP8266. If it still shows up, check the DS1820 wiring, the 4.7 kΩ pull-up and the cable length |
| RPM reads 0 | Missing tach pull-up, fan not powered, or grounds not common |
| RPM jumps around | Add a 10 kΩ external pull-up (instead of `INPUT_PULLUP`) and/or 10 nF from tach pin to GND |
| A fan reads ~760,000 RPM | Its tach pin is counting the 25 kHz PWM (760,000 ÷ 30 ≈ 25,000 pulses/s), so it's shorted to a PWM line. Look for a solder bridge between neighbouring header pins (D5 sits next to D6 on the D1 mini) or a tach wire touching a transistor collector (fan pin 4). If unplugging the fan doesn't change the reading, the short is on the board |
| Wi-Fi flaky or won't connect | A tach pin shorted to PWM (row above) fires 25,000 interrupts per second and starves Wi-Fi. Fix that first |
| Setup access point appears unexpectedly | A second reset within 10 s of boot counted as a [double reset](#getting-back-into-setup). Opening the serial monitor right after flashing can do this. Press RST once and wait |
| `fan-controller.local` doesn't resolve | Usually `avahi-daemon` isn't running (`systemctl is-active avahi-daemon`). See [Setup step 5](#5-resolve-local-names-for-httpfan-controllerlocal). If it runs and still fails, a firewall may be blocking UDP 5353. Or use the IP from serial |
| Status page unreachable after changing network | The board couldn't join the new network (wrong password, or out of range). Press RST: if the saved network still can't be reached, it falls back to the setup access point after 20 s |

---

## .gitignore

```
build/
out/
sketch.yaml
```

`sketch.yaml` is ignored because its `default_port` is specific to one machine. Each
checkout creates its own with the `board attach` step in [Setup](#4-attach-board-and-port-to-the-sketch),
or passes `-b $FQBN` and `-p $PORT` explicitly.
