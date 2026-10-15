"""세 수동 시험의 공통 실행부. 가져오기/단위시험은 포트를 열지 않습니다."""
import argparse
import pathlib
import sys
import time

POSITIONS = {1: "M1 앞왼", 2: "M2 앞오", 3: "M3 뒤왼", 4: "M4 뒤오"}
PAIRS = {"1": (1, 3), "2": (2, 4), "3": (1, 2), "4": (3, 4),
         "5": (1, 4), "6": (2, 3)}
MOTIONS = {"w": (1, 0, 0), "s": (-1, 0, 0), "a": (0, 0, -1),
           "d": (0, 0, 1), "z": (0, -1, 0), "c": (0, 1, 0)}
FIRMWARE_INFO = "MECANUM_HKX_REVIEW_20261012"
VK = {k: ord(k.upper()) for k in "wsadzcfreqxo123456"}
VK.update(up=0x26, down=0x28, space=0x20, esc=0x1B)
VK.update({"+": 0xBB, "-": 0xBD, "]": 0xDD, "[": 0xDB})


class TestFault(RuntimeError):
    """오류 뒤에는 같은 세션에서 구동을 재개하지 않습니다."""


def parse_encoder(line):
    fields = line.split()
    if len(fields) != 5 or fields[0] != "ENC":
        raise TestFault("엔코더 응답 형식 오류: " + line)
    try:
        values = tuple(int(v) for v in fields[1:])
    except ValueError as exc:
        raise TestFault("엔코더 숫자 오류") from exc
    if any(not -(2**31) <= v < 2**31 for v in values):
        raise TestFault("엔코더 범위 오류")
    return values


class Link:
    """제한된 프레임 버퍼와 요청당 응답 기한. 오류를 숨기지 않습니다."""
    def __init__(self, serial_port, clock=time.monotonic, sleep=time.sleep):
        self.ser, self.clock, self.sleep = serial_port, clock, sleep
        self.buffer = bytearray()

    def send(self, command):
        data = (command + "\n").encode("ascii")
        if self.ser.write(data) != len(data):
            raise TestFault("시리얼 일부만 송신됨")

    def read(self):
        self.buffer.extend(self.ser.read(min(self.ser.in_waiting, 512)))
        if len(self.buffer) > 2048:
            raise TestFault("시리얼 응답 길이 초과")
        lines = []
        while b"\n" in self.buffer:
            raw, _, rest = self.buffer.partition(b"\n")
            self.buffer = bytearray(rest)
            try:
                line = raw.decode("ascii").strip()
            except UnicodeDecodeError as exc:
                raise TestFault("시리얼 응답 인코딩 오류") from exc
            if line:
                lines.append(line)
        return lines

    @staticmethod
    def check(lines):
        for line in lines:
            if line == "READY" or line.startswith(("ERR", "UNK", "EVT PWR OFF")):
                raise TestFault("펌웨어 중단: " + line)

    def request(self, command, accepts):
        # 이전 응답을 새 명령의 ACK로 인정하지 않음.
        pending = self.read()
        self.check(pending)
        if self.buffer:
            raise TestFault("명령 전에 미완성 응답이 남아 있음")
        self.send(command)
        deadline = self.clock() + 0.25
        while self.clock() < deadline:
            lines = self.read()
            self.check(lines)  # ACK와 같은 묶음에 온 오류도 우선 처리
            for line in lines:
                if accepts(line):
                    return line
            self.sleep(0.002)
        raise TestFault("응답 시간 초과: " + command)


