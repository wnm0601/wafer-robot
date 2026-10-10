"""Pure geometry and stop decisions for two-boundary line tracking."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class LineAction(str, Enum):
    """High-level intent; physical velocity scaling is deliberately separate."""

    STOP = "stop"
    TRACK = "track"


@dataclass(frozen=True)
class LineBoundaries:
    """Detected left/right road boundaries in one image row or projected plane."""

    image_width: float
    left_x: float
    right_x: float
    stable: bool
    far_left_x: float | None = None
    far_right_x: float | None = None

    def __post_init__(self) -> None:
        if self.image_width <= 0.0:
            raise ValueError("image_width must be positive")
        if not 0.0 <= self.left_x < self.right_x <= self.image_width:
            raise ValueError("boundaries must satisfy 0 <= left_x < right_x <= image_width")
        if (self.far_left_x is None) != (self.far_right_x is None):
            raise ValueError("far_left_x and far_right_x must be provided together")
        if self.far_left_x is not None and self.far_right_x is not None:
            if not 0.0 <= self.far_left_x < self.far_right_x <= self.image_width:
                raise ValueError(
                    "far boundaries must satisfy 0 <= far_left_x < far_right_x <= image_width"
                )

    @property
    def road_center_x(self) -> float:
        return (self.left_x + self.right_x) / 2.0

    @property
    def normalized_center_error(self) -> float:
        """Return -1..1; positive means the detected road center is to camera-right."""
        image_center_x = self.image_width / 2.0
        return (self.road_center_x - image_center_x) / image_center_x

    @property
    def normalized_heading_error(self) -> float | None:
        """Return positive when the road center ahead bends toward camera-right."""
        if self.far_left_x is None or self.far_right_x is None:
            return None
        far_center_x = (self.far_left_x + self.far_right_x) / 2.0
        image_center_x = self.image_width / 2.0
        return (far_center_x - self.road_center_x) / image_center_x


@dataclass(frozen=True)
class LineTrackingDecision:
    action: LineAction
    normalized_center_error: float | None
    normalized_heading_error: float | None
    reason: str


class LineTrackingCore:
    """Create a motor-independent tracking or stop decision."""

    def decide(
        self,
        boundaries: LineBoundaries | None,
        *,
        auto_drive_enabled: bool,
        operator_stop_requested: bool,
    ) -> LineTrackingDecision:
        if operator_stop_requested:
            return LineTrackingDecision(LineAction.STOP, None, None, "operator_stop")
        if not auto_drive_enabled:
            return LineTrackingDecision(LineAction.STOP, None, None, "auto_drive_disabled")
        if boundaries is None:
            return LineTrackingDecision(LineAction.STOP, None, None, "line_unavailable")
        if not boundaries.stable:
            return LineTrackingDecision(LineAction.STOP, None, None, "line_unstable")
        return LineTrackingDecision(
            LineAction.TRACK,
            boundaries.normalized_center_error,
            boundaries.normalized_heading_error,
            "line_stable",
        )
