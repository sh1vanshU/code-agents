"""Tests for morning.py — morning autopilot."""

import os
from unittest.mock import patch, MagicMock

import pytest

from code_agents.reporters.morning import (
    MorningAutopilot, MorningReport, MorningStep, format_morning_report,
)


@pytest.fixture
def mock_cwd(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname = 'demo'\n")
    return str(tmp_path)


class TestMorningAutopilot:
    """Tests for MorningAutopilot."""

    def test_init(self, mock_cwd):
        pilot = MorningAutopilot(cwd=mock_cwd)
        assert pilot.cwd == mock_cwd
        assert pilot.report.timestamp != ""

    @patch("subprocess.run")
    def test_git_pull_success(self, mock_run, mock_cwd):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="Already up to date.\n", stderr="",
        )
        pilot = MorningAutopilot(cwd=mock_cwd)
        pilot._git_pull()
        step = pilot.report.steps[0]
        assert step.name == "Git Pull"
        assert step.status == "ok"

    @patch("subprocess.run")
    def test_git_pull_failure(self, mock_run, mock_cwd):
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="error: merge conflict\n",
        )
        pilot = MorningAutopilot(cwd=mock_cwd)
        pilot._git_pull()
        step = pilot.report.steps[0]
        assert step.status == "warning"

    @patch.dict("os.environ", {"JENKINS_URL": ""}, clear=False)
    def test_build_status_skipped(self, mock_cwd):
        pilot = MorningAutopilot(cwd=mock_cwd)
        pilot._build_status()
        step = pilot.report.steps[0]
        assert step.status == "skipped"

    @patch.dict("os.environ", {"JIRA_URL": ""}, clear=False)
    def test_jira_board_skipped(self, mock_cwd):
        pilot = MorningAutopilot(cwd=mock_cwd)
        pilot._jira_board()
        step = pilot.report.steps[0]
        assert step.status == "skipped"

    @patch.dict("os.environ", {"KIBANA_URL": ""}, clear=False)
    def test_kibana_alerts_skipped(self, mock_cwd):
        pilot = MorningAutopilot(cwd=mock_cwd)
        pilot._kibana_alerts()
        step = pilot.report.steps[0]
        assert step.status == "skipped"

    @patch("subprocess.run")
    def test_standup_summary(self, mock_run, mock_cwd):
        mock_run.return_value = MagicMock(
            returncode=0, stdout="abc123 feat: add login\ndef456 fix: crash\n",
        )
        pilot = MorningAutopilot(cwd=mock_cwd)
        pilot._standup_summary()
        step = pilot.report.steps[0]
        assert step.status == "ok"
        assert "2 commits" in step.output

    def test_morning_report_summary(self):
        report = MorningReport(steps=[
            MorningStep(name="A", status="ok"),
            MorningStep(name="B", status="warning"),
            MorningStep(name="C", status="error"),
            MorningStep(name="D", status="skipped"),
        ])
        assert "1 ok" in report.summary
        assert "1 warnings" in report.summary
        assert "1 errors" in report.summary


class TestFormatMorningReport:
    """Tests for format_morning_report."""

    def test_format_with_steps(self):
        report = MorningReport(
            timestamp="2026-04-01T08:00:00",
            steps=[
                MorningStep(name="Git Pull", status="ok", output="Up to date"),
                MorningStep(name="Build", status="skipped", output="Not configured"),
            ],
        )
        output = format_morning_report(report)
        assert "Morning Autopilot" in output
        assert "[OK]" in output
        assert "[--]" in output

    def test_format_empty(self):
        report = MorningReport()
        output = format_morning_report(report)
        assert "Morning Autopilot" in output


# ── _api_get (lines 74-81) ────────────────────────────────────────────────


class TestApiGet:
    """Test _api_get helper."""

    @patch("urllib.request.urlopen")
    def test_api_get_success(self, mock_urlopen, mock_cwd):
        import json as _json
        mock_resp = MagicMock()
        mock_resp.read.return_value = _json.dumps({"ok": True}).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        pilot = MorningAutopilot(cwd=mock_cwd)
        result = pilot._api_get("/health")
        assert result == {"ok": True}

    @patch("urllib.request.urlopen", side_effect=Exception("connection refused"))
    def test_api_get_failure(self, mock_urlopen, mock_cwd):
        pilot = MorningAutopilot(cwd=mock_cwd)
        result = pilot._api_get("/health")
        assert result is None


