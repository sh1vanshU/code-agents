"""Tests for token_tracker.py — session usage, CSV recording, cost guard, summaries."""

from __future__ import annotations

import csv
import os
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from code_agents.core.token_tracker import (
    SessionUsage,
    init_session,
    record_usage,
    get_session_summary,
    check_cost_guard,
    get_cost_guard_status,
    get_daily_summary,
    get_monthly_summary,
    get_yearly_summary,
    get_all_time_summary,
    get_model_breakdown,
    _append_csv,
    _current_session,
    CSV_HEADERS,
    USAGE_CSV_PATH,
)


# ---------------------------------------------------------------------------
# SessionUsage dataclass
# ---------------------------------------------------------------------------


class TestSessionUsage:
    def test_defaults(self):
        s = SessionUsage()
        assert s.session_id == ""
        assert s.agent == ""
        assert s.messages == 0
        assert s.total_input == 0
        assert s.total_output == 0
        assert s.total_cache_read == 0
        assert s.total_cache_write == 0
        assert s.total_cost == 0.0
        assert s.total_duration_ms == 0
        assert s.start_time > 0

    def test_custom_values(self):
        s = SessionUsage(session_id="s1", agent="code-writer", messages=5, total_input=100)
        assert s.session_id == "s1"
        assert s.agent == "code-writer"
        assert s.messages == 5
        assert s.total_input == 100


# ---------------------------------------------------------------------------
# init_session
# ---------------------------------------------------------------------------


class TestInitSession:
    def test_init_session_resets(self):
        init_session(session_id="sess-1", agent="test-agent", backend="cursor", model="gpt-4")
        import code_agents.core.token_tracker as tt
        s = tt._current_session
        assert s.session_id == "sess-1"
        assert s.agent == "test-agent"
        assert s.backend == "cursor"
        assert s.model == "gpt-4"
        assert s.messages == 0
        assert s.total_input == 0

    def test_init_session_defaults(self):
        init_session()
        import code_agents.core.token_tracker as tt
        s = tt._current_session
        assert s.session_id == ""
        assert s.agent == ""


# ---------------------------------------------------------------------------
# record_usage
# ---------------------------------------------------------------------------


class TestRecordUsage:
    def setup_method(self):
        init_session(session_id="test-sess", agent="code-writer", backend="cursor", model="test")

    def test_record_none_usage(self):
        """Should return immediately without error for None usage."""
        import code_agents.core.token_tracker as tt
        before = tt._current_session.messages
        record_usage("agent", "backend", "model", None)
        assert tt._current_session.messages == before

    def test_record_updates_session(self):
        import code_agents.core.token_tracker as tt
        usage = {
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_read_input_tokens": 10,
            "cache_creation_input_tokens": 5,
        }
        with patch("code_agents.core.token_tracker._append_csv"):
            record_usage("test-agent", "cursor", "gpt-4", usage, cost_usd=0.01, duration_ms=200)

        s = tt._current_session
        assert s.messages == 1
        assert s.total_input == 115  # 100 uncached + 10 cache_read + 5 cache_write
        assert s.total_output == 50
        assert s.total_cache_read == 10
        assert s.total_cache_write == 5
        assert s.total_cost == pytest.approx(0.01)
        assert s.total_duration_ms == 200

    def test_record_multiple_updates_accumulate(self):
        import code_agents.core.token_tracker as tt
        usage = {"input_tokens": 100, "output_tokens": 50}
        with patch("code_agents.core.token_tracker._append_csv"):
            record_usage("agent", "backend", "model", usage, cost_usd=0.01)
            record_usage("agent", "backend", "model", usage, cost_usd=0.02)

        s = tt._current_session
        assert s.messages == 2
        assert s.total_input == 200
        assert s.total_output == 100
        assert s.total_cost == pytest.approx(0.03)

    def test_record_updates_agent_backend_model(self):
        import code_agents.core.token_tracker as tt
        usage = {"input_tokens": 10, "output_tokens": 5}
        with patch("code_agents.core.token_tracker._append_csv"):
            record_usage("new-agent", "claude", "opus", usage)

        s = tt._current_session
        assert s.agent == "new-agent"
        assert s.backend == "claude"
        assert s.model == "opus"

    def test_record_handles_missing_cache_fields(self):
        import code_agents.core.token_tracker as tt
        usage = {"input_tokens": 100, "output_tokens": 50}
        with patch("code_agents.core.token_tracker._append_csv"):
            record_usage("agent", "backend", "model", usage)

        s = tt._current_session
        assert s.total_cache_read == 0
        assert s.total_cache_write == 0


# ---------------------------------------------------------------------------
# _append_csv
# ---------------------------------------------------------------------------


