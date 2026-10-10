#pragma once
// Unmeasured electrical settings MUST remain unknown. Configure only after
// responsible operator verifies actual wiring and first-drive power conditions.
#ifndef CART_POWER_ON_LEVEL
#define CART_POWER_ON_LEVEL -1
#endif
#ifndef CART_PHYSICAL_LIMIT_PERCENT
#define CART_PHYSICAL_LIMIT_PERCENT 0
#endif
#ifndef CART_WHEEL_MAPPING_VERIFIED
#define CART_WHEEL_MAPPING_VERIFIED 0
#endif
#ifndef CART_OPERATOR_POWER_ACK
#define CART_OPERATOR_POWER_ACK 0
#endif
// Logical FL/FR/RL/RR -> PCB M1..M4. Only used when mapping is verified.
constexpr unsigned char CART_WHEEL_CHANNELS[4] = {0, 1, 2, 3};
constexpr signed char CART_WHEEL_SIGNS[4] = {1, 1, 1, 1};
static_assert(CART_POWER_ON_LEVEL >= -1 && CART_POWER_ON_LEVEL <= 1, "A8 polarity must be -1/0/1");
static_assert(CART_PHYSICAL_LIMIT_PERCENT >= 0 && CART_PHYSICAL_LIMIT_PERCENT <= CART_PROTOCOL_MAX_PERCENT, "physical limit outside protocol cap");
static_assert(CART_OPERATOR_POWER_ACK == 0 || CART_OPERATOR_POWER_ACK == 1, "operator power ACK mode must be 0/1");
static_assert(!CART_OPERATOR_POWER_ACK || CART_POWER_ON_LEVEL == -1, "ACK mode must not pretend to measure A8");
static_assert(CART_WHEEL_MAPPING_VERIFIED == 0 || CART_WHEEL_MAPPING_VERIFIED == 1, "mapping flag must be 0/1");
