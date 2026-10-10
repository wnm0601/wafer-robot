import unittest

from wafer_cart_keyboard_drive.policy import MotionCommand
from wafer_cart_keyboard_drive.transport import DryRunTransport


class DryRunTransportTest(unittest.TestCase):
    def test_dry_run_records_protocol_without_serial(self) -> None:
        transport = DryRunTransport()

        transport.send_motion(MotionCommand(20, 0, 0))
        self.assertEqual(transport.last_line, "V 20 0 0")

        transport.send_stop()
        self.assertEqual(transport.last_line, "STOP")

        transport.send_estop()
        self.assertEqual(transport.last_line, "ESTOP")
