#pragma once
#include <stdint.h>
#define F_CPU 16000000UL
#define HIGH 1
#define LOW 0
#define INPUT 0
#define OUTPUT 1
#define INPUT_PULLUP 2
#define RISING 3
#define A8 62
#define _BV(bit) (1u << (bit))
#define WGM11 1
#define WGM12 3
#define WGM13 4
#define CS10 0
#define WGM51 1
#define WGM52 3
#define WGM53 4
#define CS50 0
extern volatile uint8_t TCCR1A, TCCR1B, TCCR5A, TCCR5B;
extern volatile uint8_t DDRB, DDRL, DDRC, PORTC, PINC;
extern volatile uint16_t OCR1A, OCR1B, OCR5A, OCR5B, OCR5C, ICR1, ICR5;
extern uint8_t fake_levels[70], fake_modes[70];
inline void digitalWrite(uint8_t pin, uint8_t value) {
  fake_levels[pin] = value;
  if (pin >= 34 && pin <= 37) {
    const uint8_t bit = 37-pin;
    if (value) { PORTC |= _BV(bit); PINC |= _BV(bit); }
    else { PORTC &= ~_BV(bit); PINC &= ~_BV(bit); }
  }
}
inline int digitalRead(uint8_t pin) { return fake_levels[pin]; }
inline void pinMode(uint8_t pin, uint8_t mode) {
  fake_modes[pin] = mode;
  if (mode == OUTPUT) {
    if (pin == 11 || pin == 12) DDRB |= _BV(pin-6);
    if (pin == 44 || pin == 45) DDRL |= _BV(49-pin);
    if (pin >= 34 && pin <= 37) DDRC |= _BV(37-pin);
  }
}
inline uint32_t millis() { return 0; }
inline int digitalPinToInterrupt(uint8_t pin) {
  return pin == 2 ? 0 : pin == 3 ? 1 : pin >= 18 && pin <= 21 ? 23-pin : -1;
}
inline void attachInterrupt(int, void (*)(), int) {}
struct FakeSerial {
  void begin(unsigned long) {}
  int available() { return 0; }
  int read() { return -1; }
  void println(const char*) {}
};
extern FakeSerial Serial;
