"""CLI shared helpers — colors, server URL, API calls, env loading."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger("code_agents.cli.cli_helpers")


def _find_code_agents_home() -> Path:
    """Find where code-agents is installed.

    Resolution order:
    1. CODE_AGENTS_HOME env var if set
    2. ~/.code-agents if it exists and is a git repo (the canonical install location)
    3. The directory containing this module (dev mode — running from source)
    """
    env_home = os.environ.get("CODE_AGENTS_HOME")
    if env_home:
        p = Path(env_home).expanduser().resolve()
        if p.exists():
            return p

    installed = Path.home() / ".code-agents"
    if (installed / ".git").is_dir() and (installed / "pyproject.toml").is_file():
        return installed

    return Path(__file__).resolve().parent.parent.parent


def _user_cwd() -> str:
    """Get the user's REAL working directory."""
    return os.environ.get("CODE_AGENTS_USER_CWD") or os.getcwd()


def _load_env():
    """Load env from global config + per-repo overrides."""
    from code_agents.core.env_loader import load_all_env
    load_all_env(_user_cwd())


def _colors():
    """Import color helpers lazily."""
    from code_agents.setup.setup import bold, green, yellow, red, cyan, dim
    return bold, green, yellow, red, cyan, dim


def _server_url() -> str:
    host = os.getenv("HOST", "127.0.0.1")
    port = os.getenv("PORT", "8000")
    if host == "0.0.0.0":
        host = "127.0.0.1"
    return f"http://{host}:{port}"


def _api_get(path: str) -> dict | list | None:
    """Make a GET request to the running server."""
    import httpx
    try:
        r = httpx.get(f"{_server_url()}{path}", timeout=5.0)
        return r.json()
    except Exception:
        return None


def _api_post(path: str, body: dict | None = None) -> dict | list | None:
    """Make a POST request to the running server."""
    import httpx
    try:
        r = httpx.post(f"{_server_url()}{path}", json=body or {}, timeout=30.0)
        return r.json()
    except Exception as e:
        bold, _, _, red, _, _ = _colors()
        print(red(f"  Error: {e}"))
        return None


def prompt_yes_no(question: str, default: bool = True) -> bool:
    """Yes/No prompt — arrow keys / Tab when interactive; y/n or 1/2 otherwise."""
    from code_agents.setup.setup_ui import prompt_yes_no as _ui_yes_no

    return _ui_yes_no(question, default=default)


def _check_workspace_trust(repo_path: str) -> bool:
    """Lightweight workspace trust check."""
    if os.getenv("CODE_AGENTS_BACKEND", "").strip() == "claude-cli":
        return True
    if os.getenv("CODE_AGENTS_LOCAL_LLM_URL", "").strip():
        return True
    if os.getenv("CURSOR_API_URL", "").strip():
        return True
    if os.getenv("ANTHROPIC_API_KEY", "").strip():
        return True
    return True
