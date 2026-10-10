import time
import unittest

from wafer_cart_keyboard_drive.bench_gateway import BenchGateway
from wafer_cart_keyboard_drive.bench_mock import MockWire
from wafer_cart_keyboard_drive.bench_protocol import unframe
from wafer_cart_keyboard_drive.manual_first_drive import ManualFirstDrive, parse_command_percent


class ManualFirstDriveTest(unittest.TestCase):
    def test_percent_input_rejects_invalid_without_rounding(self):
        for text in ('', 'abc', 'nan', 'inf', '-inf', '0', '31', '5.5', None):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_command_percent(text)
        for text,value in (('1',1),('30',30),(' 7 ',7),('10.0',10)):
            self.assertEqual(parse_command_percent(text),value)

    def test_adjusted_speed_drives_next_manual_command(self):
        self.drive.set_percent(7)
        self.assertFalse(self.gateway.armed)
        self.drive.prepare()
        self.drive.set_keys({'up'})
        self.drive.step()
        self.assertEqual(self.drive.last_command,('M',1,7))
        with self.assertRaises(ValueError):self.drive.set_percent(9)
        self.assertEqual(self.drive.percent,7)

    def test_explicit_40_percent_input_cap(self):
        self.assertEqual(parse_command_percent('40',40),40)
        with self.assertRaises(ValueError):parse_command_percent('41',40)
        with self.assertRaises(ValueError):parse_command_percent('40')

    def setUp(self):
        self.wire = MockWire(mapping_verified=True, simulate_encoder=True)
        self.gateway = BenchGateway(self.wire)
        self.gateway.connect(limit_percent=10)
        self.wire.power_feedback(True)
        self.drive = ManualFirstDrive(self.gateway, mapping_verified=True)

    def tearDown(self):
        self.gateway.close()
        self.assertFalse(self.wire.armed)

    def operations(self):
        return [unframe(raw)[3] for raw in self.wire.sent if raw.startswith(b"C2 ")]

    def test_no_motion_without_separate_prepare(self):
        self.drive.set_keys({"up"})
        self.drive.step()
        self.assertNotIn("ARM", self.operations())
        self.assertNotIn("M", self.operations())

    def test_key_tap_between_ticks_does_not_arm(self):
        self.drive.prepare()
        self.drive.set_keys({"up"})
        self.drive.set_keys(set())
        self.drive.step()
        self.assertNotIn("ARM", self.operations())
        self.assertNotIn("M", self.operations())

    def test_prepare_rejects_missing_power_feedback(self):
        self.wire.power_feedback(False)
        with self.assertRaises(ValueError):
            self.drive.prepare()
        self.assertNotIn("ARM", self.operations())

    def test_single_hold_release_and_no_automatic_resume(self):
        self.drive.prepare()
        self.drive.set_keys({"up"})
        self.drive.step()
        self.assertEqual(self.drive.last_command, ("M", 1, 10))
        self.drive.set_keys(set())
        self.drive.step()
        self.assertFalse(self.gateway.armed)
        self.assertEqual(self.operations()[-1], "STOP")
        self.drive.set_keys({"up"})
        self.drive.step()
        self.assertEqual(self.operations()[-1], "STOP")

    def test_four_motors_and_both_directions(self):
        for channel in range(1, 5):
            for key, sign in (("up", 1), ("down", -1)):
                self.drive.select_motor(channel)
                self.drive.prepare()
                self.drive.set_keys({key})
                self.drive.step()
                self.assertEqual(self.drive.last_command, ("M", channel, sign * 10))
                self.drive.set_keys(set())
                self.drive.step()
                time.sleep(0.17)  # Model ramp settles; not a real stopping-time measurement.

    def test_vector_keys_after_mapping_flag(self):
        self.drive.select_mode("vector")
        self.drive.prepare()
        self.drive.set_keys({"w", "d", "e"})
        self.drive.step()
        self.assertEqual(self.drive.last_command[0], "V")
        self.assertLessEqual(sum(abs(v) for v in self.drive.last_command[1:]), 10)
        self.drive.set_keys(set())
        self.drive.step()
        self.assertFalse(self.gateway.armed)

    def test_vector_locked_without_mapping(self):
        drive = ManualFirstDrive(self.gateway, mapping_verified=False)
        with self.assertRaises(ValueError):
            drive.select_mode("vector")
        self.assertNotIn("ARM", self.operations())

    def test_c2_keys_use_left_and_counterclockwise_positive(self):
        self.drive.select_mode("vector")
        for key,command in (("a",("V",0,10,0)),("d",("V",0,-10,0)),
                            ("q",("V",0,0,10)),("e",("V",0,0,-10))):
            self.drive.set_keys({key})
            self.assertEqual(self.drive._command(),command)

    def test_focus_loss_sends_stop_and_requires_prepare(self):
        self.drive.prepare()
        self.drive.set_keys({"up"})
        self.drive.step()
        self.drive.set_keys({"up"}, focused=False)
        self.assertFalse(self.gateway.armed)
        self.assertEqual(self.operations()[-1], "STOP")
        self.drive.set_keys({"up"}, focused=True)
        self.drive.step()
        self.assertEqual(self.operations()[-1], "STOP")

    def test_estop_latches_and_never_auto_rearms(self):
        self.drive.prepare()
        self.drive.set_keys({"up"})
        self.drive.step()
        self.drive.estop()
        self.assertTrue(self.drive.latched)
        self.drive.set_keys({"up"})
        self.drive.step()
        with self.assertRaises(ValueError):
            self.drive.prepare()

    def test_speed_change_only_while_stopped(self):
        self.drive.set_percent(12)
        self.assertEqual(self.wire.limit, 12)
        self.drive.prepare()
        with self.assertRaises(ValueError):
            self.drive.set_percent(13)
        for value in (0, 31, 1.5, True):
            with self.assertRaises(ValueError):
                self.drive.set_percent(value)

    def test_mode_switch_stops_and_cancels_prepare(self):
        self.drive.prepare()
        self.drive.select_mode("vector")
        self.assertFalse(self.drive.prepared)
        self.drive.set_keys({"w"})
        self.drive.step()
        self.assertNotIn("V", self.operations())

    def test_event_fault_disables_future_motion(self):
        self.drive.prepare()
        self.drive.set_keys({"up"})
        self.drive.step()
        self.wire.inject(f"E2 {self.gateway.session} POWER_OFF")
        time.sleep(0.04)
        with self.assertRaises(Exception):
            self.drive.step()
        self.assertTrue(self.drive.latched)


