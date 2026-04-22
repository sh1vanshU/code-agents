"""Tests for sprint_velocity.py — sprint velocity tracking from Jira / git."""

import os
import subprocess
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from code_agents.reporters.sprint_velocity import (
    SprintData,
    SprintVelocityTracker,
    VelocityReport,
    format_report,
)


@pytest.fixture
def tracker(tmp_path):
    """Tracker instance with Jira configured."""
    os.environ["JIRA_URL"] = "https://jira.example.com"
    os.environ["JIRA_PROJECT_KEY"] = "PROJ"
    os.environ["HOST"] = "127.0.0.1"
    os.environ["PORT"] = "8000"
    t = SprintVelocityTracker(cwd=str(tmp_path))
    yield t
    os.environ.pop("JIRA_URL", None)
    os.environ.pop("JIRA_PROJECT_KEY", None)


@pytest.fixture
def tracker_no_jira(tmp_path):
    """Tracker instance without Jira configured."""
    os.environ.pop("JIRA_URL", None)
    os.environ.pop("JIRA_PROJECT_KEY", None)
    return SprintVelocityTracker(cwd=str(tmp_path))


# ── SprintData / VelocityReport dataclasses ─────────────────────────

def test_sprint_data_defaults():
    s = SprintData(sprint_id=1, name="Sprint 1", start_date="2026-01-01", end_date="2026-01-14")
    assert s.completed_points == 0
    assert s.committed_points == 0
    assert s.issues == []
    assert s.carry_overs == []
    assert s.bugs_created == 0
    assert s.bugs_resolved == 0
    assert s.state == "active"


def test_velocity_report_defaults():
    r = VelocityReport(project_key="PROJ", repo_name="my-repo")
    assert r.avg_velocity == 0.0
    assert r.trend == "stable"
    assert r.total_carry_overs == []
    assert r.source == "jira"


# ── Velocity calculation ────────────────────────────────────────────

def test_calculate_velocity_with_mock_sprints():
    """Test velocity calculation with manually constructed sprint data."""
    report = VelocityReport(project_key="PROJ", repo_name="test-repo")
    report.sprints = [
        SprintData(sprint_id=i, name=f"Sprint {40+i}", start_date=f"2026-0{i}-01",
                   end_date=f"2026-0{i}-14", completed_points=pts, state="closed")
        for i, pts in enumerate([28, 34, 21, 38], start=1)
    ]
    SprintVelocityTracker._compute_stats(report)

    assert report.avg_velocity == pytest.approx(30.25)
    assert report.trend in ("up", "down", "stable")


def test_trend_detection_up():
    """Increasing velocity across sprints should detect 'up' trend."""
    report = VelocityReport(project_key="PROJ", repo_name="test")
    report.sprints = [
        SprintData(sprint_id=i, name=f"Sprint {i}", start_date="", end_date="",
                   completed_points=pts, state="closed")
        for i, pts in enumerate([10, 12, 20, 25])
    ]
    SprintVelocityTracker._compute_stats(report)
    assert report.trend == "up"


def test_trend_detection_down():
    """Decreasing velocity across sprints should detect 'down' trend."""
    report = VelocityReport(project_key="PROJ", repo_name="test")
    report.sprints = [
        SprintData(sprint_id=i, name=f"Sprint {i}", start_date="", end_date="",
                   completed_points=pts, state="closed")
        for i, pts in enumerate([30, 28, 15, 10])
    ]
    SprintVelocityTracker._compute_stats(report)
    assert report.trend == "down"


def test_trend_detection_stable():
    """Flat velocity across sprints should detect 'stable' trend."""
    report = VelocityReport(project_key="PROJ", repo_name="test")
    report.sprints = [
        SprintData(sprint_id=i, name=f"Sprint {i}", start_date="", end_date="",
                   completed_points=pts, state="closed")
        for i, pts in enumerate([20, 21, 20, 21])
    ]
    SprintVelocityTracker._compute_stats(report)
    assert report.trend == "stable"


