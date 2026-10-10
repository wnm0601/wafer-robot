"""Local process wire for the real C++ Controller; never opens a device."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import queue
import subprocess
import threading


def linux_path(path: Path) -> str:
    if os.name != "nt":
        return str(path)
    return "/mnt/" + path.drive[0].lower() + path.as_posix()[2:]


def build_host(root: Path, *, unmonitored=False) -> tuple[Path, str]:
    sources = [root / "firmware/mega_cart/src/cart_controller.cpp",
               root / "firmware/mega_cart/include/cart_controller.h",
               root / "firmware/mega_cart/test/simulator_wire.cpp"]
    digest = hashlib.sha256(b"".join(p.read_bytes() for p in sources) + str(unmonitored).encode()).hexdigest()
    output = root / ('data/output/bench_build/simulator_wire_40' if unmonitored else 'data/output/bench_build/simulator_wire')
    manifest = output.with_suffix(".json")
    if output.is_file() and manifest.is_file():
        try:
            previous = json.loads(manifest.read_text(encoding="utf-8"))
        except (ValueError,OSError):
            previous = {}
        if (previous.get("source_sha256") == digest and previous.get("executable_sha256") ==
                hashlib.sha256(output.read_bytes()).hexdigest()):
            return output, digest
    output.parent.mkdir(parents=True, exist_ok=True)
    command = ["g++", "-std=c++11", "-Wall", "-Wextra", "-Werror", "-O2",
               "-I", linux_path(sources[1].parent), linux_path(sources[0]),
               linux_path(sources[2]), "-o", linux_path(output)]
    if unmonitored:command.insert(1,'-DCART_PROTOCOL_MAX_PERCENT=40')
    if os.name == "nt":
        command = ["wsl", "-d", "Ubuntu-24.04", "--", *command]
    result = subprocess.run(command, capture_output=True, timeout=60)
    if result.returncode:
        raise RuntimeError("PC 펌웨어 빌드 실패: " + result.stderr.decode("utf-8", errors="replace"))
    # A build manifest, not a physical measurement or device identity.
    manifest.write_text(json.dumps({"source_sha256": digest, "hardware": False,
        "executable_sha256": hashlib.sha256(output.read_bytes()).hexdigest()}), encoding="utf-8")
    return output, digest


class FirmwareSimulatorWire:
    """Bounded queue interface; pipe workers only serve a local simulation child."""
    simulation_fixture = True

    def __init__(self, root: Path, *, manual_fixture=False, unmonitored=False):
        if manual_fixture and unmonitored:raise ValueError('fixture modes are mutually exclusive')
        executable, self.source_sha256 = build_host(root,unmonitored=unmonitored)
        command = [str(executable)]
        if os.name == "nt":
            command = ["wsl", "-d", "Ubuntu-24.04", "--", linux_path(executable)]
        if manual_fixture:command.append('--manual-fixture')
        if unmonitored:command.append('--unmonitored-fixture')
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, bufsize=0, creationflags=flags)
        self._received = queue.Queue()
        self._outgoing = queue.Queue(maxsize=32)
        self.closed = False
        self.sent = []
        self._pump = threading.Thread(target=self._read_pipe, daemon=True)
        self._writer = threading.Thread(target=self._write_pipe, daemon=True)
        self._pump.start()
        self._writer.start()
        try:
            ready = self._received.get(timeout=15)
            if isinstance(ready, BaseException):
                raise ready
            tokens = ready.decode("ascii").strip().split()
            if len(tokens) != 2 or tokens[0] != "SIM_HOST_READY":
                raise RuntimeError("펌웨어 시뮬레이터 시작 응답 불일치")
            self.duty_scale = int(tokens[1])
            if self.duty_scale <= 0:
                raise RuntimeError("invalid simulator duty scale")
        except Exception:
            self.close()
            raise

    def _read_pipe(self):
        try:
            while not self.closed:
                raw = self.process.stdout.readline()
                if not raw:
                    raise OSError("펌웨어 시뮬레이터가 종료됐습니다")
                self._received.put(raw)
        except Exception as error:
            self._received.put(error)

    def _write_pipe(self):
        try:
            while not self.closed:
                raw = self._outgoing.get()
                if raw is None:
                    return
                self.process.stdin.write(raw)
                self.process.stdin.flush()
        except Exception as error:
            self._received.put(error)

    def write(self, raw: bytes):
        if self.closed or self.process.poll() is not None:
            raise OSError("simulator closed")
        self.sent.append(raw)
        del self.sent[:-200]
        self._outgoing.put_nowait(raw)

    def readline(self) -> bytes:
        try:
            item = self._received.get(timeout=0.02)
        except queue.Empty:
            return b""
        if isinstance(item, BaseException):
            raise item
        return item

    def power_feedback(self, on: bool, *, estop: bool = False):
        self.write(f"@power {int(on)} {int(estop)}\n".encode("ascii"))

    def encoder_feedback(self, counts):
        if len(counts) != 4 or any(type(v) is not int or not -2**31 <= v < 2**31 for v in counts):
            raise ValueError("invalid virtual encoder counts")
        self.write(("@counts " + " ".join(map(str, counts)) + "\n").encode("ascii"))

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self._outgoing.put_nowait(None)
        except queue.Full:
            pass
        if self.process.poll() is None:
            self.process.terminate()
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=2)
        self._writer.join(timeout=0.5)
        self._pump.join(timeout=0.5)
        self.process.stdin.close()
        self.process.stdout.close()
