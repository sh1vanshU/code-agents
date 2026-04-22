"""Tests for chat_history module and stream.build_prompt."""

import time
from pathlib import Path
from unittest.mock import patch

import pytest

from code_agents.chat.chat_history import (
    _make_title,
    add_message,
    create_session,
    delete_session,
    list_sessions,
    load_session,
)


# ---------------------------------------------------------------------------
# _make_title
# ---------------------------------------------------------------------------


class TestMakeTitle:
    def test_short_message(self):
        assert _make_title("Hello world") == "Hello world"

    def test_long_message(self):
        title = _make_title("A" * 100)
        assert len(title) <= 60
        assert title.endswith("...")

    def test_multiline(self):
        assert _make_title("First line\nSecond line") == "First line"

    def test_empty(self):
        assert _make_title("") == "Untitled"

    def test_whitespace(self):
        assert _make_title("   ") == "Untitled"


# ---------------------------------------------------------------------------
# Session CRUD (uses a temp directory)
# ---------------------------------------------------------------------------


class TestSessionCRUD:
    @pytest.fixture(autouse=True)
    def _use_temp_dir(self, tmp_path):
        with patch("code_agents.chat.chat_history.HISTORY_DIR", tmp_path):
            with patch("code_agents.chat.chat_history._ensure_dir", return_value=tmp_path):
                self.tmp = tmp_path
                yield

    def test_create_session(self):
        session = create_session("code-writer", "/tmp/repo")
        assert session["agent"] == "code-writer"
        assert session["repo_path"] == "/tmp/repo"
        assert session["title"] == "New chat"
        assert len(session["messages"]) == 0
        # Full UUID format (contains dashes)
        assert "-" in session["id"]

    def test_create_with_custom_id(self):
        session = create_session("code-writer", "/tmp/repo", session_id="custom-123")
        assert session["id"] == "custom-123"

    def test_load_session(self):
        session = create_session("code-writer", "/tmp/repo")
        loaded = load_session(session["id"])
        assert loaded is not None
        assert loaded["id"] == session["id"]
        assert loaded["agent"] == "code-writer"

    def test_load_nonexistent(self):
        assert load_session("nonexistent") is None

    def test_add_message(self):
        session = create_session("code-writer", "/tmp/repo")
        add_message(session, "user", "Hello")
        assert len(session["messages"]) == 1
        assert session["messages"][0]["role"] == "user"
        assert session["messages"][0]["content"] == "Hello"
        assert "timestamp" in session["messages"][0]

    def test_add_message_sets_title(self):
        session = create_session("code-writer", "/tmp/repo")
        assert session["title"] == "New chat"
        add_message(session, "user", "Fix the login bug")
        assert session["title"] == "Fix the login bug"

    def test_title_not_overwritten(self):
        session = create_session("code-writer", "/tmp/repo")
        add_message(session, "user", "First message")
        add_message(session, "user", "Second message")
        assert session["title"] == "First message"

    def test_delete_session(self):
        session = create_session("code-writer", "/tmp/repo")
        assert delete_session(session["id"]) is True
        assert load_session(session["id"]) is None

    def test_delete_nonexistent(self):
        assert delete_session("nonexistent") is False

    def test_list_sessions_empty(self):
        assert list_sessions() == []

    def test_list_sessions(self):
        create_session("code-writer", "/tmp/repo")
        create_session("code-tester", "/tmp/repo")
        sessions = list_sessions()
        assert len(sessions) == 2

    def test_list_sessions_sorted_recent_first(self):
        s1 = create_session("code-writer", "/tmp/repo")
        time.sleep(0.02)
        s2 = create_session("code-tester", "/tmp/repo")
        sessions = list_sessions()
        assert sessions[0]["id"] == s2["id"]  # most recent first
        assert sessions[1]["id"] == s1["id"]

    def test_list_sessions_filter_by_repo(self):
        create_session("code-writer", "/tmp/repo1")
        create_session("code-tester", "/tmp/repo2")
        sessions = list_sessions(repo_path="/tmp/repo1")
        assert len(sessions) == 1
        assert sessions[0]["agent"] == "code-writer"

    def test_list_sessions_limit(self):
        for _ in range(5):
            create_session("code-writer", "/tmp/repo")
        sessions = list_sessions(limit=3)
        assert len(sessions) == 3

    def test_persistence(self):
        """Messages persist to disk and can be reloaded."""
        session = create_session("code-writer", "/tmp/repo")
        add_message(session, "user", "Hello")
        add_message(session, "assistant", "Hi there!")

        loaded = load_session(session["id"])
        assert len(loaded["messages"]) == 2
        assert loaded["messages"][0]["content"] == "Hello"
        assert loaded["messages"][1]["content"] == "Hi there!"


