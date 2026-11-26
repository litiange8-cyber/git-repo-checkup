"""检测规则单元测试：覆盖四类检测与误报回归。

运行：cd backend && .venv/Scripts/python.exe -m unittest discover -s tests -v
"""
import unittest

from app.services.detector import (
    detect_all, detect_completeness, detect_hardcoded, detect_secrets, detect_windows,
)

WIN = chr(92)


class CompletenessTests(unittest.TestCase):
    def test_full_readme(self):
        files = [
            ("README.md", "# Demo\n## 项目介绍\n这是一个测试项目。\n## Quick Start\npip install -r requirements.txt"),
            ("requirements.txt", "requests==2.31.0"),
            ("start.sh", "python main.py"),
        ]
        cat, _ = detect_completeness(files)
        self.assertEqual(cat.score, cat.max_score)

    def test_missing_readme(self):
        cat, findings = detect_completeness([("main.py", "print('hi')")])
        self.assertLess(cat.score, cat.max_score)
        self.assertTrue(any("README" in f.message for f in findings))


class SecretsTests(unittest.TestCase):
    def _score(self, content, path="config.py"):
        return detect_secrets([(path, content)])[0].score

    def test_all_key_formats_detected(self):
        # 使用明显虚构的测试串（避免触发 GitHub Push Protection 的 secret 扫描）
        cases = [
            "sk-proj-AbCdEf1234567890GhIjKlMn",      # OpenAI 新版
            "AKIA1234567890ABCDEF",                   # AWS
            "ghp_" + "A" * 36,                        # GitHub Classic（拼接避免被识别为真实凭证）
            "github_pat_" + "B" * 40,                 # GitHub Fine-grained
            "xoxb-" + "1" * 12 + "-" + "2" * 12 + "-" + "c" * 24,  # Slack
            "sk_live_" + "9" * 24,                    # Stripe（拼接避免被识别为真实凭证）
            "sk-abcdefghijklmnopqrstuvwx",            # OpenAI 旧版
        ]
        for value in cases:
            content = f"KEY = '{value}'"
            with self.subTest(value=value[:12]):
                self.assertLess(self._score(content), 40, f"漏报：{value[:12]}")

    def test_test_certificates_not_penalized(self):
        """回归：psf/requests 测试私钥不应清零密钥分。"""
        files = [
            (f"tests/certs/{n}", "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIB...\n-----END RSA PRIVATE KEY-----")
            for n in ["ca-private.key", "client.key", "server.key", "expired.key"]
        ]
        cat, findings = detect_secrets(files)
        self.assertEqual(cat.score, cat.max_score)
        self.assertEqual(len(findings), 4)
        self.assertTrue(all(f.severity == "info" for f in findings))

    def test_placeholder_not_penalized(self):
        self.assertEqual(self._score("KEY = 'sk-xxxxxxxxxxxxxxxxxxxxxxxx'"), 40)

    def test_doc_example_not_penalized(self):
        self.assertEqual(self._score("使用 sk-proj-AbCdEf1234567890GhIjKlMn 作为示例", "README.md"), 40)


class HardcodedTests(unittest.TestCase):
    def test_windows_path_in_production(self):
        line = f"p = r'C:{WIN}Users{WIN}admin'"
        cat, findings = detect_hardcoded([("src/main.py", line)])
        self.assertEqual(len(findings), 1)

    def test_test_directory_exempt(self):
        line = f"p = r'C:{WIN}Users{WIN}admin'"
        cat, findings = detect_hardcoded([("tests/test_utils.py", line)])
        self.assertEqual(len(findings), 0)

    def test_url_not_mistaken_for_drive_path(self):
        cat, findings = detect_hardcoded([("src/main.py", "url = 'https://api.deepseek.com'")])
        self.assertEqual(len(findings), 0)

    def test_dockerfile_exempt(self):
        cat, findings = detect_hardcoded([("docker/Dockerfile", "ENV VIRTUAL_ENV=/opt/venv")])
        self.assertEqual(len(findings), 0)


class WindowsTests(unittest.TestCase):
    def test_detect_scripts(self):
        cat, findings = detect_windows([("scripts/setup.bat", "@echo off"), ("deploy.ps1", "Write-Host ok")])
        self.assertEqual(len(findings), 2)
        self.assertLess(cat.score, cat.max_score)

    def test_no_scripts(self):
        cat, findings = detect_windows([("main.py", "print('hi')")])
        self.assertEqual(cat.score, cat.max_score)


class IntegrationTests(unittest.TestCase):
    def test_detect_all_returns_four_categories(self):
        cats, findings = detect_all([("README.md", "# Demo\n项目介绍\n## Quick Start\npip install -r requirements.txt"), ("requirements.txt", "flask")])
        self.assertEqual(len(cats), 4)
        self.assertEqual({c.key for c in cats}, {"completeness", "secrets", "windows", "hardcoded"})


if __name__ == "__main__":
    unittest.main()
