"""Tests for the OWASPChecker module."""

import textwrap
import pytest
from code_agents.security.owasp_checker import (
    OWASPChecker, OWASPCheckerConfig, OWASPCheckerReport, format_owasp_report,
)


class TestOWASPChecker:
    def test_detect_sql_injection(self, tmp_path):
        source = textwrap.dedent('''\
            def search(name):
                cursor.execute(f"SELECT * FROM users WHERE name = '{name}'")
        ''')
        (tmp_path / "db.py").write_text(source)
        checker = OWASPChecker(OWASPCheckerConfig(cwd=str(tmp_path)))
        report = checker.analyze()
        assert report.total_findings >= 1
        assert any(f.category == "A03" for f in report.findings)
        assert any(f.fix_code for f in report.findings)

    def test_detect_weak_hash(self, tmp_path):
        source = 'digest = md5(data)\n'
        (tmp_path / "crypto.py").write_text(source)
        checker = OWASPChecker(OWASPCheckerConfig(cwd=str(tmp_path)))
        report = checker.analyze()
        assert any(f.category == "A02" for f in report.findings)

    def test_detect_debug_mode(self, tmp_path):
        source = 'DEBUG = True\n'
        (tmp_path / "settings.py").write_text(source)
        checker = OWASPChecker(OWASPCheckerConfig(cwd=str(tmp_path)))
        report = checker.analyze()
        assert any(f.category == "A05" for f in report.findings)

    def test_detect_ssl_disabled(self, tmp_path):
        source = 'response = requests.get(url, verify=False)\n'
        (tmp_path / "client.py").write_text(source)
        checker = OWASPChecker(OWASPCheckerConfig(cwd=str(tmp_path)))
        report = checker.analyze()
        assert any(f.category == "A05" for f in report.findings)
        assert report.high_count >= 1

    def test_clean_code_no_findings(self, tmp_path):
        source = textwrap.dedent('''\
            def add(a: int, b: int) -> int:
                return a + b
        ''')
        (tmp_path / "math.py").write_text(source)
        checker = OWASPChecker(OWASPCheckerConfig(cwd=str(tmp_path)))
        report = checker.analyze()
        assert report.total_findings == 0

    def test_format_report_with_category_breakdown(self):
        report = OWASPCheckerReport(
            files_scanned=10, total_findings=3,
            category_breakdown={"A03 Injection": 2, "A05 Security Misconfiguration": 1},
            summary="done",
        )
        output = format_owasp_report(report)
        assert "OWASP Checker" in output
        assert "Category breakdown" in output
