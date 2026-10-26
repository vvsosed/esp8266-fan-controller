#include <OneWire.h>
#include <DallasTemperature.h>
#include <EEPROM.h>
#include <flash_hal.h>                     // FS_PHYS_ADDR/SIZE: where the boot counter's log goes
#include <ESP8266mDNS.h>
#include <WiFiManager.h>
#include <PubSubClient.h>
#include <coredecls.h>                     // settimeofday_cb(): told when SNTP sets the clock

// ---- Firmware ----
const char *FW_VERSION = "0.0.2";          // bump by hand on release
#if __has_include("git_hash.h")
#include "git_hash.h"                      // GIT_HASH, written by build.sh
#else
#define GIT_HASH "unknown"                 // built without build.sh
#endif

// ---- Pins ----
const uint8_t PWM_PIN     = 12;            // D6 → one transistor → pin 4 of every fan (D7, D8 are free)
const uint8_t TACH_PIN[3] = {5, 4, 14};    // D1, D2, D5 ← fan pin 3 (pull-up to 3.3 V)
const uint8_t ONEWIRE_PIN = 2;             // D4 ← DS1820 DQ (4.7 kΩ to 3.3 V)
const uint8_t POWER_PIN   = 16;            // D0 → NPN → P-MOSFET on the fans' 12 V; HIGH (or undriven) = on

// ---- Fan curve (defaults; the web page can change and save them) ----
struct Curve { int tLow, tHigh, pctMin, pctMax; };   // °C, °C, %, %
const Curve DEFAULT_CURVE = {21, 30, 20, 100};
const int PCT_FAILSAFE = 100;              // boot and sensor missing, whatever the curve says
const int POWER_OFF_DELAY_S = 10;          // duty must sit at 0 % this long before the 12 V is cut...
const float POWER_HYST_C = 0.5;            // ...with the temperature this far below where the duty leaves 0 %
Curve curve = DEFAULT_CURVE;

// ---- Wi-Fi ----
char hostname[24];                         // fan-controller-<chip id>: DHCP, http://<name>.local/ and setup AP; set in setup()
const char *AP_PASS  = "fancontrol";       // setup AP password, min 8 chars; change before flashing
const int CONNECT_TIMEOUT_S = 20, PORTAL_TIMEOUT_S = 180;  // s: router join attempt (fans 100 %) / setup AP lifetime before retry

// ---- MQTT (broker set on the status page; topics under <hostname>/) ----
struct MqttCfg { char host[64]; uint16_t port; char user[32], pass[64]; };
const MqttCfg DEFAULT_MQTT = {"", 1883, "", ""};   // blank host = MQTT off
const int MQTT_STATUS_S = 5;               // s between status publishes
const uint32_t MQTT_RETRY_MIN_S = 30, MQTT_RETRY_MAX_S = 300;   // failed connects back off from 30 s to 5 min
MqttCfg mqttCfg = DEFAULT_MQTT;
uint32_t mqttLastTry, mqttRetryS;          // millis() of the last connect attempt / s to wait after it; 0 = try now

// ---- Clock (SNTP once on the LAN; for the log and the page only, never for fan control) ----
const char *NTP_SERVER = "pool.ntp.org";
const char *TIMEZONE = "EET-2EEST,M3.5.0/3,M10.5.0/4";   // POSIX TZ: Europe/Kyiv; the core's TZ.h lists others; change before flashing
bool timeSynced;                           // SNTP has set the clock this boot
uint32_t bootedAt;                         // UTC s this boot started, from the first sync; 0 = not yet known
bool bootDue;                              // the clock was set: send MQTT boot again, now with booted

// ---- Boot counter (see countBoot()) ----
// BootRec and CrashRtc are defined up here because the IDE inserts the sketch's function prototypes,
// some of which take one, just above the tach ISRs below.
struct BootRec {                           // one flash log record
    uint32_t boots, crashes;
    uint32_t crashAt, crashUp, crashWhy;   // the last crash: UTC s (0 = unknown), s it had been up, RESET_NAME index
    uint32_t check;
};
// In RTC memory: survives a reset, not a power cut. reason: set by custom_crash_callback(). at (UTC s,
// 0 = clock not set) and up (s): set every cycle by rtcBeat(), so the next boot knows when a crash came.
struct CrashRtc { uint32_t reason, magic, at, up; };
BootRec boots;                             // all boots counted, this one included, and the last crash
const char *resetReason = "unknown";       // what started this boot

// ---- Tach counting ----
volatile uint32_t pulses[3];
void IRAM_ATTR t0() { pulses[0]++; }
void IRAM_ATTR t1() { pulses[1]++; }
void IRAM_ATTR t2() { pulses[2]++; }
void (*isr[3])() = {t0, t1, t2};

OneWire oneWire(ONEWIRE_PIN);
DallasTemperature sensors(&oneWire);
WiFiManager wm;
WiFiClient net;
PubSubClient mqtt(net);

// ---- Last readings, served by the web page ----
float lastTemp = DEVICE_DISCONNECTED_C;
int lastPct = PCT_FAILSAFE;
uint32_t lastRpm[3];
bool fanPower = true;                      // 12 V rail state

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

// ---- Serial log ----
void fmtTime(char *buf, size_t n, time_t t) {   // local "2026-10-19 03:12:44"
    struct tm tm;
    strftime(buf, n, "%F %T", localtime_r(&t, &tm));
}

