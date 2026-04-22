"""Tests for headless/CI mode — HeadlessRunner, report formatting, exit codes."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from code_agents.devops.headless_mode import (
    HeadlessReport,
    HeadlessRunner,
    TaskResult,
    format_headless_json,
    format_headless_report,
)


# ---------------------------------------------------------------------------
# TaskResult basics
# ---------------------------------------------------------------------------

class TestTaskResult:
    def test_defaults(self):
        r = TaskResult(task="fix-lint", success=True, changes=2, findings=0, output="ok")
        assert r.error == ""
        assert r.duration_s == 0.0

    def test_with_error(self):
        r = TaskResult(task="review", success=False, changes=0, findings=0, output="", error="boom")
        assert r.error == "boom"
        assert not r.success


# ---------------------------------------------------------------------------
# HeadlessReport
# ---------------------------------------------------------------------------

class TestReport:
    def test_exit_code_0_clean(self):
        report = HeadlessReport(tasks=[
            TaskResult(task="fix-lint", success=True, changes=1, findings=0, output="ok"),
            TaskResult(task="audit", success=True, changes=0, findings=0, output="clean"),
        ])
        report.compute()
        assert report.exit_code == 0
        assert report.total_changes == 1
        assert report.total_findings == 0

    def test_exit_code_1_findings(self):
        report = HeadlessReport(tasks=[
            TaskResult(task="fix-lint", success=True, changes=0, findings=3, output="3 issues"),
            TaskResult(task="audit", success=True, changes=0, findings=0, output="clean"),
        ])
        report.compute()
        assert report.exit_code == 1
        assert report.total_findings == 3

    def test_exit_code_2_errors(self):
        report = HeadlessReport(tasks=[
            TaskResult(task="fix-lint", success=True, changes=0, findings=0, output="ok"),
            TaskResult(task="review", success=False, changes=0, findings=0, output="", error="fail"),
        ])
        report.compute()
        assert report.exit_code == 2

    def test_errors_override_findings(self):
        """Errors (exit 2) take priority over findings (exit 1)."""
        report = HeadlessReport(tasks=[
            TaskResult(task="fix-lint", success=True, changes=0, findings=5, output="issues"),
            TaskResult(task="review", success=False, changes=0, findings=0, output="", error="fail"),
        ])
        report.compute()
        assert report.exit_code == 2

    def test_empty_tasks(self):
        report = HeadlessReport(tasks=[])
        report.compute()
        assert report.exit_code == 0
        assert report.total_changes == 0
        assert report.total_findings == 0


# ---------------------------------------------------------------------------
# HeadlessRunner — task dispatch
# ---------------------------------------------------------------------------

class TestRunTask:
    def setup_method(self):
        self.runner = HeadlessRunner(cwd="/tmp/test-repo")

    def test_unknown_task(self):
        result = self.runner._run_task("nonexistent-task")
        assert not result.success
        assert "Unknown task" in result.error
        assert "nonexistent-task" in result.error

    @patch.object(HeadlessRunner, "_shell")
    def test_fix_lint_no_issues(self, mock_shell):
        mock_shell.return_value = (0, "")
        result = self.runner._fix_lint()
        assert result.success
        assert result.task == "fix-lint"

    @patch.object(HeadlessRunner, "_shell")
    def test_fix_lint_with_changes(self, mock_shell):
        # First call: fix command; second: count changed; third: check command; fourth: count
        call_count = {"n": 0}
        def side_effect(cmd, timeout=120):
            call_count["n"] += 1
            if "autopep8" in cmd or "eslint" in cmd and "--fix" in cmd:
                return (0, "")
            if "git diff --name-only" in cmd:
                if call_count["n"] <= 2:
                    return (0, "")  # before
                return (0, "file1.py\nfile2.py")  # after
            if "flake8" in cmd or "eslint" in cmd:
                return (1, "error1\nerror2")
            return (0, "")
        mock_shell.side_effect = side_effect
        result = self.runner._fix_lint()
        assert result.success

    @patch.object(HeadlessRunner, "_shell")
    def test_security_scan_clean(self, mock_shell):
        mock_shell.return_value = (0, "")
        result = self.runner._security_scan()
        assert result.success
        assert result.findings == 0
        assert "No security issues" in result.output

    @patch.object(HeadlessRunner, "_shell")
    def test_security_scan_findings(self, mock_shell):
        def side_effect(cmd, timeout=120):
            if "hardcoded" in cmd or "password" in cmd:
                return (0, "src/config.py\nsrc/auth.py")
            return (0, "")
        mock_shell.side_effect = side_effect
        result = self.runner._security_scan()
        assert result.success
        assert result.findings >= 2

    @patch.object(HeadlessRunner, "_shell")
    def test_review_pr_success(self, mock_shell):
        def side_effect(cmd, timeout=120):
            if "diff main...HEAD --stat" in cmd:
                return (0, " file1.py | 10 +\n file2.py | 5 -\n 2 files changed")
            if "grep -c" in cmd:
                return (0, "3")
            return (0, "")
        mock_shell.side_effect = side_effect
        result = self.runner._review_pr()
        assert result.success
        assert result.findings == 3

    @patch.object(HeadlessRunner, "_shell")
    def test_review_pr_no_branch(self, mock_shell):
        mock_shell.return_value = (1, "fatal: not a git repo")
        result = self.runner._review_pr()
        assert not result.success

    @patch.object(HeadlessRunner, "_shell")
    def test_dead_code(self, mock_shell):
        def side_effect(cmd, timeout=120):
            if "pyflakes" in cmd:
                return (0, "5")
            if "grep -rl" in cmd:
                return (0, "2")
            return (0, "")
        mock_shell.side_effect = side_effect
        result = self.runner._dead_code()
        assert result.success
        assert result.findings == 7

    @patch.object(HeadlessRunner, "_shell")
    def test_pci_scan_clean(self, mock_shell):
        mock_shell.return_value = (0, "")
        result = self.runner._pci_scan()
        assert result.success
        assert result.findings == 0

    @patch.object(HeadlessRunner, "_shell")
    def test_audit_no_deps(self, mock_shell):
        # No requirements.txt or pyproject.toml in /tmp/test-repo
        result = self.runner._audit()
        assert result.success

    def test_gen_tests_uncovered(self):
        with patch("pathlib.Path.rglob", return_value=[]), \
             patch("pathlib.Path.exists", return_value=False):
            result = self.runner._gen_tests_uncovered()
            assert result.success
            assert result.task == "gen-tests"

    def test_update_docs_no_readme(self):
        with patch("pathlib.Path.exists", return_value=False):
            result = self.runner._update_docs()
            assert result.success
            assert result.findings >= 1

    def test_task_exception_handled(self):
        """If a handler raises, _run_task catches it."""
        self.runner._handlers["fix-lint"] = MagicMock(side_effect=RuntimeError("boom"))
        result = self.runner._run_task("fix-lint")
        assert not result.success
        assert "boom" in result.error


# ---------------------------------------------------------------------------
# Full run
# ---------------------------------------------------------------------------

class TestFullRun:
    @patch.object(HeadlessRunner, "_shell")
    def test_run_multiple_tasks(self, mock_shell):
        mock_shell.return_value = (0, "")
        runner = HeadlessRunner(cwd="/tmp/test-repo")
        report = runner.run(["fix-lint", "security-scan"])
        assert len(report.tasks) == 2
        assert report.exit_code == 0

    def test_run_with_unknown_task(self):
        runner = HeadlessRunner(cwd="/tmp/test-repo")
        report = runner.run(["unknown-task"])
        assert len(report.tasks) == 1
        assert report.exit_code == 2  # error


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

class TestFormat:
    def _sample_report(self) -> HeadlessReport:
        report = HeadlessReport(tasks=[
            TaskResult(task="fix-lint", success=True, changes=3, findings=0, output="3 files auto-formatted", duration_s=1.5),
            TaskResult(task="review", success=True, changes=5, findings=2, output="2 TODO markers", duration_s=3.2),
            TaskResult(task="security-scan", success=False, changes=0, findings=0, output="", error="scanner crashed", duration_s=0.1),
        ])
        report.compute()
        return report

    def test_terminal_format(self):
        report = self._sample_report()
        text = format_headless_report(report)
        assert "Code Agents CI Run" in text
        assert "[PASS] fix-lint" in text
        assert "[WARN] review" in text
        assert "[FAIL] security-scan" in text
        assert "Exit code: 2" in text

    def test_terminal_format_clean(self):
        report = HeadlessReport(tasks=[
            TaskResult(task="audit", success=True, changes=0, findings=0, output="clean"),
        ])
        report.compute()
        text = format_headless_report(report)
        assert "Exit code: 0" in text
        assert "clean" in text

    def test_json_format(self):
        report = self._sample_report()
        raw = format_headless_json(report)
        data = json.loads(raw)
        assert data["exit_code"] == 2
        assert data["exit_label"] == "errors occurred"
        assert len(data["tasks"]) == 3
        assert data["tasks"][0]["task"] == "fix-lint"
        assert data["total_changes"] == 8
        assert data["total_findings"] == 2

    def test_json_roundtrip(self):
        report = HeadlessReport(tasks=[
            TaskResult(task="audit", success=True, changes=0, findings=0, output="ok"),
        ])
        report.compute()
        raw = format_headless_json(report)
        data = json.loads(raw)
        assert isinstance(data["tasks"], list)
        assert data["exit_code"] == 0


# ---------------------------------------------------------------------------
# Unknown task edge cases
# ---------------------------------------------------------------------------

class TestUnknownTask:
    def test_unknown_returns_error(self):
        runner = HeadlessRunner(cwd="/tmp")
        result = runner._run_task("deploy-production")
        assert not result.success
        assert "Unknown task" in result.error
        assert "deploy-production" in result.error

    def test_known_tasks_list(self):
        runner = HeadlessRunner(cwd="/tmp")
        assert "fix-lint" in runner.KNOWN_TASKS
        assert "gen-tests" in runner.KNOWN_TASKS
        assert "security-scan" in runner.KNOWN_TASKS
        assert len(runner.KNOWN_TASKS) == 8

    def test_all_known_tasks_have_handlers(self):
        runner = HeadlessRunner(cwd="/tmp")
        for task_name in runner.KNOWN_TASKS:
            assert task_name in runner._handlers, f"Missing handler for {task_name}"
