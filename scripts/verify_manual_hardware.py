"""Headless MANUAL_ONLY gateway test using real C++ code, no COM/GPIO or GUI."""
from pathlib import Path
import json
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/wafer_cart_keyboard_drive'))
from wafer_cart_keyboard_drive.firmware_simulator import FirmwareSimulatorWire
from wafer_cart_keyboard_drive.manual_hardware import ManualHardware


def verify_keyboard_hold():
    # PC C++ firmware only: no COM, no GUI, no physical power/motor commands.
    wire=FirmwareSimulatorWire(ROOT,unmonitored=True)
    session=ManualHardware(ROOT,wire=wire,percent=1,no_power_feedback=True,keyboard_hold=True)
    checks=[]
    counts=[0]*4
    def ticks(duration=.18):
        end=time.monotonic()+duration
        while time.monotonic()<end:
            session.tick()
            for i,value in enumerate(session.plant.outputs):
                if value:counts[i]+=1 if value>0 else -1
            wire.encoder_feedback(counts)
            time.sleep(.01)
    def release():
        session.drive.set_keys(set());ticks()
        assert not session.gateway.armed and not any(session.plant.outputs)
    try:
        session.drive.enable_keyboard_hold(operator_confirmed=True)
        ticks(.05)
        assert not session.gateway.armed and not any(session.plant.outputs)
        checks.append('one-time confirmation never arms/moves')
        session.drive.select_motor(2)
        for key in ('up','up','down'):
            before=counts[1]
            session.drive.set_keys({key});ticks()
            assert session.gateway.armed and session.plant.outputs[1]
            assert all(not session.plant.outputs[i] for i in (0,2,3))
            assert (counts[1]>before) if key=='up' else (counts[1]<before)
            release()
        checks.append('three fresh holds and releases without repeated prepare; M2 right-rear ASSUMED')
        session.drive.set_keys({'up'});ticks()
        session.drive.stop();ticks()
        session.drive.set_keys({'up'});ticks(.05)
        assert not session.gateway.armed
        release()
        checks.append('Space/STOP blocks held autorepeat')
        session.drive.set_keys({'up'});ticks()
        session.drive.set_keys({'up'},focused=False);ticks()
        session.drive.set_keys({'up'},focused=True);ticks(.05)
        assert not session.gateway.armed
        release()
        checks.append('focus loss stops; repeated key cannot resume')
        try:session.drive.select_mode('vector')
        except ValueError:checks.append('unverified four-wheel mapping remains locked')
        else:raise AssertionError('vector mapping unexpectedly unlocked')
        original=session.gateway.exchange
        def first_failure(operation,*values):
            if operation=='POWER_ACK':raise TimeoutError('TEST_FIRST_POWER_ACK_FAILURE')
            return original(operation,*values)
        session.gateway.exchange=first_failure
        session.drive.set_keys({'up'})
        try:session.tick()
        except TimeoutError:pass
        else:raise AssertionError('injected failure did not latch')
        session.gateway.exchange=original
        assert session.drive.latched and not session.drive.session_confirmed
        assert 'POWER_ACK' in session.drive.first_error and 'TEST_FIRST_POWER_ACK_FAILURE' in session.drive.first_error
        original_error=session.drive.first_error
        session.drive.select_motor(3)
        session.drive.set_keys(set());session.drive.set_keys({'up'});session.tick()
        assert not session.gateway.armed and not any(session.plant.outputs)
        assert session.drive.first_error==original_error
        checks.append('first fault survives ESTOP and later selection; no automatic resume')
        report={'result':'PASS','checks':checks,'physical_device_opened':False,'gui_opened':False,
                'snapshot':session.snapshot()}
        path=ROOT/'data/output/manual_keyboard_hold_headless.json'
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False))
    finally:session.close()


