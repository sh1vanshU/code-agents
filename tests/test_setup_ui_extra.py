"""Extra tests for setup_ui.py — prompt_choice interactive mode, lines 105-172."""

from __future__ import annotations

import sys
from unittest.mock import patch, MagicMock

import pytest

from code_agents.setup.setup_ui import (
    prompt_choice, _prompt_choice_plain,
    validate_url,
)


class TestPromptChoiceInteractive:
    """Test prompt_choice with tty-based arrow-key selector — lines 105-172."""

    def test_interactive_enter_default(self):
        """When stdin is a tty and user presses Enter, returns default."""
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = True
        mock_stdin.fileno.return_value = 0

        mock_termios = MagicMock()
        mock_termios.tcgetattr.return_value = [0] * 7
        mock_tty = MagicMock()

        # User presses Enter immediately
        mock_stdin.read.return_value = "\r"

        with patch("sys.stdin", mock_stdin), \
             patch.dict("sys.modules", {"tty": mock_tty, "termios": mock_termios}):
            # The function will try to use tty/termios — mock them
            result = prompt_choice("Pick", ["A", "B", "C"], default=2)
        # Should return default (2) since Enter was pressed
        assert result == 2

    def test_interactive_digit_key(self):
        """When user presses a digit key, selects that option."""
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = True
        mock_stdin.fileno.return_value = 0

        mock_termios = MagicMock()
        mock_termios.tcgetattr.return_value = [0] * 7
        mock_tty = MagicMock()

        # User presses "3"
        mock_stdin.read.return_value = "3"

        with patch("sys.stdin", mock_stdin), \
             patch.dict("sys.modules", {"tty": mock_tty, "termios": mock_termios}):
            result = prompt_choice("Pick", ["A", "B", "C"], default=1)
        assert result == 3

    def test_interactive_arrow_keys_then_enter(self):
        """Arrow down then Enter."""
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = True
        mock_stdin.fileno.return_value = 0

        mock_termios = MagicMock()
        mock_termios.tcgetattr.return_value = [0] * 7
        mock_tty = MagicMock()

        # Sequence: arrow down, then Enter
        mock_stdin.read.side_effect = ["\x1b", "[", "B", "\r"]

        with patch("sys.stdin", mock_stdin), \
             patch.dict("sys.modules", {"tty": mock_tty, "termios": mock_termios}):
            result = prompt_choice("Pick", ["A", "B"], default=1)
        assert result == 2

    def test_interactive_esc_key(self):
        """Esc key breaks selection (returns current)."""
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = True
        mock_stdin.fileno.return_value = 0

        mock_termios = MagicMock()
        mock_termios.tcgetattr.return_value = [0] * 7
        mock_tty = MagicMock()

        # Esc sequence: \x1b then \x1b (double esc)
        mock_stdin.read.side_effect = ["\x1b", "\x1b"]

        with patch("sys.stdin", mock_stdin), \
             patch.dict("sys.modules", {"tty": mock_tty, "termios": mock_termios}):
            result = prompt_choice("Pick", ["A", "B"], default=1)
        assert result == 1

    def test_fallback_when_no_tty(self):
        """When stdin is not a tty, falls back to plain prompt."""
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = False
        with patch("sys.stdin", mock_stdin), \
             patch("builtins.input", return_value="2"):
            result = prompt_choice("Pick", ["A", "B", "C"], default=1)
        assert result == 2

    def test_fallback_when_tty_not_available(self):
        """When stdin is not a tty, falls back to plain numbered input."""
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = False
        with patch("sys.stdin", mock_stdin), \
             patch("builtins.input", return_value="1"):
            result = prompt_choice("Pick", ["A", "B"], default=1)
        assert result == 1


class TestPromptChoicePlain:
    """Test _prompt_choice_plain fallback."""

    def test_plain_default(self):
        with patch("builtins.input", return_value=""):
            result = _prompt_choice_plain("Pick", ["A", "B"], default=2)
        assert result == 2

    def test_plain_valid_choice(self):
        with patch("builtins.input", return_value="1"):
            result = _prompt_choice_plain("Pick", ["A", "B"], default=2)
        assert result == 1

    def test_plain_invalid_then_valid(self):
        with patch("builtins.input", side_effect=["abc", "99", "2"]):
            result = _prompt_choice_plain("Pick", ["A", "B"], default=1)
        assert result == 2

    def test_plain_eof(self):
        with patch("builtins.input", side_effect=EOFError):
            result = _prompt_choice_plain("Pick", ["A", "B"], default=1)
        assert result == 1


class TestValidateUrlException:
    """Test validate_url exception path — lines 204-205."""

    def test_validate_url_exception(self):
        # Extremely malformed input that could trigger exception
        result = validate_url("")
        assert result is False
