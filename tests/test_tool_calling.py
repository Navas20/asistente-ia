from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from tools_engine import TOOL_SPECS, TOOL_SCAN_TYPES, ToolResult, build_openai_tools, parse_tool_call


class TestBuildOpenaiTools(unittest.TestCase):
    def test_cubiertas_todas_las_tools(self):
        tools = build_openai_tools()
        self.assertEqual(len(tools), len(TOOL_SPECS))
        names = {t["function"]["name"] for t in tools}
        self.assertEqual(names, set(TOOL_SPECS))

    def test_formato_openai(self):
        tools = build_openai_tools()
        for t in tools:
            self.assertEqual(t["type"], "function")
            fn = t["function"]
            self.assertIn("name", fn)
            self.assertIn("description", fn)
            self.assertEqual(fn["parameters"]["type"], "object")
            self.assertIsInstance(fn["parameters"]["properties"], dict)

    def test_nmap_schema_target_requerido_y_profile_enum(self):
        tools = {t["function"]["name"]: t["function"] for t in build_openai_tools()}
        nmap = tools["nmap"]
        self.assertIn("target", nmap["parameters"]["required"])
        self.assertEqual(nmap["parameters"]["properties"]["profile"]["enum"], list(TOOL_SCAN_TYPES))

    def test_msfvenom_sin_target(self):
        tools = {t["function"]["name"]: t["function"] for t in build_openai_tools()}
        msf = tools["msfvenom"]
        self.assertNotIn("target", msf["parameters"].get("required", []))

    def test_filtro_parcial(self):
        tools = build_openai_tools(["ping"])
        self.assertEqual([t["function"]["name"] for t in tools], ["ping"])


class TestParseToolCall(unittest.TestCase):
    def test_mapeo_nmap(self):
        parsed = parse_tool_call("nmap", {"target": "scanme.nmap.org", "profile": "quick", "timeout": 60})
        self.assertEqual(parsed, ("nmap", "scanme.nmap.org", "quick", {}, 60))

    def test_defaults_si_faltan_args(self):
        parsed = parse_tool_call("whois", {"target": "example.com"})
        self.assertEqual(parsed[0], "whois")
        self.assertEqual(parsed[1], "example.com")
        self.assertEqual(parsed[2], "default")
        self.assertEqual(parsed[3], {})
        self.assertIsNone(parsed[4])

    def test_tool_desconocida_retorna_none(self):
        self.assertIsNone(parse_tool_call("rsync", {}))

    def test_args_no_dict(self):
        parsed = parse_tool_call("dig", None)
        self.assertEqual(parsed[1], "")


class FakeProviderChatOnly:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.messages_seen = []

    def chat(self, messages, tools=None, temperature=0.7):
        self.messages_seen.append((messages, tools))
        return self.responses.pop(0)


class TestChatToolLoop(unittest.TestCase):
    """Test del loop de ejecución: un tool_call -> se ejecuta -> se reporta en la respuesta."""

    def setUp(self):
        import main
        self.main = main
        self._tmp = tempfile.mkdtemp()
        main.DB_PATH = str(Path(self._tmp) / "conv.db")
        main._conn_local.conn = None
        main.init_db()

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_ejecuta_whois_y_lo_reporta_en_la_respuesta_final(self):
        resp1 = {"content": "", "tool_calls": [{"id": "call_abc", "name": "whois", "arguments": {"target": "example.com"}}]}
        resp2 = {"content": "El dominio es example.com.", "tool_calls": None}
        provider = FakeProviderChatOnly(resp1, resp2)

        with patch.object(self.main, "_get_provider", return_value=provider), \
             patch.object(self.main, "tool_engine") as eng, \
             patch.object(self.main, "trigger_memory_extraction", return_value=None):
            eng.run_tool.return_value = ToolResult(success=True, stdout="Registrant: RESERVED-Internet Assigned Numbers Authority\n")

            result = self.main._run_tool_loop("test-conv", "corre un whois a example.com")

        self.assertTrue(result["tool_executed"])
        self.assertEqual(result["tool_command"], "whois")
        self.assertIn("Registrant", result["tool_output"])
        eng.run_tool.assert_called_once()
        self.assertEqual(provider.messages_seen[0][1], build_openai_tools())

    def test_respuesta_sin_tools_no_ejecuta_nada(self):
        provider = FakeProviderChatOnly({"content": "Hola.", "tool_calls": None})
        with patch.object(self.main, "_get_provider", return_value=provider), \
             patch.object(self.main, "trigger_memory_extraction", return_value=None):
            result = self.main._run_tool_loop("test-conv", "hola")
        self.assertFalse(result["tool_executed"])
        self.assertIsNone(result["tool_command"])

    def test_tool_call_a_herramienta_desconocida_genera_error(self):
        resp1 = {"content": "", "tool_calls": [{"id": "c1", "name": "rsync", "arguments": {"target": "x"}}]}
        resp2 = {"content": "No sé usar eso.", "tool_calls": None}
        provider = FakeProviderChatOnly(resp1, resp2)
        with patch.object(self.main, "_get_provider", return_value=provider), \
             patch.object(self.main, "tool_engine") as eng, \
             patch.object(self.main, "trigger_memory_extraction", return_value=None):
            result = self.main._run_tool_loop("test-conv", "usá rsync fíjate")
        eng.run_tool.assert_not_called()
        self.assertFalse(result["tool_executed"])


if __name__ == "__main__":
    unittest.main()