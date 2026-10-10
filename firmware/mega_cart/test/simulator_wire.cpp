// PC-only adapter around the same Controller compiled into the Mega firmware.
// No Arduino HAL, GPIO, serial device, or hardware-output profile is linked.
#include "cart_controller.h"
#include <chrono>
#include <iostream>
#include <sstream>
#include <string>
#include <poll.h>
#include <unistd.h>

int main(int argc, char** argv) {
  const bool manual_fixture = argc == 2 && std::string(argv[1]) == "--manual-fixture";
  const bool unmonitored = argc == 2 && std::string(argv[1]) == "--unmonitored-fixture";
  const uint8_t channels[4] = {0,1,2,3};
  const int8_t signs[4] = {1,1,1,1};
  cart::Controller controller({!manual_fixture && !unmonitored, !unmonitored,
                               manual_fixture || unmonitored, unmonitored ? 40 : 10,
                               channels, signs, unmonitored});
  const auto started = std::chrono::steady_clock::now();
  const auto clock_ms = [&]() -> uint32_t {
    return static_cast<uint32_t>(std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now() - started).count());
  };
  char response[cart::FRAME_SIZE];
  std::string buffer;
  std::cout << "SIM_HOST_READY " << cart::DUTY_SCALE << std::endl;
  while (true) {
    const uint32_t now = clock_ms();
    controller.tick(now);
    if (controller.event(response)) std::cout << response << std::endl;
    pollfd input = {STDIN_FILENO, POLLIN, 0};
    const int result = poll(&input, 1, 5);
    if (result < 0) return 2;
    if (!(input.revents & (POLLIN | POLLHUP))) continue;
    char chunk[512];
    const ssize_t size = read(STDIN_FILENO, chunk, sizeof(chunk));
    if (size <= 0) return 0;
    buffer.append(chunk, static_cast<size_t>(size));
    size_t newline;
    while ((newline = buffer.find('\n')) != std::string::npos) {
      std::string line = buffer.substr(0, newline);
      buffer.erase(0, newline + 1);
      if (!line.empty() && line.back() == '\r') line.pop_back();
      if (line.rfind("@power ", 0) == 0) {
        int power = 0, estop = 0;
        std::istringstream(line.substr(7)) >> power >> estop;
        controller.feedback(power ? cart::Power::On : cart::Power::Off,
                            estop != 0, clock_ms());
      } else if (line.rfind("@counts ", 0) == 0) {
        int32_t counts[4] = {};
        std::istringstream values(line.substr(8));
        if (values >> counts[0] >> counts[1] >> counts[2] >> counts[3])
          controller.counts(counts);
        else controller.fail("BAD_SIM_COUNTS", clock_ms());
      } else {
        controller.receive(line.c_str(), clock_ms(), response);
        std::cout << response << std::endl;
      }
      if (controller.event(response)) std::cout << response << std::endl;
    }
    if (buffer.size() > cart::FRAME_SIZE) {
      controller.fail("RX_OVERFLOW_OR_NUL", clock_ms());
      buffer.clear();
    }
  }
}
