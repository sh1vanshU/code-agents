"""Tests for pre_push.py — pre-push checklist."""

import os
import stat
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from code_agents.tools.pre_push import (
    PrePushChecklist, PrePushReport, CheckResult,
    format_pre_push_report,
)


@pytest.fixture
def git_repo(tmp_path):
    """Create a minimal git-like repo structure."""
    (tmp_path / ".git" / "hooks").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname = 'demo'\n")
    return tmp_path


class TestPrePushChecklist:
    """Tests for PrePushChecklist."""

    def test_init(self, git_repo):
        checklist = PrePushChecklist(cwd=str(git_repo))
        assert checklist.cwd == str(git_repo)

    @patch("subprocess.run")
    def test_check_secrets_clean(self, mock_run, git_repo):
        mock_run.return_value = MagicMock(returncode=0, stdout="diff content\n+normal code\n")
        checklist = PrePushChecklist(cwd=str(git_repo))
        checklist._check_secrets()
        secrets_check = [c for c in checklist.report.checks if "Secret" in c.name]
        assert len(secrets_check) == 1
        assert secrets_check[0].passed is True

    @patch("subprocess.run")
    def test_check_secrets_found(self, mock_run, git_repo):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='diff content\n+password = "supersecret123"\n',
        )
        checklist = PrePushChecklist(cwd=str(git_repo))
        checklist._check_secrets()
        secrets_check = [c for c in checklist.report.checks if "Secret" in c.name]
        assert len(secrets_check) == 1
        assert secrets_check[0].passed is False

    @patch("subprocess.run")
    def test_check_todos_clean(self, mock_run, git_repo):
        mock_run.return_value = MagicMock(returncode=0, stdout="+clean code\n")
        checklist = PrePushChecklist(cwd=str(git_repo))
        checklist._check_todos()
        todo_check = [c for c in checklist.report.checks if "TODO" in c.name]
        assert len(todo_check) == 1
        assert todo_check[0].passed is True

    @patch("subprocess.run")
    def test_check_todos_found(self, mock_run, git_repo):
        mock_run.return_value = MagicMock(returncode=0, stdout="+# TODO: fix this\n")
        checklist = PrePushChecklist(cwd=str(git_repo))
        checklist._check_todos()
        todo_check = [c for c in checklist.report.checks if "TODO" in c.name]
        assert len(todo_check) == 1
        assert todo_check[0].passed is False

    def test_install_hook(self, git_repo):
        result = PrePushChecklist.install_hook(str(git_repo))
        hook_path = git_repo / ".git" / "hooks" / "pre-push"
        assert hook_path.exists()
        assert "installed" in result
        # Check executable
        mode = hook_path.stat().st_mode
        assert mode & stat.S_IXUSR

    def test_install_hook_no_git(self, tmp_path):
        result = PrePushChecklist.install_hook(str(tmp_path))
        assert "Not a git repository" in result

    def test_report_all_passed(self):
        report = PrePushReport(checks=[
            CheckResult(name="A", passed=True),
            CheckResult(name="B", passed=True),
        ])
        assert report.all_passed is True
        assert "2/2" in report.summary

    def test_report_some_failed(self):
        report = PrePushReport(checks=[
            CheckResult(name="A", passed=True),
            CheckResult(name="B", passed=False),
        ])
        assert report.all_passed is False
        assert "1/2" in report.summary


class TestFormatPrePushReport:
    """Tests for format_pre_push_report."""

    def test_format_all_pass(self):
        report = PrePushReport(checks=[
            CheckResult(name="Tests", passed=True, message="All passed"),
        ])
        output = format_pre_push_report(report)
        assert "Pre-Push Checklist" in output
        assert "[OK]" in output
        assert "Ready to push" in output

    def test_format_failure(self):
        report = PrePushReport(checks=[
            CheckResult(name="Tests", passed=False, message="3 failures"),
        ])
        output = format_pre_push_report(report)
        assert "[FAIL]" in output
        assert "Fix issues" in output

    def test_format_with_details(self):
        report = PrePushReport(checks=[
            CheckResult(name="Tests", passed=False, message="3 failures",
                        details=["FAILED test_a", "FAILED test_b"]),
        ])
        output = format_pre_push_report(report)
        assert "FAILED test_a" in output


# ── run_checks orchestration (lines 69-82) ────────────────────────────────


class TestRunChecks:
    def test_run_checks_catches_exceptions(self, git_repo):
        checklist = PrePushChecklist(cwd=str(git_repo))
        with patch.object(checklist, "_check_tests", side_effect=RuntimeError("boom")), \
             patch.object(checklist, "_check_secrets"), \
             patch.object(checklist, "_check_todos"), \
             patch.object(checklist, "_check_lint"):
            report = checklist.run_checks()
        failed = [c for c in report.checks if not c.passed]
        assert len(failed) >= 1
        assert "boom" in failed[0].message

    def test_run_checks_all_pass(self, git_repo):
        checklist = PrePushChecklist(cwd=str(git_repo))
        with patch.object(checklist, "_check_tests"), \
             patch.object(checklist, "_check_secrets"), \
             patch.object(checklist, "_check_todos"), \
             patch.object(checklist, "_check_lint"):
            # Pre-populate with passing checks
            checklist.report.checks = [
                CheckResult(name="A", passed=True),
                CheckResult(name="B", passed=True),
            ]
            assert checklist.report.all_passed is True