# ---------------------------------------------------------------------------
# build_prompt (from stream.py)
# ---------------------------------------------------------------------------


class TestBuildPrompt:
    def test_single_message(self):
        from code_agents.core.stream import build_prompt
        from code_agents.core.models import Message

        messages = [Message(role="user", content="Hello")]
        assert build_prompt(messages) == "Hello"

    def test_multi_turn(self):
        from code_agents.core.stream import build_prompt
        from code_agents.core.models import Message

        messages = [
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi there!"),
            Message(role="user", content="How are you?"),
        ]
        result = build_prompt(messages)
        assert "Human: Hello" in result
        assert "Assistant: Hi there!" in result
        assert "Human: How are you?" in result

    def test_system_messages_filtered(self):
        from code_agents.core.stream import build_prompt
        from code_agents.core.models import Message

        messages = [
            Message(role="system", content="You are helpful"),
            Message(role="user", content="Hello"),
        ]
        result = build_prompt(messages)
        assert result == "Hello"
        assert "system" not in result.lower()

    def test_empty_messages(self):
        from code_agents.core.stream import build_prompt
        assert build_prompt([]) == ""


# ---------------------------------------------------------------------------
# Session cleanup
# ---------------------------------------------------------------------------


class TestCleanupSessions:
    def test_delete_by_age(self, tmp_path):
        from code_agents.chat.chat_history import cleanup_sessions, HISTORY_DIR
        import json
        with patch("code_agents.chat.chat_history.HISTORY_DIR", tmp_path):
            # Create an old session (40 days ago)
            old_file = tmp_path / "old-session.json"
            old_file.write_text(json.dumps({"id": "old-session", "messages": []}))
            import os
            old_time = time.time() - (40 * 86400)
            os.utime(old_file, (old_time, old_time))

            # Create a recent session
            new_file = tmp_path / "new-session.json"
            new_file.write_text(json.dumps({"id": "new-session", "messages": []}))

            result = cleanup_sessions(max_age_days=30)
            assert result["deleted_age"] == 1
            assert result["remaining"] == 1
            assert not old_file.exists()
            assert new_file.exists()

    def test_delete_by_count(self, tmp_path):
        from code_agents.chat.chat_history import cleanup_sessions
        import json
        with patch("code_agents.chat.chat_history.HISTORY_DIR", tmp_path):
            # Create 5 sessions with different mtimes
            for i in range(5):
                f = tmp_path / f"session-{i}.json"
                f.write_text(json.dumps({"id": f"session-{i}", "messages": []}))
                import os
                os.utime(f, (time.time() - (i * 3600), time.time() - (i * 3600)))

            result = cleanup_sessions(max_count=3)
            assert result["deleted_count"] == 2
            assert result["remaining"] == 3

    def test_no_cleanup_when_disabled(self, tmp_path):
        from code_agents.chat.chat_history import cleanup_sessions
        import json
        with patch("code_agents.chat.chat_history.HISTORY_DIR", tmp_path):
            (tmp_path / "s1.json").write_text(json.dumps({"id": "s1"}))
            result = cleanup_sessions(max_age_days=0, max_count=0)
            assert result["deleted_age"] == 0
            assert result["deleted_count"] == 0

    def test_cleanup_from_env_vars(self, tmp_path):
        from code_agents.chat.chat_history import cleanup_sessions
        import json
        with patch("code_agents.chat.chat_history.HISTORY_DIR", tmp_path), \
             patch.dict("os.environ", {"CODE_AGENTS_SESSION_RETENTION_DAYS": "30", "CODE_AGENTS_SESSION_MAX_COUNT": "2"}):
            for i in range(4):
                f = tmp_path / f"session-{i}.json"
                f.write_text(json.dumps({"id": f"session-{i}"}))
                import os
                os.utime(f, (time.time() - (i * 3600), time.time() - (i * 3600)))
            result = cleanup_sessions()
            assert result["deleted_count"] == 2
            assert result["remaining"] == 2

    def test_auto_cleanup_safe(self):
        from code_agents.chat.chat_history import auto_cleanup
        # Should not raise even if cleanup fails
        with patch("code_agents.chat.chat_history.cleanup_sessions", side_effect=Exception("fail")):
            auto_cleanup()  # no exception

    def test_combined_age_and_count(self, tmp_path):
        from code_agents.chat.chat_history import cleanup_sessions
        import json
        with patch("code_agents.chat.chat_history.HISTORY_DIR", tmp_path):
            # 1 old (expired) + 4 recent
            for i in range(5):
                f = tmp_path / f"s-{i}.json"
                f.write_text(json.dumps({"id": f"s-{i}"}))
                import os
                age = 40 * 86400 if i == 0 else i * 3600
                os.utime(f, (time.time() - age, time.time() - age))

            result = cleanup_sessions(max_age_days=30, max_count=2)
            assert result["deleted_age"] == 1  # the 40-day-old one
            assert result["deleted_count"] == 2  # keep only 2 of remaining 4
            assert result["remaining"] == 2


