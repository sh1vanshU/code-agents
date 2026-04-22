"""Tests for acquirer_health module — metrics, alerts, log parsing, dashboard."""

from __future__ import annotations

import json
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from code_agents.domain.acquirer_health import (
    AcquirerHealthMonitor,
    AcquirerMetrics,
    HealthReport,
    format_health_dashboard,
    report_to_dict,
    _format_volume,
    _window_to_seconds,
    _status_label,
    SUCCESS_RATE_CRIT,
    SUCCESS_RATE_WARN,
    LATENCY_WARN_MS,
    TIMEOUT_RATE_WARN,
)


# ── TestMetrics ─────────────────────────────────────────────────────────────


class TestMetrics:
    """Test AcquirerMetrics construction and dataclass behavior."""

    def test_basic_construction(self):
        m = AcquirerMetrics(
            name="Visa",
            success_rate=99.5,
            avg_latency_ms=120.0,
            error_count=5,
            timeout_count=1,
            volume=10000,
        )
        assert m.name == "Visa"
        assert m.success_rate == 99.5
        assert m.avg_latency_ms == 120.0
        assert m.error_count == 5
        assert m.timeout_count == 1
        assert m.volume == 10000
        assert m.top_errors == []

    def test_with_top_errors(self):
        m = AcquirerMetrics(
            name="RuPay",
            success_rate=87.3,
            avg_latency_ms=2100.0,
            error_count=120,
            timeout_count=40,
            volume=3100,
            top_errors=["timeout", "gateway_error", "invalid_card"],
        )
        assert len(m.top_errors) == 3
        assert "timeout" in m.top_errors

    def test_health_report_construction(self):
        metrics = [
            AcquirerMetrics("Visa", 99.2, 145, 8, 1, 12400),
            AcquirerMetrics("UPI-NPCI", 94.1, 890, 265, 90, 45200),
        ]
        report = HealthReport(
            acquirers=metrics,
            overall_success_rate=96.5,
            degraded=["UPI-NPCI: success_rate=94.1%"],
            alerts=[],
            env="prod",
            window="1h",
        )
        assert len(report.acquirers) == 2
        assert report.overall_success_rate == 96.5
        assert report.env == "prod"


# ── TestDegradation ─────────────────────────────────────────────────────────


class TestDegradation:
    """Test degradation detection thresholds."""

    def setup_method(self):
        self.monitor = AcquirerHealthMonitor()

    def test_healthy_acquirer_not_flagged(self):
        metrics = [AcquirerMetrics("Visa", 99.5, 150, 5, 1, 10000)]
        degraded = self.monitor._detect_degradation(metrics)
        assert degraded == []

    def test_low_success_rate_flagged(self):
        metrics = [AcquirerMetrics("RuPay", 93.0, 150, 70, 2, 1000)]
        degraded = self.monitor._detect_degradation(metrics)
        assert len(degraded) == 1
        assert "success_rate" in degraded[0]

    def test_high_latency_flagged(self):
        metrics = [AcquirerMetrics("HDFC", 99.0, 2500, 10, 1, 5000)]
        degraded = self.monitor._detect_degradation(metrics)
        assert len(degraded) == 1
        assert "latency" in degraded[0]

    def test_high_timeout_rate_flagged(self):
        metrics = [AcquirerMetrics("SBI", 97.0, 500, 30, 30, 1000)]
        # timeout_rate = 30/1000 = 3% > 2%
        degraded = self.monitor._detect_degradation(metrics)
        assert any("timeout_rate" in d for d in degraded)

    def test_multiple_issues(self):
        metrics = [AcquirerMetrics("Bad-Acq", 80.0, 3000, 200, 50, 1000)]
        degraded = self.monitor._detect_degradation(metrics)
        assert len(degraded) == 1
        # Should contain multiple reasons
        assert "success_rate" in degraded[0]
        assert "latency" in degraded[0]
        assert "timeout_rate" in degraded[0]

    def test_zero_volume_no_timeout_flag(self):
        metrics = [AcquirerMetrics("Empty", 0.0, 0, 0, 0, 0)]
        degraded = self.monitor._detect_degradation(metrics)
        # success_rate < 95 is flagged, but no timeout division by zero
        assert len(degraded) == 1
        assert "timeout_rate" not in degraded[0]


# ── TestAlerts ──────────────────────────────────────────────────────────────