def test_trend_detection_two_sprints():
    """With only 2 sprints, use simple comparison."""
    report = VelocityReport(project_key="PROJ", repo_name="test")
    report.sprints = [
        SprintData(sprint_id=1, name="S1", start_date="", end_date="",
                   completed_points=10, state="closed"),
        SprintData(sprint_id=2, name="S2", start_date="", end_date="",
                   completed_points=20, state="closed"),
    ]
    SprintVelocityTracker._compute_stats(report)
    assert report.trend == "up"


def test_avg_velocity_empty_sprints():
    """No closed sprints should yield 0 average."""
    report = VelocityReport(project_key="PROJ", repo_name="test")
    report.sprints = [
        SprintData(sprint_id=1, name="S1", start_date="", end_date="",
                   completed_points=10, state="active"),
    ]
    SprintVelocityTracker._compute_stats(report)
    assert report.avg_velocity == 0.0


# ── Carry-over detection ────────────────────────────────────────────

def test_carry_overs_aggregated():
    """Carry-overs from sprints should be aggregated in report."""
    report = VelocityReport(project_key="PROJ", repo_name="test")
    co1 = {"key": "PROJ-101", "summary": "Webhook retry", "points": 3}
    co2 = {"key": "PROJ-102", "summary": "Config migration", "points": 2}
    report.sprints = [
        SprintData(sprint_id=1, name="S1", start_date="", end_date="",
                   completed_points=20, state="closed", carry_overs=[co1]),
        SprintData(sprint_id=2, name="S2", start_date="", end_date="",
                   completed_points=25, state="closed", carry_overs=[co2]),
    ]
    SprintVelocityTracker._compute_stats(report)
    assert len(report.total_carry_overs) == 2
    assert report.total_carry_overs[0]["key"] == "PROJ-101"
    assert report.total_carry_overs[1]["key"] == "PROJ-102"


def test_get_carry_overs_no_jira(tracker_no_jira):
    """Without Jira config, carry-overs returns empty list."""
    assert tracker_no_jira.get_carry_overs() == []


# ── Bug rate ─────────────────────────────────────────────────────────

def test_bug_rate_aggregation():
    """Bug created/resolved counts should be aggregated."""
    report = VelocityReport(project_key="PROJ", repo_name="test")
    report.sprints = [
        SprintData(sprint_id=1, name="S1", start_date="", end_date="",
                   completed_points=20, state="closed",
                   bugs_created=5, bugs_resolved=3),
        SprintData(sprint_id=2, name="S2", start_date="", end_date="",
                   completed_points=25, state="closed",
                   bugs_created=7, bugs_resolved=12),
    ]
    SprintVelocityTracker._compute_stats(report)
    assert report.total_bugs_created == 12
    assert report.total_bugs_resolved == 15


def test_bug_rate_no_jira(tracker_no_jira):
    """Without Jira config, bug rate returns zeroes."""
    result = tracker_no_jira.get_bug_rate()
    assert result == {"created": 0, "resolved": 0, "net": 0}


def test_bug_rate_with_jira(tracker):
    """Bug rate with Jira uses server API."""
    with patch.object(tracker, "_jira_search", return_value=[
        {"key": "PROJ-1", "fields": {"issuetype": {"name": "Bug"}, "status": {"name": "Done"}}},
        {"key": "PROJ-2", "fields": {"issuetype": {"name": "Bug"}, "status": {"name": "Open"}}},
        {"key": "PROJ-3", "fields": {"issuetype": {"name": "Bug"}, "status": {"name": "Resolved"}}},
    ]):
        result = tracker.get_bug_rate()
        assert result["created"] == 3
        assert result["resolved"] == 2
        assert result["net"] == 1


# ── Git-based fallback ──────────────────────────────────────────────

def test_git_fallback_no_jira(tracker_no_jira):
    """Without Jira, calculate_velocity should use git fallback."""
    mock_result = MagicMock()
    mock_result.stdout = (
        "abc123|2026-03-30 10:00:00 +0530|Merge pull request #1\n"
        "def456|2026-03-28 10:00:00 +0530|Merge pull request #2\n"
        "ghi789|2026-03-15 10:00:00 +0530|Merge pull request #3\n"
    )

    with patch("code_agents.reporters.sprint_velocity.subprocess.run", return_value=mock_result):
        report = tracker_no_jira.calculate_velocity(sprints=3)

    assert report.source == "git"
    assert len(report.sprints) > 0