void fmtUp(char *buf, size_t n, uint32_t s) {   // "2 d 17:11:05", or "17:11:05" under a day
    unsigned d = s / 86400, h = s / 3600 % 24, m = s / 60 % 60;
    if (d) snprintf(buf, n, "%u d %02u:%02u:%02u", d, h, m, (unsigned)(s % 60));
    else snprintf(buf, n, "%u:%02u:%02u", h, m, (unsigned)(s % 60));
}

// Starts every log line: "#<boot> +<s since boot>.<ms> ", then the local date and time once SNTP has
// set the clock. The boot number and uptime never jump; the clock can, when SNTP corrects it.
void stamp() {
    uint64_t ms = micros64() / 1000;
    Serial.printf("#%u +%u.%03u ", (unsigned)boots.boots, (unsigned)(ms / 1000), (unsigned)(ms % 1000));
    if (!timeSynced) return;
    char s[20];
    fmtTime(s, sizeof s, time(nullptr));
    Serial.printf("%s ", s);
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

// ---- Saved curve and broker (EEPROM = one flash sector, written only on Save) ----
const uint32_t CURVE_MAGIC = 0xC0FE0001;   // bump when Curve changes layout
struct Saved { uint32_t magic; Curve c; };
const uint32_t MQTT_MAGIC = 0x4D515401;    // bump when MqttCfg changes layout
struct SavedMqtt { uint32_t magic; MqttCfg m; };
const int MQTT_AT = 64;                    // EEPROM offset of SavedMqtt: fixed, so a Curve change can't move it
static_assert(sizeof(Saved) <= MQTT_AT, "curve record overlaps the broker record");

// tLow < tHigh also keeps map() from dividing by zero; pctMax > 0 keeps a 0 → 0 % curve from
// cutting the fans' 12 V at every temperature
bool validCurve(const Curve &c) {
    return 0 <= c.tLow && c.tLow < c.tHigh && c.tHigh <= 100
        && 0 <= c.pctMin && c.pctMin <= c.pctMax && 0 < c.pctMax && c.pctMax <= 100;
}

void loadCurve() {
    Saved s;
    EEPROM.get(0, s);
    curve = (s.magic == CURVE_MAGIC && validCurve(s.c)) ? s.c : DEFAULT_CURVE;
}

void saveCurve() {
    EEPROM.put(0, Saved{CURVE_MAGIC, curve});
    EEPROM.commit();
}

void printCurve() {
    stamp();
    Serial.printf("Curve: %d-%d °C -> %d-%d %%\n", curve.tLow, curve.tHigh, curve.pctMin, curve.pctMax);
}

void loadMqtt() {
    SavedMqtt s;
    EEPROM.get(MQTT_AT, s);
    if (s.magic != MQTT_MAGIC) return;     // never saved: DEFAULT_MQTT, off
    mqttCfg = s.m;
    mqttCfg.host[sizeof mqttCfg.host - 1] = mqttCfg.user[sizeof mqttCfg.user - 1] = mqttCfg.pass[sizeof mqttCfg.pass - 1] = 0;
}

void saveMqtt() {
    SavedMqtt s;
    memset(&s, 0, sizeof s);               // padding too, so an unchanged Save compares equal and writes nothing
    s.magic = MQTT_MAGIC;
    s.m = mqttCfg;
    EEPROM.put(MQTT_AT, s);
    EEPROM.commit();
}

const char *broker() {                     // host:port, in a static buffer
    static char b[sizeof mqttCfg.host + 6];
    snprintf(b, sizeof b, "%s:%u", mqttCfg.host, mqttCfg.port);
    return b;
}

void printMqtt() {
    stamp();
    if (mqttCfg.host[0]) Serial.printf("MQTT: %s%s\n", broker(), mqttCfg.user[0] ? " with login" : "");
    else Serial.println("MQTT: off");
}

// ---- Boot counter, for watching stability ----
// Each boot appends a record to a log in two flash sectors of its own: the last two of the filesystem
// area, which this sketch doesn't use and an OTA update doesn't touch. A record goes into erased flash,
// so it needs no erase; a sector is erased only when the other one is full, once per LOG_N boots. The
// newest record is the valid one with the most boots in either sector, so a power cut during a write
// or an erase loses that one boot at most. The curve/broker sector stays Save-only. Every record carries
// the last crash forward, so it outlives later boots and power cuts.
const uint32_t BOOTS_MAGIC = 0xB0070003;   // bump when BootRec changes layout
const int LOG_N = SPI_FLASH_SEC_SIZE / sizeof(BootRec);   // records per sector (170)
const int CRASH_RTC = 32;                  // RTC block of CrashRtc: an OTA update overwrites blocks 0-31
const uint32_t CRASH_MAGIC = 0xC7A5B007;   // RTC holds random bits after power-on
// By REASON_*, then ours. The index is kept in flash as crashWhy, so only ever append.
// Shorter than ESP.getResetReason()'s "Software/System restart", "External System" etc.
const char *const RESET_NAME[] = {"power on", "hardware watchdog", "exception", "software watchdog",
                                  "restart", "deep-sleep wake", "reset pin", "panic", "unknown"};
const uint32_t RESET_PANIC = 7, RESET_UNKNOWN = 8;

uint32_t logAddr(int sec, int i) {         // flash address of record i in log sector sec (0 or 1)
    return FS_PHYS_ADDR + FS_PHYS_SIZE - (2 - sec) * SPI_FLASH_SEC_SIZE + i * sizeof(BootRec);
}

BootRec readRec(int sec, int i) {
    BootRec b;
    ESP.flashRead(logAddr(sec, i), (uint32_t *)&b, sizeof b);
    return b;
}

// A torn write leaves some bits unprogrammed, in no set order. A plain XOR check would pass if the same
// bit were missing from a field and check, so each word goes through murmur3's finalizer: one changed
// bit flips about half.
uint32_t recCheck(const BootRec &b) {
    const uint32_t w[] = {b.boots, b.crashes, b.crashAt, b.crashUp, b.crashWhy};
    uint32_t h = BOOTS_MAGIC;
    for (uint32_t x : w) {
        h = (h ^ x) * 0x9E3779B1;
        h ^= h >> 16; h *= 0x85EBCA6B;
        h ^= h >> 13; h *= 0xC2B2AE35;
        h ^= h >> 16;
    }
    return h;
}

bool recErased(const BootRec &b) {
    return (b.boots & b.crashes & b.crashAt & b.crashUp & b.crashWhy & b.check) == 0xFFFFFFFF;
}
bool recValid(const BootRec &b) { return !recErased(b) && b.check == recCheck(b) && b.crashes <= b.boots; }

// The core calls this on an exception, soft watchdog or panic, just before it restarts; the hardware
// watchdog resets without it. It is the only sign of a panic (abort, failed assert, out of memory),
// whose reset reason doesn't say crash. REASON_DEFAULT_RST here is the SDK restarting itself, not a
// crash. Direct stores, not an SDK call: the program is already broken.
extern "C" void custom_crash_callback(struct rst_info *ri, uint32_t, uint32_t) {
    if (ri->reason == REASON_DEFAULT_RST) return;
    RTC_USER_MEM[CRASH_RTC + offsetof(CrashRtc, reason) / 4] = ri->reason;
    RTC_USER_MEM[CRASH_RTC + offsetof(CrashRtc, magic) / 4] = CRASH_MAGIC;
}

void rtcBeat() {                           // every cycle: the time and uptime a crash would have
    CrashRtc c = {0, CRASH_MAGIC, timeSynced ? (uint32_t)time(nullptr) : 0, (uint32_t)(micros64() / 1000000)};
    ESP.rtcUserMemoryWrite(CRASH_RTC, (uint32_t *)&c, sizeof c);
}

// Sets resetReason and why (its RESET_NAME index) and gets the previous run's RTC record (prev.magic !=
// CRASH_MAGIC: lost, as at power-on); true if this boot followed a crash. After an exception or soft
// watchdog the SDK keeps reporting that reason for later plain restarts, so those count only with the
// crash handler's record. The hardware watchdog skips the handler, so its reason alone counts.
bool whyBoot(uint32_t &why, CrashRtc &prev) {
    ESP.rtcUserMemoryRead(CRASH_RTC, (uint32_t *)&prev, sizeof prev);
    CrashRtc arm = {0, CRASH_MAGIC, 0, 0}; // this run's: up 0 until the first rtcBeat()
    ESP.rtcUserMemoryWrite(CRASH_RTC, (uint32_t *)&arm, sizeof arm);
    uint32_t crash = prev.magic == CRASH_MAGIC ? prev.reason : 0;   // the handler's reason; 0 = it didn't run
    uint32_t r = ESP.getResetInfoPtr()->reason;
    if (crash) why = crash <= REASON_SOFT_WDT_RST ? crash : RESET_PANIC;   // panics pass 253/254
    else if (r == REASON_EXCEPTION_RST || r == REASON_SOFT_WDT_RST) why = REASON_SOFT_RESTART;   // a stale reason
    else why = r <= REASON_EXT_SYS_RST ? r : RESET_UNKNOWN;
    resetReason = RESET_NAME[why];
    return crash || r == REASON_WDT_RST;
}

void countBoot() {                         // early in setup(), so every log line has the boot number
    uint32_t why;
    CrashRtc prev;
    bool crash = whyBoot(why, prev);
    bool logged = FS_PHYS_SIZE >= 2 * SPI_FLASH_SEC_SIZE;   // false: a flash layout without a filesystem area
    BootRec last = {};                     // newest record so far; none: start in sector 0
    int sec = 0, at = -1;
    if (logged)
        for (int s = 0; s < 2; s++)
            for (int i = 0; i < LOG_N; i++) {
                BootRec b = readRec(s, i);
                if (recValid(b) && b.boots > last.boots) { last = b; sec = s; at = i; }
            }
    boots = last;                          // the last crash carries forward
    boots.boots++;
    if (crash) {
        bool known = prev.magic == CRASH_MAGIC;
        boots.crashes++;
        boots.crashAt = known ? prev.at : 0;
        boots.crashUp = known ? prev.up : 0;
        boots.crashWhy = why;
    }
    boots.check = recCheck(boots);
    if (logged) {
        int next = at + 1;                 // first erased slot after it; a torn write leaves one that isn't
        while (next < LOG_N && !recErased(readRec(sec, next))) next++;
        if (next == LOG_N) {               // full: move to the other sector
            sec ^= 1;
            next = 0;
            ESP.flashEraseSector(logAddr(sec, 0) / SPI_FLASH_SEC_SIZE);
        }
        if (!ESP.flashWrite(logAddr(sec, next), (uint32_t *)&boots, sizeof boots)) {
            stamp();
            Serial.println("Boot counter: flash write failed");
        }
    }
    stamp();
    if (logged) Serial.printf("Boot %u, %u crashes; this one: %s", (unsigned)boots.boots, (unsigned)boots.crashes, resetReason);
    else Serial.printf("Boot counter off (no filesystem area); this boot: %s", resetReason);
    char s[24];
    if (prev.magic == CRASH_MAGIC) { fmtUp(s, sizeof s, prev.up); Serial.printf(" after %s up", s); }
    if (crash && boots.crashAt) { fmtTime(s, sizeof s, boots.crashAt); Serial.printf(", at %s", s); }
    Serial.println();
}

int curvePct(float t) {                    // whole degrees; the core's map() rounds
    long p = map((long)t, curve.tLow, curve.tHigh, curve.pctMin, curve.pctMax);   // constrain() is a macro that
    return constrain(p, curve.pctMin, curve.pctMax);                              // would run map() up to 3 times
}

void setFan(int pct) {                     // inverted by the transistor; one line feeds all three fans
    analogWrite(PWM_PIN, 255 - pct * 255 / 100);
}

// Fans don't stop at 0 % PWM, so 0 % cuts their 12 V. The curve leaves 0 % at a whole degree, and
// sensor noise there must not toggle the rail: it comes on at once, but goes off only after the
// curve gives 0 % even POWER_HYST_C warmer for POWER_OFF_DELAY_S cycles in a row. A failed read
// (pct = PCT_FAILSAFE) powers the fans for that cycle only and leaves the count alone.
void setFanPower(float t, int pct) {       // called once per 1 s cycle
    static bool on = true;                 // updated from valid readings only
    static int coldFor;                    // consecutive cycles cold enough to cut
    if (t != DEVICE_DISCONNECTED_C) {
        coldFor = curvePct(t + POWER_HYST_C) ? 0 : min(coldFor + 1, POWER_OFF_DELAY_S);
        if (pct) on = true;
        else if (coldFor == POWER_OFF_DELAY_S) on = false;
    }
    fanPower = on || pct;
    digitalWrite(POWER_PIN, fanPower ? HIGH : LOW);
}

const int STATUS_N = 288;                  // statusJson() buffer; with both parts its worst case is 267 bytes with the NUL
const int JSON_LIVE = 1, JSON_BOOT = 2;    // statusJson() parts
// A JSON object of the parts asked for: /status.json has both, MQTT one per topic. LIVE: the live numbers,
// uptime (s) and clock (UTC s; null until SNTP has set it). BOOT: boots, when this one started (UTC s; null
// until the first sync), why, and the last crash. boots + up order everything, as neither jumps. Each part
// is written straight into buf ending in a comma, which the closing brace overwrites; past n, the JSON is
// cut short.
void statusJson(char *buf, size_t n, int parts) {
    int len = snprintf(buf, n, "{");
    if (parts & JSON_LIVE) {
        char t[12] = "null", now[12] = "null";
        if (lastTemp != DEVICE_DISCONNECTED_C) snprintf(t, sizeof t, "%.1f", lastTemp);   // else sensor missing
        if (timeSynced) snprintf(now, sizeof now, "%u", (unsigned)time(nullptr));
        len += snprintf(buf + len, n - len, "\"t\":%s,\"pct\":%d,\"pwr\":%d,\"rpm\":[%u,%u,%u],\"up\":%u,\"time\":%s,",
            t, lastPct, fanPower, (unsigned)lastRpm[0], (unsigned)lastRpm[1], (unsigned)lastRpm[2],
            (unsigned)(micros64() / 1000000), now);
    }
    if ((parts & JSON_BOOT) && len < (int)n) {
        char booted[12] = "null", at[12] = "null", crash[80] = "null";
        if (bootedAt) snprintf(booted, sizeof booted, "%u", (unsigned)bootedAt);
        if (boots.crashAt) snprintf(at, sizeof at, "%u", (unsigned)boots.crashAt);   // else crashed before the clock was set
        if (boots.crashes) snprintf(crash, sizeof crash, "{\"at\":%s,\"up\":%u,\"why\":\"%s\"}",
            at, (unsigned)boots.crashUp, RESET_NAME[min(boots.crashWhy, RESET_UNKNOWN)]);
        len += snprintf(buf + len, n - len, "\"boots\":%u,\"booted\":%s,\"reset\":\"%s\",\"crashes\":%u,\"crash\":%s,",
            (unsigned)boots.boots, booted, resetReason, (unsigned)boots.crashes, crash);
    }
    if (len < (int)n) buf[len - 1] = '}';
}

// ---- MQTT: <hostname>/ramp and /duty (retained; set via .../set), /status, /boot (retained), /online ----
const char *topic(const char *leaf) {      // <hostname>/<leaf>, in a static buffer
    static char t[48];
    snprintf(t, sizeof t, "%s/%s", hostname, leaf);
    return t;
}

// Every topic we publish retained, which the broker keeps for later subscribers. mqttLeave() erases
// these, so a new retained topic goes here too.
const char *const RETAINED[] = {"ramp", "duty", "boot", "online"};

void publishCurve() {                      // the curve in force
    char m[32];
    snprintf(m, sizeof m, "{\"low\":%d,\"high\":%d}", curve.tLow, curve.tHigh);
    mqtt.publish(topic("ramp"), m, true);
    snprintf(m, sizeof m, "{\"min\":%d,\"max\":%d}", curve.pctMin, curve.pctMax);
    mqtt.publish(topic("duty"), m, true);
}

void applyCurve(const Curve &c) {          // a valid curve from the page or MQTT; used from the next cycle
    curve = c;
    saveCurve();
    printCurve();
    publishCurve();
}

void publishStatus() {                     // not retained, so stale numbers never look live
    if (!WiFi.isConnected()) return;       // a dead link's socket still looks connected, and writing to it blocks
    char m[STATUS_N];
    statusJson(m, sizeof m, JSON_LIVE);
    mqtt.publish(topic("status"), m);
}

// At each connect, and again once the clock is set (booted). Retained, so it is there on subscribe.
void publishBoot() {
    bootDue = false;                       // first, so a sync during this publish's yield() sets it again
    char m[STATUS_N];
    statusJson(m, sizeof m, JSON_BOOT);
    mqtt.publish(topic("boot"), m, true);
}

// "key":<whole number> in a small flat JSON object: 1 = read into v, 0 = key absent,
// -1 = key present but its value isn't a whole number (a fraction, a string, junk)
int jsonInt(const char *s, const char *key, int &v) {
    char k[16];
    snprintf(k, sizeof k, "\"%s\"", key);
    const char *p = strstr(s, k);
    if (!p) return 0;
    for (p += strlen(k); isspace((unsigned char)*p); p++) {}
    if (*p++ != ':') return -1;
    char *end;
    long x = strtol(p, &end, 10);          // skips leading whitespace itself
    if (end == p) return -1;
    while (isspace((unsigned char)*end)) end++;
    if (*end != ',' && *end != '}') return -1;
    v = x;
    return 1;
}

// <hostname>/ramp/set or /duty/set: merge the keys given into the curve, then the same checks and
// save as the page's form. All or nothing: one bad key rejects the whole set. The state topics are
// republished either way, so they show what is in force.
void onMqtt(char *t, uint8_t *payload, unsigned len) {
    char msg[128];                         // copy first: publishing reuses the library's buffer
    bool fits = len < sizeof msg;          // a longer one is rejected, not cut
    len = min(len, sizeof msg - 1);
    memcpy(msg, payload, len);
    msg[len] = 0;
    Curve c = curve;
    bool ramp = !strcmp(t + strlen(hostname), "/ramp/set");
    int a = ramp ? jsonInt(msg, "low", c.tLow) : jsonInt(msg, "min", c.pctMin);
    int b = ramp ? jsonInt(msg, "high", c.tHigh) : jsonInt(msg, "max", c.pctMax);
    if (fits && a >= 0 && b >= 0 && a + b > 0 && validCurve(c)) {
        applyCurve(c);
    } else {
        stamp();
        Serial.printf("MQTT: ignored %s %s\n", t, msg);
        publishCurve();
    }
}

bool mqttConnect() {
    mqtt.setServer(mqttCfg.host, mqttCfg.port);
    const char *user = mqttCfg.user[0] ? mqttCfg.user : nullptr;
    const char *pass = user && mqttCfg.pass[0] ? mqttCfg.pass : nullptr;
    if (!mqtt.connect(hostname, user, pass, topic("online"), 0, true, "offline")) {
        stamp();
        Serial.printf("MQTT: %s failed, state %d\n", broker(), mqtt.state());
        return false;
    }
    stamp();
    Serial.printf("MQTT: connected to %s\n", broker());
    mqtt.subscribe(topic("ramp/set"));
    mqtt.subscribe(topic("duty/set"));
    publishCurve();
    publishBoot();
    mqtt.publish(topic("online"), "online", true);   // last, so whoever acts on it finds the rest current
    return true;
}

// Before the broker settings change. A clean disconnect makes the broker drop the will, so this says
// offline itself. erase (we are leaving this broker) also empties our retained topics there: an empty
// retained message deletes one. offline goes first, as watchers such as Home Assistant ignore an empty
// online. False if that erase may not have happened: not connected, or the broker didn't ack it (on a
// dead link the writes just sit in lwIP).
bool mqttLeave(bool erase) {
    bool on = mqtt.connected(), acked = false;
    if (on) {
        mqtt.publish(topic("online"), "offline", true);
        if (erase) for (const char *leaf : RETAINED) mqtt.publish(topic(leaf), "", true);
        acked = net.flush(1000);           // false after 1 s without an ack
        mqtt.disconnect();
    }
    if (!erase || !mqttCfg.host[0]) return true;
    stamp();
    Serial.printf("MQTT: left %s, %s\n", broker(),
        acked ? "topics erased" : on ? "no ack: our topics there may stay" : "not connected: any topics there stay");
    return acked;
}

// Every loop() pass: keepalive, incoming sets, the boot update after the first sync, reconnects. A
// connect blocks for up to ~6 s, so failed tries back off from MQTT_RETRY_MIN_S to MQTT_RETRY_MAX_S; a
// drop after a good connection retries at once. The wait is an unsigned millis() difference, so it
// survives the 49-day wrap.
void mqttProcess() {
    if (!mqttCfg.host[0] || !WiFi.isConnected()) return;
    if (mqtt.loop()) {                     // false while disconnected
        if (bootDue) publishBoot();        // here, as onTimeSync() can run inside a yield() mid-publish
        return;
    }
    if (mqttRetryS && millis() - mqttLastTry < mqttRetryS * 1000) return;
    mqttLastTry = millis();
    mqttRetryS = mqttConnect() ? 0 : constrain(mqttRetryS * 2, MQTT_RETRY_MIN_S, MQTT_RETRY_MAX_S);
}

// Main page = PAGE_HEAD + hostname (the title) + PAGE_TOP + snprintf'd curve form, broker form and
// footer + PAGE_SCRIPT, streamed. '%' is literal in the PROGMEM parts; only the snprintf part needs '%%'.
const char PAGE_HEAD[] PROGMEM = R"HTML(<!DOCTYPE html><meta charset=utf-8>
<meta name=viewport content='width=device-width'><title>)HTML";

