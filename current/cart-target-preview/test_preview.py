"""합성 영상/가짜 캡처로 검증. 실제 카메라·COM 포트를 열지 않습니다."""
import ast
import hashlib
from pathlib import Path
import time
import tkinter as tk
import unittest
from unittest.mock import patch

import numpy as np
from target_core import Alignment, Detection, demo_frame, detect_color, pick_color, pick_detection, left_camera_guidance
from preview import CameraWorker, PreviewApp, DEFAULT_WEIGHTS, box_caption, configure_capture, capture_caption, CAPTURE_PROFILES, DEFAULT_PROFILE


class CoreTests(unittest.TestCase):
    def test_capture_settings_and_actual_resolution_reporting(self):
        from unittest.mock import Mock
        import cv2
        cap = Mock()
        configure_capture(cap, DEFAULT_PROFILE)
        calls = cap.set.call_args_list
        self.assertEqual(calls[0].args[0], cv2.CAP_PROP_FOURCC)
        self.assertIn(unittest.mock.call(cv2.CAP_PROP_FRAME_WIDTH, 1920), calls)
        self.assertIn(unittest.mock.call(cv2.CAP_PROP_FRAME_HEIGHT, 1080), calls)
        self.assertIn("요청과 다름", capture_caption(demo_frame(), DEFAULT_PROFILE))
        self.assertIn("카메라 성능 아님", capture_caption(demo_frame(), DEFAULT_PROFILE, True))
        self.assertNotIn("요청과 다름", capture_caption(np.zeros((1080, 1920, 3), dtype=np.uint8), DEFAULT_PROFILE))

    def test_left_camera_forward_backward_and_mirror(self):
        for x, mirrored, expected in ((450, False, "전진"), (150, False, "후진"),
                                      (450, True, "후진"), (150, True, "전진")):
            with self.subTest(x=x, mirrored=mirrored):
                d = Detection((x-20, 120, x+20, 160), "box")
                position, advice = left_camera_guidance([d], "box", 640, 480, 1, 1,
                                                        confirmed=True, mirrored=mirrored)
                self.assertIn(expected, advice)
                self.assertIn("위", position)

    def test_guidance_requires_mount_confirmation_and_valid_target(self):
        d = Detection((400, 200, 440, 260), "box")
        self.assertIn("보류", left_camera_guidance([d], "box", 640, 480, 1, 1)[1])
        for targets, selected, now, frozen in (([], "box", 1, False), ([d, d], "box", 1, False),
                                               ([d], None, 1, False), ([d], "box", 2, False),
                                               ([d], "box", 1, True)):
            self.assertIn("중지", left_camera_guidance(targets, selected, 640, 480, 1, now,
                                                      frozen=frozen, confirmed=True)[1])

    def test_guidance_center_does_not_mean_docked_or_vertical_motion(self):
        d = Detection((300, 350, 340, 390), "box")
        position, advice = left_camera_guidance([d], "box", 640, 480, 1, 1, confirmed=True)
        self.assertIn("아래", position)
        self.assertIn("전후 보정 불필요", advice)
        self.assertIn("주차 완료 판정 아님", advice)

    def test_yolo_caption_shows_confidence_and_signed_error(self):
        d = Detection((420, 200, 460, 260), "red_box", .91)
        self.assertEqual(box_caption(d, 640, .5), "red_box 91% | X +120px")
        self.assertIn("X -40px", box_caption(d, 640, .75))

    def test_original_files_unchanged(self):
        base = Path(__file__).resolve().parent.parent
        expected = {
            "ROBOT-motor-review-928b2a8/urt/mecanum_motor/src/main.cpp": "6C95886A741D153604B23B092C5A1DFBA6D75294FA6BA2F2B7FEF690B3DA175C",
            "ROBOT-motor-review-928b2a8/common/manual_motor_test.py": "66F3E3A32E5965FB09B086869F5C41C495DB0148EE8635C0BCCD40FD0FAE1632",
            "cart-manual-ui/driver_adapter.py": "AA6C2FAE299025609A4E1923C45F08006A1AA0A00F62E6E9850AFB4E24029689",
            # 2026-10-15 배포 스냅샷: 사용자가 요청한 6방향/출력 UI 갱신을 반영한 기준입니다.
            "cart-manual-ui/app.py": "5259340BD270657221876B14D7BE7B87858E630962DB9D3F564F14B8116F1B5F",
        }
        for path, digest in expected.items():
            with self.subTest(path=path):
                self.assertEqual(hashlib.sha256((base/path).read_bytes()).hexdigest().upper(), digest)

    def test_no_motor_or_serial_imports(self):
        forbidden = {"serial", "driver_adapter", "drivers", "manual_motor_test", "socket", "subprocess"}
        for file in ("preview.py", "target_core.py"):
            tree = ast.parse(Path(__file__).with_name(file).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    self.assertFalse({n.name.split('.')[0] for n in node.names} & forbidden)
                elif isinstance(node, ast.ImportFrom):
                    self.assertNotIn((node.module or '').split('.')[0], forbidden)

    def test_original_color_and_repeated_detection(self):
        self.assertEqual(pick_color(demo_frame(100), 100, 240), "red")
        self.assertIsNone(pick_color(demo_frame(), 5, 5))
        self.assertIsNone(pick_color(demo_frame(), -1, 5))
        for x in (100, 320, 500):
            targets = detect_color(demo_frame(x), "red")
            self.assertEqual(len(targets), 1)
            self.assertLess(abs(targets[0].center[0]-x), 1)

    def test_lost_and_ambiguous(self):
        a = Alignment()
        b = Detection((200, 200, 250, 250), "red")
        self.assertEqual(a.update([], "red", 640, 480, 1, 1, 1)[0], "LOST")
        self.assertEqual(a.update([b, b], "red", 640, 480, 1, 1, 1)[0], "AMBIGUOUS")

    def test_sides_and_stability(self):
        a = Alignment()
        for seq, x, expected in ((1, 100, "LEFT"), (2, 500, "RIGHT")):
            self.assertEqual(a.update(detect_color(demo_frame(x), "red"), "red", 640, 480, seq, seq, seq)[0], expected)
        targets = detect_color(demo_frame(320), "red")
        for i in range(7):
            code, _ = a.update(targets, "red", 640, 480, 10+i, 3+i*.1, 3+i*.1)
        self.assertEqual(code, "CENTERED")

    def test_stale_duplicate_frozen_reset(self):
        a = Alignment()
        targets = detect_color(demo_frame(320), "red")
        self.assertEqual(a.update(targets, "red", 640, 480, 1, 1, 1)[0], "SETTLING")
        self.assertEqual(a.update(targets, "red", 640, 480, 1, 1, 1.2)[0], "WAIT")
        self.assertEqual(a.update(targets, "red", 640, 480, 1, 1, 2)[0], "STALE")
        self.assertEqual(a.update(targets, "red", 640, 480, 2, 2, 2, frozen=True)[0], "FROZEN")
        self.assertEqual(a.update(targets, "red", 640, 480, 3, 3, 3)[0], "SETTLING")

    def test_goal_and_invalid(self):
        a = Alignment()
        targets = detect_color(demo_frame(100), "red")
        code, delta = a.update(targets, "red", 640, 480, 1, 1, 1, target_x=100/640)
        self.assertEqual(code, "SETTLING")
        self.assertLess(abs(delta[0]), 1)
        self.assertEqual(a.update(targets, "red", 0, 480, 1, 1, 1)[0], "INVALID")
        self.assertEqual(a.update(targets, "red", 640, 480, 1, 1, 1, target_x=float('nan'))[0], "INVALID")

    def test_clipped_target_and_yolo_selection(self):
        self.assertEqual(detect_color(demo_frame(10), "red"), [])
        d = Detection((10, 10, 50, 50), "box")
        self.assertEqual(pick_detection([d], 30, 30), d)
        self.assertIsNone(pick_detection([d, d], 30, 30))
        self.assertIsNone(pick_detection([d], 70, 70))


class WorkerTests(unittest.TestCase):
    def test_demo_never_opens_camera(self):
        with patch("preview.cv2.VideoCapture", side_effect=AssertionError("no device")):
            worker = CameraWorker(0, "DSHOW", "색상 클릭", demo=True)
            worker.select("red")
            worker.start()
            try:
                deadline = time.monotonic()+3
                while worker.snapshot()[0] is None and time.monotonic() < deadline:
                    time.sleep(.02)
                packet, error = worker.snapshot()
                self.assertFalse(error)
                self.assertIsNotNone(packet)
                self.assertEqual(len(packet[1]), 1)
            finally:
                worker.stop()
                worker.thread.join(2)
            self.assertFalse(worker.thread.is_alive())

    def test_model_missing_no_download_or_camera(self):
        with patch("preview.cv2.VideoCapture", side_effect=AssertionError("no device")):
            worker = CameraWorker(0, "DSHOW", "YOLO", "missing-local-model.pt")
            worker.start()
            worker.thread.join(3)
            self.assertIn("로컬 YOLO", worker.snapshot()[1])

    def test_capture_failure_releases(self):
        class FakeCapture:
            released = False
            def isOpened(self): return True
            def set(self, *args): pass
            def read(self): return False, None
            def release(self): self.released = True
        cap = FakeCapture()
        with patch("preview.cv2.VideoCapture", return_value=cap):
            worker = CameraWorker(0, "DSHOW", "색상 클릭")
            worker.start()
            worker.thread.join(3)
        self.assertIn("수신 실패", worker.snapshot()[1])
        self.assertTrue(cap.released)


class UITests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.app = PreviewApp(self.root)
        self.root.update()

    def tearDown(self):
        worker = self.app.worker
        self.app.close()
        if worker:
            worker.thread.join(2)

    def pump(self, seconds=.3):
        until = time.monotonic()+seconds
        while time.monotonic() < until:
            self.root.update()
            time.sleep(.01)

    def test_invalid_camera_index(self):
        self.app.index.set("bad")
        self.app.start()
        self.assertIsNone(self.app.worker)
        self.assertIn("정수", self.app.status.get())

    def test_quality_selection_and_large_view_restore(self):
        self.assertEqual(self.app.profile.get(), DEFAULT_PROFILE)
        self.assertEqual(tuple(self.app.profile_box['values']), tuple(CAPTURE_PROFILES))
        self.app.profile.set("HD · 1280×720")
        with patch("preview.cv2.VideoCapture", side_effect=AssertionError("no device")):
            self.app.start(demo=True)
            self.pump(.2)
            self.assertEqual(self.app.worker.profile, "HD · 1280×720")
            self.assertEqual(str(self.app.profile_box['state']), 'disabled')
            self.assertIn("카메라 성능 아님", self.app.capture_text.get())
            self.app.large_button.invoke()
            self.pump(.1)
            self.assertTrue(self.app.large_view)
            self.assertFalse(self.app.model_row.winfo_ismapped())
            self.app.large_button.invoke()
            self.pump(.1)
            self.assertFalse(self.app.large_view)
            self.assertTrue(self.app.model_row.winfo_ismapped())
            self.app.stop()
            self.pump(.2)
            self.assertEqual(str(self.app.profile_box['state']), 'readonly')

    def test_full_hd_click_coordinates_and_full_frame_fit(self):
        worker = CameraWorker(0, "DSHOW", "YOLO")
        self.app.worker = worker
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        target = Detection((1550, 800, 1650, 900), "red_box", .95)
        self.app.packet = (frame, [target], 1, time.monotonic(), False)
        self.app.draw(frame, [target], False)
        ox, oy, scale, dw, dh = self.app.display_rect
        self.assertGreaterEqual(ox, 0)
        self.assertGreaterEqual(oy, 0)
        self.assertLessEqual(dw, self.app.canvas.winfo_width())
        self.assertLessEqual(dh, self.app.canvas.winfo_height())
        event = type("Event", (), {"x": ox+1600*scale, "y": oy+850*scale})()
        self.app.click(event)
        self.assertEqual(self.app.selected, "red_box")
        self.app.worker = None

    def test_guidance_controls_goal_independence_stale_and_stop(self):
        self.app.worker = CameraWorker(0, "DSHOW", "YOLO")
        frame = demo_frame(440)
        targets = [Detection((420, 200, 460, 260), "box")]
        self.app.selected = "box"
        self.app.packet = (frame, targets, 1, time.monotonic(), False)
        self.app.refresh_guidance()
        self.assertIn("보류", self.app.guidance_text.get())
        # 실제 체크버튼 이벤트로 장착 확인과 미러 설정을 검증합니다.
        checks = [child for row in self.app.canvas.master.winfo_children()
                  for child in row.winfo_children() if child.winfo_class() == "TCheckbutton"]
        checks[0].invoke()
        self.assertIn("전진", self.app.guidance_text.get())
        self.app.set_goal()
        self.app.refresh_guidance()
        self.assertIn("전진", self.app.guidance_text.get())  # 사용자 목표선이 아닌 화면 중앙
        checks[1].invoke()
        self.assertIn("후진", self.app.guidance_text.get())
        self.app.packet = (frame, targets, 1, time.monotonic()-1, False)
        self.app.refresh_guidance()
        self.assertIn("중지", self.app.guidance_text.get())
        self.app.stop()
        self.assertNotIn("후진", self.app.guidance_text.get())
        self.app.worker = None

    def test_default_yolo_model_and_selection(self):
        self.assertEqual(self.app.mode.get(), "YOLO")
        self.assertEqual(self.app.weights.get(), str(DEFAULT_WEIGHTS))
        # 공개 배포에는 가중치를 넣지 않습니다. 기본 경로와 모델 누락 오류를 별도로 검사합니다.
        self.assertEqual(DEFAULT_WEIGHTS.relative_to(Path(__file__).resolve().parent.parent).as_posix(),
                         "six_class_detection_training/runs/segment/train/weights/best.pt")
        worker = CameraWorker(0, "DSHOW", "YOLO", str(DEFAULT_WEIGHTS))
        self.app.worker = worker  # 가짜 패킷만 주입, 스레드/카메라를 시작하지 않음
        frame = demo_frame(430)
        target = Detection((395, 205, 465, 275), "red_box", .94)
        self.app.packet = (frame, [target], 1, time.monotonic(), False)
        self.app.draw(frame, [target], False)
        ox, oy, scale, *_ = self.app.display_rect
        event = type("Event", (), {"x": ox+430*scale, "y": oy+240*scale})()
        self.app.click(event)
        self.assertEqual(self.app.selected, "red_box")
        self.assertEqual(worker.selected, "red_box")
        self.app.worker = None

    def test_demo_select_goal_reset_stop(self):
        with patch("preview.cv2.VideoCapture", side_effect=AssertionError("no camera")):
            self.app.start(demo=True)
            self.pump(.4)
            frame = self.app.packet[0]
            d = detect_color(frame, "red")[0]
            ox, oy, scale, *_ = self.app.display_rect
            event = type("Event", (), {"x": ox+d.center[0]*scale, "y": oy+d.center[1]*scale})()
            self.app.click(event)
            self.pump(.2)
            self.assertEqual(self.app.selected, "red")
            self.assertIn("수평 오차", self.app.error_text.get())
            self.app.set_goal()
            self.assertNotEqual(self.app.target_x, .5)
            self.app.center_goal()
            self.assertEqual(self.app.target_x, .5)
            self.app.clear()
            self.assertIsNone(self.app.selected)
            self.app.stop()
            self.pump(.2)
            self.assertFalse(self.app.worker.thread.is_alive())
            self.assertIsNone(self.app.packet)
            self.assertEqual(str(self.app.start_button['state']), 'normal')

    def test_layout_sizes(self):
        for size in ("1120x820", "960x720"):
            self.root.geometry(size)
            self.pump(.1)
            self.assertGreater(self.app.canvas.winfo_height(), 200)
            self.assertLessEqual(self.app.tol_label.winfo_x()+self.app.tol_label.winfo_width(), self.app.tol_label.master.winfo_width())
            for widget in self.app.canvas.master.winfo_children():
                self.assertLessEqual(widget.winfo_y()+widget.winfo_height(), widget.master.winfo_height())


if __name__ == "__main__":
    unittest.main(verbosity=2)
