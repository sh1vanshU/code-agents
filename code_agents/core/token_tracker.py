"""
Token usage tracking — per message, session, day, month.

Writes to CSV at ~/.code-agents/token_usage.csv for analysis.
Tracks: backend, model, agent, input_tokens, output_tokens, cost, timestamp.
"""

from __future__ import annotations

import csv
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.core.token_tracker")

USAGE_CSV_PATH = Path.home() / ".code-agents" / "token_usage.csv"

CSV_HEADERS = [
    "timestamp", "date", "month", "year", "session_id", "agent",
    "backend", "model", "input_tokens", "output_tokens",
    "cache_read_tokens", "cache_write_tokens",
    "total_tokens", "cost_usd", "duration_ms",
]


@dataclass
class SessionUsage:
    """Tracks token usage for a terminal session."""
    session_id: str = ""
    agent: str = ""
    backend: str = ""
    model: str = ""
    messages: int = 0
    total_input: int = 0
    total_output: int = 0
    total_cache_read: int = 0
    total_cache_write: int = 0
    total_cost: float = 0.0
    total_duration_ms: int = 0
    start_time: float = field(default_factory=time.monotonic)


def check_cost_guard() -> bool:
    """
    Check if session token spend exceeds the cost guard threshold.

    Set CODE_AGENTS_MAX_SESSION_TOKENS to limit total tokens per session.
    Returns True if within limit, False if exceeded.
    """
    max_tokens_str = os.getenv("CODE_AGENTS_MAX_SESSION_TOKENS", "").strip()
    if not max_tokens_str:
        return True  # no limit set
    try:
        max_tokens = int(max_tokens_str)
    except ValueError:
        return True
    total = _current_session.total_input + _current_session.total_output
    return total < max_tokens


def get_cost_guard_status() -> Optional[dict]:
    """Get cost guard status. Returns None if no limit, or dict with current/max."""
    max_tokens_str = os.getenv("CODE_AGENTS_MAX_SESSION_TOKENS", "").strip()
    if not max_tokens_str:
        return None
    try:
        max_tokens = int(max_tokens_str)
    except ValueError:
        return None
    total = _current_session.total_input + _current_session.total_output
    return {
        "current": total,
        "max": max_tokens,
        "exceeded": total >= max_tokens,
        "remaining": max(0, max_tokens - total),
    }


# Global session tracker (reset per terminal session)
_current_session = SessionUsage()


def init_session(session_id: str = "", agent: str = "", backend: str = "", model: str = "") -> None:
    """Initialize tracking for a new terminal session."""
    logger.info("Token tracking session initialized: agent=%s, backend=%s, model=%s", agent, backend, model)
    global _current_session
    _current_session = SessionUsage(
        session_id=session_id,
        agent=agent,
        backend=backend,
        model=model,
    )


def record_usage(
    agent: str,
    backend: str,
    model: str,
    usage: dict | None,
    cost_usd: float = 0.0,
    duration_ms: int = 0,
    session_id: str = "",
) -> None:
    """Record token usage for a single message. Appends to CSV and updates session totals."""
    if not usage:
        return
    logger.debug("Token usage: agent=%s, input=%d, output=%d, cost=$%.4f",
                 agent, usage.get("input_tokens", 0) or 0, usage.get("output_tokens", 0) or 0, cost_usd)

    input_uncached = usage.get("input_tokens", 0) or 0
    output_tokens = usage.get("output_tokens", 0) or 0
    cache_read = usage.get("cache_read_input_tokens", 0) or 0
    cache_write = usage.get("cache_creation_input_tokens", 0) or 0
    input_tokens = input_uncached + cache_read + cache_write
    total = input_tokens + output_tokens

    # Update session totals
    _current_session.messages += 1
    _current_session.total_input += input_tokens
    _current_session.total_output += output_tokens
    _current_session.total_cache_read += cache_read
    _current_session.total_cache_write += cache_write
    _current_session.total_cost += cost_usd
    _current_session.total_duration_ms += duration_ms
    if agent:
        _current_session.agent = agent
    if backend:
        _current_session.backend = backend
    if model:
        _current_session.model = model

    # Write to CSV
    now = datetime.now()
    row = {
        "timestamp": now.isoformat(),
        "date": now.strftime("%Y-%m-%d"),
        "month": now.strftime("%Y-%m"),
        "year": now.strftime("%Y"),
        "session_id": session_id or _current_session.session_id,
        "agent": agent,
        "backend": backend,
        "model": model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_tokens": cache_read,
        "cache_write_tokens": cache_write,
        "total_tokens": total,
        "cost_usd": f"{cost_usd:.6f}" if cost_usd else "0",
        "duration_ms": duration_ms,
    }

    _append_csv(row)


def _append_csv(row: dict) -> None:
    """Append a row to the usage CSV. Creates file with headers if missing."""
    USAGE_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    file_exists = USAGE_CSV_PATH.is_file()

    try:
        with open(USAGE_CSV_PATH, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)
    except OSError as e:
        logger.warning("Could not write to token usage CSV: %s", e)


def get_session_summary() -> dict:
    """Get current terminal session usage summary."""
    elapsed = time.monotonic() - _current_session.start_time
    return {
        "messages": _current_session.messages,
        "input_tokens": _current_session.total_input,
        "output_tokens": _current_session.total_output,
        "cache_read_tokens": _current_session.total_cache_read,
        "cache_write_tokens": _current_session.total_cache_write,
        "total_tokens": _current_session.total_input + _current_session.total_output,
        "cost_usd": _current_session.total_cost,
        "duration_ms": _current_session.total_duration_ms,
        "session_seconds": elapsed,
        "agent": _current_session.agent,
        "backend": _current_session.backend,
        "model": _current_session.model,
    }


