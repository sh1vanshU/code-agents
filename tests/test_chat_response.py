"""Tests for chat_response.py — process_streaming_response, handle_post_response, _format_elapsed."""

from __future__ import annotations

import sys
import time
import threading
from unittest.mock import patch, MagicMock, call, mock_open
from io import StringIO

import pytest


# ---------------------------------------------------------------------------
# _format_elapsed
# ---------------------------------------------------------------------------

class TestFormatElapsed:
    """Test _format_elapsed helper."""

    def test_seconds_only(self):
        from code_agents.chat.chat_response import _format_elapsed
        assert _format_elapsed(5) == "5s"
        assert _format_elapsed(0) == "0s"
        assert _format_elapsed(59) == "59s"

    def test_minutes_seconds(self):
        from code_agents.chat.chat_response import _format_elapsed
        assert _format_elapsed(60) == "1m 00s"
        assert _format_elapsed(125) == "2m 05s"
        assert _format_elapsed(3599) == "59m 59s"

    def test_fractional_seconds(self):
        from code_agents.chat.chat_response import _format_elapsed
        assert _format_elapsed(5.7) == "6s"
        assert _format_elapsed(0.3) == "0s"


# ---------------------------------------------------------------------------
# process_streaming_response
# ---------------------------------------------------------------------------

