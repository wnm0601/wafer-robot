"""모든 시험은 가상 serial만 사용합니다. 실제 포트를 열지 않습니다."""
import time
import unittest

from driver_adapter import Session, PreviewSerial, Worker, motor


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class Tests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.ser = PreviewSerial()
        self.s = Session(self.clock)
        self.s.connect("preview", factory=lambda: self.ser)
        self.step(seconds=0.8)

    def tearDown(self):
        self.s.disconnect()

    def step(self, keys=(), focused=True, seconds=.05):
        for _ in range(round(seconds/.025)):
            self.clock.now += .025
            self.s.tick(set(keys), focused, self.clock())

    def test_original_class_reused(self):
        self.assertIsInstance(self.s.control, motor.HoldController)
        self.assertIsInstance(self.s.link, motor.Link)

    def test_connect_never_moves(self):
        self.assertEqual(self.s.state, "ready")
        self.assertFalse(any(c.startswith(("M ", "P ", "V ")) for c in self.ser.commands))

    def test_hold_release(self):
        self.step({"w"}, seconds=.2)
        self.assertIn("V 10 0 0", self.ser.commands)
        self.step()
        self.assertEqual(self.ser.commands[-1], "STOP")

    def test_all_six_directions(self):
        for key, vector in motor.MOTIONS.items():
            self.step(seconds=.8)
            self.step({key})
            self.assertIn("V " + " ".join(str(x*10) for x in vector), self.ser.commands)
            self.step()

    def test_focus_loss_blocks_held_restart(self):
        self.step({"w"})
        self.step({"w"}, focused=False)
        self.assertIn("STOP", self.ser.commands)
        self.step({"w"}, seconds=.9)
        before = len([c for c in self.ser.commands if c.startswith("V ")])
        self.step({"w"}, seconds=.3)
        self.assertEqual(before, len([c for c in self.ser.commands if c.startswith("V ")]))
        self.step()
        self.step({"w"})
        self.assertEqual(self.s.state, "moving")

    def test_opposite_keys_stop(self):
        self.step({"w"})
        self.step({"w", "s"})
        self.assertEqual(self.s.state, "stopping")

    def test_speed_five_steps_clamped(self):
        for _ in range(12):
            self.s.change_speed(5)
        self.assertEqual(self.s.speed, 40)
        for _ in range(12):
            self.s.change_speed(-5)
        self.assertEqual(self.s.speed, 5)

    def test_speed_during_motion_stops_not_increases(self):
        self.step({"w"})
        self.s.change_speed(5, {"w"})
        self.assertEqual(self.s.speed, 10)
        self.assertEqual(self.s.state, "stopping")

    def test_keyboard_speed(self):
        self.step({"]"})
        self.assertEqual(self.s.speed, 15)
        self.step()
        self.step({"w"})
        self.assertIn("V 15 0 0", self.ser.commands)

    def test_stop_button_requires_release(self):
        self.step({"w"})
        self.s.stop()
        self.step({"w"}, seconds=1)
        self.assertNotEqual(self.s.state, "moving")

    def test_heartbeat_failure(self):
        self.step({"w"})
        self.clock.now += .35
        with self.assertRaisesRegex(motor.TestFault, "UI 응답 중단"):
            self.s.tick({"w"}, True, self.clock()-.35)
        self.s.fail("UI 응답 중단")
        self.assertEqual(self.ser.commands[-1], "ESTOP")
        self.assertTrue(self.ser.closed)

    def test_wrong_firmware_closes(self):
        class Wrong(PreviewSerial):
            def write(self, data):
                result = super().write(data)
                self.buffer = self.buffer.replace(motor.FIRMWARE_INFO.encode(), b"WRONG")
                return result
        wrong = Wrong()
        s = Session()
        s.connect("preview", factory=lambda: wrong)
        self.assertEqual(s.state, "fault")
        self.assertTrue(wrong.closed)

    def test_reboot_response_fault(self):
        self.ser.buffer.extend(b"READY\n")
        with self.assertRaises(motor.TestFault):
            self.step()

    def test_real_requires_confirmation_before_open(self):
        s = Session()
        calls = []
        with self.assertRaises(ValueError):
            s.connect("real", factory=lambda: calls.append("opened"))
        self.assertEqual(calls, [])

    def test_disconnect_stops_and_closes(self):
        self.step({"w"})
        self.s.disconnect()
        self.assertTrue(self.ser.closed)
        self.assertEqual(self.ser.commands[-1], "ESTOP")
        self.assertIsNone(self.s.link)

    def test_failed_estop_still_closes(self):
        original = self.ser.write
        def fail(data):
            if data == b"ESTOP\n":
                raise OSError("test")
            return original(data)
        self.ser.write = fail
        self.s.disconnect()
        self.assertTrue(self.ser.closed)
        self.assertEqual(self.s.state, "fault")
        self.assertIn("물리 전원", self.s.message)

    def test_preview_worker_forbids_real(self):
        worker = Worker(preview_only=True)
        worker.start()
        try:
            worker.request("connect", "real", "COM7", True)
            time.sleep(.1)
            self.assertEqual(worker.get_status()["state"], "fault")
            self.assertIsNone(worker.session.link)
        finally:
            worker.quit.set()
            worker.join(1)

    def test_ui_short_stop_keys_are_events(self):
        from app import App
        from types import SimpleNamespace
        events = []
        ui = App.__new__(App)
        ui.mouse_key = "w"
        ui.worker = SimpleNamespace(request=lambda *args: events.append(args))
        ui.speed_key_down(SimpleNamespace(keysym="space"))
        ui.speed_key_down(SimpleNamespace(keysym="Escape"))
        self.assertEqual(events, [("stop",), ("estop",)])
        self.assertIsNone(ui.mouse_key)


if __name__ == "__main__":
    unittest.main()
