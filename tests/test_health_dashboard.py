"""Tests for code_agents.health_dashboard."""

from __future__ import annotations

import json
import os
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_agents.observability.health_dashboard import (
    ComplexityInfo,
    CoverageMetrics,
    DashboardData,
    HealthDashboard,
    PRInfo,
    TestMetrics,
    _analyze_file_complexity,
    _complexity_grade,
    format_dashboard_json,
)


# ---------------------------------------------------------------------------
# Grade tests
# ---------------------------------------------------------------------------


class TestComplexityGrade:
    def test_grade_a(self):
        assert _complexity_grade(1) == "A"
        assert _complexity_grade(5) == "A"

    def test_grade_b(self):
        assert _complexity_grade(6) == "B"
        assert _complexity_grade(10) == "B"

    def test_grade_c(self):
        assert _complexity_grade(11) == "C"
        assert _complexity_grade(15) == "C"

    def test_grade_d(self):
        assert _complexity_grade(16) == "D"
        assert _complexity_grade(20) == "D"

    def test_grade_e(self):
        assert _complexity_grade(21) == "E"
        assert _complexity_grade(25) == "E"

    def test_grade_f(self):
        assert _complexity_grade(26) == "F"
        assert _complexity_grade(100) == "F"


# ---------------------------------------------------------------------------
# AST complexity analysis
# ---------------------------------------------------------------------------


class TestAnalyzeFileComplexity:
    def test_simple_function(self, tmp_path: Path):
        f = tmp_path / "simple.py"
        f.write_text("def hello():\n    return 1\n")
        results = _analyze_file_complexity(str(f))
        assert len(results) == 1
        assert results[0].function == "hello"
        assert results[0].score == 1
        assert results[0].grade == "A"

    def test_branches_add_complexity(self, tmp_path: Path):
        code = textwrap.dedent("""\
            def process(x):
                if x > 0:
                    for i in range(x):
                        if i % 2 == 0:
                            pass
                        else:
                            try:
                                pass
                            except ValueError:
                                pass
        """)
        f = tmp_path / "branchy.py"
        f.write_text(code)
        results = _analyze_file_complexity(str(f))
        assert len(results) == 1
        assert results[0].score > 1
        assert results[0].function == "process"

    def test_bool_ops_add_complexity(self, tmp_path: Path):
        code = textwrap.dedent("""\
            def check(a, b, c):
                if a and b and c:
                    return True
                return False
        """)
        f = tmp_path / "boolop.py"
        f.write_text(code)
        results = _analyze_file_complexity(str(f))
        assert len(results) == 1
        # 1 base + 1 if + 2 bool ops (3 values => +2)
        assert results[0].score == 4

    def test_syntax_error_returns_empty(self, tmp_path: Path):
        f = tmp_path / "bad.py"
        f.write_text("def broken(:\n    pass\n")
        assert _analyze_file_complexity(str(f)) == []

    def test_nonexistent_file_returns_empty(self):
        assert _analyze_file_complexity("/nonexistent/file.py") == []

    def test_async_function(self, tmp_path: Path):
        code = textwrap.dedent("""\
            async def fetch(url):
                if url:
                    return url
                return None
        """)
        f = tmp_path / "async_fn.py"
        f.write_text(code)
        results = _analyze_file_complexity(str(f))
        assert len(results) == 1
        assert results[0].function == "fetch"
        assert results[0].score == 2  # 1 base + 1 if

    def test_multiple_functions(self, tmp_path: Path):
        code = textwrap.dedent("""\
            def a():
                pass

            def b():
                if True:
                    pass
        """)
        f = tmp_path / "multi.py"
        f.write_text(code)
        results = _analyze_file_complexity(str(f))
        assert len(results) == 2


# ---------------------------------------------------------------------------
# HealthDashboard
# ---------------------------------------------------------------------------


