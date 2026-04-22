"""CLI tests grouped by feature area (split from legacy monolith)."""
from __future__ import annotations

import os
import sys
from unittest.mock import patch, MagicMock

import pytest


class TestCmdSessions:
    """Test sessions management command."""

    def test_sessions_list_empty(self, capsys):
        from code_agents.cli.cli_tools import cmd_sessions
        with patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp/fake"), \
             patch("code_agents.chat.chat_history.list_sessions", return_value=[]):
            cmd_sessions([])
        output = capsys.readouterr().out
        assert "No saved chat sessions" in output

    def test_sessions_list_with_sessions(self, capsys):
        import time
        from code_agents.cli.cli_tools import cmd_sessions
        sessions = [
            {
                "id": "abc-123",
                "title": "Test Session",
                "agent": "code-reasoning",
                "message_count": 5,
                "updated_at": time.time(),
                "repo_path": "/tmp/fake",
            }
        ]
        with patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp/fake"), \
             patch("code_agents.chat.chat_history.list_sessions", return_value=sessions):
            cmd_sessions([])
        output = capsys.readouterr().out
        assert "abc-123" in output
        assert "Test Session" in output

    def test_sessions_list_all(self, capsys):
        from code_agents.cli.cli_tools import cmd_sessions
        with patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp/fake"), \
             patch("code_agents.chat.chat_history.list_sessions", return_value=[]):
            cmd_sessions(["--all"])
        output = capsys.readouterr().out
        assert "No saved chat sessions" in output

    def test_sessions_delete_no_id(self, capsys):
        from code_agents.cli.cli_tools import cmd_sessions
        with patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp/fake"):
            cmd_sessions(["delete"])
        output = capsys.readouterr().out
        assert "Usage" in output

    def test_sessions_delete_success(self, capsys):
        from code_agents.cli.cli_tools import cmd_sessions
        with patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp/fake"), \
             patch("code_agents.chat.chat_history.delete_session", return_value=True):
            cmd_sessions(["delete", "abc-123"])
        output = capsys.readouterr().out
        assert "Deleted" in output

    def test_sessions_delete_not_found(self, capsys):
        from code_agents.cli.cli_tools import cmd_sessions
        with patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp/fake"), \
             patch("code_agents.chat.chat_history.delete_session", return_value=False):
            cmd_sessions(["delete", "nonexistent"])
        output = capsys.readouterr().out
        assert "not found" in output

    def test_sessions_clear_no_sessions(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_sessions
        history_dir = tmp_path / "history"
        history_dir.mkdir()
        with patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp"), \
             patch("code_agents.chat.chat_history.HISTORY_DIR", history_dir):
            cmd_sessions(["clear"])
        output = capsys.readouterr().out
        assert "No sessions to clear" in output

    def test_sessions_clear_confirmed(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_sessions
        history_dir = tmp_path / "history"
        history_dir.mkdir()
        (history_dir / "sess1.json").write_text("{}")
        (history_dir / "sess2.json").write_text("{}")
        with patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp"), \
             patch("code_agents.chat.chat_history.HISTORY_DIR", history_dir), \
             patch("builtins.input", return_value="y"):
            cmd_sessions(["clear"])
        output = capsys.readouterr().out
        assert "Cleared" in output

    def test_sessions_clear_cancelled(self, capsys, tmp_path):
        from code_agents.cli.cli_tools import cmd_sessions
        history_dir = tmp_path / "history"
        history_dir.mkdir()
        (history_dir / "sess1.json").write_text("{}")
        with patch("code_agents.cli.cli_tools._user_cwd", return_value="/tmp"), \
             patch("code_agents.chat.chat_history.HISTORY_DIR", history_dir), \
             patch("builtins.input", return_value="n"):
            cmd_sessions(["clear"])
        output = capsys.readouterr().out
        assert "Cancelled" in output
