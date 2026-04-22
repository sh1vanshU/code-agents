"""Tests for code_agents.cli.cli_undo — CLI undo command."""

from __future__ import annotations

from unittest.mock import patch, MagicMock
from pathlib import Path

import pytest


@pytest.fixture
def fake_session(tmp_path):
    """Create a fake sessions directory with one session."""
    sessions_dir = tmp_path / "sessions"
    session_dir = sessions_dir / "test-session-001"
    session_dir.mkdir(parents=True)
    return sessions_dir, session_dir


class TestCmdUndo:
    """Tests for the cmd_undo CLI entry point."""

    @patch("sys.argv", ["code-agents", "undo"])
    def test_undo_no_sessions_dir(self, tmp_path, capsys):
        nonexistent = tmp_path / "nonexistent"
        with patch("code_agents.git_ops.action_log.SESSIONS_DIR", nonexistent):
            from code_agents.cli.cli_undo import cmd_undo
            cmd_undo()
            out = capsys.readouterr().out
            assert "No action history" in out

    @patch("sys.argv", ["code-agents", "undo", "--help"])
    def test_undo_help(self, capsys):
        from code_agents.cli.cli_undo import cmd_undo
        cmd_undo()
        out = capsys.readouterr().out
        assert "Usage" in out or "undo" in out

    @patch("sys.argv", ["code-agents", "undo", "--list"])
    def test_undo_list(self, fake_session, capsys):
        sessions_dir, session_dir = fake_session
        from code_agents.git_ops.action_log import Action
        entries = [
            Action(
                action_type="file_edit",
                description="Edited app.py",
                file_path="app.py",
                timestamp=1712000000.0,
                original_content="old",
            ),
        ]
        mock_log = MagicMock()
        mock_log.get_undoable.return_value = entries

        with patch("code_agents.git_ops.action_log.SESSIONS_DIR", sessions_dir), \
             patch("code_agents.git_ops.action_log.ActionLog", return_value=mock_log):
            from code_agents.cli.cli_undo import cmd_undo
            cmd_undo()
            out = capsys.readouterr().out
            assert "app.py" in out or "Edited" in out

    @patch("sys.argv", ["code-agents", "undo", "--all", "--dry-run"])
    def test_undo_all_dry_run(self, fake_session, capsys):
        sessions_dir, session_dir = fake_session
        from code_agents.git_ops.action_log import Action
        entries = [
            Action(action_type="file_edit", description="Edited app.py", file_path="app.py", timestamp=1712000000.0),
        ]
        mock_log = MagicMock()
        mock_log.get_undoable.return_value = entries

        with patch("code_agents.git_ops.action_log.SESSIONS_DIR", sessions_dir), \
             patch("code_agents.git_ops.action_log.ActionLog", return_value=mock_log), \
             patch("code_agents.git_ops.action_log.undo_action", return_value=(True, "Would revert")):
            from code_agents.cli.cli_undo import cmd_undo
            cmd_undo()
            out = capsys.readouterr().out
            assert "dry" in out.lower() or "Would" in out or "undone" in out.lower()


class TestUndoActionFunction:
    """Test the undo_action function from action_log directly."""

    def test_undo_file_edit(self, tmp_path):
        """Undo a file edit restores original content."""
        from code_agents.git_ops.action_log import Action, undo_action
        target = tmp_path / "test.py"
        target.write_text("new content")

        entry = Action(
            action_type="file_edit",
            description="Edited test.py",
            file_path=str(target),
            timestamp=1712000000.0,
            original_content="original content",
        )
        ok, msg = undo_action(entry)
        assert ok
        assert target.read_text() == "original content"

    def test_undo_file_edit_dry_run(self, tmp_path):
        """Dry run doesn't modify the file."""
        from code_agents.git_ops.action_log import Action, undo_action
        target = tmp_path / "test.py"
        target.write_text("new content")

        entry = Action(
            action_type="file_edit",
            description="Edited test.py",
            file_path=str(target),
            timestamp=1712000000.0,
            original_content="original content",
        )
        ok, msg = undo_action(entry, dry_run=True)
        assert ok
        assert target.read_text() == "new content"  # unchanged

    def test_undo_file_create(self, tmp_path):
        """Undo a file creation deletes the file."""
        from code_agents.git_ops.action_log import Action, undo_action
        target = tmp_path / "new_file.py"
        target.write_text("created content")

        entry = Action(
            action_type="file_create",
            description="Created new_file.py",
            file_path=str(target),
            timestamp=1712000000.0,
        )
        ok, msg = undo_action(entry)
        assert ok
        assert not target.exists()

    def test_undo_missing_file(self, tmp_path):
        """Undo a file edit when file is already gone."""
        from code_agents.git_ops.action_log import Action, undo_action
        entry = Action(
            action_type="file_edit",
            description="Edited ghost.py",
            file_path=str(tmp_path / "ghost.py"),
            timestamp=1712000000.0,
            original_content="content",
        )
        ok, msg = undo_action(entry)
        # Should handle gracefully
        assert isinstance(ok, bool)
