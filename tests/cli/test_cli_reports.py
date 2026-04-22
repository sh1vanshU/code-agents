"""CLI tests grouped by feature area (split from legacy monolith)."""
from __future__ import annotations

import os
import sys
from unittest.mock import patch, MagicMock

import pytest


class TestCmdStandup:
    """Test standup command."""

    def test_standup_runs(self, capsys):
        from code_agents.cli.cli_reports import cmd_standup
        import subprocess as _sp
        mock_result = MagicMock()
        mock_result.stdout = "abc123 fix: some bug\ndef456 feat: new feature"
        mock_result_status = MagicMock()
        mock_result_status.stdout = ""
        with patch("subprocess.run", return_value=mock_result) as mock_sp, \
             patch.dict(os.environ, {"CODE_AGENTS_USER_CWD": "/tmp/fake"}), \
             patch("httpx.get", side_effect=Exception("no server")):
            cmd_standup()
        output = capsys.readouterr().out
        assert "Standup" in output
        assert "What was done" in output

    def test_standup_no_commits(self, capsys):
        from code_agents.cli.cli_reports import cmd_standup
        mock_result = MagicMock()
        mock_result.stdout = ""
        mock_result_status = MagicMock()
        mock_result_status.stdout = ""
        with patch("subprocess.run", return_value=mock_result), \
             patch.dict(os.environ, {"CODE_AGENTS_USER_CWD": "/tmp/fake"}), \
             patch("httpx.get", side_effect=Exception("no server")):
            cmd_standup()
        output = capsys.readouterr().out
        assert "No commits since yesterday" in output
class TestCmdIncident:
    """Test incident command."""

    def test_incident_no_args(self, capsys):
        from code_agents.cli.cli_reports import cmd_incident
        with patch("code_agents.cli.cli_reports._load_env"), \
             patch("code_agents.cli.cli_reports._user_cwd", return_value="/tmp/fake"), \
             patch("sys.argv", ["code-agents", "incident"]):
            cmd_incident(None)
        output = capsys.readouterr().out
        assert "Usage" in output

    def test_incident_no_service(self, capsys):
        from code_agents.cli.cli_reports import cmd_incident
        with patch("code_agents.cli.cli_reports._load_env"), \
             patch("code_agents.cli.cli_reports._user_cwd", return_value="/tmp/fake"):
            cmd_incident(["--rca"])
        output = capsys.readouterr().out
        assert "Usage" in output

    def test_incident_basic(self, capsys):
        from code_agents.cli.cli_reports import cmd_incident
        mock_report = MagicMock()
        with patch("code_agents.cli.cli_reports._load_env"), \
             patch("code_agents.cli.cli_reports._user_cwd", return_value="/tmp/fake"), \
             patch("code_agents.reporters.incident.IncidentRunner") as MockRunner, \
             patch("code_agents.reporters.incident.format_incident_report", return_value="Incident Report"):
            MockRunner.return_value.run_all.return_value = mock_report
            cmd_incident(["my-service"])
        output = capsys.readouterr().out
        assert "Investigating: my-service" in output
        assert "Incident Report" in output

    def test_incident_with_rca(self, capsys, tmp_path):
        from code_agents.cli.cli_reports import cmd_incident
        mock_report = MagicMock()
        with patch("code_agents.cli.cli_reports._load_env"), \
             patch("code_agents.cli.cli_reports._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.reporters.incident.IncidentRunner") as MockRunner, \
             patch("code_agents.reporters.incident.format_incident_report", return_value="Report"), \
             patch("code_agents.reporters.incident.generate_rca_template", return_value="# RCA"):
            MockRunner.return_value.run_all.return_value = mock_report
            cmd_incident(["my-service", "--rca"])
        output = capsys.readouterr().out
        assert "RCA template saved" in output

    def test_incident_with_save(self, capsys, tmp_path):
        from code_agents.cli.cli_reports import cmd_incident
        mock_report = MagicMock()
        with patch("code_agents.cli.cli_reports._load_env"), \
             patch("code_agents.cli.cli_reports._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.reporters.incident.IncidentRunner") as MockRunner, \
             patch("code_agents.reporters.incident.format_incident_report", return_value="Report"):
            MockRunner.return_value.run_all.return_value = mock_report
            cmd_incident(["my-service", "--save"])
        output = capsys.readouterr().out
        assert "Report saved" in output
