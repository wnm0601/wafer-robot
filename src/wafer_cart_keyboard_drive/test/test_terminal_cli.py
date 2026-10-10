import subprocess
import sys
import unittest
from pathlib import Path


class TerminalCliTest(unittest.TestCase):
    def test_stop_cycle_and_rearm_in_ros_free_terminal(self):
        root = Path(__file__).resolve().parents[3]
        result = subprocess.run([sys.executable, str(root / "scripts/terminal_mock.py"),
            "--commands", "w,power on,status,resume,w,estop,w,resume,w,power off,power on,resume,w,stop,w,quit"],
            capture_output=True, text=True, encoding="utf-8", timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count("MOCK_TX V 20 0 0"), 2)
        self.assertIn('"state": "ESTOP"', result.stdout)
        self.assertIn('"motor_enabled": false', result.stdout)

    def test_terminal_has_no_motor_enable_or_port_option(self):
        root = Path(__file__).resolve().parents[3]
        result = subprocess.run([sys.executable, str(root / "scripts/terminal_mock.py"),
            "--enable-motors"], capture_output=True, text=True, encoding="utf-8", timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unrecognized arguments", result.stderr)
