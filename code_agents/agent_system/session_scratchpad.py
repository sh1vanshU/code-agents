"""Session Scratchpad — per-session key-value store in /tmp for agent context persistence.

Agents lose context across turns due to prompt flattening and context trimming.
The scratchpad saves discovered facts (branch, job path, image tag, etc.) to /tmp
and injects them as a compact [Session Memory] block into the system prompt.

Agents write via [REMEMBER:key=value] tags in responses (captured by chat_response.py).
Agents read via the injected memory block (injected by chat_context.py).

Auto-cleanup: files older than 1 hour are deleted on session start.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.agent_system.session_scratchpad")

# Base directory for all session scratchpads
SCRATCHPAD_BASE = Path("/tmp/code-agents")

# Max age before cleanup (seconds)
SCRATCHPAD_TTL = 3600  # 1 hour

# Regex to extract [REMEMBER:key=value] tags from agent responses
REMEMBER_RE = re.compile(r"\[REMEMBER:([a-zA-Z_][a-zA-Z0-9_]*)=([^\]]+)\]")


class SessionScratchpad:
    """Per-session key-value store backed by a JSON file in /tmp."""

    def __init__(self, session_id: str, agent: str = ""):
        self._session_id = session_id
        self._agent = agent
        self._dir = SCRATCHPAD_BASE / session_id
        self._file = self._dir / "state.json"
        self._data: Optional[dict] = None

    def _load(self) -> dict:
        """Load state from disk. Returns cached data if already loaded."""
        if self._data is not None:
            return self._data
        if self._file.exists():
            try:
                self._data = json.loads(self._file.read_text())
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to read scratchpad %s: %s", self._file, e)
                self._data = {"agent": self._agent, "updated": time.time(), "facts": {}}
        else:
            self._data = {"agent": self._agent, "updated": time.time(), "facts": {}}
        return self._data

    def _save(self) -> None:
        """Persist state to disk."""
        if self._data is None:
            return
        self._data["updated"] = time.time()
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            self._file.write_text(json.dumps(self._data, indent=2))
        except OSError as e:
            logger.warning("Failed to write scratchpad %s: %s", self._file, e)

    def get(self, key: str) -> Optional[str]:
        """Get a single value by key."""
        return self._load().get("facts", {}).get(key)

    def set(self, key: str, value: str) -> None:
        """Set (or overwrite) a key-value pair."""
        data = self._load()
        data.setdefault("facts", {})[key] = value.strip()
        if self._agent:
            data["agent"] = self._agent
        self._save()
        logger.debug("Scratchpad set: %s = %s", key, value.strip())

    def get_all(self) -> dict[str, str]:
        """Return all stored facts."""
        return dict(self._load().get("facts", {}))

    def clear(self) -> None:
        """Clear all facts (e.g., on agent switch)."""
        self._data = {"agent": self._agent, "updated": time.time(), "facts": {}}
        self._save()
        logger.info("Scratchpad cleared for session %s", self._session_id)

    def format_for_prompt(self) -> str:
        """Format stored facts as a compact block for system prompt injection.

        Returns empty string if no facts are stored.
        """
        facts = self.get_all()
        if not facts:
            return ""

        lines = [
            "[Session Memory — already discovered, do NOT re-fetch these values]",
        ]
        for key, value in facts.items():
            lines.append(f"  {key}: {value}")
        lines.append("")
        lines.append("Rules:")
        lines.append("- If user's message matches saved values → use directly, skip the fetch step.")
        lines.append("- If user's message conflicts with a saved value → confirm the change ONCE, then proceed.")
        lines.append("- Always emit [REMEMBER:key=value] when you discover or confirm a new value.")
        lines.append("- On delegation: START by listing the key values you received (e.g. image_tag, env, service). If critical values are missing, ask immediately.")
        lines.append("[End Session Memory]")
        return "\n".join(lines)

    @staticmethod
    def cleanup_stale(max_age: int = SCRATCHPAD_TTL) -> int:
        """Delete scratchpad directories older than max_age seconds.

        Returns the number of directories cleaned up.
        """
        if not SCRATCHPAD_BASE.exists():
            return 0

        cleaned = 0
        now = time.time()
        try:
            for entry in SCRATCHPAD_BASE.iterdir():
                if not entry.is_dir():
                    continue
                state_file = entry / "state.json"
                if state_file.exists():
                    try:
                        data = json.loads(state_file.read_text())
                        updated = data.get("updated", 0)
                        if now - updated > max_age:
                            _rmtree(entry)
                            cleaned += 1
                    except (json.JSONDecodeError, OSError):
                        # Corrupted — remove
                        _rmtree(entry)
                        cleaned += 1
                else:
                    # No state file — stale directory
                    _rmtree(entry)
                    cleaned += 1
        except OSError as e:
            logger.warning("Scratchpad cleanup error: %s", e)

        if cleaned:
            logger.info("Cleaned up %d stale scratchpad(s)", cleaned)
        return cleaned


def extract_remember_tags(text: str) -> list[tuple[str, str]]:
    """Extract all [REMEMBER:key=value] pairs from agent response text."""
    return REMEMBER_RE.findall(text)


def strip_remember_tags(text: str) -> str:
    """Remove [REMEMBER:key=value] tags from text for display."""
    return REMEMBER_RE.sub("", text)


def _rmtree(path: Path) -> None:
    """Remove a directory tree, ignoring errors."""
    import shutil
    try:
        shutil.rmtree(path)
    except OSError:
        pass
