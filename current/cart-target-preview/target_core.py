"""화면 전용 표적 검출. 장치 제어·거리 추정·모터 명령은 포함하지 않습니다."""
from dataclasses import dataclass
import importlib.util
import math
from pathlib import Path

import cv2
import numpy as np

COLOR_SOURCE = Path(__file__).resolve().parent.parent / "ROBOT-motor-review-928b2a8/common/color.py"
_spec = importlib.util.spec_from_file_location("original_pure_color", COLOR_SOURCE)
_color = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_color)


@dataclass(frozen=True)
class Detection:
    box: tuple
    label: str
    score: float = 1.0

    @property
    def center(self):
        x1, y1, x2, y2 = self.box
        return ((x1 + x2) / 2, (y1 + y2) / 2)


def pick_color(frame, x, y):
    h, w = frame.shape[:2]
    if not (0 <= x < w and 0 <= y < h):
        return None
    patch = frame[max(0, y-4):min(h, y+5), max(0, x-4):min(w, x+5)]
    name, _ = _color.dominant_color(patch)
    return name if name in _color.HSV_RANGES else None


def detect_color(frame, name):
    mask = _color.color_mask(frame, name)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    h, w = frame.shape[:2]
    result = []
    for contour in contours:
        if cv2.contourArea(contour) < max(50, h*w*0.001):
            continue
        x, y, bw, bh = cv2.boundingRect(contour)
        # 화면 밖으로 잘린 표적은 중심 오차를 신뢰할 수 없습니다.
        if x <= 1 or y <= 1 or x+bw >= w-1 or y+bh >= h-1:
            continue
        result.append(Detection((x, y, x+bw, y+bh), name))
    return result


def pick_detection(detections, x, y):
    matches = [d for d in detections if d.box[0] <= x <= d.box[2] and d.box[1] <= y <= d.box[3]]
    return matches[0] if len(matches) == 1 else None


class Alignment:
    """새 프레임에서만 수평 오차 판정. 중복·오래된 결과는 완료로 누적하지 않습니다."""
    def __init__(self):
        self.reset()

    def reset(self):
        self.since = None
        self.last_seq = None
        self.last_stamp = None

    def update(self, detections, selected, width, height, seq, stamp, now,
               tolerance=8, target_x=0.5, frozen=False):
        invalid = not all(math.isfinite(v) for v in (stamp, now, tolerance, target_x))
        if invalid or width <= 0 or height <= 0 or tolerance < 0 or not 0 <= target_x <= 1:
            self.reset()
            return "INVALID", None
        if now-stamp > 0.5 or now < stamp:
            self.reset()
            return "STALE", None
        if frozen:
            self.reset()
            return "FROZEN", None
        if selected is None:
            self.reset()
            return "SELECT", None
        candidates = [d for d in detections if d.label == selected]
        if len(candidates) != 1:
            self.reset()
            return ("AMBIGUOUS" if candidates else "LOST"), None
        detection = candidates[0]
        x1, y1, x2, y2 = detection.box
        if not (0 < x1 < x2 < width and 0 < y1 < y2 < height):
            self.reset()
            return "LOST", None
        cx, cy = detection.center
        error = (cx-target_x*width, cy-height/2)
        if seq == self.last_seq:
            return "WAIT", error
        if self.last_stamp is not None and (stamp-self.last_stamp > 0.3 or stamp <= self.last_stamp):
            self.since = None
        self.last_seq, self.last_stamp = seq, stamp
        if abs(error[0]) > tolerance:
            self.since = None
            return ("RIGHT" if error[0] > 0 else "LEFT"), error
        if self.since is None:
            self.since = stamp
        return ("CENTERED" if stamp-self.since >= 0.5 else "SETTLING"), error


def left_camera_guidance(detections, selected, width, height, stamp, now,
                         tolerance=8, frozen=False, confirmed=False, mirrored=False):
    """직립·좌측 바깥 방향 카메라의 화면 중앙 기준 안내만 계산합니다.

    정상 영상의 오른쪽은 차체 전방입니다. 미러 옵션은 입력 영상이 이미
    반전됐음을 뜻하며 픽셀을 다시 뒤집지 않습니다. 거리/회전은 추정하지 않습니다.
    """
    code, delta = Alignment().update(detections, selected, width, height, 1,
                                     stamp, now, tolerance, .5, frozen)
    if delta is None:
        return "표적 위치 —", "이동 안내 중지 · 유효한 표적 1개를 선택해 주세요"
    dx, dy = delta
    horizontal = "수평 중앙" if abs(dx) <= tolerance else ("오른쪽" if dx > 0 else "왼쪽")
    vertical = "세로 중앙" if abs(dy) <= tolerance else ("아래" if dy > 0 else "위")
    position = f"화면 중앙 기준: {horizontal} / {vertical} · X {dx:+.1f}px · Y {dy:+.1f}px"
    if not confirmed:
        return position, "이동 안내 보류 · 좌측 장착 방향과 영상 반전 여부를 확인해 주세요"
    if abs(dx) <= tolerance:
        return position, "전후 보정 불필요(수평 허용 범위) · 거리·각도·주차 완료 판정 아님"
    physical_dx = -dx if mirrored else dx
    action = "전진 ↑" if physical_dx > 0 else "후진 ↓"
    return position, f"대차 {action} 방향으로 수평 중앙 보정 · 안내만 / 자동 구동 없음"


def demo_frame(x=150):
    frame = np.full((480, 640, 3), 38, np.uint8)
    cv2.rectangle(frame, (x-35, 205), (x+35, 275), (0, 0, 230), -1)
    return frame