class TestCmdOncallReport:
    """Test oncall-report command."""

    def test_oncall_report_default(self, capsys):
        from code_agents.cli.cli_reports import cmd_oncall_report
        mock_report = MagicMock()
        mock_report.period_start = "2026-03-26"
        mock_report.period_end = "2026-04-02"
        with patch("code_agents.cli.cli_reports._load_env"), \
             patch("code_agents.cli.cli_reports._user_cwd", return_value="/tmp/fake"), \
             patch("code_agents.reporters.oncall.OncallReporter") as MockReporter, \
             patch("code_agents.reporters.oncall.format_oncall_report", return_value="Oncall Report"):
            MockReporter.return_value.generate.return_value = mock_report
            cmd_oncall_report([])
        output = capsys.readouterr().out
        assert "On-Call Handoff Report" in output
        assert "7 days" in output

    def test_oncall_report_custom_days(self, capsys):
        from code_agents.cli.cli_reports import cmd_oncall_report
        mock_report = MagicMock()
        mock_report.period_start = "2026-03-19"
        mock_report.period_end = "2026-04-02"
        with patch("code_agents.cli.cli_reports._load_env"), \
             patch("code_agents.cli.cli_reports._user_cwd", return_value="/tmp/fake"), \
             patch("code_agents.reporters.oncall.OncallReporter") as MockReporter, \
             patch("code_agents.reporters.oncall.format_oncall_report", return_value="Report"):
            MockReporter.return_value.generate.return_value = mock_report
            cmd_oncall_report(["--days", "14"])
        output = capsys.readouterr().out
        assert "14 days" in output

    def test_oncall_report_invalid_days(self, capsys):
        from code_agents.cli.cli_reports import cmd_oncall_report
        with patch("code_agents.cli.cli_reports._load_env"), \
             patch("code_agents.cli.cli_reports._user_cwd", return_value="/tmp/fake"):
            cmd_oncall_report(["--days", "notanumber"])
        output = capsys.readouterr().out
        assert "integer" in output

    def test_oncall_report_save(self, capsys, tmp_path):
        from code_agents.cli.cli_reports import cmd_oncall_report
        mock_report = MagicMock()
        mock_report.period_start = "2026-03-26"
        mock_report.period_end = "2026-04-02"
        with patch("code_agents.cli.cli_reports._load_env"), \
             patch("code_agents.cli.cli_reports._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.reporters.oncall.OncallReporter") as MockReporter, \
             patch("code_agents.reporters.oncall.format_oncall_report", return_value="Report"), \
             patch("code_agents.reporters.oncall.generate_oncall_markdown", return_value="# Oncall MD"):
            MockReporter.return_value.generate.return_value = mock_report
            cmd_oncall_report(["--save"])
        output = capsys.readouterr().out
        assert "Saved" in output

    def test_oncall_report_slack(self, capsys):
        from code_agents.cli.cli_reports import cmd_oncall_report
        mock_report = MagicMock()
        mock_report.period_start = "2026-03-26"
        mock_report.period_end = "2026-04-02"
        with patch("code_agents.cli.cli_reports._load_env"), \
             patch("code_agents.cli.cli_reports._user_cwd", return_value="/tmp/fake"), \
             patch("code_agents.reporters.oncall.OncallReporter") as MockReporter, \
             patch("code_agents.reporters.oncall.format_oncall_report", return_value="Report"), \
             patch("code_agents.reporters.oncall.generate_oncall_markdown", return_value="# MD"):
            MockReporter.return_value.generate.return_value = mock_report
            cmd_oncall_report(["--slack"])
        output = capsys.readouterr().out
        assert "Markdown" in output
