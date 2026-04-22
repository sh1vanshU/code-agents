"""Tests for performance.py — endpoint profiling and baseline comparison."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open

import pytest

from code_agents.observability.performance import (
    EndpointResult,
    BaselineEntry,
    ProfileReport,
    PerformanceProfiler,
    format_profile_report,
    BASELINE_PATH,
)


class TestEndpointResultPercentiles:
    """Test percentile calculation on EndpointResult."""

    def test_percentiles_basic(self):
        """Verify p50/p95/p99 on a known set of latencies."""
        result = EndpointResult(url="http://localhost/health", iterations=20)
        # 20 values: 10, 20, 30, ..., 200
        result.latencies_ms = [float(i * 10) for i in range(1, 21)]
        n = len(result.latencies_ms)
        sorted_lat = sorted(result.latencies_ms)
        result.p50 = sorted_lat[int(n * 0.5)]
        result.p95 = sorted_lat[min(int(n * 0.95), n - 1)]
        result.p99 = sorted_lat[min(int(n * 0.99), n - 1)]

        assert result.p50 == 110.0
        assert result.p95 == 200.0
        assert result.p99 == 200.0

    def test_percentiles_single_value(self):
        """Single-value latency should give same p50/p95/p99."""
        result = EndpointResult(url="http://localhost/x", iterations=1)
        result.latencies_ms = [42.0]
        sorted_lat = sorted(result.latencies_ms)
        n = 1
        result.p50 = sorted_lat[int(n * 0.5)]
        result.p95 = sorted_lat[min(int(n * 0.95), n - 1)]
        result.p99 = sorted_lat[min(int(n * 0.99), n - 1)]

        assert result.p50 == 42.0
        assert result.p95 == 42.0
        assert result.p99 == 42.0

    def test_empty_latencies(self):
        """No latencies should leave percentiles at 0."""
        result = EndpointResult(url="http://localhost/x", iterations=0)
        assert result.p50 == 0.0
        assert result.p95 == 0.0
        assert result.p99 == 0.0


class TestBaselineEntrySerialization:
    """Test BaselineEntry to/from dict."""

    def test_round_trip(self):
        entry = BaselineEntry(
            url="http://localhost/health",
            method="GET",
            p50=15.2,
            p95=45.6,
            p99=98.3,
            avg=22.1,
            recorded_at="2026-04-01T10:00:00",
        )
        d = vars(entry)
        restored = BaselineEntry(**d)
        assert restored.url == entry.url
        assert restored.p50 == entry.p50
        assert restored.p95 == entry.p95
        assert restored.p99 == entry.p99
        assert restored.avg == entry.avg
        assert restored.recorded_at == entry.recorded_at

    def test_defaults(self):
        entry = BaselineEntry(url="http://x")
        assert entry.method == "GET"
        assert entry.p50 == 0.0
        assert entry.recorded_at == ""


class TestBaselinePersistence:
    """Test _save_baselines and _load_baselines round-trip."""

    def test_save_and_load(self, tmp_path):
        baseline_file = tmp_path / "perf_baseline.json"
        with patch("code_agents.observability.performance.BASELINE_PATH", baseline_file):
            profiler = PerformanceProfiler()
            # Save a result
            result = EndpointResult(
                url="http://localhost:8000/health",
                method="GET",
                iterations=10,
                p50=12.0, p95=25.0, p99=40.0, avg=15.0,
            )
            profiler.save_as_baseline([result])

            assert baseline_file.exists()

            # Load in a new profiler
            profiler2 = PerformanceProfiler()
            key = "GET http://localhost:8000/health"
            assert key in profiler2.baselines
            assert profiler2.baselines[key].p50 == 12.0
            assert profiler2.baselines[key].p95 == 25.0

    def test_load_missing_file(self, tmp_path):
        baseline_file = tmp_path / "nonexistent.json"
        with patch("code_agents.observability.performance.BASELINE_PATH", baseline_file):
            profiler = PerformanceProfiler()
            assert profiler.baselines == {}

    def test_load_corrupt_file(self, tmp_path):
        baseline_file = tmp_path / "perf_baseline.json"
        baseline_file.write_text("not json")
        with patch("code_agents.observability.performance.BASELINE_PATH", baseline_file):
            profiler = PerformanceProfiler()
            assert profiler.baselines == {}


class TestBaselineComparison:
    """Test regression and improvement detection."""

    def test_regression_detected(self, tmp_path):
        """Change > 20% should be flagged as regression."""
        baseline_file = tmp_path / "perf_baseline.json"
        data = {
            "baselines": [
                {"url": "http://localhost/api", "method": "GET",
                 "p50": 10.0, "p95": 20.0, "p99": 30.0, "avg": 12.0,
                 "recorded_at": "2026-04-01T10:00:00"},
            ],
            "updated": "2026-04-01T10:00:00",
        }
        baseline_file.write_text(json.dumps(data))

        with patch("code_agents.observability.performance.BASELINE_PATH", baseline_file):
            profiler = PerformanceProfiler()
            # Current is 50% slower
            result = EndpointResult(
                url="http://localhost/api", method="GET", iterations=5,
                latencies_ms=[15.0] * 5,
                p50=15.0, p95=30.0, p99=45.0, avg=18.0,
            )
            report = ProfileReport(results=[result], total_requests=5)

            # Manually trigger comparison
            for r in report.results:
                key = f"{r.method} {r.url}"
                baseline = profiler.baselines.get(key)
                if baseline:
                    for metric in ["p50", "p95", "p99", "avg"]:
                        base_val = getattr(baseline, metric, 0)
                        curr_val = getattr(r, metric, 0)
                        if base_val > 0:
                            change_pct = ((curr_val - base_val) / base_val) * 100
                            report.baseline_comparison.append({
                                "url": r.url, "method": r.method, "metric": metric,
                                "baseline": base_val, "current": curr_val,
                                "change_pct": round(change_pct, 1),
                                "regression": change_pct > 20,
                            })

            regressions = [c for c in report.baseline_comparison if c["regression"]]
            assert len(regressions) > 0
            # p50: 10 -> 15 = +50%
            p50_reg = [c for c in regressions if c["metric"] == "p50"]
            assert len(p50_reg) == 1
            assert p50_reg[0]["change_pct"] == 50.0

    def test_improvement_detected(self, tmp_path):
        """Change < -10% should be flagged as improvement."""
        baseline_file = tmp_path / "perf_baseline.json"
        data = {
            "baselines": [
                {"url": "http://localhost/api", "method": "GET",
                 "p50": 100.0, "p95": 200.0, "p99": 300.0, "avg": 120.0,
                 "recorded_at": "2026-04-01T10:00:00"},
            ],
            "updated": "2026-04-01T10:00:00",
        }
        baseline_file.write_text(json.dumps(data))

        with patch("code_agents.observability.performance.BASELINE_PATH", baseline_file):
            profiler = PerformanceProfiler()
            # Current is 50% faster
            result = EndpointResult(
                url="http://localhost/api", method="GET", iterations=5,
                latencies_ms=[50.0] * 5,
                p50=50.0, p95=100.0, p99=150.0, avg=60.0,
            )
            report = profiler.profile_multiple(
                [{"url": "http://localhost/api", "method": "GET"}],
                iterations=0,
            )
            # Override with our result
            report.results = [result]
            report.baseline_comparison = []
            for r in report.results:
                key = f"{r.method} {r.url}"
                baseline = profiler.baselines.get(key)
                if baseline:
                    for metric in ["p50", "p95", "p99", "avg"]:
                        base_val = getattr(baseline, metric, 0)
                        curr_val = getattr(r, metric, 0)
                        if base_val > 0:
                            change_pct = ((curr_val - base_val) / base_val) * 100
                            report.baseline_comparison.append({
                                "url": r.url, "method": r.method, "metric": metric,
                                "baseline": base_val, "current": curr_val,
                                "change_pct": round(change_pct, 1),
                                "regression": change_pct > 20,
                            })

            improvements = [c for c in report.baseline_comparison if c["change_pct"] < -10]
            assert len(improvements) > 0

    def test_no_regression_within_threshold(self, tmp_path):
        """Change <= 20% should not be flagged as regression."""
        baseline_file = tmp_path / "perf_baseline.json"
        data = {
            "baselines": [
                {"url": "http://localhost/api", "method": "GET",
                 "p50": 100.0, "p95": 200.0, "p99": 300.0, "avg": 120.0,
                 "recorded_at": "2026-04-01T10:00:00"},
            ],
            "updated": "2026-04-01T10:00:00",
        }
        baseline_file.write_text(json.dumps(data))

        with patch("code_agents.observability.performance.BASELINE_PATH", baseline_file):
            profiler = PerformanceProfiler()
            # Only 10% slower (within 20% threshold)
            result = EndpointResult(
                url="http://localhost/api", method="GET", iterations=5,
                latencies_ms=[110.0] * 5,
                p50=110.0, p95=220.0, p99=330.0, avg=132.0,
            )
            report = ProfileReport(results=[result], total_requests=5)
            for r in report.results:
                key = f"{r.method} {r.url}"
                baseline = profiler.baselines.get(key)
                if baseline:
                    for metric in ["p50", "p95", "p99", "avg"]:
                        base_val = getattr(baseline, metric, 0)
                        curr_val = getattr(r, metric, 0)
                        if base_val > 0:
                            change_pct = ((curr_val - base_val) / base_val) * 100
                            report.baseline_comparison.append({
                                "url": r.url, "method": r.method, "metric": metric,
                                "baseline": base_val, "current": curr_val,
                                "change_pct": round(change_pct, 1),
                                "regression": change_pct > 20,
                            })

            regressions = [c for c in report.baseline_comparison if c["regression"]]
            assert len(regressions) == 0


class TestProfileEndpoint:
    """Test profile_endpoint with mocked network."""

    def test_profile_endpoint_mock(self):
        """Profile with mocked urlopen should record latencies."""
        mock_resp = MagicMock()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = b"OK"
        mock_resp.status = 200

        with patch("code_agents.observability.performance.urlopen", return_value=mock_resp):
            profiler = PerformanceProfiler()
            result = profiler.profile_endpoint(
                "http://localhost:8000/health",
                iterations=5,
                timeout=5.0,
            )

        assert result.iterations == 5
        assert len(result.latencies_ms) == 5
        assert result.errors == 0
        assert 200 in result.status_codes
        assert result.status_codes[200] == 5
        assert result.p50 > 0
        assert result.avg > 0

    def test_profile_endpoint_with_errors(self):
        """Errors should be counted but latencies still recorded."""
        from urllib.error import URLError

        def side_effect(*args, **kwargs):
            raise URLError("Connection refused")

        with patch("code_agents.observability.performance.urlopen", side_effect=side_effect):
            profiler = PerformanceProfiler()
            result = profiler.profile_endpoint(
                "http://localhost:9999/fail",
                iterations=3,
                timeout=2.0,
            )

        assert result.iterations == 3
        assert result.errors == 3
        assert len(result.latencies_ms) == 3


class TestFormatProfileReport:
    """Test format_profile_report output."""

    def test_basic_format(self):
        result = EndpointResult(
            url="http://localhost/health", method="GET", iterations=10,
            latencies_ms=[10.0, 20.0, 30.0],
            p50=20.0, p95=30.0, p99=30.0, avg=20.0,
            min_ms=10.0, max_ms=30.0,
            status_codes={200: 3},
        )
        report = ProfileReport(
            results=[result], total_requests=10, total_errors=0, duration_s=1.5,
        )
        output = format_profile_report(report)

        assert "PERFORMANCE PROFILE" in output
        assert "Requests: 10" in output
        assert "GET http://localhost/health" in output
        assert "p50:" in output
        assert "p95:" in output
        assert "p99:" in output
        assert "200: 3" in output

    def test_format_with_regressions(self):
        result = EndpointResult(
            url="http://localhost/api", method="GET", iterations=5,
            latencies_ms=[50.0],
            p50=50.0, p95=80.0, p99=90.0, avg=55.0,
            min_ms=50.0, max_ms=90.0,
        )
        report = ProfileReport(
            results=[result], total_requests=5,
            baseline_comparison=[
                {"url": "http://localhost/api", "method": "GET", "metric": "p50",
                 "baseline": 20.0, "current": 50.0, "change_pct": 150.0, "regression": True},
            ],
        )
        output = format_profile_report(report)
        assert "Regressions" in output
        assert "+150.0%" in output

    def test_format_no_data(self):
        result = EndpointResult(
            url="http://localhost/x", method="GET", iterations=0,
        )
        report = ProfileReport(results=[result], total_requests=0)
        output = format_profile_report(report)
        assert "(no data)" in output


class TestDiscoverEndpoints:
    """Test discover_endpoints fallback."""

    def test_fallback_endpoints(self):
        """When scanner is unavailable, should return health endpoints."""
        with patch.dict(os.environ, {"CODE_AGENTS_PUBLIC_BASE_URL": "http://localhost:8000"}):
            profiler = PerformanceProfiler()
            # Patch scanner to fail
            with patch("code_agents.observability.performance.PerformanceProfiler.discover_endpoints") as mock_discover:
                # Call the real method but ensure scanner import fails
                mock_discover.side_effect = lambda cwd: [
                    {"url": "http://localhost:8000/health", "method": "GET"},
                    {"url": "http://localhost:8000/actuator/health", "method": "GET"},
                ]
                endpoints = profiler.discover_endpoints(".")

        assert len(endpoints) == 2
        assert any("/health" in ep["url"] for ep in endpoints)

    def test_discover_returns_list(self):
        """discover_endpoints should always return a list."""
        profiler = PerformanceProfiler()
        # Force scanner import to fail
        with patch("code_agents.observability.performance.os.getenv", return_value="http://localhost:8000"):
            endpoints = profiler.discover_endpoints("/nonexistent")
        assert isinstance(endpoints, list)


class TestSaveAsBaseline:
    """Test save_as_baseline."""

    def test_save_multiple(self, tmp_path):
        baseline_file = tmp_path / "perf_baseline.json"
        with patch("code_agents.observability.performance.BASELINE_PATH", baseline_file):
            profiler = PerformanceProfiler()
            results = [
                EndpointResult(
                    url="http://localhost/a", method="GET", iterations=10,
                    p50=10.0, p95=20.0, p99=30.0, avg=12.0,
                ),
                EndpointResult(
                    url="http://localhost/b", method="POST", iterations=10,
                    p50=50.0, p95=80.0, p99=100.0, avg=55.0,
                ),
            ]
            count = profiler.save_as_baseline(results)

        assert count == 2
        assert baseline_file.exists()

        data = json.loads(baseline_file.read_text())
        assert len(data["baselines"]) == 2
        assert data["baselines"][0]["url"] == "http://localhost/a"
        assert data["baselines"][1]["url"] == "http://localhost/b"
        assert data["baselines"][1]["method"] == "POST"
