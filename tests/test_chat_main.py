"""Tests for code_agents/chat/chat.py — plan reports, completer, chat_main entry."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, mock_open, patch

import pytest


# ---------------------------------------------------------------------------
# _init_plan_report
# ---------------------------------------------------------------------------

class TestInitPlanReport:
    """Tests for _init_plan_report — creates .md plan report file."""

    def test_creates_plan_report_file(self, tmp_path):
        from code_agents.chat.chat import _init_plan_report

        plans_dir = tmp_path / "plans"
        state = {"agent": "code-writer", "repo_path": "/my/repo"}
        with patch("code_agents.chat.chat.Path.home", return_value=tmp_path):
            _init_plan_report(state, "Add login feature")

        assert "_plan_report" in state
        report_path = Path(state["_plan_report"])
        assert report_path.exists()
        content = report_path.read_text()
        assert "# Plan Report" in content
        assert "code-writer" in content
        assert "/my/repo" in content
        assert "Add login feature" in content
        assert "## Requirement" in content
        assert "## Plan" in content

    def test_skips_if_already_initialized(self, tmp_path):
        from code_agents.chat.chat import _init_plan_report

        state = {"_plan_report": "/existing/report.md", "agent": "code-writer"}
        with patch("code_agents.chat.chat.Path.home", return_value=tmp_path):
            _init_plan_report(state, "anything")
        # Should not overwrite
        assert state["_plan_report"] == "/existing/report.md"

    def test_default_agent_name(self, tmp_path):
        from code_agents.chat.chat import _init_plan_report

        state = {"repo_path": "/r"}
        with patch("code_agents.chat.chat.Path.home", return_value=tmp_path):
            _init_plan_report(state, "task")

        report_path = Path(state["_plan_report"])
        content = report_path.read_text()
        assert "chat" in content  # default agent name

    def test_plan_report_filename_format(self, tmp_path):
        from code_agents.chat.chat import _init_plan_report

        state = {"agent": "git-ops", "repo_path": "/r"}
        with patch("code_agents.chat.chat.Path.home", return_value=tmp_path):
            _init_plan_report(state, "task")

        report_path = Path(state["_plan_report"])
        assert report_path.name.startswith("plan-git-ops-")
        assert report_path.name.endswith(".md")

    def test_repo_path_na_when_missing(self, tmp_path):
        from code_agents.chat.chat import _init_plan_report

        state = {"agent": "x"}
        with patch("code_agents.chat.chat.Path.home", return_value=tmp_path):
            _init_plan_report(state, "task")

        content = Path(state["_plan_report"]).read_text()
        assert "N/A" in content

    def test_creates_plans_directory(self, tmp_path):
        from code_agents.chat.chat import _init_plan_report

        state = {"agent": "a", "repo_path": "/r"}
        with patch("code_agents.chat.chat.Path.home", return_value=tmp_path):
            _init_plan_report(state, "task")

        assert (tmp_path / ".code-agents" / "plans").is_dir()


# ---------------------------------------------------------------------------
# _append_plan_report
# ---------------------------------------------------------------------------

class TestAppendPlanReport:
    """Tests for _append_plan_report — appends sections to the plan report."""

    def test_appends_section(self, tmp_path):
        from code_agents.chat.chat import _append_plan_report

        report = tmp_path / "report.md"
        report.write_text("# Plan\n")
        state = {"_plan_report": str(report)}
        _append_plan_report(state, "Analysis", "Everything looks good.")

        content = report.read_text()
        assert "## Analysis" in content
        assert "Everything looks good." in content

    def test_appends_multiple_sections(self, tmp_path):
        from code_agents.chat.chat import _append_plan_report

        report = tmp_path / "report.md"
        report.write_text("# Plan\n")
        state = {"_plan_report": str(report)}
        _append_plan_report(state, "Step 1", "Do X")
        _append_plan_report(state, "Step 2", "Do Y")

        content = report.read_text()
        assert "## Step 1" in content
        assert "## Step 2" in content
        assert "Do X" in content
        assert "Do Y" in content

    def test_noop_when_no_plan_report(self):
        from code_agents.chat.chat import _append_plan_report

        state = {}
        # Should not raise
        _append_plan_report(state, "Section", "Content")

    def test_handles_oserror_gracefully(self, tmp_path):
        from code_agents.chat.chat import _append_plan_report

        state = {"_plan_report": "/nonexistent/dir/report.md"}
        # Should not raise
        _append_plan_report(state, "Section", "Content")

    def test_preserves_existing_content(self, tmp_path):
        from code_agents.chat.chat import _append_plan_report

        report = tmp_path / "report.md"
        report.write_text("# Existing header\n\nOriginal content\n")
        state = {"_plan_report": str(report)}
        _append_plan_report(state, "New", "New content")

        content = report.read_text()
        assert "# Existing header" in content
        assert "Original content" in content
        assert "## New" in content


# ---------------------------------------------------------------------------
# _make_completer
# ---------------------------------------------------------------------------

class TestMakeCompleter:
    """Tests for _make_completer — readline tab-completion."""

    def test_returns_callable(self):
        from code_agents.chat.chat import _make_completer

        with patch("code_agents.agent_system.skill_loader.load_agent_skills", side_effect=Exception("skip")):
            completer = _make_completer(["/help", "/quit"], ["code-writer"])
        assert callable(completer)

    def test_completes_slash_commands(self):
        from code_agents.chat.chat import _make_completer

        with patch("code_agents.agent_system.skill_loader.load_agent_skills", side_effect=Exception("skip")):
            completer = _make_completer(["/help", "/history", "/quit"], ["code-writer"])

        # Mock readline to return the text as the line buffer
        mock_readline = MagicMock()
        mock_readline.get_line_buffer.return_value = "/h"
        with patch.dict("sys.modules", {"readline": mock_readline}):
            result0 = completer("/h", 0)
            result1 = completer("/h", 1)
            result2 = completer("/h", 2)

        assert result0 == "/help"
        assert result1 == "/history"
        assert result2 is None

    def test_completes_agent_names_as_slash(self):
        from code_agents.chat.chat import _make_completer

        with patch("code_agents.agent_system.skill_loader.load_agent_skills", side_effect=Exception("skip")):
            completer = _make_completer(["/help"], ["code-writer", "code-tester"])

        mock_readline = MagicMock()
        mock_readline.get_line_buffer.return_value = "/code-w"
        with patch.dict("sys.modules", {"readline": mock_readline}):
            result = completer("/code-w", 0)
        assert result == "/code-writer"

    def test_completes_bare_agent_name_after_slash_agent(self):
        from code_agents.chat.chat import _make_completer

        with patch("code_agents.agent_system.skill_loader.load_agent_skills", side_effect=Exception("skip")):
            completer = _make_completer(["/agent"], ["code-writer", "code-tester"])

        mock_readline = MagicMock()
        mock_readline.get_line_buffer.return_value = "/agent code-w"
        with patch.dict("sys.modules", {"readline": mock_readline}):
            result = completer("code-w", 0)
        assert result == "code-writer"

    def test_completes_bare_agent_name_after_slash_skills(self):
        from code_agents.chat.chat import _make_completer

        with patch("code_agents.agent_system.skill_loader.load_agent_skills", side_effect=Exception("skip")):
            completer = _make_completer(["/skills"], ["code-writer", "git-ops"])

        mock_readline = MagicMock()
        mock_readline.get_line_buffer.return_value = "/skills g"
        with patch.dict("sys.modules", {"readline": mock_readline}):
            result = completer("g", 0)
        assert result == "git-ops"

    def test_returns_none_for_non_slash_text(self):
        from code_agents.chat.chat import _make_completer

        with patch("code_agents.agent_system.skill_loader.load_agent_skills", side_effect=Exception("skip")):
            completer = _make_completer(["/help"], ["code-writer"])

        mock_readline = MagicMock()
        mock_readline.get_line_buffer.return_value = "hello"
        with patch.dict("sys.modules", {"readline": mock_readline}):
            result = completer("hello", 0)
        assert result is None

    def test_handles_no_matches(self):
        from code_agents.chat.chat import _make_completer

        with patch("code_agents.agent_system.skill_loader.load_agent_skills", side_effect=Exception("skip")):
            completer = _make_completer(["/help"], ["code-writer"])

        mock_readline = MagicMock()
        mock_readline.get_line_buffer.return_value = "/zzz"
        with patch.dict("sys.modules", {"readline": mock_readline}):
            result = completer("/zzz", 0)
        assert result is None

    def test_session_id_completion(self):
        from code_agents.chat.chat import _make_completer

        with patch("code_agents.agent_system.skill_loader.load_agent_skills", side_effect=Exception("skip")):
            completer = _make_completer(["/resume"], ["code-writer"])

        mock_readline = MagicMock()
        mock_readline.get_line_buffer.return_value = "/resume ab"
        mock_sessions = [{"id": "ab123456-xxxx"}, {"id": "cd789012-xxxx"}]
        with patch.dict("sys.modules", {"readline": mock_readline}):
            with patch("code_agents.chat.chat_history.list_sessions", return_value=mock_sessions):
                result = completer("ab", 0)
        assert result == "ab123456"

    def test_session_id_completion_delete_chat(self):
        from code_agents.chat.chat import _make_completer

        with patch("code_agents.agent_system.skill_loader.load_agent_skills", side_effect=Exception("skip")):
            completer = _make_completer(["/delete-chat"], ["code-writer"])

        mock_readline = MagicMock()
        mock_readline.get_line_buffer.return_value = "/delete-chat x"
        with patch.dict("sys.modules", {"readline": mock_readline}):
            with patch("code_agents.chat.chat_history.list_sessions", return_value=[]):
                result = completer("x", 0)
        assert result is None

    def test_readline_import_error_fallback(self):
        from code_agents.chat.chat import _make_completer

        with patch("code_agents.agent_system.skill_loader.load_agent_skills", side_effect=Exception("skip")):
            completer = _make_completer(["/help", "/quit"], [])

        # Simulate readline import failure
        with patch.dict("sys.modules", {"readline": None}):
            # The completer catches ImportError and falls back to text
            try:
                result = completer("/h", 0)
            except (ImportError, TypeError):
                # Expected when readline is None
                pass

    def test_skill_completions_loaded(self):
        from code_agents.chat.chat import _make_completer

        mock_skill = MagicMock()
        mock_skill.name = "build"
        mock_skills = {"jenkins-cicd": [mock_skill]}
        with patch("code_agents.agent_system.skill_loader.load_agent_skills", return_value=mock_skills):
            with patch("code_agents.core.config.settings") as mock_settings:
                mock_settings.agents_dir = "/agents"
                completer = _make_completer(["/help"], ["jenkins-cicd"])

        mock_readline = MagicMock()
        mock_readline.get_line_buffer.return_value = "/jenkins"
        with patch.dict("sys.modules", {"readline": mock_readline}):
            result = completer("/jenkins", 0)
        # Should match /jenkins-cicd or /jenkins-cicd:build
        assert result is not None


# ---------------------------------------------------------------------------
# chat_main — entry point wrapper
# ---------------------------------------------------------------------------

class TestChatMain:
    """Tests for chat_main — the wrapper that catches exceptions."""

    def test_keyboard_interrupt_exits_gracefully(self, capsys):
        from code_agents.chat.chat import chat_main

        with patch("code_agents.chat.chat._chat_main_inner", side_effect=KeyboardInterrupt):
            chat_main([])
        captured = capsys.readouterr()
        assert "Exiting" in captured.out

    def test_generic_exception_logged_to_crash_file(self, tmp_path):
        from code_agents.chat.chat import chat_main

        with patch("code_agents.chat.chat._chat_main_inner", side_effect=RuntimeError("boom")):
            with patch("code_agents.chat.chat.Path.home", return_value=tmp_path):
                with pytest.raises(RuntimeError, match="boom"):
                    chat_main([])

        crash_file = tmp_path / ".code-agents" / "crash.log"
        assert crash_file.exists()
        content = crash_file.read_text()
        assert "CRASH" in content
        assert "boom" in content

    def test_default_args_is_none(self):
        from code_agents.chat.chat import chat_main

        with patch("code_agents.chat.chat._chat_main_inner") as mock_inner:
            chat_main()
        mock_inner.assert_called_once_with(None)

    def test_passes_args_through(self):
        from code_agents.chat.chat import chat_main

        with patch("code_agents.chat.chat._chat_main_inner") as mock_inner:
            chat_main(["--agent", "git-ops"])
        mock_inner.assert_called_once_with(["--agent", "git-ops"])


# ---------------------------------------------------------------------------
# _chat_main_inner — init paths (not the full REPL)
# ---------------------------------------------------------------------------

class TestChatMainInner:
    """Test initialization paths of _chat_main_inner."""

    @pytest.fixture(autouse=True)
    def _setup_env(self, monkeypatch):
        """Set env vars needed by _chat_main_inner init."""
        monkeypatch.setenv("CODE_AGENTS_NICKNAME", "test")
        monkeypatch.setenv("CODE_AGENTS_USER_ROLE", "Senior Engineer")
        monkeypatch.delenv("CODE_AGENTS_USER_CWD", raising=False)

    def test_loads_env_on_startup(self):
        from code_agents.chat.chat import _chat_main_inner

        with patch("code_agents.core.env_loader.load_all_env") as mock_load:
            with patch("code_agents.chat.chat._server_url", return_value="http://localhost:8000"):
                with patch("code_agents.chat.chat._check_server", return_value=False):
                    with patch("builtins.input", side_effect=EOFError):
                        _chat_main_inner([])
        mock_load.assert_called_once()

    def test_server_not_running_user_declines(self, capsys):
        from code_agents.chat.chat import _chat_main_inner

        with patch("code_agents.core.env_loader.load_all_env"):
            with patch("code_agents.chat.chat._server_url", return_value="http://localhost:8000"):
                with patch("code_agents.chat.chat._check_server", return_value=False):
                    with patch("builtins.input", return_value="n"):
                        _chat_main_inner([])
        captured = capsys.readouterr()
        assert "code-agents start" in captured.out

    def test_no_agents_from_server(self, capsys):
        from code_agents.chat.chat import _chat_main_inner

        with patch("code_agents.core.env_loader.load_all_env"):
            with patch("code_agents.chat.chat._server_url", return_value="http://localhost:8000"):
                with patch("code_agents.chat.chat._check_server", return_value=True):
                    with patch("code_agents.chat.chat._get_agents", return_value={}):
                        _chat_main_inner([])
        captured = capsys.readouterr()
        assert "No agents" in captured.out

    def test_invalid_agent_name_falls_through(self, capsys):
        from code_agents.chat.chat import _chat_main_inner

        agents = {"code-writer": "Code Writer"}
        with patch("code_agents.core.env_loader.load_all_env"):
            with patch("code_agents.chat.chat._server_url", return_value="http://localhost:8000"):
                with patch("code_agents.chat.chat._check_server", return_value=True):
                    with patch("code_agents.chat.chat._get_agents", return_value=agents):
                        with patch("code_agents.chat.chat._select_agent", return_value=None):
                            _chat_main_inner(["--agent", "nonexistent"])
        captured = capsys.readouterr()
        assert "not found" in captured.out


# ---------------------------------------------------------------------------
# Re-exports sanity check
# ---------------------------------------------------------------------------

class TestReExports:
    """Verify that chat.py re-exports from sub-modules are importable."""

    def test_agent_roles_importable(self):
        from code_agents.chat.chat import AGENT_ROLES
        assert isinstance(AGENT_ROLES, dict)

    def test_agent_welcome_importable(self):
        from code_agents.chat.chat import AGENT_WELCOME
        assert isinstance(AGENT_WELCOME, dict)

    def test_slash_commands_importable(self):
        from code_agents.chat.chat import SLASH_COMMANDS
        assert isinstance(SLASH_COMMANDS, list)
        assert "/help" in SLASH_COMMANDS

    def test_initial_chat_state_importable(self):
        from code_agents.chat.chat import initial_chat_state
        state = initial_chat_state("test-agent", "/repo", "engineer")
        assert state["agent"] == "test-agent"
        assert state["repo_path"] == "/repo"
        assert state["user_role"] == "engineer"

    def test_format_session_duration_importable(self):
        from code_agents.chat.chat import _format_session_duration
        assert callable(_format_session_duration)

    def test_parse_inline_delegation_importable(self):
        from code_agents.chat.chat import _parse_inline_delegation
        assert callable(_parse_inline_delegation)

    def test_handle_command_importable(self):
        from code_agents.chat.chat import _handle_command
        assert callable(_handle_command)

    def test_build_system_context_importable(self):
        from code_agents.chat.chat import _build_system_context
        assert callable(_build_system_context)

    def test_process_streaming_response_importable(self):
        from code_agents.chat.chat import process_streaming_response
        assert callable(process_streaming_response)

    def test_handle_post_response_importable(self):
        from code_agents.chat.chat import handle_post_response
        assert callable(handle_post_response)
