import unittest

from wafer_cart_keyboard_drive.policy import KeyboardDrivePolicy, MotionCommand


class KeyboardDrivePolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = KeyboardDrivePolicy(command_percent=20, host_limit_percent=35)

    def test_forward(self) -> None:
        self.assertEqual(
            self.policy.command_for_keys({"w"}),
            MotionCommand(20, 0, 0),
        )

    def test_strafe_left(self) -> None:
        self.assertEqual(
            self.policy.command_for_keys({"a"}),
            MotionCommand(0, -20, 0),
        )

    def test_rotate_left_uses_negative_firmware_yaw(self) -> None:
        self.assertEqual(
            self.policy.command_for_keys({"q"}),
            MotionCommand(0, 0, -20),
        )

    def test_opposite_keys_cancel(self) -> None:
        self.assertTrue(self.policy.command_for_keys({"w", "s"}).is_zero)

    def test_combined_motion_keeps_wheel_mix_within_host_limit(self) -> None:
        command = self.policy.command_for_keys({"w", "d", "e"})
        self.assertEqual(command, MotionCommand(12, 12, 11))
        self.assertEqual(
            abs(command.vx_percent) + abs(command.vy_percent) + abs(command.yaw_percent),
            35,
        )

    def test_two_axis_motion_is_unchanged_when_within_host_limit(self) -> None:
        policy = KeyboardDrivePolicy(command_percent=15, host_limit_percent=35)
        self.assertEqual(policy.command_for_keys({"w", "d"}), MotionCommand(15, 15, 0))

    def test_protocol_line(self) -> None:
        self.assertEqual(MotionCommand(20, -20, 0).to_protocol_line(), "V 20 -20 0")
