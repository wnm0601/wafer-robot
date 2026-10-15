"""원본 모터 모듈을 수정하지 않고 사용하는 별도 UI 어댑터입니다."""
from __future__ import annotations

import importlib.util
import pathlib
import queue
import sys
import threading
import time

sys.dont_write_bytecode = True
BASE = pathlib.Path(__file__).resolve().parent
SOURCE = BASE.parent / "ROBOT-motor-review-928b2a8/common/manual_motor_test.py"
spec = importlib.util.spec_from_file_location("preserved_motor_control", SOURCE)
motor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(motor)


class PreviewSerial:
    """실제 포트를 열지 않는 프로토콜 대역. ENC는 가상값입니다."""
    def __init__(self):
        self.buffer = bytearray()
        self.closed = False
        self.commands = []
        self.counts = [0, 0, 0, 0]
        self.vector = (0, 0, 0)

    @property
    def in_waiting(self):
        return len(self.buffer)

    def read(self, size):
        result = bytes(self.buffer[:size])
        del self.buffer[:size]
        return result

    def write(self, data):
        if self.closed:
            raise OSError("모의 연결 종료")
        cmd = data.decode("ascii").strip()
        self.commands.append(cmd)
        fixed = {"ID": "MECANUM", "INFO": motor.FIRMWARE_INFO,
                 "PWR": "PWR DISABLED", "STOP": "OK STOP", "ESTOP": "OK ESTOP"}
        if cmd in {"STOP", "ESTOP"}:
            self.vector = (0, 0, 0)
        if cmd.startswith("V "):
            self.vector = tuple(map(int, cmd.split()[1:]))
            reply = "OK V"
        elif cmd == "ENC":
            x, y, w = self.vector
            self.counts = [a + b for a, b in zip(self.counts, (x+y+w, x-y-w, x-y+w, x+y-w))]
            reply = "ENC " + " ".join(map(str, self.counts))
        else:
            reply = fixed.get(cmd, "ERR PREVIEW")
        self.buffer.extend((reply + "\n").encode("ascii"))
        return len(data)

    def close(self):
        self.closed = True


