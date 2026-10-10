// Bounded legacy-ramp regression. No devices or GPIO are accessed.
#include "cart_controller.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

int main() {
  static_assert(cart::RAMP_STEP == 8, "compile this test with legacy ramp flags");
  cart::Controller c({false, false, true, 40, nullptr, nullptr, true});
  const char* session = "0123456789abcdef";
  unsigned seq = 0;
  char payload[240], wire[240], response[240];
  auto send = [&](const char* op, unsigned now) {
    snprintf(payload, sizeof(payload), "C2 %s %u %s", session, ++seq, op);
    assert(cart::frame(wire, sizeof(wire), payload));
    c.receive(wire, now, response);
    assert(strstr(response, " OK ") != nullptr);
  };
  send("HELLO", 0); send("LIMIT 40", 0); send("POWER_ACK", 0); send("ARM", 0);
  send("M 3 40", 0);
  for (unsigned t = 15; t <= 150; t += 15) c.tick(t);
  assert(c.output(2) == 80); // 40% command -> legacy magnitude 80/255.
  assert(c.output(0) == 0 && c.output(1) == 0 && c.output(3) == 0);
  send("STOP", 151);
  for (unsigned t = 165; t <= 300; t += 15) c.tick(t);
  assert(c.stationary() && !c.armed());
  send("POWER_ACK", 301); send("ARM", 301); send("M 3 40", 301);
  for (unsigned t = 315; t <= 330 + cart::STALL_MS && c.armed(); t += 15) {
    if (t % 150 == 0) send("M 3 40", t);
    c.tick(t);
    if (t < 315 + cart::STALL_MS) assert(c.armed());
  }
  assert(!c.armed() && c.stationary());
  assert(strcmp(c.reason(), "STALL_NO_ENCODER") == 0);
  puts("PASS: legacy ramp reaches 40% target in 150ms, STOP, stall still locks; no hardware");
  printf("STALL_MS=%lu boundary tested\n", static_cast<unsigned long>(cart::STALL_MS));
}
