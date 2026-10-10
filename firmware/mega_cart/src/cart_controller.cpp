#include "cart_controller.h"
#include <stdio.h>
#include <string.h>

namespace cart {
uint16_t crc16(const char* data, size_t size) {
  uint16_t crc = 0xffff;
  for (size_t i = 0; i < size; ++i) {
    crc ^= static_cast<uint16_t>(static_cast<uint8_t>(data[i])) << 8;
    for (uint8_t bit = 0; bit < 8; ++bit)
      crc = (crc & 0x8000) ? static_cast<uint16_t>((crc << 1) ^ 0x1021)
                           : static_cast<uint16_t>(crc << 1);
  }
  return crc;
}
bool frame(char* out, size_t capacity, const char* payload) {
  const size_t size = strlen(payload);
  if (size + 7 > capacity) return false;
  snprintf(out, capacity, "%s *%04X", payload, static_cast<unsigned>(crc16(payload, size)));
  return true;
}
static bool unsigned_number(const char* text, uint32_t& result) {
  if (!text || !*text) return false;
  uint32_t value = 0;
  for (const char* p = text; *p; ++p) {
    if (*p < '0' || *p > '9') return false;
    const uint8_t digit = *p - '0';
    if (value > (UINT32_MAX - digit) / 10) return false;
    value = value * 10 + digit;
  }
  result = value;
  return true;
}
static bool percentage(const char* text, int& result) {
  const bool negative = text && *text == '-';
  uint32_t value;
  if (!unsigned_number(negative ? text + 1 : text, value) || value > MAX_PERCENT)
    return false;
  result = negative ? -static_cast<int>(value) : static_cast<int>(value);
  return true;
}
static int magnitude(int v) { return v < 0 ? -v : v; }
static bool valid_session(const char* value) {
  if (strlen(value) != 16) return false;
  for (const char* p = value; *p; ++p)
    if (!(*p >= '0' && *p <= '9') && !(*p >= 'a' && *p <= 'f')) return false;
  return true;
}
Controller::Controller(Config config) : config_(config) {}
bool Controller::stationary() const {
  for (uint8_t i = 0; i < 4; ++i) if (current_[i] || target_[i]) return false;
  return true;
}
void Controller::halt() {
  armed_ = false;
  operator_ack_ = false;
  for (uint8_t i = 0; i < 4; ++i) current_[i] = target_[i] = 0;
}
void Controller::fail(const char* reason, uint32_t now) {
  // Preserve the first cause and pre-halt values until an explicit successful ARM.
  if (!strcmp(first_fault_, "NONE")) {
    snprintf(first_fault_, sizeof(first_fault_), "%s", reason);
    first_fault_ms_ = now;
    for (uint8_t i = 0; i < 4; ++i) {
      fault_outputs_[i] = current_[i]; fault_counts_[i] = counts_[i];
    }
  }
  halt();
  // A fault always needs an OFF observation *after* the fault, then ON and ARM.
  seen_off_ = power_ == Power::Off;
  state_ = State::Fault;
  if (strcmp(reason_, reason)) {
    snprintf(reason_, sizeof(reason_), "%s", reason);
    snprintf(pending_, sizeof(pending_), "%s", reason);
  }
}
void Controller::feedback(Power power, bool estop, uint32_t now) {
  const bool changed = power != power_;
  power_ = power;
  if (estop && !estop_) fail("ESTOP_INPUT", now);
  estop_ = estop;
  if (power == Power::Off) {
    if (changed) fail("POWER_OFF", now);
    seen_off_ = true;
  } else if (power == Power::Unknown) {
    if (!config_.operator_power_ack && (changed || armed_)) fail("POWER_UNKNOWN", now);
  }
}
void Controller::counts(const int32_t values[4]) {
  for (uint8_t i = 0; i < 4; ++i) counts_[i] = values[i];
}
void Controller::tick(uint32_t now) {
  if (armed_ && static_cast<uint32_t>(now - lease_at_) >= COMMAND_LEASE_MS) {
    fail("COMMAND_TIMEOUT", now);
    return;
  }
  const int encoder_threshold = config_.manual_output && !config_.simulation ? 1 : 5;
  for (uint8_t i = 0; i < 4; ++i) {
    if (counts_[i] != previous_counts_[i] || magnitude(current_[i]) < encoder_threshold)
      activity_at_[i] = now;
    previous_counts_[i] = counts_[i];
    if (armed_ && magnitude(current_[i]) >= encoder_threshold &&
        static_cast<uint32_t>(now - activity_at_[i]) >= STALL_MS) {
      fail("STALL_NO_ENCODER", now);
      return;
    }
  }
  if (static_cast<uint32_t>(now - ramp_at_) < RAMP_PERIOD_MS) return;
  // No catch-up jump after a delayed loop; actual timing needs bench measurement.
  ramp_at_ = now;
  for (uint8_t i = 0; i < 4; ++i) {
    int goal = target_[i];
    if ((goal < 0 && current_[i] > 0) || (goal > 0 && current_[i] < 0)) goal = 0;
    if (current_[i] < goal) current_[i] += (goal - current_[i] < RAMP_STEP) ? goal - current_[i] : RAMP_STEP;
    if (current_[i] > goal) current_[i] -= (current_[i] - goal < RAMP_STEP) ? current_[i] - goal : RAMP_STEP;
  }
  if (state_ == State::Stopping && stationary()) state_ = State::Locked;
}
void Controller::reply(char* out, const char* session, uint32_t id, bool ok,
                       const char* op, const char* data) {
  char payload[FRAME_SIZE - 7];
  snprintf(payload, sizeof(payload), "R2 %s %lu %s %s%s%s", session,
           static_cast<unsigned long>(id), ok ? "OK" : "ERR", op,
           *data ? " " : "", data);
  frame(out, FRAME_SIZE, payload);
}
bool Controller::event(char* out) {
  if (!*pending_) return false;
  char payload[80];
  snprintf(payload, sizeof(payload), "E2 %s %s", session_, pending_);
  frame(out, FRAME_SIZE, payload);
  *pending_ = '\0';
  return true;
}
void Controller::receive(const char* line, uint32_t now, char* out) {
  tick(now);
  // Old driving clients are NOT compatible. Only their two stop commands are safe aliases.
  if (!strcmp(line, "ESTOP")) { fail("OPERATOR_ESTOP", now); reply(out, session_, 0, true, "ESTOP", ""); return; }
  if (!strcmp(line, "STOP")) {
    armed_ = false;
    operator_ack_ = false;
    for (uint8_t i = 0; i < 4; ++i) target_[i] = 0;
    if (state_ != State::Fault) state_ = State::Stopping;
    reply(out, session_, 0, true, "STOP", ""); return;
  }
  char buffer[FRAME_SIZE];
  const size_t size = strlen(line);
  bool valid = size >= 7 && size < sizeof(buffer) && line[size - 6] == ' ' && line[size - 5] == '*';
  uint16_t received = 0;
  for (size_t i = 0; valid && i < size; ++i) if (line[i] < 32 || line[i] > 126) valid = false;
  for (size_t i = size >= 4 ? size - 4 : 0; valid && i < size; ++i) {
    const char c = line[i];
    if (!((c >= '0' && c <= '9') || (c >= 'A' && c <= 'F'))) valid = false;
    else received = static_cast<uint16_t>((received << 4) | (c <= '9' ? c - '0' : c - 'A' + 10));
  }
  if (!valid || crc16(line, size - 6) != received) {
    fail("BAD_FRAME", now); reply(out, session_, 0, false, "FRAME", "BAD_FRAME"); return;
  }
  memcpy(buffer, line, size - 6); buffer[size - 6] = '\0';
  char* tokens[10]; uint8_t count = 0; char* saved = nullptr;
  for (char* token = strtok_r(buffer, " ", &saved); token; token = strtok_r(nullptr, " ", &saved)) {
    if (count == 10) { fail("BAD_ARGS", now); reply(out, session_, 0, false, "FRAME", "BAD_ARGS"); return; }
    tokens[count++] = token;
  }
  uint32_t id = 0;
  if (count < 4 || strcmp(tokens[0], "C2") || !valid_session(tokens[1]) || strlen(tokens[3]) > 12 ||
      !unsigned_number(tokens[2], id) || id == 0) {
    fail("BAD_HEADER", now); reply(out, session_, 0, false, "FRAME", "BAD_HEADER"); return;
  }
  const char* sid = tokens[1]; const char* op = tokens[3];
  if (!strcmp(op, "HELLO") && count == 4 && id == 1 && strcmp(sid, session_)) {
    halt(); limit_ = 0;
    snprintf(session_, sizeof(session_), "%s", sid); sequence_ = 1;
    if (state_ != State::Fault) state_ = State::Locked;
    reply(out, sid, id, true, op, config_.simulation ? "CART_2 HKX_20260929 SIM_ONLY" :
          config_.manual_output ? (config_.operator_power_ack ? "CART_2 HKX_20260929 MANUAL_UNMONITORED" : "CART_2 HKX_20260929 MANUAL_ONLY") : "CART_2 HKX_20260929 OUTPUT_LOCKED");
    return;
  }
  if (strcmp(sid, session_) || sequence_ == UINT32_MAX || id != sequence_ + 1) {
    fail("SESSION_OR_REPLAY", now); reply(out, sid, id, false, op, "SESSION_OR_REPLAY"); return;
  }
  sequence_ = id;
  bool ok = true; char data[150] = "";
  if (!strcmp(op, "INFO") && count == 4) {
    snprintf(data, sizeof(data), "CART_2 HKX_20260929 %s", config_.simulation ? "SIM_ONLY" :
             config_.manual_output ? (config_.operator_power_ack ? "MANUAL_UNMONITORED" : "MANUAL_ONLY") : "OUTPUT_LOCKED");
  } else if (!strcmp(op, "DIAG") && count == 4) {
    snprintf(data, sizeof(data), "%s %lu %d %d %d %d %ld %ld %ld %ld", first_fault_,
             static_cast<unsigned long>(first_fault_ms_), fault_outputs_[0], fault_outputs_[1],
             fault_outputs_[2], fault_outputs_[3], static_cast<long>(fault_counts_[0]),
             static_cast<long>(fault_counts_[1]), static_cast<long>(fault_counts_[2]),
             static_cast<long>(fault_counts_[3]));
  } else if (!strcmp(op, "IO") && count == 4) {
    if (output_diagnostic_) output_diagnostic_(data, sizeof(data));
    else strcpy(data, "UNAVAILABLE");
  } else if (!strcmp(op, "STATUS") && count == 4) {
    snprintf(data, sizeof(data), "%u %s %u %u %d %d %d %d %d", static_cast<unsigned>(state_), reason_,
             static_cast<unsigned>(power_), armed_ ? 1 : 0, limit_, current_[0], current_[1], current_[2], current_[3]);
  } else if (!strcmp(op, "ENC") && count == 4) {
    snprintf(data, sizeof(data), "%lu %ld %ld %ld %ld", static_cast<unsigned long>(now),
             static_cast<long>(counts_[0]), static_cast<long>(counts_[1]), static_cast<long>(counts_[2]), static_cast<long>(counts_[3]));
  } else if (!strcmp(op, "LIMIT") && count == 5) {
    uint32_t limit;
    if (armed_ || !stationary() || !unsigned_number(tokens[4], limit) || limit < 1 || limit > MAX_PERCENT) {
      ok = false; strcpy(data, "INVALID_LIMIT");
    } else if (config_.manual_output && !config_.simulation &&
               (config_.physical_limit < 1 || limit > static_cast<uint32_t>(config_.physical_limit))) {
      ok = false; strcpy(data, "PHYSICAL_LIMIT_UNCONFIGURED");
    } else limit_ = static_cast<int>(limit);
  } else if (!strcmp(op, "POWER_ACK") && count == 4) {
    // Operator declaration, NOT a measured power state. Consumed by one ARM.
    if (!config_.manual_output || config_.simulation || !config_.operator_power_ack ||
        armed_ || !stationary() || estop_) { ok = false; strcpy(data, "POWER_ACK_REJECTED"); }
    else { operator_ack_ = true; state_ = State::Locked; strcpy(reason_, "POWER_UNMONITORED"); }
  } else if (!strcmp(op, "ARM") && count == 4) {
    if (!config_.simulation && (!config_.manual_output || config_.physical_limit < 1 ||
                               config_.physical_limit > MAX_PERCENT)) { ok = false; strcpy(data, "HARDWARE_LOCKED"); }
    else if (estop_ || !stationary() || !limit_ ||
             (config_.operator_power_ack ? !operator_ack_ : (power_ != Power::On || !seen_off_))) { ok = false; strcpy(data, "REARM_CONDITIONS"); }
    else { armed_ = true; state_ = State::Ready; lease_at_ = now;
      operator_ack_ = false;
      strcpy(first_fault_, "NONE"); first_fault_ms_ = 0;
      for (uint8_t i = 0; i < 4; ++i) { fault_outputs_[i] = 0; fault_counts_[i] = 0; }
      strcpy(reason_, config_.simulation ? "READY_SIM_ONLY" : config_.operator_power_ack ? "READY_UNMONITORED" : "READY_MANUAL_ONLY"); }
  } else if (!strcmp(op, "STOP") && count == 4) {
    armed_ = false;
    operator_ack_ = false;
    for (uint8_t i = 0; i < 4; ++i) target_[i] = 0;
    if (state_ != State::Fault) { state_ = State::Stopping; strcpy(reason_, "OPERATOR_STOP"); }
  } else if (!strcmp(op, "ESTOP") && count == 4) {
    fail("OPERATOR_ESTOP", now);
  } else if (!strcmp(op, "M") && count == 6) {
    uint32_t channel; int pct;
    if (!armed_) {
      ok = false;
      snprintf(data, sizeof(data), "MOTION_REJECTED %s", strcmp(first_fault_, "NONE") ? first_fault_ : "NOT_ARMED");
    } else if (!unsigned_number(tokens[4], channel) || channel < 1 || channel > 4 ||
        !percentage(tokens[5], pct) || magnitude(pct) > limit_) { ok = false; strcpy(data, "MOTION_REJECTED"); }
    else {
      for (uint8_t i = 0; i < 4; ++i) if (static_cast<uint32_t>(i + 1) != channel && current_[i]) ok = false;
      if (!ok) { strcpy(data, "OTHER_MOTOR_NOT_STOPPED"); }
      else {
      // Single-channel bench command clears the other three targets.
      for (uint8_t i = 0; i < 4; ++i) target_[i] = static_cast<uint32_t>(i + 1) == channel ? pct * DUTY_SCALE / 100 : 0;
      lease_at_ = now;
      }
    }
  } else if (!strcmp(op, "V") && count == 7) {
    int x, y, w;
    if (!armed_ || !config_.mapping_verified || (!config_.simulation &&
        (!config_.wheel_channels || !config_.wheel_signs)) || !percentage(tokens[4], x) ||
        !percentage(tokens[5], y) || !percentage(tokens[6], w)) { ok = false; strcpy(data, "MAPPING_OR_MOTION_REJECTED"); }
    else {
      // SIMULATION X-roller convention, FL/FR/RL/RR. Not actual motor wiring/signs.
      const int mix[4] = {x - y - w, x + y + w, x + y - w, x - y + w};
      int maximum = limit_;
      for (uint8_t i = 0; i < 4; ++i) if (magnitude(mix[i]) > maximum) maximum = magnitude(mix[i]);
      for (uint8_t i = 0; i < 4; ++i) {
        const uint8_t channel = config_.simulation ? i : config_.wheel_channels[i];
        const int sign = config_.simulation ? 1 : config_.wheel_signs[i];
        if (channel >= 4 || (sign != 1 && sign != -1)) { ok = false; break; }
        for (uint8_t j=0; j<i && !config_.simulation; ++j)
          if (config_.wheel_channels[j] == channel) ok = false;
        if (!ok) break;
        target_[channel] = static_cast<int32_t>(mix[i]) * sign * limit_ * DUTY_SCALE / (maximum * 100);
      }
      if (!ok) strcpy(data, "INVALID_WHEEL_MAPPING");
      lease_at_ = now;
    }
  } else { ok = false; strcpy(data, "BAD_OPERATION_OR_ARGS"); }
  if (!ok) {
    // STATUS/DIAG reason is one token; the ERR reply may carry extra detail.
    char code[32]; size_t code_size = strcspn(data, " ");
    if (code_size >= sizeof(code)) code_size = sizeof(code)-1;
    memcpy(code, data, code_size); code[code_size] = '\0';
    fail(code, now);
  }
  reply(out, sid, id, ok, op, data);
}
}  // namespace cart
