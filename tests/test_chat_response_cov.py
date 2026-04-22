"""Coverage tests for chat_response.py — covers missing lines from coverage_run.json.

Missing lines: 56,60,62-69,71-74,76-77,102,120-125,130-131,253-254,275-278,
290-296,299-300,395,494-514,519,526-529
"""

from __future__ import annotations

import os
import sys
import time
import threading
from unittest.mock import patch, MagicMock, mock_open, call
from io import StringIO

import pytest


# ---------------------------------------------------------------------------
# Lines 56-77: process_streaming_response — _show_spinner function internals
# The spinner runs in a thread. We test by running real threading with short sleep.
# ---------------------------------------------------------------------------


class TestStreamingSpinnerReal:
    """Test the real spinner thread path (lines 56-77)."""

    def test_spinner_runs_and_stops(self):
        """Lines 56-77: spinner thread runs, blinks, and cleans up."""
        from code_agents.chat.chat_response import process_streaming_response

        # Use real threading, fake stream that yields after a brief delay
        def slow_stream(*args, **kwargs):
            time.sleep(0.6)  # let spinner blink at least once
            yield ("text", "Hello")

        buf = StringIO()
        with patch("code_agents.chat.chat_response._stream_chat", side_effect=slow_stream), \
             patch("sys.stdout", buf):
            state = {"repo_path": "/tmp"}
            got_text, parts, interrupted = process_streaming_response(
                "http://localhost:8000", "code-writer", [], state,
                _last_ctrl_c_ref=[0.0],
            )

        assert got_text is True
        assert parts == ["Hello"]
        output = buf.getvalue()
        # Spinner should have written something
        assert len(output) > 0


# ---------------------------------------------------------------------------
# Lines 102, 120-125, 130-131: text streaming newlines, wrap-at logic
# ---------------------------------------------------------------------------


class TestStreamingTextRendering:
    """Test the text rendering path with real stream iteration."""

    def test_text_newlines_suppressed(self):
        """Lines 120-125: consecutive newlines are filtered to max 2."""
        from code_agents.chat.chat_response import process_streaming_response

        def stream_with_newlines(*args, **kwargs):
            yield ("text", "line1\n\n\n\nline2")

        buf = StringIO()
        with patch("code_agents.chat.chat_response._stream_chat", side_effect=stream_with_newlines), \
             patch("sys.stdout", buf):
            state = {"repo_path": "/tmp"}
            got_text, parts, interrupted = process_streaming_response(
                "http://localhost:8000", "code-writer", [], state,
                _last_ctrl_c_ref=[0.0],
            )

        assert got_text is True
        assert parts == ["line1\n\n\n\nline2"]

    def test_text_escape_codes_pass_through(self):
        """Line 124-125: ESC character passes through without incrementing position."""
        from code_agents.chat.chat_response import process_streaming_response

        def stream_with_escape(*args, **kwargs):
            yield ("text", "\033[32mcolored\033[0m text")

        buf = StringIO()
        with patch("code_agents.chat.chat_response._stream_chat", side_effect=stream_with_escape), \
             patch("sys.stdout", buf):
            state = {"repo_path": "/tmp"}
            got_text, parts, interrupted = process_streaming_response(
                "http://localhost:8000", "code-writer", [], state,
                _last_ctrl_c_ref=[0.0],
            )

        assert got_text is True

    def test_text_long_line_wraps_at_space(self):
        """Lines 130-131: long lines wrap at space character."""
        from code_agents.chat.chat_response import process_streaming_response

        # Create text longer than typical _wrap_at
        long_text = " ".join(["word"] * 50)

        def stream_long(*args, **kwargs):
            yield ("text", long_text)

        buf = StringIO()
        with patch("code_agents.chat.chat_response._stream_chat", side_effect=stream_long), \
             patch("sys.stdout", buf):
            state = {"repo_path": "/tmp"}
            got_text, parts, interrupted = process_streaming_response(
                "http://localhost:8000", "code-writer", [], state,
                _last_ctrl_c_ref=[0.0],
            )

        assert got_text is True

    def test_spinner_line_overwritten(self):
        """Line 102: spinner_line_written[0] check — spinner line is overwritten on first text."""
        from code_agents.chat.chat_response import process_streaming_response

        def delayed_text(*args, **kwargs):
            time.sleep(0.6)  # ensure spinner writes at least once
            yield ("text", "response")

        buf = StringIO()
        with patch("code_agents.chat.chat_response._stream_chat", side_effect=delayed_text), \
             patch("sys.stdout", buf):
            state = {"repo_path": "/tmp"}
            got_text, parts, interrupted = process_streaming_response(
                "http://localhost:8000", "code-writer", [], state,
                _last_ctrl_c_ref=[0.0],
            )

        assert got_text is True
        output = buf.getvalue()
        # Spinner line cleared with carriage return + clear-line before response box
        assert "\033[2K" in output or "\r" in output


