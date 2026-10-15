"""20% 전진 시간 제어. 보존된 Session/펌웨어를 수정하지 않습니다."""
from __future__ import annotations

import math
import csv
import queue
import re
import time
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass

from driver_adapter import Session, Worker, motor

DEFAULT_SECONDS_PER_M = 8.543714285714286


@dataclass(frozen=True)
class Plan:
    metres: float
    seconds_per_m: float

    def __post_init__(self):
        if not all(math.isfinite(v) for v in (self.metres, self.seconds_per_m)):
            raise ValueError("거리와 시간은 유한한 숫자로 입력해 주세요.")
        if not 0.1 <= self.metres <= 5:
            raise ValueError("목표 거리는 0.1~5m입니다.")
        if not 0.5 <= self.seconds_per_m <= 30:
            raise ValueError("1m당 시간은 0.5~30초입니다.")
        if not 0.5 <= self.duration <= 60:
            raise ValueError("한 번의 명령 시간은 0.5~60초입니다.")

    @property
    def duration(self):
        return self.metres * self.seconds_per_m


class DeadlineReached(Exception):
    pass


@dataclass(frozen=True)
class RotationPlan:
    direction: str
    angle: int

    def __post_init__(self):
        if self.direction not in {"a", "d"} or self.angle not in {45, 90}:
            raise ValueError("좌/우 45도 또는 90도만 선택해 주세요.")

    @property
    def duration(self):
        return self.angle / 45.0  # 사용자 확인: 20%, 45도 1초 / 90도 2초

    @property
    def metres(self):
        return None


@dataclass(frozen=True)
class RouteTurn(RotationPlan):
    def __post_init__(self):
        if self.direction not in {"a", "d"} or not math.isfinite(self.angle) or not 5 <= self.angle <= 180:
            raise ValueError("회전각은 5~180도입니다. 시간 비례 예상값이며 실측 각도가 아닙니다.")


@dataclass(frozen=True)
class LateralPlan:
    direction: str
    seconds: float

    def __post_init__(self):
        if self.direction not in {"z", "c"} or not math.isfinite(self.seconds) or not .5 <= self.seconds <= 60:
            raise ValueError("평행이동 시간은 0.5~60초입니다. 실제 거리는 자동 측정하지 않습니다.")

    @property
    def duration(self):
        return self.seconds

    @property
    def metres(self):
        return None


def parse_sequence(text, seconds_per_m=DEFAULT_SECONDS_PER_M):
    """제한된 명령 문법만 전체 일치 검사합니다. 자연어 추측/eval은 없습니다."""
    if not isinstance(text, str) or not text.strip() or len(text) > 4000:
        raise ValueError("동작을 1~20개 입력해 주세요. 최대 4000자입니다.")
    if not math.isfinite(seconds_per_m) or not .5 <= seconds_per_m <= 30:
        raise ValueError("1m당 시간은 0.5~30초입니다.")
    parts = [p.strip() for p in re.split(r"\r?\n|->|→|,|;", text) if p.strip()]
    if not 1 <= len(parts) <= 20:
        raise ValueError("한 번에 1~20개 동작만 실행할 수 있습니다.")
    plans = []
    for index, part in enumerate(parts, 1):
        match = re.fullmatch(r"(직진|전진|좌회전|우회전|왼쪽 평행|오른쪽 평행)\s*([0-9]+(?:\.[0-9]+)?)\s*(m|미터|도|°|초)", part, re.IGNORECASE)
        if not match:
            raise ValueError(f"{index}번 입력 확인: 직진 1m / 우회전 90도 / 왼쪽 평행 2초 형식으로 입력해 주세요.")
        operation, number, unit = match.groups()
        try:
            if operation in {"직진", "전진"} and unit.lower() in {"m", "미터"}:
                plans.append(Plan(float(number), seconds_per_m))
            elif operation in {"좌회전", "우회전"} and unit in {"도", "°"}:
                plans.append(RouteTurn("a" if operation == "좌회전" else "d", float(number)))
            elif operation in {"왼쪽 평행", "오른쪽 평행"} and unit == "초":
                plans.append(LateralPlan("z" if operation == "왼쪽 평행" else "c", float(number)))
            else:
                raise ValueError("직진은 m, 회전은 도, 평행이동은 초 단위를 사용해 주세요.")
        except ValueError as exc:
            raise ValueError(f"{index}번: {exc}") from exc
    if sum(p.duration for p in plans) > 120:
        raise ValueError("전체 구동 명령 시간은 120초 이내로 나눠 주세요. 구간 정지 대기는 별도입니다.")
    return tuple(plans)