const char PAGE_TOP[] PROGMEM = R"HTML(</title>
<style>input{width:4em}.w{width:10em}canvas{display:block;width:100%;max-width:720px;height:220px}
.k{display:inline-block;width:1.2em;height:3px;vertical-align:middle}</style>
<h2 id=st>…</h2><p id=fans>
<p><span class=k style=background:#e4572e></span> Temperature °C &nbsp;
<span class=k style=background:#2e86de></span> Duty % &nbsp;
<small style=color:gray>last hour, 10 s averages; dashed = ramp start/end</small>
<canvas id=cv></canvas>
)HTML";

const char PAGE_SCRIPT[] PROGMEM = R"JS(<script>
const dur=s=>(s>=86400?Math.floor(s/86400)+' d ':'')+new Date(s*1e3).toISOString().slice(11,16),
 when=s=>new Date(s*1e3).toLocaleString([],{dateStyle:'short',timeStyle:'short'});
function u(){fetch('/status.json').then(r=>r.json()).then(d=>{
 st.textContent=(d.t==null?'sensor missing':d.t.toFixed(1)+' °C')+' → '+d.pct+' %'+(d.pwr?'':' · fans off');
 fans.innerHTML=d.rpm.map((r,i)=>'Fan'+(i+1)+' '+r+' RPM').join('<br>');
 const c=d.crash;
 up.innerText='Up '+dur(d.up)+(d.booted?' since '+when(d.booted):'')+' · boots '+d.boots+' · last reset: '+d.reset
  +'\nCrashes '+d.crashes+(c?' · last '+(c.at?when(c.at):'time unknown')+', '+c.why+' after '+dur(c.up)+' up':'')})}
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
    wm.server->setContentLength(CONTENT_LENGTH_UNKNOWN);   // chunked on HTTP/1.1
    wm.server->send(200, "text/html; charset=utf-8", "");
    wm.server->sendContent_P(PAGE_HEAD);
    wm.server->sendContent(hostname);
    wm.server->sendContent_P(PAGE_TOP);
    char buf[1024];                        // the curve form, the broker form, then the footer
    snprintf(buf, sizeof buf,
        "<form method=post action=/curve><p>"
        "Ramp <input name=tl type=number min=0 max=100 required value=%d> → "
        "<input name=th type=number min=0 max=100 required value=%d> °C<br>"
        "Duty <input name=pl type=number min=0 max=100 required value=%d> → "
        "<input name=ph type=number min=1 max=100 required value=%d> %%"
        "<p><button>Save</button> <button name=reset value=1 formnovalidate>Defaults</button></form>",
        curve.tLow, curve.tHigh, curve.pctMin, curve.pctMax);
    wm.server->sendContent(buf);
    char state[32] = "off";
    if (mqttCfg.host[0] && mqtt.connected()) strcpy(state, "connected");
    else if (mqttCfg.host[0]) snprintf(state, sizeof state, "not connected (state %d)", mqtt.state());
    snprintf(buf, sizeof buf,
        "<details><summary>MQTT · %s</summary><form method=post action=/mqtt><p>"
        "Broker <input name=host class=w maxlength=63 placeholder='IP or DNS name' value='%s'> : "
        "<input name=port type=number min=1 max=65535 required value=%u><br>"
        "User <input name=user class=w maxlength=31 value='%s'> "
        "Password <input name=pass class=w type=password maxlength=63 placeholder=unchanged><br>"
        "<small style=color:gray>Detach forgets the broker and erases this board's topics on it. "
        "Topics: %s/ramp, /duty (set via …/set), /status, /boot, /online</small>"
        "<p><button>Save</button>%s</form></details>",
        state, mqttCfg.host, mqttCfg.port, mqttCfg.user, hostname, mqttCfg.host[0]
            ? " <button name=detach value=1 formnovalidate onclick=\"return confirm('Forget this broker?')\">Detach</button>" : "");
    wm.server->sendContent(buf);
    snprintf(buf, sizeof buf,
        "<p><a href=/wifi>Wi-Fi settings</a> · <a href=/info>Info / erase Wi-Fi</a>"
        "<p style=color:gray><small>%s · Firmware v%s · %s<br><span id=up></span></small>",
        hostname, FW_VERSION, GIT_HASH);
    wm.server->sendContent(buf);
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
    char json[STATUS_N];
    statusJson(json, sizeof json, JSON_LIVE | JSON_BOOT);
    wm.server->send(200, "application/json", json);
}

