"""Tests for live_tail module — config, anomaly detection, rendering, query building."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from code_agents.observability.live_tail import (
    AnomalyAlert,
    AnomalyDetector,
    LiveTailStream,
    TailConfig,
    TailRenderer,
)


# ---------------------------------------------------------------------------
# TestTailConfig
# ---------------------------------------------------------------------------

class TestTailConfig:
    """Verify TailConfig defaults and overrides."""

    def test_defaults(self):
        cfg = TailConfig(service="payments-api")
        assert cfg.service == "payments-api"
        assert cfg.env == "dev"
        assert cfg.index == "logs-*"
        assert cfg.log_level == ""
        assert cfg.poll_interval == 5.0
        assert cfg.window_size == 100
        assert cfg.alert_threshold == 5.0

    def test_custom_values(self):
        cfg = TailConfig(
            service="auth-svc",
            env="staging",
            index="app-logs-*",
            log_level="ERROR",
            poll_interval=2.0,
            window_size=50,
            alert_threshold=10.0,
        )
        assert cfg.service == "auth-svc"
        assert cfg.env == "staging"
        assert cfg.index == "app-logs-*"
        assert cfg.log_level == "ERROR"
        assert cfg.poll_interval == 2.0
        assert cfg.window_size == 50
        assert cfg.alert_threshold == 10.0


# ---------------------------------------------------------------------------
# TestQueryBuild
# ---------------------------------------------------------------------------

class TestQueryBuild:
    """Verify Elasticsearch query DSL structure."""

    def test_basic_query_structure(self):
        cfg = TailConfig(service="payments-api")
        stream = LiveTailStream.__new__(LiveTailStream)
        stream.config = cfg
        stream._es_client = None

        query = stream._build_query("2026-01-01T00:00:00Z")

        assert "query" in query
        assert "bool" in query["query"]
        assert "must" in query["query"]["bool"]
        assert query["size"] == 100
        assert query["sort"] == [{"@timestamp": {"order": "asc"}}]

    def test_query_includes_service_filter(self):
        cfg = TailConfig(service="auth-svc")
        stream = LiveTailStream.__new__(LiveTailStream)
        stream.config = cfg
        stream._es_client = None

        query = stream._build_query("2026-01-01T00:00:00Z")
        must = query["query"]["bool"]["must"]

        service_clauses = [c for c in must if "term" in c and "service.keyword" in c["term"]]
        assert len(service_clauses) == 1
        assert service_clauses[0]["term"]["service.keyword"] == "auth-svc"

    def test_query_includes_timestamp_range(self):
        cfg = TailConfig(service="svc")
        stream = LiveTailStream.__new__(LiveTailStream)
        stream.config = cfg
        stream._es_client = None

        since = "2026-04-09T12:00:00Z"
        query = stream._build_query(since)
        must = query["query"]["bool"]["must"]

        range_clauses = [c for c in must if "range" in c]
        assert len(range_clauses) == 1
        assert range_clauses[0]["range"]["@timestamp"]["gt"] == since

    def test_query_with_env_filter(self):
        cfg = TailConfig(service="svc", env="staging")
        stream = LiveTailStream.__new__(LiveTailStream)
        stream.config = cfg
        stream._es_client = None

        query = stream._build_query("2026-01-01T00:00:00Z")
        must = query["query"]["bool"]["must"]

        env_clauses = [c for c in must if "term" in c and "environment.keyword" in c.get("term", {})]
        assert len(env_clauses) == 1
        assert env_clauses[0]["term"]["environment.keyword"] == "staging"

    def test_query_with_log_level_filter(self):
        cfg = TailConfig(service="svc", log_level="error")
        stream = LiveTailStream.__new__(LiveTailStream)
        stream.config = cfg
        stream._es_client = None

        query = stream._build_query("2026-01-01T00:00:00Z")
        must = query["query"]["bool"]["must"]

        level_clauses = [c for c in must if "term" in c and "level.keyword" in c.get("term", {})]
        assert len(level_clauses) == 1
        assert level_clauses[0]["term"]["level.keyword"] == "ERROR"

    def test_query_without_env(self):
        cfg = TailConfig(service="svc", env="")
        stream = LiveTailStream.__new__(LiveTailStream)
        stream.config = cfg
        stream._es_client = None

        query = stream._build_query("2026-01-01T00:00:00Z")
        must = query["query"]["bool"]["must"]

        env_clauses = [c for c in must if "term" in c and "environment.keyword" in c.get("term", {})]
        assert len(env_clauses) == 0

    def test_query_respects_window_size(self):
        cfg = TailConfig(service="svc", window_size=25)
        stream = LiveTailStream.__new__(LiveTailStream)
        stream.config = cfg
        stream._es_client = None

        query = stream._build_query("2026-01-01T00:00:00Z")
        assert query["size"] == 25


# ---------------------------------------------------------------------------
# TestAnomalyDetector
# ---------------------------------------------------------------------------

class TestAnomalyDetector:
    """Verify error rate computation and anomaly threshold triggering."""

    def _make_logs(self, levels: list[str]) -> list[dict]:
        return [{"level": lv, "message": f"msg-{i}"} for i, lv in enumerate(levels)]

    def test_no_errors_returns_none(self):
        cfg = TailConfig(service="svc", alert_threshold=5.0)
        det = AnomalyDetector(cfg)
        logs = self._make_logs(["INFO", "INFO", "DEBUG", "INFO"])
        assert det.analyze_batch(logs) is None

    def test_below_threshold_returns_none(self):
        cfg = TailConfig(service="svc", alert_threshold=50.0)
        det = AnomalyDetector(cfg)
        # 1/10 = 10% < 50%
        logs = self._make_logs(["ERROR"] + ["INFO"] * 9)
        assert det.analyze_batch(logs) is None

    def test_above_threshold_returns_alert(self):
        cfg = TailConfig(service="svc", alert_threshold=5.0)
        det = AnomalyDetector(cfg)
        # 3/10 = 30% > 5%
        logs = self._make_logs(["ERROR", "ERROR", "ERROR"] + ["INFO"] * 7)
        alert = det.analyze_batch(logs)
        assert alert is not None
        assert isinstance(alert, AnomalyAlert)
        assert alert.error_rate == pytest.approx(30.0)
        assert alert.severity == "HIGH"

    def test_critical_severity(self):
        cfg = TailConfig(service="svc", alert_threshold=5.0)
        det = AnomalyDetector(cfg)
        # 8/10 = 80% -> CRITICAL
        logs = self._make_logs(["ERROR"] * 8 + ["INFO"] * 2)
        alert = det.analyze_batch(logs)
        assert alert is not None
        assert alert.severity == "CRITICAL"

    def test_warning_severity(self):
        cfg = TailConfig(service="svc", alert_threshold=5.0)
        det = AnomalyDetector(cfg)
        # 1/10 = 10% -> WARNING (> 5% but <= 20%)
        logs = self._make_logs(["ERROR"] + ["INFO"] * 9)
        alert = det.analyze_batch(logs)
        assert alert is not None
        assert alert.severity == "WARNING"

    def test_error_rate_zero_for_empty_batch(self):
        cfg = TailConfig(service="svc")
        det = AnomalyDetector(cfg)
        assert det._compute_error_rate([]) == 0.0

    def test_cumulative_tracking(self):
        cfg = TailConfig(service="svc", alert_threshold=100.0)  # never triggers
        det = AnomalyDetector(cfg)
        det.analyze_batch(self._make_logs(["INFO"] * 5))
        det.analyze_batch(self._make_logs(["ERROR"] * 3))
        assert det.total_seen == 8
        assert det.total_errors == 3

    def test_extract_errors(self):
        cfg = TailConfig(service="svc")
        det = AnomalyDetector(cfg)
        logs = self._make_logs(["ERROR", "INFO", "FATAL", "DEBUG", "CRITICAL"])
        errors = det._extract_errors(logs)
        assert len(errors) == 3

    def test_sample_logs_capped_at_5(self):
        cfg = TailConfig(service="svc", alert_threshold=1.0)
        det = AnomalyDetector(cfg)
        logs = self._make_logs(["ERROR"] * 10)
        alert = det.analyze_batch(logs)
        assert alert is not None
        assert len(alert.sample_logs) <= 5


# ---------------------------------------------------------------------------
# TestTailRenderer
# ---------------------------------------------------------------------------

class TestTailRenderer:
    """Verify colorized output and alert rendering."""

    def test_render_info_log(self):
        renderer = TailRenderer()
        entry = {
            "@timestamp": "2026-04-09T12:00:00Z",
            "level": "INFO",
            "service": "payments-api",
            "message": "Request processed",
        }
        line = renderer.render_log_line(entry)
        assert "INFO" in line
        assert "payments-api" in line
        assert "Request processed" in line
        assert "\033[92m" in line  # green

    def test_render_error_log(self):
        renderer = TailRenderer()
        entry = {
            "@timestamp": "2026-04-09T12:00:00Z",
            "level": "ERROR",
            "service": "auth-svc",
            "message": "Connection refused",
        }
        line = renderer.render_log_line(entry)
        assert "\033[91m" in line  # red

    def test_render_debug_log(self):
        renderer = TailRenderer()
        entry = {"level": "DEBUG", "message": "trace details"}
        line = renderer.render_log_line(entry)
        assert "\033[2m" in line  # dim

    def test_render_alert_contains_severity(self):
        renderer = TailRenderer()
        alert = AnomalyAlert(
            timestamp="2026-04-09T12:00:00Z",
            severity="HIGH",
            message="Error rate 30.0% exceeds threshold",
            error_rate=30.0,
            sample_logs=["err1", "err2"],
            analysis="Detected 3 errors in batch of 10",
        )
        output = renderer.render_alert(alert)
        assert "ANOMALY ALERT" in output
        assert "HIGH" in output
        assert "30.0%" in output
        assert "err1" in output

    def test_render_alert_without_analysis(self):
        renderer = TailRenderer()
        alert = AnomalyAlert(
            timestamp="now",
            severity="WARNING",
            message="test",
            error_rate=10.0,
            sample_logs=[],
        )
        output = renderer.render_alert(alert)
        assert "WARNING" in output

    def test_render_stats_bar(self):
        renderer = TailRenderer()
        bar = renderer.render_stats_bar(total=100, errors=3, uptime=120.0)
        assert "logs=100" in bar
        assert "errors=3" in bar
        assert "rate=3.0%" in bar
        assert "uptime=2.0m" in bar

    def test_render_stats_bar_high_error_rate(self):
        renderer = TailRenderer()
        bar = renderer.render_stats_bar(total=100, errors=25, uptime=60.0)
        assert "\033[91m" in bar  # red for > 20%

    def test_render_stats_bar_zero_total(self):
        renderer = TailRenderer()
        bar = renderer.render_stats_bar(total=0, errors=0, uptime=0.0)
        assert "rate=0.0%" in bar


# ---------------------------------------------------------------------------
# TestLiveTailStream (with mocked ES)
# ---------------------------------------------------------------------------

class TestLiveTailStream:
    """Verify stream behaviour with mocked Elasticsearch."""

    def test_query_logs_returns_empty_without_client(self):
        stream = LiveTailStream.__new__(LiveTailStream)
        stream.config = TailConfig(service="svc")
        stream._es_client = None
        assert stream._query_logs("2026-01-01T00:00:00Z") == []

    def test_query_logs_with_mock_client(self):
        stream = LiveTailStream.__new__(LiveTailStream)
        stream.config = TailConfig(service="svc")

        mock_client = MagicMock()
        mock_client.search.return_value = {
            "hits": {
                "hits": [
                    {"_source": {"level": "INFO", "message": "ok"}},
                    {"_source": {"level": "ERROR", "message": "fail"}},
                ]
            }
        }
        stream._es_client = mock_client

        results = stream._query_logs("2026-01-01T00:00:00Z")
        assert len(results) == 2
        assert results[0]["level"] == "INFO"

    def test_query_logs_handles_exception(self):
        stream = LiveTailStream.__new__(LiveTailStream)
        stream.config = TailConfig(service="svc")

        mock_client = MagicMock()
        mock_client.search.side_effect = ConnectionError("unreachable")
        stream._es_client = mock_client

        results = stream._query_logs("2026-01-01T00:00:00Z")
        assert results == []

    def test_stop_sets_event(self):
        stream = LiveTailStream.__new__(LiveTailStream)
        stream.config = TailConfig(service="svc")
        stream._stop_event = asyncio.Event()
        stream._es_client = None

        stream.stop()
        assert stream._stop_event.is_set()

    @pytest.mark.asyncio
    async def test_start_calls_callback(self):
        """Stream should call callback with entries then stop."""
        stream = LiveTailStream.__new__(LiveTailStream)
        stream.config = TailConfig(service="svc", poll_interval=0.1)
        stream._stop_event = asyncio.Event()
        stream._last_timestamp = "2026-01-01T00:00:00Z"
        stream._es_client = None

        mock_client = MagicMock()
        mock_client.search.return_value = {
            "hits": {
                "hits": [
                    {"_source": {"@timestamp": "2026-01-01T00:00:01Z", "level": "INFO", "message": "hello"}},
                ]
            }
        }
        stream._es_client = mock_client

        received: list = []

        def cb(entries):
            received.extend(entries)
            stream.stop()  # stop after first batch

        await stream.start(cb)
        assert len(received) == 1
        assert received[0]["message"] == "hello"