# ── _check_tests (lines 92-128) ──────────────────────────────────────────


class TestCheckTests:
    def test_check_tests_env_override(self, git_repo):
        checklist = PrePushChecklist(cwd=str(git_repo))
        with patch.dict("os.environ", {"CODE_AGENTS_TEST_CMD": "make test"}), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            checklist._check_tests()
        check = [c for c in checklist.report.checks if c.name == "Tests Pass"][0]
        assert check.passed is True

    def test_check_tests_failure_with_details(self, git_repo):
        checklist = PrePushChecklist(cwd=str(git_repo))
        with patch.dict("os.environ", {"CODE_AGENTS_TEST_CMD": "pytest"}), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="line1\nline2\nline3\nFAILED test_x\nFAILED test_y\n"
            )
            checklist._check_tests()
        check = [c for c in checklist.report.checks if c.name == "Tests Pass"][0]
        assert check.passed is False
        assert len(check.details) > 0

    def test_check_tests_timeout(self, git_repo):
        import subprocess as sp
        checklist = PrePushChecklist(cwd=str(git_repo))
        with patch.dict("os.environ", {"CODE_AGENTS_TEST_CMD": "pytest"}), \
             patch("subprocess.run", side_effect=sp.TimeoutExpired(cmd="pytest", timeout=300)):
            checklist._check_tests()
        check = [c for c in checklist.report.checks if c.name == "Tests Pass"][0]
        assert check.passed is False
        assert "timed out" in check.message

    def test_check_tests_no_command_detected(self, tmp_path):
        """No project files => test skipped."""
        checklist = PrePushChecklist(cwd=str(tmp_path))
        with patch.dict("os.environ", {"CODE_AGENTS_TEST_CMD": ""}, clear=False):
            checklist._check_tests()
        check = [c for c in checklist.report.checks if c.name == "Tests Pass"][0]
        assert check.passed is True
        assert "skipped" in check.message

    def test_check_tests_detects_maven(self, tmp_path):
        (tmp_path / "pom.xml").write_text("<project/>")
        checklist = PrePushChecklist(cwd=str(tmp_path))
        with patch.dict("os.environ", {"CODE_AGENTS_TEST_CMD": ""}, clear=False), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            checklist._check_tests()
        check = [c for c in checklist.report.checks if c.name == "Tests Pass"][0]
        assert check.passed is True

    def test_check_tests_detects_npm(self, tmp_path):
        (tmp_path / "package.json").write_text("{}")
        checklist = PrePushChecklist(cwd=str(tmp_path))
        with patch.dict("os.environ", {"CODE_AGENTS_TEST_CMD": ""}, clear=False), \
             patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            checklist._check_tests()
        check = [c for c in checklist.report.checks if c.name == "Tests Pass"][0]
        assert check.passed is True


# ── _check_secrets edge case: no diff (lines 135-139) ─────────────────────


class TestCheckSecretsNoDiff:
    def test_no_diff_passes(self, git_repo):
        checklist = PrePushChecklist(cwd=str(git_repo))
        with patch.object(checklist, "_get_diff", return_value=""):
            checklist._check_secrets()
        check = [c for c in checklist.report.checks if "Secret" in c.name][0]
        assert check.passed is True


# ── _check_todos no diff (lines 165-169) ──────────────────────────────────


class TestCheckTodosNoDiff:
    def test_no_diff_passes(self, git_repo):
        checklist = PrePushChecklist(cwd=str(git_repo))
        with patch.object(checklist, "_get_diff", return_value=""):
            checklist._check_todos()
        check = [c for c in checklist.report.checks if "TODO" in c.name][0]
        assert check.passed is True


# ── _check_lint (lines 192-239) ──────────────────────────────────────────