class TestAlerts:
    """Test alert generation for critical conditions."""

    def setup_method(self):
        self.monitor = AcquirerHealthMonitor()

    def test_no_alerts_for_healthy(self):
        metrics = [AcquirerMetrics("Visa", 99.5, 150, 5, 1, 10000)]
        alerts = self.monitor._generate_alerts(metrics)
        assert alerts == []

    def test_critical_success_rate_alert(self):
        metrics = [AcquirerMetrics("RuPay", 85.0, 300, 150, 10, 1000)]
        alerts = self.monitor._generate_alerts(metrics)
        assert any("CRITICAL" in a for a in alerts)

    def test_high_latency_alert(self):
        metrics = [AcquirerMetrics("HDFC", 99.0, 3500, 10, 1, 5000)]
        # 3500 > 2000 * 1.5 = 3000
        alerts = self.monitor._generate_alerts(metrics)
        assert any("HIGH LATENCY" in a for a in alerts)

    def test_timeout_spike_alert(self):
        metrics = [AcquirerMetrics("SBI", 95.0, 500, 50, 50, 1000)]
        # timeout_rate = 5% > 2% * 2 = 4%
        alerts = self.monitor._generate_alerts(metrics)
        assert any("TIMEOUT SPIKE" in a for a in alerts)

    def test_zero_volume_alert(self):
        metrics = [AcquirerMetrics("Ghost", 0.0, 0.0, 0, 0, 0)]
        alerts = self.monitor._generate_alerts(metrics)
        assert any("NO TRAFFIC" in a for a in alerts)


# ── TestLogParsing ──────────────────────────────────────────────────────────