def describe_plan(plan):
    if isinstance(plan, LateralPlan):
        return f"{'왼쪽' if plan.direction == 'z' else '오른쪽'} 평행 → {plan.duration:g}초 / 거리 미측정"
    return (f"{'좌회전' if plan.direction == 'a' else '우회전'} {plan.angle:g}도"
            if isinstance(plan, RotationPlan) else f"직진 {plan.metres:g}m") + f" → {plan.duration:.2f}초"


class TimedSession(Session):
    def __init__(self, clock=time.monotonic):
        super().__init__(clock)
        self.speed = 20
        self.plan = None
        self.started = None
        self.ended = None
        self.active = False
        self.result = "설정 후 시작 버튼을 눌러 주세요."
        self.hold_direction = None
        self.rotation_angle = None
        self.record = None
        self.records = []
        self.sequence_active = False
        self.sequence = ()
        self.sequence_index = -1
        self.sequence_note = "동작 순서 대기"
        self._sequence_launch = False

    def start_sequence(self, text, seconds_per_m, focused, timestamp):
        plans = parse_sequence(text, seconds_per_m)  # 전체 검증 후에만 첫 구간 시작
        if self.sequence_active:
            raise ValueError("동작 순서 실행 중입니다.")
        self._sequence_launch = True
        try:
            self.start_plan(plans[0], focused, timestamp)
        finally:
            self._sequence_launch = False
        self.sequence, self.sequence_index, self.sequence_active = plans, 0, True
        self._configure_sequence_step()

    def _configure_sequence_step(self):
        if isinstance(self.plan, RotationPlan):
            self.hold_direction, self.rotation_angle = self.plan.direction, self.plan.angle
        elif isinstance(self.plan, LateralPlan):
            self.hold_direction = self.plan.direction
        self.sequence_note = f"{self.sequence_index+1}/{len(self.sequence)} · {describe_plan(self.plan)}"
        self.result = self.sequence_note + " / 시간 기반 예상"

    def advance_sequence(self, focused, timestamp):
        if self.sequence_index+1 == len(self.sequence):
            self.sequence_active = False
            self.sequence_note = "전체 순서 완료 · 실제 도착/각도 미확인"
            return
        self.sequence_index += 1
        self._sequence_launch = True
        try:
            self.start_plan(self.sequence[self.sequence_index], focused, timestamp)
        finally:
            self._sequence_launch = False
        self._configure_sequence_step()

    def cancel_sequence(self, reason):
        if self.sequence_active:
            self.sequence_active = False
            self.sequence_note = "순서 취소 · 남은 동작 실행 안 함 / " + reason

    def start_hold(self, direction, focused, timestamp):
        if direction not in {"a", "d"}:
            raise ValueError("좌회전 또는 우회전만 선택해 주세요.")
        self.start_plan(Plan(2, 30), focused, timestamp)  # 홀드도 60초 상한
        self.hold_direction = direction
        self.result = "버튼을 누르는 동안 회전 · 놓으면 정지"

    def start_rotation(self, direction, angle, focused, timestamp):
        plan = RotationPlan(direction, angle)
        self.start_plan(plan, focused, timestamp)
        self.hold_direction, self.rotation_angle = direction, angle
        self.result = f"{'좌' if direction == 'a' else '우'} {angle}° 예상 · {plan.duration:g}초 후 정지 · 실제 각도 미측정"

    def deadline_reason(self):
        return (f"{self.rotation_angle}° 기준 {self.plan.duration:g}초 종료 · 실제 각도 미측정"
                if self.rotation_angle else "설정 시간 종료 · 실제 거리/각도 미확인")

    def start_plan(self, plan, focused, timestamp):
        if self.sequence_active and not self._sequence_launch:
            raise ValueError("순서 실행 중에는 다른 동작을 시작할 수 없습니다.")
        if self.active or self.record:
            raise ValueError("이미 진행 중입니다. 중복 시작하지 않습니다.")
        if self.state != "ready" or not self.control or self.release_gate or not self.control.released:
            raise ValueError("연결 후 입력 대기 상태에서 시작해 주세요.")
        if not focused or self.clock() - timestamp > 0.30:
            raise ValueError("이 창이 활성화된 상태에서 다시 시작해 주세요.")
        if self.speed != 20 or self.control.speed != 20:
            raise ValueError("시간 이동은 출력 20%만 허용합니다.")
        self.plan, self.started, self.ended = plan, None, None
        self.hold_direction = None
        self.rotation_angle = None
        self.active = True
        self.result = "20% 전진 시작 준비"

    def exchange(self, cmd, accept):
        if cmd.startswith("V "):
            expected = {None:"V 20 0 0", "a":"V 0 0 -20", "d":"V 0 0 20",
                        "z":"V 0 -20 0", "c":"V 0 20 0"}[self.hold_direction]
            if not self.active or cmd != expected:
                raise motor.TestFault("허용하지 않은 시간 이동 명령")
            now = self.clock()
            if self.started is None:
                self.started = now  # 첫 명령 전송 직전부터 측정합니다.
                self.result = "20% 전진 명령 전송 중 · 남은 시간에 따라 정지"
                if self.hold_direction or self.sequence_active:
                    if self.hold_direction:
                        self.result = (f"{self.rotation_angle}° 예상 시간 회전 · {self.plan.duration:g}초 후 정지"
                                       if self.rotation_angle else "회전 명령 시간 측정 중 · 놓으면 정지")
                        if isinstance(self.plan, LateralPlan):
                            self.result = describe_plan(self.plan) + " / 설정 시간 후 정지"
                    self.record = dict(mode=self.mode, direction=self.hold_direction or "w",
                                       sequence_step=self.sequence_index+1 if self.sequence_active else None,
                                       target_metres=self.plan.metres if self.sequence_active else None,
                                       target_angle=self.rotation_angle, planned_seconds=self.plan.duration if self.rotation_angle or self.sequence_active else None,
                                       started_at=datetime.now().astimezone().isoformat(),
                                       start_enc=self.counts, start_age=now-self.last_enc,
                                       command=cmd, seconds=None, reason="", stop_ack=False)
            if now - self.started >= self.plan.duration:
                raise DeadlineReached()
        return super().exchange(cmd, accept)

    def stop_plan(self, reason="작업자 정지", completed=False):
        if not completed:
            self.cancel_sequence(reason)
        was_active = self.active
        self.active = False
        if was_active:
            self.ended = self.clock()
        self.result = reason
        if was_active and self.record:
            self.record.update(seconds=self.ended-self.started, reason=reason)
        if self.link and self.control:
            # 원본 STOP의 감속 지연에 의존하지 않고 먼저 출력 0을 요청합니다.
            self.exchange("ESTOP", lambda s: s == "OK ESTOP")
            super().stop()
            if self.record:
                self.record["stop_ack"] = True

    def finish_record(self, complete):
        if not self.record:
            return
        row, self.record = self.record, None
        if row["seconds"] is None:
            row.update(seconds=max(0, self.clock()-self.started), reason=self.result)
        row.update(end_enc=self.counts, end_age=None if self.counts is None else self.clock()-self.last_enc,
                   complete=complete, ended_at=datetime.now().astimezone().isoformat())
        # 부호 있는 32비트 ENC의 rollover도 차분으로 처리합니다.
        row["delta"] = tuple((b-a+2**31) % 2**32-2**31 for a, b in zip(row["start_enc"], self.counts)) if complete and row["start_enc"] is not None and self.counts is not None else None
        self.records.append(row)

    def disconnect(self, message="연결 종료", fault=False):
        self.cancel_sequence(message)
        if self.active:
            self.ended = self.clock()
            if self.record:
                self.record.update(seconds=max(0, self.ended-self.started), reason=message)
        self.active = False
        self.result = message
        super().disconnect(message, fault)
        self.finish_record(False)

    def tick(self, keys, focused, timestamp):
        try:
            if self.sequence_active and (not focused or keys or self.clock()-timestamp > .30):
                self.stop_plan("창 이탈/키 입력/입력 갱신 중단")
            if self.active:
                held = {"hold:" + self.hold_direction} if self.hold_direction and not self.rotation_angle and not self.sequence_active else set()
                if not focused or keys != held:
                    self.stop_plan("창 이탈 또는 키 입력으로 중단 · 재시작은 수동")
                    if focused and not keys and held:
                        self.result = "버튼 해제 · 정지 요청 / ENC 종료값 확인 중"
                        if self.record:
                            self.record["reason"] = "버튼 해제"
                elif self.started is not None and self.clock() - self.started >= self.plan.duration:
                    self.stop_plan(self.deadline_reason(), completed=True)
            super().tick({self.hold_direction or "w"} if self.active else set(), focused, timestamp)
            if not self.active and self.state == "ready":
                self.finish_record(True)
            if self.active and self.control.state != "moving":
                self.stop_plan("구동 상태 진입 실패 · 다시 시작해 주세요.")
            if (self.sequence_active and not self.active and self.state == "ready"
                    and not self.record and not self.release_gate and self.control.released):
                self.advance_sequence(focused, timestamp)
        except DeadlineReached:
            self.stop_plan(self.deadline_reason(), completed=True)

    def snapshot(self):
        value = super().snapshot()
        elapsed = 0 if self.started is None else max(0, (self.ended if self.ended is not None else self.clock()) - self.started)
        duration = self.plan.duration if self.plan else 0
        value.update(timed_active=self.active, elapsed=elapsed,
                     remaining=max(0, duration-elapsed), duration=duration,
                     metres=self.plan.metres if self.plan else None, result=self.result,
                     hold_direction=self.hold_direction, records=tuple(dict(r) for r in self.records),
                     record_pending=self.record is not None, rotation_angle=self.rotation_angle,
                     sequence_active=self.sequence_active, sequence_note=self.sequence_note,
                     sequence_index=self.sequence_index, sequence_total=len(self.sequence))
        return value


