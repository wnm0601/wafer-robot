"""Dry-run and serial transports for the keyboard driving beta."""

from __future__ import annotations

import time
from typing import Protocol

from .policy import MotionCommand


class DriveTransport(Protocol):
    def send_motion(self, command: MotionCommand) -> None: ...

    def send_stop(self) -> None: ...

    def send_estop(self) -> None: ...

    def close(self) -> None: ...


class DryRunTransport:
    """Print commands without opening any serial device."""

    def __init__(self) -> None:
        self.last_line: str | None = None

    def _show(self, line: str) -> None:
        if line != self.last_line:
            print(f"[DRY-RUN] {line}")
            self.last_line = line

    def send_motion(self, command: MotionCommand) -> None:
        self._show(command.to_protocol_line())

    def send_stop(self) -> None:
        self._show("STOP")

    def send_estop(self) -> None:
        self._show("ESTOP")

    def close(self) -> None:
        return


class SerialTransport:
    """Single-owner serial transport; constructed only after explicit motor enable."""

    def __init__(self, *, port: str, baudrate: int, startup_timeout_sec: float = 4.0) -> None:
        import serial

        self._serial = serial.Serial(
            port=port,
            baudrate=baudrate,
            timeout=0.15,
            write_timeout=0.25,
        )
        try:
            self._wait_for_ready(startup_timeout_sec)
            self.send_stop()
        except Exception:
            self._serial.close()
            raise

    def _wait_for_ready(self, timeout_sec: float) -> None:
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            line = self._serial.readline().decode("ascii", errors="replace").strip()
            if line == "READY":
                return
        raise TimeoutError("firmware READY was not received")

    def _exchange(self, line: str, expected_prefix: str) -> None:
        self._serial.write((line + "\n").encode("ascii"))
        self._serial.flush()
        deadline = time.monotonic() + 0.35
        while time.monotonic() < deadline:
            response = self._serial.readline().decode("ascii", errors="strict").strip()
            if not response:
                continue
            if response.startswith(("FAULT ", "ERR ", "EVENT ")):
                raise RuntimeError(f"firmware fault/event: {response!r}")
            if response == expected_prefix:
                return
            # Unknown, stale or malformed responses must not acknowledge motion.
            raise RuntimeError(f"unexpected firmware response: {response!r}")
        raise TimeoutError("firmware acknowledgment timed out")

    def send_motion(self, command: MotionCommand) -> None:
        self._exchange(command.to_protocol_line(), "OK V")

    def send_stop(self) -> None:
        self._exchange("STOP", "OK STOP")

    def send_estop(self) -> None:
        self._exchange("ESTOP", "OK ESTOP")

    def close(self) -> None:
        self._serial.close()
