"""Tests for code_agents.chat.chat_validation module."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest


class TestCheckServer:
    """Test check_server health check."""

    def test_healthy_server(self):
        from code_agents.chat.chat_validation import check_server
        mock_resp = MagicMock(status_code=200)
        with patch("httpx.get", return_value=mock_resp):
            assert check_server("http://localhost:8000") is True

    def test_unhealthy_server(self):
        from code_agents.chat.chat_validation import check_server
        mock_resp = MagicMock(status_code=500)
        with patch("httpx.get", return_value=mock_resp):
            assert check_server("http://localhost:8000") is False

    def test_connection_error(self):
        from code_agents.chat.chat_validation import check_server
        import httpx
        with patch("httpx.get", side_effect=httpx.ConnectError("refused")):
            assert check_server("http://localhost:9999") is False

    def test_timeout_error(self):
        from code_agents.chat.chat_validation import check_server
        with patch("httpx.get", side_effect=TimeoutError):
            assert check_server("http://localhost:8000") is False


class TestEnsureServerRunning:
    """Test ensure_server_running flow."""

    def test_server_already_running(self):
        from code_agents.chat.chat_validation import ensure_server_running
        with patch("code_agents.chat.chat_validation.check_server", return_value=True):
            assert ensure_server_running("http://localhost:8000", "/tmp") is True

    def test_server_not_running_user_declines(self):
        from code_agents.chat.chat_validation import ensure_server_running
        with patch("code_agents.chat.chat_validation.check_server", return_value=False):
            with patch("builtins.input", return_value="n"):
                assert ensure_server_running("http://localhost:8000", "/tmp") is False

    def test_server_not_running_user_accepts_and_starts(self):
        from code_agents.chat.chat_validation import ensure_server_running
        check_calls = iter([False, True])  # first call False, second True after start
        with patch("code_agents.chat.chat_validation.check_server", side_effect=check_calls):
            with patch("builtins.input", return_value="y"):
                with patch("subprocess.Popen"):
                    with patch("time.sleep"):
                        assert ensure_server_running("http://localhost:8000", "/tmp") is True

    def test_server_not_running_start_fails(self):
        from code_agents.chat.chat_validation import ensure_server_running
        with patch("code_agents.chat.chat_validation.check_server", return_value=False):
            with patch("builtins.input", return_value="y"):
                with patch("subprocess.Popen"):
                    with patch("time.sleep"):
                        assert ensure_server_running("http://localhost:8000", "/tmp") is False

    def test_server_not_running_eof(self):
        from code_agents.chat.chat_validation import ensure_server_running
        with patch("code_agents.chat.chat_validation.check_server", return_value=False):
            with patch("builtins.input", side_effect=EOFError):
                assert ensure_server_running("http://localhost:8000", "/tmp") is False

    def test_server_not_running_keyboard_interrupt(self):
        from code_agents.chat.chat_validation import ensure_server_running
        with patch("code_agents.chat.chat_validation.check_server", return_value=False):
            with patch("builtins.input", side_effect=KeyboardInterrupt):
                assert ensure_server_running("http://localhost:8000", "/tmp") is False


class TestCheckWorkspaceTrust:
    """Test check_workspace_trust."""

    def test_claude_cli_backend_trusted(self):
        from code_agents.chat.chat_validation import check_workspace_trust
        with patch.dict(os.environ, {"CODE_AGENTS_BACKEND": "claude-cli"}, clear=False):
            assert check_workspace_trust("/tmp") is True

    def test_cursor_api_url_trusted(self):
        from code_agents.chat.chat_validation import check_workspace_trust
        with patch.dict(os.environ, {"CODE_AGENTS_BACKEND": "", "CURSOR_API_URL": "http://api", "ANTHROPIC_API_KEY": ""}, clear=False):
            assert check_workspace_trust("/tmp") is True

    def test_anthropic_key_trusted(self):
        from code_agents.chat.chat_validation import check_workspace_trust
        with patch.dict(os.environ, {"CODE_AGENTS_BACKEND": "", "CURSOR_API_URL": "", "ANTHROPIC_API_KEY": "sk-ant-test"}, clear=False):
            assert check_workspace_trust("/tmp") is True

    def test_no_backend_warns_but_trusts(self, capsys):
        from code_agents.chat.chat_validation import check_workspace_trust
        with patch.dict(os.environ, {"CODE_AGENTS_BACKEND": "", "CURSOR_API_URL": "", "ANTHROPIC_API_KEY": ""}, clear=False):
            with patch("shutil.which", return_value=None):
                assert check_workspace_trust("/tmp") is True
        output = capsys.readouterr().out
        assert "cursor-agent not found" in output

    def test_cursor_agent_found_no_warning(self, capsys):
        from code_agents.chat.chat_validation import check_workspace_trust
        with patch.dict(os.environ, {"CODE_AGENTS_BACKEND": "", "CURSOR_API_URL": "", "ANTHROPIC_API_KEY": ""}, clear=False):
            with patch("shutil.which", return_value="/usr/bin/cursor-agent"):
                assert check_workspace_trust("/tmp") is True
        output = capsys.readouterr().out
        assert "cursor-agent not found" not in output


class TestBackendValidator:
    """Test BackendValidator background thread."""

    def test_valid_backend(self):
        from code_agents.chat.chat_validation import BackendValidator
        mock_result = MagicMock(valid=True, message="ok", backend="cursor")
        with patch("code_agents.devops.connection_validator.validate_backend", return_value=mock_result):
            with patch("asyncio.run", return_value=mock_result):
                v = BackendValidator()
                v._result = mock_result  # simulate completed thread
                assert v.check(timeout=0.1) is True

    def test_invalid_backend_user_aborts(self):
        from code_agents.chat.chat_validation import BackendValidator
        mock_result = MagicMock(valid=False, message="key missing", backend="cursor")
        v = BackendValidator()
        v._result = mock_result
        v._thread = MagicMock()  # simulate thread
        with patch("builtins.input", return_value="n"):
            assert v.check(timeout=0.1) is False

    def test_invalid_backend_user_continues(self):
        from code_agents.chat.chat_validation import BackendValidator
        mock_result = MagicMock(valid=False, message="key missing", backend="cursor")
        v = BackendValidator()
        v._result = mock_result
        v._thread = MagicMock()
        with patch("builtins.input", return_value="y"):
            assert v.check(timeout=0.1) is True

    def test_invalid_backend_eof_aborts(self):
        from code_agents.chat.chat_validation import BackendValidator
        mock_result = MagicMock(valid=False, message="key missing", backend="cursor")
        v = BackendValidator()
        v._result = mock_result
        v._thread = MagicMock()
        with patch("builtins.input", side_effect=EOFError):
            assert v.check(timeout=0.1) is False

    def test_invalid_backend_keyboard_interrupt_aborts(self):
        from code_agents.chat.chat_validation import BackendValidator
        mock_result = MagicMock(valid=False, message="key missing", backend="cursor")
        v = BackendValidator()
        v._result = mock_result
        v._thread = MagicMock()
        with patch("builtins.input", side_effect=KeyboardInterrupt):
            assert v.check(timeout=0.1) is False

    def test_validation_error_skipped(self):
        from code_agents.chat.chat_validation import BackendValidator
        v = BackendValidator()
        v._error = ImportError("no module")
        v._thread = MagicMock()
        assert v.check(timeout=0.1) is True

    def test_validation_still_running(self):
        from code_agents.chat.chat_validation import BackendValidator
        v = BackendValidator()
        v._thread = MagicMock()  # thread that never sets result
        assert v.check(timeout=0.1) is True

    def test_no_thread_started(self):
        from code_agents.chat.chat_validation import BackendValidator
        v = BackendValidator()
        assert v.check(timeout=0.1) is True

    def test_start_launches_thread(self):
        from code_agents.chat.chat_validation import BackendValidator
        v = BackendValidator()
        with patch("threading.Thread") as mock_thread_cls:
            mock_thread = MagicMock()
            mock_thread_cls.return_value = mock_thread
            v.start()
            mock_thread_cls.assert_called_once()
            mock_thread.start.assert_called_once()
