"""
Telemetry — local-only usage analytics for code-agents.

Tracks: agent usage, token costs, commands, errors, sessions.
Storage: SQLite at ~/.code-agents/telemetry.db
Privacy: local only, never sent externally. Toggle: CODE_AGENTS_TELEMETRY=true/false
"""
from __future__ import annotations

import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger("code_agents.observability.telemetry")

DB_PATH = Path.home() / ".code-agents" / "telemetry.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    event_type TEXT NOT NULL,
    agent TEXT DEFAULT '',
    user TEXT DEFAULT '',
    repo TEXT DEFAULT '',
    tokens_in INTEGER DEFAULT 0,
    tokens_out INTEGER DEFAULT 0,
    duration_ms INTEGER DEFAULT 0,
    command TEXT DEFAULT '',
    status TEXT DEFAULT 'ok',
    metadata TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_agent ON events(agent);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type);
"""


def is_enabled() -> bool:
    return os.getenv("CODE_AGENTS_TELEMETRY", "true").strip().lower() not in ("0", "false", "no")


@contextmanager
def _db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH), timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(_SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def record_event(
    event_type: str, agent: str = "", user: str = "", repo: str = "",
    tokens_in: int = 0, tokens_out: int = 0, duration_ms: int = 0,
    command: str = "", status: str = "ok", metadata: str = "",
) -> None:
    if not is_enabled():
        return
    try:
        with _db() as conn:
            conn.execute(
                "INSERT INTO events (event_type,agent,user,repo,tokens_in,tokens_out,duration_ms,command,status,metadata) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (event_type, agent, user, repo, tokens_in, tokens_out, duration_ms, command[:500], status, metadata[:500]),
            )
    except Exception as e:
        logger.debug("Telemetry record failed: %s", e)


def record_message(agent: str, tokens_in: int = 0, tokens_out: int = 0, duration_ms: int = 0, user: str = "", repo: str = "") -> None:
    record_event("message", agent=agent, tokens_in=tokens_in, tokens_out=tokens_out, duration_ms=duration_ms, user=user, repo=repo)


def record_command(agent: str, command: str, status: str = "ok", duration_ms: int = 0, repo: str = "") -> None:
    record_event("command", agent=agent, command=command, status=status, duration_ms=duration_ms, repo=repo)


def record_session(agent: str, user: str = "", repo: str = "", duration_ms: int = 0) -> None:
    record_event("session", agent=agent, user=user, repo=repo, duration_ms=duration_ms)


def record_error(agent: str, error: str, command: str = "", repo: str = "") -> None:
    record_event("error", agent=agent, command=command, status="error", metadata=error, repo=repo)


def get_summary(days: int = 1) -> dict:
    if not DB_PATH.is_file():
        return {"sessions": 0, "messages": 0, "tokens_in": 0, "tokens_out": 0, "commands": 0, "errors": 0, "cost_estimate": 0.0}
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    try:
        with _db() as conn:
            row = conn.execute("SELECT COUNT(*) as total, SUM(tokens_in) as tin, SUM(tokens_out) as tout FROM events WHERE event_type='message' AND timestamp >= ?", (since,)).fetchone()
            messages = row["total"] or 0
            tokens_in = row["tin"] or 0
            tokens_out = row["tout"] or 0
            sessions = conn.execute("SELECT COUNT(*) as c FROM events WHERE event_type='session' AND timestamp >= ?", (since,)).fetchone()["c"] or 0
            commands = conn.execute("SELECT COUNT(*) as c FROM events WHERE event_type='command' AND timestamp >= ?", (since,)).fetchone()["c"] or 0
            errors = conn.execute("SELECT COUNT(*) as c FROM events WHERE event_type='error' AND timestamp >= ?", (since,)).fetchone()["c"] or 0
            cost = (tokens_in * 3 + tokens_out * 15) / 1_000_000
            return {"sessions": sessions, "messages": messages, "tokens_in": tokens_in, "tokens_out": tokens_out, "commands": commands, "errors": errors, "cost_estimate": round(cost, 2)}
    except Exception:
        return {"sessions": 0, "messages": 0, "tokens_in": 0, "tokens_out": 0, "commands": 0, "errors": 0, "cost_estimate": 0.0}


def get_agent_usage(days: int = 7) -> list[dict]:
    if not DB_PATH.is_file():
        return []
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    try:
        with _db() as conn:
            rows = conn.execute("SELECT agent, COUNT(*) as messages, SUM(tokens_in+tokens_out) as tokens FROM events WHERE event_type='message' AND agent!='' AND timestamp>=? GROUP BY agent ORDER BY messages DESC", (since,)).fetchall()
            return [{"agent": r["agent"], "messages": r["messages"], "tokens": r["tokens"] or 0} for r in rows]
    except Exception:
        return []


def get_top_commands(days: int = 7, limit: int = 10) -> list[dict]:
    if not DB_PATH.is_file():
        return []
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    try:
        with _db() as conn:
            rows = conn.execute("SELECT command, COUNT(*) as count, AVG(duration_ms) as avg_ms FROM events WHERE event_type='command' AND command!='' AND timestamp>=? GROUP BY command ORDER BY count DESC LIMIT ?", (since, limit)).fetchall()
            return [{"command": r["command"][:80], "count": r["count"], "avg_ms": int(r["avg_ms"] or 0)} for r in rows]
    except Exception:
        return []


def get_error_summary(days: int = 7) -> list[dict]:
    if not DB_PATH.is_file():
        return []
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
    try:
        with _db() as conn:
            rows = conn.execute("SELECT agent, COUNT(*) as count, metadata FROM events WHERE event_type='error' AND timestamp>=? GROUP BY agent ORDER BY count DESC", (since,)).fetchall()
            return [{"agent": r["agent"], "count": r["count"], "last_error": r["metadata"][:100]} for r in rows]
    except Exception:
        return []


def export_csv(output_path: str, days: int = 30) -> str:
    if not DB_PATH.is_file():
        return ""
    since = (datetime.now() - timedelta(days=days)).isoformat()
    try:
        import csv
        with _db() as conn:
            rows = conn.execute("SELECT * FROM events WHERE timestamp>=? ORDER BY timestamp", (since,)).fetchall()
        with open(output_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "event_type", "agent", "user", "repo", "tokens_in", "tokens_out", "duration_ms", "command", "status", "metadata"])
            for r in rows:
                writer.writerow([r["timestamp"], r["event_type"], r["agent"], r["user"], r["repo"], r["tokens_in"], r["tokens_out"], r["duration_ms"], r["command"], r["status"], r["metadata"]])
        return output_path
    except Exception:
        return ""
