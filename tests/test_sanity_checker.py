"""Tests for sanity_checker.py — sanity check rules, execution, and reporting."""

from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_agents.cicd.sanity_checker import (
    SanityRule,
    CheckResult,
    load_rules,
    run_check,
    run_all_checks,
    format_report,
    DEFAULT_RULES,
)


class TestSanityRule:
    """Test SanityRule dataclass defaults."""

    def test_defaults(self):
        rule = SanityRule(name="test", query="error")
        assert rule.name == "test"
        assert rule.query == "error"
        assert rule.threshold == 0
        assert rule.time_window == "5m"
        assert rule.severity == "critical"

    def test_custom_fields(self):
        rule = SanityRule(name="oom", query="OOM", threshold=2, time_window="10m", severity="warning")
        assert rule.threshold == 2
        assert rule.time_window == "10m"
        assert rule.severity == "warning"


class TestCheckResult:
    """Test CheckResult dataclass."""

    def test_passed_status(self):
        rule = SanityRule(name="test", query="q")
        result = CheckResult(rule=rule, passed=True, match_count=0)
        assert result.status == "\u2705 PASS"
        assert result.samples == []

    def test_failed_status(self):
        rule = SanityRule(name="test", query="q")
        result = CheckResult(rule=rule, passed=False, match_count=5, samples=["line1", "line2"])
        assert result.status == "\u274c FAIL"
        assert len(result.samples) == 2


class TestLoadRules:
    """Test loading rules from YAML file."""

    def test_no_file_returns_empty(self, tmp_path):
        rules = load_rules(str(tmp_path))
        assert rules == []

    def test_loads_rules_from_yaml(self, tmp_path):
        config_dir = tmp_path / ".code-agents"
        config_dir.mkdir()
        yaml_content = """
rules:
  - name: No 5xx errors
    query: "level:ERROR AND status:5*"
    threshold: 0
    time_window: 5m
    severity: critical
  - name: No OOM
    query: "OOMKilled"
    threshold: 1
    time_window: 10m
    severity: warning
"""
        (config_dir / "sanity.yaml").write_text(yaml_content)
        rules = load_rules(str(tmp_path))
        assert len(rules) == 2
        assert rules[0].name == "No 5xx errors"
        assert rules[0].threshold == 0
        assert rules[1].severity == "warning"
        assert rules[1].threshold == 1

    def test_invalid_yaml_returns_empty(self, tmp_path):
        config_dir = tmp_path / ".code-agents"
        config_dir.mkdir()
        (config_dir / "sanity.yaml").write_text("{{invalid yaml")
        rules = load_rules(str(tmp_path))
        assert rules == []

    def test_empty_yaml_returns_empty(self, tmp_path):
        config_dir = tmp_path / ".code-agents"
        config_dir.mkdir()
        (config_dir / "sanity.yaml").write_text("")
        rules = load_rules(str(tmp_path))
        assert rules == []

    def test_yaml_without_rules_key(self, tmp_path):
        config_dir = tmp_path / ".code-agents"
        config_dir.mkdir()
        (config_dir / "sanity.yaml").write_text("other_key: value")
        rules = load_rules(str(tmp_path))
        assert rules == []


class TestRunCheck:
    """Test run_check against a mocked Kibana client."""

    def test_check_passes_when_under_threshold(self):
        rule = SanityRule(name="test", query="error", threshold=5)
        mock_kibana = MagicMock()
        mock_kibana.search_logs = AsyncMock(return_value=[
            {"message": "line1"},
            {"message": "line2"},
        ])
        result = asyncio.run(run_check(rule, mock_kibana, service="my-svc"))
        assert result.passed is True
        assert result.match_count == 2

    def test_check_fails_when_over_threshold(self):
        rule = SanityRule(name="test", query="error", threshold=0)
        mock_kibana = MagicMock()
        mock_kibana.search_logs = AsyncMock(return_value=[
            {"message": "error line"},
        ])
        result = asyncio.run(run_check(rule, mock_kibana))
        assert result.passed is False
        assert result.match_count == 1

    def test_check_passes_at_threshold(self):
        rule = SanityRule(name="test", query="error", threshold=3)
        mock_kibana = MagicMock()
        mock_kibana.search_logs = AsyncMock(return_value=[
            {"message": "a"},
            {"message": "b"},
            {"message": "c"},
        ])
        result = asyncio.run(run_check(rule, mock_kibana))
        assert result.passed is True
        assert result.match_count == 3

    def test_check_handles_exception(self):
        rule = SanityRule(name="failing", query="q")
        mock_kibana = MagicMock()
        mock_kibana.search_logs = AsyncMock(side_effect=Exception("Connection refused"))
        result = asyncio.run(run_check(rule, mock_kibana))
        assert result.passed is False
        assert result.match_count == -1
        assert "Connection refused" in result.samples[0]

    def test_samples_truncated(self):
        rule = SanityRule(name="test", query="q", threshold=0)
        mock_kibana = MagicMock()
        mock_kibana.search_logs = AsyncMock(return_value=[
            {"message": "a" * 300},
            {"message": "b" * 300},
            {"message": "c" * 300},
            {"message": "d" * 300},
            {"message": "e" * 300},
        ])
        result = asyncio.run(run_check(rule, mock_kibana))
        assert len(result.samples) == 3  # max 3 samples
        assert len(result.samples[0]) <= 200  # truncated to 200