# ── _git_pull timeout (line 99-100) ───────────────────────────────────────


class TestGitPullTimeout:
    @patch("subprocess.run", side_effect=__import__("subprocess").TimeoutExpired(cmd="git", timeout=30))
    def test_git_pull_timeout(self, mock_run, mock_cwd):
        pilot = MorningAutopilot(cwd=mock_cwd)
        pilot._git_pull()
        step = pilot.report.steps[0]
        assert step.status == "error"
        assert "Timeout" in step.output


# ── _build_status with Jenkins configured (lines 112-125) ─────────────────


class TestBuildStatus:
    @patch.dict("os.environ", {"JENKINS_URL": "http://jenkins:8080"})
    def test_build_status_success(self, mock_cwd):
        pilot = MorningAutopilot(cwd=mock_cwd)
        with patch.object(pilot, "_api_get", return_value={"result": "SUCCESS", "number": 42}):
            pilot._build_status()
        step = pilot.report.steps[0]
        assert step.status == "ok"
        assert "#42" in step.output

    @patch.dict("os.environ", {"JENKINS_URL": "http://jenkins:8080"})
    def test_build_status_warning(self, mock_cwd):
        pilot = MorningAutopilot(cwd=mock_cwd)
        with patch.object(pilot, "_api_get", return_value={"result": "FAILURE", "number": 43}):
            pilot._build_status()
        step = pilot.report.steps[0]
        assert step.status == "warning"

    @patch.dict("os.environ", {"JENKINS_URL": "http://jenkins:8080"})
    def test_build_status_unreachable(self, mock_cwd):
        pilot = MorningAutopilot(cwd=mock_cwd)
        with patch.object(pilot, "_api_get", return_value=None):
            pilot._build_status()
        step = pilot.report.steps[0]
        assert step.status == "error"
        assert "not reachable" in step.output


# ── _jira_board (lines 127-156) ──────────────────────────────────────────


class TestJiraBoard:
    @patch.dict("os.environ", {"JIRA_URL": "http://jira:8080"})
    def test_jira_board_with_issues(self, mock_cwd):
        pilot = MorningAutopilot(cwd=mock_cwd)
        data = {
            "issues": [
                {"key": "PROJ-1", "fields": {"summary": "Implement login"}},
                {"key": "PROJ-2", "fields": {"summary": "Fix bug"}},
            ]
        }
        with patch.object(pilot, "_api_get", return_value=data):
            pilot._jira_board()
        step = pilot.report.steps[0]
        assert step.status == "ok"
        assert "2 in progress" in step.output

    @patch.dict("os.environ", {"JIRA_URL": "http://jira:8080"})
    def test_jira_board_no_issues(self, mock_cwd):
        pilot = MorningAutopilot(cwd=mock_cwd)
        with patch.object(pilot, "_api_get", return_value={"issues": []}):
            pilot._jira_board()
        step = pilot.report.steps[0]
        assert step.status == "ok"
        assert "No tickets" in step.output

    @patch.dict("os.environ", {"JIRA_URL": "http://jira:8080"})
    def test_jira_board_unreachable(self, mock_cwd):
        pilot = MorningAutopilot(cwd=mock_cwd)
        with patch.object(pilot, "_api_get", return_value=None):
            pilot._jira_board()
        step = pilot.report.steps[0]
        assert step.status == "error"


# ── _run_tests (lines 161-197) ────────────────────────────────────────────