class TestAppendCsv:
    def test_creates_file_with_headers(self, tmp_path):
        csv_path = tmp_path / "usage.csv"
        with patch("code_agents.core.token_tracker.USAGE_CSV_PATH", csv_path):
            _append_csv({"timestamp": "2024-01-01", "agent": "test", "input_tokens": "100"})

        assert csv_path.exists()
        content = csv_path.read_text()
        assert "timestamp" in content  # header
        assert "test" in content  # data

    def test_appends_without_duplicating_headers(self, tmp_path):
        csv_path = tmp_path / "usage.csv"
        with patch("code_agents.core.token_tracker.USAGE_CSV_PATH", csv_path):
            _append_csv({"timestamp": "2024-01-01", "agent": "first"})
            _append_csv({"timestamp": "2024-01-02", "agent": "second"})

        lines = csv_path.read_text().strip().splitlines()
        # 1 header + 2 data rows
        assert len(lines) == 3
        assert lines[0].startswith("timestamp")

    def test_handles_write_error_gracefully(self, tmp_path):
        csv_path = tmp_path / "nonexistent" / "deep" / "usage.csv"
        # Parent directories will be created by _append_csv
        with patch("code_agents.core.token_tracker.USAGE_CSV_PATH", csv_path):
            # Should not raise
            _append_csv({"timestamp": "2024-01-01", "agent": "test"})


# ---------------------------------------------------------------------------
# check_cost_guard
# ---------------------------------------------------------------------------


class TestCheckCostGuard:
    def setup_method(self):
        init_session()

    def test_no_limit_returns_true(self):
        with patch.dict(os.environ, {}, clear=True):
            assert check_cost_guard() is True

    def test_empty_limit_returns_true(self):
        with patch.dict(os.environ, {"CODE_AGENTS_MAX_SESSION_TOKENS": ""}, clear=True):
            assert check_cost_guard() is True

    def test_invalid_limit_returns_true(self):
        with patch.dict(os.environ, {"CODE_AGENTS_MAX_SESSION_TOKENS": "abc"}, clear=True):
            assert check_cost_guard() is True

    def test_within_limit_returns_true(self):
        import code_agents.core.token_tracker as tt
        tt._current_session.total_input = 100
        tt._current_session.total_output = 50
        with patch.dict(os.environ, {"CODE_AGENTS_MAX_SESSION_TOKENS": "1000"}, clear=True):
            assert check_cost_guard() is True

    def test_exceeded_limit_returns_false(self):
        import code_agents.core.token_tracker as tt
        tt._current_session.total_input = 500
        tt._current_session.total_output = 600
        with patch.dict(os.environ, {"CODE_AGENTS_MAX_SESSION_TOKENS": "1000"}, clear=True):
            assert check_cost_guard() is False


# ---------------------------------------------------------------------------
# get_cost_guard_status
# ---------------------------------------------------------------------------


class TestGetCostGuardStatus:
    def setup_method(self):
        init_session()

    def test_no_limit_returns_none(self):
        with patch.dict(os.environ, {}, clear=True):
            assert get_cost_guard_status() is None

    def test_invalid_limit_returns_none(self):
        with patch.dict(os.environ, {"CODE_AGENTS_MAX_SESSION_TOKENS": "nope"}, clear=True):
            assert get_cost_guard_status() is None

    def test_returns_status_dict(self):
        import code_agents.core.token_tracker as tt
        tt._current_session.total_input = 300
        tt._current_session.total_output = 200
        with patch.dict(os.environ, {"CODE_AGENTS_MAX_SESSION_TOKENS": "1000"}, clear=True):
            status = get_cost_guard_status()

        assert status["current"] == 500
        assert status["max"] == 1000
        assert status["exceeded"] is False
        assert status["remaining"] == 500

    def test_exceeded_status(self):
        import code_agents.core.token_tracker as tt
        tt._current_session.total_input = 800
        tt._current_session.total_output = 300
        with patch.dict(os.environ, {"CODE_AGENTS_MAX_SESSION_TOKENS": "1000"}, clear=True):
            status = get_cost_guard_status()

        assert status["exceeded"] is True
        assert status["remaining"] == 0


# ---------------------------------------------------------------------------
# get_session_summary
# ---------------------------------------------------------------------------


class TestGetSessionSummary:
    def test_returns_dict_with_all_fields(self):
        init_session(session_id="s1", agent="writer", backend="cursor", model="gpt-4")
        import code_agents.core.token_tracker as tt
        tt._current_session.messages = 3
        tt._current_session.total_input = 200
        tt._current_session.total_output = 100
        tt._current_session.total_cost = 0.05

        summary = get_session_summary()
        assert summary["messages"] == 3
        assert summary["input_tokens"] == 200
        assert summary["output_tokens"] == 100
        assert summary["total_tokens"] == 300
        assert summary["cost_usd"] == pytest.approx(0.05)
        assert summary["agent"] == "writer"
        assert summary["backend"] == "cursor"
        assert summary["model"] == "gpt-4"
        assert summary["session_seconds"] >= 0


# ---------------------------------------------------------------------------
# Aggregate summaries (daily, monthly, yearly, all-time)
# ---------------------------------------------------------------------------


