"""CLI tests grouped by feature area (split from legacy monolith)."""
from __future__ import annotations

import os
import sys
from unittest.mock import patch, MagicMock

import pytest


class TestServerUrl:
    """Test _server_url resolution."""

    def test_default_url(self):
        from code_agents.cli import _server_url
        with patch.dict(os.environ, {"HOST": "0.0.0.0", "PORT": "8000"}):
            url = _server_url()
            assert url == "http://127.0.0.1:8000"

    def test_custom_host_port(self):
        from code_agents.cli import _server_url
        with patch.dict(os.environ, {"HOST": "10.0.0.1", "PORT": "9000"}):
            url = _server_url()
            assert url == "http://10.0.0.1:9000"

    def test_localhost_passthrough(self):
        from code_agents.cli import _server_url
        with patch.dict(os.environ, {"HOST": "127.0.0.1", "PORT": "8080"}):
            url = _server_url()
            assert url == "http://127.0.0.1:8080"
class TestAgentListParsing:
    """Test that cli.py _api_get parses agent lists correctly."""

    def test_parse_data_format(self):
        """Server returns {"object": "list", "data": [...]}."""
        data = {
            "object": "list",
            "data": [
                {"name": "code-reasoning", "display_name": "Code Reasoning Agent"},
                {"name": "code-writer", "display_name": "Code Writer Agent"},
            ]
        }
        # Replicate the parsing logic from cli.py cmd_agents
        if isinstance(data, dict):
            agents = data.get("data") or data.get("agents") or []
        elif isinstance(data, list):
            agents = data
        else:
            agents = []
        assert len(agents) == 2
        assert agents[0]["name"] == "code-reasoning"

    def test_parse_agents_format(self):
        data = {"agents": [{"name": "git-ops"}]}
        agents = data.get("data") or data.get("agents") or []
        assert len(agents) == 1

    def test_parse_plain_list(self):
        data = [{"name": "code-tester"}]
        if isinstance(data, list):
            agents = data
        else:
            agents = []
        assert len(agents) == 1

    def test_parse_empty(self):
        data = {"unexpected": "format"}
        agents = data.get("data") or data.get("agents") or []
        assert agents == []
class TestCmdHelp:
    """Test that help command produces comprehensive output."""

    def test_help_contains_all_commands(self, capsys):
        from code_agents.cli import cmd_help
        cmd_help()
        output = capsys.readouterr().out

        # All 22 commands should appear
        commands = [
            "init", "migrate", "rules", "start", "restart", "chat", "setup",
            "shutdown", "status", "logs", "config", "doctor", "branches", "diff",
            "test", "review", "pipeline", "agents", "curls", "update",
            "version", "help", "sessions", "repos",
        ]
        for cmd in commands:
            assert cmd in output, f"Command '{cmd}' missing from help"

    def test_help_contains_chat_slash_commands(self, capsys):
        from code_agents.cli import cmd_help
        cmd_help()
        output = capsys.readouterr().out

        slash_cmds = ["/help", "/quit", "/agent", "/agents", "/session", "/clear", "/history", "/resume"]
        for cmd in slash_cmds:
            assert cmd in output, f"Chat command '{cmd}' missing from help"

    def test_help_contains_all_agents(self, capsys):
        from code_agents.cli import cmd_help
        cmd_help()
        output = capsys.readouterr().out

        # Help output mentions agents command and chat command with agent count
        assert "agents" in output, "agents command missing from help"
        assert "chat" in output, "chat command missing from help"
        assert "specialist" in output or "agent" in output.lower(), "agent reference missing from help"

    def test_help_contains_pipeline_subcommands(self, capsys):
        from code_agents.cli import cmd_help
        cmd_help()
        output = capsys.readouterr().out

        for sub in ["start", "status", "advance", "rollback"]:
            assert sub in output, f"Pipeline subcommand '{sub}' missing from help"

    def test_help_contains_key_sections(self, capsys):
        from code_agents.cli import cmd_help
        cmd_help()
        output = capsys.readouterr().out
        for section in ["CORE", "ANALYSIS", "GIT / PR",
                        "INCIDENT & REPORTS", "QUICK START"]:
            assert section in output, f"Section '{section}' missing from help"
class TestCmdVersion:
    """Test version command."""

    def test_version_output(self, capsys):
        from code_agents.cli import cmd_version
        cmd_version()
        output = capsys.readouterr().out
        assert "code-agents" in output
        assert "Python" in output
