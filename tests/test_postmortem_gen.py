"""Tests for the Incident Postmortem Auto-Generator."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from code_agents.domain.postmortem_gen import (
    PostmortemData,
    PostmortemGenerator,
    TimelineEvent,
    format_postmortem_summary,
    _parse_range,
    _parse_relative_time,
    _resolve_time,
)


# ---------------------------------------------------------------------------
# TimelineEvent / PostmortemData dataclass tests
# ---------------------------------------------------------------------------

class TestTimelineEvent:
    def test_defaults(self):
        ev = TimelineEvent(timestamp="2026-04-08T14:00:00", source="git", description="test")
        assert ev.severity == "info"
        assert ev.source == "git"

    def test_custom_severity(self):
        ev = TimelineEvent(timestamp="t", source="alert", description="d", severity="critical")
        assert ev.severity == "critical"


class TestPostmortemData:
    def test_defaults(self):
        pm = PostmortemData()
        assert pm.incident_id == ""
        assert pm.severity == "P2"
        assert pm.impact["affected_users"] == 0
        assert pm.impact["duration_minutes"] == 0
        assert pm.timeline == []
        assert pm.remediation == []
        assert pm.action_items == []
        assert pm.contributing_factors == []

    def test_custom_values(self):
        pm = PostmortemData(
            incident_id="INC-123",
            title="Test Incident",
            severity="P0",
            root_cause="bad deploy",
        )
        assert pm.incident_id == "INC-123"
        assert pm.severity == "P0"


# ---------------------------------------------------------------------------
# Time parsing tests
# ---------------------------------------------------------------------------

class TestTimeParsing:
    def test_parse_relative_hours(self):
        result = _parse_relative_time("2h ago")
        assert result is not None
        # Should be a valid date string
        assert len(result) >= 10

    def test_parse_relative_minutes(self):
        result = _parse_relative_time("30m ago")
        assert result is not None

    def test_parse_relative_days(self):
        result = _parse_relative_time("1d ago")
        assert result is not None

    def test_parse_relative_invalid(self):
        assert _parse_relative_time("not a time") is None
        assert _parse_relative_time("") is None

    def test_resolve_time_relative(self):
        result = _resolve_time("2h ago")
        assert result  # non-empty

    def test_resolve_time_absolute(self):
        assert _resolve_time("2026-04-08 14:00") == "2026-04-08 14:00"

    def test_resolve_time_empty(self):
        assert _resolve_time("") == ""

    def test_parse_range_with_dots(self):
        start, end = _parse_range("2026-04-08 14:00..2026-04-08 16:00")
        assert start == "2026-04-08 14:00"
        assert end == "2026-04-08 16:00"

    def test_parse_range_single_value(self):
        start, end = _parse_range("2026-04-08 14:00")
        assert start == "2026-04-08 14:00"
        assert end == ""


# ---------------------------------------------------------------------------
# PostmortemGenerator tests
# ---------------------------------------------------------------------------

class TestPostmortemGenerator:
    def setup_method(self):
        self.gen = PostmortemGenerator(cwd="/tmp")

    def test_init(self):
        assert self.gen.cwd == "/tmp"

    @patch.object(PostmortemGenerator, "_run_git", return_value="")
    def test_generate_empty_git(self, mock_git):
        pm = self.gen.generate(time_range="2h ago..now")
        assert isinstance(pm, PostmortemData)
        assert pm.severity == "P2"
        assert pm.root_cause  # should have fallback message

    @patch.object(PostmortemGenerator, "_run_git")
    def test_generate_with_commits(self, mock_git):
        mock_git.return_value = (
            "abc12345|2026-04-08T14:00:00+05:30|Dev|feat: add feature\n"
            "def67890|2026-04-08T14:30:00+05:30|Dev|fix: hotfix for crash\n"
            "ghi11111|2026-04-08T15:00:00+05:30|Dev|revert: undo bad change"
        )
        pm = self.gen.generate(time_range="2026-04-08 14:00..2026-04-08 16:00")
        assert len(pm.timeline) >= 2
        # Should detect hotfix/revert as critical/warning
        severities = [e.severity for e in pm.timeline]
        assert "critical" in severities or "warning" in severities

    def test_generate_from_data(self):
        events = [
            {"timestamp": "2026-04-08T14:00:00", "source": "deploy", "description": "Deploy v1.2.3"},
            {"timestamp": "2026-04-08T14:05:00", "source": "alert", "description": "Error rate spike", "severity": "critical"},
            {"timestamp": "2026-04-08T14:15:00", "source": "git", "description": "revert: undo v1.2.3"},
            {"timestamp": "2026-04-08T14:20:00", "source": "manual", "description": "Service recovered"},
        ]
        pm = self.gen.generate_from_data(events, title="API Outage", severity="P1")
        assert pm.title == "API Outage"
        assert pm.severity == "P1"
        assert len(pm.timeline) == 4
        assert pm.root_cause  # should detect deploy + error pattern
        assert pm.remediation
        assert pm.action_items
        assert pm.contributing_factors

    def test_generate_from_data_empty(self):
        pm = self.gen.generate_from_data([], title="Empty")
        assert pm.title == "Empty"
        assert pm.timeline == []


class TestBuildTimeline:
    def setup_method(self):
        self.gen = PostmortemGenerator(cwd="/tmp")

    def test_sorts_by_timestamp(self):
        events = [
            TimelineEvent(timestamp="2026-04-08T15:00:00", source="git", description="later"),
            TimelineEvent(timestamp="2026-04-08T14:00:00", source="git", description="earlier"),
        ]
        result = self.gen._build_timeline(events)
        assert result[0].description == "earlier"
        assert result[1].description == "later"

    def test_deduplicates(self):
        ev = TimelineEvent(timestamp="2026-04-08T14:00:00", source="git", description="same")
        result = self.gen._build_timeline([ev, ev])
        assert len(result) == 1


class TestAnalyzeRootCause:
    def setup_method(self):
        self.gen = PostmortemGenerator(cwd="/tmp")

    def test_deploy_before_error(self):
        events = [
            TimelineEvent(timestamp="t1", source="deploy", description="Deploy v1.0"),
            TimelineEvent(timestamp="t2", source="alert", description="Crash", severity="critical"),
        ]
        result = self.gen._analyze_root_cause(events)
        assert "deploy" in result.lower() or "Deploy" in result

    def test_revert_detected(self):
        events = [
            TimelineEvent(timestamp="t1", source="git", description="revert: undo bad", severity="critical"),
        ]
        result = self.gen._analyze_root_cause(events)
        assert "revert" in result.lower()

    def test_config_change(self):
        events = [
            TimelineEvent(timestamp="t1", source="git", description="update config.yaml"),
        ]
        result = self.gen._analyze_root_cause(events)
        assert "config" in result.lower()

    def test_empty_timeline(self):
        result = self.gen._analyze_root_cause([])
        assert "insufficient" in result.lower()


class TestEstimateImpact:
    def setup_method(self):
        self.gen = PostmortemGenerator(cwd="/tmp")

    def test_duration_from_range(self):
        events = []
        result = self.gen._estimate_impact(events, "2026-04-08 14:00", "2026-04-08 16:00")
        assert result["duration_minutes"] == 120

    def test_counts_severities(self):
        events = [
            TimelineEvent(timestamp="t", source="a", description="d", severity="critical"),
            TimelineEvent(timestamp="t", source="a", description="d", severity="warning"),
            TimelineEvent(timestamp="t", source="a", description="d", severity="info"),
        ]
        result = self.gen._estimate_impact(events, "", "")
        assert result["critical_events"] == 1
        assert result["warning_events"] == 1
        assert result["total_events"] == 3


class TestFormatMarkdown:
    def setup_method(self):
        self.gen = PostmortemGenerator(cwd="/tmp")

    def test_contains_sections(self):
        pm = PostmortemData(
            incident_id="INC-1",
            title="Test",
            severity="P1",
            timeline=[
                TimelineEvent(timestamp="t1", source="git", description="commit"),
            ],
            root_cause="bad deploy",
            impact={"duration_minutes": 30, "critical_events": 1, "warning_events": 0, "total_events": 1},
            remediation=["rollback"],
            action_items=["add tests"],
            contributing_factors=["rushed deploy"],
            lessons_learned=["use canary"],
        )
        md = self.gen.format_markdown(pm)
        assert "## Incident Postmortem:" in md
        assert "### Summary" in md
        assert "### Timeline" in md
        assert "### Root Cause" in md
        assert "### Impact" in md
        assert "### Remediation" in md
        assert "### Action Items" in md
        assert "### Lessons Learned" in md
        assert "INC-1" in md


class TestFormatTerminal:
    def setup_method(self):
        self.gen = PostmortemGenerator(cwd="/tmp")

    def test_contains_sections(self):
        pm = PostmortemData(
            title="Test",
            severity="P2",
            timeline=[
                TimelineEvent(timestamp="t1", source="git", description="commit"),
            ],
            root_cause="unknown",
            impact={"duration_minutes": 10, "critical_events": 0, "warning_events": 1, "total_events": 1},
            remediation=["fix it"],
            action_items=["monitor"],
        )
        out = self.gen.format_terminal(pm)
        assert "INCIDENT POSTMORTEM" in out
        assert "TIMELINE" in out
        assert "ROOT CAUSE" in out
        assert "IMPACT" in out
        assert "REMEDIATION" in out
        assert "ACTION ITEMS" in out


class TestFormatPostmortemSummary:
    def test_summary_line(self):
        pm = PostmortemData(
            title="API Down",
            severity="P1",
            root_cause="bad deploy caused 500s",
            impact={"duration_minutes": 45, "total_events": 12},
        )
        result = format_postmortem_summary(pm)
        assert "[P1]" in result
        assert "API Down" in result
        assert "45min" in result


# ---------------------------------------------------------------------------
# Graceful fallback tests (Jira / Grafana / ES unavailable)
# ---------------------------------------------------------------------------

class TestGracefulFallbacks:
    def setup_method(self):
        self.gen = PostmortemGenerator(cwd="/tmp")

    def test_jira_no_config(self):
        with patch.dict(os.environ, {}, clear=True):
            events = self.gen._pull_jira_events("INC-123")
            assert events == []

    def test_grafana_no_config(self):
        with patch.dict(os.environ, {}, clear=True):
            events = self.gen._pull_grafana_alerts("", "")
            assert events == []

    def test_elasticsearch_no_config(self):
        with patch.dict(os.environ, {}, clear=True):
            events = self.gen._pull_elasticsearch_errors("", "")
            assert events == []

    def test_jira_with_bad_url(self):
        with patch.dict(os.environ, {"JIRA_URL": "http://invalid:9999", "JIRA_API_TOKEN": "tok"}):
            events = self.gen._pull_jira_events("INC-1")
            assert events == []  # graceful failure


# ---------------------------------------------------------------------------
# CLI command test
# ---------------------------------------------------------------------------

class TestCLICommand:
    @patch("code_agents.domain.postmortem_gen.PostmortemGenerator")
    def test_cmd_postmortem_gen(self, mock_cls):
        mock_gen = MagicMock()
        mock_cls.return_value = mock_gen
        mock_pm = PostmortemData(title="Test", severity="P2", root_cause="test")
        mock_gen.generate.return_value = mock_pm
        mock_gen.format_markdown.return_value = "## Test"

        from code_agents.cli.cli_postmortem_gen import cmd_postmortem_gen
        cmd_postmortem_gen(["--incident", "INC-1", "--format", "markdown"])
        mock_gen.generate.assert_called_once()
