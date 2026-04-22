"""Action audit log — tracks agent side-effects for undo/rollback.

Records every file write, git commit, and command executed during a session.
Enables `code-agents undo` to revert the last agent action safely.

Storage: ~/.code-agents/sessions/<session_id>/actions.json
Auto-cleanup: sessions older than 7 days.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.git_ops.action_log")

SESSIONS_DIR = Path.home() / ".code-agents" / "sessions"
ACTIONS_FILE = "actions.json"
SESSION_TTL = 7 * 24 * 3600  # 7 days


class ActionType(str, Enum):
    FILE_CREATE = "file_create"
    FILE_EDIT = "file_edit"
    FILE_DELETE = "file_delete"
    GIT_COMMIT = "git_commit"
    COMMAND_RUN = "command_run"


@dataclass
class Action:
    """A single recorded agent action."""
    action_type: str
    timestamp: float
    description: str
    # File actions
    file_path: str = ""
    original_content: str = ""  # before-state for file edits
    new_content: str = ""  # after-state (for reference)
    # Git actions
    commit_sha: str = ""
    commit_message: str = ""
    # Command actions
    command: str = ""
    cwd: str = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v}

    @staticmethod
    def from_dict(d: dict) -> "Action":
        return Action(
            action_type=d.get("action_type", ""),
            timestamp=d.get("timestamp", 0),
            description=d.get("description", ""),
            file_path=d.get("file_path", ""),
            original_content=d.get("original_content", ""),
            new_content=d.get("new_content", ""),
            commit_sha=d.get("commit_sha", ""),
            commit_message=d.get("commit_message", ""),
            command=d.get("command", ""),
            cwd=d.get("cwd", ""),
        )


class ActionLog:
    """Per-session action log backed by a JSON file."""

    def __init__(self, session_id: str):
        self._session_id = session_id
        self._dir = SESSIONS_DIR / session_id
        self._file = self._dir / ACTIONS_FILE
        self._actions: Optional[list[Action]] = None

    def _load(self) -> list[Action]:
        if self._actions is not None:
            return self._actions
        if self._file.exists():
            try:
                data = json.loads(self._file.read_text())
                self._actions = [Action.from_dict(a) for a in data]
            except (json.JSONDecodeError, OSError) as e:
                logger.warning("Failed to load action log %s: %s", self._file, e)
                self._actions = []
        else:
            self._actions = []
        return self._actions

    def _save(self) -> None:
        if self._actions is None:
            return
        try:
            self._dir.mkdir(parents=True, exist_ok=True)
            self._file.write_text(json.dumps(
                [a.to_dict() for a in self._actions], indent=2,
            ))
        except OSError as e:
            logger.warning("Failed to save action log %s: %s", self._file, e)

    def record_file_create(self, file_path: str, content: str = "") -> None:
        """Record a new file creation."""
        action = Action(
            action_type=ActionType.FILE_CREATE,
            timestamp=time.time(),
            description=f"Created {file_path}",
            file_path=file_path,
            new_content=content[:10000],  # cap stored content
        )
        self._load().append(action)
        self._save()
        logger.debug("Recorded file create: %s", file_path)

    def record_file_edit(self, file_path: str, original: str, new: str = "") -> None:
        """Record a file edit with original content for rollback."""
        action = Action(
            action_type=ActionType.FILE_EDIT,
            timestamp=time.time(),
            description=f"Edited {file_path}",
            file_path=file_path,
            original_content=original[:50000],  # cap at 50k
            new_content=new[:10000],
        )
        self._load().append(action)
        self._save()
        logger.debug("Recorded file edit: %s", file_path)

    def record_file_delete(self, file_path: str, original: str = "") -> None:
        """Record a file deletion."""
        action = Action(
            action_type=ActionType.FILE_DELETE,
            timestamp=time.time(),
            description=f"Deleted {file_path}",
            file_path=file_path,
            original_content=original[:50000],
        )
        self._load().append(action)
        self._save()
        logger.debug("Recorded file delete: %s", file_path)

    def record_git_commit(self, sha: str, message: str = "", cwd: str = "") -> None:
        """Record a git commit."""
        action = Action(
            action_type=ActionType.GIT_COMMIT,
            timestamp=time.time(),
            description=f"Git commit {sha[:8]}: {message[:80]}",
            commit_sha=sha,
            commit_message=message,
            cwd=cwd,
        )
        self._load().append(action)
        self._save()
        logger.debug("Recorded git commit: %s", sha[:8])

    def record_command(self, command: str, cwd: str = "") -> None:
        """Record a command execution."""
        action = Action(
            action_type=ActionType.COMMAND_RUN,
            timestamp=time.time(),
            description=f"Ran: {command[:80]}",
            command=command,
            cwd=cwd,
        )
        self._load().append(action)
        self._save()

    def get_actions(self) -> list[Action]:
        """Get all actions in chronological order."""
        return list(self._load())

    def get_last(self, n: int = 1) -> list[Action]:
        """Get last N actions (most recent first)."""
        return list(reversed(self._load()[-n:]))

    def get_undoable(self) -> list[Action]:
        """Get actions that can be undone (file ops and git commits)."""
        return [
            a for a in reversed(self._load())
            if a.action_type in (
                ActionType.FILE_CREATE, ActionType.FILE_EDIT,
                ActionType.FILE_DELETE, ActionType.GIT_COMMIT,
            )
        ]

    def pop_last(self) -> Optional[Action]:
        """Remove and return the last action."""
        actions = self._load()
        if not actions:
            return None
        action = actions.pop()
        self._save()
        return action

    @staticmethod
    def cleanup_stale(max_age: int = SESSION_TTL) -> int:
        """Delete session directories older than max_age seconds."""
        if not SESSIONS_DIR.exists():
            return 0
        cleaned = 0
        now = time.time()
        try:
            for entry in SESSIONS_DIR.iterdir():
                if not entry.is_dir():
                    continue
                actions_file = entry / ACTIONS_FILE
                if actions_file.exists():
                    try:
                        mtime = actions_file.stat().st_mtime
                        if now - mtime > max_age:
                            shutil.rmtree(entry, ignore_errors=True)
                            cleaned += 1
                    except OSError:
                        shutil.rmtree(entry, ignore_errors=True)
                        cleaned += 1
                else:
                    # Check directory age
                    try:
                        mtime = entry.stat().st_mtime
                        if now - mtime > max_age:
                            shutil.rmtree(entry, ignore_errors=True)
                            cleaned += 1
                    except OSError:
                        pass
        except OSError as e:
            logger.warning("Action log cleanup error: %s", e)
        if cleaned:
            logger.info("Cleaned up %d stale action session(s)", cleaned)
        return cleaned


def undo_action(action: Action, dry_run: bool = False) -> tuple[bool, str]:
    """
    Undo a single action. Returns (success, message).

    - FILE_CREATE → delete the file
    - FILE_EDIT → restore original content
    - FILE_DELETE → restore file from saved content
    - GIT_COMMIT → git revert (creates a new revert commit)
    - COMMAND_RUN → cannot undo (returns False)
    """
    import subprocess

    if action.action_type == ActionType.FILE_CREATE:
        path = Path(action.file_path)
        if not path.exists():
            return False, f"File already gone: {action.file_path}"
        if dry_run:
            return True, f"Would delete: {action.file_path}"
        try:
            path.unlink()
            return True, f"Deleted created file: {action.file_path}"
        except OSError as e:
            return False, f"Failed to delete {action.file_path}: {e}"

    elif action.action_type == ActionType.FILE_EDIT:
        path = Path(action.file_path)
        if not action.original_content:
            return False, f"No original content saved for: {action.file_path}"
        if dry_run:
            return True, f"Would restore: {action.file_path}"
        try:
            path.write_text(action.original_content)
            return True, f"Restored original: {action.file_path}"
        except OSError as e:
            return False, f"Failed to restore {action.file_path}: {e}"

    elif action.action_type == ActionType.FILE_DELETE:
        path = Path(action.file_path)
        if path.exists():
            return False, f"File already exists: {action.file_path}"
        if not action.original_content:
            return False, f"No content saved to restore: {action.file_path}"
        if dry_run:
            return True, f"Would recreate: {action.file_path}"
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(action.original_content)
            return True, f"Restored deleted file: {action.file_path}"
        except OSError as e:
            return False, f"Failed to restore {action.file_path}: {e}"

    elif action.action_type == ActionType.GIT_COMMIT:
        sha = action.commit_sha
        if not sha:
            return False, "No commit SHA recorded"
        cwd = action.cwd or os.getcwd()
        if dry_run:
            return True, f"Would run: git revert {sha[:8]} --no-edit"
        try:
            result = subprocess.run(
                ["git", "revert", sha, "--no-edit"],
                cwd=cwd, capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                return True, f"Reverted commit {sha[:8]}: {action.commit_message[:60]}"
            return False, f"git revert failed: {result.stderr.strip()}"
        except subprocess.TimeoutExpired:
            return False, "git revert timed out"
        except Exception as e:
            return False, f"git revert error: {e}"

    elif action.action_type == ActionType.COMMAND_RUN:
        return False, f"Cannot undo command: {action.command[:80]}"

    return False, f"Unknown action type: {action.action_type}"


# Module-level singleton (set by chat session init)
_current_log: Optional[ActionLog] = None


def get_current_log() -> Optional[ActionLog]:
    """Get the current session's action log."""
    return _current_log


def init_action_log(session_id: str) -> ActionLog:
    """Initialize action logging for a session."""
    global _current_log
    _current_log = ActionLog(session_id)
    # Cleanup old sessions on init
    ActionLog.cleanup_stale()
    return _current_log
