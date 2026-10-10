#include <Arduino.h>
#include <util/atomic.h>
#include "probe_logic.h"

// Dedicated read-only diagnostic. No drive parser, ARM, M, V or PWM generation.
static_assert(F_CPU == 16000000UL, "Mega 2560 16MHz required");
constexpr uint8_t pwm[] = {11, 44, 12, 45};
constexpr uint8_t dir[] = {34, 36, 35, 37};
constexpr uint8_t irq_pins[] = {2, 3, 18, 19, 20, 21};
volatile uint32_t irq_counts[6] = {};
probe::Edges edges[probe::size];
uint32_t last_report = 0, last_scan_us = 0, max_scan_gap_us = 0;

void irq0() { ++irq_counts[0]; }
void irq1() { ++irq_counts[1]; }
void irq2() { ++irq_counts[2]; }
void irq3() { ++irq_counts[3]; }
void irq4() { ++irq_counts[4]; }
void irq5() { ++irq_counts[5]; }
void (*const handlers[])() = {irq0, irq1, irq2, irq3, irq4, irq5};

void lock_outputs() {
  // Disconnect every Timer1/5 OC output, including D44=OC5C.
  TCCR1A = 0; TCCR1B = 0; TCCR5A = 0; TCCR5B = 0;
  OCR1A = OCR1B = OCR1C = 0;
  OCR5A = OCR5B = OCR5C = 0;
  for (uint8_t i = 0; i < 4; ++i) {
    digitalWrite(pwm[i], LOW); pinMode(pwm[i], OUTPUT);
    digitalWrite(dir[i], LOW); pinMode(dir[i], OUTPUT);
    digitalWrite(14 + i, LOW); pinMode(14 + i, OUTPUT);
  }
}

void setup() {
  lock_outputs();
  Serial.begin(115200);
  if (!probe::valid_candidates()) {
    Serial.println(F("ERROR CANDIDATE_LIST"));
    while (true) { lock_outputs(); }
  }
  for (uint8_t i = 0; i < probe::size; ++i) {
    const uint8_t pin = probe::pins[i];
    pinMode(pin, probe::known_encoder(pin) ? INPUT_PULLUP : INPUT);
    edges[i].sample(digitalRead(pin) == HIGH);
  }
  for (uint8_t i = 0; i < 6; ++i)
    attachInterrupt(digitalPinToInterrupt(irq_pins[i]), handlers[i], RISING);
  Serial.println(F("ENCODER_PIN_PROBE_V1 OUTPUT_LOCKED NO_DRIVE_COMMANDS"));
  Serial.println(F("KNOWN: A=3,18,19,20 B=30,31,32,33; OTHER INPUTS MAY FLOAT"));
  Serial.println(F("P ms pin level poll_rise poll_fall irq_rise mode"));
  last_scan_us = micros();
}

void loop() {
  lock_outputs();
  const uint32_t scan_us = micros();
  const uint32_t gap = scan_us - last_scan_us;
  if (gap > max_scan_gap_us) max_scan_gap_us = gap;
  last_scan_us = scan_us;
  for (uint8_t i = 0; i < probe::size; ++i)
    edges[i].sample(digitalRead(probe::pins[i]) == HIGH);
  // Discard inbound bytes; never interpret any received text as a drive command.
  for (uint8_t n = 0; n < 32 && Serial.available(); ++n) (void)Serial.read();
  const uint32_t now = millis();
  if (now - last_report < 1000) return;
  last_report = now;
  uint32_t counts[6];
  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
    for (uint8_t i = 0; i < 6; ++i) counts[i] = irq_counts[i];
  }
  Serial.print(F("FRAME ")); Serial.print(now);
  Serial.print(F(" OUTPUT_LOCKED max_scan_gap_us=")); Serial.println(max_scan_gap_us);
  for (uint8_t i = 0; i < probe::size; ++i) {
    Serial.print(F("P ")); Serial.print(now); Serial.print(' ');
    Serial.print(probe::pins[i]); Serial.print(' ');
    Serial.print(edges[i].level ? 1 : 0); Serial.print(' ');
    Serial.print(edges[i].rising); Serial.print(' ');
    Serial.print(edges[i].falling); Serial.print(' ');
    int8_t irq = -1;
    for (uint8_t j = 0; j < 6; ++j) if (irq_pins[j] == probe::pins[i]) irq = j;
    if (irq < 0) Serial.print('-'); else Serial.print(counts[irq]);
    Serial.print(' ');
    Serial.println(probe::known_encoder(probe::pins[i]) ? F("PULLUP") : F("INPUT_FLOAT_POSSIBLE"));
  }
  Serial.println(F("END"));
}
