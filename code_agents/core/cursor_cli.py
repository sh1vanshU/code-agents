"""Resolve which executable the Cursor backend subprocess uses (cursor-agent vs ``agent``, etc.)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

_ENV = "CODE_AGENTS_CURSOR_CLI"


def cursor_cli_env_value() -> str | None:
    """Return stripped ``CODE_AGENTS_CURSOR_CLI`` or ``None`` if unset."""
    v = os.getenv(_ENV, "").strip()
    return v if v else None


def resolve_cursor_cli_path_for_sdk() -> str | None:
    """Path for ``CursorAgentOptions(cli_path=...)``. ``None`` means use the SDK default (``cursor-agent``)."""
    raw = cursor_cli_env_value()
    if not raw:
        return None
    expanded = Path(raw).expanduser()
    if expanded.is_file():
        return str(expanded)
    if os.sep in raw or (os.name == "nt" and len(raw) > 2 and raw[1] == ":"):
        return str(expanded)
    found = shutil.which(raw)
    return found or raw


def cursor_cli_on_path() -> str | None:
    """Resolved executable for ``shutil.which``-style checks (doctor, startup warnings)."""
    return resolve_cursor_cli_path_for_sdk() or shutil.which("cursor-agent")


def cursor_cli_display_name() -> str:
    """Short label for messages (e.g. ``agent``, ``cursor-agent``)."""
    raw = cursor_cli_env_value()
    return raw if raw else "cursor-agent"
