#include <OneWire.h>
#include <DallasTemperature.h>
#include <EEPROM.h>
#include <ESP8266mDNS.h>
#include <WiFiManager.h>

// ---- Firmware ----
const char *FW_VERSION = "0.0.1";          // bump by hand on release
#if __has_include("git_hash.h")
#include "git_hash.h"                      // GIT_HASH, written by build.sh
#else
#define GIT_HASH "unknown"                 // built without build.sh
#endif

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

// ---- History for the graph (RAM only, cleared on reboot) ----
const int HIST_N = 360, HIST_STEP = 10;    // 1 h of 10-cycle (≈10 s) averages
struct Sample { int16_t t10; uint8_t pct; };   // t10 = °C×10, INT16_MIN = no sensor reading
Sample hist[HIST_N];                       // ~1.4 KB
int histHead, histCount;                   // next write slot, valid samples

void histAdd(float t, int pct) {           // called once per 1 s cycle
    static float tSum;
    static int nT, pctSum, n;
    if (t != DEVICE_DISCONNECTED_C) { tSum += t; nT++; }
    pctSum += pct;
    if (++n < HIST_STEP) return;
    hist[histHead] = {(int16_t)(nT ? lroundf(tSum / nT * 10) : INT16_MIN), (uint8_t)(pctSum / n)};
    histHead = (histHead + 1) % HIST_N;
    if (histCount < HIST_N) histCount++;
    tSum = 0; nT = pctSum = n = 0;
}

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

// Main page = PAGE_HEAD + snprintf'd form/footer + PAGE_SCRIPT, streamed. '%' is literal in the
// PROGMEM parts; only the snprintf part needs '%%'.
const char PAGE_HEAD[] PROGMEM = R"HTML(<!DOCTYPE html><meta charset=utf-8>
<meta name=viewport content='width=device-width'><title>Fan controller</title>
<style>input{width:4em}canvas{display:block;width:100%;max-width:720px;height:220px}
.k{display:inline-block;width:1.2em;height:3px;vertical-align:middle}</style>
<h2 id=st>…</h2><p id=fans>
<p><span class=k style=background:#e4572e></span> Temperature °C &nbsp;
<span class=k style=background:#2e86de></span> Duty % &nbsp;
<small style=color:gray>last hour, 10 s averages; dashed = ramp start/end</small>
<canvas id=cv></canvas>
)HTML";

const char PAGE_SCRIPT[] PROGMEM = R"JS(<script>
function u(){fetch('/status.json').then(r=>r.json()).then(d=>{
 st.textContent=(d.t==null?'sensor missing':d.t.toFixed(1)+' °C')+' → '+d.pct+' %';
 fans.innerHTML=d.rpm.map((r,i)=>'Fan'+(i+1)+' '+r+' RPM').join('<br>')})}
let H;
function g(){fetch('/history.json').then(r=>r.json()).then(h=>{H=h;draw()})}
function draw(){
 if(!H)return;
 const r=devicePixelRatio||1,W=cv.clientWidth,Hh=cv.clientHeight;
 cv.width=W*r;cv.height=Hh*r;
 const c=cv.getContext('2d');c.scale(r,r);
 const L=30,R=34,T=8,B=18,w=W-L-R,h=Hh-T-B,N=360,n=H.t.length;
 const v=H.t.filter(x=>x!=null).concat([H.tl,H.th]);
 const lo=Math.floor(Math.min(...v))-1,hi=lo+4*Math.ceil((Math.ceil(Math.max(...v))+1-lo)/4);
 const X=i=>L+w*(N-n+i+1)/N,Yt=x=>T+h*(hi-x)/(hi-lo),Yd=x=>T+h*(100-x)/100;
 c.font='11px sans-serif';c.lineWidth=1;c.strokeStyle='#ddd';c.fillStyle='#666';
 for(let k=0;k<=4;k++){const y=T+h*k/4;
  c.beginPath();c.moveTo(L,y);c.lineTo(L+w,y);c.stroke();
  c.textAlign='right';c.fillText(hi-(hi-lo)*k/4,L-4,y+4);
  c.textAlign='left';c.fillText(100-25*k,L+w+4,y+4)}
 [60,45,30,15,0].forEach(m=>{c.textAlign=m==60?'left':m?'center':'right';
  c.fillText(m?'-'+m+' min':'now',L+w*(1-m/60),Hh-4)});
 c.setLineDash([4,4]);c.strokeStyle='#999';
 [H.tl,H.th].forEach(x=>{c.beginPath();c.moveTo(L,Yt(x));c.lineTo(L+w,Yt(x));c.stroke()});
 c.setLineDash([]);c.lineWidth=2;
 [[H.d,Yd,'#2e86de'],[H.t,Yt,'#e4572e']].forEach(([a,Y,col])=>{
  c.strokeStyle=col;c.beginPath();let p=0;
  a.forEach((x,i)=>{if(x==null){p=0;return}p?c.lineTo(X(i),Y(x)):c.moveTo(X(i),Y(x));p=1});
  c.stroke()})}
