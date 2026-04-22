"""Tests for the action log and undo system."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from code_agents.git_ops.action_log import (
    ActionLog, Action, ActionType, undo_action, init_action_log,
)


class TestActionLog:
    """Test ActionLog CRUD operations."""

    def test_record_and_retrieve_file_edit(self, tmp_path):
        with patch("code_agents.git_ops.action_log.SESSIONS_DIR", tmp_path):
            log = ActionLog("test-session-1")
            log.record_file_edit("/tmp/test.py", original="old content", new="new content")
            actions = log.get_actions()
            assert len(actions) == 1
            assert actions[0].action_type == ActionType.FILE_EDIT
            assert actions[0].file_path == "/tmp/test.py"
            assert actions[0].original_content == "old content"

    def test_record_file_create(self, tmp_path):
        with patch("code_agents.git_ops.action_log.SESSIONS_DIR", tmp_path):
            log = ActionLog("test-session-2")
            log.record_file_create("/tmp/new.py", content="# new")
            actions = log.get_actions()
            assert len(actions) == 1
            assert actions[0].action_type == ActionType.FILE_CREATE

    def test_record_git_commit(self, tmp_path):
        with patch("code_agents.git_ops.action_log.SESSIONS_DIR", tmp_path):
            log = ActionLog("test-session-3")
            log.record_git_commit("abc123def", "fix: bug", "/repo")
            actions = log.get_actions()
            assert len(actions) == 1
            assert actions[0].action_type == ActionType.GIT_COMMIT
            assert actions[0].commit_sha == "abc123def"

    def test_get_last(self, tmp_path):
        with patch("code_agents.git_ops.action_log.SESSIONS_DIR", tmp_path):
            log = ActionLog("test-session-4")
            log.record_file_create("/a.py")
            log.record_file_create("/b.py")
            log.record_file_create("/c.py")
            last = log.get_last(2)
            assert len(last) == 2
            assert "/c.py" in last[0].file_path
            assert "/b.py" in last[1].file_path

    def test_get_undoable_excludes_commands(self, tmp_path):
        with patch("code_agents.git_ops.action_log.SESSIONS_DIR", tmp_path):
            log = ActionLog("test-session-5")
            log.record_file_create("/a.py")
            log.record_command("echo hello")
            log.record_git_commit("abc123", "test")
            undoable = log.get_undoable()
            assert len(undoable) == 2  # command_run excluded

    def test_pop_last(self, tmp_path):
        with patch("code_agents.git_ops.action_log.SESSIONS_DIR", tmp_path):
            log = ActionLog("test-session-6")
            log.record_file_create("/a.py")
            log.record_file_create("/b.py")
            popped = log.pop_last()
            assert popped is not None
            assert "/b.py" in popped.file_path
            assert len(log.get_actions()) == 1

    def test_pop_last_empty(self, tmp_path):
        with patch("code_agents.git_ops.action_log.SESSIONS_DIR", tmp_path):
            log = ActionLog("test-session-7")
            assert log.pop_last() is None

    def test_persistence(self, tmp_path):
        with patch("code_agents.git_ops.action_log.SESSIONS_DIR", tmp_path):
            log1 = ActionLog("test-persist")
            log1.record_file_edit("/x.py", "orig", "new")
            # New instance should load from disk
            log2 = ActionLog("test-persist")
            actions = log2.get_actions()
            assert len(actions) == 1
            assert actions[0].original_content == "orig"


class TestUndoAction:
    """Test the undo_action function."""

    def test_undo_file_create(self, tmp_path):
        test_file = tmp_path / "created.py"
        test_file.write_text("# new file")
        action = Action(
            action_type=ActionType.FILE_CREATE,
            timestamp=time.time(),
            description="test",
            file_path=str(test_file),
        )
        ok, msg = undo_action(action)
        assert ok
        assert not test_file.exists()

    def test_undo_file_create_already_gone(self, tmp_path):
        action = Action(
            action_type=ActionType.FILE_CREATE,
            timestamp=time.time(),
            description="test",
            file_path=str(tmp_path / "nonexistent.py"),
        )
        ok, msg = undo_action(action)
        assert not ok
        assert "already gone" in msg

    def test_undo_file_edit(self, tmp_path):
        test_file = tmp_path / "edited.py"
        test_file.write_text("modified content")
        action = Action(
            action_type=ActionType.FILE_EDIT,
            timestamp=time.time(),
            description="test",
            file_path=str(test_file),
            original_content="original content",
        )
        ok, msg = undo_action(action)
        assert ok
        assert test_file.read_text() == "original content"

    def test_undo_file_edit_no_original(self, tmp_path):
        action = Action(
            action_type=ActionType.FILE_EDIT,
            timestamp=time.time(),
            description="test",
            file_path=str(tmp_path / "x.py"),
            original_content="",
        )
        ok, msg = undo_action(action)
        assert not ok

    def test_undo_file_delete(self, tmp_path):
        test_file = tmp_path / "deleted.py"
        action = Action(
            action_type=ActionType.FILE_DELETE,
            timestamp=time.time(),
            description="test",
            file_path=str(test_file),
            original_content="restored content",
        )
        ok, msg = undo_action(action)
        assert ok
        assert test_file.read_text() == "restored content"

    def test_undo_git_commit(self):
        action = Action(
            action_type=ActionType.GIT_COMMIT,
            timestamp=time.time(),
            description="test",
            commit_sha="abc123",
            commit_message="fix bug",
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            ok, msg = undo_action(action)
        assert ok
        assert "Reverted" in msg

    def test_undo_git_commit_failure(self):
        action = Action(
            action_type=ActionType.GIT_COMMIT,
            timestamp=time.time(),
            description="test",
            commit_sha="abc123",
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stderr="conflict")
            ok, msg = undo_action(action)
        assert not ok
        assert "failed" in msg

    def test_undo_command_run_impossible(self):
        action = Action(
            action_type=ActionType.COMMAND_RUN,
            timestamp=time.time(),
            description="test",
            command="rm -rf /tmp/foo",
        )
        ok, msg = undo_action(action)
        assert not ok

    def test_dry_run(self, tmp_path):
        test_file = tmp_path / "dry.py"
        test_file.write_text("content")
        action = Action(
            action_type=ActionType.FILE_CREATE,
            timestamp=time.time(),
            description="test",
            file_path=str(test_file),
        )
        ok, msg = undo_action(action, dry_run=True)
        assert ok
        assert "Would" in msg
        assert test_file.exists()  # file NOT deleted in dry-run


class TestActionSerialization:
    """Test Action to_dict / from_dict."""

    def test_roundtrip(self):
        action = Action(
            action_type=ActionType.FILE_EDIT,
            timestamp=12345.0,
            description="Edited foo.py",
            file_path="/foo.py",
            original_content="old",
            new_content="new",
        )
        d = action.to_dict()
        restored = Action.from_dict(d)
        assert restored.action_type == ActionType.FILE_EDIT
        assert restored.file_path == "/foo.py"
        assert restored.original_content == "old"

    def test_empty_fields_omitted(self):
        action = Action(
            action_type=ActionType.GIT_COMMIT,
            timestamp=12345.0,
            description="commit",
            commit_sha="abc",
        )
        d = action.to_dict()
        assert "file_path" not in d
        assert "original_content" not in d


class TestCleanup:
    """Test stale session cleanup."""

    def test_cleanup_old_sessions(self, tmp_path):
        with patch("code_agents.git_ops.action_log.SESSIONS_DIR", tmp_path):
            # Create a session dir with old mtime
            old_dir = tmp_path / "old-session"
            old_dir.mkdir()
            actions_file = old_dir / "actions.json"
            actions_file.write_text("[]")
            # Set mtime to 8 days ago
            old_time = time.time() - 8 * 24 * 3600
            os.utime(actions_file, (old_time, old_time))

            cleaned = ActionLog.cleanup_stale(max_age=7 * 24 * 3600)
            assert cleaned == 1
            assert not old_dir.exists()

    def test_cleanup_keeps_recent(self, tmp_path):
        with patch("code_agents.git_ops.action_log.SESSIONS_DIR", tmp_path):
            recent_dir = tmp_path / "recent-session"
            recent_dir.mkdir()
            (recent_dir / "actions.json").write_text("[]")

            cleaned = ActionLog.cleanup_stale()
            assert cleaned == 0
            assert recent_dir.exists()
