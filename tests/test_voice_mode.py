"""Tests for code_agents.voice_mode — continuous voice interaction loop."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import pytest


class TestExitPhrases:
    """Tests for exit phrase detection."""

    def test_exit_phrases_exist(self):
        from code_agents.ui.voice_mode import EXIT_PHRASES
        assert "stop" in EXIT_PHRASES
        assert "exit" in EXIT_PHRASES
        assert "quit" in EXIT_PHRASES


class TestStartVoiceLoop:
    """Tests for start_voice_loop function."""

    @patch("code_agents.ui.voice_output.is_available", return_value=False)
    @patch("code_agents.ui.voice_input.is_available", return_value=False)
    def test_stt_unavailable_shows_instructions(self, mock_stt, mock_tts, capsys):
        """Should show install instructions when STT is unavailable."""
        mock_send = MagicMock()
        from code_agents.ui.voice_mode import start_voice_loop
        start_voice_loop(mock_send)
        out = capsys.readouterr().out
        assert "install" in out.lower() or "pip" in out.lower() or "speech" in out.lower()
        mock_send.assert_not_called()

    @patch("code_agents.ui.voice_output.speak")
    @patch("code_agents.ui.voice_output.is_available", return_value=True)
    @patch("code_agents.ui.voice_input.listen_and_transcribe", return_value="exit")
    @patch("code_agents.ui.voice_input.is_available", return_value=True)
    def test_exit_phrase_ends_loop(self, mock_stt_avail, mock_listen, mock_tts_avail, mock_speak, capsys):
        """Loop should exit when user says exit phrase."""
        mock_send = MagicMock(return_value="response")
        from code_agents.ui.voice_mode import start_voice_loop
        start_voice_loop(mock_send, mode="continuous")
        # Should NOT have called send_message since "exit" is an exit phrase
        mock_send.assert_not_called()

    @patch("code_agents.ui.voice_output.speak")
    @patch("code_agents.ui.voice_output.is_available", return_value=True)
    @patch("code_agents.ui.voice_input.listen_and_transcribe", side_effect=[None, "exit"])
    @patch("code_agents.ui.voice_input.is_available", return_value=True)
    def test_empty_input_continues(self, mock_stt_avail, mock_listen, mock_tts_avail, mock_speak, capsys):
        """Loop should continue on empty input."""
        mock_send = MagicMock()
        from code_agents.ui.voice_mode import start_voice_loop
        start_voice_loop(mock_send, mode="continuous")
        # Should have called listen twice (first None, then "exit")
        assert mock_listen.call_count == 2
        mock_send.assert_not_called()

    @patch("code_agents.ui.voice_output.speak")
    @patch("code_agents.ui.voice_output.is_available", return_value=True)
    @patch("code_agents.ui.voice_input.listen_and_transcribe", side_effect=["hello", "exit"])
    @patch("code_agents.ui.voice_input.is_available", return_value=True)
    def test_sends_message_to_agent(self, mock_stt_avail, mock_listen, mock_tts_avail, mock_speak, capsys):
        """Loop should send transcribed text to the agent."""
        mock_send = MagicMock(return_value="agent response")
        from code_agents.ui.voice_mode import start_voice_loop
        start_voice_loop(mock_send, mode="continuous")
        mock_send.assert_called_once_with("hello")

    @patch("code_agents.ui.voice_output.speak")
    @patch("code_agents.ui.voice_output.is_available", return_value=True)
    @patch("code_agents.ui.voice_input.listen_and_transcribe", side_effect=["hello", "exit"])
    @patch("code_agents.ui.voice_input.is_available", return_value=True)
    def test_speaks_response(self, mock_stt_avail, mock_listen, mock_tts_avail, mock_speak, capsys):
        """Loop should speak the agent response via TTS."""
        mock_send = MagicMock(return_value="agent response")
        from code_agents.ui.voice_mode import start_voice_loop
        start_voice_loop(mock_send, mode="continuous")
        mock_speak.assert_called_once_with("agent response")

    @patch("code_agents.ui.voice_output.is_available", return_value=True)
    @patch("code_agents.ui.voice_input.listen_and_transcribe", side_effect=["hello", "exit"])
    @patch("code_agents.ui.voice_input.is_available", return_value=True)
    def test_handles_agent_error(self, mock_stt_avail, mock_listen, mock_tts_avail, capsys):
        """Loop should handle agent errors gracefully."""
        mock_send = MagicMock(side_effect=Exception("API down"))
        from code_agents.ui.voice_mode import start_voice_loop
        with patch("code_agents.ui.voice_output.speak"):
            start_voice_loop(mock_send, mode="continuous")
        out = capsys.readouterr().out
        assert "Error" in out or "error" in out.lower()

    @patch("code_agents.ui.voice_output.is_available", return_value=True)
    @patch("code_agents.ui.voice_input.listen_and_transcribe", side_effect=KeyboardInterrupt)
    @patch("code_agents.ui.voice_input.is_available", return_value=True)
    def test_keyboard_interrupt(self, mock_stt_avail, mock_listen, mock_tts_avail, capsys):
        """Loop should handle Ctrl+C gracefully."""
        mock_send = MagicMock()
        from code_agents.ui.voice_mode import start_voice_loop
        # Should not raise
        start_voice_loop(mock_send, mode="continuous")


class TestCmdVoice:
    """Tests for the cmd_voice entry point in voice_mode."""

    @patch("code_agents.ui.voice_input.is_available", return_value=False)
    def test_cmd_voice_no_stt(self, mock_avail, capsys):
        """Should show install instructions when STT unavailable."""
        from code_agents.ui.voice_mode import cmd_voice
        cmd_voice()
        out = capsys.readouterr().out
        assert "install" in out.lower() or "pip" in out.lower() or "speech" in out.lower()