void handleCurve() {                       // form POST: validate, apply, save, back to /
    Curve c = DEFAULT_CURVE;
    if (!wm.server->hasArg("reset")) {
        c = {(int)wm.server->arg("tl").toInt(), (int)wm.server->arg("th").toInt(),
             (int)wm.server->arg("pl").toInt(), (int)wm.server->arg("ph").toInt()};
        if (!validCurve(c)) {
            wm.server->send(400, "text/html; charset=utf-8",
                "<meta charset=utf-8>Need 0 ≤ low &lt; high ≤ 100 °C and 0 ≤ min ≤ max ≤ 100 %, max &gt; 0. <a href=/>Back</a>");
            return;
        }
    }
    applyCurve(c);
    wm.server->sendHeader("Location", "/");
    wm.server->send(303);
}

// Broker form POST. Host and user are echoed into value='…', so they are limited to safe characters.
// A blank password keeps the saved one, but only for the same host and user, so a changed host never
// gets the old password; a blank user drops both. Detach or a blank broker saves DEFAULT_MQTT, whatever
// the other fields say.
void handleMqtt() {
    auto &s = *wm.server;
    String host = s.arg("host"), user = s.arg("user"), pass = s.arg("pass");
    host.trim();
    user.trim();
    long port = s.arg("port").toInt();
    if (s.hasArg("detach") || !host.length()) {
        host = user = pass = "";
        port = DEFAULT_MQTT.port;
    }
    bool ok = host.length() < sizeof mqttCfg.host && user.length() < sizeof mqttCfg.user
           && pass.length() < sizeof mqttCfg.pass && 0 < port && port <= 65535;
    for (char ch : host) ok &= isalnum(ch) || ch == '.' || ch == '-';
    for (char ch : user) ok &= !strchr("'\"<>&", ch);
    if (!ok) {
        s.send(400, "text/html; charset=utf-8",
            "<meta charset=utf-8>Need a broker IP or DNS name (letters, digits, . and -), port 1–65535, "
            "and a user without ' \" &lt; &gt; &amp;. <a href=/>Back</a>");
        return;
    }
    if (!user.length()) pass = "";
    else if (!pass.length() && host == mqttCfg.host && user == mqttCfg.user) pass = mqttCfg.pass;
    bool leaving = host != mqttCfg.host || port != mqttCfg.port;   // Detach or another broker: erase there
    char was[sizeof mqttCfg.host + 6] = "";   // the broker we left our topics on, for the page below
    if (!mqttLeave(leaving)) snprintf(was, sizeof was, "%s", broker());
    strncpy(mqttCfg.host, host.c_str(), sizeof mqttCfg.host);   // strncpy zero-fills the rest, so no
    strncpy(mqttCfg.user, user.c_str(), sizeof mqttCfg.user);   // tail of an older, longer value stays
    strncpy(mqttCfg.pass, pass.c_str(), sizeof mqttCfg.pass);   // in flash; lengths are checked above
    mqttCfg.port = port;
    saveMqtt();
    printMqtt();
    mqttRetryS = 0;                        // connect on the next pass
    if (was[0]) {                          // the old host passed the same check when saved, so it is safe to echo
        char m[320];
        snprintf(m, sizeof m, "<meta charset=utf-8>Saved, but the board couldn't erase its topics on %s (not "
            "connected, or no reply), so any it left there stay. The README's MQTT section shows how to erase "
            "them. <a href=/>Back</a>", was);
        s.send(200, "text/html; charset=utf-8", m);
        return;
    }
    s.sendHeader("Location", "/");
    s.send(303);
}

