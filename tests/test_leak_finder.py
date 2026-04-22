"""Tests for the LeakFinder module."""

import textwrap
import pytest
from code_agents.observability.leak_finder import LeakFinder, LeakFinderConfig, LeakReport, format_leak_report


class TestLeakFinder:
    def test_detect_unclosed_resource(self, tmp_path):
        source = textwrap.dedent('''\
            f = open("data.txt")
            data = f.read()
            # f.close() missing!
        ''')
        (tmp_path / "app.py").write_text(source)
        result = LeakFinder(LeakFinderConfig(cwd=str(tmp_path))).scan()
        assert any(f.pattern == "missing_context_manager" for f in result.findings)

    def test_no_leak_with_context_manager(self, tmp_path):
        source = textwrap.dedent('''\
            with open("data.txt") as f:
                data = f.read()
        ''')
        (tmp_path / "app.py").write_text(source)
        result = LeakFinder(LeakFinderConfig(cwd=str(tmp_path))).scan()
        # Should not flag context-managed opens
        resource_findings = [f for f in result.findings if f.pattern in ("unclosed_resource", "missing_context_manager")]
        assert len(resource_findings) == 0

    def test_detect_global_mutable(self, tmp_path):
        source = textwrap.dedent('''\
            cache = {}
            items = []
        ''')
        (tmp_path / "app.py").write_text(source)
        result = LeakFinder(LeakFinderConfig(cwd=str(tmp_path))).scan()
        assert any(f.pattern == "global_mutable" for f in result.findings)

    def test_empty_codebase(self, tmp_path):
        result = LeakFinder(LeakFinderConfig(cwd=str(tmp_path))).scan()
        assert result.files_scanned == 0
        assert len(result.findings) == 0

    def test_severity_counts(self, tmp_path):
        source = "f = open('x')\ncache = {}\n"
        (tmp_path / "app.py").write_text(source)
        result = LeakFinder(LeakFinderConfig(cwd=str(tmp_path))).scan()
        assert result.high_count + result.medium_count + result.low_count == len(result.findings)

    def test_format_output(self):
        report = LeakReport(summary="2 leaks", files_scanned=10)
        output = format_leak_report(report)
        assert "Leak" in output
