"""Tests for terminal_layout.py — terminal size, layout support, enter/exit layout."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch, MagicMock

import pytest


class TestSupportsLayout:
    """Test supports_layout detection logic."""

    def test_not_tty_returns_false(self):
        from code_agents.chat.terminal_layout import supports_layout
        with patch.object(sys.stdout, "isatty", return_value=False):
            assert supports_layout() is False

    def test_simple_ui_env_disables(self):
        from code_agents.chat.terminal_layout import supports_layout
        with patch.object(sys.stdout, "isatty", return_value=True), \
             patch.dict(os.environ, {"CODE_AGENTS_SIMPLE_UI": "true"}):
            assert supports_layout() is False

    def test_simple_ui_1_disables(self):
        from code_agents.chat.terminal_layout import supports_layout
        with patch.object(sys.stdout, "isatty", return_value=True), \
             patch.dict(os.environ, {"CODE_AGENTS_SIMPLE_UI": "1"}):
            assert supports_layout() is False

    def test_dumb_term_returns_false(self):
        from code_agents.chat.terminal_layout import supports_layout
        with patch.object(sys.stdout, "isatty", return_value=True), \
             patch.dict(os.environ, {"TERM": "dumb", "CODE_AGENTS_SIMPLE_UI": ""}, clear=False):
            assert supports_layout() is False

    def test_empty_term_returns_false(self):
        from code_agents.chat.terminal_layout import supports_layout
        with patch.object(sys.stdout, "isatty", return_value=True), \
             patch.dict(os.environ, {"TERM": "", "CODE_AGENTS_SIMPLE_UI": ""}, clear=False):
            assert supports_layout() is False

    def test_xterm_tty_returns_true(self):
        from code_agents.chat.terminal_layout import supports_layout
        with patch.object(sys.stdout, "isatty", return_value=True), \
             patch.dict(os.environ, {"TERM": "xterm-256color", "CODE_AGENTS_SIMPLE_UI": ""}, clear=False):
            assert supports_layout() is True


class TestGetTerminalSize:
    """Test get_terminal_size wrapper."""

    def test_returns_tuple(self):
        from code_agents.chat.terminal_layout import get_terminal_size
        cols, rows = get_terminal_size()
        assert isinstance(cols, int)
        assert isinstance(rows, int)
        assert cols > 0
        assert rows > 0


class TestEnterExitLayout:
    """Test enter_layout and exit_layout don't crash."""

    def test_enter_layout_noop_when_unsupported(self):
        from code_agents.chat.terminal_layout import enter_layout
        with patch("code_agents.chat.terminal_layout.supports_layout", return_value=False):
            enter_layout()  # should not write anything

    def test_exit_layout_noop_when_unsupported(self):
        from code_agents.chat.terminal_layout import exit_layout
        with patch("code_agents.chat.terminal_layout.supports_layout", return_value=False):
            exit_layout()  # should not write anything

    def test_enter_layout_writes_when_supported(self):
        from code_agents.chat.terminal_layout import enter_layout
        mock_stdout = MagicMock()
        with patch("code_agents.chat.terminal_layout.supports_layout", return_value=True), \
             patch("code_agents.chat.terminal_layout.get_terminal_size", return_value=(80, 24)), \
             patch("sys.stdout", mock_stdout):
            enter_layout()
            assert mock_stdout.write.called

    def test_exit_layout_writes_when_supported(self):
        from code_agents.chat import terminal_layout
        from code_agents.chat.terminal_layout import exit_layout
        mock_stdout = MagicMock()
        # exit_layout only writes if _layout_active is True (set by enter_layout)
        terminal_layout._layout_active = True
        try:
            with patch("code_agents.chat.terminal_layout.get_terminal_size", return_value=(80, 24)), \
                 patch("sys.stdout", mock_stdout):
                exit_layout()
                assert mock_stdout.write.called
        finally:
            terminal_layout._layout_active = False


class TestDrawInputBar:
    """Test draw_input_bar rendering."""

    def test_noop_when_unsupported(self):
        from code_agents.chat.terminal_layout import draw_input_bar
        with patch("code_agents.chat.terminal_layout.supports_layout", return_value=False):
            draw_input_bar()  # should not crash

    def test_draws_when_supported(self):
        from code_agents.chat.terminal_layout import draw_input_bar
        mock_stdout = MagicMock()
        with patch("code_agents.chat.terminal_layout.supports_layout", return_value=True), \
             patch("code_agents.chat.terminal_layout.get_terminal_size", return_value=(80, 24)), \
             patch("sys.stdout", mock_stdout):
            draw_input_bar(agent_name="code-writer", nickname="dev", superpower=True)
            assert mock_stdout.write.called


class TestMoveToOutput:
    """Test move_to_output cursor positioning."""

    def test_noop_when_unsupported(self):
        from code_agents.chat.terminal_layout import move_to_output
        with patch("code_agents.chat.terminal_layout.supports_layout", return_value=False):
            move_to_output()  # should not crash

    def test_writes_when_supported(self):
        from code_agents.chat.terminal_layout import move_to_output
        mock_stdout = MagicMock()
        with patch("code_agents.chat.terminal_layout.supports_layout", return_value=True), \
             patch("code_agents.chat.terminal_layout.get_terminal_size", return_value=(80, 24)), \
             patch("sys.stdout", mock_stdout):
            move_to_output()
            assert mock_stdout.write.called


class TestMoveToInput:
    """Test move_to_input cursor positioning."""

    def test_noop_when_unsupported(self):
        from code_agents.chat.terminal_layout import move_to_input
        with patch("code_agents.chat.terminal_layout.supports_layout", return_value=False):
            move_to_input()  # should not crash

    def test_writes_when_supported(self):
        from code_agents.chat.terminal_layout import move_to_input
        mock_stdout = MagicMock()
        with patch("code_agents.chat.terminal_layout.supports_layout", return_value=True), \
             patch("code_agents.chat.terminal_layout.get_terminal_size", return_value=(80, 24)), \
             patch("sys.stdout", mock_stdout):
            move_to_input()
            assert mock_stdout.write.called
