"""Tests for log_investigator.py — Log Investigator feature."""

from __future__ import annotations

import os
import pytest
from unittest.mock import patch, MagicMock

from code_agents.observability.log_investigator import (
    Investigation,
    LogInvestigator,
    format_investigation,
)


class TestInvestigationDataclass:
    """Verify Investigation dataclass defaults and fields."""

    def test_defaults(self):
        inv = Investigation(query="NullPointerException", timestamp="2026-04-01T10:00:00")
        assert inv.query == "NullPointerException"
        assert inv.timestamp == "2026-04-01T10:00:00"
        assert inv.matching_logs == []
        assert inv.error_patterns == []
        assert inv.correlated_deploys == []
        assert inv.related_commits == []
        assert inv.root_cause_hypothesis == ""
        assert inv.suggested_fix == ""
        assert inv.severity == "unknown"

    def test_mutable_defaults_independent(self):
        inv1 = Investigation(query="err1", timestamp="t1")
        inv2 = Investigation(query="err2", timestamp="t2")
        inv1.matching_logs.append({"msg": "test"})
        assert inv2.matching_logs == []


class TestLogInvestigatorInit:
    """Verify LogInvestigator constructor."""

    def test_init_defaults(self):
        inv = LogInvestigator(query="timeout", cwd="/tmp")
        assert inv.query == "timeout"
        assert inv.cwd == "/tmp"
        assert inv.hours == 24
        assert inv.investigation.query == "timeout"

    def test_init_custom_hours(self):
        inv = LogInvestigator(query="OOM", cwd="/tmp", hours=6)
        assert inv.hours == 6

    def test_init_server_url_env(self):
        with patch.dict(os.environ, {"CODE_AGENTS_PUBLIC_BASE_URL": "http://myhost:9000"}):
            inv = LogInvestigator(query="err", cwd="/tmp")
            assert inv.server_url == "http://myhost:9000"


class TestFindErrorPatterns:
    """Verify _find_error_patterns groups and sorts correctly."""

    def test_empty_logs(self):
        inv = LogInvestigator(query="err", cwd="/tmp")
        inv._find_error_patterns()
        assert inv.investigation.error_patterns == []

    def test_groups_similar_messages(self):
        inv = LogInvestigator(query="err", cwd="/tmp")
        inv.investigation.matching_logs = [
            {"message": "Error at 2026-04-01T10:00:00 id=abc12345 count=5", "timestamp": "t1"},
            {"message": "Error at 2026-04-01T11:00:00 id=def67890 count=10", "timestamp": "t2"},
            {"message": "Different error entirely", "timestamp": "t3"},
        ]
        inv._find_error_patterns()
        # The two similar messages should group together
        assert len(inv.investigation.error_patterns) == 2
        # The grouped pattern should have count 2
        top = inv.investigation.error_patterns[0]
        assert top["count"] == 2

    def test_normalizes_timestamps(self):
        inv = LogInvestigator(query="err", cwd="/tmp")
        inv.investigation.matching_logs = [
            {"message": "Failed at 2026-01-15T08:30:00Z", "timestamp": "t1"},
            {"message": "Failed at 2026-02-20T14:00:00Z", "timestamp": "t2"},
        ]
        inv._find_error_patterns()
        assert len(inv.investigation.error_patterns) == 1
        assert inv.investigation.error_patterns[0]["count"] == 2

    def test_normalizes_hex_ids(self):
        inv = LogInvestigator(query="err", cwd="/tmp")
        inv.investigation.matching_logs = [
            {"message": "Request abcdef12 failed", "timestamp": "t1"},
            {"message": "Request 99887766 failed", "timestamp": "t2"},
        ]
        inv._find_error_patterns()
        assert len(inv.investigation.error_patterns) == 1

    def test_sorts_by_count_descending(self):
        inv = LogInvestigator(query="err", cwd="/tmp")
        inv.investigation.matching_logs = [
            {"message": "rare error", "timestamp": "t1"},
            {"message": "common error", "timestamp": "t2"},
            {"message": "common error", "timestamp": "t3"},
            {"message": "common error", "timestamp": "t4"},
        ]
        inv._find_error_patterns()
        assert inv.investigation.error_patterns[0]["count"] == 3
        assert inv.investigation.error_patterns[1]["count"] == 1

    def test_limits_to_10_patterns(self):
        inv = LogInvestigator(query="err", cwd="/tmp")
        inv.investigation.matching_logs = [
            {"message": f"unique error {i}", "timestamp": f"t{i}"}
            for i in range(20)
        ]
        inv._find_error_patterns()
        assert len(inv.investigation.error_patterns) <= 10


