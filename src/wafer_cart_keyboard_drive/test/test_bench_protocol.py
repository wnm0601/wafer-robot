import binascii
import unittest

from wafer_cart_keyboard_drive.bench_protocol import ProtocolError, frame, request, unframe


class BenchProtocolTest(unittest.TestCase):
    def test_crc_standard_vector(self):
        self.assertEqual(binascii.crc_hqx(b"123456789", 0xffff), 0x29b1)

    def test_roundtrip(self):
        self.assertEqual(unframe(request("0123456789abcdef", 1, "HELLO")),
                         ["C2", "0123456789abcdef", "1", "HELLO"])

    def test_corruption(self):
        good = request("0123456789abcdef", 2, "M", 1, 10)
        with self.assertRaises(ProtocolError):
            unframe(good.replace(b" 10 ", b" 20 "))

    def test_bad_frames(self):
        for value in (b"READY\n", b"\n", b"R2\n", frame("E2 - BOOT")[:-1],
                      b"a" * 300 + b"\n", b"a *hhhh\n"):
            with self.subTest(value=value), self.assertRaises(ProtocolError):
                unframe(value)

    def test_controls_and_size(self):
        for value in ("a\nb", "a\x00b", "한글", "a" * 240):
            with self.assertRaises(ProtocolError):
                frame(value)

    def test_invalid_request(self):
        for sid, seq, op, args in (("bad", 1, "HELLO", ()), ("0123456789abcdef", True, "HELLO", ()),
                                  ("0123456789abcdef", 0, "HELLO", ()),
                                  ("0123456789abcdef", 0x100000000, "HELLO", ()),
                                  ("0123456789abcdef", 1, "M", (0, 1)),
                                  ("0123456789abcdef", 1, "M", (1, 31)),
                                  ("0123456789abcdef", 1, "LIMIT", (0,)),
                                  ("0123456789abcdef", 1, "ARM", (1,)),
                                  ("0123456789abcdef", 1, "V", (1.0, 0, 0))):
            with self.subTest(op=op, args=args), self.assertRaises(ProtocolError):
                request(sid, seq, op, *args)
