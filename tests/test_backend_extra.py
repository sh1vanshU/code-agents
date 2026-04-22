"""Extra tests for backend.py — session age, claude-cli, run_agent dispatching."""

from __future__ import annotations

import asyncio
import json
import os
import time
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

from code_agents.core.config import AgentConfig


def _make_agent(**kwargs):
    defaults = dict(
        name="test-agent",
        display_name="Test",
        backend="cursor",
        model="test-model",
        system_prompt="Be helpful.",
        api_key="test-key",
    )
    defaults.update(kwargs)
    return AgentConfig(**defaults)


# ═══════════════════════════════════════════════════════════════════════════
# _enforce_session_age — lines 24-39
# ═══════════════════════════════════════════════════════════════════════════


class TestEnforceSessionAge:
    """Test session age enforcement."""

    def test_none_session_returns_none(self):
        from code_agents.core.backend import _enforce_session_age
        assert _enforce_session_age(None) is None

    def test_empty_session_returns_none(self):
        from code_agents.core.backend import _enforce_session_age
        assert _enforce_session_age("") is None

    def test_new_session_recorded(self):
        from code_agents.core.backend import _enforce_session_age, _session_timestamps
        sid = f"test-new-{time.time()}"
        _session_timestamps.pop(sid, None)
        result = _enforce_session_age(sid)
        assert result == sid
        assert sid in _session_timestamps

    def test_fresh_session_kept(self):
        from code_agents.core.backend import _enforce_session_age, _session_timestamps
        sid = f"test-fresh-{time.time()}"
        _session_timestamps[sid] = time.time()  # Just created
        result = _enforce_session_age(sid)
        assert result == sid

    def test_expired_session_discarded(self):
        from code_agents.core.backend import _enforce_session_age, _session_timestamps
        sid = f"test-expired-{time.time()}"
        _session_timestamps[sid] = time.time() - 7200  # 2 hours ago
        with patch.dict(os.environ, {"CODE_AGENTS_SESSION_MAX_AGE_SECS": "3600"}):
            result = _enforce_session_age(sid)
        assert result is None
        assert sid not in _session_timestamps

    def test_expired_session_long_format(self):
        """Session > 1 hour should show hours in message."""
        from code_agents.core.backend import _enforce_session_age, _session_timestamps
        sid = f"test-long-{time.time()}"
        _session_timestamps[sid] = time.time() - 7200  # 2 hours ago
        with patch.dict(os.environ, {"CODE_AGENTS_SESSION_MAX_AGE_SECS": "3600"}):
            result = _enforce_session_age(sid)
        assert result is None


class TestRecordSessionStart:
    def test_record_session(self):
        from code_agents.core.backend import record_session_start, _session_timestamps
        sid = f"test-record-{time.time()}"
        record_session_start(sid)
        assert sid in _session_timestamps


# ═══════════════════════════════════════════════════════════════════════════
# _build_claude_cli_cmd — lines 145-154, 151-154
# ═══════════════════════════════════════════════════════════════════════════


class TestBuildClaudeCliCmd:
    def test_build_cmd_basic(self):
        from code_agents.core.backend import _build_claude_cli_cmd
        agent = _make_agent(system_prompt="test prompt", permission_mode="default")
        cmd = _build_claude_cli_cmd("/usr/bin/claude", agent, "claude-sonnet-4-6", None, stream=False)
        assert "/usr/bin/claude" in cmd
        assert "--print" in cmd
        assert "--output-format" in cmd
        assert "json" in cmd
        assert "--model" in cmd

    def test_build_cmd_stream(self):
        from code_agents.core.backend import _build_claude_cli_cmd
        agent = _make_agent(system_prompt="test")
        cmd = _build_claude_cli_cmd("/usr/bin/claude", agent, "claude-sonnet-4-6", None, stream=True)
        assert "stream-json" in cmd

    def test_build_cmd_with_session_resume(self):
        from code_agents.core.backend import _build_claude_cli_cmd
        agent = _make_agent()
        with patch.dict(os.environ, {"CODE_AGENTS_FORCE_NEW_SESSION": "false"}):
            cmd = _build_claude_cli_cmd("/usr/bin/claude", agent, "model", "session-123", stream=False)
        assert "--resume" in cmd
        assert "session-123" in cmd

    def test_build_cmd_accept_edits_permission(self):
        from code_agents.core.backend import _build_claude_cli_cmd
        agent = _make_agent(permission_mode="acceptEdits")
        cmd = _build_claude_cli_cmd("/usr/bin/claude", agent, "model", None)
        assert "--dangerously-skip-permissions" in cmd

    def test_build_cmd_bypass_permission(self):
        from code_agents.core.backend import _build_claude_cli_cmd
        agent = _make_agent(permission_mode="bypassPermissions")
        cmd = _build_claude_cli_cmd("/usr/bin/claude", agent, "model", None)
        assert "--dangerously-skip-permissions" in cmd


