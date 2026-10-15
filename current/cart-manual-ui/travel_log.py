"""제어권 없는 UI 관찰 기록기. serial/모터 모듈을 import하지 않습니다."""
from __future__ import annotations

import csv
from collections import deque
from datetime import datetime
from pathlib import Path
import time


FIELDS = ("종류", "모드", "시작시각", "종료시각", "경과초", "명령비율", "명령",
          "종료사유", "사용자확인거리m", "참고평균m_s", "측정기준", "평행방향", "사용자확인초_m", "주행방향")
MODE = {"preview": "모의", "real": "실차"}
LATERAL = {"z": "왼쪽", "c": "오른쪽"}
MOTIONS = {"w": "직진", "s": "후진", "a": "좌회전", "d": "우회전",
           "z": "왼쪽 평행", "c": "오른쪽 평행"}


def motion_direction(command, speed):
    if speed <= 0:
        return None
    vectors = {"w": (1, 0, 0), "s": (-1, 0, 0), "a": (0, 0, -1),
               "d": (0, 0, 1), "z": (0, -1, 0), "c": (0, 1, 0)}
    return next((key for key, vector in vectors.items()
                 if command == "V " + " ".join(str(v * speed) for v in vector)), None)


def lateral_direction(command, speed):
    return next((key for key, sign in (("z", -1), ("c", 1))
                 if command == f"V 0 {sign * speed} 0"), None)