// Goes into the <head> of WiFiManager's own pages. Its OTA result page (/u) has no link back and
// the board reboots under it, so after a successful update this polls until we answer again and
// opens our page; replace() keeps Back from re-posting the firmware. RAM, not PROGMEM: WiFiManager
// appends it as a plain char*.
const char WM_HEAD[] = R"JS(<script>addEventListener('DOMContentLoaded',()=>{
 if(location.pathname!='/u'||!document.querySelector('.msg.S'))return;
 let p=()=>fetch('/status.json',{signal:AbortSignal.timeout(2000)}).then(()=>location.replace('/'),()=>setTimeout(p,1000));
 setTimeout(p,3000)})</script>)JS";

void addRoutes() {                         // runs before WiFiManager adds its routes, so ours win
    wm.server->on("/", handleRoot);
    wm.server->on("/status.json", handleStatus);   // not /status: WiFiManager has one
    wm.server->on("/history.json", handleHistory);
    wm.server->on("/curve", HTTP_POST, handleCurve);
    wm.server->on("/mqtt", HTTP_POST, handleMqtt);
}

void startLan() {                          // joined the router: serve the pages there
    wm.startWebPortal();
    if (!MDNS.isRunning() && MDNS.begin(hostname)) MDNS.addService("http", "tcp", 80);
    // (Re)start SNTP now that the network is up: started any earlier, its first try fails and lwIP
    // retries only after 15 s, doubling up to 150 s
    configTime(TIMEZONE, NTP_SERVER);
    stamp();
    Serial.printf("Web UI: http://%s/  (http://%s.local/)\n", WiFi.localIP().toString().c_str(), hostname);
}

