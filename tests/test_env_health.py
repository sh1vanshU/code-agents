"""Tests for env_health.py — environment health checker."""

import json
from unittest.mock import patch, MagicMock

import pytest

from code_agents.reporters.env_health import (
    EnvironmentHealthChecker, EnvironmentHealth, HealthCheck,
    format_env_health,
)


class TestEnvironmentHealthChecker:
    """Tests for EnvironmentHealthChecker."""

    def test_init(self):
        checker = EnvironmentHealthChecker()
        assert checker.server_url is not None

    @patch.dict("os.environ", {"ARGOCD_APP_NAME": "", "JENKINS_URL": "", "JIRA_URL": "", "KIBANA_URL": ""}, clear=False)
    def test_run_all_unconfigured(self):
        """When nothing is configured, checks return unknown/error."""
        checker = EnvironmentHealthChecker()
        report = checker.run_all()
        assert len(report.checks) >= 1

    def test_health_check_dataclass(self):
        hc = HealthCheck(name="Test", status="ok", message="All good")
        assert hc.name == "Test"
        assert hc.status == "ok"

    def test_overall_ok(self):
        report = EnvironmentHealth(checks=[
            HealthCheck(name="A", status="ok"),
            HealthCheck(name="B", status="ok"),
        ])
        assert report.overall == "ok"

    def test_overall_warning(self):
        report = EnvironmentHealth(checks=[
            HealthCheck(name="A", status="ok"),
            HealthCheck(name="B", status="warning"),
        ])
        assert report.overall == "warning"

    def test_overall_error(self):
        report = EnvironmentHealth(checks=[
            HealthCheck(name="A", status="ok"),
            HealthCheck(name="B", status="error"),
        ])
        assert report.overall == "error"

    def test_overall_empty(self):
        report = EnvironmentHealth(checks=[])
        assert report.overall == "unknown"

    @patch.dict("os.environ", {"ARGOCD_APP_NAME": ""}, clear=False)
    def test_check_argocd_not_configured(self):
        checker = EnvironmentHealthChecker()
        checker._check_argocd()
        argocd = [c for c in checker.report.checks if "ArgoCD" in c.name]
        assert len(argocd) == 1
        assert argocd[0].status == "unknown"

    @patch.dict("os.environ", {"JENKINS_URL": ""}, clear=False)
    def test_check_jenkins_not_configured(self):
        checker = EnvironmentHealthChecker()
        checker._check_jenkins()
        jenkins = [c for c in checker.report.checks if "Jenkins" in c.name]
        assert len(jenkins) == 1
        assert jenkins[0].status == "unknown"

    @patch.dict("os.environ", {"JIRA_URL": ""}, clear=False)
    def test_check_jira_not_configured(self):
        checker = EnvironmentHealthChecker()
        checker._check_jira()
        jira = [c for c in checker.report.checks if "Jira" in c.name]
        assert len(jira) == 1
        assert jira[0].status == "unknown"

    @patch.dict("os.environ", {"KIBANA_URL": ""}, clear=False)
    def test_check_kibana_not_configured(self):
        checker = EnvironmentHealthChecker()
        checker._check_kibana()
        kibana = [c for c in checker.report.checks if "Kibana" in c.name]
        assert len(kibana) == 1
        assert kibana[0].status == "unknown"


class TestFormatEnvHealth:
    """Tests for format_env_health."""

    def test_format_with_checks(self):
        report = EnvironmentHealth(checks=[
            HealthCheck(name="Server", status="ok", message="Running"),
            HealthCheck(name="Jenkins", status="warning", message="Unstable"),
        ])
        output = format_env_health(report)
        assert "Environment Health Dashboard" in output
        assert "[OK]" in output
        assert "[!!]" in output

    def test_format_empty(self):
        report = EnvironmentHealth()
        output = format_env_health(report)
        assert "Environment Health Dashboard" in output