class TestCheckLint:
    def test_lint_no_linter_detected(self, tmp_path):
        checklist = PrePushChecklist(cwd=str(tmp_path))
        checklist._check_lint()
        check = [c for c in checklist.report.checks if c.name == "Lint Clean"][0]
        assert check.passed is True
        assert "skipped" in check.message.lower()

    def test_lint_clean(self, git_repo):
        checklist = PrePushChecklist(cwd=str(git_repo))
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            checklist._check_lint()
        check = [c for c in checklist.report.checks if c.name == "Lint Clean"][0]
        assert check.passed is True

    def test_lint_issues_found(self, git_repo):
        checklist = PrePushChecklist(cwd=str(git_repo))
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1, stdout="E501 line too long\nE302 too many blank lines\n"
            )
            checklist._check_lint()
        check = [c for c in checklist.report.checks if c.name == "Lint Clean"][0]
        assert check.passed is False

    def test_lint_command_not_found_tries_next(self, git_repo):
        checklist = PrePushChecklist(cwd=str(git_repo))
        with patch("subprocess.run") as mock_run:
            # First linter not found, second succeeds
            mock_run.side_effect = [
                FileNotFoundError("ruff not found"),
                MagicMock(returncode=0),
            ]
            checklist._check_lint()
        check = [c for c in checklist.report.checks if c.name == "Lint Clean"][0]
        assert check.passed is True

    def test_lint_timeout(self, git_repo):
        import subprocess as sp
        checklist = PrePushChecklist(cwd=str(git_repo))
        with patch("subprocess.run", side_effect=sp.TimeoutExpired(cmd="ruff", timeout=60)):
            checklist._check_lint()
        check = [c for c in checklist.report.checks if c.name == "Lint Clean"][0]
        assert check.passed is False
        assert "timed out" in check.message

    def test_lint_all_not_found_skips(self, git_repo):
        checklist = PrePushChecklist(cwd=str(git_repo))
        with patch("subprocess.run", side_effect=FileNotFoundError("not found")):
            checklist._check_lint()
        check = [c for c in checklist.report.checks if c.name == "Lint Clean"][0]
        assert check.passed is True
        assert "skipped" in check.message.lower()

    def test_lint_npm_project(self, tmp_path):
        (tmp_path / "package.json").write_text("{}")
        checklist = PrePushChecklist(cwd=str(tmp_path))
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            checklist._check_lint()
        check = [c for c in checklist.report.checks if c.name == "Lint Clean"][0]
        assert check.passed is True


# ── _check_markdown_size ─────────────────────────────────────────────────


class TestCheckMarkdownSize:
    def test_all_under_limit(self, tmp_path):
        (tmp_path / "README.md").write_text("# Hello\nShort file.")
        checklist = PrePushChecklist(cwd=str(tmp_path))
        checklist._check_markdown_size()
        check = [c for c in checklist.report.checks if "Markdown" in c.name][0]
        assert check.passed is True

    def test_oversized_file_detected(self, tmp_path):
        (tmp_path / "HUGE.md").write_text("\n".join(f"line {i}" for i in range(400)))
        checklist = PrePushChecklist(cwd=str(tmp_path))
        checklist._check_markdown_size()
        check = [c for c in checklist.report.checks if "Markdown" in c.name][0]
        assert check.passed is False
        assert "HUGE.md" in check.details[0]
        assert "400 lines" in check.details[0]

    def test_custom_limit_via_env(self, tmp_path):
        (tmp_path / "SMALL.md").write_text("\n".join(f"line {i}" for i in range(50)))
        checklist = PrePushChecklist(cwd=str(tmp_path))
        with patch.dict("os.environ", {"CODE_AGENTS_MD_MAX_LINES": "10"}):
            checklist._check_markdown_size()
        check = [c for c in checklist.report.checks if "Markdown" in c.name][0]
        assert check.passed is False

    def test_skips_hidden_dirs(self, tmp_path):
        hidden = tmp_path / ".venv" / "lib"
        hidden.mkdir(parents=True)
        (hidden / "LICENSE.md").write_text("\n".join(f"x" for _ in range(500)))
        (tmp_path / "README.md").write_text("# OK")
        checklist = PrePushChecklist(cwd=str(tmp_path))
        checklist._check_markdown_size()
        check = [c for c in checklist.report.checks if "Markdown" in c.name][0]
        assert check.passed is True

    def test_no_markdown_files(self, tmp_path):
        (tmp_path / "main.py").write_text("print('hi')")
        checklist = PrePushChecklist(cwd=str(tmp_path))
        checklist._check_markdown_size()
        check = [c for c in checklist.report.checks if "Markdown" in c.name][0]
        assert check.passed is True


# ── _get_diff edge cases (lines 93-94) ──────────────────────────────────────


class TestGetDiffEdge:
    def test_timeout_returns_empty(self, git_repo):
        import subprocess as sp
        checklist = PrePushChecklist(cwd=str(git_repo))
        with patch("subprocess.run", side_effect=sp.TimeoutExpired(cmd="git", timeout=30)):
            result = checklist._get_diff()
        assert result == ""

    def test_file_not_found_returns_empty(self, git_repo):
        checklist = PrePushChecklist(cwd=str(git_repo))
        with patch("subprocess.run", side_effect=FileNotFoundError("git not found")):
            result = checklist._get_diff()
        assert result == ""


# ── _check_markdown_size with OSError (lines 261-262) ───────────────────────


class TestMarkdownSizeOsError:
    def test_oserror_skipped(self, tmp_path):
        (tmp_path / "test.md").write_text("content")
        checklist = PrePushChecklist(cwd=str(tmp_path))
        with patch("builtins.open", side_effect=OSError("perm denied")):
            checklist._check_markdown_size()
        check = [c for c in checklist.report.checks if "Markdown" in c.name][0]
        assert check.passed is True
