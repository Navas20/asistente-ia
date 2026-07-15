from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

import tools_engine


class ToolsEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = tools_engine.ToolsEngine("http://kali.test:9001")
        self.engine._client = Mock()

    def test_run_tool_posts_generic_non_nmap_payload_and_maps_result(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "success": True,
            "stdout": "WHOIS DATA",
            "stderr": "",
            "exit_code": 0,
            "parsed": None,
            "elapsed": 0.2,
            "truncated": False,
        }
        self.engine._client.post.return_value = response

        result = self.engine.run_tool("whois", "example.com", user_id=7)

        self.assertTrue(result.success)
        self.assertEqual(result.stdout, "WHOIS DATA")
        payload = self.engine._client.post.call_args.kwargs["json"]
        self.assertEqual(payload["tool"], "whois")
        self.assertEqual(payload["args"], ["example.com"])
        self.assertEqual(payload["timeout"], 10)

    def test_run_tool_rejects_unknown_tool_without_http_request(self):
        result = self.engine.run_tool("shell", "example.com")

        self.assertFalse(result.success)
        self.assertIn("no soportada", result.error)
        self.engine._client.post.assert_not_called()

    def test_tool_result_does_not_silently_truncate_without_flag(self):
        output = "x" * 800
        result = tools_engine.ToolResult(success=True, stdout=output)

        serialized = result.to_dict()

        self.assertEqual(serialized["stdout"], output)
        self.assertFalse(serialized["truncated"])

    def test_run_nmap_delegates_to_generic_run_tool(self):
        expected = tools_engine.ToolResult(success=True)
        with patch.object(self.engine, "run_tool", return_value=expected) as run_tool:
            result = self.engine.run_nmap("scanme.nmap.org", "quick", user_id=9)

        self.assertIs(result, expected)
        run_tool.assert_called_once_with(
            "nmap",
            "scanme.nmap.org",
            profile="quick",
            options={"extra_args": []},
            timeout=None,
            user_id=9,
        )

    def test_validate_target_ipv6_cidrs_require_one_global_address(self):
        rejected = (
            "::/0",
            "2000::/3",
            "fc00::/6",
            "2001:4860:4860::/64",
            "::ffff:0:0/96",
            "::ffff:8.8.8.0/120",
            "::1/128",
            "fc00::/7",
            "fe80::/10",
            "ff00::/8",
            "ff00::1/128",
            "::ffff:192.168.1.1/128",
            "::ffff:127.0.0.1/128",
        )

        for target in rejected:
            with self.subTest(target=target):
                self.assertIsNotNone(tools_engine.validate_target(target))

        self.assertIsNone(
            tools_engine.validate_target("2001:4860:4860::8888")
        )
        self.assertIsNone(
            tools_engine.validate_target("2001:4860:4860::8888/128")
        )


if __name__ == "__main__":
    unittest.main()
