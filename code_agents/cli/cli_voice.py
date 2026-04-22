"""CLI voice command — start voice mode."""

from __future__ import annotations

import logging

logger = logging.getLogger("code_agents.cli.cli_voice")


def cmd_voice():
    """Start voice mode — speak to chat with agents.

    Usage:
      code-agents voice              # start voice mode (push-to-talk)
      code-agents voice --continuous  # always-listening mode
    """
    from code_agents.ui.voice_mode import cmd_voice as _voice_main
    _voice_main()
