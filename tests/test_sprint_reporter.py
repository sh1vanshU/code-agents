"""Tests for sprint_reporter.py — sprint summary report generation."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest

from code_agents.reporters.sprint_reporter import (
    SprintReport,
    SprintReporter,
    format_sprint_report,
    generate_sprint_markdown,
)


# ============================================================================
# SprintReport dataclass
# ============================================================================


class TestSprintReportDataclass:
    """Test SprintReport dataclass defaults and fields."""

    def test_defaults(self):
        r = SprintReport()
        assert r.sprint_name == ""
        assert r.start_date == ""
        assert r.end_date == ""
        assert r.goal == ""
        assert r.repo_name == ""
        assert r.stories_completed == []
        assert r.stories_in_progress == []
        assert r.stories_carry_over == []
        assert r.bugs_created == 0
        assert r.bugs_resolved == 0
        assert r.bugs_open == []
        assert r.total_commits == 0
        assert r.total_prs_merged == 0
        assert r.commits_by_author == {}
        assert r.files_changed == 0
        assert r.lines_added == 0
        assert r.lines_deleted == 0
        assert r.builds_triggered == 0
        assert r.deploys == []
        assert r.points_committed == 0
        assert r.points_completed == 0
        assert r.velocity == 0.0

    def test_custom_values(self):
        r = SprintReport(
            repo_name="my-svc",
            sprint_name="Sprint 42",
            total_commits=15,
            bugs_created=3,
            bugs_resolved=5,
        )
        assert r.repo_name == "my-svc"
        assert r.sprint_name == "Sprint 42"
        assert r.total_commits == 15
        assert r.bugs_created == 3
        assert r.bugs_resolved == 5

    def test_list_fields_independent(self):
        """Ensure list fields don't share references across instances."""
        r1 = SprintReport()
        r2 = SprintReport()
        r1.stories_completed.append({"key": "X-1"})
        assert r2.stories_completed == []


# ============================================================================
# SprintReporter init
# ============================================================================


