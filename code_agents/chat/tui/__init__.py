"""Textual-based Terminal UI for Code Agents chat.

Enable with: CODE_AGENTS_TUI=1
"""

from __future__ import annotations


def run_chat_tui(
    *,
    state: dict,
    url: str,
    cwd: str,
    nickname: str = "you",
    agent_name: str = "",
    session_start: float = 0.0,
) -> None:
    """Launch the Textual TUI for chat."""
    from .app import ChatTUI

    app = ChatTUI(
        state=state,
        url=url,
        cwd=cwd,
        nickname=nickname,
        agent_name=agent_name,
        session_start=session_start,
    )
    app.run()
