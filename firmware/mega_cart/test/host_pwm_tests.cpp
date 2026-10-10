// Execute the REAL AVR adapter against fake registers: no serial port or motors.
#include <Arduino.h>
#include <assert.h>
#include <stdio.h>

volatile uint8_t TCCR1A = 0, TCCR1B = 0, TCCR5A = 0, TCCR5B = 0;
volatile uint8_t DDRB = 0, DDRL = 0, DDRC = 0, PORTC = 0, PINC = 0;
volatile uint16_t OCR1A = 0, OCR1B = 0, OCR5A = 0, OCR5B = 0, OCR5C = 0, ICR1 = 0, ICR5 = 0;
uint8_t fake_levels[70] = {}, fake_modes[70] = {};
FakeSerial Serial;
#include "../src/main.cpp"
#ifndef CART_PWM_TOP
#define CART_PWM_TOP 4095
#endif

int main() {
  setup();
  assert(ICR1 == CART_PWM_TOP && ICR5 == CART_PWM_TOP);
  assert(TCCR1B == (_BV(WGM13) | _BV(WGM12) | _BV(CS10)));
  assert(TCCR5B == (_BV(WGM53) | _BV(WGM52) | _BV(CS50)));
  assert(16000000UL / (1UL + ICR1) == (CART_PWM_TOP == 3199 ? 5000 : 3906));
  for (uint8_t i = 0; i < 4; ++i) {
    assert(fake_modes[cart::PWM_PINS[i]] == OUTPUT);
    assert(fake_levels[cart::PWM_PINS[i]] == LOW);
  }
  // M2 uses D44=OC5C, NOT D46=OC5A. Old code fails here.
  apply_pwm(1, 80);
  const uint16_t expected80 = 80UL * CART_PWM_TOP / CART_PWM_DENOMINATOR;
  const uint16_t expected40 = 40UL * CART_PWM_TOP / CART_PWM_DENOMINATOR;
  assert(OCR5C == expected80 && OCR5A == 0);
  assert((TCCR5A & _BV(3)) != 0 && (TCCR5A & _BV(2)) == 0);
  assert((TCCR5A & (_BV(7) | _BV(6))) == 0);
  assert(fake_levels[36] == HIGH);
  // M4 output must survive an M2 stop.
  apply_pwm(3, 40);
  assert(OCR5B == expected40 && (TCCR5A & _BV(5)) != 0);
  apply_pwm(1, 0);
  assert(OCR5C == 0 && (TCCR5A & (_BV(3) | _BV(2))) == 0);
  assert(fake_levels[44] == LOW && (TCCR5A & _BV(5)) != 0);
  apply_pwm(1, -80);
  assert(OCR5C == expected80 && fake_levels[36] == LOW);
  assert((TCCR5A & _BV(3)) != 0 && OCR5A == 0);
  apply_pwm(0, 80);
  apply_pwm(2, 40);
  assert(OCR1A == expected80 && OCR1B == expected40);
  assert((TCCR1A & _BV(7)) != 0 && (TCCR1A & _BV(5)) != 0);
  // Compile-time output lock must override controller outputs at the adapter.
  apply_outputs();
  assert(OCR1A == 0 && OCR1B == 0 && OCR5B == 0 && OCR5C == 0 && OCR5A == 0);
  assert((TCCR1A & (_BV(7) | _BV(6) | _BV(5) | _BV(4))) == 0);
  assert((TCCR5A & (_BV(7) | _BV(6) | _BV(5) | _BV(4) | _BV(3) | _BV(2))) == 0);
  // Startup must clear OC5C even if a prior register value exists.
  OCR5C = 1234;
  setup();
  assert(OCR5C == 0);
  puts("PASS: real AVR adapter M1-M4 routing, M2 OC5C, stop, reversal, channel isolation, startup");
}