def verify_unmonitored():
    wire=FirmwareSimulatorWire(ROOT,unmonitored=True)
    session=ManualHardware(ROOT,wire=wire,percent=1,no_power_feedback=True)
    checks=[]
    counts=[0]*4
    def tick():
        session.tick()
        for i,value in enumerate(session.plant.outputs):
            if value:counts[i]+=1 if value>0 else -1
        wire.encoder_feedback(counts)
        time.sleep(.02)
    try:
        tick()
        assert not session.gateway.armed and not any(session.plant.outputs)
        assert session.device_status[2]=='0'
        checks.append('connect outputs zero; power remains unknown')
        session.set_speed(40)
        assert session.drive.percent==40 and not session.gateway.armed
        for channel in range(1,5):
            session.drive.select_motor(channel)
            session.drive.prepare();session.drive.set_keys({'up'})
            end=time.monotonic()+2.0
            while time.monotonic()<end:
                tick()
                if session.plant.outputs[channel-1]==80:break
            assert session.plant.outputs[channel-1]==80 and session.device_status[2]=='0'
            assert all(not session.plant.outputs[i] for i in range(4) if i!=channel-1)
            session.drive.set_keys(set(),focused=False)
            end=time.monotonic()+2.0
            while time.monotonic()<end:
                tick()
                if not any(session.plant.outputs):break
            assert session.is_stopped()
            session.drive.set_keys({'up'},focused=True);tick()
            assert not session.gateway.armed and not any(session.plant.outputs)
            session.drive.set_keys(set())
        checks.append('M1..M4 40% hold, focus STOP and no automatic resume')
        try:session.drive.select_mode('vector')
        except ValueError:checks.append('unverified four-wheel motion blocked')
        else:raise AssertionError('mapping lock lost')
        try:session.set_speed(41)
        except ValueError:checks.append('41% rejected')
        else:raise AssertionError('upper limit lost')
        session.drive.prepare();session.drive.stop()
        try:session.gateway.exchange('ARM')
        except Exception:checks.append('prepare cancellation clears one-shot acknowledgment')
        else:raise AssertionError('stale acknowledgment armed')
        # Last rejection is an MCU fault: establish a new operator acknowledgment.
        session.drive.prepare();session.drive.set_keys({'up'});session.drive.step()
        time.sleep(.55)
        status=session.gateway.exchange('STATUS')
        assert status[1]=='COMMAND_TIMEOUT' and not any(map(int,status[5:]))
        checks.append('heartbeat loss immediately zeroes output')
        session.drive.estop()
        try:session.drive.prepare()
        except ValueError:checks.append('software ESTOP latched until app restart')
        else:raise AssertionError('ESTOP not latched')
        report={'result':'PASS','checks':checks,'physical_device_opened':False,'gui_opened':False,
                'snapshot':session.snapshot()}
        (ROOT/'data/output/manual_unmonitored_headless.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False))
    finally:session.close()


def main():
    if '--keyboard-hold' in sys.argv:
        verify_keyboard_hold()
        return
    if '--unmonitored' in sys.argv:
        verify_unmonitored()
        return
    wire=FirmwareSimulatorWire(ROOT,manual_fixture=True)
    wire.power_feedback(False)
    session=ManualHardware(ROOT,wire=wire,percent=10,mapping_verified=True)
    wire.power_feedback(True)
    checks=[]
    counts=[0]*4
    def tick():
        session.tick()
        for i,value in enumerate(session.plant.outputs):
            if value:counts[i]+=1 if value>0 else -1
        wire.encoder_feedback(counts)
        time.sleep(.02)
    def hold(key):
        session.drive.prepare();session.drive.set_keys({key})
        end=time.monotonic()+.35
        while time.monotonic()<end:tick()
        assert session.gateway.armed and any(session.plant.outputs)
        session.drive.set_keys(set(),focused=False)
        end=time.monotonic()+.25
        while time.monotonic()<end:tick()
        assert session.is_stopped()
        session.drive.set_keys(set(),focused=True)
    try:
        tick()
        assert not session.gateway.armed and not any(session.plant.outputs)
        checks.append('connect never arms')
        for channel in range(1,5):
            session.drive.select_motor(channel)
            before=list(counts);hold('up')
            assert counts[channel-1]>before[channel-1]
            assert all(counts[i]==before[i] for i in range(4) if i!=channel-1)
        checks.append('M1..M4 and focus loss STOP')
        session.drive.select_mode('vector')
        for key in ('w','s','a','d','q','e'):hold(key)
        checks.append('six vector directions and release STOP')
        session.drive.set_keys({'w'});tick()
        assert not session.gateway.armed
        session.drive.set_keys(set())
        checks.append('no automatic resume')
        session.drive.prepare();session.drive.set_keys({'w'});session.drive.step()
        time.sleep(.6)
        assert session.gateway.exchange('STATUS')[1]=='COMMAND_TIMEOUT'
        assert not session.gateway.armed
        checks.append('missing heartbeat timeout')
        session.drive.estop()
        try:session.drive.prepare()
        except ValueError:checks.append('manual fault latch')
        else:raise AssertionError('fault rearmed')
        assert session.snapshot()['pose'] is None
        assert session.plant.distance==0 and not session.snapshot()['motor_enabled']
        assert session.last_encoder['measured'] is False
        report={'result':'PASS','checks':checks,'physical_device_opened':False,
                'gui_opened':False,'snapshot':session.snapshot()}
        path=ROOT/'data/output/manual_hardware_headless.json'
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False))
    finally:session.close()


if __name__=='__main__':main()