def test_git_fallback_empty_log(tracker_no_jira):
    """Empty git log should return empty report."""
    mock_result = MagicMock()
    mock_result.stdout = ""

    with patch("code_agents.reporters.sprint_velocity.subprocess.run", return_value=mock_result):
        report = tracker_no_jira.calculate_velocity(sprints=3)

    assert report.source == "git"
    assert len(report.sprints) == 0


def test_git_fallback_subprocess_error(tracker_no_jira):
    """Subprocess error should return empty report gracefully."""
    with patch("code_agents.reporters.sprint_velocity.subprocess.run", side_effect=Exception("git not found")):
        report = tracker_no_jira.calculate_velocity(sprints=3)

    assert report.source == "git"
    assert len(report.sprints) == 0


# ── Format output ───────────────────────────────────────────────────

def test_format_report_jira():
    """Jira report should include velocity bars, bug rate, carry-overs."""
    report = VelocityReport(project_key="PROJ", repo_name="my-service", source="jira")
    report.current_sprint = SprintData(
        sprint_id=45, name="Sprint 45", start_date="2026-03-25",
        end_date="2026-04-07", goal="Payment gateway refactoring",
        state="active", completed_points=24, committed_points=30,
    )
    report.sprints = [
        SprintData(sprint_id=41, name="Sprint 41", start_date="2026-01-28",
                   end_date="2026-02-10", completed_points=28, state="closed"),
        SprintData(sprint_id=42, name="Sprint 42", start_date="2026-02-11",
                   end_date="2026-02-24", completed_points=34, state="closed"),
        SprintData(sprint_id=43, name="Sprint 43", start_date="2026-02-25",
                   end_date="2026-03-10", completed_points=21, state="closed",
                   carry_overs=[{"key": "PROJ-456", "summary": "Webhook retry logic", "points": 3}]),
        SprintData(sprint_id=44, name="Sprint 44", start_date="2026-03-11",
                   end_date="2026-03-24", completed_points=38, state="closed"),
        report.current_sprint,
    ]
    report.total_bugs_created = 12
    report.total_bugs_resolved = 15
    report.total_carry_overs = [
        {"key": "PROJ-456", "summary": "Webhook retry logic", "points": 3},
        {"key": "PROJ-789", "summary": "Config migration", "points": 2},
    ]
    report.avg_velocity = 29.0
    report.trend = "up"

    output = format_report(report)
    assert "Sprint Velocity" in output
    assert "my-service" in output
    assert "Sprint 45" in output
    assert "Payment gateway refactoring" in output
    assert "Sprint 41" in output
    assert "Bug Rate" in output
    assert "Carry-Over" in output
    assert "PROJ-456" in output
    assert "^ improving" in output


def test_format_report_git_fallback():
    """Git fallback report should show merge counts and tip."""
    report = VelocityReport(project_key="N/A", repo_name="my-repo", source="git")
    report.sprints = [
        SprintData(sprint_id=0, name="Week Mar 16 - Mar 30", start_date="2026-03-16",
                   end_date="2026-03-30", completed_points=5, state="closed"),
        SprintData(sprint_id=1, name="Week Mar 30 - Apr 13", start_date="2026-03-30",
                   end_date="2026-04-13", completed_points=8, state="active"),
    ]
    report.avg_velocity = 5.0
    report.trend = "up"
    report.current_sprint = report.sprints[-1]

    output = format_report(report)
    assert "PRs" in output
    assert "git merge count" in output
    assert "code-agents init --jira" in output
    assert "Bug Rate" not in output  # no bugs section for git


def test_format_report_empty():
    """Empty report should not crash."""
    report = VelocityReport(project_key="PROJ", repo_name="empty")
    output = format_report(report)
    assert "Sprint Velocity" in output
    assert "empty" in output


# ── Jira API integration ────────────────────────────────────────────

