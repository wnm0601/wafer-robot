"""Manual commissioning boundary: measurements never grant motor authority."""
from __future__ import annotations

import math
from .manual_first_drive import ManualFirstDrive


PHYSICAL_BLOCKERS = (
    "mega_manual 출력 firmware를 설정·빌드·업로드해야 합니다. 기본 mega_locked는 계속 잠깁니다.",
    "배터리 실제 전압·코일 전원 구성·전선/퓨즈와 전원 차단 시험이 필요합니다.",
    "A8 전원 피드백 회로·극성 및 E-Stop 이후 재무장 조건을 확인해야 합니다.",
    "현재 PCB 기준 M1~M4 위치·방향·encoder 부호와 x1 count/rev를 확인해야 합니다.",
    "실제 PWM 제한·저속 시험값과 담당자 준비 확인 후 별도 실차 시험이 필요합니다.",
)


def connect_physical_manual(port: str):
    """Never enumerate/open ports or turn a saved boolean into an output permit."""
    raise RuntimeError("실차 연결 잠금 · COM 포트는 열지 않았습니다.\n" + "\n".join(PHYSICAL_BLOCKERS))


class ManualControlSession:
    """Shared UI command layer; owns no plant, port opener or auto-driving logic.

    Simulation and manual_hardware inject their own gateway here. This layer
    opens no port and provides no automatic mission or independent motor permit.
    """
    def __init__(self, gateway, *, percent=10, mapping_verified=False, keyboard_hold=False):
        self.gateway = gateway
        self.drive = ManualFirstDrive(gateway, percent=percent,
                                     mapping_verified=mapping_verified, keyboard_hold=keyboard_hold)

    def tick(self):
        self.drive.step()
        status = self.gateway.exchange("STATUS")
        if self.drive.keyboard_hold and status[0] == '3' and not self.drive.latched:
            self.drive.abort(RuntimeError('펌웨어 오류: ' + status[1]))
        return status

    def close(self):
        self.drive.session_confirmed = False
        try:
            self.drive.stop()
        finally:
            self.gateway.close()


def compare_measurement(*, predicted, measured, unit, source, repeated_trials=1):
    """Compare matching signed yaw OR travelled path length, not endpoint distance."""
    if unit not in ("m", "deg"):
        raise ValueError("단위는 m 또는 deg입니다")
    if any(type(v) not in (float, int) or not math.isfinite(v)
           for v in (predicted, measured)):
        raise ValueError("유한한 실측 숫자를 입력해 주세요")
    if unit == "m" and (predicted < 0 or measured < 0):
        raise ValueError("이동 경로 길이는 0 이상이어야 합니다")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("측정 방법·시험 조건을 적어 주세요")
    if type(repeated_trials) is not int or repeated_trials < 1:
        raise ValueError("반복 횟수는 1 이상의 정수입니다")
    error = predicted - measured
    return {"unit": unit, "predicted": predicted, "measured": measured,
            "error_predicted_minus_measured": error,
            "relative_error_percent": error / abs(measured) * 100 if measured else None,
            "source": source.strip(), "repeated_trials": repeated_trials,
            "calibration_verified": False, "motor_authorization": False,
            "note": "수동 입력 비교 기록입니다. 교정 설정과 실제 출력 승인을 변경하지 않습니다."}
