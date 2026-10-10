#pragma once
#include <stddef.h>
#include <stdint.h>

namespace cart {
constexpr size_t FRAME_SIZE = 240;
constexpr uint8_t PWM_PINS[4] = {11, 44, 12, 45};
constexpr uint8_t DIR_PINS[4] = {34, 36, 35, 37};
constexpr uint8_t ENC_A_PINS[4] = {3, 18, 19, 20};
constexpr uint8_t ENC_B_PINS[4] = {30, 31, 32, 33};
// Historical software ceilings, NOT measured/approved operating values.
#ifndef CART_PROTOCOL_MAX_PERCENT
#define CART_PROTOCOL_MAX_PERCENT 30
#endif
constexpr int MAX_PERCENT = CART_PROTOCOL_MAX_PERCENT;
constexpr int DUTY_SCALE = 200;
constexpr uint32_t COMMAND_LEASE_MS = 500;
constexpr uint32_t RAMP_PERIOD_MS = 15;
#ifndef CART_RAMP_STEP
#define CART_RAMP_STEP 2
#endif
constexpr int RAMP_STEP = CART_RAMP_STEP;
static_assert(RAMP_STEP >= 1 && RAMP_STEP <= 8, "ramp step outside bench bounds");
#ifndef CART_STALL_MS
#define CART_STALL_MS 600
#endif
constexpr uint32_t STALL_MS = CART_STALL_MS;
static_assert(STALL_MS >= 600 && STALL_MS <= 1500, "stall timeout outside bench bounds");

enum class Power : uint8_t { Unknown, Off, On };
enum class State : uint8_t { Locked, Ready, Stopping, Fault };
struct Config {
  bool simulation;
  bool mapping_verified;
  bool manual_output;
  int physical_limit;
  const uint8_t* wheel_channels;
  const int8_t* wheel_signs;
  bool operator_power_ack;
  Config(bool sim, bool mapping, bool manual = false, int limit = 0,
         const uint8_t* channels = nullptr, const int8_t* signs = nullptr, bool ack = false)
      : simulation(sim), mapping_verified(mapping), manual_output(manual), physical_limit(limit),
        wheel_channels(channels), wheel_signs(signs), operator_power_ack(ack) {}
};
uint16_t crc16(const char* data, size_t size);
bool frame(char* out, size_t capacity, const char* payload);

class Controller {
 public:
  explicit Controller(Config config);
  void feedback(Power power, bool estop, uint32_t now);
  void counts(const int32_t values[4]);
  void tick(uint32_t now);
  void receive(const char* line, uint32_t now, char* response);
  void fail(const char* reason, uint32_t now);
  bool event(char* out);
  using OutputDiagnostic = void (*)(char*, size_t);
  void set_output_diagnostic(OutputDiagnostic reader) { output_diagnostic_ = reader; }
  int output(size_t channel) const { return current_[channel]; }
  int target(size_t channel) const { return target_[channel]; }
  State state() const { return state_; }
  const char* reason() const { return reason_; }
  bool stationary() const;
  bool armed() const { return armed_; }
 private:
  Config config_;
  Power power_ = Power::Unknown;
  bool estop_ = false, seen_off_ = false, armed_ = false;
  bool operator_ack_ = false;
  State state_ = State::Locked;
  char session_[17] = "-", reason_[32] = "STARTUP_LOCKED", pending_[32] = "";
  uint32_t sequence_ = 0, lease_at_ = 0, ramp_at_ = 0, activity_at_[4] = {};
  int limit_ = 0, target_[4] = {}, current_[4] = {};
  int32_t counts_[4] = {}, previous_counts_[4] = {};
  char first_fault_[32] = "NONE";
  uint32_t first_fault_ms_ = 0;
  int fault_outputs_[4] = {};
  int32_t fault_counts_[4] = {};
  OutputDiagnostic output_diagnostic_ = nullptr;
  void halt();
  void reply(char* out, const char* session, uint32_t id, bool ok,
             const char* operation, const char* data);
};
}  // namespace cart
