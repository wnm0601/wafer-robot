#include "cart_controller.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <string>

static unsigned checks = 0;
#define CHECK(expr) do { assert(expr); ++checks; } while (false)
struct Fixture {
  cart::Controller c;
  uint32_t id = 1, now = 0;
  char response[cart::FRAME_SIZE];
  explicit Fixture(bool sim = true, bool mapping = false, bool manual=false, int cap=0,
                   const uint8_t* channels=nullptr,const int8_t* signs=nullptr, bool ack=false)
      : c({sim, mapping,manual,cap,channels,signs,ack}) {
    c.feedback(cart::Power::Off, false, now);
    send("HELLO"); send("LIMIT 20");
    c.feedback(cart::Power::On, false, now);
  }
  std::string send(const char* operation) {
    char payload[180], wire[cart::FRAME_SIZE];
    snprintf(payload, sizeof(payload), "C2 0123456789abcdef %lu %s", static_cast<unsigned long>(id++), operation);
    cart::frame(wire, sizeof(wire), payload);
    c.receive(wire, now, response);
    return response;
  }
  void advance(uint32_t ms) { now += ms; c.tick(now); }
};
int main() {
  CHECK(cart::crc16("123456789", 9) == 0x29b1);
  {
    Fixture f(false,false,true,0);
    CHECK(f.send("INFO").find("MANUAL_ONLY")!=std::string::npos);
    CHECK(f.send("ARM").find("HARDWARE_LOCKED")!=std::string::npos);
    CHECK(f.c.stationary());
  }
  {
    Fixture f(false,false,true,20);
    CHECK(f.send("ARM").find("OK ARM")!=std::string::npos);
    CHECK(f.send("M 4 10").find("OK M")!=std::string::npos);
    f.advance(15);CHECK(f.c.output(3)==2);
    CHECK(f.send("V 10 0 0").find("MAPPING_OR_MOTION_REJECTED")!=std::string::npos);
    CHECK(f.c.stationary());
  }
  {
    Fixture f(false,false,true,20);
    CHECK(f.send("LIMIT 21").find("PHYSICAL_LIMIT_UNCONFIGURED")!=std::string::npos);
    CHECK(!f.c.armed());
  }
  {
    const uint8_t ch[4]={1,0,3,2}; const int8_t signs[4]={-1,1,-1,1};
    Fixture f(false,true,true,20,ch,signs); f.send("ARM");
    CHECK(f.send("V 10 0 0").find("OK V")!=std::string::npos);
    CHECK(f.c.target(0)==20 && f.c.target(1)==-20 && f.c.target(2)==20 && f.c.target(3)==-20);
    f.c.feedback(cart::Power::Unknown,false,f.now);
    CHECK(f.c.stationary() && !f.c.armed());
  }
  {
    const uint8_t ch[4]={0,0,2,3}; const int8_t signs[4]={1,1,1,1};
    Fixture f(false,true,true,20,ch,signs); f.send("ARM");
    CHECK(f.send("V 10 0 0").find("INVALID_WHEEL_MAPPING")!=std::string::npos);
    CHECK(f.c.stationary());
  }
  {
    Fixture f(false);
    CHECK(f.send("ARM").find("ERR ARM HARDWARE_LOCKED") != std::string::npos);
    CHECK(!f.c.armed() && f.c.stationary());
  }
  {
    Fixture f;
    CHECK(f.c.stationary() && !f.c.armed());
    CHECK(f.send("M 1 10").find("ERR") != std::string::npos);
    CHECK(!f.c.armed());
  }
  {
    Fixture f;
    CHECK(f.send("ARM").find("OK ARM") != std::string::npos);
    CHECK(f.send("M 1 20").find("OK M") != std::string::npos);
    for (int i = 0; i < 5; ++i) f.advance(15);
    CHECK(f.c.output(0) == 10 && f.c.output(1) == 0);
    f.send("STOP");
    CHECK(f.c.target(0) == 0 && f.c.output(0) == 10 && !f.c.armed());
    CHECK(f.send("ARM").find("REARM_CONDITIONS") != std::string::npos);
    CHECK(f.c.stationary()); // rejected rearm faults and zeros all model outputs
  }
  {
    Fixture f; f.send("ARM"); f.send("M 1 10");
    for (int i = 0; i < 5; ++i) f.advance(15);
    f.send("M 1 -10");
    for (int i = 0; i < 5; ++i) f.advance(15);
    CHECK(f.c.output(0) == 0);
    f.advance(15); CHECK(f.c.output(0) == -2);
  }
  {
    Fixture f; f.send("ARM"); f.send("M 1 20"); f.advance(15);
    CHECK(f.send("M 2 20").find("OTHER_MOTOR_NOT_STOPPED") != std::string::npos);
    CHECK(f.c.stationary());
  }
  {
    Fixture f; f.send("ARM"); f.send("M 1 20"); f.advance(499);
    CHECK(f.c.armed()); f.advance(1);
    CHECK(!f.c.armed() && f.c.stationary());
    CHECK(!strcmp(f.c.reason(), "COMMAND_TIMEOUT"));
    f.c.feedback(cart::Power::On, false, f.now);
    CHECK(f.send("ARM").find("REARM_CONDITIONS") != std::string::npos);
    f.c.feedback(cart::Power::Off, false, f.now); f.c.feedback(cart::Power::On, false, f.now);
    CHECK(f.send("ARM").find("OK ARM") != std::string::npos);
  }
  {
    Fixture f; f.send("ARM"); f.send("M 1 10");
    f.advance(100); f.send("ENC"); f.advance(400);
    CHECK(!f.c.armed()); // read-only traffic cannot refresh the drive lease
  }
  {
    Fixture f; f.send("ARM"); f.send("M 1 20"); f.advance(15);
    f.c.feedback(cart::Power::On, true, f.now);
    CHECK(f.c.stationary() && !f.c.armed());
    f.c.feedback(cart::Power::On, false, f.now);
    CHECK(f.send("ARM").find("REARM_CONDITIONS") != std::string::npos);
    f.c.feedback(cart::Power::Off, false, f.now); f.c.feedback(cart::Power::On, true, f.now);
    CHECK(f.send("ARM").find("REARM_CONDITIONS") != std::string::npos);
    f.c.feedback(cart::Power::Off, false, f.now); f.c.feedback(cart::Power::On, false, f.now);
    CHECK(f.send("ARM").find("OK ARM") != std::string::npos);
  }
  {
    const char* bad[] = {"M 0 10", "M 5 10", "M 1 41", "M 1 1.0", "M 1 +1", "M 1 1 extra", "ARM extra", "UNKNOWN", "LIMIT 0", "LIMIT 9999999999999999999999", "V 1 0 0"};
    for (const char* op : bad) {
      Fixture f; f.send("ARM");
      CHECK(f.send(op).find("ERR") != std::string::npos);
      CHECK(!f.c.armed() && f.c.stationary());
    }
  }
  {
    Fixture f; f.send("ARM"); f.send("M 1 20"); f.advance(15);
    f.c.receive("C2 0123456789abcdef 5 M 1 20 *0000", f.now, f.response);
    CHECK(f.c.stationary() && !f.c.armed());
    CHECK(strstr(f.response, "BAD_FRAME") != nullptr);
  }
  {
    Fixture f; f.send("ARM"); f.send("M 1 10");
    char message[cart::FRAME_SIZE];
    cart::frame(message, sizeof(message), "C2 0123456789abcdef 4 M 1 10");
    f.c.receive(message, f.now, f.response);
    CHECK(strstr(f.response, "SESSION_OR_REPLAY") != nullptr);
    CHECK(!f.c.armed());
  }
  {
    Fixture f; f.send("ARM"); f.send("M 1 10"); f.advance(15);
    char message[cart::FRAME_SIZE];
    cart::frame(message, sizeof(message), "C2 fedcba9876543210 1 HELLO");
    f.c.receive(message, f.now, f.response);
    CHECK(f.c.stationary() && !f.c.armed());
  }
  {
    Fixture f; f.send("ARM");
    for (int i = 0; i < 50 && f.c.armed(); ++i) { f.send("M 1 20"); f.advance(15); }
    CHECK(!f.c.armed()); CHECK(!strcmp(f.c.reason(), "STALL_NO_ENCODER"));
  }
  {
    Fixture f(true, true); f.send("ARM");
    f.send("V 30 30 30");
    for (int i = 0; i < 4; ++i) CHECK(f.c.target(i) >= -40 && f.c.target(i) <= 40);
  }
  {
    Fixture f; int32_t enc[4] = {1, -2, INT32_MAX, INT32_MIN}; f.c.counts(enc);
    CHECK(f.send("ENC").find("1 -2 2147483647 -2147483648") != std::string::npos);
  }
  {
    Fixture f; f.now = UINT32_MAX - 50; f.send("ARM"); f.send("M 1 10");
    f.advance(499); CHECK(f.c.armed()); f.advance(1); CHECK(!f.c.armed());
  }
  {
    Fixture f; f.send("ARM"); f.send("M 1 20");
    f.c.receive("ESTOP", f.now, f.response);
    CHECK(f.c.stationary()); CHECK(!f.c.armed());
  }
  {
    Fixture f(false,false,true,cart::MAX_PERCENT,nullptr,nullptr,true);
    f.c.feedback(cart::Power::Unknown,false,f.now);
    CHECK(f.send("INFO").find("MANUAL_UNMONITORED")!=std::string::npos);
    CHECK(f.c.stationary() && !f.c.armed());
    CHECK(f.send("ARM").find("REARM_CONDITIONS")!=std::string::npos);
    CHECK(f.send("POWER_ACK").find("OK POWER_ACK")!=std::string::npos);
    CHECK(f.send("ARM").find("OK ARM")!=std::string::npos);
    CHECK(f.send("STATUS").find("READY_UNMONITORED 0 1")!=std::string::npos);
    f.c.feedback(cart::Power::Unknown,false,f.now);
    CHECK(f.c.armed()); // Power remains explicitly unmeasured, not fake ON.
    f.send("M 1 10"); f.advance(15); CHECK(f.c.output(0)==2);
    f.send("STOP"); f.advance(15); CHECK(f.c.stationary() && !f.c.armed());
    CHECK(f.send("ARM").find("REARM_CONDITIONS")!=std::string::npos);
    f.send("POWER_ACK"); f.send("ARM"); f.send("M 2 10");
    f.advance(500); CHECK(f.c.stationary() && !f.c.armed());
    CHECK(f.send("ARM").find("REARM_CONDITIONS")!=std::string::npos);
    f.send("POWER_ACK"); f.send("ARM"); f.send("ESTOP");
    CHECK(f.c.stationary() && !f.c.armed());
    CHECK(f.send("ARM").find("REARM_CONDITIONS")!=std::string::npos);
    char cap[30]; snprintf(cap,sizeof(cap),"LIMIT %d",cart::MAX_PERCENT);
    CHECK(f.send(cap).find("OK LIMIT")!=std::string::npos);
    f.send("POWER_ACK"); f.send("ARM");
    snprintf(cap,sizeof(cap),"M 4 %d",cart::MAX_PERCENT);
    CHECK(f.send(cap).find("OK M")!=std::string::npos);
    CHECK(f.c.target(3)==cart::MAX_PERCENT * 2);
    CHECK(f.send("V 10 0 0").find("MAPPING_OR_MOTION_REJECTED")!=std::string::npos);
    CHECK(f.c.stationary());
    f.send("POWER_ACK"); f.send("ESTOP");
    CHECK(f.send("ARM").find("REARM_CONDITIONS")!=std::string::npos);
    f.send("POWER_ACK"); f.send("HELLO");
    // Same-session HELLO rejects replay rather than retaining authority.
    CHECK(f.c.stationary() && !f.c.armed());
  }
  printf("HOST_CONTROLLER_CHECKS=%u PASS; NO GPIO/SERIAL HARDWARE\n", checks);
}
