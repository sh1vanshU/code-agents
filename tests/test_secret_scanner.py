"""Tests for the SecretScanner module."""

import textwrap
import pytest
from code_agents.security.secret_scanner import (
    SecretScanner, SecretScannerConfig, SecretScanReport, format_secret_report,
)


class TestSecretScanner:
    def test_detect_aws_key(self, tmp_path):
        source = 'AWS_KEY = "AKIAIOSFODNN7EXAMPLE"\n'
        (tmp_path / "config.py").write_text(source)
        scanner = SecretScanner(SecretScannerConfig(cwd=str(tmp_path)))
        report = scanner.scan()
        assert report.secrets_found >= 1
        assert any(f.secret_type == "aws_access_key" for f in report.findings)

    def test_detect_hardcoded_password(self, tmp_path):
        source = 'password = "super_secret_password_123"\n'
        (tmp_path / "settings.py").write_text(source)
        scanner = SecretScanner(SecretScannerConfig(cwd=str(tmp_path)))
        report = scanner.scan()
        assert any(f.secret_type == "password_assignment" for f in report.findings)
        assert report.critical_count >= 1

    def test_detect_github_token(self, tmp_path):
        source = 'GITHUB_TOKEN = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefgh1234"\n'
        (tmp_path / "ci.py").write_text(source)
        scanner = SecretScanner(SecretScannerConfig(cwd=str(tmp_path)))
        report = scanner.scan()
        assert any(f.secret_type == "github_token" for f in report.findings)

    def test_masked_preview(self, tmp_path):
        source = 'api_key = "abcdefghijklmnop1234567890"\n'
        (tmp_path / "app.py").write_text(source)
        scanner = SecretScanner(SecretScannerConfig(cwd=str(tmp_path)))
        report = scanner.scan()
        for f in report.findings:
            assert "****" in f.masked_preview
            assert len(f.masked_preview) <= 8

    def test_clean_code_no_secrets(self, tmp_path):
        source = textwrap.dedent('''\
            import os
            API_KEY = os.getenv("API_KEY")
            def greet(name):
                return f"Hello {name}"
        ''')
        (tmp_path / "app.py").write_text(source)
        scanner = SecretScanner(SecretScannerConfig(cwd=str(tmp_path)))
        report = scanner.scan()
        assert report.secrets_found == 0

    def test_format_report(self):
        report = SecretScanReport(files_scanned=10, secrets_found=2, critical_count=1, summary="done")
        output = format_secret_report(report)
        assert "Secret Scanner" in output
        assert "Critical" in output
