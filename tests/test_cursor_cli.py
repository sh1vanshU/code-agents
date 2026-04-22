"""Tests for code_agents.core.cursor_cli."""

from __future__ import annotations

import os
from unittest.mock import patch

def test_resolve_default_none():
    from code_agents.core.cursor_cli import resolve_cursor_cli_path_for_sdk

    with patch.dict(os.environ, {}, clear=True):
        assert resolve_cursor_cli_path_for_sdk() is None


def test_resolve_bare_name_uses_which():
    from code_agents.core.cursor_cli import resolve_cursor_cli_path_for_sdk

    with patch.dict(os.environ, {"CODE_AGENTS_CURSOR_CLI": "agent"}), \
         patch("shutil.which", return_value="/opt/bin/agent") as wh:
        assert resolve_cursor_cli_path_for_sdk() == "/opt/bin/agent"
    wh.assert_called_once_with("agent")


def test_cursor_cli_on_path_fallback():
    from code_agents.core.cursor_cli import cursor_cli_on_path

    with patch.dict(os.environ, {}, clear=True), \
         patch("shutil.which", side_effect=lambda n: f"/x/{n}" if n == "cursor-agent" else None):
        assert cursor_cli_on_path() == "/x/cursor-agent"


def test_display_name_default():
    from code_agents.core.cursor_cli import cursor_cli_display_name

    with patch.dict(os.environ, {}, clear=True):
        assert cursor_cli_display_name() == "cursor-agent"


def test_display_name_override():
    from code_agents.core.cursor_cli import cursor_cli_display_name

    with patch.dict(os.environ, {"CODE_AGENTS_CURSOR_CLI": "agent"}):
        assert cursor_cli_display_name() == "agent"
