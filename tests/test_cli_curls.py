"""Tests for cli_curls.py — curl command generation."""

from __future__ import annotations

import os
from unittest.mock import patch, MagicMock

import pytest


class TestCmdCurls:
    """Test cmd_curls command."""

    def test_curls_no_args_shows_index(self, capsys):
        from code_agents.cli.cli_curls import cmd_curls
        with patch("code_agents.cli.cli_curls._load_env"), \
             patch("code_agents.cli.cli_curls._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.core.config.agent_loader") as mock_loader:
            mock_loader.load.return_value = None
            mock_loader.list_agents.return_value = []
            cmd_curls([])
        output = capsys.readouterr().out
        assert "API Curl Reference" in output
        assert "health" in output
        assert "agents" in output
        assert "git" in output
        assert "testing" in output
        assert "jenkins" in output
        assert "argocd" in output
        assert "pipeline" in output

    def test_curls_health_filter(self, capsys):
        from code_agents.cli.cli_curls import cmd_curls
        with patch("code_agents.cli.cli_curls._load_env"), \
             patch("code_agents.cli.cli_curls._server_url", return_value="http://127.0.0.1:8000"):
            cmd_curls(["health"])
        output = capsys.readouterr().out
        assert "Health & Diagnostics" in output
        assert "/health" in output
        assert "/diagnostics" in output
        # Should NOT contain other sections
        assert "Jenkins CI/CD" not in output

    def test_curls_agents_filter(self, capsys):
        from code_agents.cli.cli_curls import cmd_curls
        with patch("code_agents.cli.cli_curls._load_env"), \
             patch("code_agents.cli.cli_curls._server_url", return_value="http://127.0.0.1:8000"):
            cmd_curls(["agents"])
        output = capsys.readouterr().out
        assert "Agents" in output
        assert "/v1/agents" in output
        assert "streaming" in output.lower() or "stream" in output.lower()

    def test_curls_git_filter(self, capsys):
        from code_agents.cli.cli_curls import cmd_curls
        with patch("code_agents.cli.cli_curls._load_env"), \
             patch("code_agents.cli.cli_curls._server_url", return_value="http://127.0.0.1:8000"):
            cmd_curls(["git"])
        output = capsys.readouterr().out
        assert "Git Operations" in output
        assert "/git/branches" in output
        assert "/git/diff" in output

    def test_curls_testing_filter(self, capsys):
        from code_agents.cli.cli_curls import cmd_curls
        with patch("code_agents.cli.cli_curls._load_env"), \
             patch("code_agents.cli.cli_curls._server_url", return_value="http://127.0.0.1:8000"):
            cmd_curls(["testing"])
        output = capsys.readouterr().out
        assert "Testing & Coverage" in output
        assert "/testing/run" in output

    def test_curls_jenkins_filter(self, capsys):
        from code_agents.cli.cli_curls import cmd_curls
        with patch("code_agents.cli.cli_curls._load_env"), \
             patch("code_agents.cli.cli_curls._server_url", return_value="http://127.0.0.1:8000"):
            cmd_curls(["jenkins"])
        output = capsys.readouterr().out
        assert "Jenkins CI/CD" in output
        assert "/jenkins/build" in output

    def test_curls_argocd_filter(self, capsys):
        from code_agents.cli.cli_curls import cmd_curls
        with patch("code_agents.cli.cli_curls._load_env"), \
             patch("code_agents.cli.cli_curls._server_url", return_value="http://127.0.0.1:8000"):
            cmd_curls(["argocd"])
        output = capsys.readouterr().out
        assert "ArgoCD" in output
        assert "/argocd/apps" in output

    def test_curls_pipeline_filter(self, capsys):
        from code_agents.cli.cli_curls import cmd_curls
        with patch("code_agents.cli.cli_curls._load_env"), \
             patch("code_agents.cli.cli_curls._server_url", return_value="http://127.0.0.1:8000"):
            cmd_curls(["pipeline"])
        output = capsys.readouterr().out
        assert "CI/CD Pipeline" in output
        assert "/pipeline/start" in output

    def test_curls_redash_filter(self, capsys):
        from code_agents.cli.cli_curls import cmd_curls
        with patch("code_agents.cli.cli_curls._load_env"), \
             patch("code_agents.cli.cli_curls._server_url", return_value="http://127.0.0.1:8000"):
            cmd_curls(["redash"])
        output = capsys.readouterr().out
        assert "Redash" in output
        assert "/redash/" in output

    def test_curls_elasticsearch_filter(self, capsys):
        from code_agents.cli.cli_curls import cmd_curls
        with patch("code_agents.cli.cli_curls._load_env"), \
             patch("code_agents.cli.cli_curls._server_url", return_value="http://127.0.0.1:8000"):
            cmd_curls(["elasticsearch"])
        output = capsys.readouterr().out
        assert "Elasticsearch" in output
        assert "/elasticsearch/" in output