# ---------------------------------------------------------------------------
# Lines 253-254: handle_post_response — plan_report OSError
# ---------------------------------------------------------------------------


class TestPostResponsePlanReportOSError:
    def test_plan_report_os_error_ignored(self):
        """Lines 253-254: OSError writing plan report is silently ignored."""
        from code_agents.chat.chat_response import handle_post_response

        with patch("code_agents.chat.chat_response._time") as mock_time, \
             patch("code_agents.chat.chat_response._extract_delegations", return_value=[]), \
             patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[]), \
             patch("code_agents.chat.chat_input.get_current_mode", return_value="plan"), \
             patch("builtins.open", side_effect=OSError("disk full")), \
             patch("code_agents.chat.chat_history.add_message"), \
             patch("code_agents.chat.chat_history._save"):
            mock_time.monotonic.return_value = 100.0
            state = {
                "repo_path": "/tmp",
                "_response_start": 99.0,
                "_plan_report": "/tmp/plan.md",
                "session_id": "sess-1",
                "_chat_session": {"messages": []},
            }
            # Should not raise
            handle_post_response(
                ["plan output"], "plan something", state,
                "http://localhost:8000", "code-writer", "system ctx", "/tmp",
            )


# ---------------------------------------------------------------------------
# Lines 275-278: long response expand toggle
# ---------------------------------------------------------------------------


class TestLongResponseExpandToggle:
    def test_long_response_expand_then_collapse(self):
        """Lines 275-278, 290-296: user toggles expand -> collapse -> continue."""
        from code_agents.chat.chat_response import handle_post_response

        with patch("code_agents.chat.chat_response._time") as mock_time, \
             patch("code_agents.chat.chat_response._extract_delegations", return_value=[]), \
             patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[]):
            mock_time.monotonic.return_value = 100.0
            state = {"repo_path": "/tmp", "_response_start": 99.0}

            long_text = "\n".join([f"line {i}" for i in range(30)])

            # User types 'o' to expand, then 'o' again to collapse, then Enter to continue
            with patch("builtins.input", side_effect=["o", "o", ""]):
                result, effective_agent = handle_post_response(
                    [long_text], "test", state,
                    "http://localhost:8000", "code-writer", "system ctx", "/tmp",
                )
            assert result == [long_text]
            assert effective_agent == "code-writer"

    def test_long_response_expand_exception(self):
        """Lines 299-300: exception during toggle is caught."""
        from code_agents.chat.chat_response import handle_post_response

        with patch("code_agents.chat.chat_response._time") as mock_time, \
             patch("code_agents.chat.chat_response._extract_delegations", return_value=[]), \
             patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[]):
            mock_time.monotonic.return_value = 100.0
            state = {"repo_path": "/tmp", "_response_start": 99.0}

            long_text = "\n".join([f"line {i}" for i in range(30)])

            with patch("builtins.input", side_effect=RuntimeError("broken")):
                result, effective_agent = handle_post_response(
                    [long_text], "test", state,
                    "http://localhost:8000", "code-writer", "system ctx", "/tmp",
                )
            assert result == [long_text]
            assert effective_agent == "code-writer"


# ---------------------------------------------------------------------------
# Line 395: verification — plain text review lines (not bullet/numbered)
# ---------------------------------------------------------------------------


class TestVerificationPlainTextReview:
    def test_plain_text_review_line(self, capsys):
        """Line 395: review note that's not bullet or numbered → plain bullet."""
        from code_agents.chat.chat_response import handle_post_response

        with patch("code_agents.chat.chat_response._time") as mock_time, \
             patch("code_agents.chat.chat_response._extract_delegations", return_value=[]), \
             patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[]):
            mock_time.monotonic.return_value = 100.0
            state = {"repo_path": "/tmp", "_response_start": 99.0}

            mock_verifier = MagicMock()
            mock_verifier.should_verify.return_value = True
            mock_verifier.build_verify_prompt.return_value = {"prompt": "verify", "cache_key": None}
            mock_verifier.get_cached_result.return_value = None

            review_text = "Consider adding input validation\nAlso add error handling"

            with patch("code_agents.core.response_verifier.get_verifier", return_value=mock_verifier), \
                 patch("code_agents.chat.chat_response._build_system_context", return_value="ctx"), \
                 patch("code_agents.chat.chat_response._stream_with_spinner", return_value=[review_text]):
                handle_post_response(
                    ["code response"], "write func", state,
                    "http://localhost:8000", "code-writer", "system ctx", "/tmp",
                )


# ---------------------------------------------------------------------------
# Lines 494-529: questionnaire path — [QUESTION:key] handling
# ---------------------------------------------------------------------------