class TestCmdSprintReport:
    """Test sprint-report command."""

    def test_sprint_report_default(self, capsys):
        from code_agents.cli.cli_reports import cmd_sprint_report
        mock_report = MagicMock()
        with patch("code_agents.cli.cli_reports._load_env"), \
             patch("code_agents.cli.cli_reports._user_cwd", return_value="/tmp/fake"), \
             patch("code_agents.reporters.sprint_reporter.SprintReporter") as MockReporter, \
             patch("code_agents.reporters.sprint_reporter.format_sprint_report", return_value="Sprint Report"):
            MockReporter.return_value.generate.return_value = mock_report
            cmd_sprint_report([])
        output = capsys.readouterr().out
        assert "Sprint Report" in output
        assert "14 days" in output

    def test_sprint_report_custom_days(self, capsys):
        from code_agents.cli.cli_reports import cmd_sprint_report
        mock_report = MagicMock()
        with patch("code_agents.cli.cli_reports._load_env"), \
             patch("code_agents.cli.cli_reports._user_cwd", return_value="/tmp/fake"), \
             patch("code_agents.reporters.sprint_reporter.SprintReporter") as MockReporter, \
             patch("code_agents.reporters.sprint_reporter.format_sprint_report", return_value="Report"):
            MockReporter.return_value.generate.return_value = mock_report
            cmd_sprint_report(["--days", "21"])
        output = capsys.readouterr().out
        assert "21 days" in output

    def test_sprint_report_invalid_days(self, capsys):
        from code_agents.cli.cli_reports import cmd_sprint_report
        with patch("code_agents.cli.cli_reports._load_env"), \
             patch("code_agents.cli.cli_reports._user_cwd", return_value="/tmp/fake"):
            cmd_sprint_report(["--days", "abc"])
        output = capsys.readouterr().out
        assert "integer" in output

    def test_sprint_report_save(self, capsys, tmp_path):
        from code_agents.cli.cli_reports import cmd_sprint_report
        mock_report = MagicMock()
        with patch("code_agents.cli.cli_reports._load_env"), \
             patch("code_agents.cli.cli_reports._user_cwd", return_value=str(tmp_path)), \
             patch("code_agents.reporters.sprint_reporter.SprintReporter") as MockReporter, \
             patch("code_agents.reporters.sprint_reporter.format_sprint_report", return_value="R"), \
             patch("code_agents.reporters.sprint_reporter.generate_sprint_markdown", return_value="# MD"):
            MockReporter.return_value.generate.return_value = mock_report
            cmd_sprint_report(["--save"])
        output = capsys.readouterr().out
        assert "Saved" in output

    def test_sprint_report_slack(self, capsys):
        from code_agents.cli.cli_reports import cmd_sprint_report
        mock_report = MagicMock()
        with patch("code_agents.cli.cli_reports._load_env"), \
             patch("code_agents.cli.cli_reports._user_cwd", return_value="/tmp/fake"), \
             patch("code_agents.reporters.sprint_reporter.SprintReporter") as MockReporter, \
             patch("code_agents.reporters.sprint_reporter.format_sprint_report", return_value="R"), \
             patch("code_agents.reporters.sprint_reporter.generate_sprint_markdown", return_value="# Sprint MD"):
            MockReporter.return_value.generate.return_value = mock_report
            cmd_sprint_report(["--slack"])
        output = capsys.readouterr().out
        assert "Markdown" in output
