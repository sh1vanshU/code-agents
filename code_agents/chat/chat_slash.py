"""Slash command handlers for the chat REPL.

Thin router that dispatches to specialized handler modules:
- chat_slash_nav.py      — Navigation & help (/help, /quit, /restart, /open, /setup)
- chat_slash_session.py  — Session management (/session, /clear, /history, /resume, /delete-chat, /export)
- chat_slash_agents.py   — Agent & skill ops (/agent, /agents, /rules, /skills, /tokens, /stats, /memory)
- chat_slash_ops.py      — Runtime operations (/run, /exec, /bash, /btw, /repo, /endpoints, /superpower, /layout, /voice, /plan, /mcp)
- chat_slash_config.py   — Config switching (/model, /backend)
- chat_slash_analysis.py — Code analysis (/investigate, /blame, /generate-tests, /refactor, /deps, /config-diff, /flags, /pr-preview, /impact, /solve, /review-reply, /qa-suite, /kb)
- chat_slash_tools.py    — Interactive tools (/pair, /coverage-boost, /mutate, /testdata, /profile, /compile, /verify, /style)
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger("code_agents.chat.chat_slash")

from .chat_ui import yellow, dim


def _handle_command(cmd: str, state: dict, url: str) -> Optional[str]:
    """
    Handle a slash command. Returns None to continue, or "quit" to exit.
    Modifies state dict in-place.

    This is a thin router that dispatches to specialized handler modules.
    """
    from .slash_registry import SLASH_REGISTRY

    parts = cmd.strip().rstrip(";").strip().split(None, 1)
    command = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""
    logger.info("Slash command received: %s", command)

    entry = SLASH_REGISTRY.get(command)
    if not entry:
        for _k, e in SLASH_REGISTRY.items():
            if command in e.aliases:
                entry = e
                break

    if entry:
        mod = __import__(
            f"code_agents.chat.{entry.handler_module}",
            fromlist=[entry.handler_func],
        )
        handler = getattr(mod, entry.handler_func)
        return handler(command, arg, state, url)

    print(yellow(f"  Unknown command: {command}"))
    print(dim("  Type /help for available commands"))
    return None