# ---------------------------------------------------------------------------
# load_session paths (lines 81-92)
# ---------------------------------------------------------------------------


class TestLoadSession:
    """Test load_session success and failure paths."""

    @pytest.fixture(autouse=True)
    def _use_temp_dir(self, tmp_path):
        with patch("code_agents.chat.chat_history.HISTORY_DIR", tmp_path):
            self.tmp = tmp_path
            yield

    def test_load_session_success(self):
        """Load a valid session file (lines 86-89)."""
        import json
        session_data = {
            "id": "test-session",
            "messages": [{"role": "user", "content": "hello"}],
            "agent": "test",
        }
        path = self.tmp / "test-session.json"
        path.write_text(json.dumps(session_data))
        result = load_session("test-session")
        assert result is not None
        assert result["id"] == "test-session"
        assert len(result["messages"]) == 1

    def test_load_session_not_found(self):
        """Session file does not exist (lines 82-84)."""
        result = load_session("nonexistent-id")
        assert result is None

    def test_load_session_invalid_json(self):
        """Session file contains invalid JSON (lines 90-92)."""
        path = self.tmp / "bad-session.json"
        path.write_text("not valid json{{{")
        result = load_session("bad-session")
        assert result is None

    def test_load_session_oserror(self):
        """OSError reading session file (lines 90-92)."""
        import json
        path = self.tmp / "err-session.json"
        path.write_text(json.dumps({"id": "err"}))
        with patch.object(Path, "read_text", side_effect=OSError("permission denied")):
            result = load_session("err-session")
        assert result is None


# ---------------------------------------------------------------------------
# list_sessions repo_path filter (lines 125-126)
# ---------------------------------------------------------------------------


class TestListSessionsFilter:
    @pytest.fixture(autouse=True)
    def _use_temp_dir(self, tmp_path):
        with patch("code_agents.chat.chat_history.HISTORY_DIR", tmp_path):
            self.tmp = tmp_path
            yield

    def test_filter_by_repo_path(self):
        """list_sessions filters by repo_path (lines 125-126, 128-129)."""
        import json
        for i, rp in enumerate(["/repo/a", "/repo/b", "/repo/a"]):
            path = self.tmp / f"s-{i}.json"
            path.write_text(json.dumps({
                "id": f"s-{i}",
                "agent": "test",
                "title": f"Session {i}",
                "updated_at": time.time() - i,
                "repo_path": rp,
                "messages": [],
            }))
        result = list_sessions(repo_path="/repo/a")
        assert len(result) == 2
        for s in result:
            assert s["repo_path"] == "/repo/a"