class TestMorningRunTests:
    def test_run_tests_no_command(self, tmp_path):
        """No project file => skipped."""
        pilot = MorningAutopilot(cwd=str(tmp_path))
        with patch.dict(os.environ, {"CODE_AGENTS_TEST_CMD": ""}, clear=False):
            pilot._run_tests()
        step = pilot.report.steps[0]
        assert step.status == "skipped"

    @patch("subprocess.run")
    def test_run_tests_success(self, mock_run, mock_cwd):
        pilot = MorningAutopilot(cwd=mock_cwd)
        mock_run.return_value = MagicMock(returncode=0, stdout="3 passed\n")
        with patch.dict(os.environ, {"CODE_AGENTS_TEST_CMD": ""}, clear=False):
            pilot._run_tests()
        step = pilot.report.steps[0]
        assert step.status == "ok"

    @patch("subprocess.run")
    def test_run_tests_failure(self, mock_run, mock_cwd):
        pilot = MorningAutopilot(cwd=mock_cwd)
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="FAILED\n")
        with patch.dict(os.environ, {"CODE_AGENTS_TEST_CMD": ""}, clear=False):
            pilot._run_tests()
        step = pilot.report.steps[0]
        assert step.status == "error"

    @patch("subprocess.run", side_effect=__import__("subprocess").TimeoutExpired(cmd="test", timeout=120))
    def test_run_tests_timeout(self, mock_run, mock_cwd):
        pilot = MorningAutopilot(cwd=mock_cwd)
        with patch.dict(os.environ, {"CODE_AGENTS_TEST_CMD": ""}, clear=False):
            pilot._run_tests()
        step = pilot.report.steps[0]
        assert step.status == "warning"
        assert "timed out" in step.output


# ── _kibana_alerts (lines 207-220) ────────────────────────────────────────


class TestKibanaAlerts:
    @patch.dict("os.environ", {"KIBANA_URL": "http://kibana:5601"})
    def test_kibana_low_error_rate(self, mock_cwd):
        pilot = MorningAutopilot(cwd=mock_cwd)
        with patch.object(pilot, "_api_get", return_value={"error_rate": 0.5, "error_count": 3}):
            pilot._kibana_alerts()
        step = pilot.report.steps[0]
        assert step.status == "ok"

    @patch.dict("os.environ", {"KIBANA_URL": "http://kibana:5601"})
    def test_kibana_medium_error_rate(self, mock_cwd):
        pilot = MorningAutopilot(cwd=mock_cwd)
        with patch.object(pilot, "_api_get", return_value={"error_rate": 3.0, "error_count": 30}):
            pilot._kibana_alerts()
        step = pilot.report.steps[0]
        assert step.status == "warning"

    @patch.dict("os.environ", {"KIBANA_URL": "http://kibana:5601"})
    def test_kibana_high_error_rate(self, mock_cwd):
        pilot = MorningAutopilot(cwd=mock_cwd)
        with patch.object(pilot, "_api_get", return_value={"error_rate": 8.0, "error_count": 100}):
            pilot._kibana_alerts()
        step = pilot.report.steps[0]
        assert step.status == "error"

    @patch.dict("os.environ", {"KIBANA_URL": "http://kibana:5601"})
    def test_kibana_unreachable(self, mock_cwd):
        pilot = MorningAutopilot(cwd=mock_cwd)
        with patch.object(pilot, "_api_get", return_value=None):
            pilot._kibana_alerts()
        step = pilot.report.steps[0]
        assert step.status == "error"


# ── _standup_summary edge cases (lines 222-245) ──────────────────────────


class TestStandupEdgeCases:
    @patch("subprocess.run")
    def test_standup_no_commits(self, mock_run, mock_cwd):
        mock_run.return_value = MagicMock(returncode=0, stdout="")
        pilot = MorningAutopilot(cwd=mock_cwd)
        pilot._standup_summary()
        step = pilot.report.steps[0]
        assert step.status == "ok"
        assert "No commits" in step.output

    @patch("subprocess.run", side_effect=FileNotFoundError("git not found"))
    def test_standup_git_not_available(self, mock_run, mock_cwd):
        pilot = MorningAutopilot(cwd=mock_cwd)
        pilot._standup_summary()
        step = pilot.report.steps[0]
        assert step.status == "error"
        assert "Git not available" in step.output


# ── run_all with exception in step (lines 56-72) ─────────────────────────


class TestRunAllErrorHandling:
    def test_run_all_catches_exceptions(self, mock_cwd):
        pilot = MorningAutopilot(cwd=mock_cwd)
        with patch.object(pilot, "_git_pull", side_effect=RuntimeError("boom")), \
             patch.object(pilot, "_build_status"), \
             patch.object(pilot, "_jira_board"), \
             patch.object(pilot, "_run_tests"), \
             patch.object(pilot, "_kibana_alerts"), \
             patch.object(pilot, "_standup_summary"):
            report = pilot.run_all()
        error_steps = [s for s in report.steps if s.status == "error"]
        assert len(error_steps) >= 1
        assert "boom" in error_steps[0].output
