"""Voice Output — text-to-speech for agent responses.

Optional dependency: pip install pyttsx3
Or: pip install code-agents[voice]

Engines:
  - pyttsx3: Offline, cross-platform (default)
  - system: macOS `say` command
  - edge-tts: Azure free TTS (requires edge-tts package + async)

Config: CODE_AGENTS_TTS_ENGINE=pyttsx3|system|edge-tts
"""

from __future__ import annotations

import logging
import os
import re
import subprocess

logger = logging.getLogger("code_agents.ui.voice_output")


def is_available() -> bool:
    """Check if text-to-speech is available."""
    engine = os.getenv("CODE_AGENTS_TTS_ENGINE", "system")
    if engine == "system":
        # macOS `say` is always available on macOS
        import platform
        return platform.system() == "Darwin"
    elif engine == "pyttsx3":
        try:
            import pyttsx3  # noqa: F401
            return True
        except ImportError:
            return False
    elif engine == "edge-tts":
        try:
            import edge_tts  # noqa: F401
            return True
        except ImportError:
            return False
    return False


def speak(text: str, engine: str = "", voice: str = "", rate: int = 0) -> bool:
    """Convert text to speech.

    Args:
        text: Text to speak
        engine: TTS engine override (default from env)
        voice: Voice name override
        rate: Speech rate override (words per minute)

    Returns:
        True if speech was produced, False on failure
    """
    if not text or not text.strip():
        return False

    engine = engine or os.getenv("CODE_AGENTS_TTS_ENGINE", "system")
    cleaned = _clean_for_speech(text)
    if not cleaned:
        return False

    try:
        if engine == "system":
            return _speak_system(cleaned, voice)
        elif engine == "pyttsx3":
            return _speak_pyttsx3(cleaned, voice, rate)
        elif engine == "edge-tts":
            return _speak_edge_tts(cleaned, voice)
        else:
            logger.warning("Unknown TTS engine: %s", engine)
            return False
    except Exception as e:
        logger.warning("TTS error (%s): %s", engine, e)
        return False


def _speak_system(text: str, voice: str = "") -> bool:
    """Use macOS `say` command."""
    cmd = ["say"]
    if voice:
        cmd.extend(["-v", voice])
    cmd.append(text)
    try:
        result = subprocess.run(cmd, capture_output=True, timeout=30)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.warning("System TTS error: %s", e)
        return False


def _speak_pyttsx3(text: str, voice: str = "", rate: int = 0) -> bool:
    """Use pyttsx3 offline TTS."""
    import pyttsx3
    engine = pyttsx3.init()
    if rate:
        engine.setProperty("rate", rate)
    if voice:
        voices = engine.getProperty("voices")
        for v in voices:
            if voice.lower() in v.name.lower():
                engine.setProperty("voice", v.id)
                break
    engine.say(text)
    engine.runAndWait()
    return True


def _speak_edge_tts(text: str, voice: str = "") -> bool:
    """Use edge-tts (Azure free). Requires async — runs in subprocess."""
    voice = voice or "en-US-GuyNeural"
    try:
        # edge-tts has a CLI: edge-tts --text "..." --voice "..."
        result = subprocess.run(
            ["edge-tts", "--text", text, "--voice", voice],
            capture_output=True, timeout=30,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        logger.warning("edge-tts error: %s", e)
        return False


def _clean_for_speech(text: str) -> str:
    """Clean text for TTS — strip markdown, code blocks, URLs."""
    # Remove code blocks
    text = re.sub(r"```[\s\S]*?```", "code block omitted", text)
    # Remove inline code
    text = re.sub(r"`[^`]+`", "", text)
    # Remove markdown headers
    text = re.sub(r"^#+\s+", "", text, flags=re.MULTILINE)
    # Remove markdown bold/italic
    text = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,3}([^_]+)_{1,3}", r"\1", text)
    # Remove URLs
    text = re.sub(r"https?://\S+", "link", text)
    # Remove markdown links
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # Collapse whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()

    # Truncate long responses for speech
    max_chars = int(os.getenv("CODE_AGENTS_TTS_MAX_CHARS", "500"))
    if len(text) > max_chars:
        text = text[:max_chars] + "... response truncated for speech."

    return text


def get_install_instructions() -> str:
    """Return install instructions for TTS dependencies."""
    return (
        "Text-to-speech options:\n"
        "  • macOS: Built-in (uses 'say' command, no install needed)\n"
        "  • Offline: pip install pyttsx3\n"
        "  • High quality: pip install edge-tts\n"
        "\n"
        "Set engine: CODE_AGENTS_TTS_ENGINE=system|pyttsx3|edge-tts\n"
    )
