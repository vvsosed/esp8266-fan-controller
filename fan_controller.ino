#include <OneWire.h>
#include <DallasTemperature.h>
#include <EEPROM.h>
#include <ESP8266mDNS.h>
#include <WiFiManager.h>

// ---- Pins ----
const uint8_t PWM_PIN[3]  = {12, 13, 15};  // D6, D7, D8 → transistor → fan pin 4
const uint8_t TACH_PIN[3] = {5, 4, 14};    // D1, D2, D5 ← fan pin 3 (pull-up to 3.3 V)
const uint8_t ONEWIRE_PIN = 2;             // D4 ← DS1820 DQ (4.7 kΩ to 3.3 V)

// ---- Fan curve (defaults; the web page can change and save them) ----
struct Curve { int tLow, tHigh, pctMin, pctMax; };   // °C, °C, %, %
const Curve DEFAULT_CURVE = {21, 30, 20, 100};
const int PCT_FAILSAFE = 100;              // boot and sensor missing, whatever the curve says
Curve curve = DEFAULT_CURVE;

// ---- Wi-Fi ----
const char *HOSTNAME = "fan-controller";   // DHCP name + http://fan-controller.local/
const char *AP_PASS  = "fancontrol";       // setup AP password, min 8 chars; change before flashing
const int CONNECT_TIMEOUT_S = 20, PORTAL_TIMEOUT_S = 180;  // s: router join attempt (fans 100 %) / setup AP lifetime before retry

// ---- Tach counting ----
volatile uint32_t pulses[3];
void IRAM_ATTR t0() { pulses[0]++; }
void IRAM_ATTR t1() { pulses[1]++; }
void IRAM_ATTR t2() { pulses[2]++; }
void (*isr[3])() = {t0, t1, t2};

OneWire oneWire(ONEWIRE_PIN);
DallasTemperature sensors(&oneWire);
WiFiManager wm;

// ---- Last readings, served by the web page ----
float lastTemp = DEVICE_DISCONNECTED_C;
int lastPct = PCT_FAILSAFE;
uint32_t lastRpm[3];

// ---- Double reset → setup AP (RTC memory survives RST, not power loss) ----
const uint32_t DRD_MAGIC = 0xD0D0FA17, DRD_WINDOW_MS = 10000;
bool drdArmed = true;

void drdWrite(uint32_t m) { ESP.rtcUserMemoryWrite(0, &m, sizeof m); }

bool doubleReset() {                       // RST pressed again within the window
    uint32_t m = 0;
    ESP.rtcUserMemoryRead(0, &m, sizeof m);
    drdWrite(DRD_MAGIC);
    return m == DRD_MAGIC && ESP.getResetInfoPtr()->reason == REASON_EXT_SYS_RST;
}

// ---- Saved curve (EEPROM = one flash sector, written only on Save) ----
const uint32_t CURVE_MAGIC = 0xC0FE0001;   // bump when Curve changes layout
struct Saved { uint32_t magic; Curve c; };

bool validCurve(const Curve &c) {          // tLow < tHigh also keeps map() from dividing by zero
    return 0 <= c.tLow && c.tLow < c.tHigh && c.tHigh <= 100
        && 0 <= c.pctMin && c.pctMin <= c.pctMax && c.pctMax <= 100;
}

void loadCurve() {
    EEPROM.begin(sizeof(Saved));
    Saved s;
    EEPROM.get(0, s);
    curve = (s.magic == CURVE_MAGIC && validCurve(s.c)) ? s.c : DEFAULT_CURVE;
}

void saveCurve() {
    EEPROM.put(0, Saved{CURVE_MAGIC, curve});
    EEPROM.commit();
}

void printCurve() {
    Serial.printf("Curve: %d-%d °C -> %d-%d %%\n", curve.tLow, curve.tHigh, curve.pctMin, curve.pctMax);
}

void setFan(int i, int pct) {              // inverted by the transistor
    analogWrite(PWM_PIN[i], 255 - pct * 255 / 100);
}

void handleRoot() {                        // static page; status is filled in from /status.json
    if (wm.getConfigPortalActive()) {      // setup AP: go straight to the network list
        wm.server->sendHeader("Location", "/wifi");
        wm.server->send(302);
        return;
    }
    static char page[1536];
    snprintf(page, sizeof page,
        "<!DOCTYPE html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
        "<title>Fan controller</title><style>input{width:4em}</style>"
        "<h2 id=st>…</h2><p id=fans>"
        "<form method=post action=/curve><p>"
        "Ramp <input name=tl type=number min=0 max=100 required value=%d> → "
        "<input name=th type=number min=0 max=100 required value=%d> °C<br>"
        "Duty <input name=pl type=number min=0 max=100 required value=%d> → "
        "<input name=ph type=number min=0 max=100 required value=%d> %%"
        "<p><button>Save</button> <button name=reset value=1 formnovalidate>Defaults</button></form>"
        "<p><a href=/wifi>Wi-Fi settings</a> · <a href=/info>Info / erase Wi-Fi</a>"
        "<script>"
        "function u(){fetch('/status.json').then(r=>r.json()).then(d=>{"
        "st.textContent=(d.t==null?'sensor missing':d.t.toFixed(1)+' °C')+' → '+d.pct+' %%';"
        "fans.innerHTML=d.rpm.map((r,i)=>'Fan'+(i+1)+' '+r+' RPM').join('<br>')})}"
        "u();setInterval(u,2000)"
        "</script>",
        curve.tLow, curve.tHigh, curve.pctMin, curve.pctMax);
    wm.server->send(200, "text/html; charset=utf-8", page);
}