class TestCmdSprintVelocity:
    """Test sprint-velocity command."""

    def test_sprint_velocity_default(self, capsys):
        from code_agents.cli.cli_reports import cmd_sprint_velocity
        mock_report = MagicMock()
        mock_report.sprints = []
        with patch("code_agents.cli.cli_reports._load_env"), \
             patch("code_agents.cli.cli_reports._user_cwd", return_value="/tmp/fake"), \
             patch("code_agents.reporters.sprint_velocity.SprintVelocityTracker") as MockTracker, \
             patch("code_agents.reporters.sprint_velocity.format_report", return_value="Velocity Report"):
            MockTracker.return_value.calculate_velocity.return_value = mock_report
            cmd_sprint_velocity([])
        output = capsys.readouterr().out
        assert "Sprint Velocity Tracker" in output
        assert "5 sprints" in output

    def test_sprint_velocity_custom_sprints(self, capsys):
        from code_agents.cli.cli_reports import cmd_sprint_velocity
        mock_report = MagicMock()
        mock_report.sprints = []
        with patch("code_agents.cli.cli_reports._load_env"), \
             patch("code_agents.cli.cli_reports._user_cwd", return_value="/tmp/fake"), \
             patch("code_agents.reporters.sprint_velocity.SprintVelocityTracker") as MockTracker, \
             patch("code_agents.reporters.sprint_velocity.format_report", return_value="Report"):
            MockTracker.return_value.calculate_velocity.return_value = mock_report
            cmd_sprint_velocity(["--sprints", "10"])
        output = capsys.readouterr().out
        assert "10 sprints" in output

    def test_sprint_velocity_invalid_sprints(self, capsys):
        from code_agents.cli.cli_reports import cmd_sprint_velocity
        with patch("code_agents.cli.cli_reports._load_env"), \
             patch("code_agents.cli.cli_reports._user_cwd", return_value="/tmp/fake"):
            cmd_sprint_velocity(["--sprints", "abc"])
        output = capsys.readouterr().out
        assert "integer" in output

    def test_sprint_velocity_json(self, capsys):
        from code_agents.cli.cli_reports import cmd_sprint_velocity
        mock_report = MagicMock()
        mock_report.project_key = "PROJ"
        mock_report.repo_name = "my-repo"
        mock_report.source = "jira"
        mock_report.avg_velocity = 25.5
        mock_report.trend = "up"
        mock_report.total_bugs_created = 5
        mock_report.total_bugs_resolved = 3
        mock_report.sprints = []
        mock_report.total_carry_overs = 2
        with patch("code_agents.cli.cli_reports._load_env"), \
             patch("code_agents.cli.cli_reports._user_cwd", return_value="/tmp/fake"), \
             patch("code_agents.reporters.sprint_velocity.SprintVelocityTracker") as MockTracker:
            MockTracker.return_value.calculate_velocity.return_value = mock_report
            cmd_sprint_velocity(["--json"])
        output = capsys.readouterr().out
        assert '"project_key"' in output
        assert '"PROJ"' in output
class TestCmdEnvHealth:
    """Test env-health command."""

    def test_env_health(self, capsys):
        from code_agents.cli.cli_reports import cmd_env_health
        mock_report = MagicMock()
        with patch("code_agents.cli.cli_reports._load_env"), \
             patch("code_agents.reporters.env_health.EnvironmentHealthChecker") as MockChecker, \
             patch("code_agents.reporters.env_health.format_env_health", return_value="Health Report"):
            MockChecker.return_value.run_all.return_value = mock_report
            cmd_env_health([])
        output = capsys.readouterr().out
        assert "Environment Health Check" in output
        assert "Health Report" in output
class TestCmdMorning:
    """Test morning command."""

    def test_morning(self, capsys):
        from code_agents.cli.cli_reports import cmd_morning
        mock_report = MagicMock()
        with patch("code_agents.cli.cli_reports._load_env"), \
             patch.dict(os.environ, {"CODE_AGENTS_USER_CWD": "/tmp/fake"}), \
             patch("code_agents.reporters.morning.MorningAutopilot") as MockPilot, \
             patch("code_agents.reporters.morning.format_morning_report", return_value="Morning Report"):
            MockPilot.return_value.run_all.return_value = mock_report
            cmd_morning([])
        output = capsys.readouterr().out
        assert "Morning Autopilot" in output
        assert "Morning Report" in output
