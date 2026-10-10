"""Deterministic mission state machine with no hardware or ROS side effects."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class MissionError(RuntimeError):
    """Raised when an event is not valid in the current mission state."""


class MissionState(Enum):
    SAFE_STOP = auto()
    WAITING_FOR_LOAD = auto()
    LOAD_READY = auto()
    DEPARTURE_COUNTDOWN = auto()
    OUTBOUND = auto()
    HUMAN_STOP = auto()
    OBSTACLE_STOP = auto()
    LINE_LOST_STOP = auto()
    MANUAL_LINE_RECOVERY = auto()
    ARRIVED_WAIT_UNLOAD = auto()
    RETURN_COUNTDOWN = auto()
    TURNAROUND_CONFIRM = auto()
    TURNAROUND_180 = auto()
    RETURNING = auto()
    MANUAL = auto()
    OPERATOR_STOP = auto()
    E_STOP = auto()
    FAULT = auto()


@dataclass(frozen=True)
class MissionConfig:
    """Operator-editable timings; distances and speeds live in calibrated controllers."""

    provisional_target_count: int = 5
    departure_countdown_sec: float = 5.0
    human_clear_resume_sec: float = 4.0
    return_countdown_sec: float = 10.0

    def __post_init__(self) -> None:
        if self.provisional_target_count <= 0:
            raise ValueError("provisional_target_count must be positive")
        for name in (
            "departure_countdown_sec",
            "human_clear_resume_sec",
            "return_countdown_sec",
        ):
            if getattr(self, name) < 0.0:
                raise ValueError(f"{name} must be non-negative")


class MissionController:
    """Pure state transitions used by future ROS and HMI adapters."""

    MOVING_STATES = {
        MissionState.OUTBOUND,
        MissionState.TURNAROUND_180,
        MissionState.RETURNING,
        MissionState.MANUAL_LINE_RECOVERY,
        MissionState.MANUAL,
    }

    def __init__(self, config: MissionConfig | None = None) -> None:
        self.config = config or MissionConfig()
        self.state = MissionState.SAFE_STOP
        self.destination: int | None = None
        self.loaded_count = 0
        self.cycle_id: str | None = None
        self.countdown_remaining = 0.0
        self.person_clear_elapsed = 0.0
        self._resume_state: MissionState | None = None
        self._operator_resume_state: MissionState | None = None

    @property
    def settings_locked(self) -> bool:
        """Settings remain editable only while the cart is stationary."""
        return self.state in self.MOVING_STATES

    def operator_ready(self) -> None:
        self._require(MissionState.SAFE_STOP)
        self.state = MissionState.WAITING_FOR_LOAD

    def select_destination(self, destination: int) -> None:
        if destination not in (1, 2, 3):
            raise ValueError("destination must be 1, 2, or 3")
        if self.settings_locked:
            raise MissionError("destination is locked while the cart is moving")
        if self.state in {MissionState.E_STOP, MissionState.FAULT}:
            raise MissionError("destination cannot change while safety is latched")
        self.destination = destination
        self._begin_departure_if_ready()

    def report_load_complete(self, *, cycle_id: str, loaded_count: int) -> None:
        if self.state not in {MissionState.WAITING_FOR_LOAD, MissionState.LOAD_READY}:
            raise MissionError("load completion is not accepted in the current state")
        if not cycle_id:
            raise ValueError("cycle_id is required")
        if loaded_count < self.config.provisional_target_count:
            raise MissionError("loaded_count has not reached the configured target")
        self.cycle_id = cycle_id
        self.loaded_count = loaded_count
        self.state = MissionState.LOAD_READY
        self._begin_departure_if_ready()

    def tick(self, seconds: float, *, person_visible: bool = False) -> None:
        if seconds < 0.0:
            raise ValueError("seconds must be non-negative")
        if self.state is MissionState.DEPARTURE_COUNTDOWN:
            self.countdown_remaining = max(0.0, self.countdown_remaining - seconds)
            if self.countdown_remaining == 0.0:
                self.state = MissionState.OUTBOUND
        elif self.state is MissionState.RETURN_COUNTDOWN:
            self.countdown_remaining = max(0.0, self.countdown_remaining - seconds)
            if self.countdown_remaining == 0.0:
                self.state = MissionState.TURNAROUND_CONFIRM
        elif self.state is MissionState.HUMAN_STOP:
            if person_visible:
                self.person_clear_elapsed = 0.0
            else:
                self.person_clear_elapsed += seconds
                if self.person_clear_elapsed >= self.config.human_clear_resume_sec:
                    self.state = self._resume_state or MissionState.SAFE_STOP
                    self._resume_state = None
                    self.person_clear_elapsed = 0.0

    def start_now(self) -> None:
        if self.state is MissionState.DEPARTURE_COUNTDOWN:
            self.countdown_remaining = 0.0
            self.state = MissionState.OUTBOUND
        elif self.state is MissionState.RETURN_COUNTDOWN:
            self.countdown_remaining = 0.0
            self.state = MissionState.TURNAROUND_CONFIRM
        else:
            raise MissionError("there is no active countdown")

    def cancel_departure(self) -> None:
        self._require(MissionState.DEPARTURE_COUNTDOWN)
        self.countdown_remaining = 0.0
        self.state = MissionState.LOAD_READY

    def person_detected(self) -> None:
        if self.state not in {MissionState.OUTBOUND, MissionState.RETURNING}:
            return
        self._resume_state = self.state
        self.person_clear_elapsed = 0.0
        self.state = MissionState.HUMAN_STOP

    def obstacle_detected(self) -> None:
        if self.state not in {MissionState.OUTBOUND, MissionState.RETURNING}:
            return
        self._resume_state = self.state
        self.state = MissionState.OBSTACLE_STOP

    def operator_resume_after_obstacle(self) -> None:
        self._require(MissionState.OBSTACLE_STOP)
        self.state = self._resume_state or MissionState.SAFE_STOP
        self._resume_state = None

    def line_lost(self) -> None:
        if self.state not in {MissionState.OUTBOUND, MissionState.RETURNING}:
            return
        self._resume_state = self.state
        self.state = MissionState.LINE_LOST_STOP

    def begin_manual_line_recovery(self) -> None:
        self._require(MissionState.LINE_LOST_STOP)
        self.state = MissionState.MANUAL_LINE_RECOVERY

    def line_reacquired(self, *, stable: bool) -> None:
        self._require(MissionState.MANUAL_LINE_RECOVERY)
        if stable:
            self.state = self._resume_state or MissionState.SAFE_STOP
            self._resume_state = None

    def enter_manual(self) -> None:
        if self.state in {MissionState.E_STOP, MissionState.FAULT}:
            raise MissionError("manual mode is unavailable while safety is latched")
        self._resume_state = None
        self.state = MissionState.MANUAL

    def operator_stop(self) -> None:
        """Stop an active motion and wait for an explicit operator resume command."""
        if self.state in {MissionState.E_STOP, MissionState.FAULT}:
            return
        if self.state in self.MOVING_STATES:
            self._operator_resume_state = self.state
            self.state = MissionState.OPERATOR_STOP

    def operator_resume(self) -> None:
        """Resume only the motion that was explicitly paused by the operator."""
        self._require(MissionState.OPERATOR_STOP)
        self.state = self._operator_resume_state or MissionState.SAFE_STOP
        self._operator_resume_state = None

    def press_auto_drive(self) -> None:
        """Use one UI button for immediate departure or resuming an operator stop."""
        if self.state is MissionState.DEPARTURE_COUNTDOWN:
            self.start_now()
        elif self.state is MissionState.OPERATOR_STOP:
            self.operator_resume()
        else:
            raise MissionError("auto drive button is unavailable in the current state")

    def destination_arrived(self) -> None:
        self._require(MissionState.OUTBOUND)
        self.state = MissionState.ARRIVED_WAIT_UNLOAD

    def unload_complete(self) -> None:
        self._require(MissionState.ARRIVED_WAIT_UNLOAD)
        self.state = MissionState.RETURN_COUNTDOWN
        self.countdown_remaining = self.config.return_countdown_sec

    def confirm_turnaround(self) -> None:
        self._require(MissionState.TURNAROUND_CONFIRM)
        self.state = MissionState.TURNAROUND_180

    def turnaround_complete(self, *, line_aligned: bool) -> None:
        self._require(MissionState.TURNAROUND_180)
        self.state = MissionState.RETURNING if line_aligned else MissionState.MANUAL

    def home_arrived(self) -> None:
        self._require(MissionState.RETURNING)
        self.destination = None
        self.loaded_count = 0
        self.cycle_id = None
        self._resume_state = None
        self.state = MissionState.WAITING_FOR_LOAD

    def emergency_stop(self) -> None:
        self.countdown_remaining = 0.0
        self._resume_state = None
        self._operator_resume_state = None
        self.state = MissionState.E_STOP

    def reset_estop(self) -> None:
        self._require(MissionState.E_STOP)
        self.destination = None
        self.loaded_count = 0
        self.cycle_id = None
        self.state = MissionState.SAFE_STOP

    def restart(self) -> None:
        """A process restart must never restore an active driving state."""
        self.destination = None
        self.loaded_count = 0
        self.cycle_id = None
        self.countdown_remaining = 0.0
        self.person_clear_elapsed = 0.0
        self._resume_state = None
        self._operator_resume_state = None
        self.state = MissionState.SAFE_STOP

    def _begin_departure_if_ready(self) -> None:
        if self.state is MissionState.LOAD_READY and self.destination is not None:
            self.state = MissionState.DEPARTURE_COUNTDOWN
            self.countdown_remaining = self.config.departure_countdown_sec

    def _require(self, expected: MissionState) -> None:
        if self.state is not expected:
            raise MissionError(f"expected {expected.name}, got {self.state.name}")
