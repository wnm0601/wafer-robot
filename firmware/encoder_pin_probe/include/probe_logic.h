#pragma once
#include <stdint.h>

namespace probe {
// Serial, motor and lamp pins are NEVER reconfigured as candidate inputs.
constexpr bool reserved(uint8_t pin) {
  return pin <= 1 || pin == 11 || pin == 12 ||
         (pin >= 14 && pin <= 17) || (pin >= 34 && pin <= 37) ||
         pin == 44 || pin == 45;
}
constexpr uint8_t pins[] = {
  2, 3, 4, 5, 6, 7, 8, 9, 10, 13, 18, 19, 20, 21,
  22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33,
  38, 39, 40, 41, 42, 43, 46, 47, 48, 49, 50, 51, 52, 53
};
constexpr uint8_t size = sizeof(pins) / sizeof(pins[0]);
constexpr bool known_encoder(uint8_t pin) {
  return pin == 3 || (pin >= 18 && pin <= 20) || (pin >= 30 && pin <= 33);
}
inline bool valid_candidates() {
  for (uint8_t i = 0; i < size; ++i) {
    if (reserved(pins[i]) || pins[i] > 53) return false;
    for (uint8_t j = 0; j < i; ++j) if (pins[j] == pins[i]) return false;
  }
  return true;
}
struct Edges {
  bool initialized = false;
  bool level = false;
  uint32_t rising = 0;
  uint32_t falling = 0;
  void sample(bool next) {
    if (!initialized) { initialized = true; level = next; return; }
    if (next != level) {
      if (next) ++rising;
      else ++falling;
      level = next;
    }
  }
};
}  // namespace probe
