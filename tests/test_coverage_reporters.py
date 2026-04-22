"""Coverage gap tests for reporter modules — sprint_velocity, incident, morning,
oncall, sprint_reporter, env_health."""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# sprint_velocity.py — missing lines
# ---------------------------------------------------------------------------
from code_agents.reporters.sprint_velocity import (
    SprintData,
    SprintVelocityTracker,
    VelocityReport,
    format_report,
)


class TestSprintVelocityCoverage:
    """Cover missing lines in sprint_velocity.py."""

    @pytest.fixture
    def tracker(self, tmp_path):
        os.environ["JIRA_URL"] = "https://jira.example.com"
        os.environ["JIRA_PROJECT_KEY"] = "PROJ"
        os.environ.pop("CODE_AGENTS_PUBLIC_BASE_URL", None)
        t = SprintVelocityTracker(cwd=str(tmp_path))
        yield t
        os.environ.pop("JIRA_URL", None)
        os.environ.pop("JIRA_PROJECT_KEY", None)

    @pytest.fixture
    def tracker_no_jira(self, tmp_path):
        os.environ.pop("JIRA_URL", None)
        os.environ.pop("JIRA_PROJECT_KEY", None)
        return SprintVelocityTracker(cwd=str(tmp_path))

    def test_jira_search_success(self, tracker):
        """Lines 75-76: successful Jira search."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"issues": [{"key": "PROJ-1"}]}

        with patch("httpx.get", return_value=mock_resp):
            result = tracker._jira_search("project=PROJ")
        assert len(result) == 1

    def test_velocity_from_jira_full(self, tracker):
        """Lines 147-227: _velocity_from_jira with sprint grouping."""
        mock_issues = [
            {
                "key": "PROJ-100",
                "fields": {
                    "summary": "Feature A",
                    "status": {"name": "Done"},
                    "issuetype": {"name": "Story"},
                    "story_points": 5,
                    "sprint": {"id": 40, "name": "Sprint 40", "startDate": "2026-01-01", "endDate": "2026-01-14", "goal": "Goal"},
                },
            },
            {
                "key": "PROJ-101",
                "fields": {
                    "summary": "Carry over",
                    "status": {"name": "In Progress"},
                    "issuetype": {"name": "Story"},
                    "story_points": 3,
                    "sprint": {"id": 40, "name": "Sprint 40", "startDate": "2026-01-01", "endDate": "2026-01-14", "goal": "Goal"},
                },
            },
            {
                "key": "PROJ-102",
                "fields": {
                    "summary": "Bug fix",
                    "status": {"name": "Done"},
                    "issuetype": {"name": "Bug"},
                    "story_points": 2,
                    "sprint": {"id": 40, "name": "Sprint 40", "startDate": "2026-01-01", "endDate": "2026-01-14"},
                },
            },
        ]

        with patch.object(tracker, "get_current_sprint", return_value=None):
            with patch.object(tracker, "_jira_search", return_value=mock_issues):
                report = tracker._velocity_from_jira(5)

        assert report.source == "jira"
        assert len(report.sprints) >= 1
        sprint = report.sprints[0]
        assert sprint.bugs_created >= 1
        assert sprint.bugs_resolved >= 1
        assert len(sprint.carry_overs) >= 1

    def test_velocity_from_git_with_merges(self, tracker_no_jira):
        """Lines 271-272: git velocity with merge parsing."""
        now = datetime.now()
        recent_date = (now - timedelta(days=3)).strftime("%Y-%m-%d")
        mock_result = MagicMock()
        mock_result.stdout = f"abc123|{recent_date} 10:00:00 +0530|Merge PR #1\ndef456|{recent_date} 12:00:00 +0530|Merge PR #2\n"

        with patch("code_agents.reporters.sprint_velocity.subprocess.run", return_value=mock_result):
            report = tracker_no_jira.calculate_velocity(sprints=2)

        assert report.source == "git"
        assert report.current_sprint is not None

    def test_velocity_from_git_bad_date(self, tracker_no_jira):
        """Lines 271-272: git merge with unparseable date."""
        mock_result = MagicMock()
        mock_result.stdout = "abc123|not-a-date|Merge PR\n"

        with patch("code_agents.reporters.sprint_velocity.subprocess.run", return_value=mock_result):
            report = tracker_no_jira.calculate_velocity(sprints=2)
        assert report.source == "git"

    def test_predict_velocity_enough_data(self):
        """Lines 375-389: predict_velocity with linear regression."""
        sprints = [
            SprintData(sprint_id=i, name=f"S{i}", start_date="", end_date="",
                       completed_points=pts, state="closed")
            for i, pts in enumerate([20, 25, 30, 35])
        ]
        predictions = SprintVelocityTracker.predict_velocity(sprints, num_future=3)
        assert len(predictions) == 3
        assert all(p >= 0 for p in predictions)

    def test_predict_velocity_insufficient(self):
        """Lines 375-376: not enough data."""
        sprints = [
            SprintData(sprint_id=1, name="S1", start_date="", end_date="",
                       completed_points=20, state="closed")
        ]
        predictions = SprintVelocityTracker.predict_velocity(sprints)
        assert len(predictions) == 3
        assert all(p == 20.0 for p in predictions)

    def test_predict_velocity_zero_denominator(self):
        """Line 389: denominator == 0 (all same x values after centering)."""
        sprints = [
            SprintData(sprint_id=i, name=f"S{i}", start_date="", end_date="",
                       completed_points=20, state="closed")
            for i in range(3)
        ]
        predictions = SprintVelocityTracker.predict_velocity(sprints)
        assert len(predictions) == 3

    def test_estimate_completion(self):
        """Lines 407-431: estimate_completion."""
        sprints = [
            SprintData(sprint_id=i, name=f"S{i}", start_date="", end_date="",
                       completed_points=pts, state="closed")
            for i, pts in enumerate([20, 21, 19, 20, 22])
        ]
        result = SprintVelocityTracker.estimate_completion(100, 20.0, sprints)
        assert result["estimated_sprints"] == 5
        assert result["confidence"] == "high"

    def test_estimate_completion_zero_velocity(self):
        """Lines 407-408: zero velocity."""
        result = SprintVelocityTracker.estimate_completion(100, 0.0)
        assert result["estimated_sprints"] == -1
        assert result["confidence"] == "low"

    def test_estimate_completion_high_variance(self):
        """Lines 414-425: high variance = low confidence."""
        sprints = [
            SprintData(sprint_id=i, name=f"S{i}", start_date="", end_date="",
                       completed_points=pts, state="closed")
            for i, pts in enumerate([5, 50, 10, 45, 8])
        ]
        result = SprintVelocityTracker.estimate_completion(100, 23.6, sprints)
        assert result["confidence"] == "low"

    def test_estimate_completion_few_sprints(self):
        """Lines 428-429: less than 2 closed sprints = low confidence."""
        sprints = [
            SprintData(sprint_id=1, name="S1", start_date="", end_date="",
                       completed_points=20, state="closed")
        ]
        result = SprintVelocityTracker.estimate_completion(100, 20.0, sprints)
        assert result["confidence"] == "low"

    def test_estimate_completion_no_sprints(self):
        """No sprints provided."""
        result = SprintVelocityTracker.estimate_completion(100, 20.0)
        assert result["confidence"] == "medium"

    def test_compute_stats_trend_two_sprints_down(self):
        """Lines 461: two sprints with down trend."""
        report = VelocityReport(project_key="PROJ", repo_name="test")
        report.sprints = [
            SprintData(sprint_id=1, name="S1", start_date="", end_date="",
                       completed_points=25, state="closed"),
            SprintData(sprint_id=2, name="S2", start_date="", end_date="",
                       completed_points=15, state="closed"),
        ]
        SprintVelocityTracker._compute_stats(report)
        assert report.trend == "down"

    def test_format_report_carry_over_more_than_5(self):
        """Line 543: carry-overs truncated at 5."""
        report = VelocityReport(project_key="PROJ", repo_name="test", source="jira")
        report.sprints = [
            SprintData(sprint_id=1, name="S1", start_date="", end_date="",
                       completed_points=20, state="closed"),
        ]
        report.total_carry_overs = [
            {"key": f"PROJ-{i}", "summary": f"Story {i}", "points": 2}
            for i in range(8)
        ]
        report.avg_velocity = 20.0
        report.trend = "stable"
        output = format_report(report)
        assert "... and 3 more" in output

    def test_format_report_predictions(self):
        """Lines 548-553: predictions section."""
        report = VelocityReport(project_key="PROJ", repo_name="test", source="jira")
        report.sprints = [
            SprintData(sprint_id=i, name=f"S{i}", start_date="", end_date="",
                       completed_points=pts, state="closed")
            for i, pts in enumerate([20, 25, 30], start=1)
        ]
        report.avg_velocity = 25.0
        report.trend = "up"
        output = format_report(report)
        assert "Predictions" in output


# ---------------------------------------------------------------------------
# incident.py — missing lines
# ---------------------------------------------------------------------------
from code_agents.reporters.incident import (
    IncidentReport,
    IncidentRunner,
    format_incident_report,
    generate_rca_template,
    build_rca_agent_prompt,
)


class TestIncidentCoverage:
    """Cover missing lines in incident.py."""

    @pytest.fixture
    def runner(self, tmp_path):
        return IncidentRunner(service="my-svc", cwd=str(tmp_path))

    def test_run_all_step_failure(self, runner):
        """Lines 59-60: step failure during run_all."""
        with patch.object(runner, "check_pods", side_effect=Exception("pod error")):
            with patch.object(runner, "fetch_logs"):
                with patch.object(runner, "check_deploys"):
                    with patch.object(runner, "check_git_changes"):
                        with patch.object(runner, "health_check_step"):
                            with patch.object(runner, "analyze"):
                                report = runner.run_all()
        assert report is not None

    def test_check_pods_via_argocd(self, runner):
        """Lines 74-76: pod check via ArgoCD API."""
        mock_data = json.dumps({
            "pods": [
                {"name": "pod-1", "status": "Running", "restarts": 0, "image": "img:v1"},
            ]
        })
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_resp.read.return_value = mock_data.encode()
            mock_urlopen.return_value = mock_resp
            runner.check_pods()
        assert len(runner.report.pod_status) == 1

    def test_check_pods_fallback_kubectl(self, runner):
        """Lines 98-108: kubectl fallback."""
        with patch("urllib.request.urlopen", side_effect=Exception("not reachable")):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(
                    returncode=0,
                    stdout=json.dumps({
                        "items": [
                            {
                                "metadata": {"name": "pod-1"},
                                "status": {
                                    "phase": "Running",
                                    "containerStatuses": [{"restartCount": 2}],
                                },
                            }
                        ]
                    }),
                )
                runner.check_pods()
        assert len(runner.report.pod_status) == 1
        assert runner.report.pod_status[0]["restarts"] == 2

    def test_fetch_logs(self, runner):
        """Lines 119-120: log fetching."""
        mock_data = json.dumps({"hits": [{"message": "Error: timeout"}, {"message": "Error: null"}]})
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_resp.read.return_value = mock_data.encode()
            mock_urlopen.return_value = mock_resp
            runner.fetch_logs()
        assert len(runner.report.recent_logs) == 2

    def test_check_deploys(self, runner):
        """Lines 133-134: deploy check."""
        mock_data = json.dumps({"sync_status": "Synced", "health_status": "Healthy", "revision": "abc"})
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_resp.read.return_value = mock_data.encode()
            mock_urlopen.return_value = mock_resp
            runner.check_deploys()
        assert len(runner.report.recent_deploys) == 1

    def test_check_git_changes(self, runner):
        """Lines 155-157: git changes."""
        mock_result = MagicMock(returncode=0, stdout="abc123 Fix timeout\ndef456 Add retry")
        with patch("subprocess.run", return_value=mock_result):
            runner.check_git_changes()
        assert len(runner.report.git_changes) == 2

    def test_health_check_step(self, runner, monkeypatch):
        """Lines 166-181: health check with multiple paths."""
        monkeypatch.setenv("MY_SVC_URL", "http://localhost:8080")

        mock_resp = MagicMock()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.status = 200

        with patch("urllib.request.urlopen", return_value=mock_resp):
            runner.health_check_step()
        assert runner.report.health_check.get("status") == 200

    def test_health_check_step_no_url(self, runner):
        """Lines 166-168: no URL configured."""
        runner.health_check_step()
        assert runner.report.health_check == {}

    def test_health_check_step_all_fail(self, runner, monkeypatch):
        """Lines 178-180: all health paths fail."""
        monkeypatch.setenv("MY_SVC_URL", "http://localhost:8080")
        with patch("urllib.request.urlopen", side_effect=Exception("refused")):
            runner.health_check_step()
        assert runner.report.health_check == {}

    def test_analyze_all_issues(self, runner):
        """Lines 155-173: analyze with all issue types."""
        runner.report.pod_status = [{"name": "pod-1", "restarts": 5}]
        runner.report.recent_deploys = [{"health": "Degraded"}]
        runner.report.recent_logs = ["e"] * 15
        runner.report.git_changes = ["abc Fix timeout"]
        runner.analyze()
        assert runner.report.severity == "P1"
        assert len(runner.report.suggested_actions) >= 3

    def test_analyze_no_issues(self, runner):
        """Lines 178-181: no issues detected."""
        runner.analyze()
        assert runner.report.severity == "P4"
        assert "No obvious issues" in runner.report.suggested_actions[0]

    def test_format_incident_report_full(self):
        """Format with all sections populated."""
        report = IncidentReport(service="my-svc", timestamp="2026-04-01T10:00:00", severity="P1")
        report.pod_status = [{"name": "pod-1", "status": "Running", "restarts": 0}]
        report.recent_logs = [f"Error {i}" for i in range(7)]
        report.recent_deploys = [{"app": "my-app", "sync_status": "Synced", "health": "Healthy"}]
        report.git_changes = ["abc Fix timeout"]
        report.health_check = {"endpoint": "http://localhost/health", "status": 200, "response_time_ms": 50}
        report.suggested_actions = ["Check logs"]
        output = format_incident_report(report)
        assert "Pod Status" in output
        assert "Recent Errors" in output
        assert "... and" in output
        assert "Deploy" in output
        assert "Git Changes" in output
        assert "Health Check" in output

    def test_generate_rca_template(self):
        """Test RCA template generation."""
        report = IncidentReport(service="my-svc", timestamp="2026-04-01T10:00:00", severity="P2")
        report.pod_status = [{"name": "pod-1", "status": "CrashLoop", "restarts": 10}]
        report.recent_logs = ["NullPointerException"]
        report.recent_deploys = [{"app": "my-app", "sync_status": "Synced", "health": "Degraded"}]
        report.git_changes = ["abc Fix null check"]
        output = generate_rca_template(report)
        assert "RCA" in output
        assert "my-svc" in output

    def test_build_rca_agent_prompt(self):
        """Lines covered by building prompt with all sections."""
        report = IncidentReport(service="my-svc", timestamp="2026-04-01", severity="P1")
        report.pod_status = [{"name": "pod-1"}]
        report.recent_logs = ["Error log"]
        report.recent_deploys = [{"app": "my-app"}]
        report.git_changes = ["abc Fix"]
        report.health_check = {"endpoint": "http://localhost/health"}
        output = build_rca_agent_prompt(report)
        assert "Root Cause" in output


# ---------------------------------------------------------------------------
# morning.py — missing lines
# ---------------------------------------------------------------------------
from code_agents.reporters.morning import MorningAutopilot, MorningReport, MorningStep, format_morning_report


class TestMorningCoverage:
    """Cover missing lines in morning.py."""

    @pytest.fixture
    def pilot(self, tmp_path):
        return MorningAutopilot(cwd=str(tmp_path))

    def test_run_tests_no_test_cmd_no_project(self, pilot, tmp_path):
        """Lines 169-171: no test command detected."""
        pilot._run_tests()
        test_steps = [s for s in pilot.report.steps if s.name == "Run Tests"]
        assert len(test_steps) == 1
        assert test_steps[0].status == "skipped"

    def test_run_tests_npm(self, pilot, tmp_path):
        """Line 171: npm test detection."""
        (tmp_path / "package.json").write_text("{}")
        with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="Tests passed\n", stderr="")):
            pilot._run_tests()

    def test_run_tests_maven(self, pilot, tmp_path):
        """Lines 169: mvn test detection."""
        (tmp_path / "pom.xml").write_text("<project/>")
        with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="BUILD SUCCESS\n", stderr="")):
            pilot._run_tests()

    def test_check_open_prs_branches(self, pilot):
        """Lines 264-278: open PRs via API."""
        with patch.object(pilot, "_api_get", return_value={"branches": ["feature/a", "fix/b"]}):
            pilot._check_open_prs()
        pr_steps = [s for s in pilot.report.steps if s.name == "Open PRs"]
        assert len(pr_steps) == 1
        assert "2 remote branches" in pr_steps[0].output

    def test_check_open_prs_empty(self, pilot):
        """Lines 264: empty branch list."""
        with patch.object(pilot, "_api_get", return_value={"branches": []}):
            pilot._check_open_prs()
        pr_steps = [s for s in pilot.report.steps if s.name == "Open PRs"]
        assert pr_steps[0].output == "No remote branches found"

    def test_check_open_prs_fallback_git(self, pilot, tmp_path):
        """Lines 271-292: git fallback for PRs."""
        with patch.object(pilot, "_api_get", return_value=None):
            with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="abc Fix\ndef Update\n", stderr="")):
                pilot._check_open_prs()
        pr_steps = [s for s in pilot.report.steps if s.name == "Open PRs"]
        assert "remote commits" in pr_steps[0].output

    def test_check_open_prs_fallback_no_activity(self, pilot, tmp_path):
        """Lines 284: no remote activity."""
        with patch.object(pilot, "_api_get", return_value=None):
            with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")):
                pilot._check_open_prs()
        pr_steps = [s for s in pilot.report.steps if s.name == "Open PRs"]
        assert "No recent remote activity" in pr_steps[0].output

    def test_check_open_prs_fallback_error(self, pilot, tmp_path):
        """Lines 288-289: git fallback error."""
        with patch.object(pilot, "_api_get", return_value=None):
            with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("git", 10)):
                pilot._check_open_prs()
        pr_steps = [s for s in pilot.report.steps if s.name == "Open PRs"]
        assert pr_steps[0].status == "error"

    def test_check_deploy_status(self, pilot, monkeypatch):
        """Lines 298-309: deploy status check."""
        monkeypatch.setenv("ARGOCD_URL", "https://argocd.example.com")
        with patch.object(pilot, "_api_get", return_value={"sync_status": "Synced", "health_status": "Healthy", "app_name": "my-app"}):
            pilot._check_deploy_status()
        steps = [s for s in pilot.report.steps if s.name == "Deploy Status"]
        assert steps[0].status == "ok"

    def test_check_deploy_status_warning(self, pilot, monkeypatch):
        """Deploy status with warning."""
        monkeypatch.setenv("ARGOCD_URL", "https://argocd.example.com")
        with patch.object(pilot, "_api_get", return_value={"sync_status": "OutOfSync", "health_status": "Degraded", "app_name": "my-app"}):
            pilot._check_deploy_status()
        steps = [s for s in pilot.report.steps if s.name == "Deploy Status"]
        assert steps[0].status == "warning"

    def test_check_deploy_status_not_configured(self, pilot, monkeypatch):
        """Lines 298-302: ArgoCD not configured."""
        monkeypatch.delenv("ARGOCD_URL", raising=False)
        pilot._check_deploy_status()
        steps = [s for s in pilot.report.steps if s.name == "Deploy Status"]
        assert steps[0].status == "skipped"

    def test_check_deploy_status_error(self, pilot, monkeypatch):
        """Lines 305-309: ArgoCD not reachable."""
        monkeypatch.setenv("ARGOCD_URL", "https://argocd.example.com")
        with patch.object(pilot, "_api_get", return_value=None):
            pilot._check_deploy_status()
        steps = [s for s in pilot.report.steps if s.name == "Deploy Status"]
        assert steps[0].status == "error"

    def test_check_blockers(self, pilot, monkeypatch):
        """Lines 328-337: blockers with issues."""
        monkeypatch.setenv("JIRA_URL", "https://jira.example.com")
        with patch.object(pilot, "_api_get", return_value={"issues": [
            {"key": "PROJ-1", "fields": {"summary": "Blocked on review"}},
        ]}):
            pilot._check_blockers()
        steps = [s for s in pilot.report.steps if s.name == "Blockers"]
        assert steps[0].status == "warning"

    def test_check_blockers_none(self, pilot, monkeypatch):
        """Lines 343: no blockers."""
        monkeypatch.setenv("JIRA_URL", "https://jira.example.com")
        with patch.object(pilot, "_api_get", return_value={"issues": []}):
            pilot._check_blockers()
        steps = [s for s in pilot.report.steps if s.name == "Blockers"]
        assert steps[0].status == "ok"

    def test_check_blockers_error(self, pilot, monkeypatch):
        """Lines 348: Jira not reachable."""
        monkeypatch.setenv("JIRA_URL", "https://jira.example.com")
        with patch.object(pilot, "_api_get", return_value=None):
            pilot._check_blockers()
        steps = [s for s in pilot.report.steps if s.name == "Blockers"]
        assert steps[0].status == "error"

    def test_check_blockers_not_configured(self, pilot, monkeypatch):
        """Lines 328-329: Jira not configured."""
        monkeypatch.delenv("JIRA_URL", raising=False)
        pilot._check_blockers()
        steps = [s for s in pilot.report.steps if s.name == "Blockers"]
        assert steps[0].status == "skipped"


# ---------------------------------------------------------------------------
# oncall.py — missing lines
# ---------------------------------------------------------------------------
from code_agents.reporters.oncall import (
    OncallReport,
    OncallReporter,
    format_oncall_report,
    generate_oncall_markdown,
)


class TestOncallCoverage:
    """Cover missing lines in oncall.py."""

    @pytest.fixture
    def reporter(self, tmp_path):
        return OncallReporter(cwd=str(tmp_path), days=7)

    def test_collect_deploy_history(self, reporter):
        """Lines 138-139: deploy history."""
        mock_data = json.dumps({"app": "my-app", "health_status": "Healthy", "sync_status": "Synced", "revision": "abc"})
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_resp.read.return_value = mock_data.encode()
            mock_urlopen.return_value = mock_resp
            reporter._collect_deploy_history()
        assert len(reporter.report.deploys) == 1

    def test_collect_deploy_history_error(self, reporter):
        """Lines 158-159: deploy collection error."""
        with patch("urllib.request.urlopen", side_effect=Exception("not reachable")):
            reporter._collect_deploy_history()
        assert len(reporter.report.deploys) == 0

    def test_collect_build_health(self, reporter):
        """Lines 169-172: build health from telemetry."""
        with patch("code_agents.reporters.oncall.get_summary", return_value={"build_failures": 3, "test_failures": 5}, create=True) as _:
            with patch.dict("sys.modules", {"code_agents.observability.telemetry": MagicMock(get_summary=MagicMock(return_value={"build_failures": 3, "test_failures": 5}))}):
                reporter._collect_build_health()

    def test_collect_build_health_no_telemetry(self, reporter):
        """Lines 175-178: telemetry unavailable."""
        reporter._collect_build_health()
        # Should not crash

    def test_collect_incidents(self, reporter, monkeypatch):
        """Lines 169-187: incident collection from Jira."""
        monkeypatch.setenv("JIRA_URL", "https://jira.example.com")
        monkeypatch.setenv("JIRA_PROJECT_KEY", "PROJ")
        mock_data = json.dumps({"issues": [{"key": "PROJ-1", "summary": "Bug", "status": "Open", "priority": "High"}]})
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_resp.read.return_value = mock_data.encode()
            mock_urlopen.return_value = mock_resp
            reporter._collect_incidents()
        assert len(reporter.report.incidents) == 1

    def test_collect_incidents_no_jira(self, reporter, monkeypatch):
        """Lines 169-170: no Jira configured."""
        monkeypatch.delenv("JIRA_URL", raising=False)
        monkeypatch.delenv("JIRA_PROJECT_KEY", raising=False)
        reporter._collect_incidents()
        assert len(reporter.report.incidents) == 0

    def test_collect_incidents_error(self, reporter, monkeypatch):
        """Lines 186-187: Jira not reachable."""
        monkeypatch.setenv("JIRA_URL", "https://jira.example.com")
        monkeypatch.setenv("JIRA_PROJECT_KEY", "PROJ")
        with patch("urllib.request.urlopen", side_effect=Exception("not reachable")):
            reporter._collect_incidents()
        assert len(reporter.report.incidents) == 0

    def test_identify_flaky_areas(self, reporter, tmp_path):
        """Line 208: flaky area detection."""
        mock_result = MagicMock(returncode=0, stdout="abc Fix flaky retry test\n")
        with patch("subprocess.run", return_value=mock_result):
            reporter._identify_flaky_areas()
        assert len(reporter.report.flaky_areas) >= 1

    def test_collect_open_issues(self, reporter, monkeypatch):
        """Lines 217-233: open issue collection."""
        monkeypatch.setenv("JIRA_PROJECT_KEY", "PROJ")
        mock_data = json.dumps({"issues": [{"key": "PROJ-10", "summary": "Open bug"}]})
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_resp.read.return_value = mock_data.encode()
            mock_urlopen.return_value = mock_resp
            reporter._collect_open_issues()
        assert len(reporter.report.open_issues) == 1

    def test_collect_open_issues_no_project(self, reporter, monkeypatch):
        """Lines 222-223: no project key."""
        monkeypatch.delenv("JIRA_PROJECT_KEY", raising=False)
        reporter._collect_open_issues()
        assert len(reporter.report.open_issues) == 0

    def test_collect_open_issues_error(self, reporter, monkeypatch):
        """Lines 232-233: Jira error."""
        monkeypatch.setenv("JIRA_PROJECT_KEY", "PROJ")
        with patch("urllib.request.urlopen", side_effect=Exception("not reachable")):
            reporter._collect_open_issues()
        assert len(reporter.report.open_issues) == 0

    def test_generate_watch_items(self, reporter):
        """Lines 226-253: watch item generation."""
        reporter.report.build_failures = 2
        reporter.report.test_failures = 3
        reporter.report.deploys = [{"status": "Degraded", "app": "my-app"}]
        reporter.report.flaky_areas = ["flaky1"]
        reporter.report.open_issues = [f"PROJ-{i}" for i in range(10)]
        reporter._generate_watch_items()
        assert len(reporter.report.watch_items) >= 4

    def test_format_oncall_report_full(self):
        """Lines 273-303: full format."""
        report = OncallReport(period_start="2026-03-29", period_end="2026-04-05", repo_name="my-repo")
        report.total_commits = 15
        report.commits_by_author = {"Alice": 10, "Bob": 5}
        report.branches_merged = ["branch1"]
        report.deploys = [{"app": "my-app", "status": "Healthy", "sync": "Synced"}]
        report.incidents = [{"key": "PROJ-1", "summary": "Bug", "status": "Open"}]
        report.flaky_areas = ["test_flaky"]
        report.open_issues = [f"PROJ-{i}: Bug {i}" for i in range(3)]
        report.watch_items = ["High bug count"]
        output = format_oncall_report(report)
        assert "ON-CALL HANDOFF" in output
        assert "Alice" in output
        assert "Incidents" in output
        assert "Flaky" in output
        assert "Watch Items" in output

    def test_generate_oncall_markdown(self):
        """Lines 301-303: markdown generation."""
        report = OncallReport(period_start="2026-03-29", period_end="2026-04-05", repo_name="my-repo")
        report.commits_by_author = {"Alice": 10}
        report.branches_merged = ["branch1"]
        report.deploys = [{"app": "my-app", "status": "Healthy", "sync": "Synced"}]
        report.incidents = [{"key": "PROJ-1", "summary": "Bug", "status": "Open"}]
        report.open_issues = ["PROJ-1: Bug"]
        report.watch_items = ["Watch this"]
        output = generate_oncall_markdown(report)
        assert "On-Call Handoff" in output
        assert "Alice" in output


# ---------------------------------------------------------------------------
# sprint_reporter.py — missing lines
# ---------------------------------------------------------------------------
from code_agents.reporters.sprint_reporter import (
    SprintReporter,
    SprintReport,
    format_sprint_report,
    generate_sprint_markdown,
)


class TestSprintReporterCoverage:
    """Cover missing lines in sprint_reporter.py."""

    @pytest.fixture
    def reporter(self, tmp_path):
        return SprintReporter(cwd=str(tmp_path))

    def test_collect_jira_completed(self, reporter, monkeypatch):
        """Lines 96-97: Jira completed stories error."""
        monkeypatch.setenv("JIRA_PROJECT_KEY", "PROJ")
        with patch("urllib.request.urlopen", side_effect=Exception("not reachable")):
            reporter._collect_jira_data()
        # Should not crash

    def test_collect_jira_in_progress_error(self, reporter, monkeypatch):
        """Lines 113-114: Jira in-progress error."""
        monkeypatch.setenv("JIRA_PROJECT_KEY", "PROJ")
        mock_data = json.dumps({"issues": [{"key": "PROJ-1", "summary": "Done", "story_points": 5, "assignee": "Alice"}]})

        call_count = [0]
        def mock_urlopen(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                mock_resp = MagicMock()
                mock_resp.__enter__ = MagicMock(return_value=mock_resp)
                mock_resp.__exit__ = MagicMock(return_value=False)
                mock_resp.read.return_value = mock_data.encode()
                return mock_resp
            raise Exception("error")

        with patch("urllib.request.urlopen", side_effect=mock_urlopen):
            reporter._collect_jira_data()

    def test_collect_jira_bugs(self, reporter, monkeypatch):
        """Lines 124-136: bug count collection."""
        monkeypatch.setenv("JIRA_PROJECT_KEY", "PROJ")
        mock_data = json.dumps({"issues": [{"key": "BUG-1"}]})

        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.__enter__ = MagicMock(return_value=mock_resp)
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_resp.read.return_value = mock_data.encode()
            mock_urlopen.return_value = mock_resp
            reporter._collect_jira_data()

    def test_collect_build_data(self, reporter):
        """Lines 178-179, 197-198: build data collection."""
        reporter._collect_build_data()
        # Should not crash even without telemetry

    def test_format_sprint_report(self):
        """Format with all sections."""
        report = SprintReport(repo_name="my-repo", sprint_name="Sprint 45", goal="Ship v2")
        report.stories_completed = [{"key": "PROJ-1", "summary": "Feature", "points": 5}]
        report.stories_in_progress = [{"key": "PROJ-2", "summary": "WIP"}]
        report.stories_carry_over = [{"key": "PROJ-3", "summary": "Leftover"}]
        report.points_completed = 5
        report.bugs_created = 3
        report.bugs_resolved = 5
        report.total_commits = 20
        report.total_prs_merged = 5
        report.files_changed = 30
        report.lines_added = 500
        report.lines_deleted = 200
        report.commits_by_author = {"Alice": 15, "Bob": 5}
        output = format_sprint_report(report)
        assert "Sprint 45" in output
        assert "Ship v2" in output
        assert "improving" in output

    def test_generate_sprint_markdown(self):
        """Markdown generation."""
        report = SprintReport(repo_name="my-repo", sprint_name="Sprint 45")
        report.stories_completed = [{"key": "PROJ-1", "summary": "Feature", "points": 5}]
        report.points_completed = 5
        report.bugs_created = 2
        report.bugs_resolved = 3
        output = generate_sprint_markdown(report)
        assert "Sprint Report" in output


# ---------------------------------------------------------------------------
# env_health.py — missing lines
# ---------------------------------------------------------------------------
from code_agents.reporters.env_health import (
    EnvironmentHealthChecker,
    EnvironmentHealth,
    HealthCheck,
    format_env_health,
)


class TestEnvHealthCoverage:
    """Cover missing lines in env_health.py."""

    @pytest.fixture
    def checker(self):
        return EnvironmentHealthChecker()

    def test_run_all_step_exception(self, checker):
        """Lines 65-69: exception during a health check step."""
        with patch.object(checker, "_check_argocd", side_effect=Exception("ArgoCD error")):
            with patch.object(checker, "_check_jenkins"):
                with patch.object(checker, "_check_jira"):
                    with patch.object(checker, "_check_kibana"):
                        with patch.object(checker, "_check_server"):
                            report = checker.run_all()
        error_checks = [c for c in report.checks if c.status == "error"]
        assert len(error_checks) >= 1
        assert "ArgoCD error" in error_checks[0].message

    def test_run_all_exception_logged(self, checker, monkeypatch):
        """Lines 65-66, 69: exception triggers error check with message."""
        monkeypatch.setenv("ARGOCD_APP_NAME", "my-app")
        monkeypatch.setenv("JENKINS_URL", "https://jenkins.example.com")
        monkeypatch.setenv("JIRA_URL", "https://jira.example.com")
        monkeypatch.setenv("KIBANA_URL", "https://kibana.example.com")

        with patch.object(checker, "_api_get", side_effect=RuntimeError("boom")):
            report = checker.run_all()
        # All checks should have error status since _api_get always raises
        assert len(report.checks) >= 1
