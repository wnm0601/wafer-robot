#include <Arduino.h>
#include <util/atomic.h>
#include <stdio.h>
#include "cart_controller.h"
#include "manual_hardware_config.h"

// Default build stays locked. Manual build is separate and never uploaded here.
#ifndef CART_PHYSICAL_OUTPUT
#define CART_PHYSICAL_OUTPUT 0
#endif
#if CART_PHYSICAL_OUTPUT != 0 && CART_PHYSICAL_OUTPUT != 1
#error "CART_PHYSICAL_OUTPUT must be 0/1"
#endif

#ifndef CART_PWM_TOP
#define CART_PWM_TOP 4095
#endif
#ifndef CART_PWM_DENOMINATOR
#define CART_PWM_DENOMINATOR 200
#endif
static_assert(CART_PWM_TOP == 4095 || CART_PWM_TOP == 3199,
              "only 3906.25Hz or legacy 5000Hz bench PWM is supported");
static_assert(CART_PWM_DENOMINATOR == 200 || CART_PWM_DENOMINATOR == 255,
              "only current or legacy PWM conversion is supported");

static_assert(F_CPU == 16000000UL, "Timer1/5 plan requires a 16MHz Mega 2560");
static_assert(cart::PWM_PINS[0] == 11 && cart::PWM_PINS[1] == 44 &&
              cart::PWM_PINS[2] == 12 && cart::PWM_PINS[3] == 45,
              "PWM pin changes require matching OC1A/OC5C/OC1B/OC5B routes");
cart::Controller controller({false, CART_WHEEL_MAPPING_VERIFIED != 0,
                            CART_PHYSICAL_OUTPUT != 0, CART_PHYSICAL_LIMIT_PERCENT,
                            CART_WHEEL_CHANNELS, CART_WHEEL_SIGNS,
                            CART_OPERATOR_POWER_ACK != 0});
volatile uint32_t encoder_raw[4] = {};
char line[cart::FRAME_SIZE], response[cart::FRAME_SIZE];
size_t used = 0;
bool discard_line = false;

void apply_pwm(uint8_t channel, int output) {
  const uint16_t duty = static_cast<uint32_t>(output < 0 ? -output : output) * CART_PWM_TOP / CART_PWM_DENOMINATOR;
  // Disconnect OC at zero to avoid the Fast PWM OCR=0 narrow pulse.
  // COM1A1=7, COM5C1=3, COM1B1=5, COM5B1=5.
  // PCB M2 uses D44=OC5C; OC5A would drive D46 instead.
  uint8_t bit = channel == 0 ? 7 : channel == 1 ? 3 : 5;
  volatile uint8_t& control = channel == 0 || channel == 2 ? TCCR1A : TCCR5A;
  if (!duty || digitalRead(cart::DIR_PINS[channel]) != (output < 0 ? LOW : HIGH)) {
    control &= ~(_BV(bit) | _BV(bit-1));
    digitalWrite(cart::PWM_PINS[channel], LOW);
    digitalWrite(cart::DIR_PINS[channel], output < 0 ? LOW : HIGH);
  }
  if (channel == 0) OCR1A = duty;
  else if (channel == 1) OCR5C = duty;
  else if (channel == 2) OCR1B = duty;
  else OCR5B = duty;
  if (duty) control |= _BV(bit); // Non-inverting PWM, DIR + magnitude.
}

void apply_outputs() {
  for (uint8_t i=0; i<4; ++i) {
    int value = CART_PHYSICAL_OUTPUT ? controller.output(i) : 0;
    // M uses raw PCB channel; V is mapped inside the Controller.
    apply_pwm(i, value);
  }
}

void output_diagnostic(char* out, size_t capacity) {
  // receive() runs tick first. Apply its stop/ramp before reading back registers.
  // This never changes targets, arms, or refreshes the command lease.
  apply_outputs();
  uint16_t top1, top5, a1, b1, a5, b5, c5;
  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
    top1=ICR1; top5=ICR5; a1=OCR1A; b1=OCR1B;
    a5=OCR5A; b5=OCR5B; c5=OCR5C;
  }
  // IO1 is register readback, NOT a voltage/current/waveform measurement.
  snprintf(out, capacity,
    "IO1 %lu %u %u %u %u %u %u %u %u %u %u %u %u %u %u %u %u %u %u %d %d %d %d",
    static_cast<unsigned long>(millis()), static_cast<unsigned>(CART_PHYSICAL_OUTPUT),
    static_cast<unsigned>(CART_PWM_DENOMINATOR), top1, top5,
    TCCR1A, TCCR1B, TCCR5A, TCCR5B, a1, b1, a5, b5, c5,
    DDRB, DDRL, DDRC, PORTC, PINC,
    controller.output(0), controller.output(1), controller.output(2), controller.output(3));
}

