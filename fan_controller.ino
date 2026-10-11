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

