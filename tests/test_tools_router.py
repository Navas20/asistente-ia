import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from tools import router as tools_router
from tools_engine import ToolResult


class ToolsRouterTests(unittest.TestCase):
    def setUp(self):
        self.token_patcher = patch.dict(os.environ, {"AUTH_TOKEN": "test-token-1234"})
        self.token_patcher.start()
        app = FastAPI()
        app.include_router(tools_router.router)
        self.client = TestClient(app)

    def tearDown(self):
        self.token_patcher.stop()

    def test_tools_endpoints_require_bearer_auth(self):
        response = self.client.get("/v5/tools")

        self.assertEqual(response.status_code, 401)

    def test_list_tools_is_generated_from_catalog(self):
        response = self.client.get(
            "/v5/tools",
            headers={"Authorization": "Bearer test-token-1234"},
        )

        self.assertEqual(response.status_code, 200)
        names = {tool["name"] for tool in response.json()["tools"]}
        self.assertEqual(names, {"nmap", "whois", "dig", "nslookup", "curl", "ping"})

    def test_generic_tool_endpoint_runs_supported_non_nmap_tool(self):
        result = ToolResult(success=True, stdout="WHOIS DATA")
        with patch.object(tools_router.tools_engine, "run_tool", return_value=result) as run:
            response = self.client.post(
                "/v5/tools/whois/run",
                headers={"Authorization": "Bearer test-token-1234"},
                json={"target": "example.com"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "completed")
        run.assert_called_once()

    def test_generic_tool_endpoint_rejects_raw_args(self):
        response = self.client.post(
            "/v5/tools/whois/run",
            headers={"Authorization": "Bearer test-token-1234"},
            json={"target": "example.com", "args": ["--help"]},
        )

        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
