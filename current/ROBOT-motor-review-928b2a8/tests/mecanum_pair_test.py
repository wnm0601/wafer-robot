"""두 모터: 1~6 짝 선택, 위/아래 방향키를 누르는 동안만 구동.

--port 필수, --speed 5~40 (기본 10). Space 정지, X/E/Esc/Q 종료.
M1 앞왼 / M2 앞오 / M3 뒤왼 / M4 뒤오: 공유 브랜치 기준, 라이다 쪽이 뒤.
안전 조건과 검증 한계는 docs/MOTOR_REVIEW_20261012.md를 먼저 확인하십시오.
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common.manual_motor_test import run


if __name__ == "__main__":
    raise SystemExit(run("pair"))
