"""Tests for telemetry.py — local SQLite usage analytics."""

import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from code_agents.observability import telemetry
from code_agents.observability.telemetry import (
    is_enabled,
    record_event,
    record_message,
    record_command,
    record_session,
    record_error,
    get_summary,
    get_agent_usage,
    get_top_commands,
    get_error_summary,
    export_csv,
)


@pytest.fixture(autouse=True)
def temp_db(tmp_path):
    """Redirect DB_PATH to a temp file for all tests."""
    db_path = tmp_path / "test_telemetry.db"
    with patch.object(telemetry, "DB_PATH", db_path):
        yield db_path


# ---------------------------------------------------------------------------
# is_enabled
# ---------------------------------------------------------------------------

class TestIsEnabled:
    def test_default_enabled(self):
        with patch.dict("os.environ", {}, clear=False):
            os.environ.pop("CODE_AGENTS_TELEMETRY", None)
            assert is_enabled() is True

    def test_explicit_true(self):
        with patch.dict("os.environ", {"CODE_AGENTS_TELEMETRY": "true"}):
            assert is_enabled() is True

    def test_explicit_false(self):
        with patch.dict("os.environ", {"CODE_AGENTS_TELEMETRY": "false"}):
            assert is_enabled() is False

    def test_zero(self):
        with patch.dict("os.environ", {"CODE_AGENTS_TELEMETRY": "0"}):
            assert is_enabled() is False

    def test_no(self):
        with patch.dict("os.environ", {"CODE_AGENTS_TELEMETRY": "no"}):
            assert is_enabled() is False


# ---------------------------------------------------------------------------
# record_event
# ---------------------------------------------------------------------------

class TestRecordEvent:
    def test_records_when_enabled(self, temp_db):
        with patch.dict("os.environ", {"CODE_AGENTS_TELEMETRY": "true"}):
            record_event("test_event", agent="code-writer")
        # Verify in DB
        conn = sqlite3.connect(str(temp_db))
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM events WHERE event_type='test_event'").fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0]["agent"] == "code-writer"

    def test_skips_when_disabled(self, temp_db):
        with patch.dict("os.environ", {"CODE_AGENTS_TELEMETRY": "false"}):
            record_event("skipped_event")
        # DB file may not even exist
        if temp_db.is_file():
            conn = sqlite3.connect(str(temp_db))
            rows = conn.execute("SELECT * FROM events WHERE event_type='skipped_event'").fetchall()
            conn.close()
            assert len(rows) == 0

    def test_truncates_long_command(self, temp_db):
        with patch.dict("os.environ", {"CODE_AGENTS_TELEMETRY": "true"}):
            record_event("cmd", command="x" * 1000)
        conn = sqlite3.connect(str(temp_db))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT command FROM events").fetchone()
        conn.close()
        assert len(row["command"]) <= 500

    def test_truncates_long_metadata(self, temp_db):
        with patch.dict("os.environ", {"CODE_AGENTS_TELEMETRY": "true"}):
            record_event("meta", metadata="m" * 1000)
        conn = sqlite3.connect(str(temp_db))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT metadata FROM events").fetchone()
        conn.close()
        assert len(row["metadata"]) <= 500


# ---------------------------------------------------------------------------
# Convenience recorders
# ---------------------------------------------------------------------------

class TestConvenienceRecorders:
    def test_record_message(self, temp_db):
        with patch.dict("os.environ", {"CODE_AGENTS_TELEMETRY": "true"}):
            record_message("code-writer", tokens_in=100, tokens_out=200)
        conn = sqlite3.connect(str(temp_db))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM events WHERE event_type='message'").fetchone()
        conn.close()
        assert row["agent"] == "code-writer"
        assert row["tokens_in"] == 100
        assert row["tokens_out"] == 200

    def test_record_command(self, temp_db):
        with patch.dict("os.environ", {"CODE_AGENTS_TELEMETRY": "true"}):
            record_command("git-ops", "git status", status="ok")
        conn = sqlite3.connect(str(temp_db))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM events WHERE event_type='command'").fetchone()
        conn.close()
        assert row["command"] == "git status"

    def test_record_session(self, temp_db):
        with patch.dict("os.environ", {"CODE_AGENTS_TELEMETRY": "true"}):
            record_session("code-tester", user="alice")
        conn = sqlite3.connect(str(temp_db))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM events WHERE event_type='session'").fetchone()
        conn.close()
        assert row["user"] == "alice"

    def test_record_error(self, temp_db):
        with patch.dict("os.environ", {"CODE_AGENTS_TELEMETRY": "true"}):
            record_error("code-writer", "NullPointerException")
        conn = sqlite3.connect(str(temp_db))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM events WHERE event_type='error'").fetchone()
        conn.close()
        assert row["status"] == "error"
        assert "NullPointer" in row["metadata"]


