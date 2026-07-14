from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import kali_server


class KaliServerTests(unittest.TestCase):
    def test_existing_phase3_tools_are_allowlisted(self):
        self.assertEqual(
            set(kali_server.ALLOWED_TOOLS),
            {"nmap", "whois", "dig", "nslookup", "curl", "ping"},
        )

    def test_run_request_rejects_timeout_outside_bounds(self):
        with self.assertRaises(ValidationError):
            kali_server.RunRequest(tool="whois", args=["example.com"], timeout=0)
        with self.assertRaises(ValidationError):
            kali_server.RunRequest(tool="whois", args=["example.com"], timeout=601)

    def test_run_request_rejects_oversized_argument_vector(self):
        with self.assertRaises(ValidationError):
            kali_server.RunRequest(tool="whois", args=["x"] * 65, timeout=10)

    @patch("kali_server.Path.exists", return_value=True)
    @patch("kali_server.subprocess.run")
    def test_run_tool_executes_allowlisted_non_nmap_as_argv(self, run, _exists):
        run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="WHOIS DATA", stderr=""
        )

        result = kali_server.run_tool(
            kali_server.RunRequest(
                tool="whois", args=["example.com"], timeout=10, task_id="TOOL1"
            )
        )

        run.assert_called_once_with(
            ["/usr/bin/whois", "example.com"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        self.assertTrue(result.success)
        self.assertEqual(result.stdout, "WHOIS DATA")
        self.assertEqual(result.task_id, "TOOL1")

    @patch("kali_server.Path.exists", return_value=True)
    @patch("kali_server.subprocess.run")
    def test_output_cap_applies_to_stdout_and_stderr(self, run, _exists):
        run.return_value = subprocess.CompletedProcess(
            args=[],
            returncode=1,
            stdout="x" * (kali_server.MAX_STDOUT + 1),
            stderr="y" * (kali_server.MAX_STDOUT + 1),
        )

        result = kali_server.run_tool(
            kali_server.RunRequest(tool="whois", args=["example.com"], timeout=10)
        )

        self.assertEqual(len(result.stdout), kali_server.MAX_STDOUT)
        self.assertEqual(len(result.stderr), kali_server.MAX_STDOUT)
        self.assertTrue(result.truncated)


if __name__ == "__main__":
    unittest.main()
