"""Tests for chat/chat_server.py — server communication, health check, workspace trust."""

from __future__ import annotations

import os
import shutil
from unittest.mock import patch, MagicMock

import pytest

from code_agents.chat.chat_server import (
    _server_url,
    _check_server,
    _check_workspace_trust,
    _get_agents,
    _stream_chat,
)


# ---------------------------------------------------------------------------
# _check_workspace_trust
# ---------------------------------------------------------------------------


class TestCheckWorkspaceTrust:
    """Lines 36-49: workspace trust check."""

    def test_returns_true_for_claude_cli_backend(self):
        """Line 37-38: claude-cli backend bypasses trust check."""
        with patch.dict(os.environ, {"CODE_AGENTS_BACKEND": "claude-cli"}, clear=False):
            assert _check_workspace_trust("/some/path") is True

    def test_returns_true_for_cursor_api_url(self):
        """Line 39-40: CURSOR_API_URL set bypasses trust check."""
        with patch.dict(os.environ, {
            "CODE_AGENTS_BACKEND": "",
            "CURSOR_API_URL": "http://localhost:8080",
            "ANTHROPIC_API_KEY": "",
        }, clear=False):
            assert _check_workspace_trust("/some/path") is True

    def test_returns_true_for_anthropic_api_key(self):
        """Line 41-42: ANTHROPIC_API_KEY set bypasses trust check."""
        with patch.dict(os.environ, {
            "CODE_AGENTS_BACKEND": "",
            "CURSOR_API_URL": "",
            "ANTHROPIC_API_KEY": "sk-ant-123",
        }, clear=False):
            assert _check_workspace_trust("/some/path") is True

    def test_warns_when_cursor_agent_not_found(self, capsys):
        """Lines 45-48: warns when cursor-agent binary is not found."""
        with patch.dict(os.environ, {
            "CODE_AGENTS_BACKEND": "",
            "CURSOR_API_URL": "",
            "ANTHROPIC_API_KEY": "",
        }, clear=False), \
             patch("shutil.which", return_value=None):
            result = _check_workspace_trust("/some/path")
        assert result is True
        captured = capsys.readouterr()
        assert "cursor-agent not found" in captured.out

    def test_no_warning_when_cursor_agent_found(self, capsys):
        """Line 45: cursor-agent found, no warning."""
        with patch.dict(os.environ, {
            "CODE_AGENTS_BACKEND": "",
            "CURSOR_API_URL": "",
            "ANTHROPIC_API_KEY": "",
        }, clear=False), \
             patch("shutil.which", return_value="/usr/bin/cursor-agent"):
            result = _check_workspace_trust("/some/path")
        assert result is True
        captured = capsys.readouterr()
        assert "cursor-agent not found" not in captured.out


# ---------------------------------------------------------------------------
# _get_agents
# ---------------------------------------------------------------------------


class TestGetAgents:
    """Line 63: _get_agents with non-dict/list data."""

    def test_get_agents_returns_empty_on_unexpected_data(self):
        """Line 63: non-dict, non-list response returns empty."""
        mock_response = MagicMock()
        mock_response.json.return_value = "unexpected string"

        with patch("httpx.get", return_value=mock_response):
            result = _get_agents("http://localhost:8000")
        assert result == {}

    def test_get_agents_dict_with_data_key(self):
        """Lines 59: dict response with 'data' key."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [{"name": "agent1", "display_name": "Agent 1"}]
        }

        with patch("httpx.get", return_value=mock_response):
            result = _get_agents("http://localhost:8000")
        assert result == {"agent1": "Agent 1"}

    def test_get_agents_list_response(self):
        """Line 61: list response."""
        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"name": "a1", "display_name": "A1"},
            {"name": "a2", "display_name": "A2"},
        ]

        with patch("httpx.get", return_value=mock_response):
            result = _get_agents("http://localhost:8000")
        assert result == {"a1": "A1", "a2": "A2"}


# ---------------------------------------------------------------------------
# _stream_chat error paths
# ---------------------------------------------------------------------------


class TestStreamChat:
    """Lines 140-145: error paths in _stream_chat."""

    def test_stream_chat_connect_error(self):
        """Lines 140-141: ConnectError yields error tuple."""
        import httpx

        with patch("httpx.stream", side_effect=httpx.ConnectError("refused")):
            results = list(_stream_chat("http://localhost:8000", "test", [{"role": "user", "content": "hi"}]))
        assert len(results) == 1
        assert results[0][0] == "error"
        assert "Cannot connect" in results[0][1]

    def test_stream_chat_read_timeout(self):
        """Lines 142-143: ReadTimeout yields error tuple."""
        import httpx

        with patch("httpx.stream", side_effect=httpx.ReadTimeout("timed out")):
            results = list(_stream_chat("http://localhost:8000", "test", [{"role": "user", "content": "hi"}]))
        assert len(results) == 1
        assert results[0][0] == "error"
        assert "timed out" in results[0][1].lower()

    def test_stream_chat_generic_exception(self):
        """Lines 144-145: generic Exception yields error tuple."""
        with patch("httpx.stream", side_effect=RuntimeError("boom")):
            results = list(_stream_chat("http://localhost:8000", "test", [{"role": "user", "content": "hi"}]))
        assert len(results) == 1
        assert results[0][0] == "error"
        assert "boom" in results[0][1]
