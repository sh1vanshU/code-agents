"""Tests for Sprint Velocity Dashboard."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from code_agents.domain.sprint_dashboard import (
    BlockerInfo,
    ContributorStats,
    CycleTimeMetrics,
    SprintDashboard,
    SprintDashboardReport,
    ThroughputMetrics,
    format_sprint_dashboard,
)


class TestSprintDashboard:
    """Tests for SprintDashboard."""

    def test_init_defaults(self):
        dashboard = SprintDashboard()
        assert dashboard.period_days == 14
        assert dashboard.sprint == "current"

    def test_init_custom(self):
        dashboard = SprintDashboard(period_days=7, sprint="Sprint 42")
        assert dashboard.period_days == 7
        assert dashboard.sprint == "Sprint 42"

    @patch.object(SprintDashboard, "_run_git")
    def test_calculate_throughput(self, mock_git):
        mock_git.side_effect = [
            "abc feat: add login\ndef fix: typo",  # commits
            "merge1 Merge PR #1",  # merges
            " 3 files changed, 100 insertions(+), 20 deletions(-)",  # stat
            "Alice\nBob\nAlice",  # authors
        ]
        dashboard = SprintDashboard()
        from datetime import datetime, timedelta
        t = dashboard._calculate_throughput(
            datetime.now() - timedelta(days=14), datetime.now(),
        )
        assert t.commits == 2
        assert t.prs_merged == 1
        assert t.authors == 2

    @patch.object(SprintDashboard, "_run_git")
    def test_calculate_throughput_empty(self, mock_git):
        mock_git.return_value = ""
        dashboard = SprintDashboard()
        from datetime import datetime, timedelta
        t = dashboard._calculate_throughput(
            datetime.now() - timedelta(days=7), datetime.now(),
        )
        assert t.commits == 0

    @patch.object(SprintDashboard, "_run_git")
    def test_get_contributors(self, mock_git):
        mock_git.side_effect = [
            "     5\tAlice <alice@test.com>\n     3\tBob <bob@test.com>",  # shortlog
            " 50 insertions(+), 10 deletions(-)",  # alice stat
            " 30 insertions(+), 5 deletions(-)",  # bob stat
        ]
        dashboard = SprintDashboard()
        from datetime import datetime, timedelta
        contributors = dashboard._get_contributors(
            datetime.now() - timedelta(days=14), datetime.now(),
        )
        assert len(contributors) == 2
        assert contributors[0].name == "Alice"
        assert contributors[0].commits == 5

    @patch.object(SprintDashboard, "_run_git")
    def test_find_blockers_stale_branch(self, mock_git):
        mock_git.side_effect = [
            "feature-old|3 weeks ago\nmain|2 hours ago",  # branches
            "",  # status
        ]
        dashboard = SprintDashboard()
        blockers = dashboard._find_blockers()
        assert any("Stale branch" in b.description for b in blockers)

    @patch.object(SprintDashboard, "_run_git")
    def test_find_blockers_clean(self, mock_git):
        mock_git.side_effect = [
            "main|2 hours ago",  # branches
            "",  # status (no conflicts)
        ]
        dashboard = SprintDashboard()
        blockers = dashboard._find_blockers()
        assert len(blockers) == 0

    @patch.object(SprintDashboard, "_run_git")
    def test_get_top_files(self, mock_git):
        mock_git.return_value = "src/auth.py\nsrc/auth.py\nsrc/login.py"
        dashboard = SprintDashboard()
        from datetime import datetime, timedelta
        top = dashboard._get_top_files(
            datetime.now() - timedelta(days=7), datetime.now(),
        )
        assert top[0]["file"] == "src/auth.py"
        assert top[0]["changes"] == 2

    def test_generate_summary(self):
        dashboard = SprintDashboard()
        throughput = ThroughputMetrics(commits=10, prs_merged=5, authors=3,
                                       lines_added=500, lines_removed=100)
        cycle_time = CycleTimeMetrics(avg_days=2.0, p50_days=1.5)
        contributors = [ContributorStats(name="Alice", commits=7)]
        summary = dashboard._generate_summary(throughput, cycle_time, contributors, [])
        assert "10 commits" in summary
        assert "3 contributor" in summary


class TestFormatSprintDashboard:
    """Tests for format_sprint_dashboard."""

    def test_format_full(self):
        report = SprintDashboardReport(
            sprint_name="Sprint 42",
            period_days=14,
            start_date="2026-03-25",
            end_date="2026-04-08",
            throughput=ThroughputMetrics(commits=25, prs_merged=8, files_changed=40,
                                         lines_added=1200, lines_removed=300, authors=4),
            cycle_time=CycleTimeMetrics(avg_days=1.5, p50_days=1.0, p90_days=3.0,
                                         sample_size=8),
            contributors=[ContributorStats(name="Alice", commits=10, lines_added=500, lines_removed=100)],
            blockers=[BlockerInfo(description="Stale PR #42", severity="medium")],
            top_files=[{"file": "auth.py", "changes": 5}],
            commit_activity={"2026-04-01": 5, "2026-04-02": 3},
            weekly_summary="Sprint summary...",
        )
        output = format_sprint_dashboard(report)
        assert "Sprint 42" in output
        assert "Throughput" in output
        assert "Cycle Time" in output
        assert "Alice" in output
        assert "auth.py" in output
        assert "Blockers" in output

    def test_format_minimal(self):
        report = SprintDashboardReport(sprint_name="Test")
        output = format_sprint_dashboard(report)
        assert "Sprint Dashboard" in output
