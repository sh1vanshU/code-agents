"""Tests for incident.py — incident investigation and RCA generation."""

from __future__ import annotations

import json
import os
from unittest.mock import patch, MagicMock

import pytest

from code_agents.reporters.incident import (
    IncidentReport,
    IncidentRunner,
    format_incident_report,
    generate_rca_template,
    build_rca_agent_prompt,
)


# ======================================================================
# IncidentReport dataclass
# ======================================================================


class TestIncidentReport:
    """Test IncidentReport dataclass creation and defaults."""

    def test_default_fields(self):
        report = IncidentReport(service="my-svc", timestamp="2026-04-01T10:00:00")
        assert report.service == "my-svc"
        assert report.timestamp == "2026-04-01T10:00:00"
        assert report.pod_status == []
        assert report.recent_logs == []
        assert report.recent_deploys == []
        assert report.kibana_errors == []
        assert report.git_changes == []
        assert report.health_check == {}
        assert report.suggested_actions == []
        assert report.severity == "unknown"

    def test_custom_severity(self):
        report = IncidentReport(service="svc", timestamp="t", severity="P1")
        assert report.severity == "P1"

    def test_mutable_defaults_are_independent(self):
        r1 = IncidentReport(service="a", timestamp="t")
        r2 = IncidentReport(service="b", timestamp="t")
        r1.pod_status.append({"name": "pod-1"})
        assert r2.pod_status == []


# ======================================================================
# IncidentRunner initialization
# ======================================================================


class TestIncidentRunnerInit:
    """Test IncidentRunner initialization."""

    def test_basic_init(self):
        runner = IncidentRunner(service="my-svc", cwd="/tmp")
        assert runner.service == "my-svc"
        assert runner.cwd == "/tmp"
        assert runner.report.service == "my-svc"
        assert runner.report.severity == "unknown"

    def test_server_url_from_env(self):
        with patch.dict(os.environ, {"CODE_AGENTS_PUBLIC_BASE_URL": "http://localhost:9000"}):
            runner = IncidentRunner(service="svc", cwd="/tmp")
            assert runner.server_url == "http://localhost:9000"

    def test_server_url_default(self):
        with patch.dict(os.environ, {}, clear=True):
            runner = IncidentRunner(service="svc", cwd="/tmp")
            assert runner.server_url == "http://127.0.0.1:8000"


# ======================================================================
# analyze() — severity classification
# ======================================================================


class TestAnalyze:
    """Test the analyze step with various scenarios."""

    def test_crash_looping_pods(self):
        runner = IncidentRunner(service="svc", cwd="/tmp")
        runner.report.pod_status = [
            {"name": "pod-1", "status": "CrashLoopBackOff", "restarts": 5},
        ]
        runner.analyze()
        assert runner.report.severity == "P2"
        assert any("restarts" in a for a in runner.report.suggested_actions)

    def test_unhealthy_deploy_sets_p1(self):
        runner = IncidentRunner(service="svc", cwd="/tmp")
        runner.report.recent_deploys = [
            {"app": "svc", "health": "Degraded", "sync_status": "Synced"},
        ]
        runner.analyze()
        assert runner.report.severity == "P1"
        assert any("rollback" in a for a in runner.report.suggested_actions)

    def test_high_error_volume(self):
        runner = IncidentRunner(service="svc", cwd="/tmp")
        runner.report.recent_logs = [f"error-{i}" for i in range(15)]
        runner.analyze()
        assert runner.report.severity == "P2"
        assert any("error volume" in a.lower() for a in runner.report.suggested_actions)

    def test_git_changes_noted(self):
        runner = IncidentRunner(service="svc", cwd="/tmp")
        runner.report.git_changes = ["abc123 fix something"]
        runner.analyze()
        assert any("code changes" in a.lower() for a in runner.report.suggested_actions)

    def test_no_issues_sets_p4(self):
        runner = IncidentRunner(service="svc", cwd="/tmp")
        runner.analyze()
        assert runner.report.severity == "P4"
        assert any("no obvious issues" in a.lower() for a in runner.report.suggested_actions)

    def test_unhealthy_overrides_crash_loop(self):
        """P1 from unhealthy deploy should override P2 from crash loop."""
        runner = IncidentRunner(service="svc", cwd="/tmp")
        runner.report.pod_status = [
            {"name": "pod-1", "status": "CrashLoopBackOff", "restarts": 10},
        ]
        runner.report.recent_deploys = [
            {"app": "svc", "health": "Degraded", "sync_status": "OutOfSync"},
        ]
        runner.analyze()
        assert runner.report.severity == "P1"

    def test_healthy_deploy_not_flagged(self):
        runner = IncidentRunner(service="svc", cwd="/tmp")
        runner.report.recent_deploys = [
            {"app": "svc", "health": "Healthy", "sync_status": "Synced"},
        ]
        runner.analyze()
        # Should not suggest rollback
        assert not any("rollback" in a for a in runner.report.suggested_actions)


