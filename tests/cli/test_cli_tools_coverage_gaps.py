"""CLI tests grouped by feature area (split from legacy monolith)."""
from __future__ import annotations

import os
import sys
from unittest.mock import patch, MagicMock

import pytest


class TestCmdUpdatePaths:
    """Test cmd_update additional paths."""

    def test_update_already_up_to_date(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_update
        import subprocess as _sp
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "abc1234"
        mock_result.stderr = ""
        with patch("code_agents.cli.cli_tools._find_code_agents_home", return_value=tmp_path), \
             patch("subprocess.run", return_value=mock_result):
            cmd_update()
        output = capsys.readouterr().out
        assert "Already up to date" in output

    def test_update_pull_fails(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_update
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        call_count = [0]
        def mock_run(*args, **kwargs):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] <= 2:
                # rev-parse --short HEAD, rev-parse --abbrev-ref
                result.returncode = 0
                result.stdout = "abc1234" if call_count[0] == 1 else "main"
                result.stderr = ""
            elif call_count[0] == 3:
                # remote get-url
                result.returncode = 0
                result.stdout = "https://example.com/repo.git"
                result.stderr = ""
            elif call_count[0] == 4:
                # git pull fails
                result.returncode = 1
                result.stdout = ""
                result.stderr = "fatal: could not read"
            return result
        with patch("code_agents.cli.cli_tools._find_code_agents_home", return_value=tmp_path), \
             patch("subprocess.run", side_effect=mock_run):
            cmd_update()
        output = capsys.readouterr().out
        assert "git pull failed" in output

    def test_update_ssh_fallback_to_https(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_update
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        call_count = [0]
        def mock_run(*args, **kwargs):
            call_count[0] += 1
            result = MagicMock()
            if call_count[0] == 1:
                result.returncode = 0
                result.stdout = "abc1234"
                result.stderr = ""
            elif call_count[0] == 2:
                result.returncode = 0
                result.stdout = "main"
                result.stderr = ""
            elif call_count[0] == 3:
                result.returncode = 0
                result.stdout = "git@github.com:code-agents-org/code-agents.git"
                result.stderr = ""
            elif call_count[0] == 4:
                # SSH pull fails
                result.returncode = 1
                result.stdout = ""
                result.stderr = "Permission denied"
            elif call_count[0] == 5:
                # set-url to HTTPS
                result.returncode = 0
                result.stdout = ""
                result.stderr = ""
            elif call_count[0] == 6:
                # HTTPS pull succeeds
                result.returncode = 0
                result.stdout = ""
                result.stderr = ""
            elif call_count[0] == 7:
                # new commit hash (same = up to date)
                result.returncode = 0
                result.stdout = "abc1234"
                result.stderr = ""
            else:
                result.returncode = 0
                result.stdout = ""
                result.stderr = ""
            return result
        with patch("code_agents.cli.cli_tools._find_code_agents_home", return_value=tmp_path), \
             patch("subprocess.run", side_effect=mock_run):
            cmd_update()
        output = capsys.readouterr().out
        assert "HTTPS" in output or "Already up to date" in output

    def test_update_with_changes(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_update
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        call_count = [0]
        def mock_run(*args, **kwargs):
            call_count[0] += 1
            result = MagicMock()
            result.returncode = 0
            result.stderr = ""
            if call_count[0] == 1:
                result.stdout = "abc1234"
            elif call_count[0] == 2:
                result.stdout = "main"
            elif call_count[0] == 3:
                result.stdout = "https://example.com/repo.git"
            elif call_count[0] == 4:
                # pull succeeds
                result.stdout = "Updating abc1234..def5678"
            elif call_count[0] == 5:
                # new commit
                result.stdout = "def5678"
            elif call_count[0] == 6:
                # diff --stat
                result.stdout = " file.py | 5 ++---\n 1 file changed"
            elif call_count[0] == 7:
                # log
                result.stdout = "def5678 feat: new feature"
            elif call_count[0] == 8:
                # poetry install
                result.stdout = ""
            else:
                result.stdout = ""
            return result
        with patch("code_agents.cli.cli_tools._find_code_agents_home", return_value=tmp_path), \
             patch("subprocess.run", side_effect=mock_run), \
             patch("code_agents.cli.cli_completions._generate_zsh_completion", return_value="# comp"), \
             patch("code_agents.cli.cli_completions._generate_bash_completion", return_value="# comp"), \
             patch("builtins.open", MagicMock()):
            cmd_update()
        output = capsys.readouterr().out
        assert "Updated" in output or "New commits" in output
class TestCmdMigrateWithData:
    """Test migrate command with actual data."""

    def test_migrate_with_vars_confirmed(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_migrate
        env_file = tmp_path / ".env"
        env_file.write_text("CURSOR_API_KEY=sk-123\nJENKINS_URL=http://jenkins\n")
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch("builtins.input", return_value="y"), \
             patch("code_agents.setup.setup._write_env_to_path"), \
             patch("shutil.move"):
            cmd_migrate()
        output = capsys.readouterr().out
        assert "Migrating" in output
        assert "Migration complete" in output

    def test_migrate_cancelled(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_migrate
        env_file = tmp_path / ".env"
        env_file.write_text("HOST=0.0.0.0\n")
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch("builtins.input", return_value="n"):
            cmd_migrate()
        output = capsys.readouterr().out
        assert "Cancelled" in output

    def test_migrate_eof_on_confirm(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_migrate
        env_file = tmp_path / ".env"
        env_file.write_text("HOST=0.0.0.0\n")
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch("builtins.input", side_effect=EOFError):
            cmd_migrate()
class TestCmdSessionsCleanup:
    """Test sessions cleanup subcommand."""

    def test_sessions_cleanup_default(self, capsys):
        from code_agents.cli.cli_tools import cmd_sessions
        mock_result = {"deleted_age": 2, "deleted_count": 1, "remaining": 10}
        with patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp"), \
             patch("code_agents.chat.chat_history.cleanup_sessions", return_value=mock_result):
            cmd_sessions(["cleanup"])
        output = capsys.readouterr().out
        assert "Cleaned up" in output
        assert "3" in output  # 2 + 1

    def test_sessions_cleanup_nothing(self, capsys):
        from code_agents.cli.cli_tools import cmd_sessions
        mock_result = {"deleted_age": 0, "deleted_count": 0, "remaining": 5}
        with patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp"), \
             patch("code_agents.chat.chat_history.cleanup_sessions", return_value=mock_result):
            cmd_sessions(["cleanup"])
        output = capsys.readouterr().out
        assert "No sessions to clean up" in output

    def test_sessions_cleanup_with_flags(self, capsys):
        from code_agents.cli.cli_tools import cmd_sessions
        mock_result = {"deleted_age": 1, "deleted_count": 0, "remaining": 3}
        with patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp"), \
             patch("code_agents.chat.chat_history.cleanup_sessions", return_value=mock_result) as mock_cleanup:
            cmd_sessions(["cleanup", "--days=7", "--max=50"])
        mock_cleanup.assert_called_once_with(max_age_days=7, max_count=50)

    def test_sessions_clear_eof(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_sessions
        history_dir = tmp_path / "history"
        history_dir.mkdir()
        (history_dir / "sess1.json").write_text("{}")
        with patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp"), \
             patch("code_agents.chat.chat_history.HISTORY_DIR", history_dir), \
             patch("builtins.input", side_effect=EOFError):
            cmd_sessions(["clear"])
        # Should not crash

    def test_sessions_clear_no_history_dir(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_sessions
        history_dir = tmp_path / "nonexistent"
        with patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp"), \
             patch("code_agents.chat.chat_history.HISTORY_DIR", history_dir):
            cmd_sessions(["clear"])
        output = capsys.readouterr().out
        assert "No sessions to clear" in output
class TestCmdRulesDeleteEOF:
    """Test rules delete with EOF."""

    def test_rules_delete_eof(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_rules
        rule_file = tmp_path / "test_rule.md"
        rule_file.write_text("# rule")
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch("builtins.input", side_effect=EOFError):
            cmd_rules(["delete", str(rule_file)])
        # Should not crash, file should still exist
        assert rule_file.exists()

    def test_rules_edit_existing_file(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_rules
        rule_file = tmp_path / "test_rule.md"
        rule_file.write_text("# rule")
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch("subprocess.run"):
            cmd_rules(["edit", str(rule_file)])
        # Should have tried to open editor

    def test_rules_list_with_agent_filter(self, capsys):
        from code_agents.cli.cli_tools import cmd_rules
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp"), \
             patch("code_agents.agent_system.rules_loader.list_rules", return_value=[]) as mock_list:
            cmd_rules(["list", "--agent", "code-writer"])
        mock_list.assert_called_once_with(agent_name="code-writer", repo_path="/tmp")
class TestCmdReposRemoveError:
    """Test repos remove error case."""

    def test_repos_remove_error(self, capsys):
        from code_agents.cli.cli_tools import cmd_repos
        mock_rm = MagicMock()
        mock_rm.repos = {"x": True}
        mock_rm.remove_repo.side_effect = ValueError("cannot remove")
        with patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp"), \
             patch("code_agents.domain.repo_manager.get_repo_manager", return_value=mock_rm):
            cmd_repos(["remove", "my-repo"])
        output = capsys.readouterr().out
        assert "cannot remove" in output
class TestCmdWatchdogInvalidMinutes:
    """Test watchdog with invalid minutes."""

    def test_watchdog_invalid_minutes(self, capsys):
        from code_agents.cli.cli_tools import cmd_watchdog
        mock_report = MagicMock()
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.tools.watchdog.PostDeployWatchdog") as MockWD, \
             patch("code_agents.tools.watchdog.format_watchdog_report", return_value="report"):
            MockWD.return_value.run.return_value = mock_report
            cmd_watchdog(["--minutes", "notanumber"])
        output = capsys.readouterr().out
        # Should default to 15 minutes
        assert "15 minutes" in output