// The core schedules this each time the clock is set. It runs after loop() or inside any yield() or
// delay(), such as one in the middle of an MQTT publish, so it must not publish itself.
void onTimeSync(bool sntp) {
    if (!sntp || timeSynced) return;       // the first SNTP sync only, not the hourly ones after it
    timeSynced = true;
    bootedAt = time(nullptr) - micros64() / 1000000;
    bootDue = true;                        // mqttProcess() sends boot again, now with booted
    char s[20];
    fmtTime(s, sizeof s, bootedAt);
    stamp();
    Serial.printf("Time: synced (booted %s)\n", s);
}

void setup() {
    Serial.begin(115200);
    analogWriteFreq(25000);                  // 25 kHz per fan spec
    analogWriteRange(255);

    digitalWrite(POWER_PIN, HIGH);           // GPIO16's latch takes this while still an input, so
    pinMode(POWER_PIN, OUTPUT);              // D0 never drives low; until here the 10 kΩ pull-up kept the 12 V on
    pinMode(PWM_PIN, OUTPUT);
    setFan(PCT_FAILSAFE);
    for (int i = 0; i < 3; i++) {
        pinMode(TACH_PIN[i], INPUT);           // use INPUT_PULLUP if no external resistor
        attachInterrupt(digitalPinToInterrupt(TACH_PIN[i]), isr[i], FALLING);
    }

    settimeofday_cb(onTimeSync);             // SNTP itself starts in startLan()
    setTZ(TIMEZONE);                         // the log's local time, from the boot line's crash time on
    countBoot();                             // first, so every log line has the boot number
    EEPROM.begin(MQTT_AT + sizeof(SavedMqtt));   // curve at 0, broker at MQTT_AT
    loadCurve();
    printCurve();
    loadMqtt();
    printMqtt();
    net.setTimeout(2000);                    // ms for DNS and TCP connect (5 s each by default) and...
    mqtt.setSocketTimeout(2);                // ...s for the broker's reply (15): a dead broker stalls the loop ~6 s per try
    mqtt.setBufferSize(STATUS_N + 64);       // header + topic + even both statusJson() parts; publish() quietly fails past it
    mqtt.setCallback(onMqtt);

    sensors.begin();
    sensors.setWaitForConversion(false);     // non-blocking conversions
    sensors.requestTemperatures();

    snprintf(hostname, sizeof hostname, "fan-controller-%06x", ESP.getChipId());   // unique per board, so several can share a network
    bool forcePortal = doubleReset();

    wm.setHostname(hostname);
    wm.setWebServerCallback(addRoutes);
    wm.setCustomHeadElement(WM_HEAD);        // back to / after a browser firmware update
    wm.setConfigPortalBlocking(false);       // loop keeps regulating fans while the AP is up
    wm.setConnectTimeout(CONNECT_TIMEOUT_S);
    wm.setAPClientCheck(true);               // don't time out while a phone is joined to the AP
    wm.setConfigPortalTimeoutCallback([] { ESP.restart(); });   // retry the saved network
    if (wm.getWiFiIsSaved()) wm.setConfigPortalTimeout(PORTAL_TIMEOUT_S);   // first setup never times out

    if (forcePortal) {
        stamp();
        Serial.println("Double reset: starting setup AP");
        wm.startConfigPortal(hostname, AP_PASS);
    } else {
        wm.autoConnect(hostname, AP_PASS);     // can't connect → starts the setup AP
    }
}

