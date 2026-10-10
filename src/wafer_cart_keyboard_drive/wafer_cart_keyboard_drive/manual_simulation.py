"""Firmware-backed manual simulation session, shared by GUI and headless tests."""
from __future__ import annotations

import json
import math
from pathlib import Path
import time

from .bench_gateway import BenchGateway
from .firmware_simulator import FirmwareSimulatorWire
from .simulation_plant import SimulationPlant, Pose
from .manual_commissioning import ManualControlSession


class ManualSimulation:
    def __init__(self, root: Path, *, load_saved=True):
        self.root = root
        self.booth = json.loads((root / "src/wafer_cart_mapping/config/booth_mock.json").read_text(encoding="utf-8-sig"))
        model = json.loads((root / "config/manual_simulation.json").read_text(encoding="utf-8-sig"))
        reference = json.loads((root / "src/wafer_cart_mapping/config/reference_measurements.json").read_text(encoding="utf-8-sig"))
        self.saved_path = root / "data/manual_simulation_ui.json"
        self.saved_error = None
        percent = 10
        if load_saved and self.saved_path.is_file():
            try:
                saved = json.loads(self.saved_path.read_text(encoding="utf-8"))
                for name in ("home", "destination"):
                    values = saved[name]
                    if len(values) != 3 or any(type(v) not in (int,float) or not math.isfinite(v) for v in values):
                        raise ValueError("invalid point")
                    self.booth[name] = values
                percent = saved["percent"]
                if type(percent) is not int or not 1 <= percent <= 30:
                    raise ValueError("invalid speed")
            except (ValueError, KeyError) as error:
                self.saved_error = str(error)
                # Do not overwrite an invalid saved file or silently move from a bogus pose.
                raise ValueError("저장된 모의 설정을 확인해 주세요: " + str(error)) from error
        self.wire = FirmwareSimulatorWire(root)
        self.gateway = BenchGateway(self.wire, timeout=0.35)
        try:
            self.wire.power_feedback(False)
            self.gateway.connect(limit_percent=percent)
            self.wire.power_feedback(True)
            self.gateway.exchange("STATUS")
            self.controls = ManualControlSession(self.gateway, percent=percent, mapping_verified=True)
            self.drive = self.controls.drive
            self.drive.select_mode("vector")
            self.plant = SimulationPlant(model, self.booth, reference["cad"]["mock_footprint_m"],
                                         duty_scale=self.wire.duty_scale)
            for name in ("home", "destination"):
                if self.plant.collision_at(Pose(*self.booth[name])):
                    raise ValueError("저장된 지점이 벽·테이블·지도 경계와 겹칩니다")
        except Exception:
            self.gateway.close()
            raise
        self.last_time = time.monotonic()
        self.device_status = None
        self.last_command = None
        self.collision_stop = False

    def tick(self):
        now = time.monotonic()
        dt, self.last_time = now-self.last_time, now
        # Motion arises only from the C++ Controller's current ramped outputs.
        status = self.gateway.exchange("STATUS")
        self.device_status = status
        outputs = [int(v) for v in status[5:]]
        moved = self.plant.advance(outputs, dt)
        self.wire.encoder_feedback(self.plant.counts)
        if not moved:
            self.drive.stop()
            self.collision_stop = True
        else:
            self.drive.step()
            if self.drive.last_command:
                self.last_command = self.drive.last_command
        return moved

    def is_stopped(self):
        status = self.gateway.exchange("STATUS")
        return (not self.drive.moving and not self.drive.prepared and not self.drive.keys
                and not any(int(v) for v in status[5:]))

    def save(self):
        self.saved_path.parent.mkdir(parents=True, exist_ok=True)
        self.saved_path.write_text(json.dumps({"simulation_only": True,
            "home": self.booth["home"], "destination": self.booth["destination"],
            "percent": self.drive.percent}, ensure_ascii=False, indent=2), encoding="utf-8")

    def set_point(self, name, x, y):
        if name not in ("home", "destination") or not self.is_stopped():
            raise ValueError("완전히 정지한 뒤 지점을 변경해 주세요")
        candidate = Pose(float(x), float(y), 0.0)
        if not math.isfinite(candidate.x) or not math.isfinite(candidate.y):
            raise ValueError("지점 좌표는 유한한 숫자여야 합니다")
        if self.plant.collision_at(candidate):
            raise ValueError("대차 외곽이 벽·테이블·지도 경계와 겹칩니다")
        self.booth[name] = [candidate.x, candidate.y, candidate.yaw]
        if name == "home":
            self.plant.reset()
        self.save()

    def set_speed(self, percent):
        if not self.is_stopped():
            raise ValueError("완전히 정지한 뒤 속도를 변경해 주세요")
        self.drive.set_percent(percent)
        self.save()

    def reset_pose(self):
        if not self.is_stopped():
            raise ValueError("완전히 정지한 뒤 위치를 초기화해 주세요")
        self.plant.reset()
        self.collision_stop = False

    def snapshot(self):
        p = self.plant.pose
        return {"source": "firmware/cart_controller.cpp", "source_sha256": self.wire.source_sha256,
                "motor_enabled": False, "calibration_verified": False,
                "pose": {"x_m": p.x, "y_m": p.y, "yaw_rad": p.yaw},
                "outputs": self.plant.outputs, "encoder_counts": self.plant.counts,
                "collision": self.plant.collision, "distance_m": self.plant.distance,
                "armed": self.gateway.armed}

    def close(self):
        self.gateway.close()
