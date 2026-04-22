"""CLI tests grouped by feature area (split from legacy monolith)."""
from __future__ import annotations

import os
import sys
from unittest.mock import patch, MagicMock

import pytest


class TestPromptYesNo:
    """Test prompt_yes_no helper."""

    def test_default_yes(self):
        from code_agents.cli.cli_helpers import prompt_yes_no
        with patch("builtins.input", return_value=""):
            assert prompt_yes_no("Question?", default=True) is True

    def test_default_no(self):
        from code_agents.cli.cli_helpers import prompt_yes_no
        with patch("builtins.input", return_value=""):
            assert prompt_yes_no("Question?", default=False) is False

    def test_answer_yes(self):
        from code_agents.cli.cli_helpers import prompt_yes_no
        with patch("builtins.input", return_value="y"):
            assert prompt_yes_no("Q?") is True

    def test_answer_no(self):
        from code_agents.cli.cli_helpers import prompt_yes_no
        with patch("builtins.input", return_value="n"):
            assert prompt_yes_no("Q?") is False

    def test_eof_error_returns_default(self):
        from code_agents.cli.cli_helpers import prompt_yes_no
        with patch("builtins.input", side_effect=EOFError):
            assert prompt_yes_no("Q?", default=True) is True

    def test_keyboard_interrupt_returns_default(self):
        from code_agents.cli.cli_helpers import prompt_yes_no
        with patch("builtins.input", side_effect=KeyboardInterrupt):
            assert prompt_yes_no("Q?", default=False) is False
class TestCheckWorkspaceTrust:
    """Test _check_workspace_trust."""

    def test_claude_cli_backend(self):
        from code_agents.cli.cli_helpers import _check_workspace_trust
        with patch.dict(os.environ, {"CODE_AGENTS_BACKEND": "claude-cli"}):
            assert _check_workspace_trust("/tmp") is True

    def test_cursor_api_url(self):
        from code_agents.cli.cli_helpers import _check_workspace_trust
        with patch.dict(os.environ, {"CURSOR_API_URL": "http://localhost:8080"}):
            assert _check_workspace_trust("/tmp") is True

    def test_anthropic_key(self):
        from code_agents.cli.cli_helpers import _check_workspace_trust
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-123"}):
            assert _check_workspace_trust("/tmp") is True

    def test_no_backend(self):
        from code_agents.cli.cli_helpers import _check_workspace_trust
        with patch.dict(os.environ, {}, clear=True):
            assert _check_workspace_trust("/tmp") is True
class TestApiPost:
    """Test _api_post error handling."""

    def test_api_post_success(self):
        from code_agents.cli.cli_helpers import _api_post
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"result": "ok"}
        with patch("httpx.post", return_value=mock_resp), \
             patch.dict(os.environ, {"HOST": "127.0.0.1", "PORT": "8000"}):
            result = _api_post("/test", {"key": "value"})
        assert result == {"result": "ok"}

    def test_api_post_failure(self, capsys):
        from code_agents.cli.cli_helpers import _api_post
        with patch("httpx.post", side_effect=Exception("connection refused")), \
             patch.dict(os.environ, {"HOST": "127.0.0.1", "PORT": "8000"}):
            result = _api_post("/test")
        assert result is None
class TestApiGet:
    """Test _api_get."""

    def test_api_get_success(self):
        from code_agents.cli.cli_helpers import _api_get
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"status": "ok"}
        with patch("httpx.get", return_value=mock_resp), \
             patch.dict(os.environ, {"HOST": "127.0.0.1", "PORT": "8000"}):
            result = _api_get("/health")
        assert result == {"status": "ok"}

    def test_api_get_failure(self):
        from code_agents.cli.cli_helpers import _api_get
        with patch("httpx.get", side_effect=Exception("timeout")), \
             patch.dict(os.environ, {"HOST": "127.0.0.1", "PORT": "8000"}):
            result = _api_get("/health")
        assert result is None
