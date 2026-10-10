"""Manual map simulator. The GUI runs the real firmware Controller on the PC."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/wafer_cart_keyboard_drive"))


def smoke() -> int:
    # Legacy protocol fixture remains available without requiring WSL/g++.
    from wafer_cart_keyboard_drive.bench_gateway import BenchGateway
    from wafer_cart_keyboard_drive.bench_mock import MockWire
    from wafer_cart_keyboard_drive.manual_first_drive import ManualFirstDrive
    wire = MockWire(mapping_verified=True, simulate_encoder=True)
    gateway = BenchGateway(wire)
    try:
        gateway.connect(limit_percent=10)
        wire.power_feedback(True)
        drive = ManualFirstDrive(gateway, mapping_verified=True)
        drive.prepare()
        drive.set_keys({'up'})
        drive.step()
        single = drive.last_command
        drive.set_keys(set())
        drive.step()
        drive.select_mode('vector')
        time.sleep(0.2)
        drive.prepare()
        drive.set_keys({'w'})
        drive.step()
        vector = drive.last_command
        drive.set_keys(set())
        drive.step()
        assert single == ('M',1,10) and vector == ('V',10,0,0) and not gateway.armed
        print(json.dumps({'result':'MANUAL_MOCK_PASS','backend':'Python fixture only',
                          'single':single,'vector':vector,'motor_enabled':False}))
        return 0
    finally:
        gateway.close()


def sim_smoke() -> int:
    from wafer_cart_keyboard_drive.manual_simulation import ManualSimulation
    sim = ManualSimulation(ROOT,load_saved=False)
    checks = []
    def hold(key, duration=1.2):
        sim.drive.prepare()
        sim.drive.set_keys({key})
        end=time.monotonic()+duration
        while time.monotonic()<end:
            sim.tick()
            time.sleep(0.02)
        sim.drive.set_keys(set())
        sim.drive.step()
        end=time.monotonic()+0.4
        while time.monotonic()<end:
            sim.tick()
            time.sleep(0.02)
        assert sim.is_stopped(), 'release did not stop firmware outputs'
    try:
        sim.drive.set_keys({'w'})
        sim.tick()
        assert sim.plant.distance==0
        sim.drive.set_keys(set())
        checks.append('no motion before manual prepare')
        initial=sim.plant.pose.x
        hold('w')
        assert sim.plant.pose.x>initial+0.03
        assert all(v>0 for v in sim.plant.counts)
        assert sim.gateway.encoder_snapshot()['counts_m1_m4']==sim.plant.counts
        checks.append('forward from C++ outputs with encoder feedback')
        x=sim.plant.pose.x
        hold('s')
        assert sim.plant.pose.x<x-0.03
        checks.append('reverse')
        y=sim.plant.pose.y
        hold('a')
        assert sim.plant.pose.y>y+0.03
        checks.append('left-positive C2 axis conversion')
        yaw=sim.plant.pose.yaw
        hold('e')
        assert sim.plant.pose.yaw<yaw-0.03
        checks.append('rotation')
        sim.drive.select_mode('single')
        for motor in range(1,5):
            sim.drive.select_motor(motor)
            before=list(sim.plant.counts)
            hold('up',0.8)
            assert sim.plant.counts[motor-1]>before[motor-1]
            assert all(sim.plant.counts[i]==before[i] for i in range(4) if i!=motor-1)
        checks.append('M1..M4 only selected wheel moves')
        pose=sim.snapshot()['pose']
        sim.drive.set_keys({'up'})
        for _ in range(5):sim.tick();time.sleep(0.02)
        assert sim.snapshot()['pose']==pose
        sim.drive.set_keys(set())
        checks.append('release requires manual reprepare')
        from wafer_cart_keyboard_drive.simulation_plant import Pose
        sim.drive.select_mode('vector')
        sim.plant.pose=Pose(.8,.9,3.141592653589793/2)
        hold('w')
        assert sim.collision_stop and sim.plant.collision=='테이블'
        assert sim.plant.collision_at(sim.plant.pose) is None
        checks.append('table collision stops C++ command path')
        sim.reset_pose()
        sim.drive.prepare()
        sim.drive.set_keys({'w'})
        sim.drive.step()
        time.sleep(.65)
        timed_out=sim.gateway.exchange('STATUS')
        assert timed_out[1]=='COMMAND_TIMEOUT' and not any(map(int,timed_out[5:]))
        checks.append('real-time firmware lease stops absent commands')
        sim.drive.estop()
        try:sim.drive.prepare()
        except ValueError:checks.append('ESTOP latched')
        else:raise AssertionError('ESTOP rearmed')
        report={'result':'FIRMWARE_SIM_PASS','checks':checks,'snapshot':sim.snapshot()}
        path=ROOT/'data/output/manual_simulator_current.json'
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False))
        return 0
    finally:
        sim.close()


MOTOR_LOCATIONS = {1:'왼쪽 뒤 추정',2:'오른쪽 뒤 추정',3:'왼쪽 앞 추정',4:'오른쪽 앞 추정'}


def terminal_step(backend, keys, previous, *, focused=True):
    """Same drive policy without Tk; input is injectable for no-device tests."""
    pressed = keys - previous
    if 'esc' in keys or 'x' in keys:
        backend.drive.estop()
        return False
    if not focused:
        backend.drive.set_keys(set(), focused=False)
    elif 'space' in keys:
        backend.drive.stop()
    else:
        for motor in range(1,5):
            if str(motor) in pressed:
                backend.drive.stop()
                backend.drive.select_motor(motor)
        for key,delta in (('+',5),('-',-5)):
            if key in pressed:
                backend.drive.stop()
                backend.set_speed(max(1,min(40,backend.drive.percent+delta)))
        backend.drive.set_keys(keys & {'up','down'}, focused=True)
    backend.tick()
    return True


def terminal_session(backend, *, diagnostics=False):
    import ctypes
    if sys.platform != 'win32':
        raise RuntimeError('실제 키 홀드 터미널은 Windows에서 실행해 주세요')
    user32=ctypes.WinDLL('user32',use_last_error=True)
    user32.GetForegroundWindow.restype=ctypes.c_void_p
    user32.GetAsyncKeyState.argtypes=[ctypes.c_int]
    user32.GetAsyncKeyState.restype=ctypes.c_short
    foreground=user32.GetForegroundWindow()
    if not foreground:raise RuntimeError('터미널 포커스를 확인하지 못했습니다')
    codes={'up':0x26,'down':0x28,'space':0x20,'x':0x58,'esc':0x1b,
           '1':0x31,'2':0x32,'3':0x33,'4':0x34,'+':0xbb,'-':0xbd}
    path=ROOT/'data/output'/('manual_terminal_'+time.strftime('%Y%m%d_%H%M%S')+'.jsonl')
    path.parent.mkdir(parents=True,exist_ok=True)
    print('터미널 수동: ↑/↓ 홀드·해제 정지 / 1~4 모터 / +/- 출력5씩 / Space 정지 / X·Esc 비상정지 종료')
    print('모터 위치는 추정입니다: '+str(MOTOR_LOCATIONS))
    print('현재 터미널 창의 포커스를 유지하세요. 전환 시 정지합니다. 처음에는 모든 키를 놓으세요.')
    print('기록: '+str(path),flush=True)
    previous=set(); released=False; last_print=0; last_start=None
    with path.open('x',encoding='utf-8') as log:
        try:
            while True:
                started=time.monotonic()
                focused=user32.GetForegroundWindow()==foreground
                keys={k for k,v in codes.items() if user32.GetAsyncKeyState(v)&0x8000}
                if not released:
                    released=not keys
                    keys=set()
                # A delayed input loop must stop, not silently renew a stale hold.
                if last_start is not None and started-last_start>=.4:
                    backend.drive.stop()
                    raise RuntimeError('터미널 루프 지연400ms 이상: 시험 중단')
                alive=terminal_step(backend,keys,previous,focused=focused)
                record={'monotonic_s':started,'keys':sorted(keys),'focused':focused,
                        'motor':backend.drive.motor,'percent':backend.drive.percent,
                        'command':backend.drive.last_command,'status':backend.device_status,
                        'encoder':backend.last_encoder,'cycle_ms':(time.monotonic()-started)*1000}
                log.write(json.dumps(record,ensure_ascii=False)+'\n');log.flush()
                if started-last_print>=1:
                    print(f"M{backend.drive.motor}({MOTOR_LOCATIONS[backend.drive.motor]}) {backend.drive.percent}% | {backend.device_status}",flush=True)
                    last_print=started
                if not alive:break
                previous=keys;last_start=started
                time.sleep(.025)
        except Exception as error:
            details = None
            if diagnostics:
                try:
                    backend.drive.stop()
                    details = backend.gateway.diagnostic_snapshot()
                except Exception as diagnostic_error:
                    details = {'unavailable': str(diagnostic_error)}
            log.write(json.dumps({'error':str(error),'first_error':backend.drive.first_error,
                                  'gateway_fault':backend.gateway.fault,
                                  'gateway_first_fault':backend.gateway.first_fault,
                                  'diagnostics':details,'trace':list(backend.gateway.trace)},ensure_ascii=False)+'\n')
            if details is not None: print('진단: '+json.dumps(details,ensure_ascii=False),flush=True)
            print('중단: '+str(error)+' | 모터 전원을 OFF로 해 주세요.',flush=True)
            raise
        finally:
            backend.close()
    return 0


def terminal_smoke():
    from wafer_cart_keyboard_drive.firmware_simulator import FirmwareSimulatorWire
    from wafer_cart_keyboard_drive.manual_hardware import ManualHardware
    wire=FirmwareSimulatorWire(ROOT,unmonitored=True)
    backend=ManualHardware(ROOT,wire=wire,percent=20,no_power_feedback=True,keyboard_hold=True)
    try:
        backend.drive.enable_keyboard_hold(operator_confirmed=True)
        terminal_step(backend,set(),set())
        assert not backend.gateway.armed
        terminal_step(backend,{'up'},set())
        assert backend.drive.last_command==('M',1,20)
        terminal_step(backend,{'space','up'},{'up'})
        assert not backend.gateway.armed
        terminal_step(backend,{'up'},{'space','up'})
        assert not backend.gateway.armed
        for _ in range(8):terminal_step(backend,set(),set());time.sleep(.025)
        terminal_step(backend,{'3'},set())
        assert backend.drive.motor==3
        terminal_step(backend,{'up'},{'3'})
        assert backend.drive.last_command==('M',3,20)
        terminal_step(backend,{'up'},{'up'},focused=False)
        assert not backend.gateway.armed
        assert terminal_step(backend,{'x'},set()) is False
        assert backend.drive.latched
        details=backend.gateway.diagnostic_snapshot()
        assert details['first_firmware_fault']=='OPERATOR_ESTOP'
        assert details['output']['available'] is False  # Controller-only PC fixture has no AVR registers.
        assert details['source']=='PC fixture'
        print('TERMINAL_POLICY_PASS: startup, hold, Space/release gate, motor selection, focus STOP, ESTOP, DIAG/IO unavailable correctly labelled; NO DEVICE/GUI')
        return 0
    finally:backend.close()


def real_session(args) -> int:
    from wafer_cart_keyboard_drive.manual_hardware import ManualHardware, open_manual_serial
    if not args.port or not args.no_power_feedback:
        raise ValueError('실차 시험은 --port COM번호 --no-power-feedback를 명시해 주세요')
    if args.smoke or args.sim_smoke or args.ui_test or args.hardware_ui_test:
        raise ValueError('실차와 모의시험 인자는 함께 사용할 수 없습니다')
    print('실제 모터 출력 가능 / 최초 안전 확인 후 키 홀드 / 시작 출력 1% / 4륜 매핑 미검증으로 잠금')
    print('A8 없음: 전원·물리 급정지 미감지. 전원 복구 전 키 해제 및 창 종료, 복구 후 재연결.')
    if not args.inspect_real:
        expected = 'CONNECT ' + args.port.upper()
        if input(f'받침대·물리 비상정지·주변·담당자 확인 후 {expected} 입력: ').strip() != expected:
            print('연결 취소: 포트를 열지 않았습니다')
            return 1
    backend = None
    wire = open_manual_serial(args.port, operator_confirmed=True)
    try:
        backend = ManualHardware(ROOT, wire=wire, percent=1, mapping_verified=False, no_power_feedback=True,
                                 keyboard_hold=not args.inspect_real)
        details = backend.gateway.diagnostic_snapshot() if args.diagnostics else None
        if args.inspect_real:
            status = backend.gateway.exchange('STATUS')
            assert status[2:4] == ['0', '0'] and not any(map(int, status[5:])), 'not safely idle'
            print(json.dumps({'identity':backend.gateway.exchange('INFO'), 'status':status,
                  'diagnostics':details,
                  'encoder':backend.gateway.encoder_snapshot(), 'motion_commands_sent':False},ensure_ascii=False))
            return 0
        if args.diagnostics:
            print('시작 전 진단: '+json.dumps(details,ensure_ascii=False),flush=True)
            output=details['output']
            if (not output.get('available') or not output.get('register_check_passed')
                    or output['registers']['enabled'] != 1):
                raise RuntimeError('출력 레지스터 점검 미통과: 수동 조작을 시작하지 않습니다')
        backend.drive.enable_keyboard_hold(operator_confirmed=True)
        if args.terminal:
            backend.set_speed(args.percent)
            return terminal_session(backend, diagnostics=args.diagnostics)
        from wafer_cart_keyboard_drive.manual_simulator_ui import SimulatorWindow
        return SimulatorWindow(ROOT, real_backend=backend).mainloop()
    finally:
        if backend is not None: backend.close()
        else: wire.close()


def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--smoke',action='store_true',help='기존 Python 프로토콜 fixture 시험')
    parser.add_argument('--sim-smoke',action='store_true',help='실제 C++ 펌웨어 + 가상 플랜트 시험')
    parser.add_argument('--ui-test',action='store_true',help='실제 Tk 이벤트 1.6초 홀드·해제 시험 후 종료')
    parser.add_argument('--hardware-ui-test',action='store_true',help='PC의 MANUAL_ONLY 통신 backend로 Tk 수동 제어 시험; 실제 COM 없음')
    parser.add_argument('--port',help='--real에서만 명시적인 실제 COM 포트')
    parser.add_argument('--real',action='store_true',help='실제 Arduino 수동시험 (자동 ARM 없음)')
    parser.add_argument('--no-power-feedback',action='store_true',help='MANUAL_UNMONITORED firmware만 허용')
    parser.add_argument('--inspect-real',action='store_true',help='실차 identity/정지/ENC만 확인, ARM/M/V 금지')
    parser.add_argument('--terminal',action='store_true',help='Tk 없이 Windows 터미널 키 홀드 수동시험')
    parser.add_argument('--terminal-smoke',action='store_true',help='터미널 제어 모의시험; COM/GPIO 없음')
    parser.add_argument('--diagnostics',action='store_true',help='새 DIAG/IO 지원 주행 펌웨어 전용: 정지 점검 또는 터미널 오류 후 레지스터·최초 원인 조회')
    parser.add_argument('--percent',type=int,default=1,help='터미널 시작 출력1~40, 실제 속도 아님')
    args=parser.parse_args()
    if args.diagnostics and not (args.real and (args.inspect_real or args.terminal)):
        parser.error('--diagnostics는 --real의 --inspect-real 또는 --terminal과 사용합니다')
    if not 1<=args.percent<=40:parser.error('--percent는1~40입니다')
    if args.terminal and (not args.real or args.inspect_real):parser.error('--terminal은 --real과 사용하며 --inspect-real과 함께 쓸 수 없습니다')
    if args.real and args.terminal_smoke:parser.error('실차와 모의시험을 혼합할 수 없습니다')
    if args.terminal_smoke:return terminal_smoke()
    if args.real:return real_session(args)
    if args.port or args.no_power_feedback or args.inspect_real:parser.error('실차 인자는 --real이 필요합니다')
    if args.smoke:return smoke()
    if args.sim_smoke:return sim_smoke()
    from wafer_cart_keyboard_drive.manual_simulator_ui import SimulatorWindow
    return SimulatorWindow(ROOT,ui_test=args.ui_test or args.hardware_ui_test,
                           hardware_ui_test=args.hardware_ui_test).mainloop()


if __name__ == '__main__':
    raise SystemExit(main())
