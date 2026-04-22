"""CLI tests grouped by feature area (split from legacy monolith)."""
from __future__ import annotations

import os
import sys
from unittest.mock import patch, MagicMock

import pytest


class TestCmdSessions:
    """Test sessions command."""

    def test_sessions_list_empty(self, capsys):
        from code_agents.cli.cli_tools import cmd_sessions
        with patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp"), \
             patch("code_agents.chat.chat_history.list_sessions", return_value=[]):
            cmd_sessions([])
        output = capsys.readouterr().out
        assert "No saved chat sessions" in output

    def test_sessions_list_with_all_flag(self, capsys):
        from code_agents.cli.cli_tools import cmd_sessions
        with patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp"), \
             patch("code_agents.chat.chat_history.list_sessions", return_value=[]):
            cmd_sessions(["--all"])
        output = capsys.readouterr().out
        assert "No saved chat sessions" in output
        # Should NOT suggest --all since we already used it
        assert "--all" not in output.split("No saved chat sessions")[1] or "all repos" not in output.split("No saved chat sessions")[1]

    def test_sessions_delete_no_id(self, capsys):
        from code_agents.cli.cli_tools import cmd_sessions
        with patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp"):
            cmd_sessions(["delete"])
        output = capsys.readouterr().out
        assert "Usage:" in output

    def test_sessions_delete_found(self, capsys):
        from code_agents.cli.cli_tools import cmd_sessions
        with patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp"), \
             patch("code_agents.chat.chat_history.delete_session", return_value=True):
            cmd_sessions(["delete", "abc123"])
        output = capsys.readouterr().out
        assert "Deleted" in output
        assert "abc123" in output

    def test_sessions_delete_not_found(self, capsys):
        from code_agents.cli.cli_tools import cmd_sessions
        with patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp"), \
             patch("code_agents.chat.chat_history.delete_session", return_value=False):
            cmd_sessions(["delete", "missing"])
        output = capsys.readouterr().out
        assert "not found" in output

    def test_sessions_list_with_data(self, capsys):
        from code_agents.cli.cli_tools import cmd_sessions
        import time
        sessions = [
            {
                "id": "uuid-123",
                "title": "Test session",
                "agent": "code-writer",
                "message_count": 5,
                "updated_at": time.time(),
                "repo_path": "/home/user/project",
            }
        ]
        with patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp"), \
             patch("code_agents.chat.chat_history.list_sessions", return_value=sessions):
            cmd_sessions([])
        output = capsys.readouterr().out
        assert "uuid-123" in output
        assert "Test session" in output
        assert "code-writer" in output

# ── extra session / meta command coverage ──

class TestCmdChangelog:
    """Test changelog command."""

    def test_changelog_default(self, capsys):
        from code_agents.cli.cli_tools import cmd_changelog
        mock_data = MagicMock()
        with patch("code_agents.generators.changelog_gen.ChangelogGenerator") as MockGen, \
             patch("code_agents.generators.changelog_gen.format_changelog_terminal", return_value="Changelog here"):
            MockGen.return_value.generate.return_value = mock_data
            cmd_changelog([])
        output = capsys.readouterr().out
        assert "Changelog Generator" in output
        assert "Changelog here" in output

# ── extra session / meta command coverage ──

class TestCmdOnboard:
    """Test onboard command."""

    def test_onboard_terminal(self, capsys):
        from code_agents.cli.cli_tools import cmd_onboard
        mock_profile = MagicMock()
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp"), \
             patch("code_agents.tools.onboarding.OnboardingGenerator") as MockGen, \
             patch("code_agents.tools.onboarding.format_onboarding_terminal", return_value="Onboard info"):
            MockGen.return_value.scan.return_value = mock_profile
            cmd_onboard([])
        output = capsys.readouterr().out
        assert "Onboarding Guide" in output
        assert "Onboard info" in output

# ── extra session / meta command coverage ──

class TestCmdWatchdog:
    """Test watchdog command."""

    def test_watchdog_default(self, capsys):
        from code_agents.cli.cli_tools import cmd_watchdog
        mock_report = MagicMock()
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.tools.watchdog.PostDeployWatchdog") as MockWD, \
             patch("code_agents.tools.watchdog.format_watchdog_report", return_value="Watchdog report"):
            MockWD.return_value.run.return_value = mock_report
            cmd_watchdog([])
        output = capsys.readouterr().out
        assert "Post-Deploy Watchdog" in output
        assert "Watchdog report" in output

    def test_watchdog_custom_minutes(self, capsys):
        from code_agents.cli.cli_tools import cmd_watchdog
        mock_report = MagicMock()
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.tools.watchdog.PostDeployWatchdog") as MockWD, \
             patch("code_agents.tools.watchdog.format_watchdog_report", return_value="report"):
            MockWD.return_value.run.return_value = mock_report
            cmd_watchdog(["--minutes", "30"])
        output = capsys.readouterr().out
        assert "30 minutes" in output

# ── extra session / meta command coverage ──

class TestCmdPrePush:
    """Test pre-push command."""

    def test_pre_push_passes(self, capsys):
        from code_agents.cli.cli_tools import cmd_pre_push
        mock_report = MagicMock()
        mock_report.all_passed = True
        with patch("code_agents.tools.pre_push.PrePushChecklist") as MockPP, \
             patch("code_agents.tools.pre_push.format_pre_push_report", return_value="All good"), \
             patch.dict(os.environ, {"CODE_AGENTS_USER_CWD": "/tmp"}):
            MockPP.return_value.run_checks.return_value = mock_report
            cmd_pre_push([])
        output = capsys.readouterr().out
        assert "Pre-Push Checklist" in output
        assert "All good" in output

    def test_pre_push_fails_exits_1(self, capsys):
        from code_agents.cli.cli_tools import cmd_pre_push
        mock_report = MagicMock()
        mock_report.all_passed = False
        with patch("code_agents.tools.pre_push.PrePushChecklist") as MockPP, \
             patch("code_agents.tools.pre_push.format_pre_push_report", return_value="Failures"), \
             patch.dict(os.environ, {"CODE_AGENTS_USER_CWD": "/tmp"}), \
             pytest.raises(SystemExit) as exc:
            MockPP.return_value.run_checks.return_value = mock_report
            cmd_pre_push([])
        assert exc.value.code == 1

    def test_pre_push_install(self, capsys):
        from code_agents.cli.cli_tools import cmd_pre_push
        with patch("code_agents.tools.pre_push.PrePushChecklist") as MockPP, \
             patch.dict(os.environ, {"CODE_AGENTS_USER_CWD": "/tmp"}):
            MockPP.install_hook.return_value = "Hook installed"
            cmd_pre_push(["install"])
        output = capsys.readouterr().out
        assert "Hook installed" in output
