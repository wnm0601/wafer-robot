import unittest
from wafer_cart_core.safety_gate import SafetyGate, checked_camera_url


def packet(sequence, distances=None, age=0.0, session="test"):
    return dict(sequence=sequence, distances_m=distances or [], age_s=age,
                session=session, healthy=True, motor_enabled=False)


class SafetyGateTest(unittest.TestCase):
    def ready(self):
        gate = SafetyGate()
        gate.feedback(power=False, estop=False)
        gate.feedback(power=True, estop=False)
        gate.observe(packet(0), now=0.9)
        gate.observe(packet(1), now=1.0)
        self.assertTrue(gate.rearm(now=1.0))
        return gate

    def test_startup_on_cannot_arm_without_off_observation(self):
        gate = SafetyGate()
        gate.feedback(power=True, estop=False)
        gate.observe(packet(1), now=1.0)
        self.assertFalse(gate.rearm(now=1.0))

    def test_power_return_never_arms(self):
        gate = self.ready()
        gate.feedback(power=False, estop=False)
        gate.feedback(power=True, estop=False)
        self.assertFalse(gate.allows_motion(now=1.0))

    def test_estop_requires_power_cycle_and_manual_rearm(self):
        gate = self.ready()
        gate.emergency_stop()
        self.assertFalse(gate.rearm(now=1.0))
        gate.feedback(power=False, estop=True)
        gate.feedback(power=True, estop=False)
        self.assertFalse(gate.allows_motion(now=1.0))
        self.assertTrue(gate.rearm(now=1.0))

    def test_person_threshold_unknown_and_four_seconds_new_frames(self):
        for distances in ([0.5], [None], [2.0, 0.4], [float("nan")]):
            gate = self.ready()
            gate.observe(packet(2, distances), now=1.1)
            self.assertFalse(gate.allows_motion(now=1.1))
            for i in range(42):
                now = 1.2 + i * 0.1
                gate.observe(packet(i + 3), now=now)
                self.assertEqual(gate.allows_motion(now=now), i >= 40)

    def test_frozen_frame_cannot_resume(self):
        gate = self.ready()
        gate.observe(packet(1), now=1.6)
        self.assertFalse(gate.allows_motion(now=1.6))

    def test_faults_and_restarts_lock(self):
        for change in ({"healthy": False}, {"age_s": 0.6}, {"age_s": -1},
                       {"session": "new"}, {"sequence": 0}, {"motor_enabled": True}):
            gate = self.ready()
            data = packet(2)
            data.update(change)
            gate.observe(data, now=1.1)
            self.assertFalse(gate.allows_motion(now=1.1))

    def test_far_person_does_not_stop(self):
        gate = self.ready()
        gate.observe(packet(2, [1.0]), now=1.1)
        self.assertTrue(gate.allows_motion(now=1.1))

    def test_stop_requires_manual_resume(self):
        gate = self.ready()
        gate.stop()
        self.assertFalse(gate.allows_motion(now=1.1))

    def test_local_url_only(self):
        self.assertEqual(checked_camera_url("http://127.0.0.1:8780/"), "http://127.0.0.1:8780")
        for url in ("https://example.com", "http://evil.com", "http://u@localhost", "http://localhost/x"):
            with self.assertRaises(ValueError):
                checked_camera_url(url)

    def test_pressed_button_and_single_cached_frame_cannot_rearm(self):
        gate = self.ready()
        gate.feedback(power=True, estop=True)
        self.assertFalse(gate.rearm(now=1.1))
        gate = SafetyGate()
        gate.feedback(power=False, estop=False)
        gate.feedback(power=True, estop=False)
        gate.observe(packet(1), now=1.0)
        self.assertFalse(gate.rearm(now=1.0))