class TestCurlsForAgent:
    """Test _curls_for_agent for agent-specific curls."""

    def test_agent_found(self, capsys):
        from code_agents.cli.cli_curls import _curls_for_agent

        mock_agent = MagicMock()
        mock_agent.name = "code-reviewer"
        mock_agent.display_name = "Code Reviewer"
        mock_agent.backend = "cursor"
        mock_agent.model = "gpt-4"
        mock_agent.permission_mode = "default"

        with patch("code_agents.core.config.agent_loader") as mock_loader:
            mock_loader.load.return_value = None
            mock_loader.get.return_value = mock_agent
            _curls_for_agent("code-reviewer", "http://127.0.0.1:8000")

        output = capsys.readouterr().out
        assert "Code Reviewer" in output
        assert "code-reviewer" in output
        assert "/v1/agents/code-reviewer/chat/completions" in output
        assert "non-streaming" in output.lower() or "Non" in output
        assert "streaming" in output.lower()
        assert "session" in output.lower() or "SESSION_ID" in output

    def test_agent_not_found(self, capsys):
        from code_agents.cli.cli_curls import _curls_for_agent

        with patch("code_agents.core.config.agent_loader") as mock_loader:
            mock_loader.load.return_value = None
            mock_loader.get.return_value = None
            mock_loader.list_agents.return_value = []
            _curls_for_agent("nonexistent", "http://127.0.0.1:8000")

        output = capsys.readouterr().out
        assert "not found" in output

    def test_agent_with_examples(self, capsys):
        from code_agents.cli.cli_curls import _curls_for_agent

        mock_agent = MagicMock()
        mock_agent.name = "code-reasoning"
        mock_agent.display_name = "Code Reasoning"
        mock_agent.backend = "cursor"
        mock_agent.model = "gpt-4"
        mock_agent.permission_mode = "default"

        with patch("code_agents.core.config.agent_loader") as mock_loader:
            mock_loader.load.return_value = None
            mock_loader.get.return_value = mock_agent
            _curls_for_agent("code-reasoning", "http://127.0.0.1:8000")

        output = capsys.readouterr().out
        assert "Example prompts" in output
        assert "Explain the architecture" in output

    def test_curls_unknown_agent_name_routes_to_agent(self, capsys):
        """Unknown name (not in categories) should call _curls_for_agent."""
        from code_agents.cli.cli_curls import cmd_curls

        with patch("code_agents.cli.cli_curls._load_env"), \
             patch("code_agents.cli.cli_curls._server_url", return_value="http://127.0.0.1:8000"), \
             patch("code_agents.cli.cli_curls._curls_for_agent") as mock_agent_curls:
            cmd_curls(["my-custom-agent"])

        mock_agent_curls.assert_called_once_with("my-custom-agent", "http://127.0.0.1:8000")


class TestPrintCurlSections:
    """Test _print_curl_sections helper."""

    def test_all_sections_no_filter(self, capsys):
        from code_agents.cli.cli_curls import _print_curl_sections
        _print_curl_sections("http://localhost:8000", None)
        output = capsys.readouterr().out
        # All sections should be present
        assert "Health" in output
        assert "Agents" in output
        assert "Git" in output
        assert "Testing" in output
        assert "Jenkins" in output
        assert "ArgoCD" in output
        assert "Pipeline" in output
        assert "Redash" in output
        assert "Elasticsearch" in output

    def test_filter_shows_only_one_section(self, capsys):
        from code_agents.cli.cli_curls import _print_curl_sections
        _print_curl_sections("http://localhost:8000", "health")
        output = capsys.readouterr().out
        assert "Health" in output
        assert "Jenkins CI/CD" not in output

    def test_url_is_embedded(self, capsys):
        from code_agents.cli.cli_curls import _print_curl_sections
        _print_curl_sections("http://myserver:9999", "health")
        output = capsys.readouterr().out
        assert "http://myserver:9999" in output
