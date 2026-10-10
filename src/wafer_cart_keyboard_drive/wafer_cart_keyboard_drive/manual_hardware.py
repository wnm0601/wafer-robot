"""Explicit operator-only serial session; no simulator motion in real mode."""
from __future__ import annotations

import json
from pathlib import Path
import re
import time

from .bench_gateway import BenchGateway, SerialStreamWire
from .manual_commissioning import ManualControlSession
from .simulation_plant import SimulationPlant


def open_manual_serial(port, *, operator_confirmed=False, serial_factory=None):
    if operator_confirmed is not True:
        raise ValueError('담당자 준비·출력용 firmware·전원 차단 조건을 먼저 확인해 주세요')
    if not isinstance(port,str) or not re.fullmatch(r'COM[1-9][0-9]*',port,re.IGNORECASE):
        raise ValueError('명시적인 Windows COM 번호를 입력해 주세요')
    if serial_factory is None:
        import serial
        serial_factory=serial.Serial
    # Opening a Mega can reset it via DTR. Never auto-reconnect or resume motion.
    stream=serial_factory(port=port.upper(),baudrate=115200,timeout=0.02,write_timeout=0.1)
    try:
        time.sleep(2.5)  # MCU boot only; no motion commands during boot.
        return SerialStreamWire(stream)
    except Exception:
        stream.close()
        raise


class ManualHardware:
    is_physical=True

    def __init__(self, root:Path, *, wire, percent=1, mapping_verified=False,
                 no_power_feedback=False, keyboard_hold=False):
        self.root=root
        self.fixture=getattr(wire,'simulation_fixture',False)
        self.booth=json.loads((root/'src/wafer_cart_mapping/config/booth_mock.json').read_text(encoding='utf-8-sig'))
        model=json.loads((root/'config/manual_simulation.json').read_text(encoding='utf-8-sig'))
        reference=json.loads((root/'src/wafer_cart_mapping/config/reference_measurements.json').read_text(encoding='utf-8-sig'))
        # Layout-only object: NEVER advance/integrate it from real output or key time.
        self.plant=SimulationPlant(model,self.booth,reference['cad']['mock_footprint_m'],duty_scale=200)
        mode = 'MANUAL_UNMONITORED' if no_power_feedback else 'MANUAL_ONLY'
        self.gateway=BenchGateway(wire,timeout=.35,expected_mode=mode)
        try:
            self.gateway.connect(limit_percent=percent)
            self.gateway.exchange('INFO')
            self.controls=ManualControlSession(self.gateway,percent=percent,mapping_verified=mapping_verified,
                                               keyboard_hold=keyboard_hold)
            self.drive=self.controls.drive
        except Exception:
            self.gateway.close()
            raise
        self.last_command=None
        self.collision_stop=False
        self.device_status=None
        self.last_encoder=None

    def tick(self):
        self.device_status=self.controls.tick()
        self.last_command=self.drive.last_command or self.last_command
        self.last_encoder=self.gateway.encoder_snapshot()
        self.plant.outputs=list(map(int,self.device_status[5:]))
        self.plant.counts=self.last_encoder['counts_m1_m4']
        return True

    def is_stopped(self):
        status=self.gateway.exchange('STATUS')
        return not (self.drive.prepared or self.drive.keys or self.drive.moving or any(map(int,status[5:])))

    def set_speed(self,percent):
        if not self.is_stopped():raise ValueError('완전히 정지한 뒤 변경하세요')
        self.drive.set_percent(percent)

    def set_point(self,*_):raise ValueError('실차 지도 좌표는 localization 연결 후 설정합니다')
    def reset_pose(self):raise ValueError('실차 위치는 가상 위치로 초기화하지 않습니다')
    def snapshot(self):
        return {'source':('PC ' if self.fixture else 'Arduino ') + self.gateway.expected_mode,
                'motor_enabled':not self.fixture,'pose':None,
                'encoder':self.last_encoder,'status':self.device_status,'armed':self.gateway.armed,
                'keyboard_hold':self.drive.keyboard_hold,'session_confirmed':self.drive.session_confirmed,
                'first_error':self.drive.first_error,
                'calibration_verified':False}
    def close(self):self.controls.close()
