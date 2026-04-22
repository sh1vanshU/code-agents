"""CLI tests grouped by feature area (split from legacy monolith)."""
from __future__ import annotations

import os
import sys
from unittest.mock import patch, MagicMock

import pytest


class TestCmdRules:
    """Test rules management command."""

    def test_rules_list_empty(self, capsys):
        from code_agents.cli.cli_tools import cmd_rules
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp/fake"), \
             patch("code_agents.agent_system.rules_loader.list_rules", return_value=[]):
            cmd_rules(["list"])
        output = capsys.readouterr().out
        assert "No rules found" in output

    def test_rules_list_with_rules(self, capsys):
        from code_agents.cli.cli_tools import cmd_rules
        rules = [
            {"scope": "global", "target": "_global", "preview": "Do X", "path": "/tmp/rules/_global.md"},
            {"scope": "project", "target": "code-writer", "preview": "Write Y", "path": "/tmp/rules/code-writer.md"},
        ]
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp/fake"), \
             patch("code_agents.agent_system.rules_loader.list_rules", return_value=rules):
            cmd_rules(["list"])
        output = capsys.readouterr().out
        assert "Active Rules" in output
        assert "all agents" in output
        assert "code-writer" in output

    def test_rules_list_default(self, capsys):
        from code_agents.cli.cli_tools import cmd_rules
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp/fake"), \
             patch("code_agents.agent_system.rules_loader.list_rules", return_value=[]):
            cmd_rules([])  # default is 'list'
        output = capsys.readouterr().out
        assert "No rules found" in output

    def test_rules_create(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_rules
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch("subprocess.run") as mock_sp:
            cmd_rules(["create"])
        output = capsys.readouterr().out
        assert "Created" in output or "File exists" in output

    def test_rules_create_global_agent(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_rules
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.agent_system.rules_loader.GLOBAL_RULES_DIR", tmp_path / "global_rules"), \
             patch("subprocess.run") as mock_sp:
            cmd_rules(["create", "--global", "--agent", "code-writer"])
        output = capsys.readouterr().out
        assert "Created" in output or "File exists" in output

    def test_rules_edit_missing_path(self, capsys):
        from code_agents.cli.cli_tools import cmd_rules
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp/fake"):
            cmd_rules(["edit"])
        output = capsys.readouterr().out
        assert "Usage" in output

    def test_rules_edit_file_not_found(self, capsys):
        from code_agents.cli.cli_tools import cmd_rules
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp/fake"):
            cmd_rules(["edit", "/nonexistent/path.md"])
        output = capsys.readouterr().out
        assert "File not found" in output

    def test_rules_delete_missing_arg(self, capsys):
        from code_agents.cli.cli_tools import cmd_rules
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp/fake"):
            cmd_rules(["delete"])
        output = capsys.readouterr().out
        assert "Usage" in output

    def test_rules_delete_file_not_found(self, capsys):
        from code_agents.cli.cli_tools import cmd_rules
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp/fake"):
            cmd_rules(["delete", "/nonexistent/path.md"])
        output = capsys.readouterr().out
        assert "File not found" in output

    def test_rules_delete_confirmed(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_rules
        rule_file = tmp_path / "test_rule.md"
        rule_file.write_text("# test rule")
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch("builtins.input", return_value="y"):
            cmd_rules(["delete", str(rule_file)])
        output = capsys.readouterr().out
        assert "Deleted" in output
        assert not rule_file.exists()

    def test_rules_delete_cancelled(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_rules
        rule_file = tmp_path / "test_rule.md"
        rule_file.write_text("# test rule")
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)), \
             patch("builtins.input", return_value="n"):
            cmd_rules(["delete", str(rule_file)])
        output = capsys.readouterr().out
        assert "Cancelled" in output
        assert rule_file.exists()

    def test_rules_unknown_subcommand(self, capsys):
        from code_agents.cli.cli_tools import cmd_rules
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp/fake"):
            cmd_rules(["foobar"])
        output = capsys.readouterr().out
        assert "Unknown subcommand" in output
class TestCmdMigrate:
    """Test migrate command."""

    def test_migrate_no_legacy_env(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_migrate
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)):
            cmd_migrate()
        output = capsys.readouterr().out
        assert "nothing to migrate" in output

    def test_migrate_empty_legacy_env(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_migrate
        env_file = tmp_path / ".env"
        env_file.write_text("")
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)):
            cmd_migrate()
        output = capsys.readouterr().out
        assert "empty" in output or "nothing to migrate" in output
