#include "probe_logic.h"
#include <assert.h>
#include <initializer_list>
#include <stdio.h>

int main() {
  assert(probe::valid_candidates());
  for (uint8_t p : {uint8_t(0), uint8_t(1), uint8_t(11), uint8_t(12),
                   uint8_t(14), uint8_t(17), uint8_t(34), uint8_t(37),
                   uint8_t(44), uint8_t(45)}) assert(probe::reserved(p));
  assert(probe::known_encoder(20) && probe::known_encoder(33));
  assert(!probe::known_encoder(21));
  probe::Edges e;
  e.sample(true);  // The initial level is NOT counted as a pulse.
  assert(e.rising == 0 && e.falling == 0 && e.level);
  e.sample(true);
  e.sample(false);
  e.sample(false);
  e.sample(true);
  assert(e.rising == 1 && e.falling == 1 && e.level);
  e.rising = UINT32_MAX;
  e.sample(false);
  e.sample(true);
  assert(e.rising == 0);  // Defined unsigned wrap, not signed overflow.
  for (int i = 0; i < 1000; ++i) { e.sample(false); e.sample(true); }
  assert(e.rising == 1000);
  puts("PASS: candidate exclusion, initial state, stable inputs, bidirectional edges, wrap");
}