class Session:
    """통신은 소유 작업 스레드에서만 실행합니다. 기본값은 연결 없음입니다."""
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.link = self.control = None
        self.mode = "disconnected"
        self.state = "disconnected"
        self.message = "연결 전입니다. 모의 확인 또는 실차 연결을 선택해 주세요."
        self.last_enc = float("-inf")
        self.counts = None
        self.tx = "—"
        self.last_motion = "—"
        self.speed = 10
        self.command_count = 0
        self.release_gate = True

    def exchange(self, cmd, accept):
        reply = self.link.request(cmd, accept)
        if cmd != "ENC":
            self.tx = cmd + " → " + reply
            self.command_count += 1
            if cmd.startswith("V "):
                self.last_motion = cmd
        return reply

    def connect(self, mode, port="COM7", confirmed=False, factory=None):
        if self.link is not None:
            raise ValueError("먼저 기존 연결을 종료해 주세요.")
        if mode not in {"preview", "real"}:
            raise ValueError("연결 모드 오류")
        if mode == "real" and not confirmed:
            raise ValueError("모터 전원 OFF·안전 조건 확인이 필요합니다.")
        self.mode, self.state = mode, "connecting"
        self.counts, self.last_enc, self.release_gate = None, float("-inf"), True
        try:
            if mode == "preview":
                ser = factory() if factory else PreviewSerial()
            elif factory:
                ser = factory()
            else:
                import serial
                ser = serial.Serial(port, 115200, timeout=0, write_timeout=0.15)
            self.link = motor.Link(ser)
            if mode == "real" and factory is None:
                time.sleep(2)
                ser.reset_input_buffer()
            self.exchange("ESTOP", lambda s: s == "OK ESTOP")
            self.exchange("ID", lambda s: s == "MECANUM")
            self.exchange("INFO", lambda s: s == motor.FIRMWARE_INFO)
            self.exchange("PWR", lambda s: s == "PWR DISABLED")
            self.control = motor.HoldController("drive", self.speed, self.clock())
            self.state = "stopping"
            self.message = "모의 연결 · 실제 출력 없음" if mode == "preview" else "실차 연결 · 전원 감지 없음 · 실제 위치 미측정"
        except Exception as exc:
            self.fail(str(exc))

    def stop(self):
        self.release_gate = True
        if self.link and self.control:
            for cmd in self.control.stop(self.clock()):
                self.exchange(cmd, lambda s: s == "OK STOP")
            self.state = "stopping"

    def change_speed(self, delta, keys=()):
        if delta not in {-5, 5}:
            raise ValueError("출력은 5 단위로만 변경합니다.")
        if self.control is None:
            self.speed = max(5, min(40, self.speed + delta))
        elif self.control.state == "ready" and not keys:
            # 원본의 출력 조절 분기를 그대로 사용합니다.
            key = "]" if delta > 0 else "["
            self.control.tick(set(), True, self.clock())
            self.control.tick({key}, True, self.clock())
            self.speed = self.control.speed
            self.release_gate = True
        else:
            self.stop()
            self.message = "먼저 키를 놓고 정지한 뒤 출력을 변경해 주세요."

    def tick(self, keys, focused, timestamp):
        if self.link is None or self.control is None:
            return
        now = self.clock()
        if now - timestamp > 0.30:
            raise motor.TestFault("UI 응답 중단: 정지 후 연결을 종료합니다.")
        self.link.check(self.link.read())
        if now - self.last_enc >= 0.1:
            line = self.exchange("ENC", lambda s: s.startswith("ENC "))
            self.counts = motor.parse_encoder(line)
            self.last_enc = self.clock()
            self.control.observe(self.counts, self.last_enc)
        # 연결/설정/정지 후에는 모든 입력이 해제된 것을 먼저 확인합니다.
        if self.release_gate:
            if not keys and focused:
                self.release_gate = False
            focused = False
        for cmd in self.control.tick(set(keys), focused, self.clock()):
            ack = motor.expected_ack(cmd)
            self.exchange(cmd, lambda s, a=ack: s == a)
        self.state, self.speed = self.control.state, self.control.speed

    def disconnect(self, message="연결을 종료했습니다.", fault=False):
        failure = None
        if self.link:
            try:
                self.exchange("ESTOP", lambda s: s == "OK ESTOP")
            except Exception as exc:
                failure = str(exc)
            finally:
                try:
                    self.link.ser.close()
                except Exception as exc:
                    failure = str(exc)
        self.link = self.control = None
        self.state = "fault" if fault or failure else "disconnected"
        self.message = message + (" / 정지 확인 실패: " + failure + " · 물리 전원을 차단해 주세요." if failure else "")
        self.release_gate = True

    def fail(self, reason):
        self.disconnect("중단: " + reason + " · 모터 전원을 OFF로 해 주세요.", fault=True)

    def snapshot(self):
        return dict(mode=self.mode, state=self.state, message=self.message, speed=self.speed,
                    enc=self.counts, age=None if self.counts is None else self.clock()-self.last_enc,
                    tx=self.tx, commands=self.command_count, last_motion=self.last_motion,
                    motion=self.control.motion if self.control else None)


class Worker(threading.Thread):
    def __init__(self, preview_only=False):
        super().__init__(daemon=False)
        self.preview_only = preview_only
        self.actions = queue.Queue(maxsize=32)
        self.lock = threading.Lock()
        self.input = (set(), False, time.monotonic())
        self.session = Session()
        self.status = self.session.snapshot()
        self.quit = threading.Event()

    def publish(self, keys, focused):
        with self.lock:
            self.input = (set(keys), focused, time.monotonic())

    def request(self, action, *args):
        try:
            self.actions.put_nowait((action, args))
        except queue.Full:
            self.quit.set()

    def get_status(self):
        with self.lock:
            return dict(self.status)

    def run(self):
        try:
            while not self.quit.is_set():
                try:
                    with self.lock:
                        keys, focused, stamp = self.input
                    while not self.actions.empty():
                        action, args = self.actions.get_nowait()
                        if action == "connect":
                            if self.preview_only and args[0] != "preview":
                                raise ValueError("이 실행은 모의 전용입니다.")
                            with self.lock:
                                self.status = dict(self.session.snapshot(), state="connecting")
                            self.session.connect(*args)
                        elif action == "stop":
                            self.session.stop()
                        elif action == "disconnect":
                            self.session.disconnect()
                        elif action == "estop":
                            self.session.disconnect("작업자 즉시 정지 · 재연결 전 전원 OFF를 확인해 주세요.", fault=True)
                        elif action == "speed":
                            self.session.change_speed(args[0], keys)
                    # 접속 대기 중의 오래된 입력은 절대 구동에 사용하지 않습니다.
                    with self.lock:
                        keys, focused, stamp = self.input
                    self.session.tick(keys, focused, stamp)
                except Exception as exc:
                    self.session.fail(str(exc))
                with self.lock:
                    self.status = self.session.snapshot()
                self.quit.wait(0.025)
        finally:
            self.session.disconnect("UI 종료")

