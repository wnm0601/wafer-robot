"""In-memory wire fixture, NOT Arduino/emulator/physical voltage feedback."""
from __future__ import annotations

import collections
import threading
import time

from .bench_protocol import ProtocolError, frame, unframe


class MockWire:
    simulation_fixture = True
    def __init__(self, *, mapping_verified: bool = False, locked_firmware: bool = False,
                 simulate_encoder: bool = False):
        self._condition = threading.Condition()
        self._queue = collections.deque()
        self.closed = False
        self.sent = []
        self.session, self.sequence = "-", 0
        self.power, self.button, self.seen_off = False, False, True
        self.armed, self.limit = False, 0
        self.state, self.reason = 3, "POWER_OFF"
        self.mapping_verified, self.locked_firmware = mapping_verified, locked_firmware
        self.simulate_encoder = simulate_encoder
        self.current, self.target, self.counts = [0] * 4, [0] * 4, [0] * 4
        self.start = self.last_ramp = self.lease = time.monotonic()
        self.activity = [self.start] * 4
        self.last_encoder = [self.start] * 4
        self.previous = [0] * 4

    def _emit(self, payload):
        self._queue.append(frame(payload))
        self._condition.notify_all()

    def _fault(self, reason):
        self.armed = False
        self.current, self.target = [0] * 4, [0] * 4
        self.state, self.seen_off = 3, not self.power
        if reason != self.reason:
            self.reason = reason
            self._emit(f"E2 {self.session} {reason}")

    def power_feedback(self, on: bool, *, estop: bool = False):
        if type(on) is not bool or type(estop) is not bool:
            raise ValueError("mock feedback must be boolean")
        with self._condition:
            changed = on != self.power
            self.power = on
            if estop and not self.button:
                self._fault("ESTOP_INPUT")
            self.button = estop
            if not on:
                if changed:
                    self._fault("POWER_OFF")
                self.seen_off = True

    def inject(self, payload: str):
        with self._condition:
            self._emit(payload)

    def _tick(self):
        now = time.monotonic()
        if self.armed and now - self.lease >= 0.5:
            self._fault("COMMAND_TIMEOUT")
        for i in range(4):
            if (self.simulate_encoder and abs(self.current[i]) >= 5
                    and now - self.last_encoder[i] >= 0.02):
                self.counts[i] += 1 if self.current[i] > 0 else -1
                self.last_encoder[i] = now
            if self.previous[i] != self.counts[i] or abs(self.current[i]) < 5:
                self.activity[i] = now
            self.previous[i] = self.counts[i]
            if self.armed and abs(self.current[i]) >= 5 and now - self.activity[i] >= 0.6:
                self._fault("STALL_NO_ENCODER")
                break
        if now - self.last_ramp >= 0.015:
            self.last_ramp = now
            for i in range(4):
                goal = 0 if self.target[i] * self.current[i] < 0 else self.target[i]
                self.current[i] += max(-2, min(2, goal - self.current[i]))
            if self.state == 2 and not any(self.current + self.target):
                self.state = 0

    def write(self, raw: bytes):
        with self._condition:
            if self.closed:
                raise OSError("mock wire closed")
            self.sent.append(raw)
            self._tick()
            if raw in (b"STOP\n", b"ESTOP\n"):
                self._fault("OPERATOR_ESTOP")
                # Emergency escape intentionally has no ACK in this fixture.
                return
            tokens, sid, seq, op = [], self.session, 0, "FRAME"
            try:
                tokens = unframe(raw)
                if len(tokens) < 4 or tokens[0] != "C2":
                    raise ProtocolError("bad header")
                _, sid, seq, op, *args = tokens
                seq = int(seq)
                if op == "HELLO" and not args and seq == 1 and sid != self.session:
                    self.session, self.sequence = sid, 1
                    self.armed, self.limit = False, 0
                    self.current, self.target = [0] * 4, [0] * 4
                    mode = "OUTPUT_LOCKED" if self.locked_firmware else "SIM_ONLY"
                    self._emit(f"R2 {sid} 1 OK HELLO CART_2 HKX_20260929 {mode}")
                    return
                if sid != self.session or seq != self.sequence + 1:
                    raise ProtocolError("SESSION_OR_REPLAY")
                self.sequence = seq
                data = ""
                if op == "LIMIT" and len(args) == 1 and not self.armed and not any(self.current + self.target):
                    value = int(args[0])
                    if not 1 <= value <= 30:
                        raise ValueError("INVALID_LIMIT")
                    self.limit = value
                elif op == "ARM" and not args:
                    if (not self.power or self.button or not self.seen_off
                            or not self.limit or any(self.current + self.target)):
                        raise ValueError("REARM_CONDITIONS")
                    self.armed, self.state, self.reason = True, 1, "READY_SIM_ONLY"
                    self.lease = time.monotonic()
                elif op == "M" and len(args) == 2:
                    channel, pct = map(int, args)
                    if not self.armed or not 1 <= channel <= 4 or abs(pct) > self.limit:
                        raise ValueError("MOTION_REJECTED")
                    if any(v != 0 for i, v in enumerate(self.current) if i != channel - 1):
                        raise ValueError("OTHER_MOTOR_NOT_STOPPED")
                    self.target = [int(pct * 200 / 100) if i == channel - 1 else 0 for i in range(4)]
                    self.lease = time.monotonic()
                elif op == "V" and len(args) == 3:
                    x, y, w = map(int, args)
                    if not self.armed or not self.mapping_verified or max(abs(x), abs(y), abs(w)) > 30:
                        raise ValueError("MAPPING_OR_MOTION_REJECTED")
                    mixed = [x-y-w, x+y+w, x+y-w, x-y+w]
                    maximum = max(self.limit, *map(abs, mixed))
                    self.target = [int(v * self.limit * 200 / (maximum * 100)) for v in mixed]
                    self.lease = time.monotonic()
                elif op == "STOP" and not args:
                    self.armed, self.target = False, [0] * 4
                    if self.state != 3:
                        self.state, self.reason = 2, "OPERATOR_STOP"
                elif op == "ESTOP" and not args:
                    self._fault("OPERATOR_ESTOP")
                elif op == "STATUS" and not args:
                    data = " ".join(map(str, (self.state, self.reason, 2 if self.power else 1,
                                              int(self.armed), self.limit, *self.current)))
                elif op == "ENC" and not args:
                    data = " ".join(map(str, (int((time.monotonic() - self.start) * 1000), *self.counts)))
                elif op == "INFO" and not args:
                    data = "CART_2 HKX_20260929 SIM_ONLY"
                else:
                    raise ValueError("BAD_OPERATION_OR_ARGS")
                self._emit(f"R2 {sid} {seq} OK {op}" + (" " + data if data else ""))
            except (ValueError, ProtocolError) as error:
                self._fault(str(error).replace(" ", "_"))
                if len(tokens) >= 4:
                    self._emit(f"R2 {sid} {seq} ERR {op} {str(error).replace(' ', '_')}")

    def readline(self) -> bytes:
        with self._condition:
            self._tick()
            if not self._queue and not self.closed:
                self._condition.wait(0.02)
                self._tick()
            return self._queue.popleft() if self._queue else b""

    def close(self):
        with self._condition:
            self.closed = True
            self.armed = False
            self.current, self.target = [0] * 4, [0] * 4
            self._condition.notify_all()