class HoldController:
    """하드웨어 없는 입력/정지 상태 머신. 시간은 호출자가 제공합니다."""
    def __init__(self, mode, speed, now):
        if mode not in {"single", "pair", "drive"} or not 5 <= speed <= 40:
            raise ValueError("시험 모드 또는 속도 범위 오류")
        self.mode, self.speed, self.selection = mode, speed, "1"
        self.state, self.motion, self.released = "stopping", None, False
        self.stop_at = self.last_tick = now
        self.last_send = float("-inf")
        self.enc = None
        self.enc_at = self.still_since = None
        self.previous = set()

    @property
    def move_keys(self):
        return set(MOTIONS) if self.mode == "drive" else ({"f", "r"} if self.mode == "single" else {"up", "down"})

    @property
    def label(self):
        if self.mode == "drive":
            return "4바퀴: M1 앞왼 / M2 앞오 / M3 뒤왼 / M4 뒤오"
        ids = PAIRS[self.selection] if self.mode == "pair" else (int(self.selection),)
        return " + ".join(POSITIONS[i] for i in ids)

    def observe(self, values, now):
        if self.enc != values:
            self.still_since = now
        self.enc, self.enc_at = values, now

    def stop(self, now):
        self.state, self.motion, self.released = "stopping", None, False
        self.stop_at = now
        self.enc = self.enc_at = self.still_since = None
        return ["STOP"]

    def command(self, key):
        if self.mode == "drive":
            return "V " + " ".join(str(s * self.speed) for s in MOTIONS[key])
        value = self.speed if key in {"f", "up"} else -self.speed
        if self.mode == "single":
            return f"M {self.selection} {value}"
        a, b = PAIRS[self.selection]
        return f"P {a} {b} {value}"

    def tick(self, keys, focused, now):
        if self.state == "fault":
            raise TestFault("잠긴 세션")
        if now - self.last_tick > 0.4:
            self.state = "fault"
            raise TestFault("제어 반복 0.4초 초과")
        self.last_tick = now
        pressed, self.previous = keys - self.previous, set(keys)
        if focused and keys & {"x", "e", "esc", "q"}:
            self.state = "fault"
            raise TestFault("작업자 정지/종료")
        if self.enc_at is not None and now - self.enc_at > 0.5:
            self.state = "fault"
            raise TestFault("엔코더 응답 끊김")
        if self.state == "stopping":
            self.released = False
            # 신선한 ENC를 반복 수신해야 함. 시간 경과만으로 통과하지 않음.
            if (self.enc_at is not None and self.still_since is not None
                    and self.enc_at - self.still_since >= 0.3 and now - self.stop_at >= 0.5):
                self.state = "ready"
            elif now - self.stop_at > 2:
                self.state = "fault"
                raise TestFault("정지 대기 중 ENC 확인 실패")
            return []
        held = keys & self.move_keys
        admin = keys & (set(PAIRS) | {"+", "-", "]", "[", "o"})
        if not focused or "space" in keys or len(held) > 1 or admin:
            self.released = False
            if self.state == "moving":
                return self.stop(now)
            if focused and not held and "space" not in keys and len(keys) == 1:
                for key in pressed:
                    if self.mode != "drive" and key in (PAIRS if self.mode == "pair" else "1234"):
                        self.selection = key
                    elif key in {"+", "]", "-", "["}:
                        self.speed = max(5, min(40, self.speed + (5 if key in {"+", "]"} else -5)))
                    elif key == "o":
                        return ["CLR"]
            return []
        if self.state == "moving":
            if held != {self.motion}:
                return self.stop(now)
        elif not self.released:
            self.released = not keys and focused
            return []
        elif len(held) == 1 and held <= pressed and keys == held:
            if self.enc_at is None:
                raise TestFault("첫 구동 전 ENC 응답 없음")
            self.state, self.motion = "moving", next(iter(held))
            self.last_send = float("-inf")
        if self.state == "moving" and now - self.last_send >= 0.1:
            self.last_send = now
            return [self.command(self.motion)]
        return []


def expected_ack(command):
    parts = command.split()
    if parts[0] == "M":
        return "OK M" + parts[1]
    if parts[0] == "P":
        return "OK P " + " ".join(parts[1:3])
    return "OK " + parts[0]


def shutdown(link, say):
    try:
        link.send("ESTOP")
        say("ESTOP 송신 시도 완료. 실제 정지는 전송만으로 확인할 수 없습니다.")
    except Exception as exc:
        say(f"ESTOP 송신 실패: {exc}. 물리 전원 차단이 필요합니다.")
    finally:
        try:
            link.ser.close()
        except Exception as exc:
            say(f"포트 닫기 실패: {exc}")


