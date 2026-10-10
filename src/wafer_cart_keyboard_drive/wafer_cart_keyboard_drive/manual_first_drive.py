"""Manual-only first-drive input policy; hardware access belongs to BenchGateway."""

from __future__ import annotations

from typing import AbstractSet
import math

from .policy import KeyboardDrivePolicy


DRIVE_KEYS = frozenset({"w", "a", "s", "d", "q", "e", "up", "down", "left", "right"})


def parse_command_percent(text: str, maximum: int = 30) -> int:
    """Validate UI input without changing the controller or rounding a typo."""
    try:
        value = float(text)
    except (TypeError, ValueError):
        raise ValueError(f"출력 명령은 1~{maximum} 사이의 정수로 입력해 주세요") from None
    if not math.isfinite(value) or not value.is_integer() or not 1 <= value <= maximum:
        raise ValueError(f"출력 명령은 1~{maximum} 사이의 정수로 입력해 주세요")
    return int(value)


class ManualFirstDrive:
    """One hold at a time: legacy prepare or confirmed-session fresh key presses."""

    def __init__(self, gateway, *, percent: int = 10, mapping_verified: bool = False,
                 keyboard_hold: bool = False):
        self.max_percent = getattr(gateway, 'max_percent', 30)
        if type(percent) is not int or not 1 <= percent <= self.max_percent:
            raise ValueError(f"명령값은 1..{self.max_percent} 정수여야 합니다")
        self.gateway = gateway
        self.percent = percent
        self.mapping_verified = mapping_verified
        self.mode = "single"
        self.motor = 1
        self.keys: frozenset[str] = frozenset()
        self.focused = True
        self.prepared = False
        self.moving = False
        self.latched = False
        self.last_command: tuple | None = None
        self.keyboard_hold = keyboard_hold
        self.session_confirmed = False
        self.hold_requested = False
        self.blocked_keys: frozenset[str] = frozenset()
        self.first_error = ''

    def _fail(self, error: BaseException, *, operation='제어'):
        if not self.first_error:
            cause = getattr(self.gateway, 'first_fault', None) or getattr(self.gateway, 'fault', '미수신')
            self.first_error = f'{operation}: {error} [gateway first: {cause}]'
        self.session_confirmed = False
        self.hold_requested = False
        self.prepared = False
        self.moving = False
        self.keys = frozenset()
        self.latched = True
        self.last_command = None
        try:
            self.gateway.exchange("ESTOP")
        except Exception:
            pass  # Physical stop is never inferred from a best-effort serial write.
        raise error

    def _exchange(self, operation: str, *values: int):
        try:
            return self.gateway.exchange(operation, *values)
        except Exception as error:
            self._fail(error, operation=operation)

    def abort(self, error: BaseException):
        self._fail(error, operation='상태 수신/제어')

    def enable_keyboard_hold(self, *, operator_confirmed=False):
        if (not self.keyboard_hold or operator_confirmed is not True or self.latched or
                not self.focused or self.keys or self.moving or self.prepared):
            raise ValueError('키를 놓고 정지한 상태에서 최초 안전 확인이 필요합니다')
        if self.gateway.expected_mode != 'MANUAL_UNMONITORED':
            raise ValueError('키 홀드 시험은 지정 수동 펌웨어에서만 허용합니다')
        status = self._exchange('STATUS')
        if (status[0] == '3' or status[2:4] != ['0', '0'] or
                any(map(int, status[5:]))):
            raise ValueError('최초 안전 확인 실패: ' + status[1])
        self.session_confirmed = True
        self.hold_requested = False

    def select_mode(self, mode: str):
        if mode not in ("single", "vector"):
            raise ValueError("알 수 없는 수동 모드입니다")
        if mode == "vector" and not self.mapping_verified:
            raise ValueError("4륜 모드는 실제 바퀴 매핑 검증 전 차단합니다")
        if mode != self.mode:
            self.stop()
            self.mode = mode

    def select_motor(self, motor: int):
        if type(motor) is not int or not 1 <= motor <= 4:
            raise ValueError("모터는 M1..M4 중에서 선택해 주세요")
        if motor != self.motor:
            self.stop()
            self.motor = motor

    def set_percent(self, percent: int):
        if type(percent) is not int or not 1 <= percent <= self.max_percent:
            raise ValueError(f"명령값은 1..{self.max_percent} 정수여야 합니다")
        if self.moving or self.prepared or self.keys:
            raise ValueError("정지하고 키를 놓은 뒤 값을 변경해 주세요")
        self._exchange("LIMIT", percent)
        self.percent = percent

    def prepare(self):
        if self.latched or not self.focused or self.keys or self.moving:
            raise ValueError("정지·포커스·키 해제 상태에서만 수동 준비가 가능합니다")
        if self.mode == "vector" and not self.mapping_verified:
            raise ValueError("4륜 모드는 바퀴 매핑 검증 전 차단합니다")
        unmonitored = self.gateway.expected_mode == 'MANUAL_UNMONITORED'
        status = self._exchange("STATUS")
        if len(status) != 9 or int(status[2]) != (0 if unmonitored else 2) or int(status[3]) != 0:
            raise ValueError("전원 모드·미무장 상태를 확인해 주세요")
        if any(int(value) for value in status[5:]):
            raise ValueError("아직 감속 중입니다. 완전히 멈춘 뒤 다시 준비해 주세요")
        if unmonitored:
            self._exchange('POWER_ACK')
        self.prepared = True

    def set_keys(self, keys: AbstractSet[str], *, focused: bool = True):
        incoming = frozenset(keys) & DRIVE_KEYS
        self.focused = focused
        if not focused:
            self.blocked_keys |= self.keys | incoming
            self.stop()
            self.keys = frozenset()
            return
        self.blocked_keys &= incoming
        previous = self.keys
        self.keys = incoming - self.blocked_keys
        if not self.keys:
            self.hold_requested = False
        elif not previous and self.keyboard_hold and self.session_confirmed:
            self.hold_requested = True

    def _command(self):
        if self.mode == "single":
            direction = int("up" in self.keys) - int("down" in self.keys)
            return ("M", self.motor, direction * self.percent) if direction else None
        policy = KeyboardDrivePolicy(command_percent=self.percent,
                                     host_limit_percent=self.percent)
        motion = policy.command_for_keys(self.keys)
        if motion.is_zero:
            return None
        # The legacy bare-V policy uses right/CW-positive. C2's X-roller mixer
        # uses left/CCW-positive, so convert at this protocol boundary only.
        return "V", motion.vx_percent, -motion.vy_percent, -motion.yaw_percent

    def step(self):
        if self.latched:
            return
        command = self._command() if self.focused else None
        if command is None:
            if self.moving:
                self.stop()
            return
        if not self.prepared and not self.moving:
            if not (self.keyboard_hold and self.session_confirmed and self.hold_requested):
                return
            self.hold_requested = False  # One fresh operator gesture, never retry on tick.
            status = self._exchange('STATUS')
            if status[0] == '3':
                self._fail(RuntimeError('펌웨어 오류: ' + status[1]), operation='STATUS')
            if status[2:4] != ['0', '0']:
                self._fail(RuntimeError('전원 모드/구동 준비 상태 불일치'), operation='STATUS')
            if any(map(int, status[5:])):
                return  # Still ramping: release and press again, no delayed restart.
            self._exchange('POWER_ACK')
            self.prepared = True
        if not self.moving:
            self.prepared = False
            self._exchange("ARM")
        self._exchange(*command)
        self.moving = True
        self.last_command = command

    def stop(self):
        self.blocked_keys |= self.keys
        self.hold_requested = False
        clear_ack = self.prepared and self.gateway.expected_mode == 'MANUAL_UNMONITORED'
        self.prepared = False
        self.keys = frozenset()
        self.last_command = None
        if self.moving or self.gateway.armed or clear_ack:
            self.moving = False
            self._exchange("STOP")

    def estop(self):
        if not self.first_error:
            self.first_error = '작업자 비상정지 · X/비상정지 버튼'
        self.session_confirmed = False
        self.hold_requested = False
        self.prepared = False
        self.keys = frozenset()
        self.moving = False
        self.latched = True
        self.last_command = None
        self.gateway.exchange("ESTOP")
