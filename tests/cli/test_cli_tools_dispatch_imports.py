"""CLI tests grouped by feature area (split from legacy monolith)."""
from __future__ import annotations

import os
import sys
from unittest.mock import patch, MagicMock

import pytest


class TestCmdVersion:
    """Test version command."""

    def test_version_shows_info(self, capsys):
        from code_agents.cli.cli_tools import cmd_version
        cmd_version()
        output = capsys.readouterr().out
        assert "code-agents" in output
        assert "Python" in output
        assert "Install:" in output

# ── cli_tools module via main() / dispatch paths ──

class TestCmdVersionBump:
    """Test version-bump command."""

    def test_no_args_shows_usage(self, capsys):
        from code_agents.cli.cli_tools import cmd_version_bump
        cmd_version_bump([])
        output = capsys.readouterr().out
        assert "Usage:" in output
        assert "major" in output
        assert "minor" in output
        assert "patch" in output

    def test_invalid_arg_shows_usage(self, capsys):
        from code_agents.cli.cli_tools import cmd_version_bump
        cmd_version_bump(["foo"])
        output = capsys.readouterr().out
        assert "Usage:" in output

# ── cli_tools module via main() / dispatch paths ──

class TestCmdRules:
    """Test rules management command."""

    def test_rules_list_empty(self, capsys):
        from code_agents.cli.cli_tools import cmd_rules
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp"), \
             patch("code_agents.agent_system.rules_loader.list_rules", return_value=[]):
            cmd_rules(["list"])
        output = capsys.readouterr().out
        assert "No rules found" in output

    def test_rules_list_with_rules(self, capsys):
        from code_agents.cli.cli_tools import cmd_rules
        rules = [
            {"scope": "global", "target": "_global", "preview": "Rule 1 preview", "path": "/path/to/rule"},
            {"scope": "project", "target": "code-writer", "preview": "Rule 2", "path": "/path2"},
        ]
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp"), \
             patch("code_agents.agent_system.rules_loader.list_rules", return_value=rules):
            cmd_rules(["list"])
        output = capsys.readouterr().out
        assert "Active Rules" in output
        assert "all agents" in output
        assert "code-writer" in output

    def test_rules_default_subcommand_is_list(self, capsys):
        from code_agents.cli.cli_tools import cmd_rules
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp"), \
             patch("code_agents.agent_system.rules_loader.list_rules", return_value=[]):
            cmd_rules([])
        output = capsys.readouterr().out
        assert "No rules found" in output

    def test_rules_edit_no_path(self, capsys):
        from code_agents.cli.cli_tools import cmd_rules
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp"):
            cmd_rules(["edit"])
        output = capsys.readouterr().out
        assert "Usage:" in output

    def test_rules_edit_file_not_found(self, capsys):
        from code_agents.cli.cli_tools import cmd_rules
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp"):
            cmd_rules(["edit", "/nonexistent/file.md"])
        output = capsys.readouterr().out
        assert "not found" in output

    def test_rules_delete_no_path(self, capsys):
        from code_agents.cli.cli_tools import cmd_rules
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp"):
            cmd_rules(["delete"])
        output = capsys.readouterr().out
        assert "Usage:" in output

    def test_rules_delete_file_not_found(self, capsys):
        from code_agents.cli.cli_tools import cmd_rules
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp"):
            cmd_rules(["delete", "/nonexistent/file.md"])
        output = capsys.readouterr().out
        assert "not found" in output

    def test_rules_unknown_subcommand(self, capsys):
        from code_agents.cli.cli_tools import cmd_rules
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp"):
            cmd_rules(["foobar"])
        output = capsys.readouterr().out
        assert "Unknown subcommand" in output

# ── cli_tools module via main() / dispatch paths ──

class TestCmdMigrate:
    """Test migrate command."""

    def test_migrate_no_legacy_env(self, capsys):
        from code_agents.cli.cli_tools import cmd_migrate
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp"):
            cmd_migrate()
        output = capsys.readouterr().out
        assert "No legacy .env" in output

    def test_migrate_empty_env(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_migrate
        env_file = tmp_path / ".env"
        env_file.write_text("")
        with patch("code_agents.cli.cli_tools._load_env"), \
             patch("code_agents.cli.cli_tools._user_cwd", return_value=str(tmp_path)):
            cmd_migrate()
        output = capsys.readouterr().out
        assert "empty" in output

# ── cli_tools module via main() / dispatch paths ──

class TestCmdRepos:
    """Test repos command."""

    def test_repos_list_empty(self, capsys):
        from code_agents.cli.cli_tools import cmd_repos
        mock_rm = MagicMock()
        mock_rm.repos = {}
        mock_rm.list_repos.return_value = []
        mock_rm.active_repo = None
        with patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp"), \
             patch("code_agents.domain.repo_manager.get_repo_manager", return_value=mock_rm):
            cmd_repos([])
        output = capsys.readouterr().out
        assert "No repos registered" in output

    def test_repos_add_no_path(self, capsys):
        from code_agents.cli.cli_tools import cmd_repos
        mock_rm = MagicMock()
        mock_rm.repos = {"repo": True}
        with patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp"), \
             patch("code_agents.domain.repo_manager.get_repo_manager", return_value=mock_rm):
            cmd_repos(["add"])
        output = capsys.readouterr().out
        assert "Usage:" in output

    def test_repos_remove_no_name(self, capsys):
        from code_agents.cli.cli_tools import cmd_repos
        mock_rm = MagicMock()
        mock_rm.repos = {"repo": True}
        with patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp"), \
             patch("code_agents.domain.repo_manager.get_repo_manager", return_value=mock_rm):
            cmd_repos(["remove"])
        output = capsys.readouterr().out
        assert "Usage:" in output

    def test_repos_remove_not_found(self, capsys):
        from code_agents.cli.cli_tools import cmd_repos
        mock_rm = MagicMock()
        mock_rm.repos = {"repo": True}
        mock_rm.remove_repo.return_value = False
        with patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp"), \
             patch("code_agents.domain.repo_manager.get_repo_manager", return_value=mock_rm):
            cmd_repos(["remove", "nonexistent"])
        output = capsys.readouterr().out
        assert "not found" in output
