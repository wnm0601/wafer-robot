"""Fresh-frame line guidance with person-stop priority; no hardware access."""

from __future__ import annotations

from dataclasses import dataclass
import math

from .line_tracking import LineBoundaries


@dataclass(frozen=True)
class VisionSample:
    sequence: int
    acquired_at: float
    people_count: int
    boundaries: LineBoundaries | None
    healthy: bool = True
    person_distances_m: tuple[float | None, ...] | None = None

    def __post_init__(self) -> None:
        if self.sequence < 0 or self.people_count < 0:
            raise ValueError("sequence and people_count must be non-negative")
        if not math.isfinite(self.acquired_at):
            raise ValueError("acquired_at must be finite")
        if self.person_distances_m is not None and len(self.person_distances_m) != self.people_count:
            raise ValueError("one distance is required per detected person")


@dataclass(frozen=True)
class LinePersonConfig:
    human_clear_resume_sec: float = 4.0
    max_sample_age_sec: float = 0.5
    stable_line_frames: int = 3
    person_stop_distance_m: float = 0.5

    def __post_init__(self) -> None:
        if not math.isfinite(self.human_clear_resume_sec) or self.human_clear_resume_sec < 0:
            raise ValueError("human_clear_resume_sec must be finite and non-negative")
        if not math.isfinite(self.max_sample_age_sec) or self.max_sample_age_sec <= 0:
            raise ValueError("max_sample_age_sec must be finite and positive")
        if self.stable_line_frames < 1:
            raise ValueError("stable_line_frames must be positive")
        if not math.isfinite(self.person_stop_distance_m) or self.person_stop_distance_m <= 0:
            raise ValueError("person_stop_distance_m must be finite and positive")


@dataclass(frozen=True)
class DryRunTuning:
    """Explicit simulation values, never an approval to operate real motors."""

    forward_percent: int
    center_gain_percent: float
    heading_gain_percent: float
    host_limit_percent: int

    def __post_init__(self) -> None:
        if not 1 <= self.forward_percent <= self.host_limit_percent <= 100:
            raise ValueError("expected 1 <= forward_percent <= host_limit_percent <= 100")
        for value in (self.center_gain_percent, self.heading_gain_percent):
            if not math.isfinite(value) or value < 0:
                raise ValueError("steering gains must be finite and non-negative")


@dataclass(frozen=True)
class DriveDecision:
    state: str
    reason: str
    vx_percent: int = 0
    yaw_percent: int = 0
    center_error: float | None = None
    heading_error: float | None = None
    clear_remaining_sec: float | None = None

    @property
    def protocol_line(self) -> str:
        if self.state == "E_STOP":
            return "ESTOP"
        if self.state == "TRACK":
            return f"V {self.vx_percent} 0 {self.yaw_percent}"
        return "STOP"


class LinePersonController:
    """Gate line commands using distinct frames and local monotonic time."""

    def __init__(
        self,
        config: LinePersonConfig | None = None,
        tuning: DryRunTuning | None = None,
    ) -> None:
        self.config = config or LinePersonConfig()
        self.tuning = tuning
        self._auto = False
        self._estop = False
        self._fault = False
        self._healthy_since_fault = False
        self._sample: VisionSample | None = None
        self._stable_frames = 0
        self._person_latched = False
        self._clear_since: float | None = None

    def start(self) -> None:
        """Explicit operator action; cannot bypass person or freshness guards."""
        if not self._estop:
            if self._fault and not self._healthy_since_fault:
                return
            self._auto = True
            self._fault = False

    def stop(self) -> None:
        self._auto = False

    def emergency_stop(self) -> None:
        self._estop = True
        self._auto = False

    def _person_blocks(self, sample: VisionSample) -> bool:
        if sample.people_count == 0:
            return False
        if sample.person_distances_m is None:
            return True
        return any(distance is None or not math.isfinite(distance) or distance <= 0
                   or distance <= self.config.person_stop_distance_m
                   for distance in sample.person_distances_m)

    def _invalidate(self) -> None:
        self._fault = True
        self._auto = False
        self._clear_since = None
        self._stable_frames = 0
        self._healthy_since_fault = False

    def observe(self, sample: VisionSample, *, now: float) -> None:
        age = now - sample.acquired_at
        if not sample.healthy or not 0 <= age <= self.config.max_sample_age_sec:
            self._invalidate()
            return
        previous = self._sample
        if previous is not None:
            if sample.sequence <= previous.sequence or sample.acquired_at <= previous.acquired_at:
                return
            if sample.acquired_at - previous.acquired_at > self.config.max_sample_age_sec:
                self._clear_since = None
                self._stable_frames = 0
                if self._auto:
                    self._invalidate()

        self._sample = sample
        self._healthy_since_fault = True
        line_ok = sample.boundaries is not None and sample.boundaries.stable
        self._stable_frames = self._stable_frames + 1 if line_ok else 0
        if self._person_blocks(sample):
            self._person_latched = True
            self._clear_since = None
        elif self._person_latched and self._clear_since is None:
            self._clear_since = sample.acquired_at

    def decide(self, *, now: float) -> DriveDecision:
        if self._estop:
            return DriveDecision("E_STOP", "operator_estop")
        sample = self._sample
        if sample is None:
            return DriveDecision("SENSOR_STOP", "no_valid_sample")
        if not 0 <= now - sample.acquired_at <= self.config.max_sample_age_sec:
            self._invalidate()
            return DriveDecision("SENSOR_STOP", "camera_or_inference_stale")
        if self._fault:
            return DriveDecision("FAULT_STOP", "explicit_restart_required")
        if not self._auto:
            return DriveDecision("OPERATOR_STOP", "press_a_to_start")
        if self._person_blocks(sample):
            return DriveDecision("HUMAN_STOP", "person_near_or_depth_unknown",
                                 clear_remaining_sec=self.config.human_clear_resume_sec)
        if self._person_latched:
            # Time advances only with new, healthy, person-free camera frames.
            deadline = None if self._clear_since is None else (
                self._clear_since + self.config.human_clear_resume_sec
            )
            remaining = self.config.human_clear_resume_sec if deadline is None else (
                max(0.0, deadline - sample.acquired_at)
            )
            if deadline is None or sample.acquired_at < deadline:
                return DriveDecision("HUMAN_WAIT", "continuous_clear_required",
                                     clear_remaining_sec=remaining)
            self._person_latched = False
            self._clear_since = None
        if sample.boundaries is None or not sample.boundaries.stable:
            self._auto = False
            return DriveDecision("LINE_STOP", "line_lost_press_a_after_recovery")
        if self._stable_frames < self.config.stable_line_frames:
            return DriveDecision("LINE_WAIT", "more_distinct_line_frames_required")

        center = sample.boundaries.normalized_center_error
        heading = sample.boundaries.normalized_heading_error or 0.0
        if self.tuning is None:
            return DriveDecision("TRACK_PREVIEW", "dry_run_tuning_required",
                                 center_error=center, heading_error=heading)
        # More curved guidance reduces the candidate forward request.
        forward = max(1, round(self.tuning.forward_percent * max(0.25, 1 - abs(heading))))
        yaw = round(center * self.tuning.center_gain_percent
                    + heading * self.tuning.heading_gain_percent)
        total = abs(forward) + abs(yaw)
        if total > self.tuning.host_limit_percent:
            scale = self.tuning.host_limit_percent / total
            forward, yaw = int(forward * scale), int(yaw * scale)
        return DriveDecision("TRACK", "fresh_line_no_near_person", forward, yaw, center, heading)