class TestCmdPerfBaseline:
    """Test perf-baseline command."""

    def test_perf_baseline_show_no_data(self, capsys):
        from code_agents.cli.cli_reports import cmd_perf_baseline
        with patch("code_agents.cli.cli_reports._load_env"), \
             patch("code_agents.observability.performance.BASELINE_PATH") as mock_path:
            mock_path.exists.return_value = False
            cmd_perf_baseline(["--show"])
        output = capsys.readouterr().out
        assert "No baseline saved" in output

    def test_perf_baseline_show_with_data(self, capsys, tmp_path):
        from code_agents.cli.cli_reports import cmd_perf_baseline
        import json
        baseline_file = tmp_path / "baseline.json"
        baseline_file.write_text(json.dumps({
            "updated": "2026-04-01",
            "baselines": [{"url": "/health", "method": "GET", "p50": 10.0, "p95": 20.0, "p99": 30.0, "avg": 15.0, "recorded_at": "2026-04-01"}]
        }))
        with patch("code_agents.cli.cli_reports._load_env"), \
             patch("code_agents.observability.performance.BASELINE_PATH", baseline_file):
            cmd_perf_baseline(["--show"])
        output = capsys.readouterr().out
        assert "/health" in output

    def test_perf_baseline_clear(self, capsys, tmp_path):
        from code_agents.cli.cli_reports import cmd_perf_baseline
        baseline_file = tmp_path / "baseline.json"
        baseline_file.write_text("{}")
        with patch("code_agents.cli.cli_reports._load_env"), \
             patch("code_agents.observability.performance.BASELINE_PATH", baseline_file):
            cmd_perf_baseline(["--clear"])
        output = capsys.readouterr().out
        assert "Baseline cleared" in output
        assert not baseline_file.exists()

    def test_perf_baseline_clear_nothing(self, capsys):
        from code_agents.cli.cli_reports import cmd_perf_baseline
        with patch("code_agents.cli.cli_reports._load_env"), \
             patch("code_agents.observability.performance.BASELINE_PATH") as mock_path:
            mock_path.exists.return_value = False
            cmd_perf_baseline(["--clear"])
        output = capsys.readouterr().out
        assert "No baseline to clear" in output

    def test_perf_baseline_no_endpoints(self, capsys):
        from code_agents.cli.cli_reports import cmd_perf_baseline
        with patch("code_agents.cli.cli_reports._load_env"), \
             patch("code_agents.cli.cli_reports._user_cwd", return_value="/tmp/fake"), \
             patch("code_agents.observability.performance.PerformanceProfiler") as MockProfiler:
            MockProfiler.return_value.discover_endpoints.return_value = []
            cmd_perf_baseline([])
        output = capsys.readouterr().out
        assert "No endpoints discovered" in output

    def test_perf_baseline_profile(self, capsys):
        from code_agents.cli.cli_reports import cmd_perf_baseline
        mock_report = MagicMock()
        mock_report.baseline_comparison = []
        mock_report.results = [{"url": "/health"}]
        with patch("code_agents.cli.cli_reports._load_env"), \
             patch("code_agents.cli.cli_reports._user_cwd", return_value="/tmp/fake"), \
             patch("code_agents.observability.performance.PerformanceProfiler") as MockProfiler, \
             patch("code_agents.observability.performance.format_profile_report", return_value="Profile Report"):
            MockProfiler.return_value.discover_endpoints.return_value = ["/health"]
            MockProfiler.return_value.profile_multiple.return_value = mock_report
            MockProfiler.return_value.save_as_baseline.return_value = 1
            cmd_perf_baseline([])
        output = capsys.readouterr().out
        assert "Profile Report" in output
        assert "Baseline saved" in output

    def test_perf_baseline_compare_no_regressions(self, capsys):
        from code_agents.cli.cli_reports import cmd_perf_baseline
        mock_report = MagicMock()
        mock_report.baseline_comparison = [{"regression": False}]
        mock_report.results = []
        with patch("code_agents.cli.cli_reports._load_env"), \
             patch("code_agents.cli.cli_reports._user_cwd", return_value="/tmp/fake"), \
             patch("code_agents.observability.performance.PerformanceProfiler") as MockProfiler, \
             patch("code_agents.observability.performance.format_profile_report", return_value="Report"):
            MockProfiler.return_value.discover_endpoints.return_value = ["/health"]
            MockProfiler.return_value.profile_multiple.return_value = mock_report
            cmd_perf_baseline(["--compare"])
        output = capsys.readouterr().out
        assert "within baseline thresholds" in output

    def test_perf_baseline_compare_with_regressions(self, capsys):
        from code_agents.cli.cli_reports import cmd_perf_baseline
        mock_report = MagicMock()
        mock_report.baseline_comparison = [{"regression": True}]
        mock_report.results = []
        with patch("code_agents.cli.cli_reports._load_env"), \
             patch("code_agents.cli.cli_reports._user_cwd", return_value="/tmp/fake"), \
             patch("code_agents.observability.performance.PerformanceProfiler") as MockProfiler, \
             patch("code_agents.observability.performance.format_profile_report", return_value="Report"):
            MockProfiler.return_value.discover_endpoints.return_value = ["/health"]
            MockProfiler.return_value.profile_multiple.return_value = mock_report
            cmd_perf_baseline(["--compare"])
        output = capsys.readouterr().out
        assert "regression" in output
