"""Session management slash commands: /session, /clear, /history, /resume, /delete-chat, /export."""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional

logger = logging.getLogger("code_agents.chat.chat_slash_session")

from .chat_ui import bold, green, yellow, red, cyan, dim, magenta


def _handle_session(command: str, arg: str, state: dict, url: str) -> Optional[str]:
    """Handle session-related slash commands."""

    if command == "/session":
        from code_agents.chat.chat_history import list_sessions
        current_sid = state.get("session_id")
        sessions = list_sessions()
        print()
        if current_sid:
            print(f"  {dim('Current:')} {cyan(current_sid)}")
            print()
        if sessions:
            from code_agents.chat.chat_history import HISTORY_DIR
            print(bold("  Saved sessions (newest first):"))
            for s in sessions[:15]:  # show last 15
                agent_label = cyan(s.get("agent", "?"))
                title = s.get("title", "Untitled")[:40]
                msgs = s.get("message_count", 0)
                sid = s["id"][:8]
                # Get file size
                session_file = HISTORY_DIR / f"{s['id']}.json"
                try:
                    size_bytes = session_file.stat().st_size
                    if size_bytes < 1024:
                        size_str = f"{size_bytes}B"
                    elif size_bytes < 1024 * 1024:
                        size_str = f"{size_bytes / 1024:.1f}KB"
                    else:
                        size_str = f"{size_bytes / (1024 * 1024):.1f}MB"
                except OSError:
                    size_str = "?"
                marker = f" {green('← current')}" if current_sid and s["id"].startswith(current_sid[:8]) else ""
                print(f"    {dim(sid)}  {agent_label:<20} {title:<40} {dim(f'{msgs} msgs · {size_str}')}{marker}")
            if len(sessions) > 15:
                print(dim(f"    ... and {len(sessions) - 15} more"))
            print()
            print(dim(f"  Resume: /resume <id>  |  Delete: /delete-chat <id>"))
        else:
            print(dim("  No saved sessions yet."))
        print()

    elif command == "/clear":
        state["session_id"] = None
        state["_chat_session"] = None
        print(green("  ✓ Session cleared. Next message starts fresh."))

    elif command == "/history":
        from .chat_history import list_sessions as _list_sessions
        repo = state.get("repo_path")
        show_all = arg == "--all"
        sessions = _list_sessions(limit=15, repo_path=None if show_all else repo)
        print()
        if not sessions:
            print(dim("  No chat history found."))
        else:
            print(bold("  Recent chats:"))
            print()
            for i, s in enumerate(sessions, 1):
                ts = datetime.fromtimestamp(s["updated_at"]).strftime("%b %d %H:%M")
                agent_label = cyan(s["agent"])
                msg_count = s["message_count"]
                title = s["title"]
                repo_name = os.path.basename(s.get("repo_path", ""))
                sid = s["id"]
                print(f"    {cyan(sid)}")
                print(f"      {title}")
                print(f"      {agent_label}  {dim(f'{msg_count} msgs')}  {dim(ts)}  {dim(repo_name)}")
            print()
            print(dim("  Use /resume <session-id> to continue a chat"))
            if not show_all:
                print(dim("  Use /history --all to show chats from all repos"))
        print()

    elif command == "/resume":
        if not arg:
            print(yellow("  Usage: /resume <session-id>  (from /history list)"))
            return None
        from .chat_history import load_session as _load_sess
        loaded = _load_sess(arg.strip())
        if loaded:
            state["agent"] = loaded["agent"]
            state["session_id"] = loaded.get("_server_session_id")
            state["_chat_session"] = loaded
            # Restore Q&A pairs from session so agent doesn't re-ask
            from .chat_history import get_qa_pairs as _get_qa
            saved_qa = _get_qa(loaded)
            if saved_qa:
                state["_qa_pairs"] = saved_qa
            print()
            print(green(f"  \u2713 Resumed: {bold(loaded['title'])}"))
            print(f"    Agent: {cyan(loaded['agent'])}  Messages: {len(loaded['messages'])}")
            recent = loaded["messages"][-4:]
            if recent:
                print()
                print(dim("  Recent context:"))
                for msg in recent:
                    role_label = green("you") if msg["role"] == "user" else magenta(loaded["agent"])
                    preview = msg["content"][:100]
                    if len(msg["content"]) > 100:
                        preview += "..."
                    print(f"    {bold(role_label)} \u203a {dim(preview)}")
            print()
        else:
            print(red(f"  Session '{arg}' not found. Use /history to list sessions."))

    elif command == "/delete-chat":
        if not arg:
            print(yellow("  Usage: /delete-chat <session-id>  (from /history list)"))
            return None
        from .chat_history import delete_session as _del
        if _del(arg.strip()):
            print(green(f"  ✓ Deleted session: {arg.strip()}"))
        else:
            print(red(f"  Session '{arg}' not found. Use /history to list sessions."))

    elif command == "/export":
        from pathlib import Path as _ExPath
        from datetime import datetime as _ExDt
        from code_agents.chat.chat_history import _get_history_dir
        export_dir = _ExPath(_get_history_dir())
        export_file = export_dir / f"export_{_ExDt.now().strftime('%Y%m%d_%H%M%S')}.md"
        current_agent = state.get("agent", "unknown")
        lines = [f"# Chat Export — {current_agent}", f"Date: {_ExDt.now().strftime('%Y-%m-%d %H:%M')}", ""]
        for msg in state.get("messages", []):
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                lines.append(f"**You:** {content}")
            else:
                lines.append(f"**{current_agent}:** {content}")
            lines.append("")
        export_file.write_text("\n".join(lines), encoding="utf-8")
        print(green(f"  ✓ Exported to {export_file}"))
        print()

    else:
        return "_not_handled"

    return None
