"""Skill loading and questionnaire flows tied to assistant messages.

Interactive [SKILL:name], [DELEGATE:agent], and [QUESTION:] handling after a streamed
response lives in :mod:`code_agents.chat.chat_response` (``handle_post_response``).
This module exists as a stable import surface for the Phase 5 layout described in Roadmap.md.
"""

from __future__ import annotations

import logging

# Re-export for callers that prefer a "skill runner" name
from .chat_response import handle_post_response  # noqa: F401

logger = logging.getLogger("code_agents.chat.chat_skill_runner")
