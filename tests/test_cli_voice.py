"""Tests for code_agents.cli.cli_voice — CLI voice command."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest


class TestCmdVoice:
    """Tests for the cmd_voice CLI entry point."""

    @patch("code_agents.ui.voice_mode.cmd_voice")
    def test_voice_delegates_to_voice_mode(self, mock_voice_main):
        """cli_voice.cmd_voice should delegate to voice_mode.cmd_voice."""
        from code_agents.cli.cli_voice import cmd_voice
        cmd_voice()
        mock_voice_main.assert_called_once()

    @patch("code_agents.ui.voice_mode.cmd_voice", side_effect=KeyboardInterrupt)
    def test_voice_keyboard_interrupt(self, mock_voice_main):
        """Should propagate KeyboardInterrupt (handled by caller)."""
        from code_agents.cli.cli_voice import cmd_voice
        with pytest.raises(KeyboardInterrupt):
            cmd_voice()

    @patch("code_agents.ui.voice_mode.cmd_voice", side_effect=ImportError("No module named 'speech_recognition'"))
    def test_voice_import_error(self, mock_voice_main):
        """Should propagate ImportError when voice deps missing."""
        from code_agents.cli.cli_voice import cmd_voice
        with pytest.raises(ImportError):
            cmd_voice()
