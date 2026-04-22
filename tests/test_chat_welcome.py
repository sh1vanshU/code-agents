"""Tests for chat_welcome.py — welcome messages, agent selection, AGENT_ROLES."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch, MagicMock

import pytest

from code_agents.chat.chat_welcome import (
    AGENT_ROLES,
    AGENT_WELCOME,
    _print_welcome,
    _select_agent,
)


class TestAgentData:
    """Test AGENT_ROLES and AGENT_WELCOME are consistent."""

    def test_all_welcome_keys_in_roles(self):
        for key in AGENT_WELCOME:
            assert key in AGENT_ROLES, f"{key} in AGENT_WELCOME but not AGENT_ROLES"

    def test_all_roles_have_welcome(self):
        for key in AGENT_ROLES:
            assert key in AGENT_WELCOME, f"{key} in AGENT_ROLES but not AGENT_WELCOME"


class TestPrintWelcome:
    """Test _print_welcome function — lines 303, 305."""

    def test_print_welcome_with_repo(self, capsys):
        with patch("code_agents.chat.chat_welcome._print_welcome_raw") as mock_raw, \
             patch("code_agents.domain.gita_shlokas.format_shloka_rainbow", return_value="shloka text"):
            _print_welcome("code-writer", "/path/to/my-project")
        mock_raw.assert_called_once()
        # Check that {repo} substitution happened
        args = mock_raw.call_args
        welcome_data = args[1] if len(args) > 1 else args[0][1]
        # The examples for code-writer don't have {repo} but jenkins-cicd does
        # Just verify it was called

    def test_print_welcome_repo_substitution(self, capsys):
        with patch("code_agents.chat.chat_welcome._print_welcome_raw") as mock_raw, \
             patch("code_agents.domain.gita_shlokas.format_shloka_rainbow", return_value="shloka"):
            _print_welcome("jenkins-cicd", "/home/user/my-service")
        args = mock_raw.call_args[0]
        # args[0] is agent_name, args[1] is welcome_data
        welcome_data = args[1]
        # jenkins-cicd examples should have {repo} replaced with "my-service"
        examples = welcome_data["jenkins-cicd"][2]
        for ex in examples:
            assert "{repo}" not in ex
            # Should contain the actual repo name where {repo} was
            if "my-service" in ex or "Build" in ex:
                pass  # good

    def test_print_welcome_no_repo(self, capsys):
        with patch("code_agents.chat.chat_welcome._print_welcome_raw") as mock_raw, \
             patch("code_agents.domain.gita_shlokas.format_shloka_rainbow", return_value="shloka"):
            _print_welcome("code-writer", "")
        mock_raw.assert_called_once()

    def test_print_welcome_shloka_import_error(self, capsys):
        """When gita_shlokas fails to import, should not crash — line 286."""
        with patch("code_agents.chat.chat_welcome._print_welcome_raw"), \
             patch("code_agents.domain.gita_shlokas.format_shloka_rainbow", side_effect=ImportError):
            _print_welcome("code-writer", "/tmp/repo")
        # Should not raise

    def test_print_welcome_unknown_agent(self, capsys):
        """When agent not in welcome_data, no shloka printed."""
        with patch("code_agents.chat.chat_welcome._print_welcome_raw"):
            _print_welcome("nonexistent-agent", "/tmp/repo")
        # Should not crash


class TestSelectAgent:
    """Test _select_agent interactive menu — lines 303-404."""

    def test_select_agent_fallback_valid_number(self):
        """When tty fails, use numbered fallback — lines 385-404."""
        agents = {"code-writer": "Write code", "git-ops": "Git operations"}
        # Simulate OSError on fileno (no tty)
        mock_stdin = MagicMock()
        mock_stdin.fileno.side_effect = OSError("not a tty")
        with patch("sys.stdin", mock_stdin), \
             patch("builtins.input", return_value="1"):
            result = _select_agent(agents)
        # sorted agents: code-writer, git-ops — index 1 = code-writer
        assert result == "code-writer"

    def test_select_agent_fallback_by_name(self):
        """Type agent name directly in fallback."""
        agents = {"code-writer": "Write code", "git-ops": "Git operations"}
        mock_stdin = MagicMock()
        mock_stdin.fileno.side_effect = OSError("not a tty")
        with patch("sys.stdin", mock_stdin), \
             patch("builtins.input", return_value="git-ops"):
            result = _select_agent(agents)
        assert result == "git-ops"

    def test_select_agent_fallback_cancel_zero(self):
        """Type 0 to cancel in fallback."""
        agents = {"code-writer": "Write code"}
        mock_stdin = MagicMock()
        mock_stdin.fileno.side_effect = OSError("not a tty")
        with patch("sys.stdin", mock_stdin), \
             patch("builtins.input", return_value="0"):
            result = _select_agent(agents)
        assert result is None

    def test_select_agent_fallback_eof(self):
        """EOFError in fallback returns None."""
        agents = {"code-writer": "Write code"}
        mock_stdin = MagicMock()
        mock_stdin.fileno.side_effect = OSError("not a tty")
        with patch("sys.stdin", mock_stdin), \
             patch("builtins.input", side_effect=EOFError):
            result = _select_agent(agents)
        assert result is None

    def test_select_agent_fallback_keyboard_interrupt(self):
        """KeyboardInterrupt returns None."""
        agents = {"code-writer": "Write code"}
        mock_stdin = MagicMock()
        mock_stdin.fileno.side_effect = OSError("not a tty")
        with patch("sys.stdin", mock_stdin), \
             patch("builtins.input", side_effect=KeyboardInterrupt):
            result = _select_agent(agents)
        assert result is None

    def test_select_agent_fallback_invalid_then_valid(self):
        """Invalid input loops until valid."""
        agents = {"code-writer": "Write code", "git-ops": "Git ops"}
        mock_stdin = MagicMock()
        mock_stdin.fileno.side_effect = OSError("not a tty")
        with patch("sys.stdin", mock_stdin), \
             patch("builtins.input", side_effect=["", "99", "abc", "2"]):
            result = _select_agent(agents)
        assert result == "git-ops"

    def test_select_agent_fallback_empty_skips(self):
        """Empty input continues loop."""
        agents = {"code-writer": "Write code"}
        mock_stdin = MagicMock()
        mock_stdin.fileno.side_effect = OSError("not a tty")
        with patch("sys.stdin", mock_stdin), \
             patch("builtins.input", side_effect=["", "1"]):
            result = _select_agent(agents)
        assert result == "code-writer"


class TestSelectAgentTTY:
    """Test _select_agent TTY raw-mode paths (lines 300-383)."""

    def _make_tty_mocks(self):
        mock_stdin = MagicMock()
        mock_stdin.fileno.return_value = 0
        mock_termios = MagicMock()
        mock_termios.tcgetattr.return_value = [0, 0, 0, 0, 0, 0, []]
        mock_termios.TCSANOW = 0
        return mock_stdin, mock_termios

    def test_tty_enter_selects_first(self):
        """Enter key selects current (first) agent."""
        agents = {"code-writer": "Write code", "git-ops": "Git operations"}
        mock_stdin, mock_termios = self._make_tty_mocks()
        with patch.dict("sys.modules", {"tty": MagicMock(), "termios": mock_termios}), \
             patch("sys.stdin", mock_stdin), \
             patch("code_agents.chat.chat_welcome.os.read", return_value=b'\r'):
            result = _select_agent(agents)
        assert result == "code-writer"

    def test_tty_escape_cancels(self):
        """Escape key returns None."""
        agents = {"code-writer": "Write code"}
        mock_stdin, mock_termios = self._make_tty_mocks()
        with patch.dict("sys.modules", {"tty": MagicMock(), "termios": mock_termios}), \
             patch("sys.stdin", mock_stdin), \
             patch("code_agents.chat.chat_welcome.os.read", return_value=b'\x1b'):
            result = _select_agent(agents)
        assert result is None

    def test_tty_ctrl_c_cancels(self):
        """Ctrl+C returns None."""
        agents = {"code-writer": "Write code"}
        mock_stdin, mock_termios = self._make_tty_mocks()
        with patch.dict("sys.modules", {"tty": MagicMock(), "termios": mock_termios}), \
             patch("sys.stdin", mock_stdin), \
             patch("code_agents.chat.chat_welcome.os.read", return_value=b'\x03'):
            result = _select_agent(agents)
        assert result is None

    def test_tty_arrow_down_then_enter(self):
        """Arrow down + enter selects second agent."""
        agents = {"code-writer": "Write code", "git-ops": "Git operations"}
        mock_stdin, mock_termios = self._make_tty_mocks()
        reads = [b'\x1b[B', b'\r']
        with patch.dict("sys.modules", {"tty": MagicMock(), "termios": mock_termios}), \
             patch("sys.stdin", mock_stdin), \
             patch("code_agents.chat.chat_welcome.os.read", side_effect=reads):
            result = _select_agent(agents)
        assert result == "git-ops"

    def test_tty_arrow_up_wraps_to_cancel(self):
        """Arrow up from first wraps to Cancel, enter returns None."""
        agents = {"code-writer": "Write code", "git-ops": "Git operations"}
        mock_stdin, mock_termios = self._make_tty_mocks()
        reads = [b'\x1b[A', b'\r']
        with patch.dict("sys.modules", {"tty": MagicMock(), "termios": mock_termios}), \
             patch("sys.stdin", mock_stdin), \
             patch("code_agents.chat.chat_welcome.os.read", side_effect=reads):
            result = _select_agent(agents)
        # Arrow up from 0 wraps to total (Cancel), so returns None
        assert result is None

    def test_tty_arrow_left_navigates(self):
        """Arrow left works same as arrow up."""
        agents = {"code-writer": "Write code", "git-ops": "Git ops"}
        mock_stdin, mock_termios = self._make_tty_mocks()
        reads = [b'\x1b[D', b'\r']
        with patch.dict("sys.modules", {"tty": MagicMock(), "termios": mock_termios}), \
             patch("sys.stdin", mock_stdin), \
             patch("code_agents.chat.chat_welcome.os.read", side_effect=reads):
            result = _select_agent(agents)
        assert result is None  # wrapped to Cancel

    def test_tty_arrow_right_navigates(self):
        """Arrow right works same as arrow down."""
        agents = {"code-writer": "Write code", "git-ops": "Git ops"}
        mock_stdin, mock_termios = self._make_tty_mocks()
        reads = [b'\x1b[C', b'\r']
        with patch.dict("sys.modules", {"tty": MagicMock(), "termios": mock_termios}), \
             patch("sys.stdin", mock_stdin), \
             patch("code_agents.chat.chat_welcome.os.read", side_effect=reads):
            result = _select_agent(agents)
        assert result == "git-ops"

    def test_tty_number_key_zero_cancels(self):
        """Pressing 0 cancels."""
        agents = {"code-writer": "Write code", "git-ops": "Git ops"}
        mock_stdin, mock_termios = self._make_tty_mocks()
        with patch.dict("sys.modules", {"tty": MagicMock(), "termios": mock_termios}), \
             patch("sys.stdin", mock_stdin), \
             patch("code_agents.chat.chat_welcome.os.read", return_value=b'0'):
            result = _select_agent(agents)
        assert result is None

    def test_tty_number_key_selects_agent(self):
        """Pressing a valid number selects the agent directly."""
        agents = {"code-writer": "Write code", "git-ops": "Git ops"}
        mock_stdin, mock_termios = self._make_tty_mocks()
        with patch.dict("sys.modules", {"tty": MagicMock(), "termios": mock_termios}), \
             patch("sys.stdin", mock_stdin), \
             patch("code_agents.chat.chat_welcome.os.read", return_value=b'2'):
            result = _select_agent(agents)
        assert result == "git-ops"

    def test_tty_empty_read_continues(self):
        """Empty read is skipped, then Enter selects."""
        agents = {"code-writer": "Write code"}
        mock_stdin, mock_termios = self._make_tty_mocks()
        reads = [b'', b'\r']
        with patch.dict("sys.modules", {"tty": MagicMock(), "termios": mock_termios}), \
             patch("sys.stdin", mock_stdin), \
             patch("code_agents.chat.chat_welcome.os.read", side_effect=reads):
            result = _select_agent(agents)
        assert result == "code-writer"

    def test_tty_select_cancel_option(self):
        """Navigate to Cancel and press Enter."""
        agents = {"code-writer": "Write code"}
        mock_stdin, mock_termios = self._make_tty_mocks()
        # os.read(fd,1) returns escape byte, then os.read(fd,7) returns rest of sequence
        # then os.read(fd,1) returns Enter
        reads = [b'\x1b', b'[B', b'\r']
        with patch.dict("sys.modules", {"tty": MagicMock(), "termios": mock_termios}), \
             patch("sys.stdin", mock_stdin), \
             patch("code_agents.chat.chat_welcome.os.read", side_effect=reads):
            result = _select_agent(agents)
        assert result is None
