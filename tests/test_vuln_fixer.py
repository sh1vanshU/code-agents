"""Tests for the VulnFixer module."""

import textwrap
import pytest
from code_agents.security.vuln_fixer import (
    VulnFixer, VulnFixerConfig, CVEAlert, VulnFixerReport, format_vuln_report,
)


class TestVulnFixer:
    def test_parse_advisory_text(self):
        fixer = VulnFixer(VulnFixerConfig())
        report = fixer.analyze(advisory_text="Found CVE-2024-1234 and CVE-2024-5678 in the audit.")
        assert report.cves_parsed == 2
        assert report.alerts[0].cve_id == "CVE-2024-1234"
        assert report.alerts[1].cve_id == "CVE-2024-5678"

    def test_analyze_with_alerts(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("requests==2.25.0\nflask==2.0.0\n")
        (tmp_path / "app.py").write_text("import requests\nfrom flask import Flask\n")
        alerts = [
            CVEAlert(cve_id="CVE-2024-0001", package="requests", severity="high",
                     fixed_version="2.31.0"),
        ]
        fixer = VulnFixer(VulnFixerConfig(cwd=str(tmp_path)))
        report = fixer.analyze(alerts=alerts)
        assert report.cves_parsed == 1
        assert report.affected_packages >= 1
        assert len(report.suggestions) >= 1
        assert report.suggestions[0].target_version == "2.31.0"

    def test_find_usage_in_source(self, tmp_path):
        source = textwrap.dedent('''\
            import requests
            from requests import Session

            def fetch():
                return requests.get("https://example.com")
        ''')
        (tmp_path / "client.py").write_text(source)
        (tmp_path / "requirements.txt").write_text("requests==2.25.0\n")
        alerts = [CVEAlert(cve_id="CVE-2024-0002", package="requests", severity="critical")]
        fixer = VulnFixer(VulnFixerConfig(cwd=str(tmp_path)))
        report = fixer.analyze(alerts=alerts)
        assert report.locations_found >= 1
        assert any(loc.file == "client.py" for loc in report.locations)

    def test_empty_alerts_returns_clean_report(self, tmp_path):
        fixer = VulnFixer(VulnFixerConfig(cwd=str(tmp_path)))
        report = fixer.analyze()
        assert report.cves_parsed == 0
        assert "No CVE alerts" in report.summary

    def test_severity_threshold_filters(self, tmp_path):
        (tmp_path / "requirements.txt").write_text("low-pkg==1.0\n")
        alerts = [
            CVEAlert(cve_id="CVE-2024-0003", package="low-pkg", severity="low"),
        ]
        fixer = VulnFixer(VulnFixerConfig(cwd=str(tmp_path), severity_threshold="high"))
        report = fixer.analyze(alerts=alerts)
        assert len(report.suggestions) == 0

    def test_format_report(self):
        report = VulnFixerReport(
            cves_parsed=2, affected_packages=1, summary="done",
            alerts=[CVEAlert(cve_id="CVE-2024-0001", package="pkg")],
        )
        output = format_vuln_report(report)
        assert "Vulnerability Fixer" in output
        assert "CVEs analysed" in output
