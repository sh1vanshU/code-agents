"""
Multi-repo manager for Code Agents.

Manages multiple repository contexts, allowing users to switch between repos
without restarting. Each repo keeps its own config (.env.code-agents), session
history, and environment isolation.

Usage in chat:
    /repo              — list all registered repos
    /repo <name>       — switch to repo by basename or path
    /repo add <path>   — register a new repo
    /repo remove <name> — unregister a repo
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from code_agents.core.env_loader import (
    GLOBAL_ENV_PATH,
    GLOBAL_VARS,
    PER_REPO_FILENAME,
    load_all_env,
)

logger = logging.getLogger("code_agents.domain.repo_manager")

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class RepoContext:
    """Context for a single registered repository."""

    path: str  # absolute path
    name: str  # basename (e.g., "pg-acquiring-biz")
    env_vars: dict = field(default_factory=dict)  # loaded from .env.code-agents
    git_branch: str = ""
    git_remote: str = ""
    config_file: str = ""  # path to .env.code-agents
    sessions_dir: str = ""  # per-repo session storage


def _detect_git_branch(repo_path: str) -> str:
    """Detect current git branch for a repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return ""


def _detect_git_remote(repo_path: str) -> str:
    """Detect git remote URL for a repo."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return ""


def _load_repo_env_vars(repo_path: str) -> dict:
    """Load env vars from a repo's .env.code-agents file (without applying to os.environ)."""
    env_file = Path(repo_path) / PER_REPO_FILENAME
    if not env_file.is_file():
        return {}
    vars_dict = {}
    try:
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    vars_dict[key] = value
    except OSError as e:
        logger.warning("Failed to read %s: %s", env_file, e)
    return vars_dict


# ---------------------------------------------------------------------------
# RepoManager
# ---------------------------------------------------------------------------


