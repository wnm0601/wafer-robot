// Host-only test oracle, deliberately NOT linked into the Mega firmware.
#include "cart_controller.h"
#include <iostream>
#include <sstream>
#include <string>
int main() {
  cart::Controller controller({true, false});
  uint32_t now = 0;
  char response[cart::FRAME_SIZE];
  std::string line;
  while (std::getline(std::cin, line)) {
    if (line.rfind("@power ", 0) == 0) {
      int power = 0, estop = 0;
      std::istringstream(line.substr(7)) >> power >> estop;
      controller.feedback(power ? cart::Power::On : cart::Power::Off, estop != 0, now);
      std::cout << "HOST_OK" << std::endl;
    } else if (line.rfind("@advance ", 0) == 0) {
      unsigned delta; std::istringstream(line.substr(9)) >> delta; now += delta;
      controller.tick(now); std::cout << "HOST_OK" << std::endl;
    } else {
      controller.receive(line.c_str(), now, response);
      std::cout << response << std::endl;
    }
  }
}
