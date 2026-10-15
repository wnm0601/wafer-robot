"""포트/키보드/모터 없이 실행하는 회귀시험."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from common.manual_motor_test import (HoldController, Link, TestFault,
                                     expected_ack, parse_encoder, shutdown)


class ControllerTests(unittest.TestCase):
    def ready(self, mode="drive"):
        c = HoldController(mode, 20, 0)
        for t in (.1, .2, .3, .4, .51, .55):
            c.observe((0, 0, 0, 0), t)
            self.assertEqual(c.tick(set(), True, t), [])
        self.assertEqual(c.state, "ready")
        return c

    def tick(self, c, keys=(), focused=True, dt=.1):
        now = c.last_tick + dt
        c.observe((0, 0, 0, 0), now)
        return c.tick(set(keys), focused, now)

    def test_single_release_sends_stop(self):
        c = self.ready("single")
        self.assertEqual(self.tick(c, {"f"}), ["M 1 20"])
        self.assertEqual(self.tick(c), ["STOP"])

    def test_drive_commands(self):
        for key, cmd in {"w": "V 20 0 0", "s": "V -20 0 0", "a": "V 0 0 -20",
                         "d": "V 0 0 20", "z": "V 0 -20 0", "c": "V 0 20 0"}.items():
            self.assertEqual(self.tick(self.ready(), {key}), [cmd])

    def test_pairs(self):
        from common.manual_motor_test import PAIRS
        for key, (a, b) in PAIRS.items():
            c = self.ready("pair")
            self.tick(c, {key})
            self.tick(c)
            self.assertEqual(self.tick(c, {"up"}), [f"P {a} {b} 20"])

    def test_space_precedes_start_and_repeat(self):
        c = self.ready()
        self.assertEqual(self.tick(c, {"space", "w"}), [])
        self.assertEqual(self.tick(c, {"w"}), [])
        self.tick(c)
        self.assertEqual(self.tick(c, {"w"}), ["V 20 0 0"])
        self.assertEqual(self.tick(c, {"space", "w"}), ["STOP"])

    def test_focus_return_requires_release(self):
        c = self.ready()
        self.tick(c, {"w"})
        self.assertEqual(self.tick(c, {"w"}, focused=False), ["STOP"])
        for _ in range(8):
            self.assertEqual(self.tick(c, {"w"}, focused=False), [])
        self.assertEqual(self.tick(c, {"w"}), [])
        self.tick(c)
        self.assertEqual(self.tick(c, {"w"}), ["V 20 0 0"])

    def test_selection_and_motion_do_not_start_together(self):
        c = self.ready("pair")
        self.assertEqual(self.tick(c, {"2", "up"}), [])
        self.assertEqual(c.selection, "1")
        self.assertEqual(self.tick(c, {"up"}), [])

    def test_speed_change_while_moving_stops_without_change(self):
        c = self.ready()
        self.tick(c, {"w"})
        self.assertEqual(self.tick(c, {"w", "+"}), ["STOP"])
        self.assertEqual(c.speed, 20)

    def test_opposite_key_requires_stop_and_release(self):
        c = self.ready()
        self.tick(c, {"w"})
        self.assertEqual(self.tick(c, {"s"}), ["STOP"])
        for _ in range(8):
            self.assertEqual(self.tick(c, {"s"}), [])
        self.tick(c)
        self.assertEqual(self.tick(c, {"s"}), ["V -20 0 0"])

    def test_two_motion_keys_stop(self):
        c = self.ready()
        self.tick(c, {"w"})
        self.assertEqual(self.tick(c, {"w", "s"}), ["STOP"])

    def test_stale_encoder_never_confirms_stop(self):
        c = self.ready()
        self.tick(c, {"w"})
        self.tick(c)
        c.observe((0, 0, 0, 0), c.last_tick)
        with self.assertRaises(TestFault):
            for _ in range(8):
                c.tick(set(), True, c.last_tick + .1)
        self.assertEqual(c.state, "fault")

    def test_missing_encoder_times_out(self):
        c = HoldController("drive", 10, 0)
        with self.assertRaises(TestFault):
            for i in range(1, 25):
                c.tick(set(), True, i * .1)
        self.assertEqual(c.state, "fault")

    def test_loop_delay_fault(self):
        c = self.ready()
        with self.assertRaises(TestFault):
            self.tick(c, {"w"}, dt=.41)

    def test_estop_wins(self):
        c = self.ready()
        with self.assertRaises(TestFault):
            self.tick(c, {"w", "x"})
        with self.assertRaises(TestFault):
            self.tick(c, {"w"})

    def test_speed_bounds(self):
        for value in (-1, 0, 4, 41, 100):
            with self.assertRaises(ValueError):
                HoldController("drive", value, 0)


class FakeSerial:
    def __init__(self, reply=b""):
        self.rx = bytearray()
        self.reply, self.sent, self.closed = reply, [], False
        self.fail_write = False

    @property
    def in_waiting(self):
        return len(self.rx)

    def read(self, n):
        data = bytes(self.rx[:n])
        del self.rx[:n]
        return data

    def write(self, data):
        if self.fail_write:
            raise OSError("분리 모의")
        self.sent.append(data)
        self.rx.extend(self.reply)
        return len(data)

    def close(self):
        self.closed = True


class ProtocolTests(unittest.TestCase):
    def test_ack(self):
        for cmd, reply in [("M 2 10", "OK M2"), ("P 2 4 10", "OK P 2 4"), ("V 10 0 0", "OK V")]:
            self.assertEqual(expected_ack(cmd), reply)
            link = Link(FakeSerial((reply + "\n").encode()))
            self.assertEqual(link.request(cmd, lambda s: s == reply), reply)

    def test_error_in_same_batch_wins_over_ack(self):
        for error in ("READY", "ERR PWR", "ERR M", "UNK P", "EVT PWR OFF"):
            link = Link(FakeSerial(f"OK V\n{error}\n".encode()))
            with self.assertRaises(TestFault):
                link.request("V 10 0 0", lambda s: s == "OK V")

    def test_pending_reset_prevents_send(self):
        ser = FakeSerial()
        ser.rx.extend(b"READY\n")
        with self.assertRaises(TestFault):
            Link(ser).request("V 10 0 0", lambda s: True)
        self.assertEqual(ser.sent, [])

    def test_timeout(self):
        now = [0.]
        def sleep(dt):
            now[0] += dt
        with self.assertRaises(TestFault):
            Link(FakeSerial(), lambda: now[0], sleep).request("ID", lambda s: s == "MECANUM")

    def test_partial_frames(self):
        ser = FakeSerial()
        link = Link(ser)
        ser.rx.extend(b"ENC 1 2")
        self.assertEqual(link.read(), [])
        ser.rx.extend(b" 3 4\n")
        self.assertEqual(link.read(), ["ENC 1 2 3 4"])

    def test_short_write(self):
        ser = FakeSerial()
        ser.write = lambda _: 1
        with self.assertRaises(TestFault):
            Link(ser).send("STOP")

    def test_malformed_encoder(self):
        for line in ("ENC", "ENC 1 2 3", "ENC 1 2 3 4 5", "ENC 1 x 3 4", "ENC 2147483648 0 0 0"):
            with self.assertRaises(TestFault):
                parse_encoder(line)
        self.assertEqual(parse_encoder("ENC -1 2 3 4"), (-1, 2, 3, 4))

    def test_cleanup_closes_even_if_write_fails(self):
        ser = FakeSerial()
        ser.fail_write = True
        messages = []
        shutdown(Link(ser), messages.append)
        self.assertTrue(ser.closed)
        self.assertIn("실패", messages[0])


if __name__ == "__main__":
    unittest.main()
