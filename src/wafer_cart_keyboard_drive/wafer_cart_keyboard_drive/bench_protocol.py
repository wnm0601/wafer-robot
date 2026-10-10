"""Versioned, session/sequence-bound ASCII bench protocol, CRC16-CCITT-FALSE."""
from __future__ import annotations

import binascii
import re

MAX_FRAME = 239
SESSION = re.compile(r"[0-9a-f]{16}\Z")
OPS = {"HELLO": 0, "INFO": 0, "STATUS": 0, "ENC": 0, "LIMIT": 1,
       "ARM": 0, "POWER_ACK": 0, "STOP": 0, "ESTOP": 0, "M": 2, "V": 3,
       "DIAG": 0, "IO": 0}


class ProtocolError(RuntimeError):
    pass


def frame(payload: str) -> bytes:
    if not payload or any(not 32 <= ord(c) <= 126 for c in payload):
        raise ProtocolError("non-ASCII/control character in frame")
    raw = payload.encode("ascii")
    result = raw + f" *{binascii.crc_hqx(raw, 0xffff):04X}\n".encode("ascii")
    if len(result) - 1 > MAX_FRAME:
        raise ProtocolError("oversize frame")
    return result


def unframe(raw: bytes) -> list[str]:
    if not isinstance(raw, bytes) or not raw.endswith(b"\n") or len(raw) > MAX_FRAME + 1:
        raise ProtocolError("missing delimiter or oversize frame")
    raw = raw[:-1]
    if raw.endswith(b"\r"):
        raw = raw[:-1]
    try:
        payload, checksum = raw.rsplit(b" *", 1)
        if (not re.fullmatch(rb"[0-9A-F]{4}", checksum)
                or binascii.crc_hqx(payload, 0xffff) != int(checksum, 16)):
            raise ProtocolError("checksum mismatch")
        text = payload.decode("ascii")
    except (UnicodeError, ValueError) as error:
        raise ProtocolError("malformed frame") from error
    if not text or any(not 32 <= ord(c) <= 126 for c in text):
        raise ProtocolError("control character in frame")
    return text.split()


def request(session: str, sequence: int, operation: str, *values: int, max_percent: int = 30) -> bytes:
    if (not SESSION.fullmatch(session) or type(sequence) is not int
            or not 1 <= sequence <= 0xffffffff or operation not in OPS
            or len(values) != OPS[operation] or any(type(v) is not int for v in values)):
        raise ProtocolError("invalid request")
    if max_percent not in (30, 40):
        raise ProtocolError("invalid protocol ceiling")
    if operation == "LIMIT" and not 1 <= values[0] <= max_percent:
        raise ProtocolError("invalid limit")
    if operation == "M" and (not 1 <= values[0] <= 4 or abs(values[1]) > max_percent):
        raise ProtocolError("invalid motor/percentage")
    if operation == "V" and any(abs(v) > max_percent for v in values):
        raise ProtocolError("invalid vector percentage")
    return frame(" ".join(map(str, ("C2", session, sequence, operation, *values))))
