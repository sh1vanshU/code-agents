"""Tests for voice output (TTS) module."""

from __future__ import annotations

import os
from unittest.mock import patch, MagicMock

import pytest

from code_agents.ui.voice_output import (
    is_available, speak, _clean_for_speech, get_install_instructions,
)


class TestIsAvailable:
    """Test TTS availability detection."""

    def test_system_on_macos(self):
        with patch.dict(os.environ, {"CODE_AGENTS_TTS_ENGINE": "system"}):
            with patch("platform.system", return_value="Darwin"):
                assert is_available()

    def test_system_on_linux(self):
        with patch.dict(os.environ, {"CODE_AGENTS_TTS_ENGINE": "system"}):
            with patch("platform.system", return_value="Linux"):
                assert not is_available()

    def test_pyttsx3_installed(self):
        with patch.dict(os.environ, {"CODE_AGENTS_TTS_ENGINE": "pyttsx3"}):
            with patch.dict("sys.modules", {"pyttsx3": MagicMock()}):
                assert is_available()

    def test_pyttsx3_missing(self):
        with patch.dict(os.environ, {"CODE_AGENTS_TTS_ENGINE": "pyttsx3"}):
            import sys as _sys
            # Ensure pyttsx3 is not importable
            with patch("builtins.__import__", side_effect=ImportError("no pyttsx3")):
                assert not is_available()

    def test_unknown_engine(self):
        with patch.dict(os.environ, {"CODE_AGENTS_TTS_ENGINE": "unknown"}):
            assert not is_available()


class TestCleanForSpeech:
    """Test text cleaning for TTS."""

    def test_removes_code_blocks(self):
        text = "Here's code:\n```python\nprint('hello')\n```\nDone."
        cleaned = _clean_for_speech(text)
        assert "print" not in cleaned
        assert "code block omitted" in cleaned

    def test_removes_inline_code(self):
        text = "Use `pip install foo` to install."
        cleaned = _clean_for_speech(text)
        assert "`" not in cleaned

    def test_removes_headers(self):
        text = "### Section Title\nContent here."
        cleaned = _clean_for_speech(text)
        assert "###" not in cleaned
        assert "Section Title" in cleaned

    def test_removes_bold_italic(self):
        text = "This is **bold** and *italic*."
        cleaned = _clean_for_speech(text)
        assert "**" not in cleaned
        assert "*italic*" not in cleaned
        assert "bold" in cleaned

    def test_removes_urls(self):
        text = "Visit https://example.com for details."
        cleaned = _clean_for_speech(text)
        assert "https://" not in cleaned
        assert "link" in cleaned

    def test_removes_markdown_links(self):
        text = "See [the docs](https://docs.example.com) for more."
        cleaned = _clean_for_speech(text)
        assert "the docs" in cleaned
        assert "https://" not in cleaned

    def test_truncates_long_text(self):
        text = "word " * 200  # way more than 500 chars
        cleaned = _clean_for_speech(text)
        assert len(cleaned) < 600
        assert "truncated" in cleaned

    def test_empty_text(self):
        assert _clean_for_speech("") == ""

    def test_preserves_normal_text(self):
        text = "Hello, how are you today?"
        assert _clean_for_speech(text) == text


class TestSpeak:
    """Test the speak function."""

    def test_empty_text(self):
        assert not speak("")
        assert not speak("   ")

    @patch("code_agents.ui.voice_output._speak_system")
    def test_speak_system(self, mock_sys):
        mock_sys.return_value = True
        with patch.dict(os.environ, {"CODE_AGENTS_TTS_ENGINE": "system"}):
            assert speak("hello")
        mock_sys.assert_called_once()

    @patch("code_agents.ui.voice_output._speak_pyttsx3")
    def test_speak_pyttsx3(self, mock_pyttsx3):
        mock_pyttsx3.return_value = True
        with patch.dict(os.environ, {"CODE_AGENTS_TTS_ENGINE": "pyttsx3"}):
            assert speak("hello")

    def test_speak_unknown_engine(self):
        with patch.dict(os.environ, {"CODE_AGENTS_TTS_ENGINE": "nonexistent"}):
            assert not speak("hello")

    @patch("subprocess.run")
    def test_speak_system_calls_say(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        from code_agents.ui.voice_output import _speak_system
        assert _speak_system("hello world")
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "say"
        assert "hello world" in cmd

    @patch("subprocess.run")
    def test_speak_system_with_voice(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        from code_agents.ui.voice_output import _speak_system
        _speak_system("hello", voice="Alex")
        cmd = mock_run.call_args[0][0]
        assert "-v" in cmd
        assert "Alex" in cmd


class TestVoiceMode:
    """Test the voice mode loop."""

    @patch("code_agents.ui.voice_input.is_available", return_value=False)
    def test_voice_loop_no_stt(self, mock_avail, capsys):
        from code_agents.ui.voice_mode import start_voice_loop
        start_voice_loop(lambda x: "response")
        captured = capsys.readouterr()
        assert "install" in captured.out.lower() or "pip" in captured.out.lower()

    @patch("code_agents.ui.voice_output.is_available", return_value=False)
    @patch("code_agents.ui.voice_input.listen_and_transcribe", side_effect=["hello", "stop"])
    @patch("code_agents.ui.voice_input.is_available", return_value=True)
    def test_voice_loop_exit_phrase(self, mock_avail, mock_listen, mock_tts, capsys):
        from code_agents.ui.voice_mode import start_voice_loop
        responses = iter(["test response"])

        def send(text):
            return next(responses, "")

        start_voice_loop(send, mode="continuous")
        captured = capsys.readouterr()
        assert "Voice mode ended" in captured.out or "Voice Mode" in captured.out


class TestInstallInstructions:
    """Test install instructions."""

    def test_instructions(self):
        text = get_install_instructions()
        assert "pyttsx3" in text
        assert "edge-tts" in text
        assert "say" in text
