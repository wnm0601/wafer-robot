// Actual Controller and AVR adapter, fake registers only; never opens hardware.
#include <Arduino.h>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <string>
volatile uint8_t TCCR1A=0,TCCR1B=0,TCCR5A=0,TCCR5B=0;
volatile uint8_t DDRB=0,DDRL=0,DDRC=0,PORTC=0,PINC=0;
volatile uint16_t OCR1A=0,OCR1B=0,OCR5A=0,OCR5B=0,OCR5C=0,ICR1=0,ICR5=0;
uint8_t fake_levels[70]={},fake_modes[70]={};
FakeSerial Serial;
#include "../src/main.cpp"

int main() {
  static_assert(CART_PHYSICAL_OUTPUT == 1 && cart::STALL_MS == 1500, "manual profile required");
  setup();
  unsigned seq=0, now=0;
  auto send=[&](const char* op) {
    char payload[240],wire[240],reply[240];
    snprintf(payload,sizeof(payload),"C2 0123456789abcdef %u %s",++seq,op);
    assert(cart::frame(wire,sizeof(wire),payload));
    controller.receive(wire,now,reply);
    return std::string(reply);
  };
  send("HELLO"); send("LIMIT 20"); send("POWER_ACK"); send("ARM"); send("M 3 20");
  for (now=15;now<=1500;now+=15) {
    if (now%150==0) assert(send("M 3 20").find("OK M")!=std::string::npos);
    controller.tick(now); apply_outputs();
  }
  assert(OCR1B==501 && OCR1A==0 && OCR5C==0 && OCR5B==0);
  now=1500;
  std::string io=send("IO");
  assert(io.find("OK IO IO1 0 1 255 3199 3199")!=std::string::npos);
  assert(controller.armed() && OCR1B==501);
  now=1515;
  std::string rejected=send("M 3 20"); // tick fails in the receive path itself.
  assert(rejected.find("MOTION_REJECTED STALL_NO_ENCODER")!=std::string::npos);
  assert(!controller.armed() && controller.stationary());
  assert(send("STATUS").find("OK STATUS 3 MOTION_REJECTED 0 0 20")!=std::string::npos);
  send("ESTOP"); send("STOP");
  std::string diag=send("DIAG");
  assert(diag.find("STALL_NO_ENCODER 1515 0 0 40 0 0 0 0 0")!=std::string::npos);
  assert(send("IO").find("OK IO IO1")!=std::string::npos);
  assert(OCR1A==0 && OCR1B==0 && OCR5B==0 && OCR5C==0);
  // Snapshot exposes real register mutations; it is not just expected constants.
  ICR1=123; DDRB=0;
  assert(send("IO").find("1 255 123 3199")!=std::string::npos);
  setup();
  send("POWER_ACK"); send("ARM");
  assert(send("DIAG").find("NONE 0 0 0 0 0 0 0 0 0")!=std::string::npos);
  now+=500; // diagnostic reads must not renew the motion lease.
  assert(send("DIAG").find("COMMAND_TIMEOUT")!=std::string::npos);
  assert(!controller.armed());
  puts("PASS: manual adapter OCR501, first stall preserved through rejected M/ESTOP/STOP, IO readback, rearm reset, diagnostic lease timeout; NO HARDWARE");
}