void handleStatus() {
    char t[12] = "null";                   // sensor missing
    if (lastTemp != DEVICE_DISCONNECTED_C) snprintf(t, sizeof t, "%.1f", lastTemp);
    char json[80];
    snprintf(json, sizeof json, "{\"t\":%s,\"pct\":%d,\"rpm\":[%u,%u,%u]}",
        t, lastPct, (unsigned)lastRpm[0], (unsigned)lastRpm[1], (unsigned)lastRpm[2]);
    wm.server->send(200, "application/json", json);
}

void handleCurve() {                       // form POST: validate, apply, save, back to /
    Curve c = DEFAULT_CURVE;
    if (!wm.server->hasArg("reset")) {
        c = {(int)wm.server->arg("tl").toInt(), (int)wm.server->arg("th").toInt(),
             (int)wm.server->arg("pl").toInt(), (int)wm.server->arg("ph").toInt()};
        if (!validCurve(c)) {
            wm.server->send(400, "text/html; charset=utf-8",
                "<meta charset=utf-8>Need 0 ≤ low &lt; high ≤ 100 °C and 0 ≤ min ≤ max ≤ 100 %. <a href=/>Back</a>");
            return;
        }
    }
    curve = c;
    saveCurve();
    printCurve();
    wm.server->sendHeader("Location", "/");
    wm.server->send(303);
}

void addRoutes() {                         // runs before WiFiManager adds its routes, so ours win
    wm.server->on("/", handleRoot);
    wm.server->on("/status.json", handleStatus);   // not /status: WiFiManager has one
    wm.server->on("/curve", HTTP_POST, handleCurve);
}

void startLan() {                          // joined the router: serve the pages there
    wm.startWebPortal();
    if (!MDNS.isRunning() && MDNS.begin(HOSTNAME)) MDNS.addService("http", "tcp", 80);
    Serial.printf("Web UI: http://%s/  (http://%s.local/)\n", WiFi.localIP().toString().c_str(), HOSTNAME);
}

void setup() {
    Serial.begin(115200);
    analogWriteFreq(25000);                  // 25 kHz per fan spec
    analogWriteRange(255);

    for (int i = 0; i < 3; i++) {
        pinMode(PWM_PIN[i], OUTPUT);
        pinMode(TACH_PIN[i], INPUT);           // use INPUT_PULLUP if no external resistor
        attachInterrupt(digitalPinToInterrupt(TACH_PIN[i]), isr[i], FALLING);
        setFan(i, PCT_FAILSAFE);
    }

    loadCurve();
    printCurve();

    sensors.begin();
    sensors.setWaitForConversion(false);     // non-blocking conversions
    sensors.requestTemperatures();

    char apName[24];
    snprintf(apName, sizeof apName, "FanController-%06X", ESP.getChipId());
    bool forcePortal = doubleReset();

    wm.setHostname(HOSTNAME);
    wm.setWebServerCallback(addRoutes);
    wm.setConfigPortalBlocking(false);       // loop keeps regulating fans while the AP is up
    wm.setConnectTimeout(CONNECT_TIMEOUT_S);
    wm.setAPClientCheck(true);               // don't time out while a phone is joined to the AP
    wm.setConfigPortalTimeoutCallback([] { ESP.restart(); });   // retry the saved network
    if (wm.getWiFiIsSaved()) wm.setConfigPortalTimeout(PORTAL_TIMEOUT_S);   // first setup never times out

    if (forcePortal) {
        Serial.println("Double reset: starting setup AP");
        wm.startConfigPortal(apName, AP_PASS);
    } else {
        wm.autoConnect(apName, AP_PASS);       // can't connect → starts the setup AP
    }
}

void loop() {
    wm.process();                            // setup AP / LAN pages, every pass
    MDNS.update();
    if (WiFi.isConnected() && !wm.getWebPortalActive() && !wm.getConfigPortalActive()) startLan();
    if (drdArmed && millis() > DRD_WINDOW_MS) { drdWrite(0); drdArmed = false; }

    static uint32_t last = millis();
    uint32_t now = millis();
    if (now - last < 1000) return;
    uint32_t dt = now - last;
    last = now;

    float t = sensors.getTempCByIndex(0);
    if (t == DEVICE_DISCONNECTED_C) t = sensors.getTempCByIndex(0);   // web traffic can evict OneWire from the flash cache; 2nd try runs cached
    sensors.requestTemperatures();           // start next conversion

    int pct = PCT_FAILSAFE;                  // sensor missing → full speed
    if (t != DEVICE_DISCONNECTED_C) {
        pct = constrain(map((long)t, curve.tLow, curve.tHigh, curve.pctMin, curve.pctMax), curve.pctMin, curve.pctMax);
    }
    lastTemp = t;
    lastPct = pct;

    Serial.printf("Temp %.1f °C -> %d %% |", t, pct);
    for (int i = 0; i < 3; i++) {
        setFan(i, pct);
        noInterrupts(); uint32_t p = pulses[i]; pulses[i] = 0; interrupts();
        lastRpm[i] = p * 30000UL / dt;
        Serial.printf(" Fan%d %u RPM", i + 1, (unsigned)lastRpm[i]);
    }
    Serial.println();
}
