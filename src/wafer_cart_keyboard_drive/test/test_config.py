import unittest

from wafer_cart_keyboard_drive.config import DriveOptions


class DriveOptionsTest(unittest.TestCase):
    def test_candidate_firmware_duty_conversion(self) -> None:
        options = DriveOptions(command_percent=20, host_limit_percent=50)
        self.assertEqual(options.estimated_command_duty, 40)
        self.assertEqual(options.estimated_host_limited_duty, 100)

    def test_command_must_not_exceed_host_limit(self) -> None:
        with self.assertRaises(ValueError):
            DriveOptions(command_percent=51, host_limit_percent=50)

    def test_real_motor_mode_requires_port(self) -> None:
        with self.assertRaises(ValueError):
            DriveOptions(
                command_percent=20,
                host_limit_percent=20,
                enable_motors=True,
                wheels_clear_confirmed=True,
            )
    def test_real_motor_mode_requires_wheels_clear_confirmation(self) -> None:
        with self.assertRaises(ValueError):
            DriveOptions(
                command_percent=20,
                host_limit_percent=20,
                enable_motors=True,
                port="COM_TEST",
            )
