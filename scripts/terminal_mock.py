"""ROS-free text terminal: fake controller only, no serial implementation."""
import argparse
import json
from pathlib import Path
import sys
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
for name in ("wafer_cart_core", "wafer_cart_keyboard_drive"):
    sys.path.insert(0, str(ROOT / "src" / name))
from wafer_cart_core.safety_gate import SafetyGate, checked_camera_url
from wafer_cart_keyboard_drive.policy import KeyboardDrivePolicy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--camera-url")
    parser.add_argument("--commands", help="comma-separated mock commands for repeatable tests")
    args = parser.parse_args()
    url = checked_camera_url(args.camera_url) if args.camera_url else None
    gate = SafetyGate()
    gate.feedback(power=False, estop=False)
    policy = KeyboardDrivePolicy(command_percent=20, host_limit_percent=20)
    sequence = 0
    print("MOTOR_DISABLED: 실제 COM/모터 미연결. power on/off=가상 전원, resume=수동 허용")
    print("w/s/a/d/q/e=전후/횡이동/회전 요청 1회, stop, estop, status, quit")
    scripted = iter(args.commands.split(",")) if args.commands else None
    try:
        while True:
            text = next(scripted, "quit") if scripted else input("mock> ").strip().lower()
            sequence += 1
            now = time.monotonic()
            try:
                if url:
                    with urllib.request.urlopen(url + "/state", timeout=0.2) as response:
                        gate.observe(json.load(response), now=time.monotonic())
                else:
                    gate.observe(dict(sequence=sequence, session="synthetic_terminal",
                                      age_s=0.0, distances_m=[], healthy=True,
                                      motor_enabled=False), now=now)
            except Exception:
                gate.observe({}, now=time.monotonic())
            if text == "quit":
                break
            if text.startswith("power "):
                if text not in ("power on", "power off"):
                    raise ValueError("expected power on/off")
                gate.feedback(power=text == "power on", estop=False)
            elif text == "resume":
                print("가상 재개", gate.rearm(now=time.monotonic()))
            elif text == "estop":
                gate.emergency_stop()
            elif text == "stop":
                gate.stop()
            elif text in {"w", "s", "a", "d", "q", "e"}:
                motion = policy.command_for_keys({text})
                line = motion.to_protocol_line() if gate.allows_motion(now=time.monotonic()) else "STOP"
                print("MOCK_TX", line, "MOCK_ACK", "OK V" if line.startswith("V ") else "OK STOP")
                print("MOCK_TX STOP (1회 요청 종료; 누적 주행 없음)")
            elif text != "status":
                print("알 수 없는 명령: 출력하지 않았습니다")
            gate.allows_motion(now=time.monotonic())
            print(json.dumps(dict(motor_enabled=False, source="camera_status" if url else "synthetic",
                                  state=gate.reason, armed=gate.armed), ensure_ascii=False))
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        gate.stop()
        print("MOCK_TX STOP / 종료")


if __name__ == "__main__":
    main()
