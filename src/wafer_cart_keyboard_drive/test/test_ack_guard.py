import unittest
from wafer_cart_keyboard_drive.transport import SerialTransport
from wafer_cart_keyboard_drive.config import DriveOptions


class FakeSerial:
    def __init__(self, lines):
        self.lines = iter(lines)
    def write(self, _):
        pass
    def flush(self):
        pass
    def readline(self):
        return next(self.lines, b"")


class AckGuardTest(unittest.TestCase):
    def exchange(self, lines):
        transport = SerialTransport.__new__(SerialTransport)
        transport._serial = FakeSerial(lines)
        transport._exchange("V 20 0 0", "OK V")

    def test_exact_ack(self):
        self.exchange([b"\n", b"OK V\n"])

    def test_fault_event_error_and_prefix_are_not_ack(self):
        for line in (b"FAULT STALL_NO_ENCODER M=1\n", b"EVENT DEADMAN_TIMEOUT\n",
                     b"ERR V\n", b"OK VELOCITY\n", b"OK V old\n"):
            with self.assertRaises(RuntimeError):
                self.exchange([line])

    def test_low_heartbeat_rejected(self):
        for frequency in (1, 2, 5, float("nan")):
            with self.assertRaises(ValueError):
                DriveOptions(20, 20, heartbeat_hz=frequency)

    def test_even_confirmed_real_mode_stays_locked(self):
        with self.assertRaisesRegex(ValueError, "locked"):
            DriveOptions(20, 20, enable_motors=True, port="NEVER_OPEN", wheels_clear_confirmed=True)