class TravelLog:
    """25ms UI 관찰 시점을 기록하며 실물 이동/정지를 판정하지 않습니다."""
    def __init__(self, clock=time.monotonic, wall=None):
        self.clock = clock
        self.wall = wall or (lambda: datetime.now().astimezone().isoformat(timespec="milliseconds"))
        self.rows = deque(maxlen=500)
        self.active = None
        self.armed = False
        self.trial = None
        self.note = "자동 기록 대기 · 실물 이동/정지 시점이 아닙니다."
        self.count = 0
        self.saved_count = 0
        self.lateral_last = {}
        self.lateral_candidates = {}
        self.lateral_calibration = {}
        self.motion_last = {}

    def can_confirm_lateral(self, direction, status):
        row = self.lateral_candidates.get(direction)
        return bool(row and status["state"] == "ready" and status["mode"] == "real"
                    and status["speed"] == 20 and status.get("control_mode", "manual") == "manual"
                    and row["모드"] == "실차" and row["명령비율"] == 20
                    and float(row["경과초"]) > 0)

    def confirm_lateral(self, direction, status):
        """정지 후 사용자가 실제 1m를 확인한 경우만 기록. 제어/자동 보정 없음."""
        self.observe(status)
        if not self.can_confirm_lateral(direction, status):
            self.note = "확인 불가: 실차 20% 평행이동 후 입력 대기 상태에서 실제 1m를 확인해 주세요."
            return False
        row = dict(self.lateral_candidates.pop(direction))
        row.update(종류="평행 1m 수동 확인", 사용자확인거리m=1.0,
                   참고평균m_s=f'{1 / float(row["경과초"]):.3f}',
                   사용자확인초_m=row["경과초"], 종료사유="정지 후 사용자 1m 확인 · 자동 보정 아님")
        self.rows.append(row)
        self.count += 1
        self.lateral_calibration[direction] = row
        self.note = f'{LATERAL[direction]} 20% · 사용자 확인 1m = {row["경과초"]}초 · 연결 종료 후 CSV 저장'
        return True

    def arm(self, status):
        if status["state"] != "ready":
            self.note = "입력 대기 상태에서 F8을 눌러 주세요."
            return False
        self.armed = True
        self.trial = None
        self.note = "1m 대기 · 출발선에 맞춘 뒤 W 전진, 도착 순간 F9 (정지 아님)"
        return True

    def cancel(self):
        self.armed = False
        self.trial = None
        self.note = "1m 기록 취소 · 구동에는 영향을 주지 않습니다."

    def observe(self, status):
        now = self.clock()
        moving = status["state"] == "moving" and bool(status.get("motion"))
        identity = (status["mode"], status["speed"], status.get("last_motion"))
        if self.active and (not moving or self.active["identity"] != identity):
            self.finish("명령 변경" if moving else status["state"], now)
        if moving and self.active is None:
            # 다음 움직임이 시작되면 이전 구간의 확인 대상을 폐기합니다.
            self.lateral_candidates.clear()
            self.active = {"identity": identity, "start": now, "wall": self.wall()}
            if self.armed:
                self.armed = False
                if status.get("last_motion") == f'V {status["speed"]} 0 0':
                    self.trial = self.active
                    self.note = "1m 측정 중 · 도착 순간 F9 (기록만, 정지 아님)"
                else:
                    self.note = "1m 시험 취소: W 전진 명령이 아닙니다."
        if self.armed and status["state"] != "ready":
            self.armed = False
            self.note = "1m 대기 취소: 정지/연결 상태가 변경되었습니다."
        if status["state"] in {"fault", "disconnected", "connecting"}:
            self.lateral_candidates.clear()

    def append(self, active, end, kind, reason, distance=""):
        seconds = max(0.0, end - active["start"])
        mode, speed, command = active["identity"]
        # 모의 데이터는 실제 거리나 속도로 저장하지 않습니다.
        distance = distance if mode == "real" else ""
        row = dict(zip(FIELDS, (
            kind, MODE.get(mode, mode), active["wall"], self.wall(), f"{seconds:.3f}",
            speed, command, reason, distance,
            f"{float(distance)/seconds:.3f}" if distance and seconds > 0 else "",
            "UI 명령상태 관찰시점 / 통신·가속·사용자 반응 지연 포함 / 실측 속도 보증 아님",
            LATERAL.get(lateral_direction(command, speed), ""), "",
            MOTIONS.get(motion_direction(command, speed), "미분류"))))
        self.rows.append(row)
        self.count += 1
        return row

    def finish(self, reason, now=None):
        if self.active is None:
            return
        row = self.append(self.active, self.clock() if now is None else now, "명령 구간", reason)
        motion = motion_direction(row["명령"], row["명령비율"])
        if motion:
            self.motion_last[motion] = row
        direction = lateral_direction(row["명령"], row["명령비율"])
        if direction:
            self.lateral_last[direction] = row
            if reason in {"stopping", "ready"}:
                self.lateral_candidates[direction] = row
        if self.trial is not None:
            self.note = "1m 미완료: 도착 기록 전에 명령 중단 · 거리/속도를 계산하지 않습니다."
        self.active = self.trial = None

    def arrive(self, status):
        self.observe(status)
        if self.trial is None:
            self.note = "진행 중인 1m 시험이 없습니다. 정지 후 F8 → W → F9 순서입니다."
            return False
        elapsed = self.clock() - self.trial["start"]
        if elapsed <= 0:
            return False
        real = self.trial["identity"][0] == "real"
        self.append(self.trial, self.clock(), "1m 수동 도착" if real else "도착 기록 연습",
                    "사용자 F9 · 구동 계속 가능", 1.0)
        self.note = (f"1m 수동 확인 {elapsed:.2f}초 · 참고 평균 {1/elapsed:.3f}m/s" if real else
                     f"모의 도착 {elapsed:.2f}초 · 실제 1m/속도 아님") + " · 정지 아님!"
        self.trial = None
        return True

    def elapsed(self):
        return max(0.0, self.clock() - self.active["start"]) if self.active else 0.0

    def export(self, directory):
        if not self.rows:
            raise ValueError("저장할 완료 기록이 없습니다.")
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"travel_{datetime.now():%Y%m%d_%H%M%S}_{time.time_ns()}.csv"
        with path.open("x", newline="", encoding="utf-8-sig") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(self.rows)
        self.saved_count = self.count
        return path
