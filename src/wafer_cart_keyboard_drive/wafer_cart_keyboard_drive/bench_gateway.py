"""One stream owner/reader; real manual port opening lives in manual_hardware."""
from __future__ import annotations

import collections
import secrets
import threading
import time
from typing import Protocol

from .bench_protocol import ProtocolError, request, unframe


class FirmwareRejected(ProtocolError):
    """Valid ERR reply: motion remains locked but diagnostics stay available."""


def decode_output_diagnostics(payload: list[str]) -> dict:
    """Compare AVR register readback; never claims to measure an electrical waveform."""
    if payload == ['UNAVAILABLE']:
        return {'available': False, 'waveform_measured': False}
    names = ('mcu_ms enabled denominator top1 top5 tccr1a tccr1b tccr5a tccr5b '
             'ocr1a ocr1b ocr5a ocr5b ocr5c ddrb ddrl ddrc portc pinc '
             'out1 out2 out3 out4').split()
    try:
        if len(payload) != 24 or payload[0] != 'IO1':
            raise ValueError('version/length')
        r = dict(zip(names, map(int, payload[1:])))
        if (not 0 <= r['mcu_ms'] <= 0xffffffff or r['enabled'] not in (0, 1)
                or r['denominator'] not in (200, 255)
                or any(not 0 <= r[k] <= 65535 for k in ('top1','top5','ocr1a','ocr1b','ocr5a','ocr5b','ocr5c'))
                or any(not 0 <= r[k] <= 255 for k in ('tccr1a','tccr1b','tccr5a','tccr5b','ddrb','ddrl','ddrc','portc','pinc'))
                or any(abs(r['out'+str(i)]) > 80 for i in range(1,5))):
            raise ValueError('range')
    except (ValueError, TypeError) as error:
        raise ProtocolError('invalid IO diagnostic payload') from error
    issues = []
    if r['top1'] != r['top5'] or r['top1'] not in (3199,4095): issues.append('PWM_TOP_MISMATCH')
    if r['tccr1b'] != 25 or r['tccr5b'] != 25: issues.append('TIMER_MODE_OR_PRESCALER')
    if r['ddrb'] & 0x60 != 0x60 or r['ddrl'] & 0x30 != 0x30 or r['ddrc'] & 0x0f != 0x0f:
        issues.append('PIN_NOT_OUTPUT')
    outputs = [r['out'+str(i)] if r['enabled'] else 0 for i in range(1,5)]
    expected = [abs(v)*r['top1' if i in (0,2) else 'top5']//r['denominator'] for i,v in enumerate(outputs)]
    actual = [r[k] for k in ('ocr1a','ocr5c','ocr1b','ocr5b')]
    if actual != expected: issues.append('OCR_MISMATCH')
    if r['ocr5a'] != 0: issues.append('UNUSED_D46_REGISTER_NONZERO')
    c1 = 2 | (128 if expected[0] else 0) | (32 if expected[2] else 0)
    c5 = 2 | (8 if expected[1] else 0) | (32 if expected[3] else 0)
    if r['tccr1a'] != c1 or r['tccr5a'] != c5: issues.append('PWM_CHANNEL_ENABLE_MISMATCH')
    direction = sum(1 << bit for bit,v in zip((3,1,2,0),outputs) if v >= 0)
    if r['portc'] & 15 != direction: issues.append('DIR_LATCH_MISMATCH')
    if r['pinc'] & 15 != r['portc'] & 15: issues.append('DIR_DIGITAL_READBACK_MISMATCH')
    return {'available': True, 'waveform_measured': False, 'registers': r,
            'expected_ocr_m1_m4': expected, 'actual_ocr_m1_m4': actual,
            'issues': issues, 'register_check_passed': not issues,
            'note': 'Arduino 내부 레지스터/디지털 입력 읽기입니다. 전압·전류·PWM 파형 실측이 아닙니다.'}


class Wire(Protocol):
    def write(self, data: bytes) -> None: ...
    def readline(self) -> bytes: ...  # bounded timeout, e.g. 20 ms
    def close(self) -> None: ...


class SerialStreamWire:
    """Bounded serial-like byte I/O adapter; never constructs or opens a COM port."""
    def __init__(self, stream):
        if (type(stream.timeout) not in (int, float) or not 0 < stream.timeout <= 0.05
                or type(stream.write_timeout) not in (int, float)
                or not 0 < stream.write_timeout <= 0.1):
            raise ValueError("bounded read/write timeouts required")
        self.stream = stream
        self._buffer = bytearray()
        self._write_lock = threading.Lock()

    def write(self, data: bytes):
        with self._write_lock:
            if self.stream.write(data) != len(data):
                raise OSError("partial serial write")
            # Do NOT flush: pyserial flush can wait indefinitely for a lost device.

    def readline(self) -> bytes:
        if b"\n" not in self._buffer:
            data = self.stream.read(64)
            if not isinstance(data, bytes):
                raise ProtocolError("invalid byte stream")
            self._buffer.extend(data)
        end = self._buffer.find(b"\n")
        if end < 0:
            if len(self._buffer) > 239:
                raise ProtocolError("oversize unterminated serial frame")
            return b""
        if end > 239:
            raise ProtocolError("oversize serial frame")
        result = bytes(self._buffer[:end + 1])
        del self._buffer[:end + 1]
        return result

    def close(self):
        self.stream.close()


def open_physical_wire(*, port: str, profile: dict) -> Wire:
    # No file/boolean/CLI argument is accepted as proof of electrical safety.
    raise RuntimeError("실제 serial 잠금: 전원·revision·피드백 검증과 별도 승인 후 구현을 활성화해야 합니다")


class BenchGateway:
    """Exactly one reader handles ACK and asynchronous events, even while idle."""
    def __init__(self, wire: Wire, *, timeout: float = 0.25, session: str | None = None,
                 expected_mode: str = "SIM_ONLY"):
        if expected_mode not in ('SIM_ONLY','MANUAL_ONLY','MANUAL_UNMONITORED'):
            raise ValueError('unsupported firmware mode')
        self.expected_mode = expected_mode
        self.max_percent = 40 if expected_mode == 'MANUAL_UNMONITORED' else 30
        if not 0.02 <= timeout <= 0.35:
            raise ValueError("invalid ACK timeout")
        self.wire, self.timeout = wire, timeout
        self.session = session or secrets.token_hex(8)
        self.sequence = 0
        self.armed = False
        self.connected = False
        self.mode = "UNKNOWN"
        self.fault = "STARTUP_LOCKED"
        self.first_fault = None
        self.trace = collections.deque(maxlen=128)
        self.events = collections.deque(maxlen=64)
        self._exchange_lock = threading.Lock()
        self._condition = threading.Condition()
        self._pending = None
        self._reply = None
        self._broken = None
        self._closed = False
        self._event_generation = 0
        self._reader = threading.Thread(target=self._read, name="bench-wire-reader", daemon=True)
        self._reader.start()

    def _break(self, error: BaseException):
        with self._condition:
            self._broken = str(error)
            self.armed = False
            self.fault = "TRANSPORT_FAULT"
            if self.first_fault is None: self.first_fault = 'TRANSPORT_FAULT: ' + str(error)
            self._condition.notify_all()
        # This is a best-effort stop, never treated as a physical stop guarantee.
        try:
            self.wire.write(b"ESTOP\n")
        except Exception:
            pass

    def _read(self):
        try:
            while not self._closed:
                raw = self.wire.readline()
                if not raw:
                    continue
                tokens = unframe(raw)
                with self._condition:
                    self.trace.append({'monotonic_s': time.monotonic(), 'direction': 'rx', 'tokens': tokens})
                    if tokens[0] == "E2":
                        if len(tokens) != 3 or tokens[1] not in ("-", self.session):
                            raise ProtocolError("invalid event/session")
                        self.events.append(tokens[2])
                        self._event_generation += 1
                        self.armed = False
                        self.fault = tokens[2]
                        if tokens[2] != 'BOOT_OUTPUT_LOCKED' and self.first_fault is None:
                            self.first_fault = tokens[2]
                        if tokens[2] == "BOOT_OUTPUT_LOCKED" and self.connected:
                            raise ProtocolError("controller restarted")
                        self._condition.notify_all()
                    elif tokens[0] == "R2":
                        if (len(tokens) < 5 or tokens[3] not in ("OK", "ERR")
                                or tokens[1:3] != [self.session, str(self.sequence)]
                                or self._pending != tokens[4] or self._reply is not None):
                            raise ProtocolError("stale, duplicate or mismatched ACK")
                        self._reply = tokens
                        if tokens[3] == "ERR":
                            self.armed = False
                            self.fault = " ".join(tokens[5:]) or "FIRMWARE_REJECTED"
                            if self.first_fault is None: self.first_fault = self.fault
                        self._condition.notify_all()
                    else:
                        raise ProtocolError("unsupported message/version")
        except Exception as error:
            if not self._closed:
                self._break(error)

    def exchange(self, operation: str, *values: int) -> list[str]:
        with self._exchange_lock:
            # Validate locally before changing sequence or writing anything.
            wire_data = request(self.session, self.sequence + 1, operation, *values, max_percent=self.max_percent)
            with self._condition:
                if self._closed or self._broken:
                    raise ProtocolError(self._broken or "gateway closed")
                if self.sequence == 0 and operation != "HELLO":
                    raise ProtocolError("HELLO required")
                if operation in ("M", "V") and not self.armed:
                    raise ProtocolError("manual ARM required")
                self.sequence += 1
                self._pending, self._reply = operation, None
                self.trace.append({'monotonic_s': time.monotonic(), 'direction': 'tx',
                                   'operation': operation, 'values': values, 'sequence': self.sequence})
                generation = self._event_generation
            try:
                self.wire.write(wire_data)
                deadline = time.monotonic() + self.timeout
                with self._condition:
                    while self._reply is None and self._broken is None:
                        left = deadline - time.monotonic()
                        if left <= 0:
                            raise TimeoutError("ACK timeout")
                        self._condition.wait(left)
                    if self._broken:
                        raise ProtocolError(self._broken)
                    result = self._reply
                    if result[3] != "OK":
                        raise FirmwareRejected("firmware rejected: " + " ".join(result[5:]))
                    if operation in ("ARM", "M", "V") and generation != self._event_generation:
                        raise ProtocolError("fault/event during motion exchange")
                    payload = result[5:]
                    if operation in ("ARM", "POWER_ACK", "LIMIT", "M", "V", "STOP", "ESTOP") and payload:
                        raise ProtocolError("unexpected ACK payload")
                    if operation == "INFO" and payload != ["CART_2", "HKX_20260929", self.expected_mode]:
                        raise ProtocolError("unexpected firmware identity")
                    if operation == "STATUS":
                        try:
                            if len(payload) != 9:
                                raise ValueError("status field count")
                            numeric = [int(v) for i, v in enumerate(payload) if i != 1]
                            state, power, device_armed, limit, *outputs = numeric
                            if (state not in range(4) or power not in range(3) or device_armed not in (0, 1)
                                    or not 0 <= limit <= self.max_percent or any(abs(v) > self.max_percent * 2 for v in outputs)
                                    or (device_armed == 1 and (state != 1 or power != (0 if self.expected_mode == 'MANUAL_UNMONITORED' else 2)))):
                                raise ValueError("inconsistent status")
                        except ValueError as error:
                            raise ProtocolError("invalid status payload") from error
                        if not device_armed:
                            self.armed = False
                            self.fault = payload[1]
                    if operation == "HELLO":
                        if result[5:] != ["CART_2", "HKX_20260929", self.expected_mode]:
                            raise ProtocolError("matching firmware mode required: " + self.expected_mode)
                        self.mode, self.connected = self.expected_mode, True
                    elif operation == "ARM":
                        # An event AFTER ACK is observed by the same reader before this lock.
                        self.armed = True
                        self.first_fault = None
                        self.fault = "READY_" + self.expected_mode
                    elif operation in ("STOP", "ESTOP"):
                        self.armed = False
                        self.fault = "OPERATOR_STOP" if operation == "STOP" else "OPERATOR_ESTOP"
                    return result[5:]
            except FirmwareRejected:
                raise
            except Exception as error:
                self._break(error)
                raise
            finally:
                with self._condition:
                    self._pending = None

    def connect(self, *, limit_percent: int = 20):
        self.exchange("HELLO")
        self.exchange("LIMIT", limit_percent)

    def diagnostic_snapshot(self) -> dict:
        """Explicit stopped-only diagnostics for firmware with DIAG/IO support."""
        if self.armed:
            raise ProtocolError('진단 조회는 정지 후 수행해 주세요')
        fault = self.exchange('DIAG')
        try:
            if len(fault) != 10: raise ValueError('field count')
            at = int(fault[1]); outputs = list(map(int,fault[2:6])); counts = list(map(int,fault[6:]))
            if (not 0 <= at <= 0xffffffff or any(abs(v)>80 for v in outputs)
                    or any(not -2**31 <= v < 2**31 for v in counts)):
                raise ValueError('range')
        except ValueError as error:
            raise ProtocolError('invalid DIAG payload') from error
        return {'first_firmware_fault': fault[0], 'fault_mcu_ms': at,
                'pre_stop_outputs_m1_m4': outputs, 'fault_encoder_m1_m4': counts,
                'output': decode_output_diagnostics(self.exchange('IO')),
                'received_monotonic_s': time.monotonic(),
                'source': 'PC fixture' if getattr(self.wire,'simulation_fixture',False) else 'Arduino',
                'motor_authorization': False}

    def encoder_snapshot(self) -> dict:
        values = self.exchange("ENC")
        try:
            if len(values) != 5:
                raise ValueError("expected MCU time and four counts")
            parsed = [int(v) for v in values]
            if (not 0 <= parsed[0] <= 0xffffffff
                    or any(not -0x80000000 <= v <= 0x7fffffff for v in parsed[1:])):
                raise ValueError("encoder range")
            return dict(mcu_ms=parsed[0], counts_m1_m4=parsed[1:],
                        received_monotonic_s=time.monotonic(), measured=self.mode in ('MANUAL_ONLY','MANUAL_UNMONITORED')
                        and not getattr(self.wire,'simulation_fixture',False))
        except ValueError as error:
            self._break(error)
            raise ProtocolError("invalid encoder response") from error

    def jog(self, channel: int, percent: int, *, duration: float = 0.15):
        if (type(duration) not in (int, float) or not 0.02 <= duration <= 2.0):
            raise ValueError("mock jog must be bounded to 0.02..2 seconds")
        request(self.session, self.sequence + 1, "M", channel, percent, max_percent=self.max_percent)
        try:
            end = time.monotonic() + duration
            while time.monotonic() < end:
                self.exchange("M", channel, percent)
                time.sleep(min(0.05, max(0.0, end - time.monotonic())))
        finally:
            if not self._broken and not self._closed:
                self.exchange("STOP")

    def close(self):
        if self._closed:
            return
        # No rearm or motion during close, even if ordinary STOP is still ramping.
        try:
            if self.connected and not self._broken:
                self.exchange("ESTOP")
        except (ProtocolError, TimeoutError, OSError):
            pass
        finally:
            self.armed = False
            self._closed = True
            self.wire.close()
            self._reader.join(timeout=0.5)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