def test_get_current_sprint_no_jira(tracker_no_jira):
    """Without Jira, current sprint returns None."""
    assert tracker_no_jira.get_current_sprint() is None


def test_get_sprint_issues_no_jira(tracker_no_jira):
    """Without Jira, sprint issues returns empty list."""
    assert tracker_no_jira.get_sprint_issues(42) == []


def test_jira_search_handles_error(tracker):
    """Jira search should return empty list on HTTP error."""
    with patch("httpx.get", side_effect=Exception("Connection refused")):
        result = tracker._jira_search("project=PROJ")
        assert result == []


def test_get_current_sprint_with_mock(tracker):
    """Current sprint parsing from Jira issues."""
    mock_issues = [
        {
            "key": "PROJ-100",
            "fields": {
                "summary": "Auth module refactor",
                "status": {"name": "Done"},
                "issuetype": {"name": "Story"},
                "story_points": 5,
                "sprint": {
                    "id": 45,
                    "name": "Sprint 45",
                    "startDate": "2026-03-25",
                    "endDate": "2026-04-07",
                    "goal": "Payment gateway refactoring",
                },
            },
        },
        {
            "key": "PROJ-101",
            "fields": {
                "summary": "Fix timeout bug",
                "status": {"name": "In Progress"},
                "issuetype": {"name": "Bug"},
                "story_points": 3,
                "sprint": {
                    "id": 45,
                    "name": "Sprint 45",
                    "startDate": "2026-03-25",
                    "endDate": "2026-04-07",
                    "goal": "Payment gateway refactoring",
                },
            },
        },
    ]

    with patch.object(tracker, "_jira_search", return_value=mock_issues):
        sprint = tracker.get_current_sprint()

    assert sprint is not None
    assert sprint.name == "Sprint 45"
    assert sprint.completed_points == 5
    assert sprint.committed_points == 8
    assert len(sprint.issues) == 2


def test_extract_sprint_info_list_field():
    """Sprint info extraction from list-type sprint field."""
    issues = [
        {
            "fields": {
                "sprint": [
                    {"id": 40, "name": "Sprint 40", "startDate": "2026-01-01", "endDate": "2026-01-14"},
                    {"id": 41, "name": "Sprint 41", "startDate": "2026-01-15", "endDate": "2026-01-28"},
                ],
            },
        }
    ]
    info = SprintVelocityTracker._extract_sprint_info(issues)
    assert info["name"] == "Sprint 41"  # last sprint in list


def test_extract_sprint_info_none():
    """Sprint info extraction returns None when no sprint field."""
    issues = [{"fields": {}}]
    info = SprintVelocityTracker._extract_sprint_info(issues)
    assert info is None


# ── Server URL ──────────────────────────────────────────────────────

def test_server_url_default(tracker):
    assert "127.0.0.1:8000" in tracker._server_url


def test_server_url_custom(tmp_path):
    os.environ["JIRA_URL"] = "https://jira.example.com"
    os.environ["JIRA_PROJECT_KEY"] = "PROJ"
    os.environ["CODE_AGENTS_PUBLIC_BASE_URL"] = "http://localhost:9000"
    t = SprintVelocityTracker(cwd=str(tmp_path))
    assert t._server_url == "http://localhost:9000"
    os.environ.pop("CODE_AGENTS_PUBLIC_BASE_URL", None)
    os.environ.pop("JIRA_URL", None)
    os.environ.pop("JIRA_PROJECT_KEY", None)


# ── Additional sprint velocity tests ─────────────────────────────────


def test_server_url_0000_replaced(tmp_path):
    """HOST=0.0.0.0 should be replaced with 127.0.0.1."""
    os.environ["JIRA_URL"] = "https://jira.example.com"
    os.environ["JIRA_PROJECT_KEY"] = "PROJ"
    os.environ["HOST"] = "0.0.0.0"
    os.environ["PORT"] = "9000"
    os.environ.pop("CODE_AGENTS_PUBLIC_BASE_URL", None)
    t = SprintVelocityTracker(cwd=str(tmp_path))
    assert "127.0.0.1:9000" in t._server_url
    os.environ.pop("JIRA_URL", None)
    os.environ.pop("JIRA_PROJECT_KEY", None)


