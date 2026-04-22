"""CLI tests grouped by feature area (split from legacy monolith)."""
from __future__ import annotations

import os
import sys
from unittest.mock import patch, MagicMock

import pytest


class TestCmdConfig:
    """Test config command."""

    def test_config_no_env_file(self, capsys, tmp_path, monkeypatch):
        """Should warn when no .env exists."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("CODE_AGENTS_USER_CWD", str(tmp_path))
        from code_agents.cli import cmd_config
        cmd_config()
        output = capsys.readouterr().out
        assert "not found" in output

    def test_config_with_env_file(self, capsys, tmp_path, monkeypatch):
        """Should show config when .env exists."""
        env_file = tmp_path / ".env"
        env_file.write_text("HOST=0.0.0.0\nPORT=8000\nCURSOR_API_KEY=crsr_abc123xyz789\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("CODE_AGENTS_USER_CWD", str(tmp_path))
        from code_agents.cli import cmd_config
        cmd_config()
        output = capsys.readouterr().out
        assert "Configuration" in output
        assert "HOST" in output
        # Secret should be masked
        assert "crsr_abc123xyz789" not in output
class TestCmdCurls:
    """Test curls command."""

    def test_curls_no_args_shows_index(self, capsys):
        from code_agents.cli import cmd_curls
        cmd_curls([])
        output = capsys.readouterr().out
        assert "Filter by category" in output
        assert "health" in output
        assert "jenkins" in output
        assert "argocd" in output

    def test_curls_health_filter(self, capsys):
        from code_agents.cli import cmd_curls
        cmd_curls(["health"])
        output = capsys.readouterr().out
        assert "/health" in output
        assert "/diagnostics" in output
        assert "Jenkins" not in output  # should be filtered out

    def test_curls_jenkins_filter(self, capsys):
        from code_agents.cli import cmd_curls
        cmd_curls(["jenkins"])
        output = capsys.readouterr().out
        assert "jenkins/build" in output
        assert "Showing: jenkins" in output

    def test_curls_agent_specific(self, capsys):
        from code_agents.cli import cmd_curls
        cmd_curls(["code-reasoning"])
        output = capsys.readouterr().out
        assert "code-reasoning" in output
        assert "chat/completions" in output
        assert "Example prompts" in output

    def test_curls_unknown_agent(self, capsys):
        from code_agents.cli import cmd_curls
        cmd_curls(["nonexistent-agent"])
        output = capsys.readouterr().out
        assert "not found" in output
class TestCurlsForAgentExamples:
    """Test _curls_for_agent with agents that have example prompts."""

    def test_curls_for_known_agent_with_examples(self, capsys):
        from code_agents.cli.cli_curls import _curls_for_agent
        mock_agent = MagicMock()
        mock_agent.name = "code-writer"
        mock_agent.display_name = "Code Writer Agent"
        mock_agent.backend = "cursor"
        mock_agent.model = "gpt-4"
        mock_agent.permission_mode = "suggest"
        with patch("code_agents.core.config.agent_loader") as mock_loader:
            mock_loader.load.return_value = None
            mock_loader.get.return_value = mock_agent
            _curls_for_agent("code-writer", "http://127.0.0.1:8000")
        output = capsys.readouterr().out
        assert "Code Writer Agent" in output
        assert "chat/completions" in output
        assert "Write a function" in output or "Example prompts" in output

    def test_curls_all_sections(self, capsys):
        from code_agents.cli.cli_curls import _print_curl_sections
        _print_curl_sections("http://127.0.0.1:8000", None)
        output = capsys.readouterr().out
        assert "Health" in output
        assert "Agents" in output
        assert "Git" in output
        assert "Testing" in output
        assert "Jenkins" in output
        assert "ArgoCD" in output
        assert "Pipeline" in output
        assert "Redash" in output
        assert "Elasticsearch" in output
