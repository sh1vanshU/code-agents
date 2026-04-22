"""Chat validation — pre-flight checks for server, backend, and workspace trust."""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.chat.chat_validation")


# ---------------------------------------------------------------------------
# Server health check
# ---------------------------------------------------------------------------


def check_server(url: str) -> bool:
    """Check if the server is running."""
    import httpx
    try:
        r = httpx.get(f"{url}/health", timeout=3.0)
        healthy = r.status_code == 200
        logger.info("Server health check at %s: %s", url, "healthy" if healthy else f"status {r.status_code}")
        return healthy
    except Exception as e:
        logger.warning("Server health check failed at %s: %s", url, e)
        return False


# ---------------------------------------------------------------------------
# Server startup offer
# ---------------------------------------------------------------------------


def ensure_server_running(url: str, cwd: str) -> bool:
    """Check server; if not running, offer to start it. Returns True if ready."""
    from .chat_ui import bold, green, yellow, red, dim

    if check_server(url):
        return True

    print()
    print(yellow(f"  Server is not running at {url}"))
    print()
    try:
        answer = input("  Start the server now? [Y/n]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False

    if answer not in ("", "y", "yes"):
        print(f"  Start it with: {bold('code-agents start')}")
        return False

    print(dim("  Starting server in background..."))
    import subprocess as _sp
    import time as _time
    code_agents_home = str(Path(__file__).resolve().parent.parent)
    env = os.environ.copy()
    env["TARGET_REPO_PATH"] = cwd
    log_dir = Path(code_agents_home) / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "code-agents.log"
    _sp.Popen(
        [sys.executable, "-m", "code_agents.core.main"],
        cwd=code_agents_home,
        env=env,
        stdout=_sp.DEVNULL,
        stderr=open(str(log_file), "a"),
    )
    # Wait for server to be ready
    for _ in range(10):
        _time.sleep(1)
        if check_server(url):
            print(green(f"  ✓ Server started at {url}"))
            print()
            return True

    print(red("  ✗ Server failed to start. Check: code-agents logs"))
    return False


# ---------------------------------------------------------------------------
# Workspace trust check
# ---------------------------------------------------------------------------


def check_workspace_trust(repo_path: str) -> bool:
    """Lightweight workspace trust check — no slow subprocess calls."""
    if os.getenv("CODE_AGENTS_BACKEND", "").strip() == "claude-cli":
        return True
    if os.getenv("CODE_AGENTS_LOCAL_LLM_URL", "").strip():
        return True
    if os.getenv("CURSOR_API_URL", "").strip():
        return True
    if os.getenv("ANTHROPIC_API_KEY", "").strip():
        return True
    from code_agents.core.cursor_cli import cursor_cli_display_name, cursor_cli_on_path
    from .chat_ui import yellow, dim
    if not cursor_cli_on_path():
        _n = cursor_cli_display_name()
        print(yellow(f"  ! {_n} not found — Cursor backend may not work"))
        print(dim(f"    Install {_n}, set CODE_AGENTS_CURSOR_CLI, or set CODE_AGENTS_BACKEND=claude-cli"))
        print()
    return True


# ---------------------------------------------------------------------------
# Backend connection validation (background thread)
# ---------------------------------------------------------------------------


class BackendValidator:
    """Runs backend validation in a background thread.

    Usage:
        validator = BackendValidator()
        validator.start()
        # ... do other setup work ...
        if not validator.check():
            return  # user chose to abort
    """

    def __init__(self):
        self._result = None
        self._error: Optional[Exception] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Launch backend validation in a daemon thread."""
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            from code_agents.devops.connection_validator import validate_backend
            self._result = asyncio.run(validate_backend())
        except Exception as e:
            self._error = e

    def check(self, timeout: float = 2.0) -> bool:
        """Wait for validation and handle result.

        Returns True if chat should continue, False if user chose to abort.
        """
        from .chat_ui import yellow, dim

        if self._thread is None:
            return True

        self._thread.join(timeout=timeout)

        if self._error:
            logger.debug("Backend validation skipped: %s", self._error)
            return True

        if self._result is not None:
            if not self._result.valid:
                print()
                print(yellow(f"  ⚠ Backend check: {self._result.message}"))
                print(dim(f"    Backend: {self._result.backend}"))
                print()
                try:
                    answer = input("  Continue anyway? [y/N]: ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    print()
                    return False
                return answer in ("y", "yes")
            else:
                logger.info(
                    "Backend validation passed: %s — %s",
                    self._result.backend, self._result.message,
                )
                return True

        # Still running after timeout — proceed without blocking
        logger.info("Backend validation still in progress — continuing without waiting")
        return True
