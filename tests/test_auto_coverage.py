"""Tests for auto_coverage.py — auto-coverage boost pipeline."""

from __future__ import annotations

import json
import os
import textwrap
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from code_agents.tools.auto_coverage import (
    AutoCoverageBoost,
    CoverageGap,
    CoverageReport,
    format_coverage_report,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_file(tmp_path: Path, name: str, content: str = ""):
    """Create a file inside tmp_path, creating parent dirs as needed."""
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


def _make_dir(tmp_path: Path, name: str):
    """Create a directory inside tmp_path."""
    d = tmp_path / name
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Stack detection
# ---------------------------------------------------------------------------


class TestDetectStack:
    """Test _detect_stack for each language."""

    def test_python_pyproject(self, tmp_path):
        _make_file(tmp_path, "pyproject.toml", "[tool.poetry]")
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        assert boost.report.language == "python"
        assert boost.report.test_framework == "pytest"
        assert "pytest" in boost.report.test_command

    def test_python_setup_py(self, tmp_path):
        _make_file(tmp_path, "setup.py", "from setuptools import setup")
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        assert boost.report.language == "python"

    def test_java_maven(self, tmp_path):
        _make_file(tmp_path, "pom.xml", "<project></project>")
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        assert boost.report.language == "java"
        assert boost.report.test_framework == "junit"
        assert "mvn" in boost.report.test_command

    def test_java_gradle(self, tmp_path):
        _make_file(tmp_path, "build.gradle", "plugins {}")
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        assert boost.report.language == "java"
        assert "gradlew" in boost.report.test_command

    def test_java_gradle_kts(self, tmp_path):
        _make_file(tmp_path, "build.gradle.kts", "plugins {}")
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        assert boost.report.language == "java"

    def test_javascript(self, tmp_path):
        _make_file(tmp_path, "package.json", '{"name": "test"}')
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        assert boost.report.language == "javascript"
        assert boost.report.test_framework == "jest"

    def test_go(self, tmp_path):
        _make_file(tmp_path, "go.mod", "module example.com/foo")
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        assert boost.report.language == "go"
        assert "go test" in boost.report.test_command

    def test_unknown_language(self, tmp_path):
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        assert boost.report.language == ""
        assert boost.report.test_command == ""

    def test_env_override(self, tmp_path):
        _make_file(tmp_path, "pyproject.toml", "")
        with patch.dict(os.environ, {"CODE_AGENTS_TEST_CMD": "make test"}):
            boost = AutoCoverageBoost(cwd=str(tmp_path))
        assert boost.report.test_command == "make test"


# ---------------------------------------------------------------------------
# Scan existing tests
# ---------------------------------------------------------------------------


class TestScanExistingTests:
    """Test scan_existing_tests."""

    def test_python_tests(self, tmp_path):
        _make_file(tmp_path, "pyproject.toml", "")
        _make_file(tmp_path, "tests/test_foo.py", "def test_one(): pass\ndef test_two(): pass")
        _make_file(tmp_path, "tests/test_bar.py", "def test_three(): pass")
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        result = boost.scan_existing_tests()
        assert result["files"] == 2
        assert result["methods"] == 3

    def test_java_tests(self, tmp_path):
        _make_file(tmp_path, "pom.xml", "")
        _make_file(tmp_path, "src/test/java/FooTest.java", "@Test\npublic void test1() {}\n@Test\npublic void test2() {}")
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        result = boost.scan_existing_tests()
        assert result["files"] == 1
        assert result["methods"] == 2

    def test_javascript_tests(self, tmp_path):
        _make_file(tmp_path, "package.json", "{}")
        _make_file(tmp_path, "src/foo.test.js", "it('works', () => {})\ntest('also works', () => {})")
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        result = boost.scan_existing_tests()
        assert result["files"] == 1
        assert result["methods"] == 2

    def test_go_tests(self, tmp_path):
        _make_file(tmp_path, "go.mod", "module m")
        _make_file(tmp_path, "foo_test.go", "func TestFoo(t *testing.T) {}\nfunc TestBar(t *testing.T) {}")
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        result = boost.scan_existing_tests()
        assert result["files"] == 1
        assert result["methods"] == 2

    def test_skips_node_modules(self, tmp_path):
        _make_file(tmp_path, "package.json", "{}")
        _make_file(tmp_path, "node_modules/lib/foo.test.js", "test('x', () => {})")
        _make_file(tmp_path, "src/bar.test.js", "test('y', () => {})")
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        result = boost.scan_existing_tests()
        assert result["files"] == 1

    def test_no_tests(self, tmp_path):
        _make_file(tmp_path, "pyproject.toml", "")
        _make_file(tmp_path, "src/app.py", "print('hello')")
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        result = boost.scan_existing_tests()
        assert result["files"] == 0
        assert result["methods"] == 0


# ---------------------------------------------------------------------------
# Coverage parsing
# ---------------------------------------------------------------------------


class TestParsePythonCoverage:
    """Test _parse_python_coverage with sample JSON."""

    def test_parse_coverage_json(self, tmp_path):
        _make_file(tmp_path, "pyproject.toml", "")
        data = {
            "totals": {
                "percent_covered": 72.5,
                "num_statements": 200,
                "covered_lines": 145,
            },
            "files": {
                "src/app.py": {
                    "missing_lines": [10, 15, 20],
                    "summary": {"percent_covered": 50.0},
                },
                "src/utils.py": {
                    "missing_lines": [],
                    "summary": {"percent_covered": 100.0},
                },
            },
        }
        _make_file(tmp_path, "coverage.json", json.dumps(data))
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        boost._parse_python_coverage()
        assert boost.report.coverage_pct == 72.5
        assert boost.report.total_lines == 200
        assert boost.report.covered_lines == 145
        assert len(boost.report.gaps) == 1
        assert boost.report.gaps[0].file == "src/app.py"

    def test_no_coverage_json(self, tmp_path):
        _make_file(tmp_path, "pyproject.toml", "")
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        boost._parse_python_coverage()
        assert boost.report.coverage_pct == 0


class TestParseJacocoCoverage:
    """Test _parse_jacoco_coverage with sample XML."""

    def test_parse_jacoco_xml(self, tmp_path):
        _make_file(tmp_path, "pom.xml", "")
        xml = textwrap.dedent("""\
            <?xml version="1.0"?>
            <report>
                <counter type="LINE" missed="30" covered="70"/>
            </report>
        """)
        _make_file(tmp_path, "target/site/jacoco/jacoco.xml", xml)
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        boost._parse_jacoco_coverage()
        assert boost.report.total_lines == 100
        assert boost.report.covered_lines == 70
        assert boost.report.coverage_pct == 70.0


class TestParseJestCoverage:
    """Test _parse_jest_coverage."""

    def test_parse_jest_summary(self, tmp_path):
        _make_file(tmp_path, "package.json", "{}")
        data = {
            "total": {"lines": {"pct": 65.0, "total": 200, "covered": 130}},
            "src/index.js": {"lines": {"pct": 40.0}},
        }
        _make_file(tmp_path, "coverage/coverage-summary.json", json.dumps(data))
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        boost._parse_jest_coverage()
        assert boost.report.coverage_pct == 65.0
        assert len(boost.report.gaps) == 1


class TestParseGoCoverage:
    """Test _parse_go_coverage."""

    def test_parse_go_output(self, tmp_path):
        _make_file(tmp_path, "go.mod", "module m")
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        boost._parse_go_coverage("ok  \texample.com/foo\t0.5s\tcoverage: 62.4% of statements")
        assert boost.report.coverage_pct == 62.4

    def test_no_match(self, tmp_path):
        _make_file(tmp_path, "go.mod", "module m")
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        boost._parse_go_coverage("no coverage info")
        assert boost.report.coverage_pct == 0


# ---------------------------------------------------------------------------
# Gap identification and prioritization
# ---------------------------------------------------------------------------


class TestIdentifyGaps:
    """Test identify_gaps and _find_uncovered_files."""

    def test_finds_uncovered_python_files(self, tmp_path):
        _make_file(tmp_path, "pyproject.toml", "")
        _make_file(tmp_path, "src/app.py", "class App: pass")
        _make_file(tmp_path, "src/utils.py", "def helper(): pass")
        _make_file(tmp_path, "tests/test_app.py", "def test_app(): pass")
        # utils.py has no test
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        boost.scan_existing_tests()
        gaps = boost.identify_gaps()
        gap_names = [g.name for g in gaps]
        assert "utils" in gap_names
        assert "app" not in gap_names  # has a test

    def test_uses_existing_gaps_from_parser(self, tmp_path):
        _make_file(tmp_path, "pyproject.toml", "")
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        boost.report.gaps = [CoverageGap(file="x.py", name="x", coverage_pct=30)]
        result = boost.identify_gaps()
        assert len(result) == 1
        assert result[0].name == "x"


class TestPrioritizeGaps:
    """Test prioritize_gaps."""

    def test_critical_patterns(self, tmp_path):
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        boost.report.gaps = [
            CoverageGap(file="src/payment.py", name="payment", coverage_pct=20),
            CoverageGap(file="src/utils.py", name="utils", coverage_pct=0),
            CoverageGap(file="src/service.py", name="service", coverage_pct=50),
        ]
        result = boost.prioritize_gaps()
        assert result[0].risk == "critical"  # payment
        assert result[0].name == "payment"

    def test_sort_order(self, tmp_path):
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        boost.report.gaps = [
            CoverageGap(file="low.py", name="low", coverage_pct=90),
            CoverageGap(file="auth.py", name="auth", coverage_pct=10),
            CoverageGap(file="handler.py", name="handler", coverage_pct=0),
        ]
        result = boost.prioritize_gaps()
        # critical (auth) first, then high (handler with 0%), then low
        assert result[0].risk == "critical"
        assert result[1].risk == "high"

    def test_zero_coverage_is_high(self, tmp_path):
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        boost.report.gaps = [
            CoverageGap(file="foo.py", name="foo", coverage_pct=0),
        ]
        boost.prioritize_gaps()
        assert boost.report.prioritized_gaps[0].risk == "high"

    def test_low_coverage_is_medium(self, tmp_path):
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        boost.report.gaps = [
            CoverageGap(file="foo.py", name="foo", coverage_pct=25),
        ]
        boost.prioritize_gaps()
        assert boost.report.prioritized_gaps[0].risk == "medium"


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------


class TestBuildTestPrompts:
    """Test build_test_prompts."""

    def test_builds_prompts(self, tmp_path):
        _make_file(tmp_path, "pyproject.toml", "")
        _make_file(tmp_path, "src/foo.py", "class Foo:\n    def bar(self): pass")
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        boost.report.prioritized_gaps = [
            CoverageGap(file="src/foo.py", name="foo", coverage_pct=0, risk="high"),
        ]
        prompts = boost.build_test_prompts()
        assert len(prompts) == 1
        assert prompts[0]["source_file"] == "src/foo.py"
        assert prompts[0]["test_file"] == "tests/test_foo.py"
        assert prompts[0]["language"] == "python"
        assert "class Foo" in prompts[0]["source_code"]

    def test_skips_missing_files(self, tmp_path):
        _make_file(tmp_path, "pyproject.toml", "")
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        boost.report.prioritized_gaps = [
            CoverageGap(file="nonexistent.py", name="missing", coverage_pct=0),
        ]
        prompts = boost.build_test_prompts()
        assert len(prompts) == 0

    def test_respects_max_files(self, tmp_path):
        _make_file(tmp_path, "pyproject.toml", "")
        for i in range(15):
            _make_file(tmp_path, f"src/mod{i}.py", f"x = {i}")
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        boost.report.prioritized_gaps = [
            CoverageGap(file=f"src/mod{i}.py", name=f"mod{i}") for i in range(15)
        ]
        prompts = boost.build_test_prompts(max_files=5)
        assert len(prompts) == 5

    def test_java_test_path(self, tmp_path):
        _make_file(tmp_path, "pom.xml", "")
        _make_file(tmp_path, "src/main/java/com/Foo.java", "class Foo {}")
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        boost.report.prioritized_gaps = [
            CoverageGap(file="src/main/java/com/Foo.java", name="Foo"),
        ]
        prompts = boost.build_test_prompts()
        assert prompts[0]["test_file"] == "src/test/java/com/FooTest.java"

    def test_go_test_path(self, tmp_path):
        _make_file(tmp_path, "go.mod", "module m")
        _make_file(tmp_path, "pkg/handler.go", "package pkg")
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        boost.report.prioritized_gaps = [
            CoverageGap(file="pkg/handler.go", name="handler"),
        ]
        prompts = boost.build_test_prompts()
        assert prompts[0]["test_file"] == "pkg/handler_test.go"


class TestBuildDelegationPrompt:
    """Test build_delegation_prompt."""

    def test_includes_all_sections(self, tmp_path):
        _make_file(tmp_path, "pyproject.toml", "")
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        boost.report.coverage_pct = 55.0
        prompts = [
            {
                "source_file": "src/app.py",
                "test_file": "tests/test_app.py",
                "source_code": "class App: pass",
                "language": "python",
                "framework": "pytest",
                "gap_name": "app",
                "current_coverage": 0,
                "risk": "high",
            }
        ]
        result = boost.build_delegation_prompt(prompts)
        assert "AUTO-COVERAGE BOOST" in result
        assert "python" in result
        assert "pytest" in result
        assert "55.0%" in result
        assert "src/app.py" in result
        assert "INSTRUCTIONS:" in result


# ---------------------------------------------------------------------------
# Git operations
# ---------------------------------------------------------------------------


class TestGitOperations:
    """Test git_create_branch and git_add_and_commit."""

    @patch("subprocess.run")
    def test_create_branch(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0)
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        assert boost.git_create_branch("coverage/test-branch") is True
        mock_run.assert_called_once()
        args = mock_run.call_args
        assert "checkout" in args[0][0]
        assert "-b" in args[0][0]

    @patch("subprocess.run")
    def test_create_branch_failure(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=1, stderr="error")
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        assert boost.git_create_branch("bad-branch") is False

    @patch("subprocess.run")
    def test_add_and_commit(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0)
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        assert boost.git_add_and_commit(["tests/test_foo.py"]) is True
        assert mock_run.call_count == 2  # git add + git commit

    @patch("subprocess.run")
    def test_add_and_commit_empty_files(self, mock_run, tmp_path):
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        assert boost.git_add_and_commit([]) is False
        mock_run.assert_not_called()

    @patch("subprocess.run")
    def test_add_failure(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=1, stderr="add failed")
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        assert boost.git_add_and_commit(["test.py"]) is False

    @patch("subprocess.run")
    def test_default_branch_name(self, mock_run, tmp_path):
        mock_run.return_value = MagicMock(returncode=0)
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        boost.git_create_branch()
        call_args = mock_run.call_args[0][0]
        assert any("coverage/auto-boost" in str(a) for a in call_args)


# ---------------------------------------------------------------------------
# Format report
# ---------------------------------------------------------------------------


class TestFormatCoverageReport:
    """Test format_coverage_report."""

    def test_basic_report(self):
        report = CoverageReport(
            repo_path="/tmp/my-repo",
            language="python",
            test_framework="pytest",
            test_file_count=5,
            test_method_count=20,
            coverage_pct=65.0,
            total_lines=1000,
            covered_lines=650,
            target_pct=80.0,
        )
        output = format_coverage_report(report)
        assert "AUTO-COVERAGE BOOST" in output
        assert "python" in output
        assert "pytest" in output
        assert "65.0%" in output
        assert "650/1000" in output
        assert "15.0% to target" in output

    def test_target_met(self):
        report = CoverageReport(
            repo_path="/tmp/repo",
            language="java",
            test_framework="junit",
            coverage_pct=85.0,
            target_pct=80.0,
        )
        output = format_coverage_report(report)
        assert "Target met!" in output

    def test_with_gaps(self):
        report = CoverageReport(
            repo_path="/tmp/repo",
            language="python",
            test_framework="pytest",
            prioritized_gaps=[
                CoverageGap(file="auth.py", name="auth", coverage_pct=0, risk="critical"),
                CoverageGap(file="utils.py", name="utils", coverage_pct=80, risk="low"),
            ],
        )
        output = format_coverage_report(report)
        assert "Priority Gaps (2)" in output
        assert "[!!]" in output  # critical icon
        assert "auth" in output

    def test_with_new_tests(self):
        report = CoverageReport(
            repo_path="/tmp/repo",
            language="python",
            test_framework="pytest",
            new_tests_written=[{"file": "tests/test_auth.py", "test_count": 5}],
        )
        output = format_coverage_report(report)
        assert "Tests Written" in output
        assert "test_auth.py" in output

    def test_with_final_coverage(self):
        report = CoverageReport(
            repo_path="/tmp/repo",
            language="python",
            test_framework="pytest",
            final_coverage_pct=82.0,
            improvement_pct=17.0,
        )
        output = format_coverage_report(report)
        assert "Final Coverage" in output
        assert "82.0%" in output
        assert "+17.0%" in output


# ---------------------------------------------------------------------------
# Pipeline orchestration
# ---------------------------------------------------------------------------


class TestRunPipeline:
    """Test run_pipeline."""

    def test_dry_run_pipeline(self, tmp_path):
        _make_file(tmp_path, "pyproject.toml", "")
        _make_file(tmp_path, "src/foo.py", "x = 1")
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        report = boost.run_pipeline(dry_run=True)
        assert report.repo_path == str(tmp_path)
        assert report.language == "python"
        # dry_run skips coverage baseline
        assert report.coverage_pct == 0

    def test_pipeline_with_no_source_files(self, tmp_path):
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        report = boost.run_pipeline(dry_run=True)
        assert report.language == ""
        assert len(report.gaps) == 0

    @patch("subprocess.run")
    def test_pipeline_runs_baseline(self, mock_run, tmp_path):
        _make_file(tmp_path, "pyproject.toml", "")
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        report = boost.run_pipeline(dry_run=False)
        # subprocess.run called for coverage baseline (may call coverage json too)
        assert mock_run.called


# ---------------------------------------------------------------------------
# Coverage baseline edge cases (lines 135-171)
# ---------------------------------------------------------------------------


class TestRunCoverageBaseline:
    def test_no_test_command(self, tmp_path):
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        result = boost.run_coverage_baseline()
        assert result["coverage"] == 0

    @patch("subprocess.run")
    def test_timeout(self, mock_run, tmp_path):
        import subprocess as sp
        _make_file(tmp_path, "pyproject.toml", "")
        mock_run.side_effect = sp.TimeoutExpired(cmd="pytest", timeout=300)
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        result = boost.run_coverage_baseline()
        assert result["coverage"] == 0
        assert result.get("error") == "timeout"

    @patch("subprocess.run")
    def test_java_coverage(self, mock_run, tmp_path):
        _make_file(tmp_path, "pom.xml", "")
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        # No actual XML file, just ensure it doesn't crash
        result = boost.run_coverage_baseline()
        assert "coverage" in result

    @patch("subprocess.run")
    def test_go_coverage(self, mock_run, tmp_path):
        _make_file(tmp_path, "go.mod", "module m")
        mock_run.return_value = MagicMock(
            returncode=0, stdout="coverage: 75.0% of statements", stderr=""
        )
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        result = boost.run_coverage_baseline()
        assert boost.report.coverage_pct == 75.0


# ---------------------------------------------------------------------------
# Scan existing tests — file read error (line 135-136)
# ---------------------------------------------------------------------------


class TestScanExistingTestsError:
    def test_unreadable_test_file(self, tmp_path):
        _make_file(tmp_path, "pyproject.toml", "")
        test_file = _make_file(tmp_path, "tests/test_bad.py", "def test_one(): pass")
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        with patch("builtins.open", side_effect=Exception("read error")):
            result = boost.scan_existing_tests()
        # File is counted (name check) but methods=0 (read fails, caught by except)
        assert result["files"] == 1
        assert result["methods"] == 0


# ---------------------------------------------------------------------------
# _find_uncovered_files for Java (lines 292-310)
# ---------------------------------------------------------------------------


class TestFindUncoveredJava:
    def test_finds_uncovered_java_files(self, tmp_path):
        _make_file(tmp_path, "pom.xml", "")
        _make_file(tmp_path, "src/main/java/Service.java", "class Service {}")
        _make_file(tmp_path, "src/test/java/ServiceTest.java", "@Test void test() {}")
        _make_file(tmp_path, "src/main/java/Utils.java", "class Utils {}")
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        boost.scan_existing_tests()
        boost._find_uncovered_files()
        gap_names = [g.name for g in boost.report.gaps]
        assert "Utils" in gap_names
        assert "Service" not in gap_names


# ---------------------------------------------------------------------------
# Build test prompts — JS and unknown language (lines 369-374)
# ---------------------------------------------------------------------------


class TestBuildTestPromptsJS:
    def test_javascript_test_path(self, tmp_path):
        _make_file(tmp_path, "package.json", "{}")
        _make_file(tmp_path, "src/app.js", "const x = 1;")
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        boost.report.prioritized_gaps = [
            CoverageGap(file="src/app.js", name="app"),
        ]
        prompts = boost.build_test_prompts()
        assert prompts[0]["test_file"] == "src/app.test.js"

    def test_unknown_language_test_path(self, tmp_path):
        _make_file(tmp_path, "app.rb", "puts 'hello'")
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        boost.report.prioritized_gaps = [
            CoverageGap(file="app.rb", name="app"),
        ]
        prompts = boost.build_test_prompts()
        assert prompts[0]["test_file"] == "tests/test_app.rb"


# ---------------------------------------------------------------------------
# Git operations — commit failure (lines 465-469)
# ---------------------------------------------------------------------------


class TestGitCommitFailure:
    @patch("subprocess.run")
    def test_commit_fails(self, mock_run, tmp_path):
        mock_run.side_effect = [
            MagicMock(returncode=0),  # git add
            MagicMock(returncode=1, stderr="hook failed"),  # git commit
        ]
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        assert boost.git_add_and_commit(["test.py"]) is False

    @patch("subprocess.run")
    def test_git_exception(self, mock_run, tmp_path):
        mock_run.side_effect = Exception("git error")
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        assert boost.git_add_and_commit(["test.py"]) is False

    @patch("subprocess.run")
    def test_branch_exception(self, mock_run, tmp_path):
        mock_run.side_effect = Exception("git error")
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        assert boost.git_create_branch("branch") is False


# ---------------------------------------------------------------------------
# Prioritize gaps — edge (lines 327-331)
# ---------------------------------------------------------------------------


class TestPrioritizeGapsEdge:
    def test_high_coverage_is_low_risk(self, tmp_path):
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        boost.report.gaps = [
            CoverageGap(file="foo.py", name="foo", coverage_pct=85),
        ]
        boost.prioritize_gaps()
        assert boost.report.prioritized_gaps[0].risk == "low"

    def test_service_pattern_is_high(self, tmp_path):
        boost = AutoCoverageBoost(cwd=str(tmp_path))
        boost.report.gaps = [
            CoverageGap(file="src/controller.py", name="controller", coverage_pct=50),
        ]
        boost.prioritize_gaps()
        assert boost.report.prioritized_gaps[0].risk == "high"


# ---------------------------------------------------------------------------
# Format report edge cases (lines 535-538)
# ---------------------------------------------------------------------------


class TestFormatCoverageReportEdge:
    def test_many_gaps_truncated(self):
        report = CoverageReport(
            repo_path="/tmp/repo",
            language="python",
            test_framework="pytest",
            prioritized_gaps=[
                CoverageGap(file=f"file{i}.py", name=f"file{i}", coverage_pct=i, risk="medium")
                for i in range(20)
            ],
        )
        output = format_coverage_report(report)
        assert "... and 5 more" in output
