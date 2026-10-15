"""시간 기록 시험. 실제 serial 개방이나 모터 출력은 없습니다."""
import csv
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from travel_log import TravelLog, MOTIONS, motion_direction
from test_adapter import Clock
from driver_adapter import Session, PreviewSerial


def status(state="ready", mode="preview", speed=10, command="V 10 0 0"):
    return dict(state=state, mode=mode, speed=speed, last_motion=command,
                motion=(10, 0, 0) if state == "moving" else None)


class TravelTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.log = TravelLog(self.clock, lambda: "2026-10-12T12:00:00+09:00")

    def test_all_motion_times_and_csv(self):
        from driver_adapter import motor
        for index, (key, vector) in enumerate(motor.MOTIONS.items()):
            command = "V " + " ".join(str(v * 20) for v in vector)
            self.assertEqual(motion_direction(command, 20), key)
            self.log.observe(status("moving", "preview", 20, command))
            self.clock.now += index + 1
            self.log.observe(status("stopping", "preview", 20, command))
            row = self.log.motion_last[key]
            self.assertEqual(row["경과초"], f"{index + 1:.3f}")
            self.assertEqual(row["주행방향"], MOTIONS[key])
            self.assertEqual(row["모드"], "모의")
            self.assertEqual(row["사용자확인거리m"], "")
        self.assertEqual(set(self.log.motion_last), set(MOTIONS))
        self.assertIsNone(motion_direction("V 0 0 0", 0))
        self.assertIsNone(motion_direction("V 20 20 0", 20))
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = self.log.export(directory)
            with path.open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual([r["주행방향"] for r in rows], list(MOTIONS.values()))

    def test_motion_error_speed_change_and_last_result(self):
        self.log.observe(status("moving", speed=10))
        self.clock.now += 1
        self.log.observe(status("moving", speed=20, command="V 20 0 0"))
        self.assertEqual(self.log.motion_last["w"]["종료사유"], "명령 변경")
        self.clock.now += 2
        self.log.observe(status("fault", speed=20))
        self.assertEqual(self.log.motion_last["w"]["경과초"], "2.000")
        self.assertEqual(self.log.motion_last["w"]["종료사유"], "fault")
        self.clock.now += 5
        self.log.observe(status("disconnected"))
        self.assertEqual(self.log.motion_last["w"]["경과초"], "2.000")

    def test_output_selection_limits_and_no_motion(self):
        from timed_drive import MainSession
        session = MainSession(self.clock)
        serial = PreviewSerial()
        session.connect("preview", factory=lambda: serial)
        for _ in range(40):
            self.clock.now += .025
            session.tick(set(), True, self.clock())
        before = list(serial.commands)
        for value in range(5, 41, 5):
            session.set_manual_speed(value)
            self.assertEqual(session.speed, value)
            self.assertEqual(serial.commands, before)
        for value in (0, 41, 100, 12, 20.0, True):
            with self.assertRaises(ValueError):
                session.set_manual_speed(value)
        with self.assertRaises(ValueError):
            session.set_manual_speed(20, {"w"})
        session.state = "moving"
        with self.assertRaises(ValueError):
            session.set_manual_speed(20)
        session.state = "ready"
        session.control_mode = "sequence"
        with self.assertRaises(ValueError):
            session.set_manual_speed(20)
        session.disconnect()

    def test_segment_start_stop(self):
        self.log.observe(status())
        self.clock.now = 1
        self.log.observe(status("moving"))
        self.clock.now = 3.5
        self.log.observe(status("stopping"))
        self.assertEqual(self.log.rows[0]["경과초"], "2.500")
        self.assertEqual(self.log.rows[0]["사용자확인거리m"], "")
        self.log.observe(status())
        self.assertEqual(len(self.log.rows), 1)

    def test_repeated_snapshot_does_not_restart(self):
        self.log.observe(status("moving"))
        self.clock.now = 4
        self.log.observe(status("moving"))
        self.assertEqual(self.log.elapsed(), 4)

    def test_manual_real_distance_is_explicit(self):
        self.assertTrue(self.log.arm(status(mode="real")))
        self.log.observe(status("moving", "real"))
        self.clock.now = 5
        self.assertTrue(self.log.arrive(status("moving", "real")))
        self.assertEqual(self.log.rows[-1]["참고평균m_s"], "0.200")
        self.assertIsNotNone(self.log.active)  # 도착 기록은 정지가 아닙니다.
        self.assertFalse(self.log.arrive(status("moving", "real")))

    def test_preview_has_no_distance_or_speed(self):
        self.log.arm(status())
        self.log.observe(status("moving"))
        self.clock.now = 5
        self.log.arrive(status("moving"))
        self.assertEqual(self.log.rows[-1]["참고평균m_s"], "")
        self.assertEqual(self.log.rows[-1]["사용자확인거리m"], "")

    def test_interruption_cancels_distance(self):
        for end in ("stopping", "fault", "disconnected"):
            self.log.arm(status())
            self.log.observe(status("moving"))
            self.clock.now += 2
            self.log.observe(status(end))
            self.assertIsNone(self.log.trial)
            self.assertFalse(self.log.arrive(status(end)))

    def test_direction_change_cancels_trial(self):
        self.log.arm(status())
        self.log.observe(status("moving"))
        self.clock.now = 1
        self.log.observe(status("moving", command="V 0 0 10"))
        self.assertIsNone(self.log.trial)
        self.assertEqual(self.log.rows[0]["종료사유"], "명령 변경")

    def test_nonforward_cannot_start_trial(self):
        self.log.arm(status())
        self.log.observe(status("moving", command="V -10 0 0"))
        self.assertIsNone(self.log.trial)
        self.assertFalse(self.log.armed)

    def test_arm_requires_ready_and_cancel(self):
        self.assertFalse(self.log.arm(status("moving")))
        self.log.arm(status())
        self.log.cancel()
        self.assertFalse(self.log.armed)
        self.log.arm(status())
        self.log.observe(status("disconnected"))
        self.assertFalse(self.log.armed)

    def test_export_unicode_bom_unique(self):
        self.log.observe(status("moving"))
        self.clock.now = 2
        self.log.finish("앱 종료")
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp:
            path = self.log.export(temp)
            self.assertTrue(path.read_bytes().startswith(b"\xef\xbb\xbf"))
            with path.open(encoding="utf-8-sig", newline="") as f:
                self.assertEqual(next(csv.DictReader(f))["종료사유"], "앱 종료")
            self.assertNotEqual(path, self.log.export(temp))

    def test_memory_bounded(self):
        for _ in range(510):
            self.log.observe(status("moving"))
            self.log.finish("정지")
        self.assertEqual(len(self.log.rows), 500)

    def test_recording_does_not_change_control_trace(self):
        def trace(recording):
            clock, serial = Clock(), PreviewSerial()
            session = Session(clock)
            logger = TravelLog(clock)
            session.connect("preview", factory=lambda: serial)
            for key, count in ((None, 40), ("w", 12), (None, 40), ("d", 8), (None, 40),
                               ("z", 16), (None, 40), ("c", 16), (None, 40)):
                for _ in range(count):
                    clock.now += .025
                    session.tick({key} if key else set(), True, clock())
                    if recording:
                        logger.observe(session.snapshot())
            session.disconnect()
            return serial.commands
        self.assertEqual(trace(False), trace(True))

    def lateral_run(self, direction="z", mode="real", speed=20, end="stopping"):
        command = f'V 0 {speed * (-1 if direction == "z" else 1)} 0'
        self.log.observe(status("moving", mode, speed, command))
        self.clock.now += 4
        self.log.observe(status(end, mode, speed, command))
        return status("ready", mode, speed, command)

    def test_lateral_separate_directions_and_explicit_confirmation(self):
        for direction, label in (("z", "왼쪽"), ("c", "오른쪽")):
            ready = self.lateral_run(direction)
            self.assertEqual(self.log.lateral_last[direction]["평행방향"], label)
            self.assertTrue(self.log.confirm_lateral(direction, ready))
            row = self.log.rows[-1]
            self.assertEqual(row["사용자확인초_m"], "4.000")
            self.assertEqual(row["참고평균m_s"], "0.250")
            self.assertFalse(self.log.confirm_lateral(direction, ready))
        self.assertEqual(set(self.log.lateral_calibration), {"z", "c"})

    def test_lateral_no_inferred_distance_preview_wrong_speed_or_fault(self):
        for mode, speed, end in (("preview",20,"stopping"), ("real",10,"stopping"),
                                 ("real",20,"fault"), ("real",20,"disconnected")):
            ready = self.lateral_run(mode=mode, speed=speed, end=end)
            self.assertFalse(self.log.confirm_lateral("z", ready))
            self.assertEqual(self.log.rows[-1]["사용자확인거리m"], "")
            self.assertEqual(self.log.rows[-1]["사용자확인초_m"], "")

    def test_lateral_candidate_invalidated_on_new_movement_or_disconnect(self):
        ready = self.lateral_run()
        self.assertTrue(self.log.can_confirm_lateral("z", ready))
        self.log.observe(status("moving", "real", 20, "V 20 0 0"))
        self.assertFalse(self.log.can_confirm_lateral("z", ready))
        self.log.observe(status("ready", "real", 20))
        self.lateral_run()
        self.log.observe(status("disconnected", "real", 20))
        self.assertFalse(self.log.can_confirm_lateral("z", ready))

    def test_lateral_confirm_requires_ready_manual_and_nonzero_time(self):
        ready = self.lateral_run()
        self.assertFalse(self.log.can_confirm_lateral("z", dict(ready, state="moving")))
        self.assertFalse(self.log.can_confirm_lateral("z", dict(ready, control_mode="sequence")))
        self.log.observe(status("moving", "real", 20, "V 0 -20 0"))
        self.log.observe(ready)
        self.assertFalse(self.log.can_confirm_lateral("z", ready))

    def test_lateral_csv_calibration_roundtrip(self):
        self.log.confirm_lateral("c", self.lateral_run("c"))
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = self.log.export(directory)
            with path.open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(rows[-1]["평행방향"], "오른쪽")
            self.assertEqual(rows[-1]["사용자확인초_m"], "4.000")
            self.assertEqual(rows[0]["사용자확인거리m"], "")

    def test_main_lateral_tab_mouse_keyboard_release_and_focus(self):
        import tkinter as tk
        import time
        from app import App
        root = tk.Tk()
        root.withdraw()
        ui = App(root, True)
        class Input:
            key = None
            focused = True
            def GetForegroundWindow(self): return ui.hwnd if self.focused else 0
            def GetAsyncKeyState(self, key): return 0x8000 if key == self.key else 0
        fake = Input()
        ui.user32 = fake
        def pump(seconds):
            until = time.monotonic() + seconds
            while time.monotonic() < until:
                root.update()
                time.sleep(.01)
        try:
            ui.monitor_tabs.select(ui.lateral_page)
            pump(.1)
            ui.output_choice.set("41")
            ui.output_apply.invoke()
            pump(.1)
            self.assertEqual(ui.worker.get_status()["speed"], 10)
            ui.output_choice.set("20")
            ui.output_apply.invoke()
            pump(.3)
            self.assertIsNone(ui.output_pending)
            ui.connect()
            pump(1)
            self.assertEqual(ui.worker.get_status()["speed"],20)
            self.assertEqual(set(ui.lateral_buttons), set(MOTIONS))
            from driver_adapter import motor
            for direction, vector in motor.MOTIONS.items():
                command = "V " + " ".join(str(v * 20) for v in vector)
                ui.lateral_buttons[direction].event_generate("<ButtonPress-1>")
                pump(.3)
                self.assertEqual(ui.worker.get_status()["last_motion"], command)
                self.assertIn("20%", ui.lateral_clock.get())
                self.assertEqual(str(ui.output_apply.cget("state")), "disabled")
                ui.release_mouse()
                pump(.9)
                self.assertEqual(ui.worker.get_status()["state"], "ready")
                self.assertGreater(float(ui.travel_log.motion_last[direction]["경과초"]), .1)
                self.assertIn("모의 최근", ui.lateral_values[direction].get())
                if direction in ui.lateral_confirm:
                    self.assertEqual(str(ui.lateral_confirm[direction].cget("state")), "disabled")
            ui.output_choice.set("30")
            ui.output_apply.invoke()
            pump(.3)
            self.assertEqual(ui.worker.get_status()["speed"], 30)
            self.assertIn("현재 적용 30%", ui.output_status.get())
            fake.key = ord("Z")
            pump(.3)
            self.assertEqual(ui.worker.get_status()["state"], "moving")
            fake.focused = False
            pump(.9)
            self.assertNotEqual(ui.worker.get_status()["state"], "moving")
            fake.focused = True
            pump(.3)
            self.assertNotEqual(ui.worker.get_status()["state"], "moving")
            fake.key = None
            pump(.2)
            ui.hold_mouse("c")
            pump(.3)
            ui.monitor_tabs.select(ui.route_page)
            pump(.9)
            self.assertNotEqual(ui.worker.get_status()["state"], "moving")
            ui.worker.request("disconnect")
            pump(.2)
            with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
                path = ui.travel_log.export(directory)
                self.assertIn("오른쪽", path.read_text(encoding="utf-8-sig"))
        finally:
            ui.travel_log.saved_count = ui.travel_log.count
            ui.close()

    def test_ui_timing_keys_send_no_motor_commands(self):
        from app import App
        calls = []
        ui = App.__new__(App)
        ui.timing_keys = set()
        ui.arm_timing = lambda: calls.append("arm")
        ui.arrive_timing = lambda: calls.append("arrive")
        ui.speed_keys = set()
        ui.speed_key_down(SimpleNamespace(keysym="F8"))
        ui.speed_key_down(SimpleNamespace(keysym="F8"))
        ui.speed_key_up(SimpleNamespace(keysym="F8"))
        ui.speed_key_down(SimpleNamespace(keysym="F9"))
        self.assertEqual(calls, ["arm", "arrive"])

    def test_export_blocked_while_connected(self):
        from app import App
        ui = App.__new__(App)
        ui.worker = SimpleNamespace(get_status=lambda: status("ready", "real"))
        ui.connecting = False
        ui.travel_log = self.log
        ui.export_timing()
        self.assertIn("연결을 종료", self.log.note)


if __name__ == "__main__":
    unittest.main()