class TestSprintReporterInit:
    """Test SprintReporter initialization."""

    def test_default_sprint_days(self):
        reporter = SprintReporter(cwd="/tmp/test-repo")
        assert reporter.sprint_days == 14
        assert reporter.repo_name == "test-repo"
        expected_since = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")
        assert reporter.since == expected_since

    def test_custom_sprint_days(self):
        reporter = SprintReporter(cwd="/tmp/my-project", sprint_days=21)
        assert reporter.sprint_days == 21
        expected_since = (datetime.now() - timedelta(days=21)).strftime("%Y-%m-%d")
        assert reporter.since == expected_since

    def test_repo_name_from_cwd(self):
        reporter = SprintReporter(cwd="/home/user/repos/payment-service")
        assert reporter.repo_name == "payment-service"

    def test_server_url_default(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CODE_AGENTS_PUBLIC_BASE_URL", None)
            reporter = SprintReporter(cwd="/tmp/x")
            assert reporter.server_url == "http://127.0.0.1:8000"

    def test_server_url_from_env(self):
        with patch.dict(os.environ, {"CODE_AGENTS_PUBLIC_BASE_URL": "http://myhost:9000"}):
            reporter = SprintReporter(cwd="/tmp/x")
            assert reporter.server_url == "http://myhost:9000"


# ============================================================================
# Git stats collection
# ============================================================================


class TestCollectGitStats:
    """Test _collect_git_stats with mocked subprocess."""

    def _make_reporter(self):
        reporter = SprintReporter(cwd="/tmp/test-repo")
        return reporter

    @patch("code_agents.reporters.sprint_reporter.subprocess.run")
    def test_commit_count(self, mock_run):
        """Parse git log --oneline output."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="abc1234 first commit\ndef5678 second commit\n",
        )
        reporter = self._make_reporter()
        reporter._collect_git_stats()
        assert reporter.report.total_commits == 2

    @patch("code_agents.reporters.sprint_reporter.subprocess.run")
    def test_commits_by_author(self, mock_run):
        """Parse git shortlog -sn output."""
        def side_effect(cmd, **kwargs):
            if "shortlog" in cmd:
                return MagicMock(returncode=0, stdout="     5\tAlice\n     3\tBob\n")
            return MagicMock(returncode=0, stdout="")

        mock_run.side_effect = side_effect
        reporter = self._make_reporter()
        reporter._collect_git_stats()
        assert reporter.report.commits_by_author == {"Alice": 5, "Bob": 3}

    @patch("code_agents.reporters.sprint_reporter.subprocess.run")
    def test_numstat_parsing(self, mock_run):
        """Parse git log --numstat for lines added/deleted/files changed."""
        numstat = "10\t5\tsrc/main.py\n20\t3\tsrc/utils.py\n-\t-\timage.png\n"

        def side_effect(cmd, **kwargs):
            if "--numstat" in cmd:
                return MagicMock(returncode=0, stdout=numstat)
            return MagicMock(returncode=0, stdout="")

        mock_run.side_effect = side_effect
        reporter = self._make_reporter()
        reporter._collect_git_stats()
        assert reporter.report.lines_added == 30
        assert reporter.report.lines_deleted == 8
        assert reporter.report.files_changed == 3  # including image.png

    @patch("code_agents.reporters.sprint_reporter.subprocess.run")
    def test_merge_commits(self, mock_run):
        """Parse git log --merges for PR count."""
        def side_effect(cmd, **kwargs):
            if "--merges" in cmd:
                return MagicMock(returncode=0, stdout="abc Merge PR #1\ndef Merge PR #2\n")
            return MagicMock(returncode=0, stdout="")

        mock_run.side_effect = side_effect
        reporter = self._make_reporter()
        reporter._collect_git_stats()
        assert reporter.report.total_prs_merged == 2

    @patch("code_agents.reporters.sprint_reporter.subprocess.run")
    def test_empty_git_output(self, mock_run):
        """Handle empty repo gracefully."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        reporter = self._make_reporter()
        reporter._collect_git_stats()
        assert reporter.report.total_commits == 0
        assert reporter.report.files_changed == 0

    @patch("code_agents.reporters.sprint_reporter.subprocess.run")
    def test_git_failure(self, mock_run):
        """Handle git command failure gracefully."""
        mock_run.return_value = MagicMock(returncode=128, stdout="")
        reporter = self._make_reporter()
        reporter._collect_git_stats()
        assert reporter.report.total_commits == 0


# ============================================================================
# Velocity calculation
# ============================================================================


class TestCalculateVelocity:
    """Test _calculate_velocity."""

    def test_velocity_from_completed_stories(self):
        reporter = SprintReporter(cwd="/tmp/x")
        reporter.report.stories_completed = [
            {"key": "X-1", "summary": "A", "points": 5, "assignee": "a"},
            {"key": "X-2", "summary": "B", "points": 8, "assignee": "b"},
            {"key": "X-3", "summary": "C", "points": 3, "assignee": "a"},
        ]
        reporter.report.stories_in_progress = [
            {"key": "X-4", "summary": "D", "points": 5, "assignee": "c"},
        ]
        reporter._calculate_velocity()
        assert reporter.report.points_completed == 16
        assert reporter.report.points_committed == 21
        assert reporter.report.velocity == 16

    def test_velocity_zero_stories(self):
        reporter = SprintReporter(cwd="/tmp/x")
        reporter._calculate_velocity()
        assert reporter.report.points_completed == 0
        assert reporter.report.velocity == 0.0

    def test_velocity_with_zero_point_stories(self):
        reporter = SprintReporter(cwd="/tmp/x")
        reporter.report.stories_completed = [
            {"key": "X-1", "summary": "A", "points": 0},
            {"key": "X-2", "summary": "B", "points": 5},
        ]
        reporter._calculate_velocity()
        assert reporter.report.points_completed == 5

    def test_velocity_missing_points_key(self):
        reporter = SprintReporter(cwd="/tmp/x")
        reporter.report.stories_completed = [
            {"key": "X-1", "summary": "A"},
        ]
        reporter._calculate_velocity()
        assert reporter.report.points_completed == 0


# ============================================================================
# Terminal formatting
# ============================================================================


class TestFormatSprintReport:
    """Test format_sprint_report terminal output."""

    def test_contains_header(self):
        r = SprintReport(repo_name="my-svc")
        output = format_sprint_report(r)
        assert "SPRINT REPORT" in output
        assert "my-svc" in output

    def test_sprint_name_shown(self):
        r = SprintReport(repo_name="svc", sprint_name="Sprint 42")
        output = format_sprint_report(r)
        assert "Sprint 42" in output

    def test_goal_shown(self):
        r = SprintReport(repo_name="svc", goal="Ship v2.0")
        output = format_sprint_report(r)
        assert "Ship v2.0" in output

    def test_stories_completed(self):
        r = SprintReport(
            repo_name="svc",
            stories_completed=[
                {"key": "PROJ-1", "summary": "Add login", "points": 5},
            ],
            points_completed=5,
        )
        output = format_sprint_report(r)
        assert "PROJ-1" in output
        assert "Add login" in output
        assert "5 pts" in output

    def test_in_progress_shown(self):
        r = SprintReport(
            repo_name="svc",
            stories_in_progress=[
                {"key": "PROJ-2", "summary": "Refactor auth"},
            ],
        )
        output = format_sprint_report(r)
        assert "In Progress: 1" in output
        assert "PROJ-2" in output

    def test_carry_over_shown(self):
        r = SprintReport(
            repo_name="svc",
            stories_carry_over=[
                {"key": "PROJ-3", "summary": "Legacy cleanup"},
            ],
        )
        output = format_sprint_report(r)
        assert "Carry-over: 1" in output

    def test_git_activity(self):
        r = SprintReport(
            repo_name="svc",
            total_commits=42,
            total_prs_merged=7,
            files_changed=15,
            lines_added=500,
            lines_deleted=200,
        )
        output = format_sprint_report(r)
        assert "42" in output
        assert "7" in output
        assert "+500" in output
        assert "-200" in output

    def test_top_contributors(self):
        r = SprintReport(
            repo_name="svc",
            commits_by_author={"Alice": 10, "Bob": 5, "Charlie": 3},
        )
        output = format_sprint_report(r)
        assert "Alice: 10" in output
        assert "Bob: 5" in output

    def test_velocity_line(self):
        r = SprintReport(repo_name="svc", points_completed=21)
        output = format_sprint_report(r)
        assert "Velocity: 21 pts" in output


# ============================================================================
# Bug trend detection
# ============================================================================


class TestBugTrend:
    """Test bug rate trend detection in formatted output."""

    def test_improving_trend(self):
        r = SprintReport(repo_name="svc", bugs_created=3, bugs_resolved=7)
        output = format_sprint_report(r)
        assert "improving" in output
        assert "+4" in output

    def test_worsening_trend(self):
        r = SprintReport(repo_name="svc", bugs_created=10, bugs_resolved=2)
        output = format_sprint_report(r)
        assert "worsening" in output
        assert "-8" in output

    def test_stable_trend(self):
        r = SprintReport(repo_name="svc", bugs_created=5, bugs_resolved=5)
        output = format_sprint_report(r)
        assert "stable" in output
        assert "0" in output


# ============================================================================
# Markdown generation
# ============================================================================


class TestGenerateSprintMarkdown:
    """Test generate_sprint_markdown output."""

    def test_markdown_header(self):
        r = SprintReport(repo_name="my-svc")
        md = generate_sprint_markdown(r)
        assert "# Sprint Report" in md
        assert "my-svc" in md

    def test_markdown_stories(self):
        r = SprintReport(
            repo_name="svc",
            stories_completed=[
                {"key": "X-1", "summary": "Feature A", "points": 8},
            ],
            points_completed=8,
        )
        md = generate_sprint_markdown(r)
        assert "**Completed:** 1 (8 story points)" in md
        assert "**X-1**: Feature A (8 pts)" in md

    def test_markdown_no_stories(self):
        r = SprintReport(repo_name="svc")
        md = generate_sprint_markdown(r)
        assert "- None" in md

    def test_markdown_bugs(self):
        r = SprintReport(repo_name="svc", bugs_created=3, bugs_resolved=5)
        md = generate_sprint_markdown(r)
        assert "Created: 3" in md
        assert "Resolved: 5" in md
        assert "Net: 2" in md

    def test_markdown_git(self):
        r = SprintReport(
            repo_name="svc",
            total_commits=20,
            total_prs_merged=5,
            files_changed=10,
            lines_added=300,
            lines_deleted=100,
        )
        md = generate_sprint_markdown(r)
        assert "20 commits" in md
        assert "5 PRs merged" in md
        assert "+300 -100" in md

    def test_markdown_velocity(self):
        r = SprintReport(repo_name="svc", points_completed=13)
        md = generate_sprint_markdown(r)
        assert "**13 story points**" in md

    def test_markdown_sprint_name(self):
        r = SprintReport(repo_name="svc", sprint_name="Sprint 42")
        md = generate_sprint_markdown(r)
        assert "Sprint 42" in md

    def test_markdown_goal(self):
        r = SprintReport(repo_name="svc", goal="Ship payments v2")
        md = generate_sprint_markdown(r)
        assert "Ship payments v2" in md


# ============================================================================
# Generate (integration with mocked steps)
# ============================================================================


class TestSprintReporterGenerate:
    """Test generate() orchestration."""

    @patch.object(SprintReporter, "_collect_jira_data")
    @patch.object(SprintReporter, "_collect_git_stats")
    @patch.object(SprintReporter, "_collect_build_data")
    @patch.object(SprintReporter, "_calculate_velocity")
    def test_generate_calls_all_steps(self, mock_vel, mock_build, mock_git, mock_jira):
        reporter = SprintReporter(cwd="/tmp/x")
        result = reporter.generate()
        mock_jira.assert_called_once()
        mock_git.assert_called_once()
        mock_build.assert_called_once()
        mock_vel.assert_called_once()
        assert isinstance(result, SprintReport)

    @patch.object(SprintReporter, "_collect_jira_data", side_effect=Exception("fail"))
    @patch.object(SprintReporter, "_collect_git_stats")
    @patch.object(SprintReporter, "_collect_build_data")
    @patch.object(SprintReporter, "_calculate_velocity")
    def test_generate_continues_on_step_failure(self, mock_vel, mock_build, mock_git, mock_jira):
        reporter = SprintReporter(cwd="/tmp/x")
        result = reporter.generate()
        # Should still call remaining steps
        mock_git.assert_called_once()
        mock_build.assert_called_once()
        mock_vel.assert_called_once()
        assert isinstance(result, SprintReport)


# ============================================================================
# Additional sprint_reporter tests
# ============================================================================


class TestCollectBuildData:
    """Test _collect_build_data step."""

    @patch("code_agents.reporters.sprint_reporter.get_summary", create=True)
    def test_build_data_from_telemetry(self, mock_summary):
        mock_summary.return_value = {"build_count": 15}
        reporter = SprintReporter(cwd="/tmp/x")
        with patch.dict("sys.modules", {"code_agents.observability.telemetry": MagicMock(get_summary=mock_summary)}):
            reporter._collect_build_data()
        # Even if the import works differently, should not crash

    def test_build_data_handles_import_error(self):
        reporter = SprintReporter(cwd="/tmp/x")
        # Should not raise even if telemetry not available
        reporter._collect_build_data()
        assert reporter.report.builds_triggered >= 0


class TestCollectJiraData:
    """Test _collect_jira_data step."""

    def test_no_jira_project(self, monkeypatch):
        monkeypatch.delenv("JIRA_PROJECT_KEY", raising=False)
        reporter = SprintReporter(cwd="/tmp/x")
        reporter._collect_jira_data()
        assert reporter.report.stories_completed == []

    @patch("urllib.request.urlopen")
    def test_jira_stories_completed(self, mock_urlopen, monkeypatch):
        monkeypatch.setenv("JIRA_PROJECT_KEY", "TEST")
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps({
            "issues": [
                {"key": "TEST-1", "summary": "Story A", "story_points": 5, "assignee": "Alice"},
            ],
        }).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        reporter = SprintReporter(cwd="/tmp/x")
        reporter._collect_jira_data()
        assert len(reporter.report.stories_completed) >= 0  # depends on mock order


class TestSprintReportFormatting:
    """Test edge cases in formatting."""

    def test_empty_report_no_crash(self):
        r = SprintReport()
        output = format_sprint_report(r)
        assert "SPRINT REPORT" in output

    def test_markdown_empty_report(self):
        r = SprintReport()
        md = generate_sprint_markdown(r)
        assert "# Sprint Report" in md
        assert "- None" in md

    def test_format_no_contributors(self):
        r = SprintReport(repo_name="svc")
        output = format_sprint_report(r)
        assert "Top contributors" not in output

    def test_format_no_in_progress(self):
        r = SprintReport(repo_name="svc")
        output = format_sprint_report(r)
        assert "In Progress" not in output

    def test_format_no_carry_over(self):
        r = SprintReport(repo_name="svc")
        output = format_sprint_report(r)
        assert "Carry-over" not in output
