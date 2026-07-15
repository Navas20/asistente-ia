import ast
import socket
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import dns.resolver


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from playbooks import list_playbooks, run_playbook
from hacking import network as network_hacking
from hacking import web as web_hacking
from task_queue import TaskQueue


class PlaybookResultContractTests(unittest.TestCase):
    @staticmethod
    def _web_hacking_module():
        return SimpleNamespace(
            dns_enum=Mock(return_value={"A": ["93.184.216.34"]}),
            subdomain_scan=Mock(return_value=["www.example.com"]),
            scan_ports=Mock(return_value={"open_ports": []}),
            detect_tech=Mock(
                return_value={"status": 200, "headers": {"Server": "test"}}
            ),
            dir_bruteforce=Mock(return_value={"found": []}),
            screenshot=Mock(return_value={"success": True}),
            ssl_check=Mock(return_value={"valid": True, "error": ""}),
            check_sqli=Mock(return_value={"vulnerable": False}),
            check_xss=Mock(return_value={"vulnerable": False}),
            check_lfi=Mock(return_value={"vulnerable": False}),
        )

    def test_dns_enum_distinguishes_transport_failure_from_no_answer(self):
        with patch.object(
            dns.resolver,
            "resolve",
            side_effect=TimeoutError("resolver unavailable"),
        ):
            failed = network_hacking.dns_enum("example.com")

        self.assertIn("resolver unavailable", failed.get("error", ""))
        self.assertEqual(
            failed.get("failed_record_types"),
            ["A", "AAAA", "MX", "NS", "TXT", "SOA", "CNAME"],
        )

        with patch.object(
            dns.resolver,
            "resolve",
            side_effect=dns.resolver.NoAnswer(),
        ):
            empty = network_hacking.dns_enum("example.com")

        self.assertNotIn("error", empty)
        self.assertTrue(all(records == [] for records in empty.values()))

    def test_subdomain_scan_distinguishes_transport_failure_from_no_name(self):
        with patch.object(
            network_hacking.socket,
            "getaddrinfo",
            side_effect=socket.gaierror(
                socket.EAI_AGAIN, "temporary resolver failure"
            ),
        ):
            failed = network_hacking.subdomain_scan(
                "example.com", ["www", "api"]
            )

        self.assertIsInstance(failed, dict)
        self.assertEqual(failed.get("found"), [])
        self.assertEqual(failed.get("failed_lookups"), 2)
        self.assertIn("temporary resolver failure", failed.get("error", ""))

        with patch.object(
            network_hacking.socket,
            "getaddrinfo",
            side_effect=socket.gaierror(
                socket.EAI_NONAME, "name does not exist"
            ),
        ):
            empty = network_hacking.subdomain_scan(
                "example.com", ["www", "api"]
            )

        self.assertEqual(empty, [])

    def test_dns_enum_preserves_mixed_records_as_partial_success(self):
        def mixed_resolution(domain, record_type, lifetime):
            if record_type == "A":
                return ["93.184.216.34"]
            if record_type == "AAAA":
                raise TimeoutError("resolver unavailable")
            raise dns.resolver.NoAnswer()

        with patch.object(
            dns.resolver,
            "resolve",
            side_effect=mixed_resolution,
        ):
            result = network_hacking.dns_enum("example.com")

        self.assertNotIn("error", result)
        self.assertEqual(result["A"], ["93.184.216.34"])
        self.assertEqual(result["failed_record_types"], ["AAAA"])
        self.assertEqual(
            result["completed_record_types"],
            ["A", "MX", "NS", "TXT", "SOA", "CNAME"],
        )
        self.assertTrue(result["partial"])
        self.assertIn("resolver unavailable", " ".join(result["warnings"]))

    def test_subdomain_scan_preserves_mixed_results_as_partial_success(self):
        def mixed_resolution(host, *args, **kwargs):
            if host == "www.example.com":
                return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ())]
            if host == "api.example.com":
                raise socket.gaierror(
                    socket.EAI_AGAIN, "temporary resolver failure"
                )
            raise socket.gaierror(socket.EAI_NONAME, "name does not exist")

        with patch.object(
            network_hacking.socket,
            "getaddrinfo",
            side_effect=mixed_resolution,
        ):
            result = network_hacking.subdomain_scan(
                "example.com", ["www", "api", "missing"]
            )

        self.assertIsInstance(result, dict)
        self.assertNotIn("error", result)
        self.assertEqual(result["found"], ["www.example.com"])
        self.assertEqual(result["completed_lookups"], 2)
        self.assertEqual(result["failed_lookups"], 1)
        self.assertTrue(result["partial"])
        self.assertIn("api.example.com", " ".join(result["warnings"]))

    def test_hacking_full_smoke_normalizes_subdomain_result_before_slicing(self):
        smoke_path = Path(__file__).resolve().parents[1] / "test_hacking_full.py"
        tree = ast.parse(smoke_path.read_text(encoding="utf-8"))
        assignment = next(
            (
                node
                for node in tree.body
                if isinstance(node, ast.Assign)
                and any(
                    isinstance(target, ast.Name)
                    and target.id == "subdomains"
                    for target in node.targets
                )
            ),
            None,
        )

        self.assertIsNotNone(assignment)
        expression = ast.Expression(body=assignment.value)
        ast.fix_missing_locations(expression)
        preview = compile(expression, str(smoke_path), "eval")
        self.assertEqual(
            eval(preview, {"res": {"found": ["www.example.com"]}}),
            ["www.example.com"],
        )
        self.assertEqual(
            eval(preview, {"res": ["www.example.com"]}),
            ["www.example.com"],
        )

    def test_recon_web_metadata_requires_absolute_url(self):
        self.assertEqual(list_playbooks()["recon_web"]["target_type"], "url")

    def test_recon_web_routes_canonical_url_by_tool_contract(self):
        target = "https://example.com:8443/search?q=1"
        hacking_module = self._web_hacking_module()

        result = run_playbook(
            "recon_web",
            target,
            hacking_module=hacking_module,
        )

        hacking_module.dns_enum.assert_called_once_with("example.com")
        hacking_module.subdomain_scan.assert_called_once_with("example.com")
        hacking_module.scan_ports.assert_called_once_with("example.com")
        hacking_module.detect_tech.assert_called_once_with(target)
        hacking_module.dir_bruteforce.assert_called_once_with(target)
        self.assertEqual(result["target"], target)
        self.assertNotIn("error", result)

    def test_web_audit_routes_url_host_port_and_query_parameter(self):
        target = "https://example.com:8443/search?q=1"
        hacking_module = self._web_hacking_module()

        result = run_playbook(
            "web_audit",
            target,
            hacking_module=hacking_module,
        )

        self.assertEqual(
            hacking_module.detect_tech.call_args_list,
            [call(target), call(target)],
        )
        hacking_module.screenshot.assert_called_once_with(target)
        hacking_module.ssl_check.assert_called_once_with("example.com", 8443)
        hacking_module.check_sqli.assert_called_once_with(target, "q")
        hacking_module.check_xss.assert_called_once_with(target, "q")
        hacking_module.check_lfi.assert_called_once_with(target, "q")
        hacking_module.dir_bruteforce.assert_called_once_with(target)
        self.assertEqual(result["target"], target)
        self.assertNotIn("error", result)

    def test_web_audit_uses_first_query_key_with_q_fallback(self):
        cases = (
            ("https://example.com/search?term=one&q=two", "term"),
            ("https://example.com/search", "q"),
        )

        for target, expected_param in cases:
            with self.subTest(target=target):
                hacking_module = self._web_hacking_module()

                run_playbook(
                    "web_audit",
                    target,
                    hacking_module=hacking_module,
                )

                hacking_module.check_sqli.assert_called_once_with(
                    target, expected_param
                )
                hacking_module.check_xss.assert_called_once_with(
                    target, expected_param
                )
                hacking_module.check_lfi.assert_called_once_with(
                    target, expected_param
                )

    def test_detect_tech_reports_status_zero_as_transport_failure(self):
        with patch.object(
            web_hacking,
            "_http_get",
            return_value=(0, {}, "connection refused"),
        ):
            result = web_hacking.detect_tech("https://example.com")

        self.assertEqual(result["status"], 0)
        self.assertIn("connection refused", result.get("error", ""))

    def test_web_probes_report_when_every_request_has_transport_failure(self):
        probes = (
            web_hacking.check_sqli,
            web_hacking.check_xss,
            web_hacking.check_lfi,
        )

        for probe in probes:
            with self.subTest(probe=probe.__name__), patch.object(
                web_hacking,
                "_http_get",
                return_value=(0, {}, "network unreachable"),
            ):
                result = probe("https://example.com/search?q=1", "q")

            self.assertIn("network unreachable", result.get("error", ""))

    def test_dir_bruteforce_reports_when_every_request_transport_fails(self):
        with patch.object(
            web_hacking.urllib.request,
            "urlopen",
            side_effect=OSError("network down"),
        ):
            result = web_hacking.dir_bruteforce(
                "https://example.com", ["admin", "login"]
            )

        self.assertEqual(result["found"], [])
        self.assertEqual(result.get("failed_requests"), 2)
        self.assertIn("network down", result.get("error", ""))

    def test_all_failed_playbook_returns_aggregate_error(self):
        failed = Mock(return_value={"error": "transport unavailable"})
        hacking_module = SimpleNamespace(
            dns_enum=failed,
            subdomain_scan=failed,
            scan_ports=failed,
            detect_tech=failed,
            dir_bruteforce=failed,
        )

        result = run_playbook(
            "recon_web",
            "https://example.com",
            hacking_module=hacking_module,
        )

        self.assertTrue(all(not step["success"] for step in result["results"]))
        self.assertIn("Todos los pasos", result.get("error", ""))

    def test_task_queue_fails_playbook_with_aggregate_error(self):
        queue = TaskQueue.__new__(TaskQueue)
        queue.update_progress = Mock()
        queue.complete = Mock()
        queue.fail = Mock()
        result = {
            "error": "Todos los pasos del playbook fallaron",
            "results": [{"success": False, "note": "network down"}],
        }

        with patch("playbooks.run_playbook", return_value=result):
            queue._run_playbook_task(
                "WEB01",
                "https://example.com",
                {"playbook": "web_audit", "depth": "profundo"},
            )

        queue.fail.assert_called_once_with("WEB01", result["error"])
        queue.complete.assert_not_called()

    def test_osint_domain_marks_returned_error_contracts_as_failed(self):
        hacking_module = SimpleNamespace(
            dns_enum=lambda target: {"error": "DNS unavailable"},
            subdomain_scan=lambda target: ["www.example.com"],
            cert_transparency=lambda target: [
                "Error: certificate service unavailable"
            ],
            ip_geo=lambda target: "Error: geolocation unavailable",
        )

        result = run_playbook(
            "osint_domain",
            "example.com",
            hacking_module=hacking_module,
        )

        steps = {step["step_id"]: step for step in result["results"]}
        self.assertFalse(steps["dns"]["success"])
        self.assertEqual(steps["dns"]["note"], "DNS unavailable")
        self.assertFalse(steps["certs"]["success"])
        self.assertEqual(
            steps["certs"]["note"],
            "Error: certificate service unavailable",
        )
        self.assertFalse(steps["geo"]["success"])
        self.assertEqual(
            steps["geo"]["note"], "Error: geolocation unavailable"
        )
        self.assertTrue(steps["subdomains"]["success"])
        self.assertNotIn("error", result)
        self.assertIn("[SKIP] Enumeration DNS - DNS unavailable", result["summary"])
        self.assertNotIn("[OK] Enumeration DNS", result["summary"])


if __name__ == "__main__":
    unittest.main()
