"""Comprehensive tests for chat slash command modules.

Covers: chat_slash_analysis, chat_slash_tools, chat_slash_agents,
        chat_slash_nav, chat_slash_session, chat_slash_config,
        chat_response, chat_streaming, chat_server, chat_context,
        chat_history.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open, PropertyMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _state(**overrides):
    """Build a minimal state dict for slash command handlers."""
    base = {
        "agent": "code-writer",
        "repo_path": "/tmp/test-repo",
        "session_id": "test-session-123",
        "_chat_session": None,
        "_pair_mode": None,
        "_last_output": "",
        "messages": [],
    }
    base.update(overrides)
    return base


# ============================================================================
# chat_slash_config.py
# ============================================================================


class TestSlashConfig:
    """Tests for /model and /backend commands."""

    def test_model_no_arg_shows_current(self, capsys):
        from code_agents.chat.chat_slash_config import _handle_config

        mock_cfg = MagicMock()
        mock_cfg.model = "Composer 2 Fast"
        mock_loader = MagicMock()
        mock_loader.get.return_value = mock_cfg
        with patch("code_agents.core.config.agent_loader", mock_loader):
            result = _handle_config("/model", "", _state(), "http://localhost:8000")
        assert result is None
        out = capsys.readouterr().out
        assert "Composer 2 Fast" in out

    def test_model_set_custom(self, capsys):
        from code_agents.chat.chat_slash_config import _handle_config

        mock_cfg = MagicMock()
        mock_cfg.model = "Composer 2 Fast"
        mock_loader = MagicMock()
        mock_loader.get.return_value = mock_cfg
        state = _state()
        with patch("code_agents.core.config.agent_loader", mock_loader):
            result = _handle_config("/model", "gpt-4o", state, "http://localhost:8000")
        assert result is None
        assert state["_model_override"] == "gpt-4o"
        assert mock_cfg.model == "gpt-4o"

    def test_model_shortcut_opus(self, capsys):
        from code_agents.chat.chat_slash_config import _handle_config

        mock_cfg = MagicMock()
        mock_loader = MagicMock()
        mock_loader.get.return_value = mock_cfg
        state = _state()
        with patch("code_agents.core.config.agent_loader", mock_loader):
            _handle_config("/model", "opus", state, "http://localhost:8000")
        assert state["_model_override"] == "claude-opus-4-6"

    def test_model_shortcut_sonnet(self):
        from code_agents.chat.chat_slash_config import _handle_config

        mock_cfg = MagicMock()
        mock_loader = MagicMock()
        mock_loader.get.return_value = mock_cfg
        state = _state()
        with patch("code_agents.core.config.agent_loader", mock_loader):
            _handle_config("/model", "sonnet", state, "http://localhost:8000")
        assert state["_model_override"] == "claude-sonnet-4-6"

    def test_model_shortcut_haiku(self):
        from code_agents.chat.chat_slash_config import _handle_config

        mock_cfg = MagicMock()
        mock_loader = MagicMock()
        mock_loader.get.return_value = mock_cfg
        state = _state()
        with patch("code_agents.core.config.agent_loader", mock_loader):
            _handle_config("/model", "haiku", state, "http://localhost:8000")
        assert state["_model_override"] == "claude-haiku-4-5-20251001"

    def test_backend_no_arg_shows_current(self, capsys):
        from code_agents.chat.chat_slash_config import _handle_config

        mock_cfg = MagicMock()
        mock_cfg.backend = "cursor"
        mock_loader = MagicMock()
        mock_loader.get.return_value = mock_cfg
        with patch("code_agents.core.config.agent_loader", mock_loader):
            result = _handle_config("/backend", "", _state(), "http://localhost:8000")
        assert result is None
        out = capsys.readouterr().out
        assert "cursor" in out

    def test_backend_set_claude(self, capsys):
        from code_agents.chat.chat_slash_config import _handle_config

        mock_cfg = MagicMock()
        mock_cfg.backend = "cursor"
        mock_loader = MagicMock()
        mock_loader.get.return_value = mock_cfg
        state = _state()
        with patch("code_agents.core.config.agent_loader", mock_loader):
            _handle_config("/backend", "claude", state, "http://localhost:8000")
        assert state["_backend_override"] == "claude"
        assert mock_cfg.backend == "claude"

    def test_backend_claude_cli_auto_switch_model(self, capsys):
        from code_agents.chat.chat_slash_config import _handle_config

        mock_cfg = MagicMock()
        mock_cfg.backend = "cursor"
        mock_cfg.model = "Composer 2 Fast"
        mock_loader = MagicMock()
        mock_loader.get.return_value = mock_cfg
        state = _state()
        with patch("code_agents.core.config.agent_loader", mock_loader):
            with patch.dict(os.environ, {"CODE_AGENTS_CLAUDE_CLI_MODEL": "claude-sonnet-4-6"}):
                _handle_config("/backend", "claude-cli", state, "http://localhost:8000")
        assert state["_backend_override"] == "claude-cli"
        assert mock_cfg.model == "claude-sonnet-4-6"
        out = capsys.readouterr().out
        assert "claude-cli" in out

    def test_backend_claude_api_shortcut(self):
        from code_agents.chat.chat_slash_config import _handle_config

        mock_cfg = MagicMock()
        mock_cfg.backend = "cursor"
        mock_cfg.model = "claude-sonnet-4-6"
        mock_loader = MagicMock()
        mock_loader.get.return_value = mock_cfg
        state = _state()
        with patch("code_agents.core.config.agent_loader", mock_loader):
            _handle_config("/backend", "claude-api", state, "http://localhost:8000")
        assert state["_backend_override"] == "claude"

    def test_config_not_handled(self):
        from code_agents.chat.chat_slash_config import _handle_config

        result = _handle_config("/unknown", "", _state(), "http://localhost:8000")
        assert result == "_not_handled"


# ============================================================================
# chat_slash_nav.py
# ============================================================================


class TestSlashNav:
    """Tests for navigation commands."""

    def test_quit_returns_quit(self):
        from code_agents.chat.chat_slash_nav import _handle_navigation

        for cmd in ("/quit", "/exit", "/q", "/bye"):
            assert _handle_navigation(cmd, "", _state(), "http://localhost:8000") == "quit"

    def test_help_prints_commands(self, capsys):
        from code_agents.chat.chat_slash_nav import _handle_navigation

        result = _handle_navigation("/help", "", _state(), "http://localhost:8000")
        assert result is None
        out = capsys.readouterr().out
        assert "/quit" in out
        assert "/agent" in out
        assert "/run" in out
        assert "/help" in out
        assert "/generate-tests" in out

    def test_open_no_output(self, capsys):
        from code_agents.chat.chat_slash_nav import _handle_navigation

        state = _state(_last_output="")
        result = _handle_navigation("/open", "", state, "http://localhost:8000")
        assert result is None
        out = capsys.readouterr().out
        assert "No output" in out

    def test_open_with_output(self):
        from code_agents.chat.chat_slash_nav import _handle_navigation

        state = _state(_last_output="Hello world response")
        with patch("subprocess.run") as mock_run:
            _handle_navigation("/open", "", state, "http://localhost:8000")
            mock_run.assert_called_once()

    def test_setup_no_arg_shows_sections(self, capsys):
        from code_agents.chat.chat_slash_nav import _handle_navigation

        result = _handle_navigation("/setup", "", _state(), "http://localhost:8000")
        assert result is None
        out = capsys.readouterr().out
        assert "jenkins" in out
        assert "argocd" in out

    def test_setup_unknown_section(self, capsys):
        from code_agents.chat.chat_slash_nav import _handle_navigation

        result = _handle_navigation("/setup", "foobar", _state(), "http://localhost:8000")
        assert result is None
        out = capsys.readouterr().out
        assert "Unknown section" in out

    def test_setup_section_cancelled(self, capsys):
        from code_agents.chat.chat_slash_nav import _handle_navigation

        with patch("builtins.input", side_effect=KeyboardInterrupt):
            result = _handle_navigation("/setup", "jenkins", _state(), "http://localhost:8000")
        assert result is None

    def test_setup_section_writes_values(self, capsys):
        from code_agents.chat.chat_slash_nav import _handle_navigation

        state = _state()
        # 7 Jenkins field values + "n" to decline server restart
        values = iter(["http://jenkins.local", "admin", "token123", "build-job", "deploy-job", "deploy-dev", "deploy-qa", "n"])
        with patch("builtins.input", side_effect=values):
            with patch("builtins.open", mock_open()) as mf:
                with patch("code_agents.chat.chat_slash_nav._check_server", return_value=True):
                    _handle_navigation("/setup", "jenkins", state, "http://localhost:8000")
        out = capsys.readouterr().out
        assert "Saved" in out

    def test_nav_not_handled(self):
        from code_agents.chat.chat_slash_nav import _handle_navigation

        result = _handle_navigation("/unknown_cmd", "", _state(), "http://localhost:8000")
        assert result == "_not_handled"

    def test_restart_server(self, capsys):
        from code_agents.chat.chat_slash_nav import _handle_navigation

        mock_result = MagicMock()
        mock_result.stdout = ""
        with patch("subprocess.run", return_value=mock_result):
            with patch("subprocess.Popen"):
                with patch("code_agents.chat.chat_slash_nav._check_server", return_value=True):
                    _handle_navigation("/restart", "", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "Restarting" in out


# ============================================================================
# chat_slash_session.py
# ============================================================================


class TestSlashSession:
    """Tests for session management commands."""

    def test_session_no_sessions(self, capsys):
        from code_agents.chat.chat_slash_session import _handle_session

        with patch("code_agents.chat.chat_history.list_sessions", return_value=[]):
            result = _handle_session("/session", "", _state(), "http://localhost:8000")
        assert result is None
        out = capsys.readouterr().out
        assert "No saved sessions" in out

    def test_session_with_current_id(self, capsys):
        from code_agents.chat.chat_slash_session import _handle_session

        state = _state(session_id="abc-123")
        with patch("code_agents.chat.chat_history.list_sessions", return_value=[]):
            _handle_session("/session", "", state, "http://localhost:8000")
        out = capsys.readouterr().out
        assert "abc-123" in out

    def test_session_with_saved_sessions(self, capsys):
        from code_agents.chat.chat_slash_session import _handle_session

        mock_sessions = [
            {"id": "sess-001", "agent": "code-writer", "title": "Test chat",
             "message_count": 5, "updated_at": time.time()},
        ]
        mock_path = MagicMock()
        mock_stat = MagicMock()
        mock_stat.st_size = 2048
        mock_path.stat.return_value = mock_stat

        with patch("code_agents.chat.chat_history.list_sessions", return_value=mock_sessions):
            with patch("code_agents.chat.chat_history.HISTORY_DIR") as mock_dir:
                mock_dir.__truediv__ = MagicMock(return_value=mock_path)
                _handle_session("/session", "", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "sess-00" in out

    def test_clear_resets_session(self, capsys):
        from code_agents.chat.chat_slash_session import _handle_session

        state = _state(session_id="old-session", _chat_session={"id": "old"})
        _handle_session("/clear", "", state, "http://localhost:8000")
        assert state["session_id"] is None
        assert state["_chat_session"] is None
        out = capsys.readouterr().out
        assert "cleared" in out

    def test_history_no_sessions(self, capsys):
        from code_agents.chat.chat_slash_session import _handle_session

        with patch("code_agents.chat.chat_history.list_sessions", return_value=[]):
            _handle_session("/history", "", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "No chat history" in out

    def test_history_with_sessions(self, capsys):
        from code_agents.chat.chat_slash_session import _handle_session

        sessions = [{
            "id": "abc-123-456",
            "agent": "code-writer",
            "title": "Fix auth bug",
            "message_count": 10,
            "updated_at": time.time(),
            "repo_path": "/tmp/test-repo",
        }]
        with patch("code_agents.chat.chat_history.list_sessions", return_value=sessions):
            _handle_session("/history", "", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "abc-123-456" in out
        assert "Fix auth bug" in out

    def test_history_all_flag(self, capsys):
        from code_agents.chat.chat_slash_session import _handle_session

        with patch("code_agents.chat.chat_history.list_sessions", return_value=[]) as mock_list:
            _handle_session("/history", "--all", _state(), "http://localhost:8000")
            mock_list.assert_called_once_with(limit=15, repo_path=None)

    def test_resume_no_arg(self, capsys):
        from code_agents.chat.chat_slash_session import _handle_session

        result = _handle_session("/resume", "", _state(), "http://localhost:8000")
        assert result is None
        out = capsys.readouterr().out
        assert "Usage" in out

    def test_resume_not_found(self, capsys):
        from code_agents.chat.chat_slash_session import _handle_session

        with patch("code_agents.chat.chat_history.load_session", return_value=None):
            _handle_session("/resume", "nonexistent", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "not found" in out

    def test_resume_success(self, capsys):
        from code_agents.chat.chat_slash_session import _handle_session

        loaded = {
            "agent": "code-reviewer",
            "title": "Review PR #42",
            "_server_session_id": "server-sess-1",
            "messages": [
                {"role": "user", "content": "Review this PR"},
                {"role": "assistant", "content": "Sure, looking at it..."},
            ],
        }
        state = _state()
        with patch("code_agents.chat.chat_history.load_session", return_value=loaded):
            with patch("code_agents.chat.chat_history.get_qa_pairs", return_value=[]):
                _handle_session("/resume", "abc-123", state, "http://localhost:8000")
        assert state["agent"] == "code-reviewer"
        assert state["_chat_session"] == loaded
        out = capsys.readouterr().out
        assert "Resumed" in out
        assert "Review PR #42" in out

    def test_delete_chat_no_arg(self, capsys):
        from code_agents.chat.chat_slash_session import _handle_session

        result = _handle_session("/delete-chat", "", _state(), "http://localhost:8000")
        assert result is None

    def test_delete_chat_success(self, capsys):
        from code_agents.chat.chat_slash_session import _handle_session

        with patch("code_agents.chat.chat_history.delete_session", return_value=True):
            _handle_session("/delete-chat", "sess-abc", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "Deleted" in out

    def test_delete_chat_not_found(self, capsys):
        from code_agents.chat.chat_slash_session import _handle_session

        with patch("code_agents.chat.chat_history.delete_session", return_value=False):
            _handle_session("/delete-chat", "sess-none", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "not found" in out

    def test_export(self, capsys):
        from code_agents.chat.chat_slash_session import _handle_session

        state = _state(messages=[
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ])
        with tempfile.TemporaryDirectory() as tmpdir:
            # _get_history_dir doesn't exist in chat_history, so inject it
            import code_agents.chat.chat_history as _ch_mod
            _ch_mod._get_history_dir = lambda: tmpdir
            try:
                _handle_session("/export", "", state, "http://localhost:8000")
                out = capsys.readouterr().out
                assert "Exported" in out
                exports = list(Path(tmpdir).glob("export_*.md"))
                assert len(exports) == 1
                content = exports[0].read_text()
                assert "Hello" in content
                assert "Hi there" in content
            finally:
                if hasattr(_ch_mod, "_get_history_dir"):
                    del _ch_mod._get_history_dir

    def test_session_not_handled(self):
        from code_agents.chat.chat_slash_session import _handle_session

        result = _handle_session("/unknown", "", _state(), "http://localhost:8000")
        assert result == "_not_handled"


# ============================================================================
# chat_slash_agents.py
# ============================================================================


class TestSlashAgents:
    """Tests for agent and skill commands."""

    def test_agents_list(self, capsys):
        from code_agents.chat.chat_slash_agents import _handle_agent_ops

        agents = {"code-writer": "Code Writer", "code-reviewer": "Code Reviewer"}
        with patch("code_agents.chat.chat_slash_agents._get_agents", return_value=agents):
            result = _handle_agent_ops("/agents", "", _state(), "http://localhost:8000")
        assert result is None
        out = capsys.readouterr().out
        assert "code-writer" in out
        assert "code-reviewer" in out

    def test_agent_switch_no_arg(self, capsys):
        from code_agents.chat.chat_slash_agents import _handle_agent_ops

        result = _handle_agent_ops("/agent", "", _state(), "http://localhost:8000")
        assert result is None
        out = capsys.readouterr().out
        assert "Usage" in out

    def test_agent_switch_not_found(self, capsys):
        from code_agents.chat.chat_slash_agents import _handle_agent_ops

        with patch("code_agents.chat.chat_slash_agents._get_agents", return_value={"code-writer": "CW"}):
            result = _handle_agent_ops("/agent", "nonexistent", _state(), "http://localhost:8000")
        assert result is None
        out = capsys.readouterr().out
        assert "not found" in out

    def test_agent_switch_success(self, capsys):
        from code_agents.chat.chat_slash_agents import _handle_agent_ops

        agents = {"code-writer": "CW", "code-reviewer": "CR"}
        state = _state()
        with patch("code_agents.chat.chat_slash_agents._get_agents", return_value=agents):
            with patch("code_agents.core.token_tracker.get_session_summary", return_value={"messages": 0}):
                with patch("code_agents.core.token_tracker.init_session"):
                    with patch("code_agents.chat.chat_welcome._print_welcome"):
                        _handle_agent_ops("/agent", "code-reviewer", state, "http://localhost:8000")
        assert state["agent"] == "code-reviewer"
        assert state["session_id"] is None
        out = capsys.readouterr().out
        assert "Switched" in out

    def test_agent_switch_with_token_summary(self, capsys):
        from code_agents.chat.chat_slash_agents import _handle_agent_ops

        agents = {"code-writer": "CW", "code-reviewer": "CR"}
        state = _state()
        usage = {"messages": 5, "input_tokens": 1000, "output_tokens": 500}
        with patch("code_agents.chat.chat_slash_agents._get_agents", return_value=agents):
            with patch("code_agents.core.token_tracker.get_session_summary", return_value=usage):
                with patch("code_agents.core.token_tracker.init_session"):
                    with patch("code_agents.chat.chat_welcome._print_welcome"):
                        _handle_agent_ops("/agent", "code-reviewer", state, "http://localhost:8000")
        out = capsys.readouterr().out
        assert "1,000" in out  # formatted tokens

    def test_skills_current_agent(self, capsys):
        from code_agents.chat.chat_slash_agents import _handle_agent_ops

        mock_skill = MagicMock()
        mock_skill.name = "test-skill"
        mock_skill.description = "A test skill"
        mock_skill.full_name = "code-writer:test-skill"
        all_skills = {"code-writer": [mock_skill]}
        with patch("code_agents.agent_system.skill_loader.load_agent_skills", return_value=all_skills):
            with patch("code_agents.core.config.settings") as mock_settings:
                mock_settings.agents_dir = "/agents"
                _handle_agent_ops("/skills", "", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "test-skill" in out

    def test_skills_specific_agent(self, capsys):
        from code_agents.chat.chat_slash_agents import _handle_agent_ops

        mock_skill = MagicMock()
        mock_skill.name = "deploy"
        mock_skill.description = "Deploy workflow"
        all_skills = {"jenkins-cicd": [mock_skill]}
        with patch("code_agents.agent_system.skill_loader.load_agent_skills", return_value=all_skills):
            with patch("code_agents.core.config.settings"):
                _handle_agent_ops("/skills", "jenkins-cicd", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "deploy" in out

    def test_skills_no_skills_for_agent(self, capsys):
        from code_agents.chat.chat_slash_agents import _handle_agent_ops

        with patch("code_agents.agent_system.skill_loader.load_agent_skills", return_value={}):
            with patch("code_agents.core.config.settings"):
                _handle_agent_ops("/skills", "unknown-agent", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "No skills" in out

    def test_skills_all_agents(self, capsys):
        from code_agents.chat.chat_slash_agents import _handle_agent_ops

        mock_skill = MagicMock()
        mock_skill.name = "build"
        all_skills = {"jenkins-cicd": [mock_skill], "git-ops": [mock_skill]}
        state = _state(agent="")
        with patch("code_agents.agent_system.skill_loader.load_agent_skills", return_value=all_skills):
            with patch("code_agents.core.config.settings"):
                _handle_agent_ops("/skills", "", state, "http://localhost:8000")
        out = capsys.readouterr().out
        assert "jenkins-cicd" in out
        assert "git-ops" in out

    def test_memory_show(self, capsys):
        from code_agents.chat.chat_slash_agents import _handle_agent_ops

        with patch("code_agents.agent_system.agent_memory.load_memory", return_value="- Learned X\n- Learned Y"):
            _handle_agent_ops("/memory", "", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "Learned X" in out

    def test_memory_empty(self, capsys):
        from code_agents.chat.chat_slash_agents import _handle_agent_ops

        with patch("code_agents.agent_system.agent_memory.load_memory", return_value=""):
            _handle_agent_ops("/memory", "", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "No memory" in out

    def test_memory_clear(self, capsys):
        from code_agents.chat.chat_slash_agents import _handle_agent_ops

        with patch("code_agents.agent_system.agent_memory.clear_memory", return_value=True):
            _handle_agent_ops("/memory", "clear", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "cleared" in out

    def test_memory_list(self, capsys):
        from code_agents.chat.chat_slash_agents import _handle_agent_ops

        memories = {"code-writer": 5, "code-reviewer": 3}
        with patch("code_agents.agent_system.agent_memory.list_memories", return_value=memories):
            _handle_agent_ops("/memory", "list", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "code-writer" in out
        assert "5 entries" in out

    def test_memory_list_empty(self, capsys):
        from code_agents.chat.chat_slash_agents import _handle_agent_ops

        with patch("code_agents.agent_system.agent_memory.list_memories", return_value={}):
            _handle_agent_ops("/memory", "list", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "No agent memories" in out

    def test_tokens_display(self, capsys):
        from code_agents.chat.chat_slash_agents import _handle_agent_ops

        mock_summary = {"messages": 10, "input_tokens": 5000, "output_tokens": 3000,
                        "total_tokens": 8000, "cost_usd": 0.05}
        mock_daily = {"messages": 20, "total_tokens": 15000, "cost_usd": 0.10}
        mock_monthly = {"messages": 100, "total_tokens": 80000, "cost_usd": 0.50}
        mock_yearly = {"messages": 500, "total_tokens": 400000, "cost_usd": 2.50}

        with patch("code_agents.core.token_tracker.get_session_summary", return_value=mock_summary):
            with patch("code_agents.core.token_tracker.get_daily_summary", return_value=mock_daily):
                with patch("code_agents.core.token_tracker.get_monthly_summary", return_value=mock_monthly):
                    with patch("code_agents.core.token_tracker.get_yearly_summary", return_value=mock_yearly):
                        with patch("code_agents.core.token_tracker.get_model_breakdown", return_value=[]):
                            _handle_agent_ops("/tokens", "", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "Token Usage" in out
        assert "5,000" in out
        assert "This session" in out
        assert "Today" in out
        assert "This month" in out

    def test_tokens_with_model_breakdown(self, capsys):
        from code_agents.chat.chat_slash_agents import _handle_agent_ops

        mock_summary = {"messages": 1, "input_tokens": 100, "output_tokens": 50,
                        "total_tokens": 150, "cost_usd": 0}
        mock_zero = {"messages": 0, "total_tokens": 0, "cost_usd": 0}
        breakdown = [{"backend": "cursor", "model": "Composer 2 Fast", "total_tokens": 150, "messages": 1}]

        with patch("code_agents.core.token_tracker.get_session_summary", return_value=mock_summary):
            with patch("code_agents.core.token_tracker.get_daily_summary", return_value=mock_zero):
                with patch("code_agents.core.token_tracker.get_monthly_summary", return_value=mock_zero):
                    with patch("code_agents.core.token_tracker.get_yearly_summary", return_value=mock_zero):
                        with patch("code_agents.core.token_tracker.get_model_breakdown", return_value=breakdown):
                            _handle_agent_ops("/tokens", "", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "cursor" in out
        assert "Composer 2 Fast" in out

    def test_rules_no_rules(self, capsys):
        from code_agents.chat.chat_slash_agents import _handle_agent_ops

        with patch("code_agents.agent_system.rules_loader.list_rules", return_value=[]):
            _handle_agent_ops("/rules", "", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "No rules" in out

    def test_rules_with_rules(self, capsys):
        from code_agents.chat.chat_slash_agents import _handle_agent_ops

        rules = [{"scope": "global", "target": "_global", "preview": "Always test", "path": "/rules/test.md"}]
        with patch("code_agents.agent_system.rules_loader.list_rules", return_value=rules):
            _handle_agent_ops("/rules", "", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "Always test" in out

    def test_stats_telemetry_disabled(self, capsys):
        from code_agents.chat.chat_slash_agents import _handle_agent_ops

        with patch("code_agents.observability.telemetry.is_enabled", return_value=False):
            _handle_agent_ops("/stats", "", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "disabled" in out

    def test_stats_telemetry_enabled(self, capsys):
        from code_agents.chat.chat_slash_agents import _handle_agent_ops

        summary = {"sessions": 5, "messages": 50, "tokens_in": 10000, "tokens_out": 5000,
                   "commands": 20, "errors": 1, "cost_estimate": 0.25}
        agent_usage = [{"agent": "code-writer", "messages": 30}]
        with patch("code_agents.observability.telemetry.is_enabled", return_value=True):
            with patch("code_agents.observability.telemetry.get_summary", return_value=summary):
                with patch("code_agents.observability.telemetry.get_agent_usage", return_value=agent_usage):
                    _handle_agent_ops("/stats", "", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "Stats" in out
        assert "code-writer" in out

    def test_stats_custom_days(self, capsys):
        from code_agents.chat.chat_slash_agents import _handle_agent_ops

        summary = {"sessions": 10, "messages": 100, "tokens_in": 20000, "tokens_out": 10000,
                   "commands": 40, "errors": 2, "cost_estimate": 0.50}
        with patch("code_agents.observability.telemetry.is_enabled", return_value=True):
            with patch("code_agents.observability.telemetry.get_summary", return_value=summary) as mock_get:
                with patch("code_agents.observability.telemetry.get_agent_usage", return_value=[]):
                    _handle_agent_ops("/stats", "7", _state(), "http://localhost:8000")
                    mock_get.assert_called_once_with(7)
        out = capsys.readouterr().out
        assert "last 7 days" in out

    def test_agents_not_handled(self):
        from code_agents.chat.chat_slash_agents import _handle_agent_ops

        result = _handle_agent_ops("/unknown", "", _state(), "http://localhost:8000")
        assert result == "_not_handled"


# ============================================================================
# chat_slash_analysis.py
# ============================================================================


class TestSlashAnalysis:
    """Tests for analysis slash commands."""

    def test_generate_tests_no_arg(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        result = _handle_analysis("/generate-tests", "", _state(), "http://localhost:8000")
        assert result is None
        out = capsys.readouterr().out
        assert "Usage" in out

    def test_generate_tests_file_not_found(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        result = _handle_analysis("/generate-tests", "/nonexistent/file.py", _state(), "http://localhost:8000")
        assert result is None
        out = capsys.readouterr().out
        assert "not found" in out

    def test_generate_tests_unsupported_type(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
            f.write(b"data")
            tmp = f.name
        try:
            mock_gen = MagicMock()
            mock_gen.language = "unknown"
            with patch("code_agents.generators.test_generator.TestGenerator", return_value=mock_gen):
                result = _handle_analysis("/generate-tests", tmp, _state(repo_path="/tmp"), "http://localhost:8000")
            assert result is None
            out = capsys.readouterr().out
            assert "Unsupported" in out
        finally:
            os.unlink(tmp)

    def test_generate_tests_success(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            f.write(b"def hello(): pass")
            tmp = f.name
        try:
            mock_gen = MagicMock()
            mock_gen.language = "python"
            mock_gen.framework = "pytest"
            mock_gen.analyze_source.return_value = {
                "classes": [], "functions": ["hello"], "dependencies": [],
            }
            mock_gen.generate_test_path.return_value = "tests/test_hello.py"
            mock_gen.build_prompt.return_value = "Generate tests for hello()"
            with patch("code_agents.generators.test_generator.TestGenerator", return_value=mock_gen):
                with patch("code_agents.generators.test_generator.format_analysis", return_value="  Analysis OK"):
                    state = _state(repo_path="/tmp")
                    result = _handle_analysis("/generate-tests", tmp, state, "http://localhost:8000")
            assert result == "exec_feedback"
            assert state["_exec_feedback"]["command"].startswith("/generate-tests")
        finally:
            os.unlink(tmp)

    def test_generate_tests_os_error(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as f:
            f.write(b"x")
            tmp = f.name
        try:
            with patch("code_agents.generators.test_generator.TestGenerator", side_effect=OSError("permission denied")):
                result = _handle_analysis("/generate-tests", tmp, _state(repo_path="/tmp"), "http://localhost:8000")
            assert result is None
            out = capsys.readouterr().out
            assert "Error" in out
        finally:
            os.unlink(tmp)

    def test_blame_no_arg(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        result = _handle_analysis("/blame", "", _state(), "http://localhost:8000")
        assert result is None
        out = capsys.readouterr().out
        assert "Usage" in out

    def test_blame_missing_line(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        result = _handle_analysis("/blame", "file.py", _state(), "http://localhost:8000")
        assert result is None

    def test_blame_invalid_line(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        result = _handle_analysis("/blame", "file.py abc", _state(), "http://localhost:8000")
        assert result is None
        out = capsys.readouterr().out
        assert "Invalid line" in out

    def test_blame_success(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        mock_investigator = MagicMock()
        mock_result = MagicMock()
        mock_investigator.investigate.return_value = mock_result
        state = _state()
        with patch("code_agents.git_ops.blame_investigator.BlameInvestigator", return_value=mock_investigator):
            with patch("code_agents.git_ops.blame_investigator.format_blame", return_value="Blame: author X"):
                result = _handle_analysis("/blame", "file.py 42", state, "http://localhost:8000")
        assert result == "exec_feedback"
        assert "42" in state["_exec_feedback"]["command"]

    def test_investigate_no_arg(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        result = _handle_analysis("/investigate", "", _state(), "http://localhost:8000")
        assert result is None
        out = capsys.readouterr().out
        assert "Usage" in out

    def test_investigate_success(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        mock_inv = MagicMock()
        mock_inv.investigate.return_value = MagicMock()
        state = _state()
        with patch("code_agents.observability.log_investigator.LogInvestigator", return_value=mock_inv):
            with patch("code_agents.observability.log_investigator.format_investigation", return_value="Root cause: X"):
                result = _handle_analysis("/investigate", "NullPointerException", state, "http://localhost:8000")
        assert result == "exec_feedback"

    def test_review_reply_no_comments(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        mock_resp = MagicMock()
        mock_resp.get_pr_comments.return_value = []
        with patch("code_agents.reviews.review_responder.ReviewResponder", return_value=mock_resp):
            result = _handle_analysis("/review-reply", "", _state(), "http://localhost:8000")
        assert result is None
        out = capsys.readouterr().out
        assert "No PR comments" in out

    def test_review_reply_with_comments(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        mock_comment = MagicMock()
        mock_comment.file_path = "src/main.py"
        mock_comment.line = 10
        mock_resp = MagicMock()
        mock_resp.get_pr_comments.return_value = [mock_comment]
        mock_resp.get_source_context.return_value = "context"
        mock_resp.build_reply_prompt.return_value = "Reply prompt"
        state = _state()
        with patch("code_agents.reviews.review_responder.ReviewResponder", return_value=mock_resp):
            with patch("code_agents.reviews.review_responder.format_review_comments", return_value="Comments:"):
                result = _handle_analysis("/review-reply", "42", state, "http://localhost:8000")
        assert result == "exec_feedback"

    def test_refactor_no_arg(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        result = _handle_analysis("/refactor", "", _state(), "http://localhost:8000")
        assert result is None
        out = capsys.readouterr().out
        assert "Usage" in out

    def test_refactor_success(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        mock_planner = MagicMock()
        mock_planner.analyze.return_value = MagicMock()
        with patch("code_agents.tools.refactor_planner.RefactorPlanner", return_value=mock_planner):
            with patch("code_agents.tools.refactor_planner.format_refactor_plan", return_value="Plan: extract method"):
                _handle_analysis("/refactor", "big_file.py", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "extract method" in out

    def test_deps_no_arg(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        result = _handle_analysis("/deps", "", _state(), "http://localhost:8000")
        assert result is None
        out = capsys.readouterr().out
        assert "Usage" in out

    def test_deps_not_found(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        mock_dg = MagicMock()
        mock_dg._resolve_name.return_value = []
        mock_dg.all_names = ["FooService", "BarRepo"]
        with patch("code_agents.analysis.dependency_graph.DependencyGraph", return_value=mock_dg):
            result = _handle_analysis("/deps", "NonExistent", _state(), "http://localhost:8000")
        assert result is None
        out = capsys.readouterr().out
        assert "not found" in out

    def test_deps_success(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        mock_dg = MagicMock()
        mock_dg._resolve_name.return_value = ["FooService"]
        mock_dg.format_tree.return_value = "FooService\n  -> BarRepo"
        with patch("code_agents.analysis.dependency_graph.DependencyGraph", return_value=mock_dg):
            _handle_analysis("/deps", "FooService", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "FooService" in out

    def test_config_diff_no_configs(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        mock_detector = MagicMock()
        mock_detector.load_configs.return_value = {}
        with patch("code_agents.analysis.config_drift.ConfigDriftDetector", return_value=mock_detector):
            _handle_analysis("/config-diff", "", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "No environment configs" in out

    def test_config_diff_two_envs(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        mock_detector = MagicMock()
        mock_detector.load_configs.return_value = {"dev": {}, "prod": {}}
        mock_detector.compare.return_value = MagicMock()
        with patch("code_agents.analysis.config_drift.ConfigDriftDetector", return_value=mock_detector):
            with patch("code_agents.analysis.config_drift.format_drift_report", return_value="Drift report"):
                with patch("code_agents.analysis.config_drift.DriftReport"):
                    _handle_analysis("/config-diff", "dev prod", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "Drift report" in out

    def test_config_diff_env_not_found(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        mock_detector = MagicMock()
        mock_detector.load_configs.return_value = {"dev": {}, "prod": {}}
        with patch("code_agents.analysis.config_drift.ConfigDriftDetector", return_value=mock_detector):
            _handle_analysis("/config-diff", "dev staging", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "not found" in out

    def test_config_diff_all(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        mock_detector = MagicMock()
        mock_detector.load_configs.return_value = {"dev": {}, "staging": {}, "prod": {}}
        mock_detector.compare_all.return_value = MagicMock()
        with patch("code_agents.analysis.config_drift.ConfigDriftDetector", return_value=mock_detector):
            with patch("code_agents.analysis.config_drift.format_drift_report", return_value="All drifts"):
                _handle_analysis("/config-diff", "", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "All drifts" in out

    def test_flags_no_flags(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        mock_report = MagicMock()
        mock_report.total_flags = 0
        mock_scanner = MagicMock()
        mock_scanner.scan.return_value = mock_report
        with patch("code_agents.analysis.feature_flags.FeatureFlagScanner", return_value=mock_scanner):
            _handle_analysis("/flags", "", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "No feature flags" in out

    def test_flags_with_flags(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        mock_report = MagicMock()
        mock_report.total_flags = 5
        mock_scanner = MagicMock()
        mock_scanner.scan.return_value = mock_report
        with patch("code_agents.analysis.feature_flags.FeatureFlagScanner", return_value=mock_scanner):
            with patch("code_agents.analysis.feature_flags.format_flag_report", return_value="5 flags found"):
                _handle_analysis("/flags", "", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "5 flags found" in out

    def test_flags_stale_only(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        mock_flag = MagicMock()
        mock_flag.name = "OLD_FLAG"
        mock_flag.file = ".env"
        mock_flag.line = 5
        mock_report = MagicMock()
        mock_report.total_flags = 3
        mock_report.stale_flags = [mock_flag]
        mock_scanner = MagicMock()
        mock_scanner.scan.return_value = mock_report
        with patch("code_agents.analysis.feature_flags.FeatureFlagScanner", return_value=mock_scanner):
            _handle_analysis("/flags", "--stale", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "OLD_FLAG" in out

    def test_flags_stale_none(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        mock_report = MagicMock()
        mock_report.total_flags = 3
        mock_report.stale_flags = []
        mock_scanner = MagicMock()
        mock_scanner.scan.return_value = mock_report
        with patch("code_agents.analysis.feature_flags.FeatureFlagScanner", return_value=mock_scanner):
            _handle_analysis("/flags", "--stale", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "No stale flags" in out

    def test_pr_preview_no_commits(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        mock_preview = MagicMock()
        mock_preview.get_commits.return_value = []
        with patch("code_agents.tools.pr_preview.PRPreview", return_value=mock_preview):
            _handle_analysis("/pr-preview", "", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "No commits" in out

    def test_pr_preview_with_commits(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        mock_preview = MagicMock()
        mock_preview.get_commits.return_value = ["abc123 Fix bug"]
        mock_preview.format_preview.return_value = "PR Preview: 1 commit"
        with patch("code_agents.tools.pr_preview.PRPreview", return_value=mock_preview):
            _handle_analysis("/pr-preview", "develop", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "PR Preview" in out

    def test_impact_no_arg(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        result = _handle_analysis("/impact", "", _state(), "http://localhost:8000")
        assert result is None
        out = capsys.readouterr().out
        assert "Usage" in out

    def test_impact_success(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        mock_analyzer = MagicMock()
        mock_analyzer.analyze.return_value = MagicMock()
        with patch("code_agents.analysis.impact_analysis.ImpactAnalyzer", return_value=mock_analyzer):
            with patch("code_agents.analysis.impact_analysis.format_impact_report", return_value="Impact: high"):
                _handle_analysis("/impact", "auth.py", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "Impact: high" in out

    def test_solve_no_arg(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        _handle_analysis("/solve", "", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "Usage" in out

    def test_solve_with_problem(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        mock_analysis = MagicMock()
        mock_analysis.recommended = None
        with patch("code_agents.knowledge.problem_solver.ProblemSolver") as MockSolver:
            MockSolver.return_value.analyze.return_value = mock_analysis
            with patch("code_agents.knowledge.problem_solver.format_problem_analysis", return_value="Steps: 1, 2, 3"):
                _handle_analysis("/solve", "deploy to staging", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "Steps" in out

    def test_solve_with_agent_recommendation(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        mock_rec = MagicMock()
        mock_rec.action_type = "agent"
        mock_rec.action = "jenkins-cicd"
        mock_analysis = MagicMock()
        mock_analysis.recommended = mock_rec
        with patch("code_agents.knowledge.problem_solver.ProblemSolver") as MockSolver:
            MockSolver.return_value.analyze.return_value = mock_analysis
            with patch("code_agents.knowledge.problem_solver.format_problem_analysis", return_value="Analysis"):
                _handle_analysis("/solve", "build project", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "jenkins-cicd" in out

    def test_solve_with_slash_recommendation(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        mock_rec = MagicMock()
        mock_rec.action_type = "slash"
        mock_rec.action = "/compile"
        mock_analysis = MagicMock()
        mock_analysis.recommended = mock_rec
        with patch("code_agents.knowledge.problem_solver.ProblemSolver") as MockSolver:
            MockSolver.return_value.analyze.return_value = mock_analysis
            with patch("code_agents.knowledge.problem_solver.format_problem_analysis", return_value="Analysis"):
                _handle_analysis("/solve", "check compilation", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "/compile" in out

    def test_solve_with_command_recommendation(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        mock_rec = MagicMock()
        mock_rec.action_type = "command"
        mock_rec.action = "mvn clean install"
        mock_analysis = MagicMock()
        mock_analysis.recommended = mock_rec
        with patch("code_agents.knowledge.problem_solver.ProblemSolver") as MockSolver:
            MockSolver.return_value.analyze.return_value = mock_analysis
            with patch("code_agents.knowledge.problem_solver.format_problem_analysis", return_value="Analysis"):
                _handle_analysis("/solve", "build java project", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "mvn clean install" in out

    def test_kb_no_arg(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        with patch("code_agents.knowledge.knowledge_base.KnowledgeBase"):
            _handle_analysis("/kb", "", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "Usage" in out

    def test_kb_search(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        mock_kb = MagicMock()
        mock_kb.search.return_value = [{"title": "Auth", "content": "OAuth flow"}]
        with patch("code_agents.knowledge.knowledge_base.KnowledgeBase", return_value=mock_kb):
            with patch("code_agents.knowledge.knowledge_base.format_kb_results", return_value="KB: Auth"):
                _handle_analysis("/kb", "authentication", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "KB: Auth" in out

    def test_kb_rebuild(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        mock_kb = MagicMock()
        mock_kb.rebuild_index.return_value = 42
        with patch("code_agents.knowledge.knowledge_base.KnowledgeBase", return_value=mock_kb):
            _handle_analysis("/kb", "--rebuild", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "42" in out

    def test_kb_stats(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        entry1 = MagicMock(source="code")
        entry2 = MagicMock(source="docs")
        mock_kb = MagicMock()
        mock_kb.entries = [entry1, entry2]
        with patch("code_agents.knowledge.knowledge_base.KnowledgeBase", return_value=mock_kb):
            _handle_analysis("/kb", "--stats", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "2 entries" in out

    def test_kb_stats_empty_rebuilds(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        mock_kb = MagicMock()
        mock_kb.entries = []
        with patch("code_agents.knowledge.knowledge_base.KnowledgeBase", return_value=mock_kb):
            _handle_analysis("/kb", "--stats", _state(), "http://localhost:8000")
        mock_kb.rebuild_index.assert_called_once()

    def test_qa_suite_success(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        mock_analysis = MagicMock()
        mock_analysis.language = "python"
        mock_analysis.framework = "fastapi"
        mock_analysis.endpoints = ["/api/v1/users"]
        mock_analysis.services = ["UserService"]
        mock_gen = MagicMock()
        mock_gen.analyze.return_value = mock_analysis
        mock_gen.generate_suite.return_value = ["/tests/test_users.py"]
        mock_gen.build_agent_prompt.return_value = "Generate QA tests"
        state = _state()
        with patch("code_agents.generators.qa_suite_generator.QASuiteGenerator", return_value=mock_gen):
            with patch("code_agents.generators.qa_suite_generator.format_analysis", return_value="Analysis OK"):
                result = _handle_analysis("/qa-suite", "", state, "http://localhost:8000")
        assert result == "exec_feedback"
        assert state["agent"] == "qa-regression"

    def test_qa_suite_no_language(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        mock_analysis = MagicMock()
        mock_analysis.language = ""
        mock_gen = MagicMock()
        mock_gen.analyze.return_value = mock_analysis
        with patch("code_agents.generators.qa_suite_generator.QASuiteGenerator", return_value=mock_gen):
            with patch("code_agents.generators.qa_suite_generator.format_analysis"):
                result = _handle_analysis("/qa-suite", "", _state(), "http://localhost:8000")
        assert result is None

    def test_qa_suite_no_generated(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        mock_analysis = MagicMock()
        mock_analysis.language = "java"
        mock_analysis.framework = "spring"
        mock_analysis.endpoints = []
        mock_analysis.services = []
        mock_gen = MagicMock()
        mock_gen.analyze.return_value = mock_analysis
        mock_gen.generate_suite.return_value = []
        with patch("code_agents.generators.qa_suite_generator.QASuiteGenerator", return_value=mock_gen):
            with patch("code_agents.generators.qa_suite_generator.format_analysis", return_value="OK"):
                result = _handle_analysis("/qa-suite", "", _state(), "http://localhost:8000")
        assert result is None
        out = capsys.readouterr().out
        assert "No test files generated" in out

    def test_qa_suite_error(self, capsys):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        with patch("code_agents.generators.qa_suite_generator.QASuiteGenerator", side_effect=Exception("scan failed")):
            result = _handle_analysis("/qa-suite", "", _state(), "http://localhost:8000")
        assert result is None
        out = capsys.readouterr().out
        assert "Error" in out

    def test_analysis_not_handled(self):
        from code_agents.chat.chat_slash_analysis import _handle_analysis

        result = _handle_analysis("/unknown", "", _state(), "http://localhost:8000")
        assert result == "_not_handled"


# ============================================================================
# chat_slash_tools.py
# ============================================================================


class TestSlashTools:
    """Tests for interactive tool slash commands."""

    def test_pair_start(self, capsys):
        from code_agents.chat.chat_slash_tools import _handle_tools

        mock_pm = MagicMock()
        mock_pm._file_hashes = {"a.py": "hash1"}
        state = _state()
        with patch("code_agents.domain.pair_mode.PairMode", return_value=mock_pm):
            _handle_tools("/pair", "", state, "http://localhost:8000")
        assert state["_pair_mode"] == mock_pm
        out = capsys.readouterr().out
        assert "ON" in out

    def test_pair_start_with_patterns(self, capsys):
        from code_agents.chat.chat_slash_tools import _handle_tools

        mock_pm = MagicMock()
        mock_pm._file_hashes = {}
        state = _state()
        with patch("code_agents.domain.pair_mode.PairMode", return_value=mock_pm) as MockPM:
            _handle_tools("/pair", "*.py,*.java", state, "http://localhost:8000")
            MockPM.assert_called_once_with(cwd="/tmp/test-repo", watch_patterns=["*.py", "*.java"])

    def test_pair_stop(self, capsys):
        from code_agents.chat.chat_slash_tools import _handle_tools

        mock_pm = MagicMock()
        state = _state(_pair_mode=mock_pm)
        _handle_tools("/pair", "off", state, "http://localhost:8000")
        assert state["_pair_mode"] is None
        mock_pm.stop.assert_called_once()
        out = capsys.readouterr().out
        assert "OFF" in out

    def test_pair_stop_not_active(self, capsys):
        from code_agents.chat.chat_slash_tools import _handle_tools

        state = _state(_pair_mode=None)
        _handle_tools("/pair", "stop", state, "http://localhost:8000")
        out = capsys.readouterr().out
        assert "not active" in out

    def test_pair_status_active(self, capsys):
        from code_agents.chat.chat_slash_tools import _handle_tools

        mock_pm = MagicMock()
        mock_pm.active = True
        mock_pm._file_hashes = {"a.py": "h1", "b.py": "h2"}
        mock_pm.watch_patterns = ["*.py"]
        state = _state(_pair_mode=mock_pm)
        _handle_tools("/pair", "status", state, "http://localhost:8000")
        out = capsys.readouterr().out
        assert "ACTIVE" in out
        assert "2 files" in out

    def test_pair_status_inactive(self, capsys):
        from code_agents.chat.chat_slash_tools import _handle_tools

        state = _state(_pair_mode=None)
        _handle_tools("/pair", "status", state, "http://localhost:8000")
        out = capsys.readouterr().out
        assert "inactive" in out

    def test_coverage_boost(self, capsys):
        from code_agents.chat.chat_slash_tools import _handle_tools

        mock_report = MagicMock()
        mock_report.prioritized_gaps = []
        mock_boost = MagicMock()
        mock_boost.run_pipeline.return_value = mock_report
        with patch("code_agents.tools.auto_coverage.AutoCoverageBoost", return_value=mock_boost):
            with patch("code_agents.tools.auto_coverage.format_coverage_report", return_value="Coverage: 75%"):
                _handle_tools("/coverage-boost", "", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "Coverage: 75%" in out

    def test_coverage_boost_with_target(self, capsys):
        from code_agents.chat.chat_slash_tools import _handle_tools

        mock_report = MagicMock()
        mock_report.prioritized_gaps = []
        mock_boost = MagicMock()
        mock_boost.run_pipeline.return_value = mock_report
        with patch("code_agents.tools.auto_coverage.AutoCoverageBoost", return_value=mock_boost) as MockBoost:
            with patch("code_agents.tools.auto_coverage.format_coverage_report", return_value="OK"):
                _handle_tools("/coverage-boost", "90", _state(), "http://localhost:8000")
            MockBoost.assert_called_once_with(cwd="/tmp/test-repo", target_pct=90.0)

    def test_coverage_boost_with_gaps(self, capsys):
        from code_agents.chat.chat_slash_tools import _handle_tools

        mock_report = MagicMock()
        mock_report.prioritized_gaps = [MagicMock()]
        mock_boost = MagicMock()
        mock_boost.run_pipeline.return_value = mock_report
        mock_boost.build_test_prompts.return_value = ["prompt1"]
        mock_boost.build_delegation_prompt.return_value = "Generate tests..."
        state = _state()
        with patch("code_agents.tools.auto_coverage.AutoCoverageBoost", return_value=mock_boost):
            with patch("code_agents.tools.auto_coverage.format_coverage_report", return_value="Gaps found"):
                result = _handle_tools("/coverage-boost", "", state, "http://localhost:8000")
        assert result == "exec_feedback"

    def test_mutate_no_arg(self, capsys):
        from code_agents.chat.chat_slash_tools import _handle_tools

        result = _handle_tools("/mutate", "", _state(), "http://localhost:8000")
        assert result is None
        out = capsys.readouterr().out
        assert "Usage" in out

    def test_mutate_success(self, capsys):
        from code_agents.chat.chat_slash_tools import _handle_tools

        mock_report = MagicMock()
        mock_tester = MagicMock()
        mock_tester.test_file.return_value = mock_report
        with patch("code_agents.testing.mutation_tester.MutationTester", return_value=mock_tester):
            with patch("code_agents.testing.mutation_tester.format_mutation_report", return_value="Mutations: 5 killed"):
                _handle_tools("/mutate", "auth.py", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "Mutations" in out

    def test_testdata_no_arg(self, capsys):
        from code_agents.chat.chat_slash_tools import _handle_tools

        mock_gen = MagicMock()
        mock_gen.detect_domain.return_value = ["payment"]
        mock_gen.generate.return_value = [{"amount": 100}]
        with patch("code_agents.generators.test_data_generator.TestDataGenerator", return_value=mock_gen):
            with patch("code_agents.generators.test_data_generator.format_test_data", return_value='[{"amount": 100}]'):
                _handle_tools("/testdata", "", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "100" in out

    def test_testdata_with_domain(self, capsys):
        from code_agents.chat.chat_slash_tools import _handle_tools

        mock_gen = MagicMock()
        mock_gen.generate.return_value = [{"name": "Test User"}]
        with patch("code_agents.generators.test_data_generator.TestDataGenerator", return_value=mock_gen):
            with patch("code_agents.generators.test_data_generator.format_test_data", return_value="data"):
                _handle_tools("/testdata", "user 3 yaml", _state(), "http://localhost:8000")

    def test_testdata_unknown_domain(self, capsys):
        from code_agents.chat.chat_slash_tools import _handle_tools

        mock_gen = MagicMock()
        mock_gen.generate.return_value = []
        with patch("code_agents.generators.test_data_generator.TestDataGenerator", return_value=mock_gen):
            _handle_tools("/testdata", "nonexistent", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "Unknown domain" in out

    def test_profile_no_arg(self, capsys):
        from code_agents.chat.chat_slash_tools import _handle_tools

        with patch("code_agents.observability.performance.PerformanceProfiler"):
            _handle_tools("/profile", "", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "Usage" in out

    def test_profile_discover(self, capsys):
        from code_agents.chat.chat_slash_tools import _handle_tools

        mock_profiler = MagicMock()
        mock_profiler.discover_endpoints.return_value = ["http://localhost:8000/health"]
        mock_profiler.profile_multiple.return_value = MagicMock()
        with patch("code_agents.observability.performance.PerformanceProfiler", return_value=mock_profiler):
            with patch("code_agents.observability.performance.format_profile_report", return_value="Profile OK"):
                _handle_tools("/profile", "--discover", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "Profile OK" in out

    def test_profile_discover_no_endpoints(self, capsys):
        from code_agents.chat.chat_slash_tools import _handle_tools

        mock_profiler = MagicMock()
        mock_profiler.discover_endpoints.return_value = []
        with patch("code_agents.observability.performance.PerformanceProfiler", return_value=mock_profiler):
            _handle_tools("/profile", "--discover", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "No endpoints" in out

    def test_profile_url(self, capsys):
        from code_agents.chat.chat_slash_tools import _handle_tools

        mock_result = MagicMock()
        mock_result.errors = 0
        mock_profiler = MagicMock()
        mock_profiler.profile_endpoint.return_value = mock_result
        with patch("code_agents.observability.performance.PerformanceProfiler", return_value=mock_profiler):
            with patch("code_agents.observability.performance.ProfileReport") as MockReport:
                with patch("code_agents.observability.performance.format_profile_report", return_value="OK"):
                    _handle_tools("/profile", "http://localhost:8000/health --iterations 5", _state(), "http://localhost:8000")
        mock_profiler.profile_endpoint.assert_called_once_with("http://localhost:8000/health", iterations=5)

    def test_compile_no_language(self, capsys):
        from code_agents.chat.chat_slash_tools import _handle_tools

        mock_checker = MagicMock()
        mock_checker.language = None
        with patch("code_agents.analysis.compile_check.CompileChecker", return_value=mock_checker):
            _handle_tools("/compile", "", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "No supported build system" in out

    def test_compile_success(self, capsys):
        from code_agents.chat.chat_slash_tools import _handle_tools

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.elapsed = 2.5
        mock_result.warnings = []
        mock_checker = MagicMock()
        mock_checker.language = "java"
        mock_checker.run_compile.return_value = mock_result
        with patch("code_agents.analysis.compile_check.CompileChecker", return_value=mock_checker):
            _handle_tools("/compile", "", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "successful" in out

    def test_compile_failure(self, capsys):
        from code_agents.chat.chat_slash_tools import _handle_tools

        mock_result = MagicMock()
        mock_result.success = False
        mock_result.elapsed = 1.0
        mock_result.errors = ["Error: line 5", "Error: line 10"]
        mock_checker = MagicMock()
        mock_checker.language = "java"
        mock_checker.run_compile.return_value = mock_result
        with patch("code_agents.analysis.compile_check.CompileChecker", return_value=mock_checker):
            _handle_tools("/compile", "", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "failed" in out

    def test_compile_with_warnings(self, capsys):
        from code_agents.chat.chat_slash_tools import _handle_tools

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.elapsed = 3.0
        mock_result.warnings = ["Deprecated API", "Unused import"]
        mock_checker = MagicMock()
        mock_checker.language = "java"
        mock_checker.run_compile.return_value = mock_result
        with patch("code_agents.analysis.compile_check.CompileChecker", return_value=mock_checker):
            _handle_tools("/compile", "", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "warning" in out

    def test_verify_on(self, capsys):
        from code_agents.chat.chat_slash_tools import _handle_tools

        mock_verifier = MagicMock()
        with patch("code_agents.core.response_verifier.get_verifier", return_value=mock_verifier):
            _handle_tools("/verify", "on", _state(), "http://localhost:8000")
        mock_verifier.toggle.assert_called_once_with(True)
        out = capsys.readouterr().out
        assert "ON" in out

    def test_verify_off(self, capsys):
        from code_agents.chat.chat_slash_tools import _handle_tools

        mock_verifier = MagicMock()
        with patch("code_agents.core.response_verifier.get_verifier", return_value=mock_verifier):
            _handle_tools("/verify", "off", _state(), "http://localhost:8000")
        mock_verifier.toggle.assert_called_once_with(False)
        out = capsys.readouterr().out
        assert "OFF" in out

    def test_verify_status(self, capsys):
        from code_agents.chat.chat_slash_tools import _handle_tools

        mock_verifier = MagicMock()
        mock_verifier.enabled = True
        with patch("code_agents.core.response_verifier.get_verifier", return_value=mock_verifier):
            _handle_tools("/verify", "status", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "ON" in out

    def test_verify_invalid_arg(self, capsys):
        from code_agents.chat.chat_slash_tools import _handle_tools

        with patch("code_agents.core.response_verifier.get_verifier"):
            _handle_tools("/verify", "maybe", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "Usage" in out

    def test_style_success(self, capsys):
        from code_agents.chat.chat_slash_tools import _handle_tools

        mock_profile = MagicMock()
        mock_profile.language = "python"
        mock_matcher = MagicMock()
        mock_matcher.analyze.return_value = mock_profile
        mock_matcher.format_display.return_value = "  indent: 4 spaces"
        mock_matcher.generate_style_prompt.return_value = "Use 4-space indent"
        with patch("code_agents.reviews.style_matcher.StyleMatcher", return_value=mock_matcher):
            _handle_tools("/style", "", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "Code Style" in out

    def test_style_unknown_language(self, capsys):
        from code_agents.chat.chat_slash_tools import _handle_tools

        mock_profile = MagicMock()
        mock_profile.language = "unknown"
        mock_matcher = MagicMock()
        mock_matcher.analyze.return_value = mock_profile
        with patch("code_agents.reviews.style_matcher.StyleMatcher", return_value=mock_matcher):
            _handle_tools("/style", "", _state(), "http://localhost:8000")
        out = capsys.readouterr().out
        assert "No source files" in out

    def test_tools_not_handled(self):
        from code_agents.chat.chat_slash_tools import _handle_tools

        result = _handle_tools("/unknown", "", _state(), "http://localhost:8000")
        assert result == "_not_handled"


# ============================================================================
# chat_server.py
# ============================================================================


class TestChatServer:
    """Tests for server communication functions."""

    def test_server_url_defaults(self):
        from code_agents.chat.chat_server import _server_url

        with patch.dict(os.environ, {"HOST": "127.0.0.1", "PORT": "8000"}, clear=False):
            assert _server_url() == "http://127.0.0.1:8000"

    def test_server_url_zero_host(self):
        from code_agents.chat.chat_server import _server_url

        with patch.dict(os.environ, {"HOST": "0.0.0.0", "PORT": "9000"}, clear=False):
            assert _server_url() == "http://127.0.0.1:9000"

    def test_check_server_healthy(self):
        from code_agents.chat.chat_server import _check_server

        mock_response = MagicMock()
        mock_response.status_code = 200
        with patch("httpx.get", return_value=mock_response):
            assert _check_server("http://localhost:8000") is True

    def test_check_server_unhealthy(self):
        from code_agents.chat.chat_server import _check_server

        mock_response = MagicMock()
        mock_response.status_code = 500
        with patch("httpx.get", return_value=mock_response):
            assert _check_server("http://localhost:8000") is False

    def test_check_server_connection_error(self):
        from code_agents.chat.chat_server import _check_server

        with patch("httpx.get", side_effect=Exception("refused")):
            assert _check_server("http://localhost:8000") is False

    def test_check_workspace_trust_claude_cli(self):
        from code_agents.chat.chat_server import _check_workspace_trust

        with patch.dict(os.environ, {"CODE_AGENTS_BACKEND": "claude-cli"}, clear=False):
            assert _check_workspace_trust("/tmp/repo") is True

    def test_check_workspace_trust_cursor_url(self):
        from code_agents.chat.chat_server import _check_workspace_trust

        with patch.dict(os.environ, {"CURSOR_API_URL": "http://cursor.local", "CODE_AGENTS_BACKEND": ""}, clear=False):
            assert _check_workspace_trust("/tmp/repo") is True

    def test_check_workspace_trust_anthropic_key(self):
        from code_agents.chat.chat_server import _check_workspace_trust

        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test", "CODE_AGENTS_BACKEND": "", "CURSOR_API_URL": ""}, clear=False):
            assert _check_workspace_trust("/tmp/repo") is True

    def test_get_agents_success(self):
        from code_agents.chat.chat_server import _get_agents

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {"name": "code-writer", "display_name": "Code Writer"},
                {"name": "code-reviewer", "display_name": "Code Reviewer"},
            ]
        }
        with patch("httpx.get", return_value=mock_response):
            agents = _get_agents("http://localhost:8000")
        assert agents == {"code-writer": "Code Writer", "code-reviewer": "Code Reviewer"}

    def test_get_agents_list_format(self):
        from code_agents.chat.chat_server import _get_agents

        mock_response = MagicMock()
        mock_response.json.return_value = [
            {"name": "code-writer", "display_name": "CW"},
        ]
        with patch("httpx.get", return_value=mock_response):
            agents = _get_agents("http://localhost:8000")
        assert agents == {"code-writer": "CW"}

    def test_get_agents_error(self):
        from code_agents.chat.chat_server import _get_agents

        with patch("httpx.get", side_effect=Exception("fail")):
            agents = _get_agents("http://localhost:8000")
        assert agents == {}

    def test_stream_chat_success(self):
        from code_agents.chat.chat_server import _stream_chat

        lines = [
            'data: {"choices":[{"delta":{"content":"Hello"}}]}',
            'data: {"session_id":"sid-1"}',
            'data: {"usage":{"input_tokens":10,"output_tokens":5}}',
            'data: {"duration_ms":500}',
            'data: {"choices":[{"delta":{"reasoning_content":"Thinking..."}}]}',
            'data: [DONE]',
        ]
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_lines.return_value = iter(lines)
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("httpx.stream", return_value=mock_response):
            pieces = list(_stream_chat("http://localhost:8000", "code-writer", [{"role": "user", "content": "hi"}]))
        types = [p[0] for p in pieces]
        assert "text" in types
        assert "session_id" in types
        assert "usage" in types
        assert "duration_ms" in types
        assert "reasoning" in types

    def test_stream_chat_http_error(self):
        from code_agents.chat.chat_server import _stream_chat

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("httpx.stream", return_value=mock_response):
            pieces = list(_stream_chat("http://localhost:8000", "code-writer", []))
        assert pieces[0] == ("error", "Server returned HTTP 500")

    def test_stream_chat_connect_error(self):
        from code_agents.chat.chat_server import _stream_chat
        import httpx

        with patch("httpx.stream", side_effect=httpx.ConnectError("refused")):
            pieces = list(_stream_chat("http://localhost:8000", "code-writer", []))
        assert pieces[0][0] == "error"
        assert "Cannot connect" in pieces[0][1]

    def test_stream_chat_timeout(self):
        from code_agents.chat.chat_server import _stream_chat
        import httpx

        with patch("httpx.stream", side_effect=httpx.ReadTimeout("timeout")):
            pieces = list(_stream_chat("http://localhost:8000", "code-writer", []))
        assert pieces[0][0] == "error"
        assert "timed out" in pieces[0][1]

    def test_stream_chat_skips_empty_lines(self):
        from code_agents.chat.chat_server import _stream_chat

        lines = [
            "",
            "not-data-prefix: something",
            'data: invalid-json',
            'data: {"choices":[]}',
            'data: [DONE]',
        ]
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_lines.return_value = iter(lines)
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("httpx.stream", return_value=mock_response):
            pieces = list(_stream_chat("http://localhost:8000", "code-writer", []))
        assert len(pieces) == 0

    def test_stream_chat_with_session_and_cwd(self):
        from code_agents.chat.chat_server import _stream_chat

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.iter_lines.return_value = iter(['data: [DONE]'])
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("httpx.stream", return_value=mock_response) as mock_stream:
            list(_stream_chat("http://localhost:8000", "code-writer", [], session_id="s1", cwd="/repo"))
            call_kwargs = mock_stream.call_args
            body = call_kwargs[1]["json"]
            assert body["session_id"] == "s1"
            assert body["cwd"] == "/repo"


# ============================================================================
# chat_context.py
# ============================================================================


class TestChatContext:
    """Tests for system context building."""

    def test_build_system_context_basic(self):
        from code_agents.chat.chat_context import _build_system_context

        with patch("code_agents.agent_system.rules_loader.load_rules", return_value=""):
            with patch("code_agents.agent_system.skill_loader.load_agent_skills", return_value={}):
                with patch("code_agents.agent_system.agent_memory.load_memory", return_value=""):
                    with patch("code_agents.integrations.mcp_client.get_servers_for_agent", return_value=[]):
                        with patch("code_agents.integrations.mcp_client.get_smart_mcp_context", return_value=""):
                            ctx = _build_system_context("/tmp/repo", "code-writer")
        assert "/tmp/repo" in ctx
        assert "repo" in ctx
        assert "Bash Tool" in ctx

    def test_build_system_context_with_rules(self):
        from code_agents.chat.chat_context import _build_system_context

        with patch("code_agents.agent_system.rules_loader.load_rules", return_value="Always write tests"):
            with patch("code_agents.agent_system.skill_loader.load_agent_skills", return_value={}):
                with patch("code_agents.agent_system.agent_memory.load_memory", return_value=""):
                    with patch("code_agents.integrations.mcp_client.get_servers_for_agent", return_value=[]):
                        with patch("code_agents.integrations.mcp_client.get_smart_mcp_context", return_value=""):
                            ctx = _build_system_context("/tmp/repo", "code-writer")
        assert "Always write tests" in ctx
        assert "Rules" in ctx

    def test_build_system_context_with_skills(self):
        from code_agents.chat.chat_context import _build_system_context

        mock_skill = MagicMock()
        mock_skill.name = "deploy"
        mock_skill.description = "Deploy workflow"
        all_skills = {"code-writer": [mock_skill]}
        with patch("code_agents.agent_system.rules_loader.load_rules", return_value=""):
            with patch("code_agents.agent_system.skill_loader.load_agent_skills", return_value=all_skills):
                with patch("code_agents.core.config.settings") as mock_settings:
                    mock_settings.agents_dir = "/agents"
                    with patch("code_agents.agent_system.agent_memory.load_memory", return_value=""):
                        with patch("code_agents.integrations.mcp_client.get_servers_for_agent", return_value=[]):
                            with patch("code_agents.integrations.mcp_client.get_smart_mcp_context", return_value=""):
                                ctx = _build_system_context("/tmp/repo", "code-writer")
        assert "deploy" in ctx
        assert "SKILL:name" in ctx

    def test_build_system_context_with_memory(self):
        from code_agents.chat.chat_context import _build_system_context

        with patch("code_agents.agent_system.rules_loader.load_rules", return_value=""):
            with patch("code_agents.agent_system.skill_loader.load_agent_skills", return_value={}):
                with patch("code_agents.agent_system.agent_memory.load_memory", return_value="- Learned X"):
                    with patch("code_agents.integrations.mcp_client.get_servers_for_agent", return_value=[]):
                        with patch("code_agents.integrations.mcp_client.get_smart_mcp_context", return_value=""):
                            ctx = _build_system_context("/tmp/repo", "code-writer")
        assert "Learned X" in ctx
        assert "Agent Memory" in ctx

    def test_build_system_context_with_user_role(self):
        from code_agents.chat.chat_context import _build_system_context

        with patch.dict(os.environ, {"CODE_AGENTS_USER_ROLE": "Senior Engineer"}):
            with patch("code_agents.agent_system.rules_loader.load_rules", return_value=""):
                with patch("code_agents.agent_system.skill_loader.load_agent_skills", return_value={}):
                    with patch("code_agents.agent_system.agent_memory.load_memory", return_value=""):
                        with patch("code_agents.integrations.mcp_client.get_servers_for_agent", return_value=[]):
                            with patch("code_agents.integrations.mcp_client.get_smart_mcp_context", return_value=""):
                                ctx = _build_system_context("/tmp/repo", "code-writer")
        assert "Senior Engineer" in ctx
        assert "concise" in ctx.lower() or "technical" in ctx.lower()

    def test_build_system_context_auto_pilot_gets_catalog(self):
        from code_agents.chat.chat_context import _build_system_context

        with patch("code_agents.agent_system.rules_loader.load_rules", return_value=""):
            with patch("code_agents.agent_system.skill_loader.load_agent_skills", return_value={}):
                with patch("code_agents.core.config.settings") as mock_settings:
                    mock_settings.agents_dir = "/agents"
                    with patch("code_agents.agent_system.skill_loader.get_all_agents_with_skills", return_value="Agent catalog..."):
                        with patch("code_agents.agent_system.agent_memory.load_memory", return_value=""):
                            with patch("code_agents.integrations.mcp_client.get_servers_for_agent", return_value=[]):
                                with patch("code_agents.integrations.mcp_client.get_smart_mcp_context", return_value=""):
                                    ctx = _build_system_context("/tmp/repo", "auto-pilot")
        assert "DELEGATE" in ctx
        assert "Sub-Agent Catalog" in ctx

    def test_build_system_context_superpower_gets_catalog(self):
        from code_agents.chat.chat_context import _build_system_context

        with patch("code_agents.agent_system.rules_loader.load_rules", return_value=""):
            with patch("code_agents.agent_system.skill_loader.load_agent_skills", return_value={}):
                with patch("code_agents.core.config.settings") as mock_settings:
                    mock_settings.agents_dir = "/agents"
                    with patch("code_agents.agent_system.skill_loader.get_all_agents_with_skills", return_value="All agents"):
                        with patch("code_agents.agent_system.agent_memory.load_memory", return_value=""):
                            with patch("code_agents.integrations.mcp_client.get_servers_for_agent", return_value=[]):
                                with patch("code_agents.integrations.mcp_client.get_smart_mcp_context", return_value=""):
                                    ctx = _build_system_context("/tmp/repo", "code-writer", superpower=True)
        assert "SUPERPOWER" in ctx

    def test_build_system_context_with_btw_messages(self):
        from code_agents.chat.chat_context import _build_system_context

        with patch("code_agents.agent_system.rules_loader.load_rules", return_value=""):
            with patch("code_agents.agent_system.skill_loader.load_agent_skills", return_value={}):
                with patch("code_agents.agent_system.agent_memory.load_memory", return_value=""):
                    with patch("code_agents.integrations.mcp_client.get_servers_for_agent", return_value=[]):
                        with patch("code_agents.integrations.mcp_client.get_smart_mcp_context", return_value=""):
                            ctx = _build_system_context(
                                "/tmp/repo", "code-writer",
                                btw_messages=["Use Python 3.12", "Prefer dataclasses"],
                            )
        assert "Python 3.12" in ctx
        assert "Prefer dataclasses" in ctx
        assert "USER UPDATES" in ctx

    def test_suggest_skills_matching(self, capsys):
        from code_agents.chat.chat_context import _suggest_skills

        mock_skill = MagicMock()
        mock_skill.name = "test-and-report"
        all_skills = {"code-writer": [mock_skill]}
        with patch("code_agents.agent_system.skill_loader.load_agent_skills", return_value=all_skills):
            _suggest_skills("run the tests", "code-writer", "/agents")
        out = capsys.readouterr().out
        assert "test-and-report" in out

    def test_suggest_skills_no_match(self, capsys):
        from code_agents.chat.chat_context import _suggest_skills

        all_skills = {"code-writer": []}
        with patch("code_agents.agent_system.skill_loader.load_agent_skills", return_value=all_skills):
            _suggest_skills("hello world", "code-writer", "/agents")
        out = capsys.readouterr().out
        assert out == ""

    def test_suggest_skills_skips_skill_invocation(self, capsys):
        from code_agents.chat.chat_context import _suggest_skills

        with patch("code_agents.agent_system.skill_loader.load_agent_skills", return_value={}):
            _suggest_skills("/code-writer:deploy", "code-writer", "/agents")
        out = capsys.readouterr().out
        assert out == ""


# ============================================================================
# chat_history.py
# ============================================================================


class TestChatHistory:
    """Tests for chat history persistence."""

    def test_make_title_short(self):
        from code_agents.chat.chat_history import _make_title

        assert _make_title("Fix the auth bug") == "Fix the auth bug"

    def test_make_title_long(self):
        from code_agents.chat.chat_history import _make_title

        long_text = "A" * 100
        title = _make_title(long_text, max_len=60)
        assert len(title) <= 60
        assert title.endswith("...")

    def test_make_title_multiline(self):
        from code_agents.chat.chat_history import _make_title

        assert _make_title("First line\nSecond line") == "First line"

    def test_make_title_empty(self):
        from code_agents.chat.chat_history import _make_title

        assert _make_title("") == "Untitled"

    def test_create_session(self):
        from code_agents.chat.chat_history import create_session

        with patch("code_agents.chat.chat_history._save"):
            session = create_session("code-writer", "/tmp/repo")
        assert session["agent"] == "code-writer"
        assert session["repo_path"] == "/tmp/repo"
        assert session["title"] == "New chat"
        assert len(session["messages"]) == 0
        assert "id" in session

    def test_create_session_with_id(self):
        from code_agents.chat.chat_history import create_session

        with patch("code_agents.chat.chat_history._save"):
            session = create_session("code-writer", "/tmp/repo", session_id="custom-id")
        assert session["id"] == "custom-id"

    def test_add_message_sets_title(self):
        from code_agents.chat.chat_history import add_message

        session = {
            "id": "test",
            "title": "New chat",
            "messages": [],
            "updated_at": 0,
        }
        with patch("code_agents.chat.chat_history._save"):
            add_message(session, "user", "Fix the login page")
        assert session["title"] == "Fix the login page"
        assert len(session["messages"]) == 1
        assert session["messages"][0]["role"] == "user"

    def test_add_message_keeps_existing_title(self):
        from code_agents.chat.chat_history import add_message

        session = {
            "id": "test",
            "title": "Already set",
            "messages": [],
            "updated_at": 0,
        }
        with patch("code_agents.chat.chat_history._save"):
            add_message(session, "user", "Something else")
        assert session["title"] == "Already set"

    def test_save_qa_pairs(self):
        from code_agents.chat.chat_history import save_qa_pairs, get_qa_pairs

        session = {"id": "test"}
        qa = [{"question": "Environment?", "answer": "production"}]
        with patch("code_agents.chat.chat_history._save"):
            save_qa_pairs(session, qa)
        assert get_qa_pairs(session) == qa

    def test_get_qa_pairs_empty(self):
        from code_agents.chat.chat_history import get_qa_pairs

        assert get_qa_pairs({}) == []

    def test_build_qa_context(self):
        from code_agents.chat.chat_history import build_qa_context

        session = {
            "qa_pairs": [
                {"question": "Environment?", "answer": "staging", "is_other": False},
                {"question": "Custom Q", "answer": "my answer", "is_other": True},
            ]
        }
        ctx = build_qa_context(session)
        assert "Environment?" in ctx
        assert "staging" in ctx
        assert "custom answer" in ctx

    def test_build_qa_context_empty(self):
        from code_agents.chat.chat_history import build_qa_context

        assert build_qa_context({}) == ""

    def test_delete_session_exists(self):
        from code_agents.chat.chat_history import delete_session

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_agents.chat.chat_history._ensure_dir", return_value=Path(tmpdir)):
                with patch("code_agents.chat.chat_history.HISTORY_DIR", Path(tmpdir)):
                    # Create a file
                    (Path(tmpdir) / "test-id.json").write_text("{}")
                    assert delete_session("test-id") is True
                    assert not (Path(tmpdir) / "test-id.json").exists()

    def test_delete_session_not_exists(self):
        from code_agents.chat.chat_history import delete_session

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("code_agents.chat.chat_history._ensure_dir", return_value=Path(tmpdir)):
                with patch("code_agents.chat.chat_history.HISTORY_DIR", Path(tmpdir)):
                    assert delete_session("nonexistent") is False

    def test_format_age(self):
        from code_agents.chat.chat_history import _format_age

        now = time.time()
        assert _format_age(now - 30) == "just now"
        assert "m ago" in _format_age(now - 300)
        assert "h ago" in _format_age(now - 7200)
        assert _format_age(now - 90000) == "yesterday"
        assert "d ago" in _format_age(now - 259200)

    def test_list_sessions_with_filter(self):
        from code_agents.chat.chat_history import list_sessions

        with tempfile.TemporaryDirectory() as tmpdir:
            session1 = {"id": "s1", "agent": "code-writer", "title": "Test",
                        "updated_at": time.time(), "repo_path": "/repo1", "messages": []}
            session2 = {"id": "s2", "agent": "code-reviewer", "title": "Review",
                        "updated_at": time.time(), "repo_path": "/repo2", "messages": []}
            (Path(tmpdir) / "s1.json").write_text(json.dumps(session1))
            (Path(tmpdir) / "s2.json").write_text(json.dumps(session2))

            with patch("code_agents.chat.chat_history._ensure_dir", return_value=Path(tmpdir)):
                with patch("code_agents.chat.chat_history.HISTORY_DIR", Path(tmpdir)):
                    result = list_sessions(repo_path="/repo1")
            assert len(result) == 1
            assert result[0]["id"] == "s1"

    def test_list_sessions_sorted(self):
        from code_agents.chat.chat_history import list_sessions

        with tempfile.TemporaryDirectory() as tmpdir:
            s1 = {"id": "old", "agent": "a", "title": "Old", "updated_at": 100, "repo_path": "", "messages": []}
            s2 = {"id": "new", "agent": "b", "title": "New", "updated_at": 200, "repo_path": "", "messages": []}
            (Path(tmpdir) / "old.json").write_text(json.dumps(s1))
            (Path(tmpdir) / "new.json").write_text(json.dumps(s2))

            with patch("code_agents.chat.chat_history._ensure_dir", return_value=Path(tmpdir)):
                with patch("code_agents.chat.chat_history.HISTORY_DIR", Path(tmpdir)):
                    result = list_sessions()
            assert result[0]["id"] == "new"

    def test_list_recent_sessions(self):
        from code_agents.chat.chat_history import list_recent_sessions

        with tempfile.TemporaryDirectory() as tmpdir:
            session = {"id": "s1", "agent": "code-writer", "title": "Test",
                       "messages": [{"role": "user", "content": "hi"}]}
            (Path(tmpdir) / "s1.json").write_text(json.dumps(session))

            with patch("code_agents.chat.chat_history._ensure_dir", return_value=Path(tmpdir)):
                with patch("code_agents.chat.chat_history.HISTORY_DIR", Path(tmpdir)):
                    result = list_recent_sessions()
            assert len(result) == 1
            assert result[0]["agent"] == "code-writer"

    def test_list_recent_sessions_skips_empty(self):
        from code_agents.chat.chat_history import list_recent_sessions

        with tempfile.TemporaryDirectory() as tmpdir:
            session = {"id": "s1", "agent": "code-writer", "title": "Empty", "messages": []}
            (Path(tmpdir) / "s1.json").write_text(json.dumps(session))

            with patch("code_agents.chat.chat_history._ensure_dir", return_value=Path(tmpdir)):
                with patch("code_agents.chat.chat_history.HISTORY_DIR", Path(tmpdir)):
                    result = list_recent_sessions()
            assert len(result) == 0


# ============================================================================
# chat_streaming.py
# ============================================================================


class TestChatStreaming:
    """Tests for streaming response handling."""

    def test_format_session_duration_seconds(self):
        from code_agents.chat.chat_streaming import _format_session_duration

        assert _format_session_duration(45) == "45s"

    def test_format_session_duration_minutes(self):
        from code_agents.chat.chat_streaming import _format_session_duration

        assert _format_session_duration(135) == "2m 15s"

    def test_format_session_duration_hours(self):
        from code_agents.chat.chat_streaming import _format_session_duration

        assert _format_session_duration(3723) == "1h 02m"

    def test_print_session_summary(self, capsys):
        from code_agents.chat.chat_streaming import _print_session_summary

        usage = {
            "total_tokens": 1000,
            "input_tokens": 600,
            "output_tokens": 400,
            "cache_read_tokens": 50,
            "cache_write_tokens": 20,
            "cost_usd": 0.01,
        }
        with patch("code_agents.core.token_tracker.get_session_summary", return_value=usage):
            _print_session_summary(
                session_start=time.monotonic() - 120,
                message_count=10,
                agent_name="code-writer",
                commands_run=5,
            )
        out = capsys.readouterr().out
        assert "Session Summary" in out
        assert "code-writer" in out
        assert "10" in out
        assert "5" in out
        assert "1,000" in out

    def test_print_session_summary_no_tokens(self, capsys):
        from code_agents.chat.chat_streaming import _print_session_summary

        usage = {
            "total_tokens": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
            "cost_usd": 0,
        }
        with patch("code_agents.core.token_tracker.get_session_summary", return_value=usage):
            _print_session_summary(
                session_start=time.monotonic() - 5,
                message_count=0,
                agent_name="code-writer",
                commands_run=0,
            )
        out = capsys.readouterr().out
        assert "Session Summary" in out


# ============================================================================
# chat_response.py
# ============================================================================


class TestChatResponse:
    """Tests for response processing."""

    def test_format_elapsed_seconds(self):
        from code_agents.chat.chat_response import _format_elapsed

        assert _format_elapsed(45.3) == "45s"

    def test_format_elapsed_minutes(self):
        from code_agents.chat.chat_response import _format_elapsed

        assert _format_elapsed(125) == "2m 05s"

    def test_handle_post_response_basic(self, capsys):
        from code_agents.chat.chat_response import handle_post_response

        state = _state()
        state["_response_start"] = time.monotonic() - 2
        with patch("code_agents.core.token_tracker.record_usage"):
            with patch("code_agents.core.confidence_scorer.get_scorer") as mock_scorer:
                mock_scorer.return_value.score_response.return_value = MagicMock(
                    should_delegate=False, score=4, suggested_agent=None
                )
                with patch("code_agents.core.response_verifier.get_verifier") as mock_verifier:
                    mock_verifier.return_value.should_verify.return_value = False
                    with patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[]):
                        with patch("code_agents.chat.chat_response._extract_delegations", return_value=[]):
                            with patch("code_agents.analysis.compile_check.is_auto_compile_enabled", return_value=False):
                                result, effective_agent = handle_post_response(
                                    full_response=["Hello world"],
                                    user_input="test",
                                    state=state,
                                    url="http://localhost:8000",
                                    current_agent="code-writer",
                                    system_context="system",
                                    cwd="/tmp",
                                )
        assert result == ["Hello world"]
        assert effective_agent == "code-writer"
        assert state["_last_output"] == "Hello world"

    def test_handle_post_response_saves_to_chat_session(self, capsys):
        from code_agents.chat.chat_response import handle_post_response

        session = {"id": "test", "messages": [], "_server_session_id": None}
        state = _state(_chat_session=session, session_id="sid-1")
        state["_response_start"] = time.monotonic()
        with patch("code_agents.core.token_tracker.record_usage"):
            with patch("code_agents.chat.chat_history.add_message") as mock_save:
                with patch("code_agents.core.confidence_scorer.get_scorer") as mock_scorer:
                    mock_scorer.return_value.score_response.return_value = MagicMock(
                        should_delegate=False, score=4, suggested_agent=None
                    )
                    with patch("code_agents.core.response_verifier.get_verifier") as mock_verifier:
                        mock_verifier.return_value.should_verify.return_value = False
                        with patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[]):
                            with patch("code_agents.chat.chat_response._extract_delegations", return_value=[]):
                                with patch("code_agents.analysis.compile_check.is_auto_compile_enabled", return_value=False):
                                    handle_post_response(
                                        full_response=["Response text"],
                                        user_input="test",
                                        state=state,
                                        url="http://localhost:8000",
                                        current_agent="code-writer",
                                        system_context="system",
                                        cwd="/tmp",
                                    )
        mock_save.assert_called_once()

    def test_handle_post_response_with_usage(self, capsys):
        from code_agents.chat.chat_response import handle_post_response

        state = _state()
        state["_response_start"] = time.monotonic()
        state["_last_usage"] = {"input_tokens": 100, "output_tokens": 50, "estimated": False}
        state["_last_duration_ms"] = 500
        with patch("code_agents.core.token_tracker.record_usage") as mock_record:
            with patch("code_agents.core.confidence_scorer.get_scorer") as mock_scorer:
                mock_scorer.return_value.score_response.return_value = MagicMock(
                    should_delegate=False, score=4, suggested_agent=None
                )
                with patch("code_agents.core.response_verifier.get_verifier") as mock_verifier:
                    mock_verifier.return_value.should_verify.return_value = False
                    with patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[]):
                        with patch("code_agents.chat.chat_response._extract_delegations", return_value=[]):
                            with patch("code_agents.analysis.compile_check.is_auto_compile_enabled", return_value=False):
                                handle_post_response(
                                    full_response=["text"],
                                    user_input="test",
                                    state=state,
                                    url="http://localhost:8000",
                                    current_agent="code-writer",
                                    system_context="system",
                                    cwd="/tmp",
                                )
        mock_record.assert_called_once()
        out = capsys.readouterr().out
        assert "100" in out  # token count

    def test_handle_post_response_low_confidence(self, capsys):
        from code_agents.chat.chat_response import handle_post_response

        state = _state()
        state["_response_start"] = time.monotonic()
        with patch("code_agents.core.token_tracker.record_usage"):
            with patch("code_agents.core.confidence_scorer.get_scorer") as mock_scorer:
                mock_conf = MagicMock()
                mock_conf.should_delegate = True
                mock_conf.score = 2
                mock_conf.suggested_agent = "code-reviewer"
                mock_scorer.return_value.score_response.return_value = mock_conf
                with patch("code_agents.core.response_verifier.get_verifier") as mock_verifier:
                    mock_verifier.return_value.should_verify.return_value = False
                    with patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[]):
                        with patch("code_agents.chat.chat_response._extract_delegations", return_value=[]):
                            with patch("code_agents.analysis.compile_check.is_auto_compile_enabled", return_value=False):
                                handle_post_response(
                                    full_response=["I'm not sure about this..."],
                                    user_input="complex question",
                                    state=state,
                                    url="http://localhost:8000",
                                    current_agent="code-writer",
                                    system_context="system",
                                    cwd="/tmp",
                                )
        out = capsys.readouterr().out
        assert "code-reviewer" in out

    def test_handle_post_response_empty(self, capsys):
        from code_agents.chat.chat_response import handle_post_response

        state = _state()
        state["_response_start"] = time.monotonic()
        with patch("code_agents.analysis.compile_check.is_auto_compile_enabled", return_value=False):
            result, _ = handle_post_response(
                full_response=[],
                user_input="",
                state=state,
                url="http://localhost:8000",
                current_agent="code-writer",
                system_context="system",
                cwd="/tmp",
            )
        assert result == []