void loop() {
    wm.process();                            // setup AP / LAN pages, every pass
    MDNS.update();
    if (WiFi.isConnected() && !wm.getWebPortalActive() && !wm.getConfigPortalActive()) startLan();
    mqttProcess();
    if (drdArmed && millis() > DRD_WINDOW_MS) { drdWrite(0); drdArmed = false; }

    static uint32_t last = millis();
    uint32_t now = millis();
    if (now - last < 1000) return;
    uint32_t dt = now - last;
    last = now;
    rtcBeat();

    float t = sensors.getTempCByIndex(0);
    if (t == DEVICE_DISCONNECTED_C) t = sensors.getTempCByIndex(0);   // web traffic can evict OneWire from the flash cache; 2nd try runs cached
    sensors.requestTemperatures();           // start next conversion

    int pct = PCT_FAILSAFE;                  // sensor missing → full speed
    if (t != DEVICE_DISCONNECTED_C) {
        pct = curvePct(t);
    }
    lastTemp = t;
    lastPct = pct;
    histAdd(t, pct);
    setFanPower(t, pct);

    stamp();
    Serial.printf("Temp %.1f °C -> %d %%%s |", t, pct, fanPower ? "" : " (12 V off)");
    setFan(fanPower ? pct : 100);              // 12 V cut: 100 % = GPIO low, so the PWM transistor idles too
    for (int i = 0; i < 3; i++) {
        noInterrupts(); uint32_t p = pulses[i]; pulses[i] = 0; interrupts();
        lastRpm[i] = p * 30000UL / dt;
        Serial.printf(" Fan%d %u RPM", i + 1, (unsigned)lastRpm[i]);
    }
    Serial.println();

    static int cycles;
    if (++cycles % MQTT_STATUS_S == 0) publishStatus();   // no-op while disconnected
}