# ======================================================================
# format_incident_report
# ======================================================================


class TestFormatReport:
    """Test terminal report formatting."""

    def test_contains_service_name(self):
        report = IncidentReport(service="my-svc", timestamp="2026-04-01T10:00:00")
        output = format_incident_report(report)
        assert "my-svc" in output

    def test_contains_severity(self):
        report = IncidentReport(service="svc", timestamp="t", severity="P1")
        output = format_incident_report(report)
        assert "P1" in output

    def test_pod_status_shown(self):
        report = IncidentReport(
            service="svc", timestamp="t",
            pod_status=[{"name": "pod-1", "status": "Running", "restarts": 0}],
        )
        output = format_incident_report(report)
        assert "pod-1" in output
        assert "[ok]" in output

    def test_unhealthy_pod_icon(self):
        report = IncidentReport(
            service="svc", timestamp="t",
            pod_status=[{"name": "pod-x", "status": "CrashLoopBackOff", "restarts": 5}],
        )
        output = format_incident_report(report)
        assert "[!!]" in output

    def test_error_truncation(self):
        report = IncidentReport(
            service="svc", timestamp="t",
            recent_logs=[f"error-{i}" for i in range(10)],
        )
        output = format_incident_report(report)
        assert "... and 5 more" in output

    def test_suggested_actions_shown(self):
        report = IncidentReport(
            service="svc", timestamp="t",
            suggested_actions=["Do thing A", "Do thing B"],
        )
        output = format_incident_report(report)
        assert "1. Do thing A" in output
        assert "2. Do thing B" in output

    def test_deploy_info_shown(self):
        report = IncidentReport(
            service="svc", timestamp="t",
            recent_deploys=[{"app": "svc", "sync_status": "Synced", "health": "Healthy"}],
        )
        output = format_incident_report(report)
        assert "sync: Synced" in output

    def test_git_changes_shown(self):
        report = IncidentReport(
            service="svc", timestamp="t",
            git_changes=["abc123 fix bug"],
        )
        output = format_incident_report(report)
        assert "abc123 fix bug" in output

    def test_health_check_shown(self):
        report = IncidentReport(
            service="svc", timestamp="t",
            health_check={"endpoint": "http://svc/health", "status": 200, "response_time_ms": 42},
        )
        output = format_incident_report(report)
        assert "http://svc/health" in output
        assert "42ms" in output


# ======================================================================
# generate_rca_template
# ======================================================================


class TestRCATemplate:
    """Test RCA markdown template generation."""

    def test_contains_service(self):
        report = IncidentReport(service="my-svc", timestamp="t", severity="P2")
        rca = generate_rca_template(report)
        assert "my-svc" in rca
        assert "P2" in rca

    def test_contains_timeline_table(self):
        report = IncidentReport(service="svc", timestamp="t")
        rca = generate_rca_template(report)
        assert "## Timeline" in rca
        assert "| Time | Event |" in rca

    def test_contains_action_items(self):
        report = IncidentReport(service="svc", timestamp="t")
        rca = generate_rca_template(report)
        assert "## Action Items" in rca

    def test_pod_data_included(self):
        report = IncidentReport(
            service="svc", timestamp="t",
            pod_status=[{"name": "pod-1", "status": "Running", "restarts": 0}],
        )
        rca = generate_rca_template(report)
        assert "pod-1: Running" in rca

    def test_no_pod_data_message(self):
        report = IncidentReport(service="svc", timestamp="t")
        rca = generate_rca_template(report)
        assert "No pod data available" in rca

    def test_errors_included(self):
        report = IncidentReport(
            service="svc", timestamp="t",
            recent_logs=["NullPointerException at line 42"],
        )
        rca = generate_rca_template(report)
        assert "NullPointerException" in rca

    def test_no_errors_message(self):
        report = IncidentReport(service="svc", timestamp="t")
        rca = generate_rca_template(report)
        assert "No errors captured" in rca


