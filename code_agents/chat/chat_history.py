"""
Chat history persistence for Code Agents.

Saves and loads chat sessions as JSON files in ~/.code-agents/chat_history/.
Each session tracks: agent, repo, messages, timestamps, and a title derived
from the first user message.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.chat.chat_history")


HISTORY_DIR = Path.home() / ".code-agents" / "chat_history"


def _ensure_dir() -> Path:
    """Ensure the chat history directory exists."""
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    return HISTORY_DIR


def _session_path(session_id: str) -> Path:
    """Return the file path for a given session ID."""
    return _ensure_dir() / f"{session_id}.json"


def _make_title(text: str, max_len: int = 60) -> str:
    """Derive a short title from the first user message."""
    # Take first line, strip whitespace
    line = text.strip().splitlines()[0].strip() if text.strip() else "Untitled"
    if len(line) > max_len:
        line = line[:max_len - 3] + "..."
    return line


# ---------------------------------------------------------------------------
# Session CRUD
# ---------------------------------------------------------------------------


def create_session(
    agent_name: str,
    repo_path: str,
    session_id: Optional[str] = None,
) -> dict:
    """Create a new chat session and persist it. Returns the session dict."""
    sid = session_id or str(uuid.uuid4())
    now = time.time()
    session = {
        "id": sid,
        "agent": agent_name,
        "repo_path": repo_path,
        "title": "New chat",
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }
    _save(session)
    logger.info("Session created: id=%s, agent=%s", sid, agent_name)
    return session


def _save(session: dict) -> None:
    """Write session dict to disk."""
    path = _session_path(session["id"])
    with open(path, "w", encoding="utf-8") as f:
        json.dump(session, f, ensure_ascii=False, indent=2)


def load_session(session_id: str) -> Optional[dict]:
    """Load a session by ID. Returns None if not found."""
    path = _session_path(session_id)
    if not path.exists():
        logger.debug("Session not found: %s", session_id)
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        logger.info("Session loaded: id=%s, messages=%d", session_id, len(data.get("messages", [])))
        return data
    except (json.JSONDecodeError, OSError):
        logger.warning("Failed to load session file: %s", path)
        return None


def add_message(session: dict, role: str, content: str) -> None:
    """Append a message to the session and persist."""
    session["messages"].append({
        "role": role,
        "content": content,
        "timestamp": time.time(),
    })
    session["updated_at"] = time.time()

    # Auto-set title from first user message
    if role == "user" and session.get("title") == "New chat":
        session["title"] = _make_title(content)

    _save(session)


def list_sessions(limit: int = 20, repo_path: Optional[str] = None) -> list[dict]:
    """
    List recent sessions, sorted by updated_at descending.

    Returns lightweight dicts with: id, agent, title, updated_at, repo_path, message_count.
    Optionally filter by repo_path.
    """
    history_dir = _ensure_dir()
    sessions = []

    for f in history_dir.glob("*.json"):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except (json.JSONDecodeError, OSError):
            continue

        if repo_path and data.get("repo_path") != repo_path:
            continue

        sessions.append({
            "id": data.get("id", f.stem),
            "agent": data.get("agent", "?"),
            "title": data.get("title", "Untitled"),
            "updated_at": data.get("updated_at", 0),
            "repo_path": data.get("repo_path", ""),
            "message_count": len(data.get("messages", [])),
        })

    sessions.sort(key=lambda s: s["updated_at"], reverse=True)
    return sessions[:limit]


def save_qa_pairs(session: dict, qa_pairs: list[dict]) -> None:
    """Persist Q&A pairs to the session so they survive resume."""
    session["qa_pairs"] = qa_pairs
    _save(session)


def get_qa_pairs(session: dict) -> list[dict]:
    """Retrieve saved Q&A pairs from a session."""
    return session.get("qa_pairs", [])


def build_qa_context(session: dict) -> str:
    """Build Q&A context string from saved session pairs for prompt injection.

    When resuming a session, this injects previous answers so the agent
    doesn't re-ask the same questions.
    """
    qa_pairs = get_qa_pairs(session)
    if not qa_pairs:
        return ""
    lines = ["Previously answered clarifications (do not re-ask these):"]
    for qa in qa_pairs:
        other_tag = " (custom answer)" if qa.get("is_other") else ""
        lines.append(f"  Q: {qa['question']}")
        lines.append(f"  A: {qa['answer']}{other_tag}")
        lines.append("")
    return "\n".join(lines)


def delete_session(session_id: str) -> bool:
    """Delete a session file. Returns True if deleted."""
    path = _session_path(session_id)
    if path.exists():
        path.unlink()
        return True
    return False


def list_recent_sessions(limit: int = 5) -> list[dict]:
    """List recent chat sessions, newest first."""
    history_dir = _ensure_dir()
    sessions = []
    for f in sorted(history_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            msg_count = len(data.get("messages", []))
            if msg_count == 0:
                continue
            sessions.append({
                "id": f.stem,
                "agent": data.get("agent", "unknown"),
                "messages": msg_count,
                "title": data.get("title", f.stem),
                "mtime": f.stat().st_mtime,
                "age": _format_age(f.stat().st_mtime),
                "path": str(f),
            })
        except Exception:
            continue
    logger.info("Listed %d recent sessions", len(sessions[:limit]))
    return sessions[:limit]


def _format_age(timestamp: float) -> str:
    """Format timestamp as human-readable age."""
    diff = time.time() - timestamp
    if diff < 60:
        return "just now"
    if diff < 3600:
        return f"{int(diff / 60)}m ago"
    if diff < 86400:
        return f"{int(diff / 3600)}h ago"
    if diff < 172800:
        return "yesterday"
    return f"{int(diff / 86400)}d ago"


def load_session(session_id: str) -> Optional[dict]:
    """Load a session by ID."""
    path = _session_path(session_id)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Auto-cleanup: retention + max count
# ---------------------------------------------------------------------------


def cleanup_sessions(
    max_age_days: int = 0,
    max_count: int = 0,
) -> dict:
    """Auto-cleanup old sessions based on retention policy.

    Args:
        max_age_days: Delete sessions older than this (0 = no age limit).
                      Default from CODE_AGENTS_SESSION_RETENTION_DAYS env var.
        max_count: Keep only the N most recent sessions (0 = no limit).
                   Default from CODE_AGENTS_SESSION_MAX_COUNT env var.

    Returns:
        {"deleted_age": N, "deleted_count": N, "remaining": N}
    """
    # Read from env if not specified
    if max_age_days <= 0:
        max_age_days = int(os.getenv("CODE_AGENTS_SESSION_RETENTION_DAYS", "0"))
    if max_count <= 0:
        max_count = int(os.getenv("CODE_AGENTS_SESSION_MAX_COUNT", "0"))

    if max_age_days <= 0 and max_count <= 0:
        return {"deleted_age": 0, "deleted_count": 0, "remaining": 0}

    history_dir = _ensure_dir()
    files = sorted(history_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    now = time.time()
    deleted_age = 0
    deleted_count = 0

    # Phase 1: delete by age
    if max_age_days > 0:
        cutoff = now - (max_age_days * 86400)
        remaining = []
        for f in files:
            try:
                mtime = f.stat().st_mtime
                if mtime < cutoff:
                    f.unlink()
                    deleted_age += 1
                    logger.debug("Deleted expired session: %s (age: %dd)", f.stem, int((now - mtime) / 86400))
                else:
                    remaining.append(f)
            except OSError:
                remaining.append(f)
        files = remaining

    # Phase 2: delete by count (keep newest N)
    if max_count > 0 and len(files) > max_count:
        to_delete = files[max_count:]
        for f in to_delete:
            try:
                f.unlink()
                deleted_count += 1
                logger.debug("Deleted excess session: %s", f.stem)
            except OSError:
                pass
        files = files[:max_count]

    total_deleted = deleted_age + deleted_count
    if total_deleted > 0:
        logger.info("Session cleanup: %d deleted (%d expired, %d excess), %d remaining",
                     total_deleted, deleted_age, deleted_count, len(files))

    return {"deleted_age": deleted_age, "deleted_count": deleted_count, "remaining": len(files)}


def auto_cleanup() -> None:
    """Run cleanup using env var defaults. Safe to call at startup.

    Set CODE_AGENTS_SESSION_RETENTION_DAYS=30 to auto-delete sessions older than 30 days.
    Set CODE_AGENTS_SESSION_MAX_COUNT=100 to keep only the 100 most recent sessions.
    """
    try:
        result = cleanup_sessions()
        if result["deleted_age"] + result["deleted_count"] > 0:
            logger.info("Auto-cleanup: deleted %d sessions (%d expired + %d excess)",
                         result["deleted_age"] + result["deleted_count"],
                         result["deleted_age"], result["deleted_count"])
    except Exception as e:
        logger.debug("Session auto-cleanup failed: %s", e)
