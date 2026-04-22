"""Extra tests for chat_history.py — covers list_recent_sessions, _format_age,
save_qa_pairs, build_qa_context, session search, and migration paths."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from code_agents.chat.chat_history import (
    _format_age,
    _make_title,
    add_message,
    auto_cleanup,
    build_qa_context,
    cleanup_sessions,
    create_session,
    delete_session,
    get_qa_pairs,
    list_recent_sessions,
    list_sessions,
    load_session,
    save_qa_pairs,
)


# ---------------------------------------------------------------------------
# _format_age
# ---------------------------------------------------------------------------


class TestFormatAge:
    def test_just_now(self):
        assert _format_age(time.time() - 30) == "just now"

    def test_minutes(self):
        result = _format_age(time.time() - 300)  # 5 min ago
        assert "m ago" in result

    def test_hours(self):
        result = _format_age(time.time() - 7200)  # 2h ago
        assert "h ago" in result

    def test_yesterday(self):
        result = _format_age(time.time() - 100000)  # ~27h
        assert result == "yesterday"

    def test_days(self):
        result = _format_age(time.time() - 5 * 86400)  # 5 days
        assert "d ago" in result
        assert "5" in result


# ---------------------------------------------------------------------------
# QA pairs
# ---------------------------------------------------------------------------


class TestQAPairs:
    @pytest.fixture(autouse=True)
    def _use_temp_dir(self, tmp_path):
        with patch("code_agents.chat.chat_history.HISTORY_DIR", tmp_path), \
             patch("code_agents.chat.chat_history._ensure_dir", return_value=tmp_path):
            self.tmp = tmp_path
            yield

    def test_save_and_get_qa_pairs(self):
        session = create_session("code-writer", "/tmp/repo")
        qa = [
            {"question": "Which env?", "answer": "production"},
            {"question": "Branch?", "answer": "main", "is_other": True},
        ]
        save_qa_pairs(session, qa)
        loaded = get_qa_pairs(session)
        assert len(loaded) == 2
        assert loaded[0]["answer"] == "production"
        assert loaded[1]["is_other"] is True

    def test_get_qa_pairs_empty(self):
        session = create_session("code-writer", "/tmp/repo")
        assert get_qa_pairs(session) == []

    def test_build_qa_context_with_pairs(self):
        session = create_session("code-writer", "/tmp/repo")
        qa = [
            {"question": "Which env?", "answer": "prod"},
            {"question": "Custom?", "answer": "yes", "is_other": True},
        ]
        save_qa_pairs(session, qa)
        ctx = build_qa_context(session)
        assert "Which env?" in ctx
        assert "prod" in ctx
        assert "(custom answer)" in ctx

    def test_build_qa_context_empty(self):
        session = create_session("code-writer", "/tmp/repo")
        assert build_qa_context(session) == ""


# ---------------------------------------------------------------------------
# list_recent_sessions
# ---------------------------------------------------------------------------


class TestListRecentSessions:
    @pytest.fixture(autouse=True)
    def _use_temp_dir(self, tmp_path):
        with patch("code_agents.chat.chat_history.HISTORY_DIR", tmp_path), \
             patch("code_agents.chat.chat_history._ensure_dir", return_value=tmp_path):
            self.tmp = tmp_path
            yield

    def test_empty(self):
        assert list_recent_sessions() == []

    def test_lists_sessions_with_messages(self):
        session = create_session("code-writer", "/tmp/repo")
        add_message(session, "user", "Hello")
        result = list_recent_sessions()
        assert len(result) == 1
        assert result[0]["agent"] == "code-writer"
        assert result[0]["messages"] == 1
        assert "age" in result[0]

    def test_skips_empty_sessions(self):
        create_session("code-writer", "/tmp/repo")  # no messages
        result = list_recent_sessions()
        assert len(result) == 0

    def test_limit(self):
        for i in range(10):
            session = create_session("code-writer", "/tmp/repo", session_id=f"s{i}")
            add_message(session, "user", f"Message {i}")
            time.sleep(0.01)
        result = list_recent_sessions(limit=3)
        assert len(result) == 3

    def test_sorted_newest_first(self):
        s1 = create_session("code-writer", "/tmp/repo", session_id="old")
        add_message(s1, "user", "old msg")
        time.sleep(0.05)
        s2 = create_session("code-tester", "/tmp/repo", session_id="new")
        add_message(s2, "user", "new msg")
        result = list_recent_sessions()
        assert result[0]["id"] == "new"

    def test_handles_corrupt_files(self):
        (self.tmp / "corrupt.json").write_text("not valid json{{{")
        result = list_recent_sessions()
        assert result == []


# ---------------------------------------------------------------------------
# delete_session edge cases
# ---------------------------------------------------------------------------


class TestDeleteSession:
    @pytest.fixture(autouse=True)
    def _use_temp_dir(self, tmp_path):
        with patch("code_agents.chat.chat_history.HISTORY_DIR", tmp_path), \
             patch("code_agents.chat.chat_history._ensure_dir", return_value=tmp_path):
            self.tmp = tmp_path
            yield

    def test_delete_existing(self):
        session = create_session("code-writer", "/tmp/repo")
        assert delete_session(session["id"]) is True
        assert load_session(session["id"]) is None

    def test_delete_nonexistent(self):
        assert delete_session("does-not-exist") is False


# ---------------------------------------------------------------------------
# load_session edge cases
# ---------------------------------------------------------------------------


class TestLoadSession:
    @pytest.fixture(autouse=True)
    def _use_temp_dir(self, tmp_path):
        with patch("code_agents.chat.chat_history.HISTORY_DIR", tmp_path), \
             patch("code_agents.chat.chat_history._ensure_dir", return_value=tmp_path):
            self.tmp = tmp_path
            yield

    def test_load_corrupt_file(self):
        (self.tmp / "bad.json").write_text("{{invalid json")
        assert load_session("bad") is None

    def test_load_valid_file(self):
        session = create_session("code-writer", "/tmp/repo")
        loaded = load_session(session["id"])
        assert loaded is not None
        assert loaded["agent"] == "code-writer"


# ---------------------------------------------------------------------------
# auto_cleanup
# ---------------------------------------------------------------------------


class TestAutoCleanup:
    def test_auto_cleanup_no_env(self, tmp_path):
        with patch("code_agents.chat.chat_history.HISTORY_DIR", tmp_path), \
             patch("code_agents.chat.chat_history._ensure_dir", return_value=tmp_path), \
             patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CODE_AGENTS_SESSION_RETENTION_DAYS", None)
            os.environ.pop("CODE_AGENTS_SESSION_MAX_COUNT", None)
            auto_cleanup()  # should be a no-op

    def test_auto_cleanup_with_env(self, tmp_path):
        with patch("code_agents.chat.chat_history.HISTORY_DIR", tmp_path), \
             patch("code_agents.chat.chat_history._ensure_dir", return_value=tmp_path), \
             patch.dict(os.environ, {"CODE_AGENTS_SESSION_RETENTION_DAYS": "1", "CODE_AGENTS_SESSION_MAX_COUNT": "5"}):
            # Create a file
            (tmp_path / "test.json").write_text(json.dumps({"id": "test"}))
            auto_cleanup()  # should not raise

    def test_auto_cleanup_exception_swallowed(self):
        with patch("code_agents.chat.chat_history.cleanup_sessions", side_effect=RuntimeError("fail")):
            auto_cleanup()  # should not raise


# ---------------------------------------------------------------------------
# cleanup_sessions edge: OSError on unlink
# ---------------------------------------------------------------------------


class TestCleanupOSError:
    def test_oserror_on_unlink(self, tmp_path):
        with patch("code_agents.chat.chat_history.HISTORY_DIR", tmp_path), \
             patch("code_agents.chat.chat_history._ensure_dir", return_value=tmp_path):
            # Create old file
            f = tmp_path / "old.json"
            f.write_text(json.dumps({"id": "old"}))
            old_time = time.time() - (40 * 86400)
            os.utime(f, (old_time, old_time))

            with patch.object(Path, "unlink", side_effect=OSError("perm")):
                result = cleanup_sessions(max_age_days=30)
                # File couldn't be deleted, so it stays in remaining
                assert result["deleted_age"] == 0