# ---------------------------------------------------------------------------
# get_summary
# ---------------------------------------------------------------------------

class TestGetSummary:
    def test_empty_db(self, temp_db):
        result = get_summary()
        assert result["messages"] == 0
        assert result["sessions"] == 0
        assert result["errors"] == 0

    def test_with_data(self, temp_db):
        with patch.dict("os.environ", {"CODE_AGENTS_TELEMETRY": "true"}):
            record_message("a", tokens_in=1000, tokens_out=500)
            record_message("a", tokens_in=2000, tokens_out=1000)
            record_session("a")
            record_command("a", "ls")
            record_error("a", "boom")
        result = get_summary(days=1)
        assert result["messages"] == 2
        assert result["tokens_in"] == 3000
        assert result["tokens_out"] == 1500
        assert result["sessions"] == 1
        assert result["commands"] == 1
        assert result["errors"] == 1
        assert result["cost_estimate"] > 0

    def test_no_db_file(self, temp_db):
        # DB file doesn't exist
        result = get_summary()
        assert result["messages"] == 0


# ---------------------------------------------------------------------------
# get_agent_usage
# ---------------------------------------------------------------------------

class TestGetAgentUsage:
    def test_empty(self, temp_db):
        assert get_agent_usage() == []

    def test_with_messages(self, temp_db):
        with patch.dict("os.environ", {"CODE_AGENTS_TELEMETRY": "true"}):
            record_message("code-writer", tokens_in=100, tokens_out=50)
            record_message("code-writer", tokens_in=200, tokens_out=100)
            record_message("git-ops", tokens_in=50, tokens_out=25)
        result = get_agent_usage(days=1)
        assert len(result) == 2
        # code-writer should have 2 messages
        writer = [r for r in result if r["agent"] == "code-writer"][0]
        assert writer["messages"] == 2


# ---------------------------------------------------------------------------
# get_top_commands
# ---------------------------------------------------------------------------

class TestGetTopCommands:
    def test_empty(self, temp_db):
        assert get_top_commands() == []

    def test_with_commands(self, temp_db):
        with patch.dict("os.environ", {"CODE_AGENTS_TELEMETRY": "true"}):
            record_command("a", "git status", duration_ms=10)
            record_command("a", "git status", duration_ms=20)
            record_command("a", "git diff", duration_ms=50)
        result = get_top_commands(days=1)
        assert len(result) >= 1
        top = result[0]
        assert top["command"] == "git status"
        assert top["count"] == 2


# ---------------------------------------------------------------------------
# get_error_summary
# ---------------------------------------------------------------------------

class TestGetErrorSummary:
    def test_empty(self, temp_db):
        assert get_error_summary() == []

    def test_with_errors(self, temp_db):
        with patch.dict("os.environ", {"CODE_AGENTS_TELEMETRY": "true"}):
            record_error("code-writer", "NPE at line 42")
            record_error("code-writer", "OOM error")
        result = get_error_summary(days=1)
        assert len(result) == 1
        assert result[0]["agent"] == "code-writer"
        assert result[0]["count"] == 2


# ---------------------------------------------------------------------------
# export_csv
# ---------------------------------------------------------------------------

class TestExportCsv:
    def test_no_db_returns_empty(self, temp_db):
        assert export_csv("/tmp/test.csv") == ""

    def test_export_with_data(self, temp_db):
        with patch.dict("os.environ", {"CODE_AGENTS_TELEMETRY": "true"}):
            record_message("a", tokens_in=100)
            record_command("a", "ls")
        import tempfile as tf
        with tf.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            path = f.name
        try:
            result = export_csv(path, days=1)
            assert result == path
            content = Path(path).read_text()
            assert "timestamp" in content
            assert "event_type" in content
        finally:
            os.unlink(path)
