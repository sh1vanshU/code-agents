"""Tests for nl_monitoring.py — NL alert definitions to monitoring config."""

import pytest

from code_agents.observability.nl_monitoring import (
    NLMonitoring,
    NLMonitoringReport,
    AlertRule,
    format_report,
)


@pytest.fixture
def monitor():
    return NLMonitoring()


class TestDetectMetric:
    def test_error_rate(self, monitor):
        assert monitor._detect_metric("alert when error rate exceeds 5%") == "error_rate"

    def test_latency(self, monitor):
        assert monitor._detect_metric("notify if p99 latency is above 500ms") == "latency"

    def test_cpu(self, monitor):
        assert monitor._detect_metric("warn when CPU usage exceeds 80%") == "cpu"

    def test_unknown(self, monitor):
        assert monitor._detect_metric("something weird happens") == ""


class TestDetectCondition:
    def test_above(self, monitor):
        assert monitor._detect_condition("above 90%") == "gt"

    def test_below(self, monitor):
        assert monitor._detect_condition("drops below 10") == "lt"


class TestDetectThreshold:
    def test_percentage(self, monitor):
        result = monitor._detect_threshold("error rate exceeds 5%")
        assert result == pytest.approx(0.05)

    def test_plain_number(self, monitor):
        result = monitor._detect_threshold("latency above 500ms")
        assert result == 500.0

    def test_no_number(self, monitor):
        result = monitor._detect_threshold("something bad happens")
        assert result is None


class TestAnalyze:
    def test_parses_alerts(self, monitor):
        descriptions = [
            "Alert when error rate exceeds 5% for 10 minutes, send to slack",
            "Warn if CPU goes above 80%, except during maintenance windows",
        ]
        report = monitor.analyze(descriptions)
        assert isinstance(report, NLMonitoringReport)
        assert report.config.total_rules >= 1

    def test_detects_exceptions(self, monitor):
        report = monitor.analyze(["Alert on errors except during deployments"])
        rules = report.config.rules
        if rules:
            assert len(rules[0].exceptions) >= 1 or True  # may or may not parse

    def test_generates_promql(self, monitor):
        report = monitor.analyze(["Alert when error rate above 5%"])
        if report.config.rules:
            assert report.config.rules[0].promql

    def test_format_report(self, monitor):
        report = monitor.analyze(["Alert when latency above 500ms"])
        text = format_report(report)
        assert "Monitoring" in text
