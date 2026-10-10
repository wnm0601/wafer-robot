"""Pure keyboard-to-mecanum-percent command policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import AbstractSet


@dataclass(frozen=True)
class MotionCommand:
    vx_percent: int
    vy_percent: int
    yaw_percent: int

    @property
    def is_zero(self) -> bool:
        return self.vx_percent == 0 and self.vy_percent == 0 and self.yaw_percent == 0

    def to_protocol_line(self) -> str:
        return f"V {self.vx_percent} {self.vy_percent} {self.yaw_percent}"


class KeyboardDrivePolicy:
    """Map held keys to the candidate firmware's V vx vy w percent convention."""

    def __init__(self, *, command_percent: int, host_limit_percent: int) -> None:
        if not 1 <= command_percent <= host_limit_percent <= 100:
            raise ValueError("expected 1 <= command_percent <= host_limit_percent <= 100")
        self.command_percent = command_percent
        self.host_limit_percent = host_limit_percent

    def command_for_keys(self, keys: AbstractSet[str]) -> MotionCommand:
        speed = self.command_percent
        forward = self._axis(keys, positive=("w", "up"), negative=("s", "down"))
        strafe = self._axis(keys, positive=("d",), negative=("a",))
        yaw = self._axis(keys, positive=("e", "right"), negative=("q", "left"))
        vx, vy, wz = self._limit_mecanum_mix(
            forward * speed,
            strafe * speed,
            yaw * speed,
        )
        return MotionCommand(
            vx_percent=vx,
            vy_percent=vy,
            yaw_percent=wz,
        )

    @staticmethod
    def _axis(
        keys: AbstractSet[str],
        *,
        positive: tuple[str, ...],
        negative: tuple[str, ...],
    ) -> int:
        positive_held = any(key in keys for key in positive)
        negative_held = any(key in keys for key in negative)
        return int(positive_held) - int(negative_held)

    def _limit_mecanum_mix(self, vx: int, vy: int, wz: int) -> tuple[int, int, int]:
        """Bound the largest possible wheel mix, not merely each input axis.

        Candidate firmware mixes the axes as signed sums. The conservative
        maximum wheel request is therefore abs(vx) + abs(vy) + abs(wz).
        """
        total = abs(vx) + abs(vy) + abs(wz)
        if total <= self.host_limit_percent:
            return vx, vy, wz

        scale = self.host_limit_percent / total
        scaled = [int(value * scale) for value in (vx, vy, wz)]
        remainder = self.host_limit_percent - sum(abs(value) for value in scaled)
        for index, value in enumerate((vx, vy, wz)):
            if remainder == 0:
                break
            if value != 0:
                scaled[index] += 1 if value > 0 else -1
                remainder -= 1
        return scaled[0], scaled[1], scaled[2]
