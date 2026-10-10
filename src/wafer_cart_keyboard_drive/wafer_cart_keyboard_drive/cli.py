"""VSCode/Windows keyboard driving beta; DRY-RUN unless explicitly enabled."""

from __future__ import annotations

import argparse
import threading
import time

from .config import DriveOptions
from .policy import KeyboardDrivePolicy
from .transport import DriveTransport, DryRunTransport, SerialTransport


class KeyboardState:
    """Thread-safe held-key state populated by pynput callbacks."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pressed: set[str] = set()
        self.stop_requested = threading.Event()
        self.estop_requested = threading.Event()
        self.exit_requested = threading.Event()

    @staticmethod
    def normalize(key: object) -> str | None:
        char = getattr(key, "char", None)
        if isinstance(char, str):
            return char.lower()
        name = getattr(key, "name", None)
        if name in {"up", "down", "left", "right"}:
            return str(name)
        return None

    def on_press(self, key: object) -> bool | None:
        name = getattr(key, "name", None)
        char = getattr(key, "char", None)
        if name == "esc":
            self.exit_requested.set()
            return False
        if name == "space":
            with self._lock:
                self._pressed.clear()
            self.stop_requested.set()
            return None
        if isinstance(char, str) and char.lower() == "x":
            with self._lock:
                self._pressed.clear()
            self.estop_requested.set()
            return False
        normalized = self.normalize(key)
        if normalized is not None:
            with self._lock:
                self._pressed.add(normalized)
        return None

    def on_release(self, key: object) -> None:
        normalized = self.normalize(key)
        if normalized is not None:
            with self._lock:
                self._pressed.discard(normalized)

    def snapshot(self) -> set[str]:
        with self._lock:
            return set(self._pressed)


def run_keyboard_loop(options: DriveOptions, transport: DriveTransport) -> None:
    from pynput import keyboard

    policy = KeyboardDrivePolicy(
        command_percent=options.command_percent,
        host_limit_percent=options.host_limit_percent,
    )
    state = KeyboardState()
    period_sec = 1.0 / options.heartbeat_hz
    motion_active = False
    estop_sent = False

    print("W/S=전후, A/D=좌우 횡이동, Q/E=좌/우 회전")
    print("Space=일반 감속정지, X=ESTOP, Esc=감속정지 후 종료")
    transport.send_stop()
    listener = keyboard.Listener(on_press=state.on_press, on_release=state.on_release)
    listener.start()
    try:
        while not state.exit_requested.is_set():
            loop_started = time.monotonic()
            if state.estop_requested.is_set():
                transport.send_estop()
                estop_sent = True
                break
            if state.stop_requested.is_set():
                state.stop_requested.clear()
                transport.send_stop()
                motion_active = False

            command = policy.command_for_keys(state.snapshot())
            if command.is_zero:
                if motion_active:
                    transport.send_stop()
                    motion_active = False
            else:
                transport.send_motion(command)
                motion_active = True

            elapsed = time.monotonic() - loop_started
            time.sleep(max(0.0, period_sec - elapsed))
    except Exception:
        try:
            transport.send_estop()
            estop_sent = True
        finally:
            raise
    finally:
        listener.stop()
        if not estop_sent:
            transport.send_stop()
        transport.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--enable-motors", action="store_true")
    parser.add_argument("--port", help="motor controller COM port, required for real motor mode")
    parser.add_argument("--baudrate", type=int, default=115200)
    parser.add_argument("--command-percent", type=int)
    parser.add_argument("--host-limit-percent", type=int)
    parser.add_argument("--firmware-max-duty", type=int, default=200)
    parser.add_argument("--heartbeat-hz", type=float, default=20.0)
    parser.add_argument(
        "--confirm-wheels-clear",
        action="store_true",
        help="required guard after physically lifting/clearing all wheels",
    )
    return parser


def options_from_args(args: argparse.Namespace) -> DriveOptions:
    if args.enable_motors:
        if args.command_percent is None or args.host_limit_percent is None:
            raise ValueError(
                "real motor mode requires --command-percent and --host-limit-percent"
            )
        command_percent = args.command_percent
        host_limit_percent = args.host_limit_percent
    else:
        command_percent = args.command_percent or 20
        host_limit_percent = args.host_limit_percent or command_percent
    return DriveOptions(
        command_percent=command_percent,
        host_limit_percent=host_limit_percent,
        firmware_max_duty=args.firmware_max_duty,
        heartbeat_hz=args.heartbeat_hz,
        port=args.port,
        baudrate=args.baudrate,
        enable_motors=args.enable_motors,
        wheels_clear_confirmed=args.confirm_wheels_clear,
    )


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        options = options_from_args(args)
    except ValueError as exc:
        parser.error(str(exc))

    mode = "REAL MOTOR" if options.enable_motors else "DRY-RUN"
    print(f"mode={mode}")
    print(
        f"command={options.command_percent}% host_limit={options.host_limit_percent}% "
        f"estimated_command_duty={options.estimated_command_duty}/255 "
        f"estimated_limit_duty={options.estimated_host_limited_duty}/255"
    )
    if options.enable_motors:
        assert options.port is not None
        transport: DriveTransport = SerialTransport(
            port=options.port,
            baudrate=options.baudrate,
        )
    else:
        transport = DryRunTransport()
    run_keyboard_loop(options, transport)


if __name__ == "__main__":
    main()
