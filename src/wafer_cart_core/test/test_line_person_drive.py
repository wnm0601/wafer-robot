import unittest

from wafer_cart_core.line_person_drive import (
    DryRunTuning, LinePersonConfig, LinePersonController, VisionSample,
)
from wafer_cart_core.line_tracking import LineBoundaries


def road(*, right_curve: bool = False) -> LineBoundaries:
    return LineBoundaries(640, 170, 470, True, 260 if right_curve else 210,
                          540 if right_curve else 430)


class LinePersonControllerTest(unittest.TestCase):
    def test_distance_gate_boundary_unknown_multiple_and_far(self) -> None:
        for distances, expected in [((0.5,), "HUMAN_STOP"), ((0.499,), "HUMAN_STOP"),
                                    ((0.501,), "TRACK_PREVIEW"), ((20.0,), "TRACK_PREVIEW"),
                                    ((2.0, 0.4), "HUMAN_STOP"), ((None,), "HUMAN_STOP"),
                                    ((float("nan"),), "HUMAN_STOP"), ((0.0,), "HUMAN_STOP")]:
            with self.subTest(distances=distances):
                controller = LinePersonController(LinePersonConfig(stable_line_frames=1))
                controller.start()
                controller.observe(VisionSample(1, 0, len(distances), road(),
                                                person_distances_m=distances), now=0)
                self.assertEqual(controller.decide(now=0).state, expected)

    def test_near_person_then_far_person_visible_for_four_seconds_resumes(self) -> None:
        controller = LinePersonController(LinePersonConfig(stable_line_frames=1))
        controller.start()
        for index in range(43):
            now = index / 10
            distance = 0.4 if index == 0 else 2.0
            controller.observe(VisionSample(index, now, 1, road(),
                                            person_distances_m=(distance,)), now=now)
            state = controller.decide(now=now).state
            if index == 0:
                self.assertEqual(state, "HUMAN_STOP")
            elif index < 41:
                self.assertEqual(state, "HUMAN_WAIT")
            else:
                self.assertEqual(state, "TRACK_PREVIEW")

    def setUp(self) -> None:
        self.controller = LinePersonController(
            LinePersonConfig(stable_line_frames=1), DryRunTuning(20, 20, 40, 20),
        )

    def sample(self, time: float, people: int = 0, boundaries=True, healthy=True) -> None:
        self.controller.observe(
            VisionSample(round(time * 100) + 1, time, people,
                         road() if boundaries is True else boundaries, healthy), now=time,
        )

    def test_restart_stays_stopped_until_explicit_start(self) -> None:
        self.sample(0)
        self.assertEqual(self.controller.decide(now=0).protocol_line, "STOP")
        self.controller.start()
        self.assertEqual(self.controller.decide(now=0).protocol_line, "V 20 0 0")

    def test_person_overrides_good_line(self) -> None:
        self.controller.start()
        self.sample(0, people=1)
        result = self.controller.decide(now=0)
        self.assertEqual(result.state, "HUMAN_STOP")
        self.assertEqual(result.protocol_line, "STOP")

    def test_four_seconds_of_new_clear_frames_resume(self) -> None:
        self.controller.start()
        self.sample(0, people=1)
        self.sample(0.1)
        for index in range(1, 40):
            current = 0.1 + index / 10
            self.sample(current)
            self.assertEqual(self.controller.decide(now=current).protocol_line, "STOP")
        self.sample(4.1)
        self.assertEqual(self.controller.decide(now=4.1).state, "TRACK")

    def test_person_reappearance_restarts_clear_timer(self) -> None:
        self.controller.start()
        self.sample(0, people=1)
        for index in range(1, 31):
            self.sample(index / 10)
        self.sample(3.1, people=1)
        self.sample(3.2)
        self.assertAlmostEqual(self.controller.decide(now=3.2).clear_remaining_sec, 4)

    def test_cached_frame_and_wall_time_cannot_resume(self) -> None:
        self.controller.start()
        self.sample(0, people=1)
        self.sample(0.1)
        for current in (0.2, 0.3, 0.4, 0.5):
            self.assertEqual(self.controller.decide(now=current).protocol_line, "STOP")
        self.assertEqual(self.controller.decide(now=4.2).state, "SENSOR_STOP")

    def test_stale_gap_requires_operator_restart(self) -> None:
        self.controller.start()
        self.sample(0)
        self.assertEqual(self.controller.decide(now=1).state, "SENSOR_STOP")
        self.sample(1.1)
        self.assertEqual(self.controller.decide(now=1.1).protocol_line, "STOP")
        self.controller.start()
        self.assertEqual(self.controller.decide(now=1.1).state, "TRACK")

    def test_line_occluded_by_person_does_not_cancel_auto_resume(self) -> None:
        self.controller.start()
        self.sample(0, people=1, boundaries=None)
        self.assertEqual(self.controller.decide(now=0).state, "HUMAN_STOP")
        for index in range(1, 43):
            current = index / 10
            self.sample(current)
            result = self.controller.decide(now=current)
        self.assertEqual(result.state, "TRACK")

    def test_line_loss_requires_explicit_restart(self) -> None:
        self.controller.start()
        self.sample(0, boundaries=None)
        self.assertEqual(self.controller.decide(now=0).state, "LINE_STOP")
        self.sample(0.1)
        self.assertEqual(self.controller.decide(now=0.1).protocol_line, "STOP")

    def test_failed_person_inference_is_not_a_clear_frame(self) -> None:
        self.controller.start()
        self.sample(0, people=1)
        self.sample(0.1, healthy=False)
        self.assertEqual(self.controller.decide(now=0.1).state, "FAULT_STOP")

    def test_start_cannot_bypass_failed_inference_with_cached_good_frame(self) -> None:
        self.controller.start()
        self.sample(0)
        self.sample(0.1, healthy=False)
        self.controller.start()
        self.assertEqual(self.controller.decide(now=0.1).state, "FAULT_STOP")

    def test_duplicate_sequence_cannot_replace_person(self) -> None:
        self.controller.start()
        self.sample(0, people=1)
        self.controller.observe(VisionSample(1, 0.1, 0, road()), now=0.1)
        self.assertEqual(self.controller.decide(now=0.1).state, "HUMAN_STOP")

    def test_curve_slows_and_stays_under_mecanum_wheel_limit(self) -> None:
        self.controller.start()
        self.sample(0, boundaries=road(right_curve=True))
        result = self.controller.decide(now=0)
        self.assertGreater(result.yaw_percent, 0)
        self.assertLess(result.vx_percent, 20)
        self.assertLessEqual(abs(result.vx_percent) + abs(result.yaw_percent), 20)

    def test_estop_remains_latched_after_start(self) -> None:
        self.controller.emergency_stop()
        self.controller.start()
        self.sample(0)
        self.assertEqual(self.controller.decide(now=0).protocol_line, "ESTOP")

    def test_no_tuning_never_emits_motion(self) -> None:
        controller = LinePersonController(LinePersonConfig(stable_line_frames=1))
        controller.observe(VisionSample(1, 0, 0, road()), now=0)
        controller.start()
        self.assertEqual(controller.decide(now=0).state, "TRACK_PREVIEW")
        self.assertEqual(controller.decide(now=0).protocol_line, "STOP")

    def test_repeated_decisions_do_not_count_as_stable_line_frames(self) -> None:
        controller = LinePersonController(LinePersonConfig(stable_line_frames=3))
        controller.start()
        controller.observe(VisionSample(1, 0, 0, road()), now=0)
        for _ in range(10):
            self.assertEqual(controller.decide(now=0).state, "LINE_WAIT")
