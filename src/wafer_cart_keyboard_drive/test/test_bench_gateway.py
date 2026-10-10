import subprocess
import sys
import time
import unittest
from pathlib import Path

from wafer_cart_keyboard_drive.bench_gateway import (
    BenchGateway, FirmwareRejected, SerialStreamWire, open_physical_wire, decode_output_diagnostics)
from wafer_cart_keyboard_drive.bench_mock import MockWire
from wafer_cart_keyboard_drive.bench_protocol import ProtocolError, frame


class BenchGatewayTest(unittest.TestCase):
    def setUp(self):
        self.wire = MockWire()
        self.gateway = BenchGateway(self.wire)
        self.gateway.connect()

    def tearDown(self):
        self.gateway.close()
        self.assertFalse(self.wire.armed)
        self.assertEqual(self.wire.current, [0] * 4)

    def armed(self):
        self.wire.power_feedback(True)
        self.gateway.exchange("ARM")

    def eventually(self, check, timeout=0.3):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if check():
                return
            time.sleep(0.005)
        self.assertTrue(check())

    def test_startup_and_motion_lock(self):
        self.assertFalse(self.gateway.armed)
        with self.assertRaises(ProtocolError):
            self.gateway.jog(1, 10)

    def test_power_required(self):
        with self.assertRaises(FirmwareRejected):
            self.gateway.exchange("ARM")
        self.assertFalse(self.gateway.armed)
        self.gateway.exchange("STATUS")

    def test_jog_stop_and_manual_rearm(self):
        self.armed()
        self.gateway.jog(1, 10)
        self.assertFalse(self.gateway.armed)
        with self.assertRaises(ProtocolError):
            self.gateway.jog(1, 10)

    def test_all_four_channels_both_directions(self):
        self.wire.power_feedback(True)
        for channel in range(1, 5):
            for percent in (10, -10):
                self.gateway.exchange("ARM")
                self.gateway.jog(channel, percent, duration=0.05)
                self.assertFalse(self.gateway.armed)
                time.sleep(0.1)
                self.gateway.exchange("STATUS")
                self.assertEqual(self.wire.current, [0] * 4)

    def test_malformed_ack_payload_never_arms(self):
        class BadArmWire(MockWire):
            def _emit(self, payload):
                if " OK ARM" in payload:
                    payload += " UNEXPECTED"
                super()._emit(payload)
        wire = BadArmWire()
        with BenchGateway(wire) as gateway:
            gateway.connect()
            wire.power_feedback(True)
            with self.assertRaises(ProtocolError):
                gateway.exchange("ARM")
            self.assertFalse(gateway.armed)

    def test_unknown_event_locks(self):
        self.armed()
        self.wire.inject(f"E2 {self.gateway.session} FUTURE_UNKNOWN_EVENT")
        self.eventually(lambda: not self.gateway.armed)

    def test_jog_invalid_duration(self):
        for duration in (float("nan"), float("inf"), True, -1, 3):
            with self.assertRaises(ValueError):
                self.gateway.jog(1, 10, duration=duration)

    def test_encoder_signed_values(self):
        self.wire.counts = [1, -2, 2147483647, -2147483648]
        data = self.gateway.encoder_snapshot()
        self.assertEqual(data["counts_m1_m4"], self.wire.counts)
        self.assertFalse(data["measured"])

    def test_post_ack_event_is_read_while_idle(self):
        self.armed()
        self.wire.inject(f"E2 {self.gateway.session} TEST_FAULT")
        self.eventually(lambda: not self.gateway.armed)
        self.assertEqual(self.gateway.fault, "TEST_FAULT")

    def test_first_fault_survives_cleanup_estop(self):
        self.armed()
        self.wire.inject(f'E2 {self.gateway.session} STALL_NO_ENCODER')
        self.eventually(lambda: self.gateway.first_fault == 'STALL_NO_ENCODER')
        self.gateway.exchange('ESTOP')
        self.assertEqual(self.gateway.first_fault, 'STALL_NO_ENCODER')
        self.assertFalse(self.gateway.armed)
        self.assertTrue(any(t.get('tokens', [''])[0]=='E2' for t in self.gateway.trace))

    def test_diagnostic_query_does_not_run_while_armed(self):
        self.armed()
        before=len(self.wire.sent)
        with self.assertRaisesRegex(ProtocolError,'정지'):
            self.gateway.diagnostic_snapshot()
        self.assertEqual(len(self.wire.sent),before)

    def test_io_register_checks_detect_output_path_errors(self):
        # M3 +20% => magnitude40 => OCR1B501, OC1B enabled, all DIR positive.
        good='IO1 100 1 255 3199 3199 34 25 2 25 0 501 0 0 0 96 48 15 15 15 0 0 40 0'.split()
        self.assertTrue(decode_output_diagnostics(good)['register_check_passed'])
        self.assertFalse(decode_output_diagnostics(good)['waveform_measured'])
        for index,value,issue in ((11,'0','OCR_MISMATCH'),(6,'2','PWM_CHANNEL_ENABLE_MISMATCH'),
                                  (15,'0','PIN_NOT_OUTPUT'),(19,'0','DIR_DIGITAL_READBACK_MISMATCH'),
                                  (12,'501','UNUSED_D46_REGISTER_NONZERO'),(7,'0','TIMER_MODE_OR_PRESCALER')):
            altered=good.copy(); altered[index]=value
            self.assertIn(issue,decode_output_diagnostics(altered)['issues'])
        for bad in (good[:-1], ['IO2']+good[1:], good[:15]+['-1']+good[16:]):
            with self.assertRaises(ProtocolError):decode_output_diagnostics(bad)
        self.assertFalse(decode_output_diagnostics(['UNAVAILABLE'])['available'])

    def test_stale_same_operation_ack(self):
        self.armed()
        self.wire.inject(f"R2 {self.gateway.session} 1 OK ARM")
        self.eventually(lambda: self.gateway._broken is not None)
        with self.assertRaises(ProtocolError):
            self.gateway.exchange("M", 1, 10)

    def test_old_session_ack(self):
        self.armed()
        self.wire.inject("R2 0000000000000000 3 OK ARM")
        self.eventually(lambda: self.gateway._broken is not None)

    def test_wrong_operation_ack(self):
        self.wire.inject(f"R2 {self.gateway.session} 2 OK ARMED")
        self.eventually(lambda: self.gateway._broken is not None)

    def test_power_loss_and_no_restart(self):
        self.armed()
        self.gateway.exchange("M", 1, 10)
        self.wire.power_feedback(False)
        self.eventually(lambda: not self.gateway.armed)
        self.wire.power_feedback(True)
        self.assertFalse(self.wire.armed)
        with self.assertRaises(ProtocolError):
            self.gateway.exchange("M", 1, 10)
        self.gateway.exchange("ARM")
        self.assertTrue(self.gateway.armed)

    def test_estop_release_not_rearm(self):
        self.armed()
        self.gateway.exchange("ESTOP")
        self.eventually(lambda: not self.gateway.armed)
        with self.assertRaises(FirmwareRejected):
            self.gateway.exchange("ARM")
        self.wire.power_feedback(False)
        self.gateway.exchange("STATUS")
        self.wire.power_feedback(True)
        self.gateway.exchange("ARM")
        self.assertTrue(self.gateway.armed)

    def test_pressed_button_blocks_arm(self):
        self.wire.power_feedback(False, estop=True)
        self.gateway.exchange("STATUS")
        self.wire.power_feedback(True, estop=True)
        with self.assertRaises(FirmwareRejected):
            self.gateway.exchange("ARM")

    def test_idle_lease_timeout(self):
        self.armed()
        self.gateway.exchange("M", 1, 10)
        self.eventually(lambda: not self.gateway.armed, timeout=0.8)
        self.assertEqual(self.gateway.fault, "COMMAND_TIMEOUT")

    def test_mapping_blocks_vector(self):
        self.armed()
        with self.assertRaises(FirmwareRejected):
            self.gateway.exchange("V", 10, 0, 0)

    def test_percent_limit_and_invalid_input(self):
        self.armed()
        with self.assertRaises(FirmwareRejected):
            self.gateway.exchange("M", 1, 21)
        before = len(self.wire.sent)
        with self.assertRaises(ProtocolError):
            self.gateway.exchange("M", 1, 31)
        self.assertEqual(len(self.wire.sent), before)

    def test_controller_boot_breaks_existing_session(self):
        self.armed()
        self.wire.inject("E2 - BOOT_OUTPUT_LOCKED")
        self.eventually(lambda: self.gateway._broken is not None)

    def test_real_constructor_locked_before_open(self):
        with self.assertRaises(RuntimeError):
            open_physical_wire(port="COM_DO_NOT_OPEN", profile={"verified": True})

    def test_locked_firmware_not_accepted(self):
        wire = MockWire(locked_firmware=True)
        with BenchGateway(wire) as gateway:
            with self.assertRaises(ProtocolError):
                gateway.connect()

    def test_timeout_no_retry(self):
        class SilentWire(MockWire):
            def write(self, data):
                self.sent.append(data)
        wire = SilentWire()
        with BenchGateway(wire, timeout=0.03) as gateway:
            with self.assertRaises(TimeoutError):
                gateway.connect()
            self.assertEqual(sum(b"HELLO" in line for line in wire.sent), 1)

    def test_console_real_port_fails(self):
        root = Path(__file__).resolve().parents[3]
        result = subprocess.run([sys.executable, str(root / "scripts/bench_console.py"),
                                 "--port", "DO_NOT_OPEN"], capture_output=True, timeout=3)
        self.assertEqual(result.returncode, 2)

    def test_fragmented_stream_and_coalesced_frames(self):
        first, second = frame("E2 - BOOT"), frame("E2 - POWER_OFF")
        class FakeStream:
            timeout = 0.02
            write_timeout = 0.05
            chunks = [first[:5], first[5:] + second]
            def read(self, size):
                return self.chunks.pop(0) if self.chunks else b""
            def write(self, data):
                return len(data)
            def close(self):
                pass
        wire = SerialStreamWire(FakeStream())
        self.assertEqual(wire.readline(), b"")
        self.assertEqual(wire.readline(), first)
        self.assertEqual(wire.readline(), second)

    def test_stream_requires_bounded_timeouts(self):
        class FakeStream:
            timeout = None
            write_timeout = None
        with self.assertRaises(ValueError):
            SerialStreamWire(FakeStream())

    def test_partial_write_fails(self):
        class FakeStream:
            timeout = 0.02
            write_timeout = 0.05
            def write(self, data):
                return len(data) - 1
        with self.assertRaises(OSError):
            SerialStreamWire(FakeStream()).write(b"STOP\n")

    def test_stream_overflow_fails(self):
        class FakeStream:
            timeout = 0.02
            write_timeout = 0.05
            def read(self, size):
                return b"x" * 64
        wire = SerialStreamWire(FakeStream())
        for _ in range(3):
            self.assertEqual(wire.readline(), b"")
        with self.assertRaises(ProtocolError):
            wire.readline()