class TestQuestionnaireHandling:
    def test_question_tags_trigger_questionnaire(self):
        """Lines 494-529: [QUESTION:key] tags trigger the questionnaire flow."""
        from code_agents.chat.chat_response import handle_post_response

        with patch("code_agents.chat.chat_response._time") as mock_time, \
             patch("code_agents.chat.chat_response._extract_delegations", return_value=[]), \
             patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[]):
            mock_time.monotonic.return_value = 100.0

            mock_session = {"messages": []}
            state = {
                "repo_path": "/tmp",
                "_response_start": 99.0,
                "_chat_session": mock_session,
            }

            mock_qa_answer = {"question": "deploy_target", "answer": "staging"}
            mock_templates = {
                "deploy_target": {"question": "Where to deploy?", "options": ["staging", "prod"]}
            }

            with patch("code_agents.agent_system.questionnaire.ask_question", return_value=mock_qa_answer) as mock_ask, \
                 patch("code_agents.agent_system.questionnaire.TEMPLATES", mock_templates), \
                 patch("code_agents.agent_system.questionnaire.format_qa_for_prompt", return_value="QA context") as mock_fmt, \
                 patch("code_agents.agent_system.questionnaire.has_been_answered", return_value=False), \
                 patch("code_agents.chat.chat_history.save_qa_pairs") as mock_persist_qa, \
                 patch("code_agents.chat.chat_history.add_message"), \
                 patch("code_agents.chat.chat_response._stream_with_spinner", return_value=["qa response"]) as mock_stream:
                result, effective_agent = handle_post_response(
                    ["Please answer: [QUESTION:deploy_target]"], "deploy", state,
                    "http://localhost:8000", "code-writer", "system ctx", "/tmp",
                )

            mock_ask.assert_called_once()
            mock_persist_qa.assert_called_once()
            mock_stream.assert_called_once()
            assert result == ["qa response"]
            assert effective_agent == "code-writer"
            assert state["_last_output"] == "qa response"

    def test_question_already_answered_skipped(self):
        """Lines 499-500: already answered questions are skipped."""
        from code_agents.chat.chat_response import handle_post_response

        with patch("code_agents.chat.chat_response._time") as mock_time, \
             patch("code_agents.chat.chat_response._extract_delegations", return_value=[]), \
             patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[]):
            mock_time.monotonic.return_value = 100.0

            state = {
                "repo_path": "/tmp",
                "_response_start": 99.0,
            }

            mock_templates = {
                "deploy_target": {"question": "Where to deploy?"}
            }

            with patch("code_agents.agent_system.questionnaire.TEMPLATES", mock_templates), \
                 patch("code_agents.agent_system.questionnaire.has_been_answered", return_value=True), \
                 patch("code_agents.agent_system.questionnaire.format_qa_for_prompt", return_value=""), \
                 patch("code_agents.agent_system.questionnaire.ask_question") as mock_ask:
                handle_post_response(
                    ["[QUESTION:deploy_target]"], "deploy", state,
                    "http://localhost:8000", "code-writer", "system ctx", "/tmp",
                )

            mock_ask.assert_not_called()

    def test_question_unknown_template(self):
        """Lines 503-507: question key not in TEMPLATES uses raw key."""
        from code_agents.chat.chat_response import handle_post_response

        with patch("code_agents.chat.chat_response._time") as mock_time, \
             patch("code_agents.chat.chat_response._extract_delegations", return_value=[]), \
             patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[]):
            mock_time.monotonic.return_value = 100.0

            state = {
                "repo_path": "/tmp",
                "_response_start": 99.0,
            }

            mock_qa_answer = {"question": "custom_q", "answer": "yes"}

            with patch("code_agents.agent_system.questionnaire.TEMPLATES", {}), \
                 patch("code_agents.agent_system.questionnaire.has_been_answered", return_value=False), \
                 patch("code_agents.agent_system.questionnaire.ask_question", return_value=mock_qa_answer) as mock_ask, \
                 patch("code_agents.agent_system.questionnaire.format_qa_for_prompt", return_value=""):
                handle_post_response(
                    ["[QUESTION:custom_q]"], "test", state,
                    "http://localhost:8000", "code-writer", "system ctx", "/tmp",
                )

            # Called with question=key and generic options
            mock_ask.assert_called_once_with(question="custom_q", options=["Yes", "No", "Skip"])

    def test_question_no_qa_context(self):
        """Lines 513-514: empty QA context → no follow-up stream."""
        from code_agents.chat.chat_response import handle_post_response

        with patch("code_agents.chat.chat_response._time") as mock_time, \
             patch("code_agents.chat.chat_response._extract_delegations", return_value=[]), \
             patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[]):
            mock_time.monotonic.return_value = 100.0

            state = {"repo_path": "/tmp", "_response_start": 99.0}

            mock_qa_answer = {"question": "q", "answer": "a"}

            with patch("code_agents.agent_system.questionnaire.TEMPLATES", {}), \
                 patch("code_agents.agent_system.questionnaire.has_been_answered", return_value=False), \
                 patch("code_agents.agent_system.questionnaire.ask_question", return_value=mock_qa_answer), \
                 patch("code_agents.agent_system.questionnaire.format_qa_for_prompt", return_value=""), \
                 patch("code_agents.chat.chat_response._stream_with_spinner") as mock_stream:
                handle_post_response(
                    ["[QUESTION:q]"], "test", state,
                    "http://localhost:8000", "code-writer", "system ctx", "/tmp",
                )

            mock_stream.assert_not_called()