# ======================================================================
# build_rca_agent_prompt
# ======================================================================


class TestBuildRCAAgentPrompt:
    """Test AI-powered RCA prompt generation."""

    def test_contains_service_and_severity(self):
        report = IncidentReport(service="my-svc", timestamp="t", severity="P1")
        prompt = build_rca_agent_prompt(report)
        assert "my-svc" in prompt
        assert "P1" in prompt

    def test_contains_analysis_instructions(self):
        report = IncidentReport(service="svc", timestamp="t")
        prompt = build_rca_agent_prompt(report)
        assert "Root Cause Analysis" in prompt
        assert "Immediate Fix" in prompt
        assert "Action Items" in prompt
        assert "Prevention" in prompt

    def test_includes_pod_status(self):
        report = IncidentReport(
            service="svc", timestamp="t",
            pod_status=[{"name": "pod-1", "status": "Running", "restarts": 0}],
        )
        prompt = build_rca_agent_prompt(report)
        assert "Pod Status" in prompt
        assert "pod-1" in prompt

    def test_includes_error_logs(self):
        report = IncidentReport(
            service="svc", timestamp="t",
            recent_logs=["NullPointerException at line 42"],
        )
        prompt = build_rca_agent_prompt(report)
        assert "Error Logs" in prompt
        assert "NullPointerException" in prompt

    def test_includes_deploys(self):
        report = IncidentReport(
            service="svc", timestamp="t",
            recent_deploys=[{"app": "svc", "health": "Degraded"}],
        )
        prompt = build_rca_agent_prompt(report)
        assert "Deployment Status" in prompt
        assert "Degraded" in prompt

    def test_includes_git_changes(self):
        report = IncidentReport(
            service="svc", timestamp="t",
            git_changes=["abc123 fix something"],
        )
        prompt = build_rca_agent_prompt(report)
        assert "Recent Git Changes" in prompt
        assert "abc123" in prompt

    def test_includes_health_check(self):
        report = IncidentReport(
            service="svc", timestamp="t",
            health_check={"endpoint": "http://svc/health", "status": 200},
        )
        prompt = build_rca_agent_prompt(report)
        assert "Health Check" in prompt
        assert "http://svc/health" in prompt

    def test_empty_report_still_has_instructions(self):
        report = IncidentReport(service="svc", timestamp="t")
        prompt = build_rca_agent_prompt(report)
        assert "Root Cause Analysis" in prompt
        assert "Pod Status" not in prompt
        assert "Error Logs" not in prompt

    def test_truncates_pods_to_10(self):
        pods = [{"name": f"pod-{i}", "status": "Running"} for i in range(15)]
        report = IncidentReport(service="svc", timestamp="t", pod_status=pods)
        prompt = build_rca_agent_prompt(report)
        assert "pod-9" in prompt
        assert "pod-10" not in prompt

    def test_truncates_logs_to_20(self):
        logs = [f"error-{i}" for i in range(25)]
        report = IncidentReport(service="svc", timestamp="t", recent_logs=logs)
        prompt = build_rca_agent_prompt(report)
        assert "error-19" in prompt
        assert "error-20" not in prompt


# ======================================================================
# run_all — integration-style (mocked network)
# ======================================================================


class TestRunAll:
    """Test run_all orchestration with mocked steps."""

    def test_run_all_succeeds_with_failures(self):
        """run_all should complete even if individual steps fail."""
        runner = IncidentRunner(service="svc", cwd="/tmp")
        # All network calls will fail (no server), but run_all should not raise
        report = runner.run_all()
        assert report.service == "svc"
        assert report.severity in ("P4", "unknown")
        # analyze should still run and set P4
        assert report.severity == "P4"

    def test_run_all_returns_report(self):
        runner = IncidentRunner(service="test-svc", cwd="/tmp")
        result = runner.run_all()
        assert isinstance(result, IncidentReport)
        assert result.service == "test-svc"