class TestRunAllChecks:
    """Test run_all_checks orchestration."""

    def test_no_rules_returns_empty(self, tmp_path):
        mock_kibana = MagicMock()
        results = asyncio.run(run_all_checks(str(tmp_path), "svc", mock_kibana))
        assert results == []

    def test_runs_all_rules(self, tmp_path):
        config_dir = tmp_path / ".code-agents"
        config_dir.mkdir()
        yaml_content = """
rules:
  - name: Rule1
    query: "error"
    threshold: 0
  - name: Rule2
    query: "fatal"
    threshold: 1
"""
        (config_dir / "sanity.yaml").write_text(yaml_content)
        mock_kibana = MagicMock()
        mock_kibana.search_logs = AsyncMock(return_value=[])
        results = asyncio.run(run_all_checks(str(tmp_path), "my-svc", mock_kibana))
        assert len(results) == 2
        assert all(r.passed for r in results)


class TestFormatReport:
    """Test format_report output."""

    def test_empty_results(self):
        report = format_report([])
        assert "No sanity rules" in report

    def test_all_passed(self):
        rule = SanityRule(name="Test Rule", query="q", threshold=5)
        results = [CheckResult(rule=rule, passed=True, match_count=2)]
        report = format_report(results)
        assert "ALL CHECKS PASSED" in report
        assert "Test Rule" in report

    def test_some_failed(self):
        rule1 = SanityRule(name="Good Rule", query="q", threshold=5)
        rule2 = SanityRule(name="Bad Rule", query="q", threshold=0)
        results = [
            CheckResult(rule=rule1, passed=True, match_count=2),
            CheckResult(rule=rule2, passed=False, match_count=3, samples=["error line"]),
        ]
        report = format_report(results)
        assert "FAILED" in report
        assert "Bad Rule" in report
        assert "error line" in report

    def test_error_result_formatting(self):
        rule = SanityRule(name="Error Rule", query="q")
        results = [CheckResult(rule=rule, passed=False, match_count=-1, samples=["Check failed"])]
        report = format_report(results)
        assert "(error)" in report


class TestDefaultRules:
    """Test DEFAULT_RULES are properly defined."""

    def test_default_rules_count(self):
        assert len(DEFAULT_RULES) == 4

    def test_default_rules_types(self):
        for rule in DEFAULT_RULES:
            assert isinstance(rule, SanityRule)
            assert rule.name
            assert rule.query


# ---------------------------------------------------------------------------
# Endpoint health checks
# ---------------------------------------------------------------------------


class TestEndpointCheck:
    def test_defaults(self):
        from code_agents.cicd.sanity_checker import EndpointCheck
        ec = EndpointCheck(url="http://localhost:8080/health")
        assert ec.expected_status == 200
        assert ec.timeout == 10
        assert ec.name == ""

    def test_custom(self):
        from code_agents.cicd.sanity_checker import EndpointCheck
        ec = EndpointCheck(url="http://x/ping", expected_status=204, name="Ping", timeout=5)
        assert ec.expected_status == 204
        assert ec.name == "Ping"


class TestRunEndpointChecks:
    def test_success(self):
        import asyncio
        from code_agents.cicd.sanity_checker import run_endpoint_checks, EndpointCheck
        check = EndpointCheck(url="http://localhost:8080/health", name="Health")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client
            results = asyncio.run(run_endpoint_checks([check]))
        assert len(results) == 1
        assert results[0].passed is True

    def test_failure_wrong_status(self):
        import asyncio
        from code_agents.cicd.sanity_checker import run_endpoint_checks, EndpointCheck
        check = EndpointCheck(url="http://localhost:8080/health", name="Health")
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client
            results = asyncio.run(run_endpoint_checks([check]))
        assert results[0].passed is False

    def test_connection_error(self):
        import asyncio
        from code_agents.cicd.sanity_checker import run_endpoint_checks, EndpointCheck
        check = EndpointCheck(url="http://localhost:9999/health", name="Health")
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_cls.return_value = mock_client
            results = asyncio.run(run_endpoint_checks([check]))
        assert results[0].passed is False
        assert "Connection refused" in results[0].samples[0]


class TestDiscoverHealthEndpoints:
    def test_finds_health_endpoints(self, tmp_path):
        from code_agents.cicd.sanity_checker import discover_health_endpoints
        from code_agents.cicd.endpoint_scanner import RestEndpoint, ScanResult
        mock_result = ScanResult(
            repo_name="test",
            rest_endpoints=[
                RestEndpoint(method="GET", path="/actuator/health", controller="HealthCtrl", file="x.java", line=1),
                RestEndpoint(method="GET", path="/api/orders", controller="OrderCtrl", file="y.java", line=1),
                RestEndpoint(method="GET", path="/ping", controller="PingCtrl", file="z.java", line=1),
            ],
        )
        with patch("code_agents.cicd.endpoint_scanner.load_cache", return_value=mock_result):
            checks = discover_health_endpoints(str(tmp_path))
        assert len(checks) == 2  # /actuator/health and /ping
        urls = [c.url for c in checks]
        assert any("/actuator/health" in u for u in urls)
        assert any("/ping" in u for u in urls)

    def test_default_when_no_cache(self, tmp_path):
        from code_agents.cicd.sanity_checker import discover_health_endpoints
        with patch("code_agents.cicd.endpoint_scanner.load_cache", return_value=None):
            checks = discover_health_endpoints(str(tmp_path))
        assert len(checks) == 1
        assert "actuator/health" in checks[0].url