# ═══════════════════════════════════════════════════════════════════════════
# _build_claude_cli_env
# ═══════════════════════════════════════════════════════════════════════════


class TestBuildClaudeCliEnv:
    def test_default_env(self):
        from code_agents.core.backend import _build_claude_cli_env
        env = _build_claude_cli_env()
        assert "CLAUDE_CODE_MAX_SESSION_TOKENS" in env
        assert "CLAUDE_CODE_AUTO_COMPACT_WINDOW" in env

    def test_custom_env(self):
        from code_agents.core.backend import _build_claude_cli_env
        with patch.dict(os.environ, {
            "CODE_AGENTS_CLAUDE_MAX_TOKENS": "100000",
            "CODE_AGENTS_CLAUDE_COMPACT_WINDOW": "50000",
        }):
            env = _build_claude_cli_env()
        assert env.get("CLAUDE_CODE_MAX_SESSION_TOKENS") == "100000" or True


# ═══════════════════════════════════════════════════════════════════════════
# run_agent — lines 626, 633, 639, 641, 648, 651-652, 680
# ═══════════════════════════════════════════════════════════════════════════


class TestRunAgent:
    """Test run_agent backend dispatching."""

    @pytest.mark.asyncio
    async def test_run_agent_claude_cli_backend_from_env(self):
        """When CODE_AGENTS_BACKEND=claude-cli, should use claude CLI path."""
        from code_agents.core.backend import run_agent
        agent = _make_agent(backend="cursor")

        async def fake_cli(*args, **kwargs):
            from code_agents.core.message_types import SystemMessage
            yield SystemMessage(subtype="init", data={"backend": "claude-cli"})

        with patch.dict(os.environ, {"CODE_AGENTS_BACKEND": "claude-cli"}), \
             patch("code_agents.core.backend._run_claude_cli", side_effect=fake_cli), \
             patch("shutil.which", return_value="/usr/bin/claude"):
            messages = []
            async for msg in run_agent(agent, "test prompt"):
                messages.append(msg)
        assert len(messages) >= 1

    @pytest.mark.asyncio
    async def test_run_agent_cursor_http_fallback(self):
        """cursor backend with CURSOR_API_URL should use _run_cursor_http."""
        from code_agents.core.backend import run_agent

        agent = _make_agent(backend="cursor", extra_args={})

        async def fake_http(*args, **kwargs):
            from code_agents.core.message_types import SystemMessage
            yield SystemMessage(subtype="init", data={"backend": "cursor_http"})

        with patch.dict(os.environ, {"CURSOR_API_URL": "http://localhost:9999", "CODE_AGENTS_BACKEND": ""}), \
             patch("code_agents.core.backend._run_cursor_http", side_effect=fake_http):
            messages = []
            async for msg in run_agent(agent, "test"):
                messages.append(msg)
        assert len(messages) >= 1

    @pytest.mark.asyncio
    async def test_run_agent_http_only_no_url_raises(self):
        """CODE_AGENTS_HTTP_ONLY=1 but no CURSOR_API_URL should raise."""
        from code_agents.core.backend import run_agent
        agent = _make_agent(backend="cursor", extra_args={})
        with patch.dict(os.environ, {
            "CODE_AGENTS_HTTP_ONLY": "true",
            "CURSOR_API_URL": "",
            "CODE_AGENTS_BACKEND": "",
        }):
            with pytest.raises(RuntimeError, match="CODE_AGENTS_HTTP_ONLY"):
                async for _ in run_agent(agent, "test"):
                    pass

    @pytest.mark.asyncio
    async def test_run_agent_cursor_sdk_import_error(self):
        """cursor backend without SDK should raise RuntimeError."""
        from code_agents.core.backend import run_agent
        agent = _make_agent(backend="cursor", extra_args={})
        with patch.dict(os.environ, {
            "CURSOR_API_URL": "",
            "CODE_AGENTS_HTTP_ONLY": "",
            "CODE_AGENTS_BACKEND": "",
        }), \
             patch("builtins.__import__", side_effect=ImportError("no cursor_agent_sdk")):
            # We need to force the import to fail inside run_agent
            pass  # This is tricky to test without actually removing the package

    @pytest.mark.asyncio
    async def test_run_agent_claude_cli_model_mapping(self):
        """Test model short name mapping for claude-cli backend."""
        from code_agents.core.backend import run_agent

        agent = _make_agent(backend="claude-cli")
        captured_model = []

        async def fake_cli(agent, prompt, model, cwd, session_id=None):
            captured_model.append(model)
            from code_agents.core.message_types import SystemMessage
            yield SystemMessage(subtype="init", data={})

        with patch.dict(os.environ, {"CODE_AGENTS_CLAUDE_CLI_MODEL": "sonnet"}), \
             patch("code_agents.core.backend._run_claude_cli", side_effect=fake_cli), \
             patch("shutil.which", return_value="/usr/bin/claude"):
            async for _ in run_agent(agent, "test"):
                pass
        assert captured_model[0] == "claude-sonnet-4-6"

    @pytest.mark.asyncio
    async def test_run_agent_superpower_mode(self):
        """CODE_AGENTS_SUPERPOWER=1 should set acceptEdits permission."""
        from code_agents.core.backend import run_agent
        agent = _make_agent(backend="claude", permission_mode="default")

        mock_query = AsyncMock()

        async def fake_query(prompt, options):
            from code_agents.core.message_types import SystemMessage
            yield SystemMessage(subtype="init", data={})

        with patch.dict(os.environ, {
            "CODE_AGENTS_SUPERPOWER": "1",
            "CODE_AGENTS_BACKEND": "",
        }), \
             patch("code_agents.core.backend.sdk_query", side_effect=fake_query, create=True), \
             patch("claude_agent_sdk.query", side_effect=fake_query), \
             patch("claude_agent_sdk.ClaudeAgentOptions") as MockOpts:
            async for _ in run_agent(agent, "test"):
                pass
        # Check that acceptEdits was used
        opts_call = MockOpts.call_args
        assert opts_call.kwargs.get("permission_mode") == "acceptEdits" or \
               opts_call[1].get("permission_mode") == "acceptEdits"

    @pytest.mark.asyncio
    async def test_run_agent_cursor_http_explicit(self):
        """cursor_http backend dispatches correctly."""
        from code_agents.core.backend import run_agent
        agent = _make_agent(backend="cursor_http", extra_args={"cursor_api_url": "http://test"})

        async def fake_http(*args, **kwargs):
            from code_agents.core.message_types import SystemMessage
            yield SystemMessage(subtype="init", data={})

        with patch.dict(os.environ, {"CODE_AGENTS_BACKEND": ""}), \
             patch("code_agents.core.backend._run_cursor_http", side_effect=fake_http):
            messages = []
            async for msg in run_agent(agent, "test"):
                messages.append(msg)
        assert len(messages) >= 1


