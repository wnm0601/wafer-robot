#!/usr/bin/env bash
set -euo pipefail
task_root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$task_root"
mkdir -p data/output/bench_build
task_flags=(-std=c++11 -Wall -Wextra -Werror -fsanitize=address,undefined -fno-omit-frame-pointer)
g++ "${task_flags[@]}" -I firmware/mega_cart/include firmware/mega_cart/src/cart_controller.cpp firmware/mega_cart/test/host_tests.cpp -o data/output/bench_build/host_tests
data/output/bench_build/host_tests
g++ "${task_flags[@]}" -I firmware/mega_cart/test/avr_stub -I firmware/mega_cart/include firmware/mega_cart/src/cart_controller.cpp firmware/mega_cart/test/host_pwm_tests.cpp -o data/output/bench_build/host_pwm_tests
data/output/bench_build/host_pwm_tests
g++ "${task_flags[@]}" -DCART_PWM_DENOMINATOR=255 -I firmware/mega_cart/test/avr_stub -I firmware/mega_cart/include firmware/mega_cart/src/cart_controller.cpp firmware/mega_cart/test/host_pwm_tests.cpp -o data/output/bench_build/host_legacy_pwm_tests
data/output/bench_build/host_legacy_pwm_tests
g++ "${task_flags[@]}" -DCART_PWM_TOP=3199 -DCART_PWM_DENOMINATOR=255 -I firmware/mega_cart/test/avr_stub -I firmware/mega_cart/include firmware/mega_cart/src/cart_controller.cpp firmware/mega_cart/test/host_pwm_tests.cpp -o data/output/bench_build/host_5khz_pwm_tests
data/output/bench_build/host_5khz_pwm_tests
g++ "${task_flags[@]}" -DCART_RAMP_STEP=8 -DCART_PROTOCOL_MAX_PERCENT=40 -I firmware/mega_cart/include firmware/mega_cart/src/cart_controller.cpp firmware/mega_cart/test/host_legacy_ramp_tests.cpp -o data/output/bench_build/host_legacy_ramp_tests
data/output/bench_build/host_legacy_ramp_tests
g++ "${task_flags[@]}" -DCART_RAMP_STEP=8 -DCART_PROTOCOL_MAX_PERCENT=40 -DCART_STALL_MS=1500 -I firmware/mega_cart/include firmware/mega_cart/src/cart_controller.cpp firmware/mega_cart/test/host_legacy_ramp_tests.cpp -o data/output/bench_build/host_stall_1500_tests
data/output/bench_build/host_stall_1500_tests
g++ "${task_flags[@]}" -DCART_PHYSICAL_OUTPUT=1 -DCART_OPERATOR_POWER_ACK=1 -DCART_PHYSICAL_LIMIT_PERCENT=40 -DCART_PROTOCOL_MAX_PERCENT=40 -DCART_RAMP_STEP=8 -DCART_STALL_MS=1500 -DCART_PWM_TOP=3199 -DCART_PWM_DENOMINATOR=255 -I firmware/mega_cart/test/avr_stub -I firmware/mega_cart/include firmware/mega_cart/src/cart_controller.cpp firmware/mega_cart/test/host_diagnostic_tests.cpp -o data/output/bench_build/host_diagnostic_tests
data/output/bench_build/host_diagnostic_tests
g++ "${task_flags[@]}" -I firmware/mega_cart/include firmware/mega_cart/src/cart_controller.cpp firmware/mega_cart/test/host_wire.cpp -o data/output/bench_build/host_wire
python3 scripts/verify_firmware_contract.py
