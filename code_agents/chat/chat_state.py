"""Chat REPL session state — initial dict, slash command list, resume helpers."""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("code_agents.chat.chat_state")

# Tab-completion list for readline / prompt_toolkit (keep in sync with slash_registry)
SLASH_COMMANDS: list[str] = [
    "/help", "/quit", "/exit", "/agents", "/agent", "/run", "/exec", "/execute", "/open",
    "/restart", "/rules", "/skills", "/tokens", "/endpoints", "/session", "/clear", "/history",
    "/resume", "/delete-chat", "/setup", "/memory", "/plan", "/superpower", "/export", "/mcp",
    "/btw", "/voice", "/model", "/backend", "/bash", "/stats", "/layout", "/repo",
    "/generate-tests", "/blame", "/investigate", "/review-reply", "/config-diff", "/flags",
    "/kb", "/pair", "/deps", "/coverage-boost", "/refactor", "/pr-preview", "/verify",
    "/compile", "/style", "/impact", "/solve", "/profile", "/mutate", "/testdata",
    "/bg", "/fg",
]


def initial_chat_state(agent_name: str, repo_path: str, role: str) -> dict[str, Any]:
    """Build the default in-memory state dict for a chat session."""
    return {
        "agent": agent_name,
        "session_id": None,
        "repo_path": repo_path,
        "_chat_session": None,
        "user_role": role,
    }


def apply_resume_session(
    state: dict[str, Any],
    resume_id: str,
) -> tuple[bool, Optional[str]]:
    """Load a session by UUID into ``state``. Returns (ok, agent_name or None)."""
    from .chat_history import get_qa_pairs as _get_qa
    from .chat_history import load_session as _load_sess

    loaded = _load_sess(resume_id.strip())
    if not loaded:
        return False, None
    state["agent"] = loaded["agent"]
    state["session_id"] = loaded.get("_server_session_id")
    state["_chat_session"] = loaded
    saved_qa = _get_qa(loaded)
    if saved_qa:
        state["_qa_pairs"] = saved_qa
    return True, loaded["agent"]