def get_daily_summary(date: str | None = None) -> dict:
    """Get token usage for a specific date (default: today). Reads from CSV."""
    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")
    return _aggregate_csv("date", date)


def get_monthly_summary(month: str | None = None) -> dict:
    """Get token usage for a specific month (default: this month). Reads from CSV."""
    if month is None:
        month = datetime.now().strftime("%Y-%m")
    return _aggregate_csv("month", month)


def get_yearly_summary(year: str | None = None) -> dict:
    """Get token usage for a specific year (default: this year)."""
    if year is None:
        year = datetime.now().strftime("%Y")
    return _aggregate_csv("year", year)


def get_all_time_summary() -> dict:
    """Get total token usage across all time."""
    return _aggregate_csv(None, None)


def get_model_breakdown(date: str | None = None) -> list[dict]:
    """Get token usage broken down by backend + model."""
    if not USAGE_CSV_PATH.is_file():
        return []

    breakdown: dict[str, dict] = {}
    try:
        with open(USAGE_CSV_PATH, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if date and row.get("date") != date:
                    continue
                key = f"{row.get('backend', '?')} / {row.get('model', '?')}"
                if key not in breakdown:
                    breakdown[key] = {
                        "backend": row.get("backend", ""),
                        "model": row.get("model", ""),
                        "messages": 0, "input_tokens": 0, "output_tokens": 0,
                        "total_tokens": 0, "cost_usd": 0.0,
                    }
                b = breakdown[key]
                b["messages"] += 1
                b["input_tokens"] += int(row.get("input_tokens", 0) or 0)
                b["output_tokens"] += int(row.get("output_tokens", 0) or 0)
                b["total_tokens"] += int(row.get("total_tokens", 0) or 0)
                b["cost_usd"] += float(row.get("cost_usd", 0) or 0)
    except (OSError, csv.Error):
        pass

    return sorted(breakdown.values(), key=lambda x: x["total_tokens"], reverse=True)


def get_agent_breakdown(date: str | None = None, agent_filter: str = "") -> list[dict]:
    """Get token usage broken down by agent, optionally filtered by date or agent name."""
    if not USAGE_CSV_PATH.is_file():
        return []

    if date is None:
        date = datetime.now().strftime("%Y-%m-%d")

    breakdown: dict[str, dict] = {}
    try:
        with open(USAGE_CSV_PATH, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if date and row.get("date") != date:
                    continue
                agent = row.get("agent", "")
                if agent_filter and agent != agent_filter:
                    continue
                if agent not in breakdown:
                    breakdown[agent] = {
                        "agent": agent,
                        "messages": 0, "input_tokens": 0, "output_tokens": 0,
                        "total_tokens": 0, "cost_usd": 0.0,
                    }
                b = breakdown[agent]
                b["messages"] += 1
                b["input_tokens"] += int(row.get("input_tokens", 0) or 0)
                b["output_tokens"] += int(row.get("output_tokens", 0) or 0)
                b["total_tokens"] += int(row.get("total_tokens", 0) or 0)
                b["cost_usd"] += float(row.get("cost_usd", 0) or 0)
    except (OSError, csv.Error):
        pass

    return sorted(breakdown.values(), key=lambda x: x["total_tokens"], reverse=True)


def get_daily_history(limit: int = 14) -> list[dict]:
    """Get daily usage for the last N days, ordered by date descending."""
    if not USAGE_CSV_PATH.is_file():
        return []

    daily: dict[str, dict] = {}
    try:
        with open(USAGE_CSV_PATH, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                d = row.get("date", "")
                if not d:
                    continue
                if d not in daily:
                    daily[d] = {
                        "date": d, "messages": 0,
                        "total_tokens": 0, "cost_usd": 0.0,
                    }
                daily[d]["messages"] += 1
                daily[d]["total_tokens"] += int(row.get("total_tokens", 0) or 0)
                daily[d]["cost_usd"] += float(row.get("cost_usd", 0) or 0)
    except (OSError, csv.Error):
        pass

    return sorted(daily.values(), key=lambda x: x["date"], reverse=True)[:limit]


def _aggregate_csv(filter_field: str | None, filter_value: str | None) -> dict:
    """Aggregate token usage from CSV, optionally filtered."""
    result = {
        "messages": 0, "input_tokens": 0, "output_tokens": 0,
        "cache_read_tokens": 0, "cache_write_tokens": 0,
        "total_tokens": 0, "cost_usd": 0.0,
    }

    if not USAGE_CSV_PATH.is_file():
        return result

    try:
        with open(USAGE_CSV_PATH, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if filter_field and row.get(filter_field) != filter_value:
                    continue
                result["messages"] += 1
                result["input_tokens"] += int(row.get("input_tokens", 0) or 0)
                result["output_tokens"] += int(row.get("output_tokens", 0) or 0)
                result["cache_read_tokens"] += int(row.get("cache_read_tokens", 0) or 0)
                result["cache_write_tokens"] += int(row.get("cache_write_tokens", 0) or 0)
                result["total_tokens"] += int(row.get("total_tokens", 0) or 0)
                result["cost_usd"] += float(row.get("cost_usd", 0) or 0)
    except (OSError, csv.Error):
        pass

    return result