"""Python-generated CRC frames against the compiled C++ host oracle, no hardware."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src/wafer_cart_keyboard_drive"))
from wafer_cart_keyboard_drive.bench_protocol import frame, request, unframe


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, default=ROOT / "data/output/bench_build/host_wire")
    parser.add_argument("--report", type=Path, default=ROOT / "data/output/bench_contract.json")
    args = parser.parse_args()
    if not args.binary.resolve().is_relative_to((ROOT / "data/output").resolve()):
        parser.error("host oracle must be under this project's data/output")
    if not args.report.resolve().is_relative_to((ROOT / "data/output").resolve()):
        parser.error("report must be under this project's data/output")
    sid = "0123456789abcdef"
    records = []
    requests = ["@power 0 0\n", "@power 1 0\n"]
    expected = [None, None]
    operations = [("HELLO", (), ["CART_2", "HKX_20260929", "SIM_ONLY"]),
                  ("LIMIT", (20,), []), ("ARM", (), []), ("M", (1, 10), [])]
    seq = 0
    for op, values, result in operations:
        seq += 1
        requests.append(request(sid, seq, op, *values).decode("ascii"))
        expected.append((seq, op, "OK", result))
    requests.append("@advance 15\n"); expected.append(None)
    for op, values, result in (("STATUS", (), ["1", "READY_SIM_ONLY", "2", "1", "20", "2", "0", "0", "0"]),
                               ("ENC", (), ["15", "0", "0", "0", "0"]),
                               ("STOP", (), [])):
        seq += 1; requests.append(request(sid, seq, op, *values).decode("ascii"))
        expected.append((seq, op, "OK", result))
    requests.append("@advance 15\n"); expected.append(None)
    for op, values, status, result in (("ARM", (), "OK", []), ("M", (4, -20), "OK", []),
                                      ("ESTOP", (), "OK", []),
                                      ("ARM", (), "ERR", ["REARM_CONDITIONS"])):
        seq += 1; requests.append(request(sid, seq, op, *values).decode("ascii"))
        expected.append((seq, op, status, result))
    requests.extend(["@power 0 0\n", "@power 1 0\n"]); expected.extend([None, None])
    seq += 1; requests.append(request(sid, seq, "ARM").decode("ascii")); expected.append((seq, "ARM", "OK", []))
    # Structurally valid CRC but invalid percentage/arity must fault, not partially execute.
    seq += 1; requests.append(frame(f"C2 {sid} {seq} M 1 10 extra").decode("ascii"))
    expected.append((seq, "M", "ERR", ["BAD_OPERATION_OR_ARGS"]))
    result = subprocess.run([str(args.binary)], input="".join(requests).encode("ascii"),
                            capture_output=True, timeout=5, check=True)
    lines = result.stdout.splitlines(keepends=True)
    assert len(lines) == len(expected), (len(lines), len(expected), result.stderr)
    for i, (line, wanted) in enumerate(zip(lines, expected)):
        if wanted is None:
            assert line.strip() == b"HOST_OK"
            continue
        sequence, operation, status, data = wanted
        parsed = unframe(line)
        assert parsed == ["R2", sid, str(sequence), status, operation, *data], (i, parsed, wanted)
        records.append(dict(sequence=sequence, operation=operation, status=status, data=data))
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(dict(kind="python_to_cpp_host_contract", motor_enabled=False,
                                          measured=False, responses_verified=len(records), records=records), indent=2),
                           encoding="utf-8")
    print(f"PYTHON_CPP_CONTRACT_RESPONSES={len(records)} PASS; NO DEVICE OPENED")


if __name__ == "__main__":
    main()