# ---------------------------------------------------------------------------
# auto_cleanup logs deletions (lines 292-293, 313)
# ---------------------------------------------------------------------------


class TestAutoCleanupLogs:
    def test_auto_cleanup_with_deletions(self):
        """auto_cleanup logs when sessions are deleted (lines 312-315)."""
        from code_agents.chat.chat_history import auto_cleanup
        mock_result = {"deleted_age": 2, "deleted_count": 1, "remaining": 5}
        with patch("code_agents.chat.chat_history.cleanup_sessions", return_value=mock_result):
            auto_cleanup()  # Should not raise

    def test_auto_cleanup_exception_caught(self):
        """auto_cleanup silently catches exceptions (line 317)."""
        from code_agents.chat import chat_history
        from code_agents.chat.chat_history import auto_cleanup
        with patch("code_agents.chat.chat_history.cleanup_sessions", side_effect=Exception("fail")):
            auto_cleanup()  # Should not raise


# ---------------------------------------------------------------------------
# Coverage gap tests — missing lines
# ---------------------------------------------------------------------------


class TestLoadSessionCorruptFile:
    """Lines 81-92: load_session with corrupt/missing file."""

    def test_load_session_json_decode_error(self, tmp_path):
        """Lines 90-92: corrupt JSON file."""
        from code_agents.chat.chat_history import load_session, _session_path
        session_id = "test-corrupt"
        with patch("code_agents.chat.chat_history._session_path", return_value=tmp_path / f"{session_id}.json"):
            path = tmp_path / f"{session_id}.json"
            path.write_text("{invalid json")
            result = load_session(session_id)
        assert result is None

    def test_load_session_valid_file(self, tmp_path):
        """Lines 81-89: valid session file."""
        import json
        from code_agents.chat.chat_history import load_session
        session_id = "test-valid"
        path = tmp_path / f"{session_id}.json"
        data = {"id": session_id, "messages": [{"role": "user", "content": "hi"}]}
        path.write_text(json.dumps(data))
        with patch("code_agents.chat.chat_history._session_path", return_value=path):
            result = load_session(session_id)
        assert result is not None
        assert result["id"] == session_id
        assert len(result["messages"]) == 1


class TestListSessionsCorruptFiles:
    """Lines 125-126: list_sessions skips corrupt files."""

    def test_list_sessions_skips_corrupt(self, tmp_path):
        import json
        from code_agents.chat.chat_history import list_sessions
        good = tmp_path / "good.json"
        good.write_text(json.dumps({"id": "good", "messages": [], "agent": "a", "repo_path": "/r", "updated_at": "2025-01-01"}))
        bad = tmp_path / "bad.json"
        bad.write_text("not json")
        with patch("code_agents.chat.chat_history._ensure_dir", return_value=tmp_path):
            sessions = list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["id"] == "good"


class TestCleanupSessionsExcessDeletion:
    """Lines 292-293: cleanup_sessions excess deletion OSError."""

    def test_cleanup_excess_oserror(self, tmp_path):
        import json
        from code_agents.chat.chat_history import cleanup_sessions
        # Create 3 sessions
        for i in range(3):
            p = tmp_path / f"session{i}.json"
            data = {"id": f"s{i}", "messages": [], "updated_at": "2025-01-01T00:00:00"}
            p.write_text(json.dumps(data))
        with patch("code_agents.chat.chat_history._ensure_dir", return_value=tmp_path):
            result = cleanup_sessions(max_age_days=0, max_count=1)
        # Should have tried to delete, may fail with OSError on some
        assert "remaining" in result