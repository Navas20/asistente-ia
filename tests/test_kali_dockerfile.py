from pathlib import Path
import unittest


class KaliDockerfileTests(unittest.TestCase):
    def test_runtime_switches_to_toolrunner_after_copy(self):
        dockerfile = (
            Path(__file__).resolve().parents[1] / "docker" / "kali.Dockerfile"
        ).read_text(encoding="utf-8")

        self.assertIn("USER toolrunner", dockerfile)
        self.assertGreater(dockerfile.index("USER toolrunner"), dockerfile.index("COPY backend/kali_server.py"))
        self.assertLess(dockerfile.index("USER toolrunner"), dockerfile.index("CMD ["))

    def test_phase3_runtime_packages_are_declared(self):
        dockerfile = (
            Path(__file__).resolve().parents[1] / "docker" / "kali.Dockerfile"
        ).read_text(encoding="utf-8")

        for package in ("nmap", "dnsutils", "whois", "iputils-ping", "curl"):
            with self.subTest(package=package):
                self.assertIn(package, dockerfile)


if __name__ == "__main__":
    unittest.main()
