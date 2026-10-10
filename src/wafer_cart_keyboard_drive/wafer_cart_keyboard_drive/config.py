"""Validated options for dry-run and explicitly enabled motor operation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DriveOptions:
    command_percent: int
    host_limit_percent: int
    firmware_max_duty: int = 200
    heartbeat_hz: float = 20.0
    port: str | None = None
    baudrate: int = 115200
    enable_motors: bool = False
    wheels_clear_confirmed: bool = False

    def __post_init__(self) -> None:
        if not 1 <= self.command_percent <= 100:
            raise ValueError("command_percent must be in 1..100")
        if not 1 <= self.host_limit_percent <= 100:
            raise ValueError("host_limit_percent must be in 1..100")
        if self.command_percent > self.host_limit_percent:
            raise ValueError("command_percent must not exceed host_limit_percent")
        if not 1 <= self.firmware_max_duty <= 255:
            raise ValueError("firmware_max_duty must be in 1..255")
        if not 10.0 <= self.heartbeat_hz <= 100.0:
            raise ValueError("heartbeat_hz must be in 10..100 for the 500ms deadman")
        if self.baudrate <= 0:
            raise ValueError("baudrate must be positive")
        if self.enable_motors:
            if not self.port:
                raise ValueError("port is required when motors are enabled")
            if not self.wheels_clear_confirmed:
                raise ValueError("wheels-clear confirmation is required when motors are enabled")
            raise ValueError("Real serial mode is locked pending PCB-C/firmware/power preflight; use mock")

    @property
    def estimated_host_limited_duty(self) -> int:
        """Match the candidate firmware's integer percent-to-MAX_DUTY conversion."""
        return int(self.host_limit_percent * self.firmware_max_duty / 100.0)

    @property
    def estimated_command_duty(self) -> int:
        return int(self.command_percent * self.firmware_max_duty / 100.0)
