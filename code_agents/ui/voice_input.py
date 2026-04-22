"""
Voice Input — speech-to-text for hands-free chat operation.

Optional dependency: pip install SpeechRecognition PyAudio
Or: pip install code-agents[voice]

Uses Google Speech API (free) by default. Whisper for offline.
Config: CODE_AGENTS_VOICE_ENGINE=google|whisper|system
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("code_agents.ui.voice_input")


def is_available() -> bool:
    """Check if speech recognition is installed."""
    try:
        import speech_recognition  # noqa: F401
        return True
    except ImportError:
        return False


def listen_and_transcribe(
    engine: str = "",
    timeout: int = 10,
    phrase_time_limit: int = 30,
) -> str:
    """Listen to microphone and return transcribed text.

    Returns empty string on failure or if user says nothing.
    """
    if not is_available():
        return ""

    engine = engine or os.getenv("CODE_AGENTS_VOICE_ENGINE", "google")

    import speech_recognition as sr

    recognizer = sr.Recognizer()
    recognizer.energy_threshold = 300
    recognizer.dynamic_energy_threshold = True

    try:
        with sr.Microphone() as source:
            logger.info("Adjusting for ambient noise...")
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            logger.info("Listening...")
            audio = recognizer.listen(
                source,
                timeout=timeout,
                phrase_time_limit=phrase_time_limit,
            )
    except sr.WaitTimeoutError:
        logger.info("No speech detected within timeout")
        return ""
    except Exception as e:
        logger.warning("Microphone error: %s", e)
        return ""

    # Transcribe
    try:
        if engine == "whisper":
            text = recognizer.recognize_whisper(audio, language="en")
        elif engine == "system":
            # Use macOS built-in
            text = recognizer.recognize_google(audio)  # fallback
        else:
            # Default: Google Speech API (free, no key needed)
            text = recognizer.recognize_google(audio)

        logger.info("Transcribed: %s", text[:100])
        return text.strip()
    except sr.UnknownValueError:
        logger.info("Could not understand audio")
        return ""
    except sr.RequestError as e:
        logger.warning("Speech API error: %s", e)
        return ""
    except Exception as e:
        logger.warning("Transcription failed: %s", e)
        return ""


def get_install_instructions() -> str:
    """Return install instructions for voice dependencies."""
    return (
        "Voice input requires additional dependencies:\n"
        "  pip install SpeechRecognition PyAudio\n"
        "  or: pip install code-agents[voice]\n"
        "\n"
        "On macOS, you may also need:\n"
        "  brew install portaudio\n"
        "\n"
        "Then try /voice again."
    )
