"""Tests for code_agents.cli.cli_skill — CLI skill marketplace command."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest


class TestSkillList:
    """Tests for _skill_list function."""

    @patch("code_agents.agent_system.skill_marketplace.list_installed", return_value={})
    def test_list_empty(self, mock_list, capsys):
        from code_agents.cli.cli_skill import _skill_list
        _skill_list()
        out = capsys.readouterr().out
        assert "no" in out.lower() or "No" in out

    @patch("code_agents.agent_system.skill_marketplace.list_installed")
    def test_list_with_skills(self, mock_list, capsys):
        mock_list.return_value = {
            "_shared": [
                {"name": "debug-flow", "description": "Debug workflow", "path": "/tmp/skill.md", "size": 1024},
            ]
        }
        from code_agents.cli.cli_skill import _skill_list
        _skill_list()
        out = capsys.readouterr().out
        assert "debug-flow" in out


class TestSkillSearch:
    """Tests for _skill_search function."""

    @patch("code_agents.agent_system.skill_marketplace.search_registry", return_value=[])
    def test_search_no_results(self, mock_search, capsys):
        from code_agents.cli.cli_skill import _skill_search
        _skill_search("nonexistent")
        out = capsys.readouterr().out
        assert "no" in out.lower() or "No" in out

    @patch("code_agents.agent_system.skill_marketplace.search_registry")
    def test_search_with_results(self, mock_search, capsys):
        from code_agents.agent_system.skill_marketplace import SkillInfo
        mock_search.return_value = [
            SkillInfo(name="debug-flow", agent="_shared", description="Debug workflow", url="https://example.com/skill.md"),
        ]
        from code_agents.cli.cli_skill import _skill_search
        _skill_search("debug")
        out = capsys.readouterr().out
        assert "debug-flow" in out


class TestSkillInstall:
    """Tests for _skill_install function."""

    @patch("code_agents.agent_system.skill_marketplace.install_skill", return_value=(True, "Installed: _shared:my-skill"))
    def test_install_success(self, mock_install, capsys):
        from code_agents.cli.cli_skill import _skill_install
        _skill_install("https://example.com/my-skill.md", "_shared")
        out = capsys.readouterr().out
        assert "Installed" in out

    @patch("code_agents.agent_system.skill_marketplace.install_skill", return_value=(False, "Validation failed"))
    def test_install_failure(self, mock_install, capsys):
        from code_agents.cli.cli_skill import _skill_install
        _skill_install("https://example.com/bad-skill.md", "_shared")
        out = capsys.readouterr().out
        assert "Validation failed" in out


class TestSkillRemove:
    """Tests for _skill_remove function."""

    @patch("code_agents.agent_system.skill_marketplace.remove_skill", return_value=(True, "Removed: _shared:my-skill"))
    def test_remove_success(self, mock_remove, capsys):
        from code_agents.cli.cli_skill import _skill_remove
        _skill_remove("_shared:my-skill")
        out = capsys.readouterr().out
        assert "Removed" in out

    @patch("code_agents.agent_system.skill_marketplace.remove_skill", return_value=(False, "Skill not found"))
    def test_remove_not_found(self, mock_remove, capsys):
        from code_agents.cli.cli_skill import _skill_remove
        _skill_remove("_shared:nonexistent")
        out = capsys.readouterr().out
        assert "not found" in out

    def test_remove_no_colon(self, capsys):
        """Should warn about format when no colon in spec."""
        from code_agents.cli.cli_skill import _skill_remove
        _skill_remove("no-colon-here")
        out = capsys.readouterr().out
        assert "Format" in out or "agent" in out.lower()


class TestSkillInfo:
    """Tests for _skill_info function."""

    @patch("code_agents.agent_system.skill_marketplace.get_skill_info")
    def test_info_found(self, mock_info, capsys):
        mock_info.return_value = {
            "name": "debug-flow",
            "agent": "_shared",
            "description": "Debug workflow",
            "path": "/tmp/skill.md",
            "size": 1024,
            "content_preview": "---\nname: debug-flow\n---\nSome content",
        }
        from code_agents.cli.cli_skill import _skill_info
        _skill_info("_shared:debug-flow")
        out = capsys.readouterr().out
        assert "debug-flow" in out

    @patch("code_agents.agent_system.skill_marketplace.get_skill_info", return_value=None)
    def test_info_not_found(self, mock_info, capsys):
        from code_agents.cli.cli_skill import _skill_info
        _skill_info("_shared:nonexistent")
        out = capsys.readouterr().out
        assert "not found" in out.lower()

    def test_info_no_colon(self, capsys):
        """Should warn about format when no colon in spec."""
        from code_agents.cli.cli_skill import _skill_info
        _skill_info("no-colon-here")
        out = capsys.readouterr().out
        assert "Format" in out or "agent" in out.lower()


class TestCmdSkillEntryPoint:
    """Tests for the cmd_skill main entry point."""

    @patch("sys.argv", ["code-agents", "skill", "--help"])
    def test_help(self, capsys):
        from code_agents.cli.cli_skill import cmd_skill
        cmd_skill()
        out = capsys.readouterr().out
        assert "Usage" in out or "skill" in out

    @patch("sys.argv", ["code-agents", "skill", "unknown-cmd"])
    def test_unknown_subcmd(self, capsys):
        from code_agents.cli.cli_skill import cmd_skill
        cmd_skill()
        out = capsys.readouterr().out
        assert "Unknown" in out or "unknown" in out
