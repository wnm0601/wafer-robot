"""실차 포트 없이 시간 이동과 중단을 검증합니다."""
import time
import unittest
import tempfile
import csv
import sys
from pathlib import Path

from driver_adapter import PreviewSerial, motor
from timed_drive import DEFAULT_SECONDS_PER_M, Plan, RotationPlan, LateralPlan, TimedSession, TimedWorker, export_rotation_records, parse_sequence, MainSession, describe_plan
from test_adapter import Clock


class TimedTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.ser = PreviewSerial()
        self.s = TimedSession(self.clock)
        self.s.connect("preview", factory=lambda: self.ser)
        self.step(.9)

    def tearDown(self):
        self.s.disconnect()

    def step(self, seconds=.025, keys=(), focused=True):
        for _ in range(round(seconds/.025)):
            self.clock.now += .025
            self.s.tick(set(keys), focused, self.clock())

    def start(self, metres=1, seconds_per_m=.5):
        self.s.start_plan(Plan(metres, seconds_per_m), True, self.clock())
        self.step()

    def test_default_distances(self):
        self.assertAlmostEqual(Plan(1, DEFAULT_SECONDS_PER_M).duration, 8.5437142857)
        self.assertAlmostEqual(Plan(2, DEFAULT_SECONDS_PER_M).duration, 17.0874285714)

    def test_sequence_parser_and_bounds(self):
        plans = parse_sequence("직진 1m → 우회전 90도, 전진 0.5미터\n좌회전 30°", 5)
        self.assertEqual([p.duration for p in plans], [5, 2, 2.5, 30/45])
        for text in ["", "직진 1m\n멈추고 돌아", "후진 1m", "직진 -1m", "직진 nanm", "직진 1도", "우회전 90m", "좌회전 181도", "직진 6m", "좌회전 0도", "직진 1m\n"*21, "직진 5m\n"*4]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_sequence(text)
        with self.assertRaises(ValueError):
            self.s.start_sequence("직진 1m\n오타", 5, True, self.clock())
        self.step(1)
        self.assertFalse(any(c.startswith("V ") for c in self.ser.commands))

    def test_sequence_full_order_stop_gaps_and_csv(self):
        self.s.start_sequence("직진 0.1m, 우회전 45도, 직진 0.1m, 좌회전 30도", 5, True, self.clock())
        self.step(7)
        self.assertFalse(self.s.sequence_active)
        self.assertIn("전체 순서 완료", self.s.sequence_note)
        self.assertEqual([r["direction"] for r in self.s.records], ["w", "d", "w", "a"])
        self.assertEqual([r["sequence_step"] for r in self.s.records], [1,2,3,4])
        self.assertTrue(all(r["complete"] and r["stop_ack"] for r in self.s.records))
        commands = [c for c in self.ser.commands if c != "ENC"]
        groups = []
        for c in commands:
            if not groups or c != groups[-1]:
                groups.append(c)
        self.assertEqual([c for c in groups if c.startswith("V ")], ["V 20 0 0", "V 0 0 20", "V 20 0 0", "V 0 0 -20"])
        for i, c in enumerate(groups):
            if c.startswith("V "):
                self.assertEqual(groups[i+1:i+3], ["ESTOP", "STOP"])
        before = len(self.ser.commands)
        self.step(1)
        self.assertFalse(any(c.startswith("V ") for c in self.ser.commands[before:]))
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory)/"sequence.csv"
            export_rotation_records(self.s.records, path)
            with path.open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(rows[0]["방향"], "직진")
            self.assertEqual(rows[0]["요청거리m_실측아님"], "0.1")
            self.assertEqual(rows[0]["설정시간초"], "0.5")

    def test_lateral_seconds_parser_and_limits(self):
        plans = parse_sequence("왼쪽 평행 0.5초 → 오른쪽 평행 2.75초")
        self.assertEqual([p.duration for p in plans], [.5,2.75])
        self.assertEqual([p.direction for p in plans], ["z","c"])
        self.assertTrue(all(p.metres is None for p in plans))
        self.assertIn("오른쪽 평행",describe_plan(plans[1]))
        for text in ("왼쪽 평행 0초","왼쪽 평행 0.49초","오른쪽 평행 60.1초",
                     "왼쪽 평행 1m","오른쪽 평행 90도","왼쪽 평행 -1초","왼쪽 평행 nan초",
                     "오른쪽 평행 60초\n"*3):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_sequence(text)
        for direction, seconds in (("w",1),("z",float("inf")),("c",float("nan"))):
            with self.assertRaises(ValueError):
                LateralPlan(direction,seconds)
        with self.assertRaises(ValueError):
            self.s.start_sequence("왼쪽 평행 1초 → 오타",5,True,self.clock())
        self.assertFalse(any(c.startswith("V ") for c in self.ser.commands))

    def test_mixed_lateral_sequence_deadlines_stop_gaps_and_csv(self):
        self.s.start_sequence("직진 0.1m, 왼쪽 평행 0.5초, 우회전 45도, 오른쪽 평행 0.75초",5,True,self.clock())
        self.step(8)
        self.assertFalse(self.s.sequence_active)
        self.assertEqual([r["direction"] for r in self.s.records],["w","z","d","c"])
        for row, duration in zip(self.s.records,(.5,.5,1,.75)):
            self.assertAlmostEqual(row["seconds"],duration,delta=.03)
            self.assertTrue(row["complete"] and row["stop_ack"])
        groups=[]
        for command in self.ser.commands:
            if command!="ENC" and (not groups or groups[-1]!=command): groups.append(command)
        self.assertEqual([c for c in groups if c.startswith("V ")],["V 20 0 0","V 0 -20 0","V 0 0 20","V 0 20 0"])
        for i,c in enumerate(groups):
            if c.startswith("V "): self.assertEqual(groups[i+1:i+3],["ESTOP","STOP"])
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path=Path(directory)/"lateral.csv"
            export_rotation_records(self.s.records,path)
            with path.open(encoding="utf-8-sig",newline="") as stream: rows=list(csv.DictReader(stream))
            self.assertEqual(rows[1]["방향"],"왼쪽 평행")
            self.assertEqual(rows[3]["설정시간초"],"0.75")
            self.assertEqual(rows[1]["요청거리m_실측아님"],"")
            self.assertEqual(rows[3]["요청각도_실측아님"],"")

    def test_lateral_interruption_never_starts_remaining_step(self):
        for keys,focused in (({"space"},True),(set(),False)):
            self.step(1)
            self.ser.commands.clear()
            self.s.start_sequence("왼쪽 평행 2초, 오른쪽 평행 1초",5,True,self.clock())
            self.step(.2)
            self.step(keys=keys,focused=focused)
            self.assertEqual(self.ser.vector,(0,0,0))
            self.step(4)
            self.assertFalse(self.s.sequence_active)
            self.assertNotIn("V 0 20 0",self.ser.commands)

    def test_lateral_stale_input_stops_and_wrong_axis_rejected(self):
        self.s.start_sequence("오른쪽 평행 2초, 직진 1m",5,True,self.clock())
        self.step(.2)
        with self.assertRaises(motor.TestFault):
            self.s.exchange("V 0 0 20",lambda s:True)
        with self.assertRaises(motor.TestFault):
            self.s.tick(set(),True,self.clock()-1)
        self.s.fail("입력 갱신 중단 모의")
        self.assertEqual(self.ser.vector,(0,0,0))
        self.assertFalse(self.s.sequence_active)
        self.assertNotIn("V 20 0 0",self.ser.commands)

    def test_sequence_cancel_in_stop_gap(self):
        self.s.start_sequence("직진 0.1m, 우회전 90도", 5, True, self.clock())
        self.step(.6)
        self.assertFalse(self.s.active)
        self.assertTrue(self.s.sequence_active)
        self.assertEqual(self.s.state, "stopping")
        with self.assertRaises(ValueError):
            self.s.start_rotation("a",45,True,self.clock())
        self.s.stop_plan()
        self.step(4)
        self.assertFalse(self.s.sequence_active)
        self.assertNotIn("V 0 0 20", self.ser.commands)

    def test_sequence_interruptions_cancel_remaining(self):
        for keys, focused in [({"space"},True), (set(),False)]:
            self.step(1)
            self.s.start_sequence("직진 1m, 우회전 90도", 5, True, self.clock())
            self.step(.2)
            self.step(keys=keys, focused=focused)
            self.assertFalse(self.s.sequence_active)
            self.step(3)
            self.assertNotIn("V 0 0 20", self.ser.commands)

    def test_sequence_disconnect_and_stale_input(self):
        self.s.start_sequence("직진 1m, 우회전 90도", 5, True, self.clock())
        self.step(.2)
        with self.assertRaises(motor.TestFault):
            self.s.tick(set(), True, self.clock()-1)
        self.s.fail("입력 갱신 중단 모의")
        self.assertFalse(self.s.sequence_active)
        self.assertEqual(self.ser.vector, (0,0,0))
        self.assertNotIn("V 0 0 20", self.ser.commands)

    def test_sequence_waits_for_encoder_stop(self):
        self.s.start_sequence("직진 0.1m, 우회전 90도", 5, True, self.clock())
        self.step(.6)
        original = self.ser.write
        def encoder_moves(data):
            if data == b"ENC\n":
                self.ser.vector = (20,0,0)
            return original(data)
        self.ser.write = encoder_moves
        with self.assertRaises(motor.TestFault):
            self.step(3)
        self.s.fail("정지 응답 불일치 모의")
        self.assertFalse(self.s.sequence_active)
        self.assertNotIn("V 0 0 20", self.ser.commands)

    def test_bad_values(self):
        for m, t in [(0, 8), (-1, 8), (6, 8), (1, 0), (1, 31), (5, 30), (.1, .5), (float("nan"), 8), (1, float("inf"))]:
            with self.subTest(m=m, t=t), self.assertRaises(ValueError):
                Plan(m, t)

    def test_connect_does_not_move(self):
        self.step(1)
        self.assertFalse(any(c.startswith("V ") for c in self.ser.commands))

    def test_start_20_percent_only(self):
        self.start()
        self.step(.25)
        motion = [c for c in self.ser.commands if c.startswith("V ")]
        self.assertGreater(len(motion), 1)
        self.assertEqual(set(motion), {"V 20 0 0"})

    def test_deadline_and_no_repeat(self):
        self.start()
        self.step(.475)
        self.assertTrue(self.s.active)
        self.step(.05)
        self.assertFalse(self.s.active)
        self.assertIn("설정 시간 종료", self.s.result)
        self.assertEqual(self.ser.vector, (0, 0, 0))
        self.assertEqual([c for c in self.ser.commands if c != "ENC"][-2:], ["ESTOP", "STOP"])
        count = self.ser.commands.count("V 20 0 0")
        self.step(2)
        self.assertEqual(count, self.ser.commands.count("V 20 0 0"))

    def test_progress(self):
        self.start(seconds_per_m=2)
        self.step(.5)
        s = self.s.snapshot()
        self.assertAlmostEqual(s["elapsed"], .5)
        self.assertAlmostEqual(s["remaining"], 1.5)

    def test_focus_loss(self):
        self.start()
        self.step(focused=False)
        self.assertFalse(self.s.active)
        self.assertEqual(self.ser.vector, (0, 0, 0))
        self.step(1)
        self.assertNotEqual(self.s.state, "moving")

    def test_any_keyboard_input_stops(self):
        for key in ["space", "w", "esc"]:
            self.step(1)
            self.start()
            self.step(keys={key})
            self.assertFalse(self.s.active)
            self.assertEqual(self.ser.vector, (0, 0, 0))

    def test_stop_preserves_elapsed(self):
        self.start(seconds_per_m=3)
        self.step(.2)
        self.s.stop_plan()
        elapsed = self.s.snapshot()["elapsed"]
        self.step(1)
        self.assertEqual(elapsed, self.s.snapshot()["elapsed"])

    def test_duplicate_rejected(self):
        self.start()
        with self.assertRaises(ValueError):
            self.s.start_plan(Plan(1, 1), True, self.clock())

    def test_speed_mismatch_rejected(self):
        self.s.speed = 40
        with self.assertRaises(ValueError):
            self.start()

    def test_unfocused_or_stale_start_rejected(self):
        for focused, stamp in [(False, self.clock()), (True, self.clock()-1)]:
            with self.assertRaises(ValueError):
                self.s.start_plan(Plan(1, 1), focused, stamp)
        self.assertFalse(any(c.startswith("V ") for c in self.ser.commands))

    def test_not_connected_start_rejected(self):
        self.s.disconnect()
        with self.assertRaises(ValueError):
            self.start()

    def test_heartbeat_stops_through_worker_fail_path(self):
        self.start(seconds_per_m=3)
        with self.assertRaises(motor.TestFault):
            self.s.tick(set(), True, self.clock()-1)
        self.s.fail("heartbeat")
        self.assertFalse(self.s.active)
        self.assertTrue(self.ser.closed)
        self.assertEqual(self.ser.vector, (0, 0, 0))

    def test_serial_failure_does_not_resume(self):
        self.start()
        original = self.ser.write
        def fail(data):
            if data.startswith(b"V "):
                raise OSError("송신 실패 모의")
            return original(data)
        self.ser.write = fail
        with self.assertRaises(OSError):
            self.step(.2)
        self.s.fail("송신 실패 모의")
        self.assertFalse(self.s.active)
        self.assertTrue(self.ser.closed)

    def test_deadline_checked_after_slow_encoder_request(self):
        self.start()
        original = self.ser.write
        def delay(data):
            if data == b"ENC\n":
                self.clock.now += .3
            return original(data)
        self.ser.write = delay
        self.step(.2)
        self.assertFalse(self.s.active)
        self.assertEqual(self.ser.vector, (0, 0, 0))

    def test_manual_keys_never_start_motion(self):
        self.step(.5, keys={"w"})
        self.assertFalse(any(c.startswith("V ") for c in self.ser.commands))

    def test_pending_start_discarded_by_stop(self):
        w = TimedWorker(preview_only=True)
        w.request("connect", "preview")
        w.request("start", 1, .5)
        w.request("stop")
        w.start()
        try:
            time.sleep(.1)
            self.assertIsNone(w.session.link)
            self.assertFalse(w.session.active)
            self.assertTrue(w.actions.empty())
        finally:
            w.quit.set()
            w.join(1)

    def test_preview_worker_blocks_real(self):
        w = TimedWorker(preview_only=True)
        w.request("connect", "real", "COM7", True)
        w.start()
        try:
            time.sleep(.1)
            self.assertEqual(w.get_status()["state"], "fault")
            self.assertIsNone(w.session.link)
        finally:
            w.quit.set()
            w.join(1)

    def test_rotation_both_directions_release_records(self):
        for direction, command in [("a", "V 0 0 -20"), ("d", "V 0 0 20")]:
            self.step(1)
            self.s.start_hold(direction, True, self.clock())
            self.step(.4, keys={"hold:"+direction})
            self.assertIn(command, self.ser.commands)
            self.assertTrue(self.s.active)
            self.step()
            elapsed = self.s.snapshot()["elapsed"]
            self.assertEqual(self.ser.vector, (0, 0, 0))
            self.step(1)
            row = self.s.records[-1]
            self.assertAlmostEqual(row["seconds"], elapsed)
            self.assertTrue(row["stop_ack"])
            self.assertTrue(row["complete"])
            self.assertEqual(len(row["delta"]), 4)
            self.assertTrue(any(row["delta"]))
            self.assertEqual(row["direction"], direction)

    def test_presets_both_angles_both_directions(self):
        for direction in ("a", "d"):
            for angle in (45, 90):
                with self.subTest(direction=direction, angle=angle):
                    self.step(1)
                    self.s.start_rotation(direction, angle, True, self.clock())
                    self.step(.025)
                    self.assertTrue(self.s.active)
                    self.assertEqual(self.s.snapshot()["duration"], angle/45)
                    self.assertIsNone(self.s.snapshot()["metres"])
                    self.assertEqual(self.ser.vector, (0, 0, -20 if direction == "a" else 20))
                    self.step(angle/45-.025)
                    self.assertTrue(self.s.active)
                    self.step(.05)
                    self.assertFalse(self.s.active)
                    self.assertEqual(self.ser.vector, (0, 0, 0))
                    self.step(1)
                    row = self.s.records[-1]
                    self.assertEqual(row["target_angle"], angle)
                    self.assertAlmostEqual(row["seconds"], angle/45, delta=.03)
                    self.assertTrue(row["complete"])
                    self.assertIn("실제 각도 미측정", row["reason"])
                    count = sum(c.startswith("V ") for c in self.ser.commands)
                    self.step(1)
                    self.assertEqual(count, sum(c.startswith("V ") for c in self.ser.commands))

    def test_presets_validation_and_duplicate(self):
        for direction, angle in [("w",45),("a",0),("d",180),("d",float("nan"))]:
            with self.assertRaises(ValueError):
                RotationPlan(direction, angle)
        self.s.start_rotation("a",90,True,self.clock())
        with self.assertRaises(ValueError):
            self.s.start_rotation("d",45,True,self.clock())

    def test_preset_interruptions(self):
        for keys, focused in [({"space"},True),(set(),False)]:
            self.step(1)
            self.s.start_rotation("d",90,True,self.clock())
            self.step(.2)
            self.step(keys=keys, focused=focused)
            self.assertFalse(self.s.active)
            self.assertEqual(self.ser.vector,(0,0,0))
            self.assertLess(self.s.snapshot()["elapsed"],2)

    def test_preset_slow_enc_never_sends_after_deadline(self):
        self.s.start_rotation("a",45,True,self.clock())
        self.step(.025)
        original = self.ser.write
        def delay(data):
            if data == b"ENC\n":
                self.clock.now += 1.1
            return original(data)
        self.ser.write = delay
        with self.assertRaises(motor.TestFault):
            self.step(.1)
        self.s.fail("모의 통신 지연 · 작업 스레드 오류 종료 경로")
        self.assertFalse(self.s.active)
        self.assertEqual(self.ser.vector,(0,0,0))
        self.assertEqual(self.ser.commands.count("V 0 0 -20"),1)

    def test_rotation_focus_loss_no_resume(self):
        self.s.start_hold("a", True, self.clock())
        self.step(.2, keys={"hold:a"})
        self.step(keys={"hold:a"}, focused=False)
        before = self.ser.commands.count("V 0 0 -20")
        self.step(1, keys={"hold:a"})
        self.assertEqual(before, self.ser.commands.count("V 0 0 -20"))
        self.assertEqual(self.ser.vector, (0, 0, 0))

    def test_rotation_conflict_stops(self):
        self.s.start_hold("d", True, self.clock())
        self.step(.2, keys={"hold:d"})
        self.step(keys={"hold:a", "hold:d"})
        self.assertFalse(self.s.active)
        self.assertEqual(self.ser.vector, (0, 0, 0))

    def test_rotation_stop_failure_not_complete(self):
        self.s.start_hold("d", True, self.clock())
        self.step(.2, keys={"hold:d"})
        self.s.fail("통신 끊김 모의")
        self.assertFalse(self.s.records[-1]["complete"])
        self.assertIsNone(self.s.records[-1]["delta"])
        self.assertFalse(self.s.active)

    def test_rotation_deadline(self):
        self.s.start_hold("a", True, self.clock())
        self.step(60.1, keys={"hold:a"})
        self.assertFalse(self.s.active)
        self.assertEqual(self.ser.vector, (0, 0, 0))
        self.assertLessEqual(self.s.snapshot()["elapsed"], 60.05)

    def test_rotation_release_before_first_tick_never_moves(self):
        self.s.start_hold("a", True, self.clock())
        self.step()
        self.assertFalse(any(c.startswith("V ") for c in self.ser.commands))
        self.assertEqual(self.s.records, [])

    def test_rotation_csv_roundtrip(self):
        self.s.start_hold("a", True, self.clock())
        self.step(.2, keys={"hold:a"})
        self.step(1)
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            path = Path(directory)/"rotation.csv"
            export_rotation_records(self.s.records, path)
            self.assertTrue(path.read_bytes().startswith(b"\xef\xbb\xbf"))
            with path.open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(rows[0]["방향"], "좌회전")
            self.assertEqual(rows[0]["모드"], "모의")
            self.assertEqual(rows[0]["출력%"], "20")
            self.assertIn("실물 회전각", rows[0]["측정기준"])

    def test_worker_released_queued_hold_never_moves(self):
        w = TimedWorker(preview_only=True)
        w.session = self.s
        w.publish(set(), True)
        w.request("hold", "a")
        w.start()
        try:
            time.sleep(.1)
            self.assertFalse(any(c.startswith("V ") for c in self.ser.commands))
        finally:
            w.quit.set()
            w.join(1)

    @unittest.skipUnless(sys.platform == "win32", "Windows Tk UI 검사")
    def test_tk_rotation_callbacks_and_autosave(self):
        import tkinter as tk
        from timed_app import TimedApp
        root = tk.Tk()
        root.withdraw()
        app = TimedApp(root, True)
        class Input:
            down = False
            def GetForegroundWindow(self):
                return app.hwnd
            def GetAsyncKeyState(self, key):
                return 0x8000 if key == 1 and self.down else 0
        fake = Input()
        app.user32 = fake
        def pump(seconds):
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                root.update()
                time.sleep(.01)
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            app.log_path = Path(directory)/"preview.csv"
            try:
                app.connect()
                pump(1)
                for direction in ("a", "d"):
                    fake.down = True
                    app.press_hold(direction)
                    pump(.35)
                    self.assertTrue(app.worker.get_status()["timed_active"])
                    fake.down = False
                    app.release_hold()
                    pump(.8)
                self.assertEqual(len(app.worker.get_status()["records"]), 2)
                self.assertIn("2건", app.record_note.get())
                self.assertIn("자동 저장", app.log_note.get())
                self.assertTrue(app.log_path.exists())
                self.assertIn("우회전", app.log_path.read_text(encoding="utf-8-sig"))
                for button, angle in zip(app.rotation_buttons, (45,45,90,90)):
                    button.invoke()
                    pump(.2)
                    self.assertTrue(app.worker.get_status()["timed_active"])
                    pump(angle/45+.8)
                    self.assertFalse(app.worker.get_status()["timed_active"])
                    self.assertEqual(app.worker.get_status()["records"][-1]["target_angle"],angle)
                self.assertEqual(len(app.worker.get_status()["records"]),6)
                self.assertIn("요청각도_실측아님",app.log_path.read_text(encoding="utf-8-sig"))
                app.sequence_text.delete("1.0", "end")
                app.sequence_text.insert("1.0", "직진 0.1m\n우회전 45도")
                app.calibration.set("5")
                pump(.1)
                app.validate_button.invoke()
                pump(.1)
                self.assertIsNotNone(app.validated_sequence)
                app.sequence_button.invoke()
                pump(.2)
                self.assertTrue(app.worker.get_status()["sequence_active"],app.worker.get_status())
                self.assertEqual(str(app.sequence_text.cget("state")), "disabled")
                self.assertEqual(str(app.start_button.cget("state")), "disabled")
                pump(3)
                self.assertFalse(app.worker.get_status()["sequence_active"])
                self.assertEqual(len(app.worker.get_status()["records"]),8)
                self.assertIn("전체 순서 완료", app.note.get())
                app.calibration.set("6")
                pump(.1)
                self.assertIsNone(app.validated_sequence)
                self.assertEqual(str(app.sequence_button.cget("state")), "disabled")
            finally:
                app.close()