u();g();setInterval(u,2000);setInterval(g,10000);addEventListener('resize',draw);
</script>)JS";

void handleRoot() {                        // status and graph are filled in by the script
    if (wm.getConfigPortalActive()) {      // setup AP: go straight to the network list
        wm.server->sendHeader("Location", "/wifi");
        wm.server->send(302);
        return;
    }
    char form[768];
    snprintf(form, sizeof form,
        "<form method=post action=/curve><p>"
        "Ramp <input name=tl type=number min=0 max=100 required value=%d> → "
        "<input name=th type=number min=0 max=100 required value=%d> °C<br>"
        "Duty <input name=pl type=number min=0 max=100 required value=%d> → "
        "<input name=ph type=number min=0 max=100 required value=%d> %%"
        "<p><button>Save</button> <button name=reset value=1 formnovalidate>Defaults</button></form>"
        "<p><a href=/wifi>Wi-Fi settings</a> · <a href=/info>Info / erase Wi-Fi</a>"
        "<p style=color:gray><small>Firmware v%s · %s</small>",
        curve.tLow, curve.tHigh, curve.pctMin, curve.pctMax, FW_VERSION, GIT_HASH);
    wm.server->setContentLength(CONTENT_LENGTH_UNKNOWN);   // chunked on HTTP/1.1
    wm.server->send(200, "text/html; charset=utf-8", "");
    wm.server->sendContent_P(PAGE_HEAD);
    wm.server->sendContent(form);
    wm.server->sendContent_P(PAGE_SCRIPT);
}

void handleHistory() {                     // ~3.3 KB when full, so streamed in small pieces
    auto &s = *wm.server;
    char buf[256];
    snprintf(buf, sizeof buf, "{\"step\":%d,\"tl\":%d,\"th\":%d,\"t\":[", HIST_STEP, curve.tLow, curve.tHigh);
    s.setContentLength(CONTENT_LENGTH_UNKNOWN);
    s.send(200, "application/json", "");
    s.sendContent(buf);
    for (int pass = 0; pass < 2; pass++) {   // 0: temperatures, 1: duties; oldest first
        int len = 0;
        for (int k = 0; k < histCount; k++) {
            const Sample &x = hist[(histHead - histCount + k + HIST_N) % HIST_N];
            const char *sep = k ? "," : "";
            if (pass)                    len += snprintf(buf + len, sizeof buf - len, "%s%u", sep, x.pct);
            else if (x.t10 == INT16_MIN) len += snprintf(buf + len, sizeof buf - len, "%snull", sep);
            else                         len += snprintf(buf + len, sizeof buf - len, "%s%.1f", sep, x.t10 / 10.0f);
            if (len > (int)sizeof buf - 16) { s.sendContent(buf, len); len = 0; }
        }
        if (len) s.sendContent(buf, len);
        s.sendContent(pass ? "]}" : "],\"d\":[");
    }
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
    wm.server->on("/history.json", handleHistory);
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
    histAdd(t, pct);

    Serial.printf("Temp %.1f °C -> %d %% |", t, pct);
    for (int i = 0; i < 3; i++) {
        setFan(i, pct);
        noInterrupts(); uint32_t p = pulses[i]; pulses[i] = 0; interrupts();
        lastRpm[i] = p * 30000UL / dt;
        Serial.printf(" Fan%d %u RPM", i + 1, (unsigned)lastRpm[i]);
    }
    Serial.println();
}