# ---------------------------------------------------------------------------
# Delegation scratchpad injection
# ---------------------------------------------------------------------------


class TestDelegationScratchpadInjection:
    """Verify scratchpad is injected into delegate agent's system context."""

    def test_delegate_receives_scratchpad(self):
        """Delegate system message includes [Session Memory] with source agent's facts."""
        from code_agents.chat.chat_response import handle_post_response

        captured_msgs = []

        def _capture_stream(url, agent, msgs, session_id, **kwargs):
            captured_msgs.extend(msgs)
            return ["delegate response"]

        mock_scratchpad = MagicMock()
        mock_scratchpad.format_for_prompt.return_value = (
            "[Session Memory — already discovered, do NOT re-fetch these values]\n"
            "  image_tag: 924-grv\n"
            "  deploy_env: qa4\n"
            "  repo: pg-acquiring-biz\n"
            "[End Session Memory]"
        )

        with patch("code_agents.chat.chat_response._time") as mock_time, \
             patch("code_agents.chat.chat_response._extract_delegations",
                   return_value=[("argocd-verify", "Verify deployment")]), \
             patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[]), \
             patch("code_agents.chat.chat_response._build_system_context", return_value="system ctx"), \
             patch("code_agents.chat.chat_response._stream_with_spinner", side_effect=_capture_stream), \
             patch("code_agents.agent_system.session_scratchpad.SessionScratchpad", return_value=mock_scratchpad), \
             patch("sys.stdout") as mock_stdout:
            mock_stdout.isatty.return_value = True
            mock_time.monotonic.return_value = 100.0
            state = {
                "repo_path": "/tmp",
                "_response_start": 99.0,
                "_chat_session": {"id": "sess-123", "messages": []},
                "session_id": "sess-123",
            }
            handle_post_response(
                ["[DELEGATE:argocd-verify] Verify deployment"], "deploy", state,
                "http://localhost:8000", "jenkins-cicd", "system ctx", "/tmp",
            )

        # Delegate's system message should contain scratchpad
        assert captured_msgs, "delegate messages should have been captured"
        system_msg = captured_msgs[0]["content"]
        assert "[Session Memory" in system_msg
        assert "image_tag: 924-grv" in system_msg
        assert "deploy_env: qa4" in system_msg

    def test_delegate_without_scratchpad(self):
        """Delegation works normally when no scratchpad facts exist."""
        from code_agents.chat.chat_response import handle_post_response

        captured_msgs = []

        def _capture_stream(url, agent, msgs, session_id, **kwargs):
            captured_msgs.extend(msgs)
            return ["delegate response"]

        mock_scratchpad = MagicMock()
        mock_scratchpad.format_for_prompt.return_value = ""  # no facts

        with patch("code_agents.chat.chat_response._time") as mock_time, \
             patch("code_agents.chat.chat_response._extract_delegations",
                   return_value=[("argocd-verify", "Verify deployment")]), \
             patch("code_agents.chat.chat_response._extract_skill_requests", return_value=[]), \
             patch("code_agents.chat.chat_response._build_system_context", return_value="system ctx"), \
             patch("code_agents.chat.chat_response._stream_with_spinner", side_effect=_capture_stream), \
             patch("code_agents.agent_system.session_scratchpad.SessionScratchpad", return_value=mock_scratchpad), \
             patch("sys.stdout") as mock_stdout:
            mock_stdout.isatty.return_value = True
            mock_time.monotonic.return_value = 100.0
            state = {
                "repo_path": "/tmp",
                "_response_start": 99.0,
                "_chat_session": {"id": "sess-123", "messages": []},
                "session_id": "sess-123",
            }
            handle_post_response(
                ["[DELEGATE:argocd-verify] Verify deployment"], "deploy", state,
                "http://localhost:8000", "jenkins-cicd", "system ctx", "/tmp",
            )

        assert captured_msgs
        system_msg = captured_msgs[0]["content"]
        assert "[Session Memory" not in system_msg
        # System ctx starts with base context, plus delegation context block
        assert system_msg.startswith("system ctx")
        assert "[DELEGATION CONTEXT]" in system_msg
        assert "jenkins-cicd" in system_msg  # source agent name injected