class MainSession(TimedSession):
    """메인 UI 전용: 연결 종료 중에만 수동/시간 제어를 선택합니다."""
    def __init__(self, clock=time.monotonic):
        super().__init__(clock)
        self.control_mode = "manual"
        self.speed = 10

    def select_control(self, mode):
        if mode not in {"manual", "sequence"} or self.link is not None:
            raise ValueError("연결 종료 후 조작 방식을 선택해 주세요.")
        self.control_mode = mode
        self.speed = 20 if mode == "sequence" else 10
        self.release_gate = True

    def start_plan(self, plan, focused, timestamp):
        if self.control_mode != "sequence":
            raise ValueError("순서 주행 모드에서만 실행할 수 있습니다.")
        return super().start_plan(plan, focused, timestamp)

    def change_speed(self, delta, keys=()):
        if self.control_mode != "manual":
            raise ValueError("순서 주행은 20% 고정입니다.")
        return super().change_speed(delta, keys)

    def exchange(self, cmd, accept):
        if self.control_mode == "manual":
            return Session.exchange(self, cmd, accept)
        return super().exchange(cmd, accept)

    def set_manual_speed(self, value, keys=()):
        """UI 출력 선택을 기존 5% 변경 경로로 적용. 구동 명령은 만들지 않습니다."""
        if type(value) is not int or value not in range(5, 41, 5):
            raise ValueError("출력은 5~40% 사이의 5% 단위로 선택해 주세요.")
        if self.control_mode != "manual" or self.state not in {"ready", "disconnected"} or keys:
            raise ValueError("수동 모드에서 모든 주행 키를 놓고 정지한 뒤 출력을 적용해 주세요.")
        delta = 5 if value > self.speed else -5
        for _ in range(abs(value - self.speed) // 5):
            self.change_speed(delta)

    def tick(self, keys, focused, timestamp):
        if self.control_mode == "manual":
            return Session.tick(self, keys, focused, timestamp)
        return super().tick(keys, focused, timestamp)

    def snapshot(self):
        result = super().snapshot()
        result["control_mode"] = self.control_mode
        return result


class TimedWorker(Worker):
    """포트 한 개를 한 스레드에서 소유. 중단 요청이 대기 중 시작보다 우선합니다."""
    def __init__(self, preview_only=False, session_factory=TimedSession):
        super().__init__(preview_only)
        self.session = session_factory()
        self.status = self.session.snapshot()
        self.urgent = None

    def request(self, action, *args):
        if action in {"stop", "disconnect", "estop"}:
            with self.lock:
                priority = {None: 0, "stop": 1, "disconnect": 2, "estop": 3}
                if priority[action] > priority[self.urgent]:
                    self.urgent = action
        else:
            super().request(action, *args)

    def run(self):
        try:
            while not self.quit.is_set():
                try:
                    with self.lock:
                        urgent, self.urgent = self.urgent, None
                    if urgent:
                        while True:
                            try:
                                self.actions.get_nowait()
                            except queue.Empty:
                                break
                        if urgent == "stop":
                            self.session.stop_plan()
                        else:
                            self.session.disconnect("작업자 연결 종료 / 정지", fault=urgent == "estop")
                    else:
                        try:
                            action, args = self.actions.get_nowait()
                        except queue.Empty:
                            action, args = None, ()
                        if action == "connect":
                            if self.preview_only and args[0] != "preview":
                                raise ValueError("모의 전용 실행입니다.")
                            with self.lock:
                                self.status = dict(self.session.snapshot(), state="connecting")
                            self.session.connect(*args)
                        elif action == "start":
                            with self.lock:
                                keys, focused, stamp = self.input
                            if keys:
                                raise ValueError("모든 키를 놓은 뒤 시작해 주세요.")
                            self.session.start_plan(Plan(*args), focused, stamp)
                        elif action == "hold":
                            with self.lock:
                                keys, focused, stamp = self.input
                            # 대기열 처리 전에 놓았거나 창을 벗어나면 출발하지 않습니다.
                            if focused and keys == {"hold:" + args[0]} and self.session.clock()-stamp <= .30:
                                self.session.start_hold(args[0], focused, stamp)
                        elif action == "rotate":
                            with self.lock:
                                keys, focused, stamp = self.input
                            if keys:
                                raise ValueError("모든 키를 놓은 뒤 회전 버튼을 눌러 주세요.")
                            self.session.start_rotation(*args, focused, stamp)
                        elif action == "sequence":
                            with self.lock:
                                keys, focused, stamp = self.input
                            if keys:
                                raise ValueError("모든 키를 놓은 뒤 순서를 시작해 주세요.")
                            self.session.start_sequence(*args, focused, stamp)
                        elif action == "control_mode":
                            self.session.select_control(*args)
                        elif action == "speed":
                            with self.lock:
                                keys, _, _ = self.input
                            self.session.change_speed(args[0], keys)
                        elif action == "manual_speed":
                            with self.lock:
                                keys, _, _ = self.input
                            self.session.set_manual_speed(args[0], keys)
                    with self.lock:
                        keys, focused, stamp = self.input
                    self.session.tick(keys, focused, stamp)
                except Exception as exc:
                    self.session.fail(str(exc))
                with self.lock:
                    self.status = self.session.snapshot()
                self.quit.wait(0.025)
        finally:
            self.session.disconnect("시간 이동 UI 종료")


def export_rotation_records(records, path):
    """측정값은 명령 시간/ENC 원시값이며 실제 각도나 실물 정지가 아닙니다."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["모드", "방향", "시작시각", "종료기록시각", "명령시간초", "출력%", "명령", "종료사유", "정지ACK", "ENC종료확인", "시작ENC", "종료ENC", "변화량_M1앞왼_M2앞오_M3뒤왼_M4뒤오", "시작ENC나이초", "종료ENC나이초", "측정기준", "요청각도_실측아님", "설정시간초", "순서번호", "요청거리m_실측아님"]
    temp = path.with_suffix(".tmp")
    with temp.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.writer(stream)
        writer.writerow(fields)
        for row in records:
            writer.writerow(["모의" if row["mode"] == "preview" else "실차", {"a":"좌회전", "d":"우회전", "w":"직진", "z":"왼쪽 평행", "c":"오른쪽 평행"}[row["direction"]],
                             row["started_at"], row["ended_at"], f'{row["seconds"]:.3f}', 20, row["command"], row["reason"],
                             row["stop_ack"], row["complete"], row["start_enc"], row["end_enc"], row["delta"], row["start_age"], row["end_age"],
                             "명령 전송 시작~정지 요청 / ENC는 정지 대기 후 값 / 방향은 명령부호 / 실물 회전각·정지 미검증",
                             row.get("target_angle"), row.get("planned_seconds"), row.get("sequence_step"), row.get("target_metres")])
    temp.replace(path)
