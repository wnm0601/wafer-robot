"""Motor-disabled interlock shared by terminal and isolated Nav2 tests."""
from __future__ import annotations

import math


class SafetyGate:
    def __init__(self, *, clear_seconds=4.0, freshness=0.5):
        if not math.isfinite(clear_seconds) or clear_seconds < 0:
            raise ValueError("invalid clear time")
        if not math.isfinite(freshness) or freshness <= 0:
            raise ValueError("invalid freshness")
        self.clear_seconds, self.freshness = clear_seconds, freshness
        self.power = False
        self.estop = False
        self.button_pressed = False
        self.armed = False
        self.seen_power_off = False
        self.last_sample = -math.inf
        self.sequence = -1
        self.session = None
        self.fresh_count = 0
        self.person = True
        self.person_latched = False
        self.clear_since = None
        self.reason = "STARTUP_LOCKED"

    def feedback(self, *, power: bool, estop: bool):
        if type(power) is not bool or type(estop) is not bool:
            raise ValueError("feedback requires booleans")
        self.power = power
        self.button_pressed = estop
        if not power:
            self.seen_power_off = True
        if estop or not power:
            self.armed = False
        if estop:
            self.estop = True
        self.reason = "ESTOP" if self.estop else "POWER_OFF" if not power else "MANUAL_REARM"

    def observe(self, data: dict, *, now: float):
        try:
            if data["motor_enabled"] is not False or data["healthy"] is not True:
                raise ValueError("unhealthy or non-disabled source")
            age, sequence = data["age_s"], data["sequence"]
            session, distances = data["session"], data["distances_m"]
            if (type(sequence) is not int or sequence < 0 or not isinstance(session, str)
                    or not session or not isinstance(distances, list)
                    or type(age) not in (int, float) or not math.isfinite(age)
                    or not 0 <= age <= self.freshness):
                raise ValueError("invalid perception packet")
            if session != self.session:
                if self.session is not None:
                    self.armed = False
                self.session, self.sequence = session, -1
                self.fresh_count = 0
                self.clear_since = None
            if sequence < self.sequence:
                raise ValueError("backwards sequence")
            if sequence == self.sequence:
                return
            sampled = now - age
            if self.sequence >= 0 and (sampled <= self.last_sample
                                      or sampled - self.last_sample > self.freshness):
                self.armed = False
                self.clear_since = None
                self.fresh_count = 0
            near = any(value is None or type(value) not in (int, float)
                       or not math.isfinite(value) or value <= 0.5 for value in distances)
            self.sequence, self.last_sample = sequence, sampled
            self.fresh_count += 1
            self.person = near
            if near:
                self.person_latched, self.clear_since = True, None
            elif self.person_latched:
                if self.clear_since is None:
                    self.clear_since = sampled
                if sampled - self.clear_since >= self.clear_seconds:
                    self.person_latched, self.clear_since = False, None
        except (KeyError, TypeError, ValueError):
            self.armed = False
            self.fresh_count = 0
            self.last_sample = -math.inf
            self.clear_since = None
            self.reason = "SENSOR_FAULT"

    def stop(self):
        self.armed = False
        self.reason = "OPERATOR_STOP"

    def emergency_stop(self):
        self.estop, self.armed = True, False
        self.seen_power_off = False
        self.reason = "ESTOP"

    def rearm(self, *, now: float) -> bool:
        if (not self.power or self.button_pressed or not self.seen_power_off or self.person or self.person_latched
                or self.fresh_count < 2
                or not 0 <= now - self.last_sample <= self.freshness):
            return False
        # This is an explicit operator command, never called by an automatic timer.
        self.estop = False
        self.armed = True
        return True

    def allows_motion(self, *, now: float) -> bool:
        if not 0 <= now - self.last_sample <= self.freshness:
            self.armed = False
            self.fresh_count = 0
            self.clear_since = None
            self.reason = "SENSOR_STALE"
        elif self.estop:
            self.reason = "ESTOP"
        elif not self.power:
            self.reason = "POWER_OFF"
        elif not self.armed:
            self.reason = "MANUAL_REARM"
        elif self.person or self.person_latched:
            self.reason = "HUMAN_STOP_OR_CLEAR_WAIT"
        else:
            self.reason = "READY_MOTOR_DISABLED"
            return True
        return False


def checked_camera_url(url: str) -> str:
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if (parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost")
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in ("", "/")):
        raise ValueError("Only a local read-only camera bridge is allowed")
    return url.rstrip("/")
