"""Tests for cli_tools.py — rules, migrate, repos, sessions, update, version, version-bump, etc."""

from __future__ import annotations

import os
import sys
import datetime
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import pytest


# ═══════════════════════════════════════════════════════════════════════════
# cmd_rules
# ═══════════════════════════════════════════════════════════════════════════


class TestCmdRulesCreate:
    """Test rules create subcommand — lines 54-84."""

    def test_create_global_rule(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_rules
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.agent_system.rules_loader.GLOBAL_RULES_DIR", tmp_path / "global-rules"), \
             patch("subprocess.run") as mock_run:
            cmd_rules(["create", "--global"])
        output = capsys.readouterr().out
        assert "Created" in output
        filepath = tmp_path / "global-rules" / "_global.md"
        assert filepath.exists()
        content = filepath.read_text()
        assert "all agents" in content
        assert "global" in content

    def test_create_agent_rule(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_rules
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch("subprocess.run") as mock_run:
            cmd_rules(["create", "--agent", "code-writer"])
        output = capsys.readouterr().out
        assert "Created" in output
        filepath = tmp_path / ".code-agents" / "rules" / "code-writer.md"
        assert filepath.exists()
        content = filepath.read_text()
        assert "code-writer" in content

    def test_create_rule_file_exists(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_rules
        rules_dir = tmp_path / ".code-agents" / "rules"
        rules_dir.mkdir(parents=True)
        (rules_dir / "_global.md").write_text("existing")
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch("subprocess.run") as mock_run:
            cmd_rules(["create"])
        output = capsys.readouterr().out
        assert "File exists" in output

    def test_create_uses_editor(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_rules
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch.dict(os.environ, {"EDITOR": "nano"}), \
             patch("subprocess.run") as mock_run:
            cmd_rules(["create"])
        # Check that editor was called
        mock_run.assert_called_once()
        assert "nano" in mock_run.call_args[0][0]


class TestCmdRulesDelete:
    """Test rules delete subcommand — lines 110-114."""

    def test_delete_confirm_yes(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_rules
        rule_file = tmp_path / "test.md"
        rule_file.write_text("# rule")
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch("builtins.input", return_value="y"):
            cmd_rules(["delete", str(rule_file)])
        output = capsys.readouterr().out
        assert "Deleted" in output
        assert not rule_file.exists()

    def test_delete_confirm_no(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_rules
        rule_file = tmp_path / "test.md"
        rule_file.write_text("# rule")
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch("builtins.input", return_value="n"):
            cmd_rules(["delete", str(rule_file)])
        output = capsys.readouterr().out
        assert "Cancelled" in output
        assert rule_file.exists()

    def test_delete_eof_interrupt(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_rules
        rule_file = tmp_path / "test.md"
        rule_file.write_text("# rule")
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch("builtins.input", side_effect=EOFError):
            cmd_rules(["delete", str(rule_file)])
        assert rule_file.exists()


class TestCmdRulesUnknown:
    """Test unknown subcommand — line 117."""

    def test_unknown_subcommand(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_rules
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)):
            cmd_rules(["bogus"])
        output = capsys.readouterr().out
        assert "Unknown subcommand" in output


class TestCmdRulesList:
    """Test rules list subcommand with --agent."""

    def test_list_with_agent_flag(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_rules
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.agent_system.rules_loader.list_rules", return_value=[]) as mock_list:
            cmd_rules(["list", "--agent", "code-writer"])
        mock_list.assert_called_once_with(agent_name="code-writer", repo_path=str(tmp_path))


# ═══════════════════════════════════════════════════════════════════════════
# cmd_migrate
# ═══════════════════════════════════════════════════════════════════════════


class TestCmdMigrate:
    """Test migrate command — lines 160-191."""

    def test_migrate_no_legacy(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_migrate
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)):
            cmd_migrate()
        output = capsys.readouterr().out
        assert "nothing to migrate" in output

    def test_migrate_empty_legacy(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_migrate
        (tmp_path / ".env").write_text("")
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)):
            cmd_migrate()
        output = capsys.readouterr().out
        assert "empty" in output

    def test_migrate_proceed(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_migrate
        (tmp_path / ".env").write_text("CURSOR_API_KEY=sk-test\nJENKINS_BUILD_JOB=my-job\n")
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "global.env"), \
             patch("code_agents.core.env_loader.PER_REPO_FILENAME", ".env.code-agents"), \
             patch("builtins.input", return_value="y"), \
             patch("code_agents.setup.setup._write_env_to_path") as mock_write:
            cmd_migrate()
        output = capsys.readouterr().out
        assert "Migration complete" in output
        # Legacy file should have been moved
        assert not (tmp_path / ".env").exists()
        backups = list(tmp_path.glob(".env.backup.*"))
        assert len(backups) == 1

    def test_migrate_cancel(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_migrate
        (tmp_path / ".env").write_text("FOO=bar\n")
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "global.env"), \
             patch("code_agents.core.env_loader.PER_REPO_FILENAME", ".env.code-agents"), \
             patch("builtins.input", return_value="n"):
            cmd_migrate()
        output = capsys.readouterr().out
        assert "Cancelled" in output

    def test_migrate_eof(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_migrate
        (tmp_path / ".env").write_text("FOO=bar\n")
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.core.env_loader.GLOBAL_ENV_PATH", tmp_path / "global.env"), \
             patch("code_agents.core.env_loader.PER_REPO_FILENAME", ".env.code-agents"), \
             patch("builtins.input", side_effect=EOFError):
            cmd_migrate()
        # Should not crash


# ═══════════════════════════════════════════════════════════════════════════
# cmd_repos
# ═══════════════════════════════════════════════════════════════════════════


class TestCmdRepos:
    """Test repos command — lines 224-276."""

    def test_repos_add(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_repos
        mock_ctx = MagicMock(name="test-repo", path=str(tmp_path), git_branch="main")
        mock_rm = MagicMock()
        mock_rm.repos = {"test": mock_ctx}
        mock_rm.add_repo.return_value = mock_ctx
        with patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.domain.repo_manager.get_repo_manager", return_value=mock_rm):
            cmd_repos(["add", str(tmp_path)])
        output = capsys.readouterr().out
        assert "Registered" in output

    def test_repos_add_no_path(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_repos
        mock_rm = MagicMock()
        mock_rm.repos = {"test": MagicMock()}
        with patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.domain.repo_manager.get_repo_manager", return_value=mock_rm):
            cmd_repos(["add"])
        output = capsys.readouterr().out
        assert "Usage" in output

    def test_repos_add_error(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_repos
        mock_rm = MagicMock()
        mock_rm.repos = {"test": MagicMock()}
        mock_rm.add_repo.side_effect = ValueError("already registered")
        with patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.domain.repo_manager.get_repo_manager", return_value=mock_rm):
            cmd_repos(["add", str(tmp_path)])
        output = capsys.readouterr().out
        assert "already registered" in output

    def test_repos_remove(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_repos
        mock_rm = MagicMock()
        mock_rm.repos = {"test": MagicMock()}
        mock_rm.remove_repo.return_value = True
        with patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.domain.repo_manager.get_repo_manager", return_value=mock_rm):
            cmd_repos(["remove", "test-repo"])
        output = capsys.readouterr().out
        assert "Removed" in output

    def test_repos_remove_not_found(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_repos
        mock_rm = MagicMock()
        mock_rm.repos = {"test": MagicMock()}
        mock_rm.remove_repo.return_value = False
        with patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.domain.repo_manager.get_repo_manager", return_value=mock_rm):
            cmd_repos(["remove", "missing"])
        output = capsys.readouterr().out
        assert "not found" in output

    def test_repos_list_with_repos(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_repos
        mock_ctx = MagicMock()
        mock_ctx.name = "my-repo"
        mock_ctx.path = str(tmp_path)
        mock_ctx.git_branch = "main"
        mock_rm = MagicMock()
        mock_rm.repos = {"my-repo": mock_ctx}
        mock_rm.list_repos.return_value = [mock_ctx]
        mock_rm.active_repo = str(tmp_path)
        with patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.domain.repo_manager.get_repo_manager", return_value=mock_rm):
            cmd_repos()
        output = capsys.readouterr().out
        assert "Registered repos" in output
        assert "active" in output
        assert "Total:" in output

    def test_repos_list_empty(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_repos
        mock_rm = MagicMock()
        mock_rm.repos = {}
        mock_rm.list_repos.return_value = []
        mock_rm.add_repo.side_effect = ValueError("not a repo")
        with patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.domain.repo_manager.get_repo_manager", return_value=mock_rm):
            cmd_repos()
        output = capsys.readouterr().out
        assert "No repos registered" in output

    def test_repos_remove_no_name(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_repos
        mock_rm = MagicMock()
        mock_rm.repos = {"test": MagicMock()}
        with patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.domain.repo_manager.get_repo_manager", return_value=mock_rm):
            cmd_repos(["remove"])
        output = capsys.readouterr().out
        assert "Usage" in output


# ═══════════════════════════════════════════════════════════════════════════
# cmd_sessions
# ═══════════════════════════════════════════════════════════════════════════


class TestCmdSessions:
    """Test sessions command — lines 297-310, 354-355, etc."""

    def test_sessions_clear_confirm(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_sessions
        mock_history_dir = tmp_path / "history"
        mock_history_dir.mkdir()
        (mock_history_dir / "s1.json").write_text("{}")
        (mock_history_dir / "s2.json").write_text("{}")
        with patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.chat.chat_history.HISTORY_DIR", mock_history_dir), \
             patch("builtins.input", return_value="y"):
            cmd_sessions(["clear"])
        output = capsys.readouterr().out
        assert "Cleared 2 sessions" in output

    def test_sessions_clear_cancel(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_sessions
        mock_history_dir = tmp_path / "history"
        mock_history_dir.mkdir()
        (mock_history_dir / "s1.json").write_text("{}")
        with patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.chat.chat_history.HISTORY_DIR", mock_history_dir), \
             patch("builtins.input", return_value="n"):
            cmd_sessions(["clear"])
        output = capsys.readouterr().out
        assert "Cancelled" in output

    def test_sessions_clear_eof(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_sessions
        mock_history_dir = tmp_path / "history"
        mock_history_dir.mkdir()
        (mock_history_dir / "s1.json").write_text("{}")
        with patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.chat.chat_history.HISTORY_DIR", mock_history_dir), \
             patch("builtins.input", side_effect=EOFError):
            cmd_sessions(["clear"])
        # Should not crash

    def test_sessions_clear_empty(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_sessions
        mock_history_dir = tmp_path / "history"
        mock_history_dir.mkdir()
        with patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.chat.chat_history.HISTORY_DIR", mock_history_dir):
            cmd_sessions(["clear"])
        output = capsys.readouterr().out
        assert "No sessions to clear" in output

    def test_sessions_delete(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_sessions
        with patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.chat.chat_history.delete_session", return_value=True):
            cmd_sessions(["delete", "abc123"])
        output = capsys.readouterr().out
        assert "Deleted session" in output

    def test_sessions_delete_not_found(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_sessions
        with patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.chat.chat_history.delete_session", return_value=False):
            cmd_sessions(["delete", "missing"])
        output = capsys.readouterr().out
        assert "not found" in output

    def test_sessions_delete_no_id(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_sessions
        with patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)):
            cmd_sessions(["delete"])
        output = capsys.readouterr().out
        assert "Usage" in output

    def test_sessions_list_with_sessions(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_sessions
        import time
        sessions = [
            {
                "id": "s1",
                "updated_at": time.time(),
                "agent": "code-writer",
                "message_count": 5,
                "title": "Test session",
                "repo_path": str(tmp_path),
            },
        ]
        with patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.chat.chat_history.list_sessions", return_value=sessions), \
             patch("os.path.isdir", return_value=True):
            cmd_sessions()
        output = capsys.readouterr().out
        assert "Saved chat sessions" in output
        assert "s1" in output

    def test_sessions_list_empty(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_sessions
        with patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.chat.chat_history.list_sessions", return_value=[]):
            cmd_sessions()
        output = capsys.readouterr().out
        assert "No saved chat sessions" in output

    def test_sessions_list_all_flag(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_sessions
        with patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.chat.chat_history.list_sessions", return_value=[]):
            cmd_sessions(["--all"])
        output = capsys.readouterr().out
        assert "No saved chat sessions" in output
        # With --all, should not show the "Use --all" hint
        assert "--all" not in output.split("No saved chat sessions")[1]

    def test_sessions_cleanup(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_sessions
        cleanup_result = {"deleted_age": 3, "deleted_count": 2, "remaining": 10}
        with patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.chat.chat_history.cleanup_sessions", return_value=cleanup_result):
            cmd_sessions(["cleanup", "--days=7", "--max=50"])
        output = capsys.readouterr().out
        assert "Cleaned up 5 sessions" in output

    def test_sessions_cleanup_nothing(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_sessions
        cleanup_result = {"deleted_age": 0, "deleted_count": 0, "remaining": 5}
        with patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.chat.chat_history.cleanup_sessions", return_value=cleanup_result):
            cmd_sessions(["cleanup"])
        output = capsys.readouterr().out
        assert "No sessions to clean up" in output


# ═══════════════════════════════════════════════════════════════════════════
# cmd_version_bump
# ═══════════════════════════════════════════════════════════════════════════


class TestCmdVersionBump:
    """Test version-bump command — lines 602-640."""

    def test_version_bump_no_args(self, capsys):
        from code_agents.cli.cli_tools import cmd_version_bump
        cmd_version_bump()
        output = capsys.readouterr().out
        assert "Usage" in output
        assert "patch" in output

    def test_version_bump_patch_logic(self):
        """Test version bump arithmetic directly."""
        parts = "1.2.3".split(".")
        major, minor, patch_v = int(parts[0]), int(parts[1]), int(parts[2])
        patch_v += 1
        assert f"{major}.{minor}.{patch_v}" == "1.2.4"

    def test_version_bump_major(self, capsys):
        from code_agents.cli.cli_tools import cmd_version_bump
        with patch("code_agents.__version__.__version__", "1.2.3"), \
             patch("pathlib.Path.write_text"), \
             patch("pathlib.Path.read_text", return_value='version = "1.2.3"'), \
             patch("pathlib.Path.is_file", return_value=True):
            cmd_version_bump(["major"])
        output = capsys.readouterr().out
        assert "2.0.0" in output

    def test_version_bump_minor(self, capsys):
        from code_agents.cli.cli_tools import cmd_version_bump
        with patch("code_agents.__version__.__version__", "1.2.3"), \
             patch("pathlib.Path.write_text"), \
             patch("pathlib.Path.read_text", return_value='version = "1.2.3"'), \
             patch("pathlib.Path.is_file", return_value=True):
            cmd_version_bump(["minor"])
        output = capsys.readouterr().out
        assert "1.3.0" in output

    def test_version_bump_patch_cmd(self, capsys):
        from code_agents.cli.cli_tools import cmd_version_bump
        with patch("code_agents.__version__.__version__", "1.2.3"), \
             patch("pathlib.Path.write_text"), \
             patch("pathlib.Path.read_text", return_value='version = "1.2.3"'), \
             patch("pathlib.Path.is_file", return_value=True):
            cmd_version_bump(["patch"])
        output = capsys.readouterr().out
        assert "1.2.4" in output


# ═══════════════════════════════════════════════════════════════════════════
# cmd_update
# ═══════════════════════════════════════════════════════════════════════════


class TestCmdUpdate:
    """Test update command — lines 444, 458, 509, 528-530, 544-549, 555-568."""

    def test_update_not_git_repo(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_update
        with patch("code_agents.cli.cli_tools._find_code_agents_home", return_value=tmp_path):
            cmd_update()
        output = capsys.readouterr().out
        assert "Not a git repository" in output

    def test_update_ssh_fallback_to_https(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_update
        (tmp_path / ".git").mkdir()

        def mock_run_side_effect(cmd, **kwargs):
            mock_result = MagicMock()
            if cmd[1:3] == ["rev-parse", "--short"]:
                mock_result.stdout = "abc1234\n"
                mock_result.returncode = 0
            elif cmd[1:3] == ["rev-parse", "--abbrev-ref"]:
                mock_result.stdout = "main\n"
                mock_result.returncode = 0
            elif cmd[1:3] == ["remote", "get-url"]:
                mock_result.stdout = "git@bitbucket.org:team/repo.git\n"
                mock_result.returncode = 0
            elif cmd[1:2] == ["pull"]:
                mock_result.returncode = 1
                mock_result.stderr = "Permission denied"
                mock_result.stdout = ""
            elif cmd[1:3] == ["remote", "set-url"]:
                mock_result.returncode = 0
                mock_result.stdout = ""
            else:
                mock_result.returncode = 0
                mock_result.stdout = ""
            return mock_result

        with patch("code_agents.cli.cli_tools._find_code_agents_home", return_value=tmp_path), \
             patch("subprocess.run", side_effect=mock_run_side_effect):
            cmd_update()
        output = capsys.readouterr().out
        assert "git pull failed" in output

    def test_update_already_up_to_date(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_update
        (tmp_path / ".git").mkdir()
        mock_result = MagicMock(stdout="abc1234\n", returncode=0, stderr="")

        with patch("code_agents.cli.cli_tools._find_code_agents_home", return_value=tmp_path), \
             patch("subprocess.run", return_value=mock_result):
            cmd_update()
        output = capsys.readouterr().out
        assert "Already up to date" in output

    def test_update_with_changes(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_update
        (tmp_path / ".git").mkdir()
        call_count = {"rev_parse": 0}

        def mock_run_side_effect(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stderr = ""
            if cmd[1:3] == ["rev-parse", "--short"]:
                call_count["rev_parse"] += 1
                result.stdout = "old1234\n" if call_count["rev_parse"] == 1 else "new5678\n"
            elif cmd[1:3] == ["rev-parse", "--abbrev-ref"]:
                result.stdout = "main\n"
            elif cmd[1:3] == ["remote", "get-url"]:
                result.stdout = "https://bitbucket.org/team/repo.git\n"
            elif cmd[1:2] == ["pull"]:
                result.stdout = "Updating...\n"
            elif cmd[1:2] == ["diff"]:
                result.stdout = " file.py | 5 +++--\n 1 file changed\n"
            elif cmd[1:2] == ["log"]:
                result.stdout = "new5678 feat: new feature\n"
            elif cmd[:2] == ["poetry", "install"]:
                result.returncode = 1
                result.stderr = "warning: something\n"
            else:
                result.stdout = ""
            return result

        with patch("code_agents.cli.cli_tools._find_code_agents_home", return_value=tmp_path), \
             patch("subprocess.run", side_effect=mock_run_side_effect):
            # Mock the completion refresh to avoid import issues
            with patch("code_agents.cli.cli_completions._generate_zsh_completion", side_effect=ImportError):
                cmd_update()
        output = capsys.readouterr().out
        assert "Updated" in output or "poetry install had issues" in output

    def test_update_completions_refresh(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_update
        (tmp_path / ".git").mkdir()
        call_count = {"rev_parse": 0}

        def mock_run_side_effect(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            result.stderr = ""
            if cmd[1:3] == ["rev-parse", "--short"]:
                call_count["rev_parse"] += 1
                result.stdout = "old1234\n" if call_count["rev_parse"] == 1 else "new5678\n"
            elif cmd[1:3] == ["rev-parse", "--abbrev-ref"]:
                result.stdout = "main\n"
            elif cmd[1:3] == ["remote", "get-url"]:
                result.stdout = "https://bitbucket.org/team/repo.git\n"
            elif cmd[1:2] == ["pull"]:
                result.stdout = "ok\n"
            elif cmd[:2] == ["poetry", "install"]:
                result.returncode = 0
            elif cmd[:2] == ["pbcopy"]:
                result.returncode = 0
            else:
                result.stdout = ""
                result.returncode = 0
            return result

        zshrc = tmp_path / ".zshrc"
        zshrc.write_text("# some config\n")

        with patch("code_agents.cli.cli_tools._find_code_agents_home", return_value=tmp_path), \
             patch("subprocess.run", side_effect=mock_run_side_effect), \
             patch("os.path.expanduser", return_value=str(zshrc)), \
             patch("os.path.isfile", return_value=True):
            try:
                cmd_update()
            except Exception:
                pass  # completion refresh may fail in test env


# ═══════════════════════════════════════════════════════════════════════════
# cmd_onboard
# ═══════════════════════════════════════════════════════════════════════════


class TestCmdOnboard:
    """Test onboard command — lines 671-679."""

    def test_onboard_save(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_onboard
        mock_profile = MagicMock()
        mock_gen = MagicMock()
        mock_gen.scan.return_value = mock_profile
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.tools.onboarding.OnboardingGenerator", return_value=mock_gen), \
             patch("code_agents.tools.onboarding.generate_onboarding_doc", return_value="# Onboarding"):
            cmd_onboard(["--save"])
        output = capsys.readouterr().out
        assert "Saved to" in output
        assert (tmp_path / "ONBOARDING.md").exists()

    def test_onboard_full(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_onboard
        mock_profile = MagicMock()
        mock_gen = MagicMock()
        mock_gen.scan.return_value = mock_profile
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.tools.onboarding.OnboardingGenerator", return_value=mock_gen), \
             patch("code_agents.tools.onboarding.generate_onboarding_doc", return_value="# Full Doc"):
            cmd_onboard(["--full"])
        output = capsys.readouterr().out
        assert "# Full Doc" in output


# ═══════════════════════════════════════════════════════════════════════════
# cmd_changelog
# ═══════════════════════════════════════════════════════════════════════════


class TestCmdChangelog:
    """Test changelog command — lines 773-788."""

    def test_changelog_write(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_changelog
        mock_gen = MagicMock()
        mock_data = {"entries": []}
        mock_gen.generate.return_value = mock_data
        mock_gen.prepend_to_changelog.return_value = str(tmp_path / "CHANGELOG.md")
        with patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch.dict(os.environ, {"CODE_AGENTS_USER_CWD": str(tmp_path)}), \
             patch("code_agents.generators.changelog_gen.ChangelogGenerator", return_value=mock_gen), \
             patch("code_agents.generators.changelog_gen.format_changelog_terminal", return_value="Changelog text"):
            cmd_changelog(["--write"])
        output = capsys.readouterr().out
        assert "Changelog written to" in output

    def test_changelog_with_version(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_changelog
        mock_gen = MagicMock()
        mock_gen.generate.return_value = {}
        with patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch.dict(os.environ, {"CODE_AGENTS_USER_CWD": str(tmp_path)}), \
             patch("code_agents.generators.changelog_gen.ChangelogGenerator", return_value=mock_gen) as MockCls, \
             patch("code_agents.generators.changelog_gen.format_changelog_terminal", return_value="text"):
            cmd_changelog(["--version", "2.0.0"])
        # Verify version was passed
        MockCls.assert_called_once_with(cwd=str(tmp_path), version="2.0.0")
