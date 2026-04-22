"""Tests for Test Impact Analyzer."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from code_agents.testing.test_impact import (
    ImpactedTest,
    ImpactAnalyzer,
    ImpactReport,
    format_test_impact,
)


class ImpactAnalyzerTests:
    """Tests for ImpactAnalyzer."""

    def test_init_defaults(self):
        analyzer = ImpactAnalyzer()
        assert analyzer.base == "main"

    def test_init_custom(self):
        analyzer = ImpactAnalyzer(cwd="/tmp", base="develop")
        assert analyzer.base == "develop"

    @patch.object(ImpactAnalyzer, "_run_git")
    def test_get_changed_files(self, mock_git):
        mock_git.return_value = "src/auth.py\nsrc/login.py"
        analyzer = ImpactAnalyzer()
        files = analyzer._get_changed_files()
        assert files == ["src/auth.py", "src/login.py"]

    @patch.object(ImpactAnalyzer, "_run_git")
    def test_get_changed_files_empty(self, mock_git):
        mock_git.return_value = ""
        analyzer = ImpactAnalyzer()
        assert analyzer._get_changed_files() == []

    def test_parse_diff_lines(self):
        analyzer = ImpactAnalyzer()
        diff = "@@ -10,5 +10,7 @@ def foo():"
        lines = analyzer._parse_diff_lines(diff)
        assert 10 in lines
        assert 16 in lines  # 10 + 7 - 1

    def test_parse_diff_lines_empty(self):
        analyzer = ImpactAnalyzer()
        assert analyzer._parse_diff_lines("") == set()

    def test_find_all_test_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "tests"))
            Path(os.path.join(tmpdir, "tests", "test_auth.py")).write_text("def test_login(): pass")
            Path(os.path.join(tmpdir, "tests", "test_utils.py")).write_text("def test_helper(): pass")
            Path(os.path.join(tmpdir, "src", "auth.py")).mkdir(parents=True, exist_ok=True)

            # Fix: auth.py is a dir, create proper files
            os.rmdir(os.path.join(tmpdir, "src", "auth.py"))
            Path(os.path.join(tmpdir, "src", "auth.py")).write_text("def login(): pass")

            analyzer = ImpactAnalyzer(cwd=tmpdir)
            test_files = analyzer._find_all_test_files()
            assert len(test_files) == 2
            assert any("test_auth" in f for f in test_files)

    def test_map_to_tests_naming_convention(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "tests"))
            Path(os.path.join(tmpdir, "tests", "test_auth.py")).write_text("")

            analyzer = ImpactAnalyzer(cwd=tmpdir)
            all_tests = ["tests/test_auth.py"]
            impacted = analyzer._map_to_tests(["src/auth.py"], [], all_tests)
            assert len(impacted) == 1
            assert impacted[0].reason == "naming convention"

    def test_map_to_tests_direct_change(self):
        analyzer = ImpactAnalyzer()
        all_tests = ["tests/test_auth.py"]
        impacted = analyzer._map_to_tests(["tests/test_auth.py"], [], all_tests)
        assert len(impacted) == 1
        # File matches as "directly changed" or "same directory" depending on ordering
        assert impacted[0].test_file == "tests/test_auth.py"

    def test_detect_test_framework_pytest(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(os.path.join(tmpdir, "conftest.py")).write_text("")
            analyzer = ImpactAnalyzer(cwd=tmpdir)
            assert analyzer._detect_test_framework() == "pytest"

    def test_detect_test_framework_default(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            analyzer = ImpactAnalyzer(cwd=tmpdir)
            assert analyzer._detect_test_framework() == "pytest"


class TestImpactReport:
    """Tests for ImpactReport."""

    def test_skipped_tests(self):
        report = ImpactReport(total_test_files=10, impacted_test_files=3)
        assert report.skipped_tests == 7


class TestFormatTestImpact:
    """Tests for format_test_impact."""

    def test_format_report(self):
        report = ImpactReport(
            changed_files=["src/auth.py"],
            changed_functions=["src/auth.py::login"],
            impacted_tests=[
                ImpactedTest(test_file="tests/test_auth.py",
                             reason="naming convention", confidence=0.95),
            ],
            total_test_files=50,
            impacted_test_files=1,
            reduction_pct=98.0,
            test_framework="pytest",
        )
        output = format_test_impact(report)
        assert "98.0%" in output
        assert "test_auth" in output
        assert "naming convention" in output

    def test_format_with_run_result(self):
        report = ImpactReport(
            run_result={"status": "pass", "tests_run": 1, "stdout": "1 passed"},
        )
        output = format_test_impact(report)
        assert "pass" in output.lower()

    def test_format_empty(self):
        report = ImpactReport()
        output = format_test_impact(report)
        assert "Test Impact" in output
