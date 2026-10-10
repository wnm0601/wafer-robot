"""Standalone mock bench console; no COM opening or automatic physical enable."""
import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src" / "wafer_cart_keyboard_drive"))
from wafer_cart_keyboard_drive.bench_gateway import BenchGateway, open_physical_wire
from wafer_cart_keyboard_drive.bench_mock import MockWire
from wafer_cart_keyboard_drive.bench_protocol import ProtocolError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="확인되지 않은 실제 serial 요청은 연결 전에 차단됩니다")
    parser.add_argument("--limit-percent", type=int, default=20, help="가상시험 상한; 실제 승인값 아님")
    parser.add_argument("--commands", help="세미콜론으로 구분한 가상시험 명령")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.port:
        try:
            open_physical_wire(port=args.port, profile={})
        except RuntimeError as error:
            parser.error(str(error))
    if not 1 <= args.limit_percent <= 30:
        parser.error("가상시험 상한은 1..30입니다")
    if args.report and not args.report.resolve().is_relative_to((ROOT / "data/output").resolve()):
        parser.error("시험 기록은 이 저장소의 data/output 안에만 저장합니다")
    print("MOTOR_DISABLED / MOCK_ONLY — 실제 Arduino·모터·카메라를 열지 않습니다.")
    print("power on/off=가상 피드백, arm=수동 허용, m 1 10=가상 단일 모터 0.15초")
    print("stop, estop, status, enc, wait 0.5, quit / STOP 이후 다시 arm이 필요합니다.")
    wire = MockWire()
    records = []
    scripted = iter(args.commands.split(";")) if args.commands else None
    try:
        with BenchGateway(wire) as gateway:
            gateway.connect(limit_percent=args.limit_percent)
            while True:
                text = next(scripted, "quit") if scripted else input("bench> ")
                parts = text.strip().lower().split()
                if not parts:
                    continue
                try:
                    if parts == ["quit"]:
                        break
                    if parts in (["power", "on"], ["power", "off"]):
                        wire.power_feedback(parts[1] == "on")
                        result = gateway.exchange("STATUS")
                    elif parts[0] == "m" and len(parts) == 3:
                        gateway.jog(int(parts[1]), int(parts[2]))
                        result = gateway.exchange("STATUS")
                    elif parts[0] == "wait" and len(parts) == 2:
                        duration = float(parts[1])
                        if not 0 <= duration <= 3:
                            raise ValueError("wait는 0..3초입니다")
                        time.sleep(duration)
                        result = gateway.exchange("STATUS")
                    elif parts == ["enc"]:
                        result = gateway.encoder_snapshot()
                    elif len(parts) == 1 and parts[0] in {"arm", "stop", "estop", "status", "info"}:
                        result = gateway.exchange(parts[0].upper())
                    else:
                        raise ValueError("지원하지 않는 명령입니다")
                    entry = dict(command=text, result=result, host_armed=gateway.armed,
                                 host_fault=gateway.fault, motor_enabled=False)
                except (ProtocolError, ValueError, TimeoutError) as error:
                    # Invalid operator input also leaves no continuing motion.
                    if gateway.armed:
                        gateway.exchange("STOP")
                    entry = dict(command=text, error=str(error), motor_enabled=False)
                records.append(entry)
                print(json.dumps(entry, ensure_ascii=False))
    except (EOFError, KeyboardInterrupt):
        print("종료 요청: 가상 ESTOP 및 연결 정리")
    finally:
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(json.dumps(dict(kind="mock_bench_console", motor_enabled=False,
                                                   measured=False, records=records), ensure_ascii=False, indent=2),
                                   encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