class RepoManager:
    """Manages multiple repository contexts with env isolation."""

    def __init__(self):
        self.repos: dict[str, RepoContext] = {}  # path -> context
        self.active_repo: str = ""  # current active repo path
        self._saved_global_vars: dict[str, str] = {}  # snapshot of global vars

    def add_repo(self, path: str) -> RepoContext:
        """
        Register a new repository.

        Validates the path exists and is a git repo, loads its .env.code-agents,
        detects git branch/remote.

        Raises:
            ValueError: if path doesn't exist or is not a git repo.
        """
        abs_path = str(Path(path).resolve())

        if not Path(abs_path).is_dir():
            raise ValueError(f"Directory does not exist: {abs_path}")

        if not (Path(abs_path) / ".git").is_dir():
            raise ValueError(f"Not a git repository: {abs_path}")

        if abs_path in self.repos:
            logger.info("Repo already registered: %s", abs_path)
            return self.repos[abs_path]

        name = Path(abs_path).name
        config_file = str(Path(abs_path) / PER_REPO_FILENAME)
        sessions_dir = str(
            Path.home() / ".code-agents" / "chat_history"
        )

        ctx = RepoContext(
            path=abs_path,
            name=name,
            env_vars=_load_repo_env_vars(abs_path),
            git_branch=_detect_git_branch(abs_path),
            git_remote=_detect_git_remote(abs_path),
            config_file=config_file,
            sessions_dir=sessions_dir,
        )
        self.repos[abs_path] = ctx
        logger.info("Repo registered: %s (%s) branch=%s", name, abs_path, ctx.git_branch)

        # If this is the first repo, make it active
        if not self.active_repo:
            self.active_repo = abs_path
            self._snapshot_global_vars()

        return ctx

    def switch_repo(self, name_or_path: str) -> RepoContext:
        """
        Switch to a registered repo by basename or full path.

        Updates os.environ with repo-specific vars, sets TARGET_REPO_PATH.

        Raises:
            ValueError: if no matching repo is found.
        """
        ctx = self._resolve(name_or_path)
        if ctx is None:
            available = ", ".join(c.name for c in self.repos.values())
            raise ValueError(
                f"No repo matching '{name_or_path}'. Registered: {available or 'none'}"
            )

        # Restore global vars (clear repo-specific vars from previous repo)
        self._restore_global_vars()

        # Apply new repo's env vars
        for key, value in ctx.env_vars.items():
            os.environ[key] = value

        # Always set TARGET_REPO_PATH
        os.environ["TARGET_REPO_PATH"] = ctx.path

        # Refresh git info
        ctx.git_branch = _detect_git_branch(ctx.path)

        self.active_repo = ctx.path
        logger.info("Switched to repo: %s (%s)", ctx.name, ctx.path)
        return ctx

    def remove_repo(self, name_or_path: str) -> bool:
        """
        Unregister a repo. Cannot remove the active repo.

        Returns True if removed, False if not found.

        Raises:
            ValueError: if trying to remove the active repo.
        """
        ctx = self._resolve(name_or_path)
        if ctx is None:
            return False

        if ctx.path == self.active_repo:
            raise ValueError(
                f"Cannot remove active repo '{ctx.name}'. Switch to another repo first."
            )

        del self.repos[ctx.path]
        logger.info("Repo removed: %s (%s)", ctx.name, ctx.path)
        return True

    def list_repos(self) -> list[RepoContext]:
        """Return all registered repos, active first."""
        result = []
        for path, ctx in self.repos.items():
            result.append(ctx)
        # Sort: active first, then alphabetical by name
        result.sort(key=lambda c: (c.path != self.active_repo, c.name))
        return result

    def get_active(self) -> Optional[RepoContext]:
        """Return the active repo context, or None if none registered."""
        if self.active_repo and self.active_repo in self.repos:
            return self.repos[self.active_repo]
        return None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve(self, name_or_path: str) -> Optional[RepoContext]:
        """Resolve a repo by basename or full path."""
        # Try exact path match first
        abs_path = str(Path(name_or_path).resolve()) if "/" in name_or_path else ""
        if abs_path and abs_path in self.repos:
            return self.repos[abs_path]

        # Try basename match
        for ctx in self.repos.values():
            if ctx.name == name_or_path:
                return ctx

        # Try partial match (startswith)
        for ctx in self.repos.values():
            if ctx.name.startswith(name_or_path):
                return ctx

        return None

    def _snapshot_global_vars(self):
        """Save current global env vars so we can restore them on switch."""
        self._saved_global_vars = {}
        for key in GLOBAL_VARS:
            val = os.environ.get(key)
            if val is not None:
                self._saved_global_vars[key] = val

    def _restore_global_vars(self):
        """Clear repo-specific vars from os.environ, restore global vars."""
        # Get current active repo's vars to clear
        active = self.get_active()
        if active:
            for key in active.env_vars:
                if key not in GLOBAL_VARS and key in os.environ:
                    del os.environ[key]

        # Restore global vars
        for key, value in self._saved_global_vars.items():
            os.environ[key] = value


# ---------------------------------------------------------------------------
# Singleton instance
# ---------------------------------------------------------------------------

_repo_manager: Optional[RepoManager] = None


def get_repo_manager() -> RepoManager:
    """Get (or create) the singleton RepoManager instance."""
    global _repo_manager
    if _repo_manager is None:
        _repo_manager = RepoManager()
    return _repo_manager


def reload_env_for_repo(repo_path: str) -> dict:
    """
    Load global env + repo-specific env for the given path.

    Returns the combined env vars dict (does not modify os.environ).
    """
    combined = {}

    # Load global config vars
    if GLOBAL_ENV_PATH.is_file():
        try:
            with open(GLOBAL_ENV_PATH) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, _, value = line.partition("=")
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        combined[key] = value
        except OSError:
            pass

    # Overlay repo-specific vars
    repo_vars = _load_repo_env_vars(repo_path)
    combined.update(repo_vars)

    return combined