class MainIntegrationTests(unittest.TestCase):
    def test_lateral_editor_buttons_execute_with_cad_visible(self):
        import tkinter as tk
        from app import App
        root=tk.Tk()
        root.withdraw()
        app=App(root,True)
        class Input:
            def GetForegroundWindow(self): return app.hwnd
            def GetAsyncKeyState(self,key): return 0
        app.user32=Input()
        def pump(seconds):
            deadline=time.monotonic()+seconds
            while time.monotonic()<deadline:
                root.update()
                time.sleep(.01)
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            app.sequence_log_path=Path(directory)/"preview.csv"
            try:
                pump(.1)
                self.assertIsNotNone(app.cad_image)
                app.draw_cad()  # 숨긴 Tk 창에서는 Configure 이벤트가 생략될 수 있습니다.
                self.assertIsNotNone(app.cad_photo)
                self.assertGreater(app.cad_image.width,100)
                editor=app.route_editor
                for kind in ("왼쪽 평행","오른쪽 평행"):
                    radio=next(w for w in editor.widgets if isinstance(w,tk.Radiobutton) and w.cget("text")==kind)
                    radio.invoke()
                    self.assertIn("초",editor.unit.cget("text"))
                    editor.amount.set("0.5")
                    editor.add_button.invoke()
                self.assertEqual(editor.items,["왼쪽 평행 0.5초","오른쪽 평행 0.5초"])
                editor.validate_button.invoke()
                app.control_mode.set("sequence")
                app.select_control()
                pump(.1)
                app.connect()
                pump(1)
                self.assertEqual(str(app.cad_expand.cget("state")),"disabled",app.worker.get_status())
                editor.start_button.invoke()
                pump(.2)
                self.assertTrue(app.worker.get_status()["sequence_active"])
                pump(3)
                rows=app.worker.get_status()["records"]
                self.assertEqual([r["direction"] for r in rows],["z","c"])
                self.assertTrue(all(r["complete"] for r in rows))
                app.worker.request("disconnect")
                pump(.2)
                self.assertIn("왼쪽 평행",app.sequence_log_path.read_text(encoding="utf-8-sig"))
            finally:
                app.travel_log.saved_count=app.travel_log.count
                app.close()

    def test_manual_trace_preserved_and_connected_mode_change_blocked(self):
        from driver_adapter import Session
        traces = []
        for cls in (Session,MainSession):
            clock, ser = Clock(), PreviewSerial()
            session = cls(clock)
            session.connect("preview",factory=lambda:ser)
            for key,steps in [(None,40),("w",8),(None,40),("a",8),(None,40)]:
                for _ in range(steps):
                    clock.now += .025
                    session.tick({key} if key else set(),True,clock())
            if isinstance(session,MainSession):
                with self.assertRaises(ValueError):
                    session.select_control("sequence")
                with self.assertRaises(ValueError):
                    session.start_sequence("직진 1m",5,True,clock())
            traces.append(ser.commands[:])
            session.disconnect()
        self.assertEqual(traces[0],traces[1])

    def test_sequence_mode_ignores_manual_movement_and_locks_speed(self):
        clock,ser = Clock(),PreviewSerial()
        s = MainSession(clock)
        s.select_control("sequence")
        s.connect("preview",factory=lambda:ser)
        try:
            for _ in range(40):
                clock.now += .025
                s.tick(set(),True,clock())
            for _ in range(8):
                clock.now += .025
                s.tick({"w"},True,clock())
            self.assertFalse(any(c.startswith("V ") for c in ser.commands))
            with self.assertRaises(ValueError):
                s.change_speed(5)
            self.assertEqual(s.speed,20)
        finally:
            s.disconnect()

    def test_recorder_roundtrip_resize_and_stop(self):
        from screen_recording import WindowRecorder
        from PIL import Image
        import cv2
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            recorder = WindowRecorder()
            counter = [0]
            def capture():
                counter[0] += 1
                return Image.new("RGB",(320,200) if counter[0]%2 else (200,320),(50,120,200))
            self.assertTrue(recorder.start(0,directory,capture))
            self.assertFalse(recorder.start(0,directory,capture))
            deadline=time.monotonic()+5
            while recorder.snapshot()["frames"]<3 and time.monotonic()<deadline:
                time.sleep(.05)
            recorder.stop()
            recorder.thread.join(3)
            status=recorder.snapshot()
            self.assertFalse(status["active"])
            self.assertIn("저장 완료",status["message"])
            self.assertGreaterEqual(status["frames"],3)
            video=cv2.VideoCapture(status["path"])
            try:
                ok,frame=video.read()
                self.assertTrue(ok)
                self.assertEqual(frame.shape[:2],(200,320))
                self.assertGreater(frame.mean(),0)
            finally:
                video.release()

    def test_recorder_capture_failure_reported(self):
        from screen_recording import WindowRecorder
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            recorder=WindowRecorder()
            def fail():
                raise OSError("모의 캡처 실패")
            recorder.start(0,directory,fail)
            recorder.thread.join(5)
            status=recorder.snapshot()
            self.assertFalse(status["active"])
            self.assertIsNone(status["path"])
            self.assertIn("모의 캡처 실패",status["message"])

    @unittest.skipUnless(sys.platform == "win32", "Windows 메인 UI 검사")
    def test_main_buttons_route_execution_cancel_and_csv(self):
        import tkinter as tk
        from app import App
        root=tk.Tk()
        root.withdraw()
        app=App(root,True)
        class Input:
            def GetForegroundWindow(self): return app.hwnd
            def GetAsyncKeyState(self,key): return 0
        app.user32=Input()
        def pump(seconds):
            deadline=time.monotonic()+seconds
            while time.monotonic()<deadline:
                root.update()
                time.sleep(.01)
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as directory:
            app.sequence_log_path=Path(directory)/"route.csv"
            try:
                editor=app.route_editor
                editor.calibration.set("5")
                editor.amount.set("0.1")
                editor.add_button.invoke()
                editor.operation.set("우회전")
                editor.kind_changed()
                editor.amount.set("45")
                editor.add_button.invoke()
                self.assertEqual(editor.items,["직진 0.1m","우회전 45도"])
                editor.move(-1)
                self.assertEqual(editor.items[0],"우회전 45도")
                editor.move(1)
                editor.amount.set("1800")
                editor.add_button.invoke()
                self.assertEqual(len(editor.items),2)
                editor.validate_button.invoke()
                self.assertIsNotNone(editor.validated)
                self.assertEqual(str(editor.start_button.cget("state")),"disabled")
                app.control_mode.set("sequence")
                app.select_control()
                pump(.1)
                app.connect()
                pump(1)
                self.assertEqual(app.worker.get_status()["control_mode"],"sequence")
                self.assertEqual(str(app.move_buttons[0].cget("state")),"disabled")
                self.assertEqual(str(app.control_radios[0].cget("state")),"disabled",app.worker.get_status())
                editor.start_button.invoke()
                pump(.2)
                self.assertTrue(app.worker.get_status()["sequence_active"],app.worker.get_status())
                self.assertEqual(str(editor.add_button.cget("state")),"disabled")
                editor.clear()
                self.assertEqual(len(editor.items),2)
                pump(3)
                self.assertFalse(app.worker.get_status()["sequence_active"])
                self.assertEqual(len(app.worker.get_status()["records"]),2)
                editor.start_button.invoke()
                pump(.2)
                app.stop()
                pump(1)
                self.assertFalse(app.worker.get_status()["sequence_active"])
                self.assertEqual(len(app.worker.get_status()["records"]),3)
                app.worker.request("disconnect")
                pump(.3)
                self.assertTrue(app.sequence_log_path.exists())
                self.assertEqual(app.sequence_saved,3)
                editor.listbox.selection_clear(0,"end")
                editor.listbox.selection_set(0)
                editor.delete()
                self.assertEqual(editor.items,["우회전 45도"])
                editor.clear()
                self.assertEqual(editor.items,[])
                app.control_mode.set("manual")
                app.select_control()
                pump(.1)
                self.assertEqual(app.worker.get_status()["control_mode"],"manual")
            finally:
                app.travel_log.saved_count=app.travel_log.count
                app.close()


if __name__ == "__main__":
    unittest.main()