void count_encoder(uint8_t i) {
  // Raw connector direction, x1 A rising + B level; not normalized wheel-forward sign.
  encoder_raw[i] += digitalRead(cart::ENC_B_PINS[i]) == HIGH ? 1u : UINT32_MAX;
}
void encoder1() { count_encoder(0); }
void encoder2() { count_encoder(1); }
void encoder3() { count_encoder(2); }
void encoder4() { count_encoder(3); }

void setup() {
  controller.set_output_diagnostic(output_diagnostic);
  // Low latch before OUTPUT. Hardware pull-downs/reset behavior still need verification.
  for (uint8_t i = 0; i < 4; ++i) {
    digitalWrite(cart::PWM_PINS[i], LOW); pinMode(cart::PWM_PINS[i], OUTPUT);
    digitalWrite(cart::DIR_PINS[i], LOW); pinMode(cart::DIR_PINS[i], OUTPUT);
    pinMode(cart::ENC_A_PINS[i], INPUT_PULLUP);
    pinMode(cart::ENC_B_PINS[i], INPUT_PULLUP);
  }
  // Fast PWM Timer1/5: 16MHz/(TOP+1), /1 prescaler; OC initially DISCONNECTED.
  // TOP4095=3906.25Hz default; TOP3199=5000Hz explicit legacy bench profile.
  TCCR1A = _BV(WGM11); TCCR1B = _BV(WGM13) | _BV(WGM12) | _BV(CS10);
  TCCR5A = _BV(WGM51); TCCR5B = _BV(WGM53) | _BV(WGM52) | _BV(CS50);
  ICR1 = ICR5 = CART_PWM_TOP;
  OCR1A = OCR1B = OCR5A = OCR5B = OCR5C = 0;
  attachInterrupt(digitalPinToInterrupt(cart::ENC_A_PINS[0]), encoder1, RISING);
  attachInterrupt(digitalPinToInterrupt(cart::ENC_A_PINS[1]), encoder2, RISING);
  attachInterrupt(digitalPinToInterrupt(cart::ENC_A_PINS[2]), encoder3, RISING);
  attachInterrupt(digitalPinToInterrupt(cart::ENC_A_PINS[3]), encoder4, RISING);
  // A8 must be a verified, externally driven 0..5V logic input. No pull-up guess.
  if (CART_POWER_ON_LEVEL != -1) pinMode(A8, INPUT);
  Serial.begin(115200);
  cart::frame(response, sizeof(response), "E2 - BOOT_OUTPUT_LOCKED");
  Serial.println(response);
}
void loop() {
  const uint32_t now = millis();
  int32_t counts[4];
  ATOMIC_BLOCK(ATOMIC_RESTORESTATE) {
    for (uint8_t i = 0; i < 4; ++i) counts[i] = static_cast<int32_t>(encoder_raw[i]);
  }
  controller.counts(counts);
  cart::Power power = cart::Power::Unknown;
  if (CART_PHYSICAL_OUTPUT && CART_POWER_ON_LEVEL != -1)
    power = digitalRead(A8) == CART_POWER_ON_LEVEL ? cart::Power::On : cart::Power::Off;
  controller.feedback(power, false, now); // Hard E-Stop acts through contactor feedback.
  controller.tick(now);
  apply_outputs();
  // Bound work per loop so a serial flood cannot starve the interlock.
  for (uint8_t n = 0; n < 48 && Serial.available(); ++n) {
    const char c = static_cast<char>(Serial.read());
    if (c == '\n') {
      if (!discard_line) {
        if (used && line[used - 1] == '\r') --used;
        line[used] = '\0'; controller.receive(line, millis(), response);
        apply_outputs(); Serial.println(response);
      }
      used = 0; discard_line = false;
    } else if (!discard_line) {
      if (c == '\0' || used >= sizeof(line) - 1) {
        controller.fail("RX_OVERFLOW_OR_NUL", millis()); apply_outputs(); discard_line = true; used = 0;
      } else line[used++] = c;
    }
  }
  if (controller.event(response)) Serial.println(response);
}