class TestLogParsing:
    """Test local log file parsing for metrics extraction."""

    def setup_method(self):
        self.monitor = AcquirerHealthMonitor()

    def test_parse_json_log_lines(self):
        log_lines = [
            json.dumps({"acquirer": "Visa", "status": "success", "latency_ms": 100}),
            json.dumps({"acquirer": "Visa", "status": "success", "latency_ms": 200}),
            json.dumps({"acquirer": "Visa", "status": "failed", "latency_ms": 500, "error": "declined"}),
            json.dumps({"acquirer": "RuPay", "status": "success", "latency_ms": 300}),
            json.dumps({"acquirer": "RuPay", "status": "failed", "latency_ms": 3000, "error": "timeout"}),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "payments.log")
            with open(log_file, "w") as f:
                f.write("\n".join(log_lines) + "\n")

            metrics = self.monitor._parse_log_files(tmpdir)

        assert len(metrics) == 2
        visa = next(m for m in metrics if m.name == "Visa")
        assert visa.volume == 3
        assert visa.success_rate == pytest.approx(66.67, abs=0.01)
        assert visa.avg_latency_ms == pytest.approx(266.7, abs=0.1)
        assert visa.error_count == 1

        rupay = next(m for m in metrics if m.name == "RuPay")
        assert rupay.volume == 2
        assert rupay.timeout_count == 1

    def test_empty_log_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            metrics = self.monitor._parse_log_files(tmpdir)
        assert metrics == []

    def test_malformed_lines_skipped(self):
        log_lines = [
            "not json at all",
            json.dumps({"acquirer": "Visa", "status": "success", "latency_ms": 100}),
            "{bad json",
            json.dumps({"no_acquirer": True}),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "app.log")
            with open(log_file, "w") as f:
                f.write("\n".join(log_lines) + "\n")

            metrics = self.monitor._parse_log_files(tmpdir)

        assert len(metrics) == 1
        assert metrics[0].name == "Visa"
        assert metrics[0].volume == 1

    def test_check_from_logs(self):
        log_lines = [
            json.dumps({"acquirer": "Visa", "status": "success", "latency_ms": 100}),
            json.dumps({"acquirer": "Visa", "status": "success", "latency_ms": 150}),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = os.path.join(tmpdir, "payments.log")
            with open(log_file, "w") as f:
                f.write("\n".join(log_lines) + "\n")

            report = self.monitor.check_from_logs(log_dir=tmpdir)

        assert isinstance(report, HealthReport)
        assert report.env == "local"
        assert report.window == "logs"
        assert len(report.acquirers) == 1
        assert report.acquirers[0].success_rate == 100.0


# ── TestFormatDashboard ─────────────────────────────────────────────────────


class TestFormatDashboard:
    """Test dashboard table formatting."""

    def test_empty_report(self):
        report = HealthReport(
            acquirers=[],
            overall_success_rate=0.0,
            degraded=[],
            alerts=["No data"],
        )
        output = format_health_dashboard(report)
        assert "No acquirer data available" in output
        assert "No data" in output

    def test_table_structure(self):
        report = HealthReport(
            acquirers=[
                AcquirerMetrics("Visa", 99.2, 145, 8, 1, 12400),
                AcquirerMetrics("UPI-NPCI", 94.1, 890, 265, 90, 45200),
                AcquirerMetrics("RuPay", 87.3, 2100, 120, 40, 3100),
            ],
            overall_success_rate=93.5,
            degraded=["UPI-NPCI: success_rate=94.1%"],
            alerts=["CRITICAL: RuPay success rate 87.3%"],
            env="prod",
            window="1h",
        )
        output = format_health_dashboard(report)
        assert "Visa" in output
        assert "UPI-NPCI" in output
        assert "RuPay" in output
        assert "Acquirer" in output
        assert "Success" in output
        assert "Latency" in output
        assert "Volume" in output
        assert "Overall success rate" in output
        assert "Degraded" in output
        assert "Alerts" in output

    def test_report_to_dict(self):
        report = HealthReport(
            acquirers=[AcquirerMetrics("Visa", 99.2, 145, 8, 1, 12400)],
            overall_success_rate=99.2,
            degraded=[],
            alerts=[],
            timestamp="2026-04-09T10:00:00+00:00",
            env="prod",
            window="1h",
        )
        d = report_to_dict(report)
        assert d["env"] == "prod"
        assert d["window"] == "1h"
        assert len(d["acquirers"]) == 1
        assert d["acquirers"][0]["name"] == "Visa"
        assert d["overall_success_rate"] == 99.2


# ── TestHelpers ─────────────────────────────────────────────────────────────


class TestHelpers:
    """Test utility functions."""

    def test_format_volume_small(self):
        assert _format_volume(500) == "500"

    def test_format_volume_thousands(self):
        assert _format_volume(12400) == "12.4K"

    def test_format_volume_millions(self):
        assert _format_volume(1_500_000) == "1.5M"

    def test_window_to_seconds(self):
        assert _window_to_seconds("1h") == 3600
        assert _window_to_seconds("30m") == 1800
        assert _window_to_seconds("2d") == 172800
        assert _window_to_seconds("invalid") == 3600

    def test_status_label_ok(self):
        m = AcquirerMetrics("Visa", 99.0, 150, 5, 1, 10000)
        label = _status_label(m)
        assert "OK" in label

    def test_status_label_degrade(self):
        m = AcquirerMetrics("UPI", 93.0, 500, 70, 10, 5000)
        label = _status_label(m)
        assert "DEGRADE" in label

    def test_status_label_down(self):
        m = AcquirerMetrics("RuPay", 85.0, 2100, 150, 40, 3000)
        label = _status_label(m)
        assert "DOWN" in label

    def test_status_label_slow(self):
        m = AcquirerMetrics("HDFC", 98.0, 2500, 20, 5, 8000)
        label = _status_label(m)
        assert "SLOW" in label


# ── TestCheckWithMocks ──────────────────────────────────────────────────────


class TestCheckWithMocks:
    """Test check() method with mocked external clients."""

    def test_check_no_sources_configured(self):
        monitor = AcquirerHealthMonitor()
        report = monitor.check(env="prod", window="1h")
        assert report.overall_success_rate == 0.0
        assert len(report.alerts) > 0
        assert "No data sources" in report.alerts[0]

    @patch.dict(os.environ, {"GRAFANA_URL": "http://grafana:3000"})
    def test_check_grafana_connection_error(self):
        monitor = AcquirerHealthMonitor()
        # Grafana client will be created but queries will fail gracefully
        report = monitor.check(env="staging", window="30m")
        # Should fall through to no-data state
        assert isinstance(report, HealthReport)

    def test_build_report(self):
        monitor = AcquirerHealthMonitor()
        metrics = [
            AcquirerMetrics("Visa", 99.0, 150, 10, 1, 10000),
            AcquirerMetrics("UPI", 93.0, 800, 350, 100, 5000),
        ]
        report = monitor._build_report(metrics, "prod", "1h")
        assert report.env == "prod"
        assert report.window == "1h"
        assert report.overall_success_rate > 0
        assert len(report.degraded) > 0  # UPI is degraded
        assert report.timestamp != ""