class TestAggregateSummaries:
    def _write_test_csv(self, csv_path):
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writeheader()
            writer.writerow({
                "timestamp": "2024-06-15T10:00:00",
                "date": "2024-06-15",
                "month": "2024-06",
                "year": "2024",
                "session_id": "s1",
                "agent": "code-writer",
                "backend": "cursor",
                "model": "gpt-4",
                "input_tokens": "100",
                "output_tokens": "50",
                "cache_read_tokens": "10",
                "cache_write_tokens": "5",
                "total_tokens": "150",
                "cost_usd": "0.01",
                "duration_ms": "200",
            })
            writer.writerow({
                "timestamp": "2024-06-16T10:00:00",
                "date": "2024-06-16",
                "month": "2024-06",
                "year": "2024",
                "session_id": "s2",
                "agent": "code-tester",
                "backend": "claude",
                "model": "opus",
                "input_tokens": "200",
                "output_tokens": "100",
                "cache_read_tokens": "20",
                "cache_write_tokens": "10",
                "total_tokens": "300",
                "cost_usd": "0.02",
                "duration_ms": "400",
            })

    def test_daily_summary(self, tmp_path):
        csv_path = tmp_path / "usage.csv"
        self._write_test_csv(csv_path)
        with patch("code_agents.core.token_tracker.USAGE_CSV_PATH", csv_path):
            result = get_daily_summary("2024-06-15")
        assert result["messages"] == 1
        assert result["input_tokens"] == 100
        assert result["output_tokens"] == 50

    def test_daily_summary_no_match(self, tmp_path):
        csv_path = tmp_path / "usage.csv"
        self._write_test_csv(csv_path)
        with patch("code_agents.core.token_tracker.USAGE_CSV_PATH", csv_path):
            result = get_daily_summary("2024-01-01")
        assert result["messages"] == 0

    def test_monthly_summary(self, tmp_path):
        csv_path = tmp_path / "usage.csv"
        self._write_test_csv(csv_path)
        with patch("code_agents.core.token_tracker.USAGE_CSV_PATH", csv_path):
            result = get_monthly_summary("2024-06")
        assert result["messages"] == 2
        assert result["input_tokens"] == 300

    def test_yearly_summary(self, tmp_path):
        csv_path = tmp_path / "usage.csv"
        self._write_test_csv(csv_path)
        with patch("code_agents.core.token_tracker.USAGE_CSV_PATH", csv_path):
            result = get_yearly_summary("2024")
        assert result["messages"] == 2
        assert result["total_tokens"] == 450

    def test_all_time_summary(self, tmp_path):
        csv_path = tmp_path / "usage.csv"
        self._write_test_csv(csv_path)
        with patch("code_agents.core.token_tracker.USAGE_CSV_PATH", csv_path):
            result = get_all_time_summary()
        assert result["messages"] == 2
        assert result["cost_usd"] == pytest.approx(0.03)

    def test_missing_csv_returns_empty(self, tmp_path):
        csv_path = tmp_path / "nonexistent.csv"
        with patch("code_agents.core.token_tracker.USAGE_CSV_PATH", csv_path):
            result = get_daily_summary("2024-06-15")
        assert result["messages"] == 0


# ---------------------------------------------------------------------------
# get_model_breakdown
# ---------------------------------------------------------------------------


class TestGetModelBreakdown:
    def _write_test_csv(self, csv_path):
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
            writer.writeheader()
            for i in range(3):
                writer.writerow({
                    "timestamp": f"2024-06-15T1{i}:00:00",
                    "date": "2024-06-15",
                    "month": "2024-06",
                    "year": "2024",
                    "session_id": f"s{i}",
                    "agent": "test",
                    "backend": "cursor",
                    "model": "gpt-4",
                    "input_tokens": "100",
                    "output_tokens": "50",
                    "cache_read_tokens": "0",
                    "cache_write_tokens": "0",
                    "total_tokens": "150",
                    "cost_usd": "0.01",
                    "duration_ms": "200",
                })

    def test_breakdown_returns_list(self, tmp_path):
        csv_path = tmp_path / "usage.csv"
        self._write_test_csv(csv_path)
        with patch("code_agents.core.token_tracker.USAGE_CSV_PATH", csv_path):
            result = get_model_breakdown()
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["backend"] == "cursor"
        assert result[0]["model"] == "gpt-4"
        assert result[0]["messages"] == 3
        assert result[0]["total_tokens"] == 450

    def test_breakdown_with_date_filter(self, tmp_path):
        csv_path = tmp_path / "usage.csv"
        self._write_test_csv(csv_path)
        with patch("code_agents.core.token_tracker.USAGE_CSV_PATH", csv_path):
            result = get_model_breakdown(date="2024-06-15")
        assert len(result) == 1

    def test_breakdown_no_csv(self, tmp_path):
        csv_path = tmp_path / "nonexistent.csv"
        with patch("code_agents.core.token_tracker.USAGE_CSV_PATH", csv_path):
            result = get_model_breakdown()
        assert result == []

    def test_breakdown_no_match_date(self, tmp_path):
        csv_path = tmp_path / "usage.csv"
        self._write_test_csv(csv_path)
        with patch("code_agents.core.token_tracker.USAGE_CSV_PATH", csv_path):
            result = get_model_breakdown(date="2020-01-01")
        assert result == []
