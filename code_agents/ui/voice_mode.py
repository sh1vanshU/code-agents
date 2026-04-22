"""Voice Mode — continuous listen → agent → speak loop.

Hands-free debugging: speak your question, hear the answer.

Usage:
  code-agents voice        # start voice mode
  /voice mode              # start from chat

Modes:
  - push-to-talk: Hold Enter to speak (default)
  - continuous: Always listening (set CODE_AGENTS_VOICE_MODE=continuous)

Exit: say "stop", "exit", "quit", or press Ctrl+C.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

logger = logging.getLogger("code_agents.ui.voice_mode")

EXIT_PHRASES = {"stop", "exit", "quit", "goodbye", "bye", "end", "terminate"}


def start_voice_loop(
    send_message_fn: callable,
    agent: str = "auto-pilot",
    mode: str = "",
) -> None:
    """Start the voice interaction loop.

    Args:
        send_message_fn: Function that sends a message to the agent and returns response text.
        agent: Current agent name.
        mode: "continuous" or "push-to-talk" (default).
    """
    from code_agents.ui.voice_input import is_available as stt_available, listen_and_transcribe
    from code_agents.ui.voice_output import is_available as tts_available, speak

    if not stt_available():
        from code_agents.ui.voice_input import get_install_instructions
        print(get_install_instructions())
        return

    mode = mode or os.getenv("CODE_AGENTS_VOICE_MODE", "push-to-talk")
    tts_ok = tts_available()

    print()
    print("  🎤 Voice Mode Active")
    print(f"     Agent: {agent}")
    print(f"     Mode: {mode}")
    print(f"     TTS: {'ON' if tts_ok else 'OFF (install pyttsx3 for speech output)'}")
    print()
    if mode == "push-to-talk":
        print("  Press Enter to start listening, Ctrl+C to exit.")
    else:
        print("  Listening continuously. Say 'stop' to exit, Ctrl+C to quit.")
    print()

    try:
        while True:
            # Listen phase
            if mode == "push-to-talk":
                try:
                    input("  🎤 Press Enter to speak... ")
                except EOFError:
                    break
            else:
                print("  🎤 Listening...")

            text = listen_and_transcribe(timeout=15, phrase_time_limit=30)

            if not text:
                print("  (no speech detected)")
                continue

            # Check for exit
            if text.strip().lower() in EXIT_PHRASES:
                print("  👋 Voice mode ended.")
                break

            print(f"  📝 You: {text}")
            print("  🔄 Processing...")

            # Send to agent
            try:
                response = send_message_fn(text)
            except Exception as e:
                logger.warning("Agent error in voice mode: %s", e)
                print(f"  ❌ Error: {e}")
                if tts_ok:
                    speak("Sorry, there was an error processing your request.")
                continue

            if response:
                # Show response (truncated for terminal)
                display = response[:500] + "..." if len(response) > 500 else response
                print(f"  🤖 {display}")

                # Speak response
                if tts_ok:
                    print("  🔊 Speaking...")
                    speak(response)
            else:
                print("  (no response)")

            print()

    except KeyboardInterrupt:
        print("\n  👋 Voice mode ended.")


def cmd_voice():
    """Start voice mode — speak to chat with agents.

    Usage:
      code-agents voice              # start voice mode
      code-agents voice --continuous  # always-listening mode
      code-agents voice --engine <e>  # set TTS engine (system/pyttsx3/edge-tts)
    """
    import sys
    from code_agents.ui.voice_input import is_available as stt_available

    if not stt_available():
        from code_agents.ui.voice_input import get_install_instructions
        print(get_install_instructions())
        return

    args = sys.argv[2:]
    mode = "push-to-talk"
    for a in args:
        if a == "--continuous":
            mode = "continuous"
        elif a in ("--help", "-h"):
            print(cmd_voice.__doc__)
            return

    # Build a simple send function using the server API
    from code_agents.cli.cli_helpers import _server_url, _api_post
    url = _server_url()

    def send_message(text: str) -> str:
        """Send message to agent and return response."""
        try:
            resp = _api_post(f"{url}/v1/chat/completions", {
                "model": "auto-pilot",
                "messages": [{"role": "user", "content": text}],
                "stream": False,
            })
            if resp and "choices" in resp:
                return resp["choices"][0].get("message", {}).get("content", "")
        except Exception as e:
            logger.warning("API error: %s", e)
        return ""

    start_voice_loop(send_message, mode=mode)