def run(mode):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="누르는 동안만 구동하는 수동 모터 시험")
    parser.add_argument("--port", required=True, help="확인한 모터 Arduino 포트; 자동 선택하지 않음")
    parser.add_argument("--speed", type=int, default=10, help="명령 비율 5~40, 기본 10 (실측 속도 아님)")
    args = parser.parse_args()
    if not 5 <= args.speed <= 40:
        parser.error("--speed는 5~40이어야 합니다")
    if sys.platform != "win32":
        parser.error("실제 조작은 Windows 콘솔 전용입니다")
    import ctypes
    import msvcrt
    import serial
    print("퓨즈·전원 차단 수단·배선·받침대·주변 인원 안전을 확인해 주세요.")
    print("바퀴를 드는 것은 퓨즈를 대신하지 않습니다. 전원 감시가 꺼진 보드는 전원을 판정하지 못합니다.")
    if input("모터 전원을 OFF로 두고 준비 조건을 확인했다면 '확인' 입력: ").strip() != "확인":
        return 1
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetForegroundWindow.restype = ctypes.c_void_p
    user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    user32.GetAsyncKeyState.restype = ctypes.c_short
    foreground = user32.GetForegroundWindow()
    if not foreground:
        raise TestFault("조작 창 확인 실패")
    log_dir = pathlib.Path(__file__).resolve().parent.parent / "data" / "motor_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{mode}_{time.time_ns()}.log"
    with log_path.open("w", encoding="utf-8") as log:
        def say(message):
            print(message, flush=True)
            log.write(f"{time.monotonic():.3f} {message}\n")
            log.flush()
        link = None
        try:
            # timeout/write_timeout을 모두 제한. 이 함수 외에는 실제 포트를 열지 않음.
            ser = serial.Serial(args.port, 115200, timeout=0, write_timeout=0.15)
            link = Link(ser)
            time.sleep(2)
            ser.reset_input_buffer()  # 부팅 READY만 제거; 이후 READY는 오류 처리
            link.request("ID", lambda s: s == "MECANUM")
            link.request("ESTOP", lambda s: s == "OK ESTOP")
            # 옛 핀맵도 ID=MECANUM이므로 검토한 펌웨어 표식까지 대조.
            link.request("INFO", lambda s: s == FIRMWARE_INFO)
            power = link.request("PWR", lambda s: s == "PWR DISABLED" or
                                 (len(s.split()) == 4 and s.split()[0] == "PWR" and
                                  all(v in {"0", "1"} for v in s.split()[1:])))
            say(power + " | 수신 ACK는 핀 전압/모터 회전 증명이 아닙니다.")
            say("단일: 1~4 선택, F/R 홀드 | 두 개: 1~6 선택, ↑/↓ 홀드")
            say("4륜: W/S 전후, A/D 회전, Z/C 평행 | +/- 속도 | Space 정지 | X/E/Esc/Q 종료")
            say("O: 동력 잠김 해제 요청. 모든 키를 놓은 뒤 새로 눌러야 구동합니다.")
            say("연결 시 모터 전원은 OFF로 유지. 준비 조건 충족 후 작업자가 전원 ON을 결정합니다.")
            control = HoldController(mode, args.speed, time.monotonic())
            last_enc = float("-inf")
            previous_status = None
            while True:
                # 오류/리셋 응답을 먼저 처리한 뒤에만 다음 구동을 판단.
                link.check(link.read())
                now = time.monotonic()
                if now - last_enc >= 0.1:
                    values = parse_encoder(link.request("ENC", lambda s: s.startswith("ENC")))
                    control.observe(values, time.monotonic())
                    last_enc = time.monotonic()
                    log.write(f"{last_enc:.3f} ENC {values}\n")
                keys = {k for k, vk in VK.items() if user32.GetAsyncKeyState(vk) & 0x8000}
                focused = user32.GetForegroundWindow() == foreground
                for _ in range(64):
                    if not msvcrt.kbhit():
                        break
                    msvcrt.getch()
                commands = control.tick(keys, focused, time.monotonic())
                for command in commands:
                    ack = expected_ack(command)
                    link.request(command, lambda s, expected=ack: s == expected)
                    log.write(f"{time.monotonic():.3f} TX {command} RX {ack}\n")
                status = (control.state, control.selection, control.speed, control.motion)
                if status != previous_status:
                    labels = {"ready": "입력 대기(실물 정지 미확정)", "moving": "구동 명령 중",
                              "stopping": "정지 명령 후 ENC 변화 대기", "fault": "오류 잠금"}
                    say(f"{control.label} | {labels[control.state]} | 명령 {control.speed}% | {control.motion or '-'}")
                    previous_status = status
                time.sleep(0.025)
        except (Exception, KeyboardInterrupt) as exc:
            say(f"중단: {exc}. 모터 전원을 OFF로 하고 원인을 확인해 주세요.")
            return 1
        finally:
            if link is not None:
                shutdown(link, say)
    return 0