class TestProcessStreamingResponse:
    """Test process_streaming_response — the main streaming handler."""

    @patch("code_agents.chat.chat_response._stream_chat")
    @patch("code_agents.chat.chat_response.sys")
    @patch("code_agents.chat.chat_response.threading")
    def test_text_streaming_basic(self, mock_threading, mock_sys, mock_stream):
        """Text pieces collected, spinner started and stopped, got_text=True."""
        from code_agents.chat.chat_response import process_streaming_response

        mock_sys.stdout = MagicMock()
        mock_sys.stdout.isatty.return_value = True
        mock_thread = MagicMock()
        mock_threading.Thread.return_value = mock_thread
        mock_threading.Event.return_value = MagicMock()

        mock_stream.return_value = [
            ("text", "Hello "),
            ("text", "world"),
        ]

        state = {"repo_path": "/tmp"}
        got_text, parts, interrupted = process_streaming_response(
            "http://localhost:8000", "code-writer", [], state,
            _last_ctrl_c_ref=[0.0],
        )

        assert got_text is True
        assert parts == ["Hello ", "world"]
        assert interrupted is False
        # Spinner thread was started
        mock_thread.start.assert_called_once()

    @patch("code_agents.chat.chat_response._stream_chat")
    @patch("code_agents.chat.chat_response.sys")
    @patch("code_agents.chat.chat_response.threading")
    def test_no_text_pieces(self, mock_threading, mock_sys, mock_stream):
        """No text pieces -> got_text=False, empty parts."""
        from code_agents.chat.chat_response import process_streaming_response

        mock_sys.stdout = MagicMock()
        mock_thread = MagicMock()
        mock_threading.Thread.return_value = mock_thread
        mock_threading.Event.return_value = MagicMock()

        mock_stream.return_value = [
            ("reasoning", "thinking about it"),
        ]

        state = {}
        got_text, parts, interrupted = process_streaming_response(
            "http://localhost:8000", "code-writer", [], state,
            _last_ctrl_c_ref=[0.0],
        )

        assert got_text is False
        assert parts == []
        assert interrupted is False

    @patch("code_agents.chat.chat_response._stream_chat")
    @patch("code_agents.chat.chat_response.sys")
    @patch("code_agents.chat.chat_response.threading")
    def test_session_id_captured(self, mock_threading, mock_sys, mock_stream):
        """session_id piece updates state."""
        from code_agents.chat.chat_response import process_streaming_response

        mock_sys.stdout = MagicMock()
        mock_thread = MagicMock()
        mock_threading.Thread.return_value = mock_thread
        mock_threading.Event.return_value = MagicMock()

        mock_stream.return_value = [
            ("session_id", "sess-abc-123"),
        ]

        state = {}
        process_streaming_response(
            "http://localhost:8000", "code-writer", [], state,
            _last_ctrl_c_ref=[0.0],
        )

        assert state["session_id"] == "sess-abc-123"

    @patch("code_agents.chat.chat_response._stream_chat")
    @patch("code_agents.chat.chat_response.sys")
    @patch("code_agents.chat.chat_response.threading")
    def test_usage_captured(self, mock_threading, mock_sys, mock_stream):
        """usage piece updates state."""
        from code_agents.chat.chat_response import process_streaming_response

        mock_sys.stdout = MagicMock()
        mock_thread = MagicMock()
        mock_threading.Thread.return_value = mock_thread
        mock_threading.Event.return_value = MagicMock()

        usage_data = {"input_tokens": 100, "output_tokens": 50}
        mock_stream.return_value = [
            ("usage", usage_data),
        ]

        state = {}
        process_streaming_response(
            "http://localhost:8000", "code-writer", [], state,
            _last_ctrl_c_ref=[0.0],
        )

        assert state["_last_usage"] == usage_data

    @patch("code_agents.chat.chat_response._stream_chat")
    @patch("code_agents.chat.chat_response.sys")
    @patch("code_agents.chat.chat_response.threading")
    def test_duration_ms_captured(self, mock_threading, mock_sys, mock_stream):
        """duration_ms piece updates state."""
        from code_agents.chat.chat_response import process_streaming_response

        mock_sys.stdout = MagicMock()
        mock_thread = MagicMock()
        mock_threading.Thread.return_value = mock_thread
        mock_threading.Event.return_value = MagicMock()

        mock_stream.return_value = [
            ("duration_ms", 1234),
        ]

        state = {}
        process_streaming_response(
            "http://localhost:8000", "code-writer", [], state,
            _last_ctrl_c_ref=[0.0],
        )

        assert state["_last_duration_ms"] == 1234

    @patch("code_agents.chat.chat_response._stream_chat")
    @patch("code_agents.chat.chat_response.sys")
    @patch("code_agents.chat.chat_response.threading")
    def test_error_handling(self, mock_threading, mock_sys, mock_stream):
        """Error piece stops spinner and prints error."""
        from code_agents.chat.chat_response import process_streaming_response

        mock_sys.stdout = MagicMock()
        mock_stop_event = MagicMock()
        mock_stop_event.is_set.return_value = False
        mock_threading.Event.return_value = mock_stop_event
        mock_thread = MagicMock()
        mock_threading.Thread.return_value = mock_thread

        mock_stream.return_value = [
            ("error", "Something went wrong"),
        ]

        state = {}
        got_text, parts, interrupted = process_streaming_response(
            "http://localhost:8000", "code-writer", [], state,
            _last_ctrl_c_ref=[0.0],
        )

        assert got_text is False
        assert parts == []
        assert interrupted is False
        # Spinner should be stopped on error
        mock_stop_event.set.assert_called()

    @patch("code_agents.chat.chat_response._stream_chat")
    @patch("code_agents.chat.chat_response.sys")
    @patch("code_agents.chat.chat_response.threading")
    def test_reasoning_updates_spinner_label(self, mock_threading, mock_sys, mock_stream):
        """Reasoning pieces update the spinner label while spinner is running."""
        from code_agents.chat.chat_response import process_streaming_response

        mock_sys.stdout = MagicMock()
        mock_stop_event = MagicMock()
        mock_stop_event.is_set.return_value = False
        mock_threading.Event.return_value = mock_stop_event
        mock_thread = MagicMock()
        mock_threading.Thread.return_value = mock_thread

        mock_stream.return_value = [
            ("reasoning", "Analyzing code structure"),
        ]

        state = {}
        process_streaming_response(
            "http://localhost:8000", "code-writer", [], state,
            _last_ctrl_c_ref=[0.0],
        )
        # No crash — label updated internally

    @patch("code_agents.chat.chat_response._stream_chat")
    @patch("code_agents.chat.chat_response.sys")
    @patch("code_agents.chat.chat_response.threading")
    def test_reasoning_tool_result_displayed_dimmed(self, mock_threading, mock_sys, mock_stream):
        """Tool Result reasoning is written to stdout (dimmed)."""
        from code_agents.chat.chat_response import process_streaming_response

        mock_stdout = MagicMock()
        mock_sys.stdout = mock_stdout
        mock_stop_event = MagicMock()
        mock_stop_event.is_set.return_value = False
        mock_threading.Event.return_value = mock_stop_event
        mock_thread = MagicMock()
        mock_threading.Thread.return_value = mock_thread

        mock_stream.return_value = [
            ("reasoning", "**Tool Result**: success"),
        ]

        state = {}
        process_streaming_response(
            "http://localhost:8000", "code-writer", [], state,
            _last_ctrl_c_ref=[0.0],
        )

        # Should write tool result to stdout
        mock_stdout.write.assert_called()

    @patch("code_agents.chat.chat_response._stream_chat")
    @patch("code_agents.chat.chat_response.sys")
    @patch("code_agents.chat.chat_response.threading")
    def test_reasoning_after_spinner_stopped(self, mock_threading, mock_sys, mock_stream):
        """After spinner stops, reasoning shown as inline dim text (non-structured)."""
        from code_agents.chat.chat_response import process_streaming_response

        mock_stdout = MagicMock()
        mock_sys.stdout = mock_stdout
        mock_stop_event = MagicMock()
        # Spinner already stopped
        mock_stop_event.is_set.return_value = True
        mock_threading.Event.return_value = mock_stop_event
        mock_thread = MagicMock()
        mock_threading.Thread.return_value = mock_thread

        mock_stream.return_value = [
            ("reasoning", "simple reasoning text"),
        ]

        state = {}
        process_streaming_response(
            "http://localhost:8000", "code-writer", [], state,
            _last_ctrl_c_ref=[0.0],
        )

        # Should write inline dim text to stdout
        mock_stdout.write.assert_called()

    @patch("code_agents.chat.chat_response._stream_chat")
    @patch("code_agents.chat.chat_response.sys")
    @patch("code_agents.chat.chat_response.threading")
    def test_keyboard_interrupt_single(self, mock_threading, mock_sys, mock_stream):
        """Single Ctrl+C: sets interrupted flag, prints warning, does not raise."""
        from code_agents.chat.chat_response import process_streaming_response

        mock_sys.stdout = MagicMock()
        mock_stop_event = MagicMock()
        mock_stop_event.is_set.return_value = False
        mock_threading.Event.return_value = mock_stop_event
        mock_thread = MagicMock()
        mock_threading.Thread.return_value = mock_thread

        mock_stream.side_effect = KeyboardInterrupt()

        state = {}
        got_text, parts, interrupted = process_streaming_response(
            "http://localhost:8000", "code-writer", [], state,
            _last_ctrl_c_ref=[0.0],
        )

        assert interrupted is True
        assert got_text is False
        mock_stop_event.set.assert_called()

    @patch("code_agents.chat.chat_response._stream_chat")
    @patch("code_agents.chat.chat_response.sys")
    @patch("code_agents.chat.chat_response.threading")
    def test_keyboard_interrupt_returns_interrupted(self, mock_threading, mock_sys, mock_stream):
        """Ctrl+C during streaming: returns interrupted (no longer raises)."""
        from code_agents.chat.chat_response import process_streaming_response

        mock_sys.stdout = MagicMock()
        mock_stop_event = MagicMock()
        mock_stop_event.is_set.return_value = False
        mock_threading.Event.return_value = mock_stop_event
        mock_thread = MagicMock()
        mock_threading.Thread.return_value = mock_thread

        mock_stream.side_effect = KeyboardInterrupt()

        state = {}
        got_text, response, interrupted = process_streaming_response(
            "http://localhost:8000", "code-writer", [], state,
            _last_ctrl_c_ref=[time.time()],
        )
        assert interrupted is True

    @patch("code_agents.chat.chat_response._stream_chat")
    @patch("code_agents.chat.chat_response.sys")
    @patch("code_agents.chat.chat_response.threading")
    def test_response_start_stored_in_state(self, mock_threading, mock_sys, mock_stream):
        """_response_start is stored in state after streaming."""
        from code_agents.chat.chat_response import process_streaming_response

        mock_sys.stdout = MagicMock()
        mock_thread = MagicMock()
        mock_threading.Thread.return_value = mock_thread
        mock_threading.Event.return_value = MagicMock()
        mock_stream.return_value = []

        state = {}
        process_streaming_response(
            "http://localhost:8000", "code-writer", [], state,
            _last_ctrl_c_ref=[0.0],
        )

        assert "_response_start" in state
        assert isinstance(state["_response_start"], float)

    @patch("code_agents.chat.chat_response._stream_chat")
    @patch("code_agents.chat.chat_response.sys")
    @patch("code_agents.chat.chat_response.threading")
    def test_text_then_session_id(self, mock_threading, mock_sys, mock_stream):
        """Mixed pieces: text + session_id both handled."""
        from code_agents.chat.chat_response import process_streaming_response

        mock_sys.stdout = MagicMock()
        mock_sys.stdout.isatty.return_value = True
        mock_thread = MagicMock()
        mock_threading.Thread.return_value = mock_thread
        mock_threading.Event.return_value = MagicMock()

        mock_stream.return_value = [
            ("text", "some output"),
            ("session_id", "sess-xyz"),
            ("usage", {"input_tokens": 10, "output_tokens": 5}),
            ("duration_ms", 500),
        ]

        state = {"repo_path": "/tmp"}
        got_text, parts, interrupted = process_streaming_response(
            "http://localhost:8000", "code-writer", [], state,
            _last_ctrl_c_ref=[0.0],
        )

        assert got_text is True
        assert parts == ["some output"]
        assert state["session_id"] == "sess-xyz"
        assert state["_last_usage"]["input_tokens"] == 10
        assert state["_last_duration_ms"] == 500

    @patch("code_agents.chat.chat_response._stream_chat")
    @patch("code_agents.chat.chat_response.sys")
    @patch("code_agents.chat.chat_response.threading")
    def test_box_closed_on_success(self, mock_threading, mock_sys, mock_stream):
        """Response box is closed (footer written) when got_text and not interrupted."""
        from code_agents.chat.chat_response import process_streaming_response

        mock_stdout = MagicMock()
        mock_sys.stdout = mock_stdout
        mock_sys.stdout.isatty.return_value = True
        mock_thread = MagicMock()
        mock_threading.Thread.return_value = mock_thread
        mock_threading.Event.return_value = MagicMock()

        mock_stream.return_value = [("text", "response")]

        state = {"repo_path": "/tmp"}
        got_text, parts, interrupted = process_streaming_response(
            "http://localhost:8000", "code-writer", [], state,
            _last_ctrl_c_ref=[0.0],
        )

        assert got_text is True
        assert interrupted is False
        # Box footer written (contains box drawing char)
        write_calls = [str(c) for c in mock_stdout.write.call_args_list]
        footer_written = any("\u255a" in c for c in write_calls)
        assert footer_written

    @patch("code_agents.chat.chat_response._stream_chat")
    @patch("code_agents.chat.chat_response.sys")
    @patch("code_agents.chat.chat_response.threading")
    def test_box_not_closed_on_interrupt(self, mock_threading, mock_sys, mock_stream):
        """Response box is NOT closed when streaming was interrupted."""
        from code_agents.chat.chat_response import process_streaming_response

        mock_stdout = MagicMock()
        mock_sys.stdout = mock_stdout

        mock_stop_event = MagicMock()
        mock_stop_event.is_set.return_value = False
        mock_threading.Event.return_value = mock_stop_event
        mock_thread = MagicMock()
        mock_threading.Thread.return_value = mock_thread

        # Yield text then interrupt
        def _stream_then_interrupt(*args, **kwargs):
            yield ("text", "partial")
            raise KeyboardInterrupt()

        mock_stream.side_effect = _stream_then_interrupt

        state = {"repo_path": "/tmp"}
        got_text, parts, interrupted = process_streaming_response(
            "http://localhost:8000", "code-writer", [], state,
            _last_ctrl_c_ref=[0.0],
        )

        assert interrupted is True
        # Box footer should NOT be written for interrupted responses
        write_calls = [str(c) for c in mock_stdout.write.call_args_list]
        footer_written = any("\u255a" in c for c in write_calls)
        assert not footer_written

    @patch("code_agents.chat.chat_response._stream_chat")
    @patch("code_agents.chat.chat_response.sys")
    @patch("code_agents.chat.chat_response.threading")
    def test_empty_stream(self, mock_threading, mock_sys, mock_stream):
        """Empty stream returns got_text=False, empty parts."""
        from code_agents.chat.chat_response import process_streaming_response

        mock_sys.stdout = MagicMock()
        mock_thread = MagicMock()
        mock_threading.Thread.return_value = mock_thread
        mock_threading.Event.return_value = MagicMock()
        mock_stream.return_value = []

        state = {}
        got_text, parts, interrupted = process_streaming_response(
            "http://localhost:8000", "code-writer", [], state,
            _last_ctrl_c_ref=[0.0],
        )

        assert got_text is False
        assert parts == []
        assert interrupted is False

    @patch("code_agents.chat.chat_response._stream_chat")
    @patch("code_agents.chat.chat_response.sys")
    @patch("code_agents.chat.chat_response.threading")
    def test_reasoning_single_word(self, mock_threading, mock_sys, mock_stream):
        """Reasoning with a single word updates only the action label."""
        from code_agents.chat.chat_response import process_streaming_response

        mock_sys.stdout = MagicMock()
        mock_stop_event = MagicMock()
        mock_stop_event.is_set.return_value = False
        mock_threading.Event.return_value = mock_stop_event
        mock_thread = MagicMock()
        mock_threading.Thread.return_value = mock_thread

        mock_stream.return_value = [
            ("reasoning", "Analyzing"),
        ]

        state = {}
        # Should not crash with single-word reasoning
        process_streaming_response(
            "http://localhost:8000", "code-writer", [], state,
            _last_ctrl_c_ref=[0.0],
        )

    @patch("code_agents.chat.chat_response._stream_chat")
    @patch("code_agents.chat.chat_response.sys")
    @patch("code_agents.chat.chat_response.threading")
    def test_reasoning_tool_result_backtick(self, mock_threading, mock_sys, mock_stream):
        """Reasoning starting with ``` is treated as tool output."""
        from code_agents.chat.chat_response import process_streaming_response

        mock_stdout = MagicMock()
        mock_sys.stdout = mock_stdout
        mock_stop_event = MagicMock()
        mock_stop_event.is_set.return_value = False
        mock_threading.Event.return_value = mock_stop_event
        mock_thread = MagicMock()
        mock_threading.Thread.return_value = mock_thread

        mock_stream.return_value = [
            ("reasoning", "```\nsome code output\n```"),
        ]

        state = {}
        process_streaming_response(
            "http://localhost:8000", "code-writer", [], state,
            _last_ctrl_c_ref=[0.0],
        )

        # Tool output written to stdout
        mock_stdout.write.assert_called()