class TestCmdRepos:
    """Test repos management command."""

    def test_repos_list(self, capsys):
        from code_agents.cli.cli_tools import cmd_repos
        mock_ctx = MagicMock()
        mock_ctx.name = "my-project"
        mock_ctx.path = "/tmp/my-project"
        mock_ctx.git_branch = "main"
        mock_rm = MagicMock()
        mock_rm.repos = {"my-project": mock_ctx}
        mock_rm.list_repos.return_value = [mock_ctx]
        mock_rm.active_repo = "/tmp/my-project"
        with patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp/my-project"), \
             patch("code_agents.domain.repo_manager.get_repo_manager", return_value=mock_rm):
            cmd_repos([])
        output = capsys.readouterr().out
        assert "my-project" in output
        assert "Registered repos" in output

    def test_repos_add_no_path(self, capsys):
        from code_agents.cli.cli_tools import cmd_repos
        mock_rm = MagicMock()
        mock_rm.repos = {"x": True}
        with patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp"), \
             patch("code_agents.domain.repo_manager.get_repo_manager", return_value=mock_rm):
            cmd_repos(["add"])
        output = capsys.readouterr().out
        assert "Usage" in output

    def test_repos_add_success(self, capsys):
        from code_agents.cli.cli_tools import cmd_repos
        mock_ctx = MagicMock()
        mock_ctx.name = "new-repo"
        mock_ctx.path = "/tmp/new-repo"
        mock_ctx.git_branch = "main"
        mock_rm = MagicMock()
        mock_rm.repos = {"x": True}
        mock_rm.add_repo.return_value = mock_ctx
        with patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp"), \
             patch("code_agents.domain.repo_manager.get_repo_manager", return_value=mock_rm):
            cmd_repos(["add", "/tmp/new-repo"])
        output = capsys.readouterr().out
        assert "Registered" in output
        assert "new-repo" in output

    def test_repos_add_error(self, capsys):
        from code_agents.cli.cli_tools import cmd_repos
        mock_rm = MagicMock()
        mock_rm.repos = {"x": True}
        mock_rm.add_repo.side_effect = ValueError("already registered")
        with patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp"), \
             patch("code_agents.domain.repo_manager.get_repo_manager", return_value=mock_rm):
            cmd_repos(["add", "/tmp/new-repo"])
        output = capsys.readouterr().out
        assert "already registered" in output

    def test_repos_remove_no_name(self, capsys):
        from code_agents.cli.cli_tools import cmd_repos
        mock_rm = MagicMock()
        mock_rm.repos = {"x": True}
        with patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp"), \
             patch("code_agents.domain.repo_manager.get_repo_manager", return_value=mock_rm):
            cmd_repos(["remove"])
        output = capsys.readouterr().out
        assert "Usage" in output

    def test_repos_remove_success(self, capsys):
        from code_agents.cli.cli_tools import cmd_repos
        mock_rm = MagicMock()
        mock_rm.repos = {"x": True}
        mock_rm.remove_repo.return_value = True
        with patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp"), \
             patch("code_agents.domain.repo_manager.get_repo_manager", return_value=mock_rm):
            cmd_repos(["remove", "my-repo"])
        output = capsys.readouterr().out
        assert "Removed" in output

    def test_repos_remove_not_found(self, capsys):
        from code_agents.cli.cli_tools import cmd_repos
        mock_rm = MagicMock()
        mock_rm.repos = {"x": True}
        mock_rm.remove_repo.return_value = False
        with patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp"), \
             patch("code_agents.domain.repo_manager.get_repo_manager", return_value=mock_rm):
            cmd_repos(["remove", "nonexistent"])
        output = capsys.readouterr().out
        assert "not found" in output

    def test_repos_empty_list(self, capsys):
        from code_agents.cli.cli_tools import cmd_repos
        mock_rm = MagicMock()
        mock_rm.repos = {}
        mock_rm.add_repo.side_effect = ValueError("not a git repo")
        mock_rm.list_repos.return_value = []
        with patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp"), \
             patch("code_agents.domain.repo_manager.get_repo_manager", return_value=mock_rm):
            cmd_repos([])
        output = capsys.readouterr().out
        assert "No repos registered" in output
