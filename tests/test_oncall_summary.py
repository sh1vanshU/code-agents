"""Tests for On-Call Log Summarizer."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from code_agents.domain.oncall_summary import (
    AlertEntry,
    AlertGroup,
    OncallSummarizer,
    OncallSummaryReport,
    format_oncall_summary,
)


class TestOncallSummarizer:
    """Tests for OncallSummarizer."""

    def test_init_defaults(self):
        summarizer = OncallSummarizer()
        assert summarizer.hours == 12
        assert summarizer.channel == "oncall"

    def test_init_custom(self):
        summarizer = OncallSummarizer(hours=24, channel="alerts")
        assert summarizer.hours == 24
        assert summarizer.channel == "alerts"

    def test_parse_log_line_error(self):
        summarizer = OncallSummarizer()
        entry = summarizer._parse_log_line(
            "2026-04-08T14:30:00 [api-gateway] ERROR: connection refused to database"
        )
        assert entry is not None
        assert entry.severity == "critical"
        assert entry.service == "api-gateway"
        assert entry.alert_type == "connection"

    def test_parse_log_line_warning(self):
        summarizer = OncallSummarizer()
        entry = summarizer._parse_log_line(
            "2026-04-08T14:30:00 [auth-svc] WARNING: high latency detected p99=200ms"
        )
        assert entry is not None
        assert entry.severity == "warning"
        assert entry.alert_type == "latency"

    def test_parse_log_line_skip_info(self):
        summarizer = OncallSummarizer()
        entry = summarizer._parse_log_line("2026-04-08T14:30:00 INFO: request processed")
        assert entry is None  # Should skip non-alert lines

    def test_parse_log_line_empty(self):
        summarizer = OncallSummarizer()
        assert summarizer._parse_log_line("") is None

    def test_parse_log_line_oom(self):
        summarizer = OncallSummarizer()
        entry = summarizer._parse_log_line(
            "2026-04-08T14:30:00 [worker] CRITICAL: OOM killed process 1234"
        )
        assert entry is not None
        assert entry.alert_type == "memory"
        assert entry.severity == "critical"

    def test_group_alerts(self):
        summarizer = OncallSummarizer()
        alerts = [
            AlertEntry(timestamp="t1", service="api", alert_type="timeout", message="m1", severity="warning"),
            AlertEntry(timestamp="t2", service="api", alert_type="timeout", message="m2", severity="warning"),
            AlertEntry(timestamp="t3", service="db", alert_type="connection", message="m3", severity="critical"),
        ]
        groups = summarizer._group_alerts(alerts)
        assert len(groups) == 2
        api_group = next(g for g in groups if g.service == "api")
        assert api_group.count == 2

    def test_detect_patterns_recurring(self):
        summarizer = OncallSummarizer()
        groups = [
            AlertGroup(service="api", alert_type="timeout", count=10,
                       first_seen="t1", last_seen="t10"),
        ]
        patterns = summarizer._detect_patterns(groups)
        assert any("Recurring" in p for p in patterns)

    def test_rank_services(self):
        summarizer = OncallSummarizer()
        alerts = [
            AlertEntry(timestamp="t", service="api", alert_type="x", message="m"),
            AlertEntry(timestamp="t", service="api", alert_type="x", message="m"),
            AlertEntry(timestamp="t", service="db", alert_type="x", message="m"),
        ]
        ranked = summarizer._rank_services(alerts)
        assert ranked[0]["service"] == "api"
        assert ranked[0]["alert_count"] == 2

    def test_generate_standup(self):
        summarizer = OncallSummarizer(hours=8)
        groups = [
            AlertGroup(service="api", alert_type="timeout", count=5, severity="warning"),
            AlertGroup(service="db", alert_type="connection", count=2, severity="critical"),
        ]
        standup = summarizer._generate_standup(groups, ["Pattern 1"], [{"service": "api", "alert_count": 5}])
        assert "last 8h" in standup
        assert "7 total alerts" in standup

    def test_parse_log_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = os.path.join(tmpdir, "error.log")
            Path(log_path).write_text(
                "2026-04-08T14:00:00 [api] ERROR: timeout on /health\n"
                "2026-04-08T14:01:00 [api] WARNING: slow response 500ms\n"
                "2026-04-08T14:02:00 [api] INFO: request ok\n"
            )
            summarizer = OncallSummarizer()
            alerts = summarizer._parse_log_file(log_path)
            assert len(alerts) == 2  # INFO should be skipped


class TestFormatOncallSummary:
    """Tests for format_oncall_summary."""

    def test_format_report(self):
        report = OncallSummaryReport(
            period_hours=12,
            total_alerts=5,
            top_services=[{"service": "api", "alert_count": 3}],
            patterns=["Recurring: api/timeout"],
            standup_update="On-call summary...",
            action_items=["Fix timeout"],
        )
        output = format_oncall_summary(report)
        assert "12 hours" in output
        assert "api" in output
        assert "Standup" in output

    def test_format_empty(self):
        report = OncallSummaryReport()
        output = format_oncall_summary(report)
        assert "On-Call Summary" in output