# ---------------------------------------------------------------------------
# handle_post_response
# ---------------------------------------------------------------------------

class TestHandlePostResponse:
    """Test handle_post_response — post-streaming processing."""

    def _make_state(self, **extra):
        """Create a minimal state dict."""
        base = {
            "repo_path": "/tmp/test-repo",
            "_response_start": time.monotonic(),
        }
        base.update(extra)
        return base

    @patch("code_agents.chat.chat_response._extract_delegations", return_value=[])
    @patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[])
    @patch("code_agents.chat.chat_response._time")
    def test_returns_full_response(self, mock_time, mock_skills, mock_deleg):
        """handle_post_response returns the full_response list."""
        from code_agents.chat.chat_response import handle_post_response

        mock_time.monotonic.return_value = 100.0

        state = self._make_state(_response_start=99.0)
        result, effective_agent = handle_post_response(
            ["hello", " world"], "test input", state,
            "http://localhost:8000", "code-writer", "system ctx", "/tmp",
        )

        assert result == ["hello", " world"]
        assert effective_agent == "code-writer"

    @patch("code_agents.chat.chat_response._extract_delegations", return_value=[])
    @patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[])
    @patch("code_agents.chat.chat_response._time")
    def test_stores_last_output(self, mock_time, mock_skills, mock_deleg):
        """full_text stored in state._last_output."""
        from code_agents.chat.chat_response import handle_post_response

        mock_time.monotonic.return_value = 100.0
        state = self._make_state(_response_start=99.0)
        handle_post_response(
            ["hello", " world"], "test input", state,
            "http://localhost:8000", "code-writer", "system ctx", "/tmp",
        )

        assert state["_last_output"] == "hello world"

    @patch("code_agents.chat.chat_response._extract_delegations", return_value=[])
    @patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[])
    @patch("code_agents.chat.chat_response._time")
    def test_empty_response(self, mock_time, mock_skills, mock_deleg):
        """Empty response list handled gracefully."""
        from code_agents.chat.chat_response import handle_post_response

        mock_time.monotonic.return_value = 100.0
        state = self._make_state(_response_start=99.0)
        result, effective_agent = handle_post_response(
            [], "test input", state,
            "http://localhost:8000", "code-writer", "system ctx", "/tmp",
        )

        assert result == []
        assert effective_agent == "code-writer"
        assert state["_last_output"] == ""

    @patch("code_agents.chat.chat_response._extract_delegations", return_value=[])
    @patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[])
    @patch("code_agents.chat.chat_response._time")
    @patch("code_agents.chat.chat_response.logger")
    def test_saves_to_chat_history(self, mock_logger, mock_time, mock_skills, mock_deleg):
        """Saves assistant message to chat session history."""
        from code_agents.chat.chat_response import handle_post_response

        mock_time.monotonic.return_value = 100.0
        mock_session = {"messages": []}
        state = self._make_state(_response_start=99.0, _chat_session=mock_session)

        with patch("code_agents.chat.chat_history.add_message") as mock_add:
            handle_post_response(
                ["response text"], "user question", state,
                "http://localhost:8000", "code-writer", "system ctx", "/tmp",
            )
            mock_add.assert_called_once_with(mock_session, "assistant", "response text")

    @patch("code_agents.chat.chat_response._extract_delegations", return_value=[])
    @patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[])
    @patch("code_agents.chat.chat_response._time")
    def test_appends_to_md_file(self, mock_time, mock_skills, mock_deleg):
        """Appends clean agent response to summary md file."""
        from code_agents.chat.chat_response import handle_post_response

        mock_time.monotonic.return_value = 100.0
        state = self._make_state(
            _response_start=99.0,
            _md_file="/tmp/summary.md",
        )

        m = mock_open()
        with patch("builtins.open", m):
            handle_post_response(
                ["clean response text"], "test input", state,
                "http://localhost:8000", "code-writer", "system ctx", "/tmp",
            )

        m.assert_called_with("/tmp/summary.md", "a")
        handle = m()
        handle.write.assert_called_once_with("clean response text\n\n---\n\n")

    @patch("code_agents.chat.chat_response._extract_delegations", return_value=[])
    @patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[])
    @patch("code_agents.chat.chat_response._time")
    def test_md_file_strips_bash_blocks(self, mock_time, mock_skills, mock_deleg):
        """Bash code blocks are stripped from the text appended to md file."""
        from code_agents.chat.chat_response import handle_post_response

        mock_time.monotonic.return_value = 100.0
        state = self._make_state(
            _response_start=99.0,
            _md_file="/tmp/summary.md",
        )

        m = mock_open()
        with patch("builtins.open", m):
            handle_post_response(
                ["before ```bash\nls -la\n``` after"], "test", state,
                "http://localhost:8000", "code-writer", "system ctx", "/tmp",
            )

        handle = m()
        # The write should not contain the bash block
        written = handle.write.call_args[0][0]
        assert "```bash" not in written
        assert "ls -la" not in written

    @patch("code_agents.chat.chat_response._extract_delegations", return_value=[])
    @patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[])
    @patch("code_agents.chat.chat_response._time")
    def test_md_file_os_error_ignored(self, mock_time, mock_skills, mock_deleg):
        """OSError when writing md file is silently ignored."""
        from code_agents.chat.chat_response import handle_post_response

        mock_time.monotonic.return_value = 100.0
        state = self._make_state(
            _response_start=99.0,
            _md_file="/nonexistent/path/summary.md",
        )

        with patch("builtins.open", side_effect=OSError("disk full")):
            # Should not raise
            handle_post_response(
                ["response"], "test", state,
                "http://localhost:8000", "code-writer", "system ctx", "/tmp",
            )

    @patch("code_agents.chat.chat_response._extract_delegations", return_value=[])
    @patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[])
    @patch("code_agents.chat.chat_response._time")
    def test_plan_mode_appends_to_plan_report(self, mock_time, mock_skills, mock_deleg):
        """In plan mode, appends to plan_report file."""
        from code_agents.chat.chat_response import handle_post_response

        mock_time.monotonic.return_value = 100.0
        mock_session = {"messages": []}
        state = self._make_state(
            _response_start=99.0,
            _plan_report="/tmp/plan.md",
            session_id="sess-123",
            _chat_session=mock_session,
        )

        m = mock_open()
        with patch("builtins.open", m), \
             patch("code_agents.chat.chat_input.get_current_mode", return_value="plan"), \
             patch("code_agents.chat.chat_history._save") as mock_persist, \
             patch("code_agents.chat.chat_history.add_message"):
            handle_post_response(
                ["plan output"], "plan something", state,
                "http://localhost:8000", "code-writer", "system ctx", "/tmp",
            )

        # Plan report written
        m.assert_any_call("/tmp/plan.md", "a")
        # Session persisted
        assert mock_session.get("_server_session_id") == "sess-123"

    @patch("code_agents.chat.chat_response._extract_delegations", return_value=[])
    @patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[])
    @patch("code_agents.chat.chat_response._time")
    def test_usage_stats_printed(self, mock_time, mock_skills, mock_deleg):
        """Usage stats are printed when available."""
        from code_agents.chat.chat_response import handle_post_response

        mock_time.monotonic.return_value = 100.0
        state = self._make_state(
            _response_start=99.0,
            _last_usage={"input_tokens": 100, "output_tokens": 50},
            _last_duration_ms=1500,
        )

        with patch("code_agents.core.token_tracker.record_usage") as mock_record:
            handle_post_response(
                ["some response"], "test input", state,
                "http://localhost:8000", "code-writer", "system ctx", "/tmp",
            )
            mock_record.assert_called_once()
            call_kwargs = mock_record.call_args
            assert call_kwargs[1]["agent"] == "code-writer"

        # Usage should be popped from state
        assert "_last_usage" not in state
        assert "_last_duration_ms" not in state

    @patch("code_agents.chat.chat_response._extract_delegations", return_value=[])
    @patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[])
    @patch("code_agents.chat.chat_response._time")
    def test_usage_estimated_flag(self, mock_time, mock_skills, mock_deleg):
        """Usage with estimated flag prints ~est suffix."""
        from code_agents.chat.chat_response import handle_post_response

        mock_time.monotonic.return_value = 100.0
        state = self._make_state(
            _response_start=99.0,
            _last_usage={"input_tokens": 100, "output_tokens": 50, "estimated": True},
        )

        with patch("code_agents.core.token_tracker.record_usage"):
            handle_post_response(
                ["response"], "test", state,
                "http://localhost:8000", "code-writer", "system ctx", "/tmp",
            )

    @patch("code_agents.chat.chat_response._extract_delegations", return_value=[])
    @patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[])
    @patch("code_agents.chat.chat_response._time")
    def test_no_usage_no_crash(self, mock_time, mock_skills, mock_deleg):
        """No usage data -> no crash, no record_usage call."""
        from code_agents.chat.chat_response import handle_post_response

        mock_time.monotonic.return_value = 100.0
        state = self._make_state(_response_start=99.0)

        handle_post_response(
            ["response"], "test", state,
            "http://localhost:8000", "code-writer", "system ctx", "/tmp",
        )

    @patch("code_agents.chat.chat_response._extract_delegations", return_value=[])
    @patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[])
    @patch("code_agents.chat.chat_response._time")
    def test_confidence_scoring_delegation_hint(self, mock_time, mock_skills, mock_deleg):
        """Low confidence triggers delegation hint."""
        from code_agents.chat.chat_response import handle_post_response

        mock_time.monotonic.return_value = 100.0
        state = self._make_state(_response_start=99.0)

        mock_score = MagicMock()
        mock_score.should_delegate = True
        mock_score.suggested_agent = "code-reviewer"
        mock_score.score = 2

        mock_scorer = MagicMock()
        mock_scorer.score_response.return_value = mock_score

        with patch("code_agents.core.confidence_scorer.get_scorer", return_value=mock_scorer), \
             patch("code_agents.chat.chat_welcome.AGENT_ROLES", {"code-reviewer": "Reviews code"}):
            handle_post_response(
                ["response text"], "fix this bug", state,
                "http://localhost:8000", "code-writer", "system ctx", "/tmp",
            )

        mock_scorer.score_response.assert_called_once_with("code-writer", "fix this bug", "response text")

    @patch("code_agents.chat.chat_response._extract_delegations", return_value=[])
    @patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[])
    @patch("code_agents.chat.chat_response._time")
    def test_confidence_scoring_no_delegation(self, mock_time, mock_skills, mock_deleg):
        """High confidence — no delegation hint shown."""
        from code_agents.chat.chat_response import handle_post_response

        mock_time.monotonic.return_value = 100.0
        state = self._make_state(_response_start=99.0)

        mock_score = MagicMock()
        mock_score.should_delegate = False
        mock_score.score = 5

        mock_scorer = MagicMock()
        mock_scorer.score_response.return_value = mock_score

        with patch("code_agents.core.confidence_scorer.get_scorer", return_value=mock_scorer):
            handle_post_response(
                ["good response"], "simple question", state,
                "http://localhost:8000", "code-writer", "system ctx", "/tmp",
            )

    @patch("code_agents.chat.chat_response._extract_delegations", return_value=[])
    @patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[])
    @patch("code_agents.chat.chat_response._time")
    def test_confidence_scoring_exception_ignored(self, mock_time, mock_skills, mock_deleg):
        """Exception in confidence scoring is silently ignored."""
        from code_agents.chat.chat_response import handle_post_response

        mock_time.monotonic.return_value = 100.0
        state = self._make_state(_response_start=99.0)

        with patch("code_agents.core.confidence_scorer.get_scorer", side_effect=Exception("broken")):
            # Should not raise
            handle_post_response(
                ["response"], "question", state,
                "http://localhost:8000", "code-writer", "system ctx", "/tmp",
            )

    @patch("code_agents.chat.chat_response._extract_delegations", return_value=[])
    @patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[])
    @patch("code_agents.chat.chat_response._time")
    def test_confidence_scoring_skipped_empty_input(self, mock_time, mock_skills, mock_deleg):
        """Confidence scoring skipped when user_input is blank."""
        from code_agents.chat.chat_response import handle_post_response

        mock_time.monotonic.return_value = 100.0
        state = self._make_state(_response_start=99.0)

        with patch("code_agents.core.confidence_scorer.get_scorer") as mock_get:
            handle_post_response(
                ["response"], "   ", state,
                "http://localhost:8000", "code-writer", "system ctx", "/tmp",
            )
            mock_get.assert_not_called()

    @patch("code_agents.chat.chat_response._extract_delegations", return_value=[])
    @patch("code_agents.chat.chat_response._time")
    def test_skill_extraction_loads_skill(self, mock_time, mock_deleg):
        """Skill requests in response trigger skill loading."""
        from code_agents.chat.chat_response import handle_post_response

        mock_time.monotonic.return_value = 100.0
        state = self._make_state(_response_start=99.0)

        mock_skill = MagicMock()
        mock_skill.full_name = "code-writer/deploy"
        mock_skill.name = "deploy"
        mock_skill.body = "## Deploy workflow\n1. Build\n2. Deploy"

        with patch("code_agents.chat.chat_response._extract_skill_requests", return_value=["deploy"]), \
             patch("code_agents.agent_system.skill_loader.get_skill", return_value=mock_skill) as mock_get_skill, \
             patch("code_agents.core.config.settings") as mock_settings, \
             patch("code_agents.chat.chat_response._stream_with_spinner", return_value=["skill output"]) as mock_spinner:
            mock_settings.agents_dir = "/tmp/agents"

            result, effective_agent = handle_post_response(
                ["[SKILL:deploy]"], "deploy the app", state,
                "http://localhost:8000", "code-writer", "system ctx", "/tmp",
            )

            mock_get_skill.assert_called_once_with("/tmp/agents", "code-writer", "deploy")
            mock_spinner.assert_called_once()
            assert result == ["skill output"]
            assert effective_agent == "code-writer"
            assert state["_last_output"] == "skill output"

    @patch("code_agents.chat.chat_response._extract_delegations", return_value=[])
    @patch("code_agents.chat.chat_response._time")
    def test_skill_extraction_no_skill_found(self, mock_time, mock_deleg):
        """Skill name not found -> no streaming, original response returned."""
        from code_agents.chat.chat_response import handle_post_response

        mock_time.monotonic.return_value = 100.0
        state = self._make_state(_response_start=99.0)

        with patch("code_agents.chat.chat_response._extract_skill_requests", return_value=["nonexistent"]), \
             patch("code_agents.agent_system.skill_loader.get_skill", return_value=None), \
             patch("code_agents.core.config.settings") as mock_settings:
            mock_settings.agents_dir = "/tmp/agents"

            result, effective_agent = handle_post_response(
                ["original response"], "test", state,
                "http://localhost:8000", "code-writer", "system ctx", "/tmp",
            )

            assert result == ["original response"]
            assert effective_agent == "code-writer"

    @patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[])
    @patch("code_agents.chat.chat_response._time")
    def test_delegation_roundtrip(self, mock_time, mock_skills):
        """Round-trip delegation: delegate result returns to source agent."""
        from code_agents.chat.chat_response import handle_post_response

        mock_time.monotonic.return_value = 100.0
        state = self._make_state(_response_start=99.0)

        # _stream_with_spinner called twice: first for delegate, then for source continuation
        with patch("code_agents.chat.chat_response._extract_delegations",
                    return_value=[("code-reviewer", "Review this code")]), \
             patch("code_agents.chat.chat_response._build_system_context", return_value="delegate ctx"), \
             patch("code_agents.chat.chat_response._stream_with_spinner",
                    side_effect=[["delegate output"], ["synthesized response"]]) as mock_spinner, \
             patch("code_agents.chat.chat_response.sys") as mock_sys:
            mock_sys.stdout.isatty.return_value = True

            result, effective_agent = handle_post_response(
                ["[DELEGATE:code-reviewer]Review this code"], "original question", state,
                "http://localhost:8000", "code-writer", "system ctx", "/tmp",
            )

            # Two calls: delegate execution + source agent continuation
            assert mock_spinner.call_count == 2
            # Result is from source agent's continuation, not delegate
            assert result == ["synthesized response"]
            # Effective agent stays as source (source synthesizes)
            assert effective_agent == "code-writer"
            assert state["_last_output"] == "synthesized response"

    @patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[])
    @patch("code_agents.chat.chat_response._time")
    def test_delegation_empty_prompt_skipped(self, mock_time, mock_skills):
        """Delegation with empty prompt is skipped."""
        from code_agents.chat.chat_response import handle_post_response

        mock_time.monotonic.return_value = 100.0
        state = self._make_state(_response_start=99.0)

        with patch("code_agents.chat.chat_response._extract_delegations",
                    return_value=[("code-reviewer", "   ")]), \
             patch("code_agents.chat.chat_response._stream_with_spinner") as mock_spinner:
            result, effective_agent = handle_post_response(
                ["original"], "test", state,
                "http://localhost:8000", "code-writer", "system ctx", "/tmp",
            )

            mock_spinner.assert_not_called()
            assert result == ["original"]
            assert effective_agent == "code-writer"

    @patch("code_agents.chat.chat_response._extract_delegations", return_value=[])
    @patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[])
    @patch("code_agents.chat.chat_response._time")
    def test_compile_check_success(self, mock_time, mock_skills, mock_deleg):
        """Auto-compile check runs and reports success."""
        from code_agents.chat.chat_response import handle_post_response

        mock_time.monotonic.return_value = 100.0
        state = self._make_state(_response_start=99.0)

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.warnings = []
        mock_result.elapsed = 1.5

        mock_checker = MagicMock()
        mock_checker.should_check.return_value = True
        mock_checker.run_compile.return_value = mock_result

        with patch("code_agents.analysis.compile_check.is_auto_compile_enabled", return_value=True), \
             patch("code_agents.analysis.compile_check.CompileChecker", return_value=mock_checker):
            handle_post_response(
                ["some code changes"], "fix this", state,
                "http://localhost:8000", "code-writer", "system ctx", "/tmp",
            )

        mock_checker.should_check.assert_called_once()
        mock_checker.run_compile.assert_called_once()

    @patch("code_agents.chat.chat_response._extract_delegations", return_value=[])
    @patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[])
    @patch("code_agents.chat.chat_response._time")
    def test_compile_check_failure(self, mock_time, mock_skills, mock_deleg):
        """Auto-compile check runs and reports failure with errors."""
        from code_agents.chat.chat_response import handle_post_response

        mock_time.monotonic.return_value = 100.0
        state = self._make_state(_response_start=99.0)

        mock_result = MagicMock()
        mock_result.success = False
        mock_result.errors = ["error1.py:10: syntax error", "error2.py:20: type error"]
        mock_result.elapsed = 2.0

        mock_checker = MagicMock()
        mock_checker.should_check.return_value = True
        mock_checker.run_compile.return_value = mock_result

        with patch("code_agents.analysis.compile_check.is_auto_compile_enabled", return_value=True), \
             patch("code_agents.analysis.compile_check.CompileChecker", return_value=mock_checker):
            handle_post_response(
                ["some code changes"], "fix this", state,
                "http://localhost:8000", "code-writer", "system ctx", "/tmp",
            )

        mock_checker.run_compile.assert_called_once()

    @patch("code_agents.chat.chat_response._extract_delegations", return_value=[])
    @patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[])
    @patch("code_agents.chat.chat_response._time")
    def test_compile_check_disabled(self, mock_time, mock_skills, mock_deleg):
        """Compile check skipped when disabled."""
        from code_agents.chat.chat_response import handle_post_response

        mock_time.monotonic.return_value = 100.0
        state = self._make_state(_response_start=99.0)

        with patch("code_agents.analysis.compile_check.is_auto_compile_enabled", return_value=False), \
             patch("code_agents.analysis.compile_check.CompileChecker") as mock_checker_cls:
            handle_post_response(
                ["response"], "test", state,
                "http://localhost:8000", "code-writer", "system ctx", "/tmp",
            )

            mock_checker_cls.assert_not_called()

    @patch("code_agents.chat.chat_response._extract_delegations", return_value=[])
    @patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[])
    @patch("code_agents.chat.chat_response._time")
    def test_compile_check_with_warnings(self, mock_time, mock_skills, mock_deleg):
        """Compile check success with warnings."""
        from code_agents.chat.chat_response import handle_post_response

        mock_time.monotonic.return_value = 100.0
        state = self._make_state(_response_start=99.0)

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.warnings = ["unused import", "deprecated function"]
        mock_result.elapsed = 0.5

        mock_checker = MagicMock()
        mock_checker.should_check.return_value = True
        mock_checker.run_compile.return_value = mock_result

        with patch("code_agents.analysis.compile_check.is_auto_compile_enabled", return_value=True), \
             patch("code_agents.analysis.compile_check.CompileChecker", return_value=mock_checker):
            handle_post_response(
                ["code"], "test", state,
                "http://localhost:8000", "code-writer", "system ctx", "/tmp",
            )

    @patch("code_agents.chat.chat_response._extract_delegations", return_value=[])
    @patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[])
    @patch("code_agents.chat.chat_response._time")
    def test_verification_lgtm(self, mock_time, mock_skills, mock_deleg):
        """Response verification — LGTM result."""
        from code_agents.chat.chat_response import handle_post_response

        mock_time.monotonic.return_value = 100.0
        state = self._make_state(_response_start=99.0)

        mock_verifier = MagicMock()
        mock_verifier.should_verify.return_value = True
        mock_verifier.build_verify_prompt.return_value = {"prompt": "verify this", "cache_key": None}
        mock_verifier.get_cached_result.return_value = None

        with patch("code_agents.core.response_verifier.get_verifier", return_value=mock_verifier), \
             patch("code_agents.chat.chat_response._build_system_context", return_value="ctx"), \
             patch("code_agents.chat.chat_response._stream_with_spinner", return_value=["LGTM - no issues found"]):
            handle_post_response(
                ["code response"], "write a function", state,
                "http://localhost:8000", "code-writer", "system ctx", "/tmp",
            )

        mock_verifier.should_verify.assert_called_once()

    @patch("code_agents.chat.chat_response._extract_delegations", return_value=[])
    @patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[])
    @patch("code_agents.chat.chat_response._time")
    def test_verification_with_review_notes(self, mock_time, mock_skills, mock_deleg):
        """Response verification — review notes (not LGTM)."""
        from code_agents.chat.chat_response import handle_post_response

        mock_time.monotonic.return_value = 100.0
        state = self._make_state(_response_start=99.0)

        mock_verifier = MagicMock()
        mock_verifier.should_verify.return_value = True
        mock_verifier.build_verify_prompt.return_value = {"prompt": "verify", "cache_key": "k1"}
        mock_verifier.get_cached_result.return_value = None

        with patch("code_agents.core.response_verifier.get_verifier", return_value=mock_verifier), \
             patch("code_agents.chat.chat_response._build_system_context", return_value="ctx"), \
             patch("code_agents.chat.chat_response._stream_with_spinner",
                   return_value=["- Missing error handling\n- No tests"]):
            handle_post_response(
                ["code response"], "write a function", state,
                "http://localhost:8000", "code-writer", "system ctx", "/tmp",
            )

        # Cache the result
        mock_verifier.cache_result.assert_called_once()

    @patch("code_agents.chat.chat_response._extract_delegations", return_value=[])
    @patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[])
    @patch("code_agents.chat.chat_response._time")
    def test_verification_cached_result(self, mock_time, mock_skills, mock_deleg):
        """Response verification — uses cached result if available."""
        from code_agents.chat.chat_response import handle_post_response

        mock_time.monotonic.return_value = 100.0
        state = self._make_state(_response_start=99.0)

        mock_verifier = MagicMock()
        mock_verifier.should_verify.return_value = True
        mock_verifier.build_verify_prompt.return_value = {"prompt": "verify", "cache_key": "k1"}
        mock_verifier.get_cached_result.return_value = "LGTM"

        with patch("code_agents.core.response_verifier.get_verifier", return_value=mock_verifier), \
             patch("code_agents.chat.chat_response._stream_with_spinner") as mock_spinner:
            handle_post_response(
                ["code response"], "write a function", state,
                "http://localhost:8000", "code-writer", "system ctx", "/tmp",
            )

        # Should NOT call _stream_with_spinner since result was cached
        mock_spinner.assert_not_called()

    @patch("code_agents.chat.chat_response._extract_delegations", return_value=[])
    @patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[])
    @patch("code_agents.chat.chat_response._time")
    def test_verification_exception_ignored(self, mock_time, mock_skills, mock_deleg):
        """Exception in response verification is silently ignored."""
        from code_agents.chat.chat_response import handle_post_response

        mock_time.monotonic.return_value = 100.0
        state = self._make_state(_response_start=99.0)

        with patch("code_agents.core.response_verifier.get_verifier", side_effect=Exception("broken")):
            # Should not raise
            handle_post_response(
                ["response"], "question", state,
                "http://localhost:8000", "code-writer", "system ctx", "/tmp",
            )

    @patch("code_agents.chat.chat_response._extract_delegations", return_value=[])
    @patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[])
    @patch("code_agents.chat.chat_response._time")
    def test_skill_saves_to_chat_history(self, mock_time, mock_skills, mock_deleg):
        """Skill response is saved to chat history."""
        from code_agents.chat.chat_response import handle_post_response

        mock_time.monotonic.return_value = 100.0
        mock_session = {"messages": []}
        state = self._make_state(_response_start=99.0, _chat_session=mock_session)

        mock_skill = MagicMock()
        mock_skill.full_name = "code-writer/deploy"
        mock_skill.name = "deploy"
        mock_skill.body = "## Deploy"

        with patch("code_agents.chat.chat_response._extract_skill_requests", return_value=["deploy"]), \
             patch("code_agents.agent_system.skill_loader.get_skill", return_value=mock_skill), \
             patch("code_agents.core.config.settings") as mock_settings, \
             patch("code_agents.chat.chat_response._stream_with_spinner", return_value=["skill result"]), \
             patch("code_agents.chat.chat_history.add_message") as mock_add:
            mock_settings.agents_dir = "/tmp/agents"

            handle_post_response(
                ["[SKILL:deploy]"], "deploy", state,
                "http://localhost:8000", "code-writer", "system ctx", "/tmp",
            )

            # Called twice: once for initial response, once for skill response
            assert mock_add.call_count == 2

    @patch("code_agents.chat.chat_response._extract_delegations", return_value=[])
    @patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[])
    @patch("code_agents.chat.chat_response._time")
    def test_long_response_collapse(self, mock_time, mock_skills, mock_deleg):
        """Long responses (>25 lines) trigger collapse/expand UI."""
        from code_agents.chat.chat_response import handle_post_response

        mock_time.monotonic.return_value = 100.0
        state = self._make_state(_response_start=99.0)

        # 30-line response
        long_text = "\n".join([f"line {i}" for i in range(30)])

        with patch("builtins.input", return_value=""):
            result, effective_agent = handle_post_response(
                [long_text], "test", state,
                "http://localhost:8000", "code-writer", "system ctx", "/tmp",
            )

        assert result == [long_text]
        assert effective_agent == "code-writer"

    @patch("code_agents.chat.chat_response._extract_delegations", return_value=[])
    @patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[])
    @patch("code_agents.chat.chat_response._time")
    def test_long_response_collapse_eof_error(self, mock_time, mock_skills, mock_deleg):
        """EOFError during collapse/expand is handled gracefully."""
        from code_agents.chat.chat_response import handle_post_response

        mock_time.monotonic.return_value = 100.0
        state = self._make_state(_response_start=99.0)

        long_text = "\n".join([f"line {i}" for i in range(30)])

        with patch("builtins.input", side_effect=EOFError):
            handle_post_response(
                [long_text], "test", state,
                "http://localhost:8000", "code-writer", "system ctx", "/tmp",
            )

    @patch("code_agents.chat.chat_response._extract_delegations", return_value=[])
    @patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[])
    @patch("code_agents.chat.chat_response._time")
    def test_short_response_no_collapse(self, mock_time, mock_skills, mock_deleg):
        """Short responses (<= 25 lines) do not trigger collapse UI."""
        from code_agents.chat.chat_response import handle_post_response

        mock_time.monotonic.return_value = 100.0
        state = self._make_state(_response_start=99.0)

        short_text = "\n".join([f"line {i}" for i in range(5)])

        with patch("builtins.input") as mock_input:
            handle_post_response(
                [short_text], "test", state,
                "http://localhost:8000", "code-writer", "system ctx", "/tmp",
            )

            mock_input.assert_not_called()

    @patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[])
    @patch("code_agents.chat.chat_response._time")
    def test_delegation_roundtrip_with_known_agent(self, mock_time, mock_skills):
        """Round-trip delegation to a known agent returns to source."""
        from code_agents.chat.chat_response import handle_post_response

        mock_time.monotonic.return_value = 100.0
        state = self._make_state(_response_start=99.0)

        with patch("code_agents.chat.chat_response._extract_delegations",
                    return_value=[("code-tester", "write tests for this")]), \
             patch("code_agents.chat.chat_response._build_system_context", return_value="ctx"), \
             patch("code_agents.chat.chat_response._stream_with_spinner",
                    side_effect=[["test results"], ["final synthesis"]]), \
             patch("code_agents.chat.chat_response.sys") as mock_sys:
            mock_sys.stdout.isatty.return_value = True

            result, effective_agent = handle_post_response(
                ["[DELEGATE:code-tester]write tests for this"], "test", state,
                "http://localhost:8000", "code-writer", "system ctx", "/tmp",
            )

            # Source agent (code-writer) stays in control
            assert result == ["final synthesis"]
            assert effective_agent == "code-writer"

    @patch("code_agents.chat.chat_response._extract_delegations", return_value=[])
    @patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[])
    @patch("code_agents.chat.chat_response._time")
    def test_compile_check_many_errors_truncated(self, mock_time, mock_skills, mock_deleg):
        """Compile errors beyond 5 are truncated with '... and N more'."""
        from code_agents.chat.chat_response import handle_post_response

        mock_time.monotonic.return_value = 100.0
        state = self._make_state(_response_start=99.0)

        mock_result = MagicMock()
        mock_result.success = False
        mock_result.errors = [f"error{i}.py: line {i}" for i in range(10)]
        mock_result.elapsed = 3.0

        mock_checker = MagicMock()
        mock_checker.should_check.return_value = True
        mock_checker.run_compile.return_value = mock_result

        with patch("code_agents.analysis.compile_check.is_auto_compile_enabled", return_value=True), \
             patch("code_agents.analysis.compile_check.CompileChecker", return_value=mock_checker):
            handle_post_response(
                ["code"], "test", state,
                "http://localhost:8000", "code-writer", "system ctx", "/tmp",
            )

    @patch("code_agents.chat.chat_response._extract_delegations", return_value=[])
    @patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[])
    @patch("code_agents.chat.chat_response._time")
    def test_none_full_response(self, mock_time, mock_skills, mock_deleg):
        """None items in full_response handled."""
        from code_agents.chat.chat_response import handle_post_response

        mock_time.monotonic.return_value = 100.0
        state = self._make_state(_response_start=99.0)

        # Pass None as full_response — function checks `if full_response`
        result, effective_agent = handle_post_response(
            None, "test", state,
            "http://localhost:8000", "code-writer", "system ctx", "/tmp",
        )
        assert result is None
        assert effective_agent == "code-writer"

    @patch("code_agents.chat.chat_response._extract_delegations", return_value=[])
    @patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[])
    @patch("code_agents.chat.chat_response._time")
    def test_verification_review_numbered_lines(self, mock_time, mock_skills, mock_deleg):
        """Review notes with numbered lines (1., 2.) are formatted."""
        from code_agents.chat.chat_response import handle_post_response

        mock_time.monotonic.return_value = 100.0
        state = self._make_state(_response_start=99.0)

        mock_verifier = MagicMock()
        mock_verifier.should_verify.return_value = True
        mock_verifier.build_verify_prompt.return_value = {"prompt": "verify", "cache_key": None}
        mock_verifier.get_cached_result.return_value = None

        with patch("code_agents.core.response_verifier.get_verifier", return_value=mock_verifier), \
             patch("code_agents.chat.chat_response._build_system_context", return_value="ctx"), \
             patch("code_agents.chat.chat_response._stream_with_spinner",
                   return_value=["1. Error handling missing\n2. No input validation"]):
            handle_post_response(
                ["code response"], "write a function", state,
                "http://localhost:8000", "code-writer", "system ctx", "/tmp",
            )

    @patch("code_agents.chat.chat_response._extract_delegations", return_value=[])
    @patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[])
    @patch("code_agents.chat.chat_response._time")
    def test_verification_should_verify_false(self, mock_time, mock_skills, mock_deleg):
        """Verification skipped when should_verify returns False."""
        from code_agents.chat.chat_response import handle_post_response

        mock_time.monotonic.return_value = 100.0
        state = self._make_state(_response_start=99.0)

        mock_verifier = MagicMock()
        mock_verifier.should_verify.return_value = False

        with patch("code_agents.core.response_verifier.get_verifier", return_value=mock_verifier), \
             patch("code_agents.chat.chat_response._stream_with_spinner") as mock_spinner:
            handle_post_response(
                ["code"], "question", state,
                "http://localhost:8000", "code-writer", "system ctx", "/tmp",
            )

            mock_spinner.assert_not_called()

    @patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[])
    @patch("code_agents.chat.chat_response._time")
    def test_delegation_no_response(self, mock_time, mock_skills):
        """Delegation returns empty -> original response kept."""
        from code_agents.chat.chat_response import handle_post_response

        mock_time.monotonic.return_value = 100.0
        state = self._make_state(_response_start=99.0)

        with patch("code_agents.chat.chat_response._extract_delegations",
                    return_value=[("code-reviewer", "review this")]), \
             patch("code_agents.chat.chat_response._build_system_context", return_value="ctx"), \
             patch("code_agents.chat.chat_response._stream_with_spinner", return_value=[]), \
             patch("code_agents.chat.chat_response.sys") as mock_sys:
            mock_sys.stdout.isatty.return_value = True

            result, effective_agent = handle_post_response(
                ["original"], "test", state,
                "http://localhost:8000", "code-writer", "system ctx", "/tmp",
            )

            # Original kept because delegate_response is empty/falsy
            assert result == ["original"]
            assert effective_agent == "code-writer"

    @patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[])
    @patch("code_agents.chat.chat_response._time")
    def test_delegation_depth_limit_blocks(self, mock_time, mock_skills):
        """Delegation is blocked when depth exceeds MAX_DELEGATION_DEPTH."""
        from code_agents.chat.chat_response import handle_post_response

        mock_time.monotonic.return_value = 100.0
        state = self._make_state(_response_start=99.0)
        state["_delegation_depth"] = 3  # at limit

        with patch("code_agents.chat.chat_response._extract_delegations",
                    return_value=[("code-reviewer", "review this")]), \
             patch("code_agents.chat.chat_response._stream_with_spinner") as mock_spinner:
            result, effective_agent = handle_post_response(
                ["[DELEGATE:code-reviewer]review this"], "test", state,
                "http://localhost:8000", "code-writer", "system ctx", "/tmp",
            )

            # Spinner never called — delegation blocked by depth
            mock_spinner.assert_not_called()
            assert effective_agent == "code-writer"

    @patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[])
    @patch("code_agents.chat.chat_response._time")
    def test_delegation_depth_restored_after_roundtrip(self, mock_time, mock_skills):
        """Delegation depth is restored after delegate completes."""
        from code_agents.chat.chat_response import handle_post_response

        mock_time.monotonic.return_value = 100.0
        state = self._make_state(_response_start=99.0)
        state["_delegation_depth"] = 0

        with patch("code_agents.chat.chat_response._extract_delegations",
                    return_value=[("code-tester", "run tests")]), \
             patch("code_agents.chat.chat_response._build_system_context", return_value="ctx"), \
             patch("code_agents.chat.chat_response._stream_with_spinner",
                    side_effect=[["test passed"], ["all good"]]), \
             patch("code_agents.chat.chat_response.sys") as mock_sys:
            mock_sys.stdout.isatty.return_value = True

            handle_post_response(
                ["[DELEGATE:code-tester]run tests"], "test", state,
                "http://localhost:8000", "code-writer", "system ctx", "/tmp",
            )

            # Depth restored to original after delegation completes
            assert state["_delegation_depth"] == 0

    def test_agent_color_code_known(self):
        """Known agents return their ANSI color code."""
        from code_agents.chat.chat_response import _agent_color_code
        assert _agent_color_code("code-writer") == "32"
        assert _agent_color_code("jenkins-cicd") == "31"

    def test_agent_color_code_unknown(self):
        """Unknown agents return default white color code."""
        from code_agents.chat.chat_response import _agent_color_code
        assert _agent_color_code("unknown-agent") == "37"

    @patch("code_agents.chat.chat_response._extract_delegations", return_value=[])
    @patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[])
    @patch("code_agents.chat.chat_response._time")
    def test_response_start_popped_from_state(self, mock_time, mock_skills, mock_deleg):
        """_response_start is popped from state during processing."""
        from code_agents.chat.chat_response import handle_post_response

        mock_time.monotonic.return_value = 100.0
        state = self._make_state(_response_start=99.0)

        handle_post_response(
            ["response"], "test", state,
            "http://localhost:8000", "code-writer", "system ctx", "/tmp",
        )

        assert "_response_start" not in state
