"""Extra tests for chat_ui.py — covers color functions, markdown rendering,
spinner, activity indicator, response box, selectors, welcome box."""

from __future__ import annotations

import sys
import threading
import time
from io import StringIO
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Color / theme helpers
# ---------------------------------------------------------------------------


class TestColorFunctions:
    """Test _w() wrapper and all color functions."""

    def test_w_with_color_enabled(self):
        from code_agents.chat.chat_ui import _w
        with patch("code_agents.chat.chat_ui._USE_COLOR", True):
            result = _w("32", "hello")
            assert "\033[32m" in result
            assert "hello" in result
            assert "\033[0m" in result

    def test_w_with_color_disabled(self):
        from code_agents.chat.chat_ui import _w
        with patch("code_agents.chat.chat_ui._USE_COLOR", False):
            result = _w("32", "hello")
            assert result == "hello"

    def test_all_color_functions_return_string(self):
        from code_agents.chat import chat_ui
        fns = [
            chat_ui.bold, chat_ui.green, chat_ui.yellow, chat_ui.red,
            chat_ui.cyan, chat_ui.dim, chat_ui.magenta, chat_ui.blue,
            chat_ui.white, chat_ui.bright_red, chat_ui.bright_green,
            chat_ui.bright_yellow, chat_ui.bright_cyan, chat_ui.bright_magenta,
        ]
        for fn in fns:
            result = fn("test")
            assert isinstance(result, str)
            assert "test" in result

    def test_agent_color_known(self):
        from code_agents.chat.chat_ui import agent_color, cyan
        fn = agent_color("code-reasoning")
        assert fn is cyan

    def test_agent_color_unknown_falls_back(self):
        from code_agents.chat.chat_ui import agent_color, magenta
        fn = agent_color("nonexistent-agent")
        assert fn is magenta


class TestRlWrap:
    def test_rl_wrap_with_color(self):
        from code_agents.chat.chat_ui import _rl_wrap
        with patch("code_agents.chat.chat_ui._USE_COLOR", True):
            result = _rl_wrap("1", "hello")
            assert "\x01" in result
            assert "\x02" in result
            assert "hello" in result

    def test_rl_wrap_without_color(self):
        from code_agents.chat.chat_ui import _rl_wrap
        with patch("code_agents.chat.chat_ui._USE_COLOR", False):
            result = _rl_wrap("1", "hello")
            assert result == "hello"

    def test_rl_bold(self):
        from code_agents.chat.chat_ui import _rl_bold
        result = _rl_bold("text")
        assert "text" in result

    def test_rl_green(self):
        from code_agents.chat.chat_ui import _rl_green
        result = _rl_green("text")
        assert "text" in result


# ---------------------------------------------------------------------------
# ANSI helpers
# ---------------------------------------------------------------------------


class TestVisibleLen:
    def test_plain_text(self):
        from code_agents.chat.chat_ui import _visible_len
        assert _visible_len("hello") == 5

    def test_ansi_stripped(self):
        from code_agents.chat.chat_ui import _visible_len
        assert _visible_len("\033[32mhello\033[0m") == 5

    def test_empty(self):
        from code_agents.chat.chat_ui import _visible_len
        assert _visible_len("") == 0


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------


class TestRenderMarkdown:
    def test_no_color_passthrough(self):
        from code_agents.chat.chat_ui import _render_markdown
        with patch("code_agents.chat.chat_ui._USE_COLOR", False):
            text = "**bold** and `code`"
            assert _render_markdown(text) == text

    def test_bold_rendering(self):
        from code_agents.chat.chat_ui import _render_markdown
        with patch("code_agents.chat.chat_ui._USE_COLOR", True):
            result = _render_markdown("**bold text**")
            assert "bold text" in result
            assert "**" not in result

    def test_italic_rendering(self):
        from code_agents.chat.chat_ui import _render_markdown
        with patch("code_agents.chat.chat_ui._USE_COLOR", True):
            result = _render_markdown("*italic text*")
            assert "italic text" in result

    def test_inline_code(self):
        from code_agents.chat.chat_ui import _render_markdown
        with patch("code_agents.chat.chat_ui._USE_COLOR", True):
            result = _render_markdown("`my_var`")
            assert "my_var" in result
            assert "`" not in result

    def test_header_rendering(self):
        from code_agents.chat.chat_ui import _render_markdown
        with patch("code_agents.chat.chat_ui._USE_COLOR", True):
            result = _render_markdown("## My Header")
            assert "My Header" in result
            assert "##" not in result

    def test_horizontal_rule(self):
        from code_agents.chat.chat_ui import _render_markdown
        with patch("code_agents.chat.chat_ui._USE_COLOR", True):
            result = _render_markdown("---")
            assert "─" in result

    def test_blockquote(self):
        from code_agents.chat.chat_ui import _render_markdown
        with patch("code_agents.chat.chat_ui._USE_COLOR", True):
            result = _render_markdown("> quoted text")
            assert "quoted text" in result
            assert "▎" in result

    def test_list_items(self):
        from code_agents.chat.chat_ui import _render_markdown
        with patch("code_agents.chat.chat_ui._USE_COLOR", True):
            result = _render_markdown("- item one\n- item two")
            assert "item one" in result
            assert "•" in result

    def test_code_block_rendering(self):
        from code_agents.chat.chat_ui import _render_markdown
        with patch("code_agents.chat.chat_ui._USE_COLOR", True):
            text = "```bash\necho hello\n```"
            result = _render_markdown(text)
            assert "echo hello" in result
            assert "┌" in result
            assert "└" in result

    def test_code_block_long_lines(self):
        from code_agents.chat.chat_ui import _render_markdown
        with patch("code_agents.chat.chat_ui._USE_COLOR", True):
            long_line = "x" * 200
            text = f"```bash\n{long_line}\n```"
            result = _render_markdown(text)
            assert "x" in result

    def test_table_rendering(self):
        from code_agents.chat.chat_ui import _render_markdown
        with patch("code_agents.chat.chat_ui._USE_COLOR", True):
            text = "| Col1 | Col2 |\n| --- | --- |\n| a | b |"
            result = _render_markdown(text)
            assert "Col1" in result
            assert "a" in result

    def test_table_no_data_rows(self):
        from code_agents.chat.chat_ui import _render_markdown
        with patch("code_agents.chat.chat_ui._USE_COLOR", True):
            # Only separator — degenerate table
            text = "| --- | --- |"
            result = _render_markdown(text)
            assert "---" in result