class HoldGatewayStub:
    expected_mode = 'MANUAL_UNMONITORED'
    max_percent = 40
    def __init__(self):
        self.armed = False
        self.operations = []
        self.reason = 'STARTUP_LOCKED'
        self.output = 0
        self.fail_operation = None
    def exchange(self, operation, *values):
        self.operations.append((operation, *values))
        if operation == self.fail_operation:
            raise TimeoutError('first ACK failure')
        if operation == 'STATUS':
            return ['3' if self.reason == 'FAULT' else '0', self.reason, '0',
                    str(int(self.armed)), '1', str(self.output), '0', '0', '0']
        if operation == 'ARM': self.armed = True
        elif operation == 'M': self.output = values[1]
        elif operation in ('STOP', 'ESTOP'):
            self.armed = False; self.output = 0
        return []


class KeyboardHoldTest(unittest.TestCase):
    def setUp(self):
        self.gateway = HoldGatewayStub()
        self.drive = ManualFirstDrive(self.gateway, percent=1, keyboard_hold=True)

    def enable(self):
        self.drive.enable_keyboard_hold(operator_confirmed=True)

    def press(self):
        self.drive.set_keys({'up'}); self.drive.step()

    def release(self):
        self.drive.set_keys(set()); self.drive.step()

    def test_confirmation_does_not_arm_or_move(self):
        self.enable()
        self.assertFalse(self.gateway.armed)
        self.assertFalse(self.drive.prepared)
        self.assertNotIn(('POWER_ACK',), self.gateway.operations)
        self.assertNotIn(('ARM',), self.gateway.operations)

    def test_without_confirmation_key_cannot_move(self):
        self.press()
        self.assertFalse(self.gateway.armed)

    def test_explicit_confirmation_required_and_held_key_rejected(self):
        with self.assertRaises(ValueError):self.drive.enable_keyboard_hold(operator_confirmed=False)
        self.drive.set_keys({'up'})
        with self.assertRaises(ValueError):self.enable()

    def test_repeat_press_release_without_modal_prepare(self):
        self.enable()
        for _ in range(3):
            self.press()
            self.assertEqual(self.drive.last_command, ('M', 1, 1))
            self.release()
            self.assertFalse(self.gateway.armed)
        self.assertEqual(self.gateway.operations.count(('ARM',)), 3)
        self.assertEqual(self.gateway.operations.count(('POWER_ACK',)), 3)

    def test_explicit_stop_requires_release_before_new_press(self):
        self.enable(); self.press(); self.drive.stop()
        self.press()  # OS autorepeat of an already held key is not a new gesture.
        self.assertFalse(self.gateway.armed)
        self.release(); self.press()
        self.assertTrue(self.gateway.armed)

    def test_motor_change_while_held_does_not_restart(self):
        self.enable(); self.press(); self.drive.select_motor(2); self.press()
        self.assertFalse(self.gateway.armed)
        self.release(); self.press()
        self.assertEqual(self.drive.last_command, ('M', 2, 1))

    def test_focus_loss_does_not_restart_on_repeated_key(self):
        self.enable(); self.press()
        self.drive.set_keys({'up'}, focused=False)
        self.drive.set_keys({'up'}, focused=True); self.drive.step()
        self.assertFalse(self.gateway.armed)
        self.release(); self.press()
        self.assertTrue(self.gateway.armed)

    def test_fault_latches_preserves_first_operation_and_disables_session(self):
        self.enable(); self.gateway.fail_operation = 'POWER_ACK'
        with self.assertRaises(TimeoutError):self.press()
        self.assertTrue(self.drive.latched)
        self.assertFalse(self.drive.session_confirmed)
        self.assertIn('POWER_ACK', self.drive.first_error)
        self.assertIn('first ACK failure', self.drive.first_error)
        self.gateway.fail_operation = None
        self.release(); self.press()
        self.assertFalse(self.gateway.armed)
        with self.assertRaises(ValueError):self.enable()

    def test_estop_never_rearms(self):
        self.enable(); self.press(); self.drive.estop(); self.release(); self.press()
        self.assertFalse(self.gateway.armed)
        self.assertFalse(self.drive.session_confirmed)

    def test_firmware_fault_is_not_cleared_by_keyboard_session(self):
        self.gateway.reason = 'FAULT'
        with self.assertRaises(ValueError):self.enable()
        self.assertFalse(self.drive.session_confirmed)

    def test_unverified_vector_still_blocked(self):
        self.enable()
        with self.assertRaises(ValueError):self.drive.select_mode('vector')

    def test_still_ramping_never_starts_later_without_new_press(self):
        self.enable(); self.gateway.output = 1
        self.press()
        self.assertFalse(self.gateway.armed)
        self.gateway.output = 0
        self.drive.step()
        self.assertFalse(self.gateway.armed)
        self.release(); self.press()
        self.assertTrue(self.gateway.armed)

    def make_ui(self):
        from types import SimpleNamespace, MethodType
        from wafer_cart_keyboard_drive.manual_simulator_ui import SimulatorWindow
        ui = SimpleNamespace(sim=SimpleNamespace(drive=self.drive,last_command=None),
            held=set(),blocked_keys=set(),pointer_key=None,error='',transport_fault=False,
            speed_entry=object(),speed_scale=object(),refresh=lambda:None)
        for name in ('run','stop','on_press','on_release','change_motor'):
            setattr(ui,name,MethodType(getattr(SimulatorWindow,name),ui))
        return ui

    def test_real_ui_handlers_space_blocks_autorepeat_until_release(self):
        from types import SimpleNamespace
        self.enable(); ui = self.make_ui(); widget = object()
        up = SimpleNamespace(keysym='Up',widget=widget)
        ui.on_press(up)
        self.assertTrue(self.gateway.armed)
        ui.on_press(SimpleNamespace(keysym='space',widget=widget))
        ui.on_press(up)
        self.assertFalse(self.gateway.armed)
        ui.on_release(up); ui.on_press(up)
        self.assertTrue(self.gateway.armed)

    def test_click_same_motor_stops_without_held_key_restart(self):
        from types import SimpleNamespace
        self.enable(); ui = self.make_ui(); up = SimpleNamespace(keysym='Up',widget=object())
        ui.on_press(up); ui.change_motor(1); ui.on_press(up)
        self.assertFalse(self.gateway.armed)
        ui.on_release(up); ui.on_press(up)
        self.assertTrue(self.gateway.armed)

    def test_ui_success_never_erases_first_fault(self):
        self.enable(); ui = self.make_ui(); self.gateway.fail_operation = 'POWER_ACK'
        ui.run(self.press)
        first = ui.error
        self.assertIn('POWER_ACK',first)
        self.gateway.fail_operation = None
        ui.run(lambda:self.drive.select_motor(2))
        self.assertEqual(ui.error,first)