class TestCmdIncidentAnalyze:
    """Test incident with --analyze flag."""

    def test_incident_analyze(self, capsys):
        from code_agents.cli.cli_reports import cmd_incident
        mock_report = MagicMock()
        with patch("code_agents.cli.cli_reports._load_env"), \
             patch("code_agents.cli.cli_reports._user_cwd", return_value="/tmp"), \
             patch("code_agents.reporters.incident.IncidentRunner") as MockRunner, \
             patch("code_agents.reporters.incident.format_incident_report", return_value="Report"), \
             patch("code_agents.reporters.incident.build_rca_agent_prompt", return_value="Analyze this incident"):
            MockRunner.return_value.run_all.return_value = mock_report
            cmd_incident(["my-service", "--analyze"])
        output = capsys.readouterr().out
        assert "AI RCA Analysis Prompt" in output
class TestCmdPerfBaselineIterations:
    """Test perf-baseline with --iterations flag."""

    def test_perf_baseline_custom_iterations(self, capsys):
        from code_agents.cli.cli_reports import cmd_perf_baseline
        mock_report = MagicMock()
        mock_report.baseline_comparison = []
        mock_report.results = [{"url": "/health"}]
        with patch("code_agents.cli.cli_reports._load_env"), \
             patch("code_agents.cli.cli_reports._user_cwd", return_value="/tmp"), \
             patch("code_agents.observability.performance.PerformanceProfiler") as MockProfiler, \
             patch("code_agents.observability.performance.format_profile_report", return_value="Report"):
            MockProfiler.return_value.discover_endpoints.return_value = ["/health"]
            MockProfiler.return_value.profile_multiple.return_value = mock_report
            MockProfiler.return_value.save_as_baseline.return_value = 1
            cmd_perf_baseline(["--iterations", "50"])
        output = capsys.readouterr().out
        assert "50 iterations" in output

    def test_perf_baseline_compare_no_baseline(self, capsys):
        from code_agents.cli.cli_reports import cmd_perf_baseline
        mock_report = MagicMock()
        mock_report.baseline_comparison = []
        mock_report.results = []
        with patch("code_agents.cli.cli_reports._load_env"), \
             patch("code_agents.cli.cli_reports._user_cwd", return_value="/tmp"), \
             patch("code_agents.observability.performance.PerformanceProfiler") as MockProfiler, \
             patch("code_agents.observability.performance.format_profile_report", return_value="Report"):
            MockProfiler.return_value.discover_endpoints.return_value = ["/health"]
            MockProfiler.return_value.profile_multiple.return_value = mock_report
            cmd_perf_baseline(["--compare"])
        output = capsys.readouterr().out
        assert "No baseline" in output