class TestHypothesizeRootCause:
    """Verify _hypothesize_root_cause severity and hypothesis logic."""

    def test_deploy_correlation_sets_p2(self):
        inv = LogInvestigator(query="err", cwd="/tmp")
        inv.investigation.correlated_deploys = [{"revision": "abc12345", "app": "myapp"}]
        inv.investigation.error_patterns = [{"count": 5, "pattern": "err", "first_seen": "t1", "last_seen": "t2"}]
        inv._hypothesize_root_cause()
        assert inv.investigation.severity == "P2"
        assert "deploy" in inv.investigation.root_cause_hypothesis.lower()
        assert "rolling back" in inv.investigation.suggested_fix.lower()

    def test_high_volume_sets_p2(self):
        inv = LogInvestigator(query="err", cwd="/tmp")
        inv.investigation.error_patterns = [{"count": 50, "pattern": "err", "first_seen": "t1", "last_seen": "t2"}]
        inv._hypothesize_root_cause()
        assert inv.investigation.severity == "P2"
        assert "systematic" in inv.investigation.root_cause_hypothesis.lower()

    def test_related_commits_sets_p3(self):
        inv = LogInvestigator(query="err", cwd="/tmp")
        inv.investigation.related_commits = ["abc1234 fix auth module"]
        inv._hypothesize_root_cause()
        assert inv.investigation.severity == "P3"
        assert "commits" in inv.investigation.root_cause_hypothesis.lower()
        assert "commits" in inv.investigation.suggested_fix.lower()

    def test_no_data_sets_p4(self):
        inv = LogInvestigator(query="err", cwd="/tmp")
        inv._hypothesize_root_cause()
        assert inv.investigation.severity == "P4"
        assert "manual" in inv.investigation.root_cause_hypothesis.lower()


class TestFormatInvestigation:
    """Verify format_investigation produces readable output."""

    def test_basic_format(self):
        inv = Investigation(query="NullPointerException", timestamp="2026-04-01T10:00:00")
        inv.severity = "P2"
        inv.root_cause_hypothesis = "Deploy caused it"
        inv.suggested_fix = "Rollback"
        output = format_investigation(inv)
        assert "INVESTIGATION" in output
        assert "NullPointerException" in output
        assert "P2" in output
        assert "Deploy caused it" in output
        assert "Rollback" in output

    def test_format_with_patterns(self):
        inv = Investigation(query="OOM", timestamp="t1")
        inv.severity = "P2"
        inv.error_patterns = [{"count": 10, "pattern": "java.lang.OutOfMemoryError", "first_seen": "t1", "last_seen": "t2"}]
        inv.root_cause_hypothesis = "Memory leak"
        inv.suggested_fix = "Check heap"
        output = format_investigation(inv)
        assert "Error Patterns" in output
        assert "10x" in output
        assert "OutOfMemoryError" in output

    def test_format_with_deploys(self):
        inv = Investigation(query="err", timestamp="t1")
        inv.severity = "P2"
        inv.correlated_deploys = [{"app": "myapp", "revision": "abc12345def", "health": "Healthy"}]
        inv.root_cause_hypothesis = "Deploy"
        inv.suggested_fix = "Rollback"
        output = format_investigation(inv)
        assert "Correlated Deploys" in output
        assert "myapp" in output
        assert "abc12345" in output

    def test_format_with_commits(self):
        inv = Investigation(query="err", timestamp="t1")
        inv.severity = "P3"
        inv.related_commits = ["abc1234 fix auth"]
        inv.root_cause_hypothesis = "Code change"
        inv.suggested_fix = "Review"
        output = format_investigation(inv)
        assert "Related Commits" in output
        assert "abc1234 fix auth" in output

    def test_format_truncates_long_query(self):
        long_query = "A" * 100
        inv = Investigation(query=long_query, timestamp="t1")
        inv.severity = "P4"
        inv.root_cause_hypothesis = "Unknown"
        inv.suggested_fix = "Investigate"
        output = format_investigation(inv)
        # Query should be truncated to 50 chars in header
        assert long_query[:50] in output
        assert long_query not in output


class TestInvestigateFlow:
    """Verify the full investigate() orchestration."""

    def test_investigate_catches_step_failures(self):
        inv = LogInvestigator(query="err", cwd="/tmp")
        # All steps should fail gracefully (no Kibana, no ArgoCD, etc.)
        result = inv.investigate()
        assert result.severity in ("P2", "P3", "P4", "unknown")
        assert result.query == "err"

    def test_step_failure_continues(self):
        inv = LogInvestigator(query="err", cwd="/tmp")
        original = inv._search_kibana_logs

        def boom():
            raise RuntimeError("boom")
        boom.__name__ = "_search_kibana_logs"

        inv._search_kibana_logs = boom
        result = inv.investigate()
        # Should still complete despite kibana failure
        assert result is not None
        assert result.severity in ("P2", "P3", "P4")