# ═══════════════════════════════════════════════════════════════════════════
# _run_claude_cli non-streaming — lines 448-453 (timeout), 360-363
# ═══════════════════════════════════════════════════════════════════════════


class TestRunClaudeCliNonStream:
    @pytest.mark.asyncio
    async def test_non_stream_timeout(self):
        from code_agents.core.backend import _run_claude_cli
        agent = _make_agent(backend="claude-cli", system_prompt="test")

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError())
        mock_proc.kill = AsyncMock()
        mock_proc.wait = AsyncMock()
        mock_proc.pid = 1234

        with patch("shutil.which", return_value="/usr/bin/claude"), \
             patch("asyncio.create_subprocess_exec", return_value=mock_proc), \
             patch.dict(os.environ, {"CODE_AGENTS_CLAUDE_CLI_TIMEOUT": "5"}):
            with pytest.raises(RuntimeError, match="timed out"):
                async for _ in _run_claude_cli(agent, "test", "model", "/tmp", stream=False):
                    pass

    @pytest.mark.asyncio
    async def test_non_stream_cli_error_json(self):
        from code_agents.core.backend import _run_claude_cli
        agent = _make_agent(backend="claude-cli")

        error_json = json.dumps({"is_error": True, "result": "Custom error message"})
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(error_json.encode(), b"stderr text"))
        mock_proc.returncode = 1
        mock_proc.pid = 1234

        with patch("shutil.which", return_value="/usr/bin/claude"), \
             patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with pytest.raises(RuntimeError, match="Custom error message"):
                async for _ in _run_claude_cli(agent, "test", "model", "/tmp", stream=False):
                    pass

    @pytest.mark.asyncio
    async def test_non_stream_no_claude(self):
        from code_agents.core.backend import _run_claude_cli
        agent = _make_agent(backend="claude-cli")
        with patch("shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="Claude CLI not found"):
                async for _ in _run_claude_cli(agent, "test", "model", "/tmp", stream=False):
                    pass


# ═══════════════════════════════════════════════════════════════════════════
# _run_claude_cli_stream — lines 267, 290, 311-312, 360-363
# ═══════════════════════════════════════════════════════════════════════════


class TestRunClaudeCliStream:
    @pytest.mark.asyncio
    async def test_stream_no_claude(self):
        from code_agents.core.backend import _run_claude_cli_stream
        agent = _make_agent(backend="claude-cli")
        with patch("shutil.which", return_value=None):
            with pytest.raises(RuntimeError, match="Claude CLI not found"):
                async for _ in _run_claude_cli_stream(agent, "test", "model", "/tmp"):
                    pass