def test_get_sprint_issues_with_jira(tracker):
    """Sprint issues with Jira uses server API."""
    mock_issues = [
        {
            "key": "PROJ-50",
            "fields": {
                "summary": "Add retry logic",
                "status": {"name": "Done"},
                "issuetype": {"name": "Story"},
                "story_points": 5,
            },
        },
    ]
    with patch.object(tracker, "_jira_search", return_value=mock_issues):
        result = tracker.get_sprint_issues(42)
    assert len(result) == 1
    assert result[0]["key"] == "PROJ-50"
    assert result[0]["points"] == 5


def test_get_current_sprint_no_issues(tracker):
    """get_current_sprint returns None when search returns no issues."""
    with patch.object(tracker, "_jira_search", return_value=[]):
        assert tracker.get_current_sprint() is None


def test_get_current_sprint_no_sprint_field(tracker):
    """get_current_sprint returns None when issues have no sprint field."""
    mock_issues = [
        {"key": "PROJ-1", "fields": {"summary": "A", "status": {"name": "Done"}}},
    ]
    with patch.object(tracker, "_jira_search", return_value=mock_issues):
        assert tracker.get_current_sprint() is None


def test_extract_sprint_info_dict_field():
    """Sprint info extraction from dict-type sprint field."""
    issues = [
        {"fields": {"sprint": {"id": 45, "name": "Sprint 45", "startDate": "2026-04-01"}}}
    ]
    info = SprintVelocityTracker._extract_sprint_info(issues)
    assert info["id"] == 45


def test_extract_sprint_info_customfield():
    """Sprint info extraction from customfield_10020."""
    issues = [
        {"fields": {"customfield_10020": {"id": 50, "name": "Sprint 50"}}}
    ]
    info = SprintVelocityTracker._extract_sprint_info(issues)
    assert info["id"] == 50


def test_compute_stats_aggregates_bugs():
    """Bug counts from sprints should be aggregated."""
    report = VelocityReport(project_key="PROJ", repo_name="test")
    report.sprints = [
        SprintData(sprint_id=1, name="S1", start_date="", end_date="",
                   completed_points=20, state="closed",
                   bugs_created=3, bugs_resolved=2),
    ]
    SprintVelocityTracker._compute_stats(report)
    assert report.total_bugs_created == 3
    assert report.total_bugs_resolved == 2


def test_velocity_from_jira_with_mock(tracker):
    """Test _velocity_from_jira with mocked Jira API."""
    mock_current = SprintData(
        sprint_id=45, name="Sprint 45", start_date="2026-03-25",
        end_date="2026-04-07", state="active", completed_points=15,
    )
    with patch.object(tracker, "get_current_sprint", return_value=mock_current):
        with patch.object(tracker, "_jira_search", return_value=[]):
            report = tracker._velocity_from_jira(5)
    assert report.source == "jira"
    assert report.current_sprint is not None
    assert report.current_sprint.name == "Sprint 45"


def test_format_report_no_carry_overs():
    """Report without carry-overs should not show carry-over section."""
    report = VelocityReport(project_key="PROJ", repo_name="test", source="jira")
    report.sprints = [
        SprintData(sprint_id=1, name="S1", start_date="", end_date="",
                   completed_points=20, state="closed"),
    ]
    report.avg_velocity = 20.0
    report.trend = "stable"
    output = format_report(report)
    assert "Carry-Over" not in output


def test_get_carry_overs_with_jira(tracker):
    """Test carry-overs from Jira with mock data."""
    mock_issues = [
        {
            "key": "PROJ-10",
            "fields": {
                "summary": "Unfinished story",
                "status": {"name": "In Progress"},
                "story_points": 3,
            },
        },
        {
            "key": "PROJ-11",
            "fields": {
                "summary": "Done story",
                "status": {"name": "Done"},
                "story_points": 5,
            },
        },
    ]
    with patch.object(tracker, "_jira_search", return_value=mock_issues):
        carry = tracker.get_carry_overs()
    assert len(carry) == 1
    assert carry[0]["key"] == "PROJ-10"
