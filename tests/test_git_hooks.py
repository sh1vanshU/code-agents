"""Tests for code_agents.git_hooks — install, uninstall, analysis, rendering."""

from __future__ import annotations

import os
import stat
import textwrap
from unittest.mock import patch, MagicMock

import pytest

from code_agents.git_ops.git_hooks import (
    GitHooksManager,
    HookFinding,
    HookReport,
    PreCommitAnalyzer,
    PrePushAnalyzer,
    render_hook_report,
    _MARKER,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def git_repo(tmp_path):
    """Create a minimal git repo structure."""
    hooks_dir = tmp_path / ".git" / "hooks"
    hooks_dir.mkdir(parents=True)
    return tmp_path


@pytest.fixture
def manager(git_repo):
    return GitHooksManager(str(git_repo))


# ---------------------------------------------------------------------------
# TestInstall
# ---------------------------------------------------------------------------

class TestInstall:
    def test_install_creates_hook_files(self, manager, git_repo):
        installed = manager.install(["pre-commit", "pre-push"])
        assert "pre-commit" in installed
        assert "pre-push" in installed

        hook = git_repo / ".git" / "hooks" / "pre-commit"
        assert hook.exists()
        assert _MARKER in hook.read_text()
        # Check executable
        mode = hook.stat().st_mode
        assert mode & stat.S_IXUSR

    def test_install_backs_up_existing(self, manager, git_repo):
        hook_path = git_repo / ".git" / "hooks" / "pre-commit"
        hook_path.write_text("#!/bin/sh\necho existing\n")

        manager.install(["pre-commit"])

        backup = git_repo / ".git" / "hooks" / "pre-commit.backup"
        assert backup.exists()
        assert "existing" in backup.read_text()
        assert _MARKER in hook_path.read_text()

    def test_install_skips_own_hook_backup(self, manager, git_repo):
        hook_path = git_repo / ".git" / "hooks" / "pre-commit"
        hook_path.write_text(f"#!/bin/sh\n{_MARKER}\ncode-agents hook-run pre-commit\n")

        manager.install(["pre-commit"])

        backup = git_repo / ".git" / "hooks" / "pre-commit.backup"
        assert not backup.exists()

    def test_install_no_git_dir(self, tmp_path):
        mgr = GitHooksManager(str(tmp_path))
        installed = mgr.install()
        assert installed == []

    def test_install_unknown_hook(self, manager):
        installed = manager.install(["post-merge"])
        assert installed == []


# ---------------------------------------------------------------------------
# TestUninstall
# ---------------------------------------------------------------------------

class TestUninstall:
    def test_uninstall_removes_hook(self, manager, git_repo):
        manager.install(["pre-commit"])
        removed = manager.uninstall(["pre-commit"])
        assert "pre-commit" in removed
        assert not (git_repo / ".git" / "hooks" / "pre-commit").exists()

    def test_uninstall_restores_backup(self, manager, git_repo):
        hook_path = git_repo / ".git" / "hooks" / "pre-commit"
        hook_path.write_text("#!/bin/sh\necho original\n")

        manager.install(["pre-commit"])
        manager.uninstall(["pre-commit"])

        assert hook_path.exists()
        assert "original" in hook_path.read_text()

    def test_uninstall_skips_foreign_hook(self, git_repo):
        hook_path = git_repo / ".git" / "hooks" / "pre-commit"
        hook_path.write_text("#!/bin/sh\necho foreign\n")

        mgr = GitHooksManager(str(git_repo))
        removed = mgr.uninstall(["pre-commit"])
        assert removed == []
        assert hook_path.exists()

    def test_uninstall_nonexistent(self, manager):
        removed = manager.uninstall(["pre-commit"])
        assert removed == []


# ---------------------------------------------------------------------------
# TestStatus
# ---------------------------------------------------------------------------

class TestStatus:
    def test_status_none_installed(self, manager):
        status = manager.status()
        assert status == {"pre-commit": False, "pre-push": False}

    def test_status_after_install(self, manager):
        manager.install(["pre-commit"])
        status = manager.status()
        assert status["pre-commit"] is True
        assert status["pre-push"] is False

    def test_status_foreign_hook_not_detected(self, git_repo):
        hook_path = git_repo / ".git" / "hooks" / "pre-commit"
        hook_path.write_text("#!/bin/sh\necho foreign\n")
        mgr = GitHooksManager(str(git_repo))
        status = mgr.status()
        assert status["pre-commit"] is False


# ---------------------------------------------------------------------------
# TestPreCommit
# ---------------------------------------------------------------------------

class TestPreCommit:
    DIFF_WITH_SECRET = textwrap.dedent("""\
        diff --git a/config.py b/config.py
        +++ b/config.py
        @@ -1,3 +1,4 @@
        +API_KEY = "sk-abc123def456ghi789jkl012mno345pqr678stu901vwx234"
    """)

    DIFF_WITH_DEBUG = textwrap.dedent("""\
        diff --git a/main.py b/main.py
        +++ b/main.py
        @@ -1,3 +1,4 @@
        +print("debugging value")
    """)

    DIFF_WITH_EVAL = textwrap.dedent("""\
        diff --git a/handler.py b/handler.py
        +++ b/handler.py
        @@ -1,3 +1,4 @@
        +result = eval(user_input)
    """)

    DIFF_WITH_TODO = textwrap.dedent("""\
        diff --git a/app.py b/app.py
        +++ b/app.py
        @@ -1,3 +1,4 @@
        +# TODO: fix this later
    """)

    CLEAN_DIFF = textwrap.dedent("""\
        diff --git a/utils.py b/utils.py
        +++ b/utils.py
        @@ -1,3 +1,4 @@
        +def helper(): pass
    """)

    @patch("code_agents.git_ops.git_hooks._run_git")
    def test_detects_secrets(self, mock_git, tmp_path):
        mock_git.return_value = self.DIFF_WITH_SECRET
        analyzer = PreCommitAnalyzer(str(tmp_path))
        report = analyzer.analyze()
        assert not report.passed
        assert report.critical_count >= 1
        assert any("secret" in f.message.lower() or "Secret" in f.message for f in report.findings)

    @patch("code_agents.git_ops.git_hooks._run_git")
    def test_detects_debug_statements(self, mock_git, tmp_path):
        mock_git.return_value = self.DIFF_WITH_DEBUG
        analyzer = PreCommitAnalyzer(str(tmp_path))
        report = analyzer.analyze()
        assert report.warning_count >= 1
        assert any("debug" in f.message.lower() or "Debug" in f.message for f in report.findings)

    @patch("code_agents.git_ops.git_hooks._run_git")
    def test_detects_eval(self, mock_git, tmp_path):
        mock_git.return_value = self.DIFF_WITH_EVAL
        analyzer = PreCommitAnalyzer(str(tmp_path))
        report = analyzer.analyze()
        assert any("eval" in f.message.lower() for f in report.findings)

    @patch("code_agents.git_ops.git_hooks._run_git")
    def test_detects_todos(self, mock_git, tmp_path):
        mock_git.return_value = self.DIFF_WITH_TODO
        analyzer = PreCommitAnalyzer(str(tmp_path))
        report = analyzer.analyze()
        assert report.info_count >= 1

    @patch("code_agents.git_ops.git_hooks._run_git")
    def test_clean_diff_passes(self, mock_git, tmp_path):
        mock_git.return_value = self.CLEAN_DIFF
        analyzer = PreCommitAnalyzer(str(tmp_path))
        report = analyzer.analyze()
        assert report.passed

    @patch("code_agents.git_ops.git_hooks._run_git")
    def test_empty_diff(self, mock_git, tmp_path):
        mock_git.return_value = ""
        analyzer = PreCommitAnalyzer(str(tmp_path))
        report = analyzer.analyze()
        assert report.passed
        assert "No staged" in report.summary


# ---------------------------------------------------------------------------
# TestPrePush
# ---------------------------------------------------------------------------

class TestPrePush:
    @patch("code_agents.git_ops.git_hooks._run_git")
    def test_blast_radius_warning(self, mock_git, tmp_path):
        """Many files changed triggers blast radius warning."""
        # Generate a diff with 55 files
        diff_lines = []
        for i in range(55):
            diff_lines.append(f"+++ b/file_{i}.py")
            diff_lines.append(f"+pass")
        diff = "\n".join(diff_lines)

        def side_effect(args, cwd):
            if "log" in args:
                return "abc1234 commit 1\ndef5678 commit 2\n"
            if "diff" in args:
                return diff
            return ""

        mock_git.side_effect = side_effect
        analyzer = PrePushAnalyzer(str(tmp_path))
        report = analyzer.analyze()
        assert any("blast radius" in f.message.lower() for f in report.findings)

    @patch("code_agents.git_ops.git_hooks._run_git")
    def test_secrets_in_commits(self, mock_git, tmp_path):
        diff = textwrap.dedent("""\
            diff --git a/secrets.py b/secrets.py
            +++ b/secrets.py
            +password = "supersecretpassword123"
        """)

        def side_effect(args, cwd):
            if "log" in args:
                return "abc1234 add secrets\n"
            if "diff" in args:
                return diff
            return ""

        mock_git.side_effect = side_effect
        analyzer = PrePushAnalyzer(str(tmp_path))
        report = analyzer.analyze()
        assert not report.passed
        assert report.critical_count >= 1

    @patch("code_agents.git_ops.git_hooks._run_git")
    def test_missing_tests_info(self, mock_git, tmp_path):
        diff = textwrap.dedent("""\
            diff --git a/handler.py b/handler.py
            +++ b/handler.py
            +def handle(): pass
        """)

        def side_effect(args, cwd):
            if "log" in args:
                return "abc1234 add handler\n"
            if "diff" in args:
                return diff
            return ""

        mock_git.side_effect = side_effect
        analyzer = PrePushAnalyzer(str(tmp_path))
        report = analyzer.analyze()
        assert any("test" in f.message.lower() for f in report.findings)


# ---------------------------------------------------------------------------
# TestRender
# ---------------------------------------------------------------------------

class TestRender:
    def test_render_passed(self):
        report = HookReport(
            hook_type="pre-commit",
            findings=[],
            passed=True,
            summary="All checks passed — no issues found.",
        )
        output = render_hook_report(report)
        assert "Pre Commit Review" in output
        assert "PASSED" in output

    def test_render_blocked(self):
        report = HookReport(
            hook_type="pre-commit",
            findings=[
                HookFinding(severity="critical", message="Hardcoded API key", file="config.py", line=10),
                HookFinding(severity="warning", message="shell=True usage", file="utils.py", line=5),
                HookFinding(severity="info", message="TODO added", file="app.py", line=20),
            ],
            passed=False,
            summary="3 finding(s): 1 critical, 1 warning(s), 1 info.",
        )
        output = render_hook_report(report)
        assert "BLOCKED" in output
        assert "CRITICAL" in output
        assert "WARNING" in output
        assert "INFO" in output
        assert "config.py:10" in output

    def test_render_pre_push(self):
        report = HookReport(
            hook_type="pre-push",
            findings=[],
            passed=True,
            summary="All checks passed.",
        )
        output = render_hook_report(report)
        assert "Pre Push Review" in output
        assert "PASSED" in output
