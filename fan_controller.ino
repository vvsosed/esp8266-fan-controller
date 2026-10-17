#include <OneWire.h>
#include <DallasTemperature.h>
#include <ESP8266mDNS.h>
#include <WiFiManager.h>

// ---- Pins ----
const uint8_t PWM_PIN[3]  = {12, 13, 15};  // D6, D7, D8 → transistor → fan pin 4
const uint8_t TACH_PIN[3] = {5, 4, 14};    // D1, D2, D5 ← fan pin 3 (pull-up to 3.3 V)
const uint8_t ONEWIRE_PIN = 2;             // D4 ← DS1820 DQ (4.7 kΩ to 3.3 V)

// ---- Fan curve ----
const int T_LOW = 21,   T_HIGH = 30;       // °C
const int PCT_MIN = 20, PCT_MAX = 100;     // %

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
int lastPct = PCT_MAX;
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

void setFan(int i, int pct) {              // inverted by the transistor
    analogWrite(PWM_PIN[i], 255 - pct * 255 / 100);
}

void handleRoot() {
    if (wm.getConfigPortalActive()) {      // setup AP: go straight to the network list
        wm.server->sendHeader("Location", "/wifi");
        wm.server->send(302);
        return;
    }
    char temp[24] = "sensor missing";
    if (lastTemp != DEVICE_DISCONNECTED_C) snprintf(temp, sizeof temp, "%.1f &deg;C", lastTemp);

    static char page[640];
    snprintf(page, sizeof page,
        "<!DOCTYPE html><meta name=viewport content='width=device-width'>"
        "<meta http-equiv=refresh content=2><title>Fan controller</title>"
        "<h2>%s &rarr; %d %%</h2>"
        "<p>Fan1 %u RPM<br>Fan2 %u RPM<br>Fan3 %u RPM"
        "<p><a href=/wifi>Wi-Fi settings</a> &middot; <a href=/info>Info / erase Wi-Fi</a>",
        temp, lastPct, (unsigned)lastRpm[0], (unsigned)lastRpm[1], (unsigned)lastRpm[2]);
    wm.server->send(200, "text/html", page);
}

void addRoutes() {                         // runs before WiFiManager adds its routes, so ours win
    wm.server->on("/", handleRoot);
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
        setFan(i, PCT_MAX);
    }

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

    int pct = PCT_MAX;                       // sensor missing → full speed
    if (t != DEVICE_DISCONNECTED_C) {
        pct = constrain(map((long)t, T_LOW, T_HIGH, PCT_MIN, PCT_MAX), PCT_MIN, PCT_MAX);
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