# ---------------------------------------------------------------------------
# Spinner
# ---------------------------------------------------------------------------


class TestSpinner:
    def test_spinner_context_manager(self):
        from code_agents.chat.chat_ui import _spinner
        buf = StringIO()
        with patch("sys.stdout", buf):
            with _spinner("Loading"):
                time.sleep(0.15)
        # Spinner wrote something
        output = buf.getvalue()
        assert len(output) > 0

    def test_spinner_cleanup(self):
        from code_agents.chat.chat_ui import _spinner
        buf = StringIO()
        with patch("sys.stdout", buf):
            ctx = _spinner("Test")
            ctx.__enter__()
            time.sleep(0.15)
            ctx.__exit__(None, None, None)
        # After exit the line should be cleared


class TestActivityIndicator:
    def test_activity_indicator_basic(self):
        from code_agents.chat.chat_ui import activity_indicator
        buf = StringIO()
        with patch("sys.stdout", buf):
            with activity_indicator("Reading", "file.py"):
                time.sleep(0.15)
        output = buf.getvalue()
        assert len(output) > 0

    def test_activity_indicator_update(self):
        from code_agents.chat.chat_ui import activity_indicator
        buf = StringIO()
        with patch("sys.stdout", buf):
            with activity_indicator("Reading") as ai:
                ai.update("Writing", "out.txt")
                time.sleep(0.15)

    def test_activity_indicator_no_target(self):
        from code_agents.chat.chat_ui import activity_indicator
        buf = StringIO()
        with patch("sys.stdout", buf):
            with activity_indicator("Thinking"):
                time.sleep(0.1)


# ---------------------------------------------------------------------------
# Agent color functions
# ---------------------------------------------------------------------------


class TestAgentColorFn:
    def test_known_agent(self):
        from code_agents.chat.chat_ui import agent_color_fn
        with patch("code_agents.chat.chat_ui._USE_COLOR", True):
            fn = agent_color_fn("code-writer")
            result = fn("hello")
            assert "hello" in result
            assert "\033[" in result

    def test_unknown_agent(self):
        from code_agents.chat.chat_ui import agent_color_fn
        with patch("code_agents.chat.chat_ui._USE_COLOR", True):
            fn = agent_color_fn("unknown-agent")
            result = fn("text")
            assert "text" in result

    def test_no_color_mode(self):
        from code_agents.chat.chat_ui import agent_color_fn
        with patch("code_agents.chat.chat_ui._USE_COLOR", False):
            fn = agent_color_fn("code-writer")
            assert fn("text") == "text"


# ---------------------------------------------------------------------------
# Response box
# ---------------------------------------------------------------------------


class TestFormatResponseBox:
    def test_empty_text(self):
        from code_agents.chat.chat_ui import format_response_box
        assert format_response_box("") == ""
        assert format_response_box("   ") == ""

    def test_basic_box(self):
        from code_agents.chat.chat_ui import format_response_box
        result = format_response_box("Hello world")
        assert "Hello world" in result
        assert "╔" in result
        assert "╚" in result

    def test_box_with_agent_name(self):
        from code_agents.chat.chat_ui import format_response_box
        result = format_response_box("test", agent_name="code-writer")
        assert "CODE-WRITER" in result

    def test_box_without_agent_name(self):
        from code_agents.chat.chat_ui import format_response_box
        result = format_response_box("test", agent_name="")
        assert "╔" in result

    def test_long_line_wrapping(self):
        from code_agents.chat.chat_ui import format_response_box
        long_text = "x" * 200
        result = format_response_box(long_text)
        assert "x" in result

    def test_print_response_box(self, capsys):
        from code_agents.chat.chat_ui import print_response_box
        print_response_box("Hello", agent_name="explore")
        captured = capsys.readouterr()
        assert "Hello" in captured.out

    def test_print_response_box_empty(self, capsys):
        from code_agents.chat.chat_ui import print_response_box
        print_response_box("")
        captured = capsys.readouterr()
        assert captured.out == ""