class TestHealthDashboard:
    def test_init(self, tmp_path: Path):
        dash = HealthDashboard(str(tmp_path))
        assert dash.cwd == str(tmp_path)
        assert dash.root == tmp_path

    @patch("code_agents.observability.health_dashboard.subprocess.run")
    def test_test_status_parses_collected(self, mock_run, tmp_path: Path):
        mock_run.return_value = MagicMock(
            stdout="test_a.py::test_one\ntest_b.py::test_two\n\n2 tests collected\n",
            returncode=0,
        )
        dash = HealthDashboard(str(tmp_path))
        result = dash._test_status()
        assert result is not None
        assert result.total == 2
        assert result.passed == 2

    @patch("code_agents.observability.health_dashboard.subprocess.run")
    def test_test_status_fallback_to_lines(self, mock_run, tmp_path: Path):
        mock_run.return_value = MagicMock(
            stdout="test_a.py::test_one\ntest_b.py::test_two\ntest_c.py::test_three\n",
            returncode=0,
        )
        dash = HealthDashboard(str(tmp_path))
        result = dash._test_status()
        assert result is not None
        assert result.total == 3

    @patch("code_agents.observability.health_dashboard.subprocess.run")
    def test_test_status_timeout_returns_none(self, mock_run, tmp_path: Path):
        import subprocess as sp
        mock_run.side_effect = sp.TimeoutExpired(cmd="pytest", timeout=60)
        dash = HealthDashboard(str(tmp_path))
        assert dash._test_status() is None

    def test_coverage_status_from_json(self, tmp_path: Path):
        cov_data = {
            "totals": {
                "num_statements": 1000,
                "covered_lines": 780,
                "percent_covered": 78.0,
            }
        }
        (tmp_path / "coverage.json").write_text(json.dumps(cov_data))
        dash = HealthDashboard(str(tmp_path))
        result = dash._coverage_status()
        assert result is not None
        assert result.total_lines == 1000
        assert result.covered_lines == 780
        assert result.percentage == 78.0

    def test_coverage_status_no_file_returns_none(self, tmp_path: Path):
        dash = HealthDashboard(str(tmp_path))
        assert dash._coverage_status() is None

    def test_complexity_hotspots(self, tmp_path: Path):
        # Create some Python files
        (tmp_path / "simple.py").write_text("def f():\n    return 1\n")
        code = textwrap.dedent("""\
            def complex_func(x):
                if x > 0:
                    for i in range(x):
                        while i > 0:
                            if i % 2 == 0:
                                try:
                                    pass
                                except Exception:
                                    pass
                            i -= 1
        """)
        (tmp_path / "complex.py").write_text(code)
        dash = HealthDashboard(str(tmp_path))
        results = dash._complexity_hotspots(top_n=5)
        assert len(results) >= 1
        # Most complex should be first
        assert results[0].function == "complex_func"
        assert results[0].score > results[-1].score or len(results) == 1

    @patch("code_agents.observability.health_dashboard.subprocess.run")
    def test_open_prs(self, mock_run, tmp_path: Path):
        mock_run.return_value = MagicMock(
            stdout=json.dumps([
                {
                    "number": 42,
                    "title": "Add feature X",
                    "author": {"login": "dev1"},
                    "createdAt": "2026-04-01T10:00:00Z",
                }
            ]),
            returncode=0,
        )
        dash = HealthDashboard(str(tmp_path))
        prs = dash._open_prs()
        assert len(prs) == 1
        assert prs[0].number == 42
        assert prs[0].author == "dev1"
        assert prs[0].age_days >= 0

    @patch("code_agents.observability.health_dashboard.subprocess.run")
    def test_open_prs_gh_not_found(self, mock_run, tmp_path: Path):
        mock_run.side_effect = FileNotFoundError("gh not found")
        dash = HealthDashboard(str(tmp_path))
        assert dash._open_prs() == []

    def test_collect_metrics_independent(self, tmp_path: Path):
        """Each metric collector is independent; one failing doesn't block others."""
        dash = HealthDashboard(str(tmp_path))
        with patch.object(dash, "_test_status", side_effect=RuntimeError("boom")), \
             patch.object(dash, "_coverage_status", return_value=CoverageMetrics(100, 80, 80.0)), \
             patch.object(dash, "_complexity_hotspots", return_value=[]), \
             patch.object(dash, "_open_prs", return_value=[]):
            data = dash.collect_metrics()
        assert data.tests is None  # failed, but didn't crash
        assert data.coverage is not None
        assert data.coverage.percentage == 80.0


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


class TestRendering:
    def _make_data(self) -> DashboardData:
        return DashboardData(
            tests=TestMetrics(total=100, passed=95, failed=3, skipped=2, duration=12.5),
            coverage=CoverageMetrics(total_lines=5000, covered_lines=4000, percentage=80.0),
            complexity_hotspots=[
                ComplexityInfo(file="api.py", function="handle_request", score=18, grade="D"),
                ComplexityInfo(file="utils.py", function="parse", score=8, grade="B"),
            ],
            open_prs=[
                PRInfo(number=123, title="Add mindmap feature", author="shivanshu", age_days=3, status="open"),
            ],
            timestamp="2026-04-09 12:00:00 UTC",
        )

    def test_render_terminal_contains_key_info(self, tmp_path: Path):
        dash = HealthDashboard(str(tmp_path))
        data = self._make_data()
        output = dash.render_terminal(data)
        assert "95" in output  # passed count
        assert "80.0" in output  # coverage pct
        assert "handle_request" in output  # complexity hotspot
        assert "#123" in output  # PR number

    def test_render_plain_fallback(self, tmp_path: Path):
        dash = HealthDashboard(str(tmp_path))
        data = self._make_data()
        output = dash._render_plain(data)
        assert "95 passed" in output
        assert "80.0%" in output
        assert "handle_request" in output
        assert "#123" in output

    def test_render_empty_data(self, tmp_path: Path):
        dash = HealthDashboard(str(tmp_path))
        data = DashboardData(
            tests=None, coverage=None,
            complexity_hotspots=[], open_prs=[],
            timestamp="2026-04-09 12:00:00 UTC",
        )
        output = dash.render_terminal(data)
        assert "No test data" in output or "No data" in output


# ---------------------------------------------------------------------------
# JSON export
# ---------------------------------------------------------------------------


class TestFormatDashboardJson:
    def test_full_data(self):
        data = DashboardData(
            tests=TestMetrics(total=50, passed=48, failed=1, skipped=1, duration=5.0),
            coverage=CoverageMetrics(total_lines=2000, covered_lines=1600, percentage=80.0),
            complexity_hotspots=[
                ComplexityInfo(file="a.py", function="fn", score=12, grade="C"),
            ],
            open_prs=[
                PRInfo(number=7, title="Fix bug", author="dev", age_days=1, status="open"),
            ],
            timestamp="2026-04-09 12:00:00 UTC",
        )
        raw = format_dashboard_json(data)
        parsed = json.loads(raw)
        assert parsed["tests"]["total"] == 50
        assert parsed["coverage"]["percentage"] == 80.0
        assert len(parsed["complexity_hotspots"]) == 1
        assert parsed["open_prs"][0]["number"] == 7

    def test_empty_data(self):
        data = DashboardData(
            tests=None, coverage=None,
            complexity_hotspots=[], open_prs=[],
            timestamp="2026-04-09 12:00:00 UTC",
        )
        parsed = json.loads(format_dashboard_json(data))
        assert parsed["tests"] is None
        assert parsed["coverage"] is None
        assert parsed["complexity_hotspots"] == []
        assert parsed["open_prs"] == []
