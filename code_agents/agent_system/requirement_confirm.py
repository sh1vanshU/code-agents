"""Requirement Confirmation — enforced spec-before-execution gate.

Before an agent starts working on a non-trivial request, it first produces
a structured requirement specification.  The user confirms, edits, or
replaces it.  Only after confirmation does the agent execute.

Simple confirmations ("yes", "ok", "go ahead") bypass the spec step and
let the agent proceed immediately.
"""

from __future__ import annotations

import logging
import os
import re
from enum import Enum

logger = logging.getLogger("code_agents.agent_system.requirement_confirm")


# ---------------------------------------------------------------------------
# Status enum
# ---------------------------------------------------------------------------

class RequirementStatus(str, Enum):
    """Lifecycle of a requirement confirmation cycle."""
    NONE = "none"              # Feature disabled or no active requirement
    PENDING = "pending"        # Waiting for user to confirm/edit the spec
    CONFIRMED = "confirmed"    # User confirmed — agent may execute


# ---------------------------------------------------------------------------
# Simple confirmation detection
# ---------------------------------------------------------------------------

_CONFIRM_EXACT: set[str] = {
    "yes", "y", "ok", "okay", "go", "go ahead", "proceed", "confirm",
    "confirmed", "do it", "looks good", "lgtm", "approved", "yep", "sure",
    "correct", "continue", "start", "that's right", "thats right",
    "perfect", "good", "fine", "sounds good", "right", "exactly", "agreed",
    "ship it", "execute", "run it", "go for it", "all good", "no changes",
    "approve", "accepted", "done", "yes please",
}

_CONFIRM_PREFIX_RE = re.compile(
    r"^(yes|ok|okay|sure|go ahead|proceed|confirm|approved|lgtm|looks good|sounds good)"
    r"[,.\s!]*"
    r"(?:please|thanks|thank you|go ahead|that works|looks good|no changes)?[.!]*$",
    re.IGNORECASE,
)


def is_simple_confirmation(text: str) -> bool:
    """Return True if *text* is a simple confirmation that should bypass spec generation.

    Matches: "yes", "ok", "go ahead", "looks good, thanks", etc.
    Does NOT match: "yes, but also add logging", "ok change the DB schema too".
    """
    cleaned = text.strip().lower().rstrip(".!,")
    if cleaned in _CONFIRM_EXACT:
        return True
    if len(cleaned) < 40 and _CONFIRM_PREFIX_RE.match(cleaned):
        return True
    return False


# ---------------------------------------------------------------------------
# Feature toggle
# ---------------------------------------------------------------------------

def is_confirm_enabled(state: dict | None = None) -> bool:
    """Check if requirement confirmation is enabled.

    Disabled by:
    - ``CODE_AGENTS_REQUIRE_CONFIRM=false`` env var
    - ``state["_require_confirm_enabled"] == False`` (per-session toggle via /confirm off)
    - Superpower mode
    """
    env = os.getenv("CODE_AGENTS_REQUIRE_CONFIRM", "true").strip().lower()
    if env in ("0", "false", "no", "off"):
        return False
    if state:
        if state.get("superpower"):
            return False
        if state.get("_require_confirm_enabled") is False:
            return False
    return True


# ---------------------------------------------------------------------------
# Should this input trigger requirement confirmation?
# ---------------------------------------------------------------------------

_SKIP_PREFIXES = ("/", "!", "#")  # slash commands, shell escapes, comments

# Patterns that suggest a real task (not a quick question)
_TASK_VERBS_RE = re.compile(
    r"\b(add|fix|refactor|create|build|implement|change|update|modify|remove|"
    r"delete|migrate|rewrite|convert|replace|move|rename|deploy|setup|configure|"
    r"install|integrate|optimize|debug|investigate|analyze|write|design|test)\b",
    re.IGNORECASE,
)


def should_confirm(user_input: str, state: dict | None = None) -> bool:
    """Return True if this user input should go through the requirement confirmation gate.

    Returns False for:
    - Simple confirmations
    - Slash commands
    - Very short inputs (< 15 chars)
    - When confirmation is disabled
    """
    if not is_confirm_enabled(state):
        return False

    text = user_input.strip()

    # Skip slash commands, shell escapes
    if any(text.startswith(p) for p in _SKIP_PREFIXES):
        return False

    # Skip simple confirmations
    if is_simple_confirmation(text):
        return False

    # Skip very short inputs — likely a quick question or follow-up
    if len(text) < 15:
        return False

    # Only trigger for messages that look like tasks (contain action verbs)
    if not _TASK_VERBS_RE.search(text):
        return False

    return True


# ---------------------------------------------------------------------------
# System prompt fragments
# ---------------------------------------------------------------------------

_SPEC_ONLY_PROMPT = """
--- Requirement Specification Mode ---
You are in REQUIREMENT SPECIFICATION mode. Do NOT execute commands, write code, or make changes yet.

Instead, analyze the user's request and produce a STRUCTURED REQUIREMENT SPECIFICATION:

## Requirement Specification

**Objective:** <one-line summary of what needs to be done>

**Scope:**
1. <specific deliverable or change>
2. <specific deliverable or change>
...

**Files likely affected:**
- <file path> — <what changes>

**Assumptions:**
- <assumption about the request>

**Out of scope:**
- <what this does NOT include>

**Risks:**
- <potential issues or side effects>

After producing the spec, end with:
"Please confirm this requirement, suggest edits, or say **Go ahead** to proceed."

Do NOT execute any commands or write any code in this response.
--- End Requirement Specification Mode ---
"""


def build_spec_prompt() -> str:
    """Return the system context fragment that tells the agent to produce a spec only."""
    return _SPEC_ONLY_PROMPT


_CONFIRMED_TEMPLATE = """
--- Confirmed Requirement ---
The user has reviewed and confirmed the following requirement specification.
Proceed with implementation based on this confirmed spec.

{spec}
--- End Confirmed Requirement ---
"""


def format_confirmed_spec(spec_text: str) -> str:
    """Wrap a confirmed requirement spec for injection into the system context."""
    return _CONFIRMED_TEMPLATE.format(spec=spec_text.strip())