# ---------------------------------------------------------------------------
# _ask_yes_no
# ---------------------------------------------------------------------------


class TestAskYesNo:
    def test_yes_default(self):
        from code_agents.chat.chat_ui import _ask_yes_no
        with patch("code_agents.chat.chat_ui._tab_selector", return_value=0) as mock_sel:
            assert _ask_yes_no("Continue?") is True
            mock_sel.assert_called_once_with("Continue?", ["Yes", "No"], default=0)

    def test_no_default(self):
        from code_agents.chat.chat_ui import _ask_yes_no
        with patch("code_agents.chat.chat_ui._tab_selector", return_value=1) as mock_sel:
            assert _ask_yes_no("Continue?", default=False) is False
            mock_sel.assert_called_once_with("Continue?", ["Yes", "No"], default=1)


# ---------------------------------------------------------------------------
# _amend_prompt
# ---------------------------------------------------------------------------


class TestAmendPrompt:
    def test_normal_input(self):
        from code_agents.chat.chat_ui import _amend_prompt
        with patch("builtins.input", return_value="fix the bug"):
            assert _amend_prompt() == "fix the bug"

    def test_eof(self):
        from code_agents.chat.chat_ui import _amend_prompt
        with patch("builtins.input", side_effect=EOFError):
            assert _amend_prompt() == ""

    def test_keyboard_interrupt(self):
        from code_agents.chat.chat_ui import _amend_prompt
        with patch("builtins.input", side_effect=KeyboardInterrupt):
            assert _amend_prompt() == ""


# ---------------------------------------------------------------------------
# _tab_selector fallback path (no tty)
# ---------------------------------------------------------------------------


class TestTabSelectorFallback:
    """Test the fallback (non-tty) path of _tab_selector."""

    def test_fallback_digit_selection(self):
        from code_agents.chat.chat_ui import _tab_selector
        # Force ImportError for tty/termios to trigger fallback
        with patch("builtins.input", return_value="2"), \
             patch("builtins.__import__", side_effect=lambda name, *a, **kw: (_ for _ in ()).throw(ImportError) if name in ("tty", "termios") else __builtins__.__import__(name, *a, **kw)):
            # Simulate tty/termios not available — trigger fallback via OSError
            pass

    def test_fallback_tab_key(self):
        from code_agents.chat.chat_ui import _tab_selector
        # Trigger fallback via OSError on fileno()
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.fileno.side_effect = OSError("not a tty")
            with patch("builtins.input", return_value="t"):
                result = _tab_selector("Choose:", ["A", "B"], default=0)
                assert result == -2

    def test_fallback_digit(self):
        from code_agents.chat.chat_ui import _tab_selector
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.fileno.side_effect = OSError("not a tty")
            with patch("builtins.input", return_value="1"):
                result = _tab_selector("Choose:", ["A", "B"], default=0)
                assert result == 0

    def test_fallback_eof(self):
        from code_agents.chat.chat_ui import _tab_selector
        with patch("sys.stdin") as mock_stdin:
            mock_stdin.fileno.side_effect = OSError("not a tty")
            with patch("builtins.input", side_effect=EOFError):
                result = _tab_selector("Choose:", ["A", "B"], default=0)
                assert result == 1  # last option


# ---------------------------------------------------------------------------
# _print_welcome
# ---------------------------------------------------------------------------


class TestPrintWelcome:
    def test_no_welcome(self, capsys):
        from code_agents.chat.chat_ui import _print_welcome
        _print_welcome("unknown-agent", {})
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_welcome_prints_box(self, capsys):
        from code_agents.chat.chat_ui import _print_welcome
        welcome_data = {
            "test-agent": (
                "Test Agent",
                ["Can do X", "Can do Y"],
                ["Try this", "Try that"],
            )
        }
        _print_welcome("test-agent", welcome_data)
        captured = capsys.readouterr()
        assert "Test Agent" in captured.out
        assert "Can do X" in captured.out
        assert "Try this" in captured.out
        assert "┌" in captured.out
        assert "└" in captured.out


# ---------------------------------------------------------------------------
# AGENT_ANSI_COLORS / _AGENT_COLORS compat
# ---------------------------------------------------------------------------


class TestAgentAnsiColors:
    def test_agent_ansi_colors_populated(self):
        from code_agents.chat.chat_ui import AGENT_ANSI_COLORS
        assert "code-writer" in AGENT_ANSI_COLORS
        assert "code-reviewer" in AGENT_ANSI_COLORS

    def test_backward_compat(self):
        from code_agents.chat.chat_ui import _AGENT_COLORS, AGENT_ANSI_COLORS
        assert _AGENT_COLORS is AGENT_ANSI_COLORS
