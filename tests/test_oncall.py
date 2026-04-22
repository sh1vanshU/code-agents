"""Tests for oncall.py — on-call handoff report generation."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest

from code_agents.reporters.oncall import (
    OncallReport,
    OncallReporter,
    format_oncall_report,
    generate_oncall_markdown,
)


class TestOncallReportDataclass:
    """Test OncallReport dataclass defaults and fields."""

    def test_defaults(self):
        r = OncallReport(period_start="2026-03-25", period_end="2026-04-01", repo_name="my-repo")
        assert r.total_commits == 0
        assert r.commits_by_author == {}
        assert r.branches_merged == []
        assert r.deploys == []
        assert r.incidents == []
        assert r.build_failures == 0
        assert r.test_failures == 0
        assert r.flaky_areas == []
        assert r.open_issues == []
        assert r.watch_items == []

    def test_custom_values(self):
        r = OncallReport(
            period_start="2026-03-25",
            period_end="2026-04-01",
            repo_name="svc",
            total_commits=42,
            build_failures=3,
        )
        assert r.total_commits == 42
        assert r.build_failures == 3
        assert r.repo_name == "svc"


class TestOncallReporterInit:
    """Test OncallReporter initialization."""

    def test_default_days(self):
        reporter = OncallReporter(cwd="/tmp/test-repo")
        assert reporter.days == 7
        assert reporter.repo_name == "test-repo"
        expected_since = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        assert reporter.since == expected_since

    def test_custom_days(self):
        reporter = OncallReporter(cwd="/tmp/my-project", days=14)
        assert reporter.days == 14
        expected_since = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")
        assert reporter.since == expected_since

    def test_report_period(self):
        reporter = OncallReporter(cwd="/tmp/repo", days=3)
        assert reporter.report.period_end == datetime.now().strftime("%Y-%m-%d")
        expected_start = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
        assert reporter.report.period_start == expected_start

    def test_server_url_from_env(self):
        with patch.dict(os.environ, {"CODE_AGENTS_PUBLIC_BASE_URL": "http://myhost:9000"}):
            reporter = OncallReporter(cwd="/tmp/repo")
            assert reporter.server_url == "http://myhost:9000"

    def test_server_url_default(self):
        with patch.dict(os.environ, {}, clear=True):
            reporter = OncallReporter(cwd="/tmp/repo")
            assert reporter.server_url == "http://127.0.0.1:8000"


class TestCollectGitActivity:
    """Test _collect_git_activity with mocked subprocess."""

    @patch("subprocess.run")
    def test_commit_count(self, mock_run):
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="abc1234 feat: add feature\ndef5678 fix: bug fix\n",
        )
        reporter = OncallReporter(cwd="/tmp/repo")
        reporter._collect_git_activity()
        # Called 3 times: log --oneline, shortlog, log --merges
        assert mock_run.call_count == 3
        assert reporter.report.total_commits == 2

    @patch("subprocess.run")
    def test_empty_repo(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        reporter = OncallReporter(cwd="/tmp/repo")
        reporter._collect_git_activity()
        assert reporter.report.total_commits == 0

    @patch("subprocess.run")
    def test_shortlog_parsing(self, mock_run):
        # First call: oneline log
        # Second call: shortlog
        # Third call: merges
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout="abc feat\ndef fix\n"),
            MagicMock(returncode=0, stdout="     5\tAlice\n     3\tBob\n"),
            MagicMock(returncode=0, stdout=""),
        ]
        reporter = OncallReporter(cwd="/tmp/repo")
        reporter._collect_git_activity()
        assert reporter.report.commits_by_author == {"Alice": 5, "Bob": 3}

    @patch("subprocess.run")
    def test_git_failure_handled(self, mock_run):
        mock_run.return_value = MagicMock(returncode=128, stdout="")
        reporter = OncallReporter(cwd="/tmp/repo")
        reporter._collect_git_activity()
        assert reporter.report.total_commits == 0


class TestGenerateWatchItems:
    """Test _generate_watch_items logic."""

    def test_no_issues(self):
        reporter = OncallReporter(cwd="/tmp/repo")
        reporter._generate_watch_items()
        assert reporter.report.watch_items == []

    def test_build_failures(self):
        reporter = OncallReporter(cwd="/tmp/repo")
        reporter.report.build_failures = 5
        reporter._generate_watch_items()
        assert any("Build failures" in item for item in reporter.report.watch_items)

    def test_test_failures(self):
        reporter = OncallReporter(cwd="/tmp/repo")
        reporter.report.test_failures = 3
        reporter._generate_watch_items()
        assert any("Test failures" in item for item in reporter.report.watch_items)

    def test_unhealthy_deploy(self):
        reporter = OncallReporter(cwd="/tmp/repo")
        reporter.report.deploys = [{"app": "my-app", "status": "Degraded"}]
        reporter._generate_watch_items()
        assert any("Deploy unhealthy" in item for item in reporter.report.watch_items)

    def test_healthy_deploy_no_watch(self):
        reporter = OncallReporter(cwd="/tmp/repo")
        reporter.report.deploys = [{"app": "my-app", "status": "Healthy"}]
        reporter._generate_watch_items()
        assert not any("Deploy unhealthy" in item for item in reporter.report.watch_items)

    def test_flaky_areas(self):
        reporter = OncallReporter(cwd="/tmp/repo")
        reporter.report.flaky_areas = ["test_a", "test_b"]
        reporter._generate_watch_items()
        assert any("Flaky test areas" in item for item in reporter.report.watch_items)

    def test_high_open_bugs(self):
        reporter = OncallReporter(cwd="/tmp/repo")
        reporter.report.open_issues = [f"BUG-{i}: issue" for i in range(8)]
        reporter._generate_watch_items()
        assert any("High open bug count" in item for item in reporter.report.watch_items)

    def test_low_open_bugs_no_watch(self):
        reporter = OncallReporter(cwd="/tmp/repo")
        reporter.report.open_issues = ["BUG-1: issue"]
        reporter._generate_watch_items()
        assert not any("High open bug count" in item for item in reporter.report.watch_items)


class TestFormatOncallReport:
    """Test format_oncall_report terminal output."""

    def test_header_contains_repo(self):
        r = OncallReport(period_start="2026-03-25", period_end="2026-04-01", repo_name="my-svc")
        output = format_oncall_report(r)
        assert "my-svc" in output
        assert "2026-03-25" in output
        assert "2026-04-01" in output

    def test_commits_section(self):
        r = OncallReport(
            period_start="2026-03-25", period_end="2026-04-01", repo_name="svc",
            total_commits=10, commits_by_author={"Alice": 7, "Bob": 3},
        )
        output = format_oncall_report(r)
        assert "10 commits" in output
        assert "Alice: 7 commits" in output
        assert "Bob: 3 commits" in output

    def test_deploys_section(self):
        r = OncallReport(
            period_start="2026-03-25", period_end="2026-04-01", repo_name="svc",
            deploys=[{"app": "my-app", "status": "Healthy", "sync": "Synced"}],
        )
        output = format_oncall_report(r)
        assert "my-app" in output
        assert "[ok]" in output

    def test_unhealthy_deploy_icon(self):
        r = OncallReport(
            period_start="2026-03-25", period_end="2026-04-01", repo_name="svc",
            deploys=[{"app": "my-app", "status": "Degraded", "sync": "OutOfSync"}],
        )
        output = format_oncall_report(r)
        assert "[!]" in output

    def test_build_health_section(self):
        r = OncallReport(
            period_start="2026-03-25", period_end="2026-04-01", repo_name="svc",
            build_failures=2, test_failures=5,
        )
        output = format_oncall_report(r)
        assert "Build failures: 2" in output
        assert "Test failures: 5" in output

    def test_watch_items_section(self):
        r = OncallReport(
            period_start="2026-03-25", period_end="2026-04-01", repo_name="svc",
            watch_items=["Deploy unhealthy: my-app"],
        )
        output = format_oncall_report(r)
        assert "Watch Items" in output
        assert "Deploy unhealthy: my-app" in output

    def test_incidents_section(self):
        r = OncallReport(
            period_start="2026-03-25", period_end="2026-04-01", repo_name="svc",
            incidents=[{"key": "BUG-1", "summary": "Login broken", "status": "Open"}],
        )
        output = format_oncall_report(r)
        assert "BUG-1" in output
        assert "Login broken" in output

    def test_open_bugs_section(self):
        r = OncallReport(
            period_start="2026-03-25", period_end="2026-04-01", repo_name="svc",
            open_issues=["BUG-1: Login broken", "BUG-2: Timeout"],
        )
        output = format_oncall_report(r)
        assert "Open Bugs (2)" in output
        assert "BUG-1: Login broken" in output


class TestGenerateOncallMarkdown:
    """Test generate_oncall_markdown output."""

    def test_markdown_header(self):
        r = OncallReport(period_start="2026-03-25", period_end="2026-04-01", repo_name="my-svc")
        md = generate_oncall_markdown(r)
        assert "# On-Call Handoff -- my-svc" in md
        assert "2026-03-25" in md

    def test_markdown_contributors(self):
        r = OncallReport(
            period_start="2026-03-25", period_end="2026-04-01", repo_name="svc",
            total_commits=10, commits_by_author={"Alice": 7, "Bob": 3},
        )
        md = generate_oncall_markdown(r)
        assert "- Alice: 7" in md
        assert "- Bob: 3" in md
        assert "**10 commits**" in md

    def test_markdown_no_deploys(self):
        r = OncallReport(period_start="2026-03-25", period_end="2026-04-01", repo_name="svc")
        md = generate_oncall_markdown(r)
        assert "- No deploy data" in md

    def test_markdown_no_incidents(self):
        r = OncallReport(period_start="2026-03-25", period_end="2026-04-01", repo_name="svc")
        md = generate_oncall_markdown(r)
        assert "- No incidents this period" in md

    def test_markdown_watch_items(self):
        r = OncallReport(
            period_start="2026-03-25", period_end="2026-04-01", repo_name="svc",
            watch_items=["Build failures this week: 3"],
        )
        md = generate_oncall_markdown(r)
        assert "Build failures this week: 3" in md

    def test_markdown_all_clear(self):
        r = OncallReport(period_start="2026-03-25", period_end="2026-04-01", repo_name="svc")
        md = generate_oncall_markdown(r)
        assert "- All clear" in md


class TestGenerateFullReport:
    """Test OncallReporter.generate() orchestration."""

    @patch("subprocess.run")
    def test_generate_catches_step_errors(self, mock_run):
        """Steps that fail should not crash the whole report."""
        mock_run.side_effect = Exception("git not found")
        reporter = OncallReporter(cwd="/tmp/repo")
        report = reporter.generate()
        # Should still return a report even if steps fail
        assert report.repo_name == "repo"
        assert report.total_commits == 0

    @patch("subprocess.run")
    def test_generate_returns_report(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        reporter = OncallReporter(cwd="/tmp/my-project")
        report = reporter.generate()
        assert isinstance(report, OncallReport)
        assert report.repo_name == "my-project"
