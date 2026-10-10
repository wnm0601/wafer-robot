import unittest

from wafer_cart_core.line_tracking import LineAction, LineBoundaries, LineTrackingCore


class LineBoundariesTest(unittest.TestCase):
    def test_centered_boundaries_have_zero_error(self) -> None:
        boundaries = LineBoundaries(image_width=640, left_x=100, right_x=540, stable=True)
        self.assertAlmostEqual(boundaries.normalized_center_error, 0.0)

    def test_right_shift_is_positive_normalized_error(self) -> None:
        boundaries = LineBoundaries(image_width=640, left_x=200, right_x=600, stable=True)
        self.assertAlmostEqual(boundaries.normalized_center_error, 0.25)

    def test_far_center_produces_heading_error(self) -> None:
        boundaries = LineBoundaries(
            image_width=640,
            left_x=100,
            right_x=540,
            stable=True,
            far_left_x=180,
            far_right_x=600,
        )
        self.assertAlmostEqual(boundaries.normalized_center_error, 0.0)
        self.assertAlmostEqual(boundaries.normalized_heading_error, 0.21875)

    def test_crossed_boundaries_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            LineBoundaries(image_width=640, left_x=500, right_x=100, stable=True)


class LineTrackingCoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.core = LineTrackingCore()
        self.stable_line = LineBoundaries(
            image_width=640,
            left_x=100,
            right_x=540,
            stable=True,
        )

    def test_stable_line_allows_tracking(self) -> None:
        decision = self.core.decide(
            self.stable_line,
            auto_drive_enabled=True,
            operator_stop_requested=False,
        )
        self.assertEqual(decision.action, LineAction.TRACK)
        self.assertEqual(decision.reason, "line_stable")

    def test_operator_stop_has_highest_priority(self) -> None:
        decision = self.core.decide(
            self.stable_line,
            auto_drive_enabled=True,
            operator_stop_requested=True,
        )
        self.assertEqual(decision.action, LineAction.STOP)
        self.assertEqual(decision.reason, "operator_stop")

    def test_missing_line_stops_automatic_drive(self) -> None:
        decision = self.core.decide(
            None,
            auto_drive_enabled=True,
            operator_stop_requested=False,
        )
        self.assertEqual(decision.action, LineAction.STOP)
        self.assertEqual(decision.reason, "line_unavailable")

    def test_unstable_line_stops_automatic_drive(self) -> None:
        unstable = LineBoundaries(image_width=640, left_x=100, right_x=540, stable=False)
        decision = self.core.decide(
            unstable,
            auto_drive_enabled=True,
            operator_stop_requested=False,
        )
        self.assertEqual(decision.action, LineAction.STOP)
        self.assertEqual(decision.reason, "line_unstable")


if __name__ == "__main__":
    unittest.main()
