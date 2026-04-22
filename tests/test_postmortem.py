"""Tests for Incident Postmortem Writer."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from code_agents.domain.postmortem import (
    ActionItem,
    PostmortemReport,
    PostmortemWriter,
    TimelineEvent,
    format_postmortem,
)


class TestPostmortemWriter:
    """Tests for PostmortemWriter."""

    def test_init_defaults(self):
        writer = PostmortemWriter()
        assert writer.time_from == ""
        assert writer.service == ""

    def test_init_custom(self):
        writer = PostmortemWriter(
            time_from="2026-04-08 14:00", time_to="2026-04-08 16:00", service="api",
        )
        assert writer.time_from == "2026-04-08 14:00"
        assert writer.service == "api"

    @patch.object(PostmortemWriter, "_run_git")
    def test_collect_commits(self, mock_git):
        mock_git.return_value = "abc12345|2026-04-08T14:30:00|Alice|fix: hotfix for crash"
        writer = PostmortemWriter(time_from="2026-04-08 14:00")
        commits = writer._collect_commits()
        assert len(commits) == 1
        assert commits[0]["subject"] == "fix: hotfix for crash"

    @patch.object(PostmortemWriter, "_run_git")
    def test_collect_commits_empty(self, mock_git):
        mock_git.return_value = ""
        writer = PostmortemWriter()
        assert writer._collect_commits() == []

    def test_build_timeline(self):
        writer = PostmortemWriter()
        commits = [{"timestamp": "2026-04-08T14:30:00", "author": "Alice", "subject": "fix: crash"}]
        timeline = writer._build_timeline(commits, [], [])
        assert len(timeline) == 1
        assert timeline[0].source == "git"

    def test_infer_root_cause_with_fix(self):
        writer = PostmortemWriter()
        commits = [{"subject": "fix: null pointer in handler"}]
        cause = writer._infer_root_cause(commits, [], [])
        assert "fix commit" in cause

    def test_infer_root_cause_no_data(self):
        writer = PostmortemWriter()
        cause = writer._infer_root_cause([], [], [])
        assert "could not be determined" in cause.lower()

    def test_assess_severity_critical(self):
        writer = PostmortemWriter()
        timeline = [TimelineEvent(timestamp="t", description="d", source="s", severity="critical")]
        assert writer._assess_severity([], timeline) == "P1"

    def test_assess_severity_warnings(self):
        writer = PostmortemWriter()
        timeline = [TimelineEvent(timestamp="t", description="d", source="s", severity="warning")
                     for _ in range(6)]
        assert writer._assess_severity([], timeline) == "P2"

    def test_assess_severity_none(self):
        writer = PostmortemWriter()
        assert writer._assess_severity([], []) == "P4"

    def test_generate_title_with_service(self):
        writer = PostmortemWriter(service="api-gateway", time_from="2026-04-08 14:00")
        title = writer._generate_title([], [])
        assert "[api-gateway]" in title
        assert "2026-04-08" in title

    def test_generate_action_items(self):
        writer = PostmortemWriter()
        items = writer._generate_action_items("fix: resolved", [{"pattern": "err"}])
        assert len(items) >= 2
        assert any("monitor" in a.action.lower() for a in items)


class TestFormatPostmortem:
    """Tests for format_postmortem."""

    def test_format_md(self):
        report = PostmortemReport(
            title="Test Postmortem",
            time_range_start="2026-04-08 14:00",
            time_range_end="2026-04-08 16:00",
            service="api",
            severity_level="P2",
            root_cause="Bug in handler",
            impact="2 warnings",
            action_items=[ActionItem(action="Fix monitoring", priority="high")],
        )
        output = format_postmortem(report)
        assert "Test Postmortem" in output
        assert "P2" in output
        assert "Root Cause" in output
        assert "Fix monitoring" in output

    def test_format_json(self):
        report = PostmortemReport(
            title="Test", time_range_start="", time_range_end="",
            service="", severity_level="P4",
        )
        output = format_postmortem(report, "json")
        assert '"title": "Test"' in output

    def test_format_empty_report(self):
        report = PostmortemReport(
            title="Empty", time_range_start="", time_range_end="",
            service="", severity_level="P4",
        )
        output = format_postmortem(report)
        assert "Empty" in output
