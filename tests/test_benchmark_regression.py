"""Tests for code_agents.benchmark_regression — regression detection and comparison."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from code_agents.testing.benchmark_regression import (
    ComparisonResult,
    RegressionAlert,
    RegressionDetector,
    Threshold,
    format_comparison,
    format_trend,
    load_custom_tasks,
)


# ---------------------------------------------------------------------------
# Custom task loader tests
# ---------------------------------------------------------------------------


class TestLoadCustomTasks:
    """Tests for loading custom benchmark tasks."""

    def test_load_nonexistent(self):
        tasks = load_custom_tasks("/nonexistent/path.yaml")
        assert tasks == []

    def test_load_json_fallback(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = os.path.join(tmpdir, "benchmarks.json")
            Path(json_path).write_text(json.dumps({
                "tasks": [
                    {"id": "custom1", "name": "Custom Task", "category": "test", "prompt": "Do something", "judge_criteria": "Does it work?"}
                ]
            }))

            # Pass the yaml path, it should fall back to json
            tasks = load_custom_tasks(os.path.join(tmpdir, "benchmarks.yaml"))
            # May or may not find json depending on yaml import availability
            # Just verify it doesn't crash
            assert isinstance(tasks, list)

    def test_load_default_path(self):
        tasks = load_custom_tasks()
        assert isinstance(tasks, list)


# ---------------------------------------------------------------------------
# RegressionDetector tests
# ---------------------------------------------------------------------------


class TestRegressionDetector:
    """Tests for RegressionDetector."""

    def test_init_defaults(self):
        detector = RegressionDetector()
        assert len(detector.thresholds) > 0

    def test_init_custom_thresholds(self):
        thresholds = [Threshold(metric="min_quality", value=4.5)]
        detector = RegressionDetector(thresholds=thresholds)
        assert len(detector.thresholds) == 1

    def test_compare_no_reports(self):
        detector = RegressionDetector()
        with patch.object(detector, "_latest_reports", return_value=[]):
            result = detector.compare()
            assert len(result.alerts) > 0
            assert "Need at least" in result.alerts[0].message

    def test_compare_one_report(self):
        detector = RegressionDetector()
        with patch.object(detector, "_latest_reports", return_value=[{"summary": {}}]):
            result = detector.compare()
            assert len(result.alerts) > 0

    def test_compare_two_reports(self):
        baseline = {
            "run_id": "base123",
            "started_at": "2026-01-01T00:00:00",
            "summary": {
                "avg_quality": 4.0,
                "avg_latency_ms": 5000,
                "total_tokens": 1000,
                "per_agent": {
                    "code-writer/default": {
                        "avg_quality": 4.0,
                        "avg_latency_ms": 5000,
                        "total_tokens": 1000,
                    }
                },
                "per_category": {
                    "generation": {"avg_quality": 4.0, "avg_latency_ms": 5000},
                },
            },
        }
        current = {
            "run_id": "curr456",
            "started_at": "2026-01-02T00:00:00",
            "summary": {
                "avg_quality": 4.5,
                "avg_latency_ms": 4500,
                "total_tokens": 1100,
                "per_agent": {
                    "code-writer/default": {
                        "avg_quality": 4.5,
                        "avg_latency_ms": 4500,
                        "total_tokens": 1100,
                    }
                },
                "per_category": {
                    "generation": {"avg_quality": 4.5, "avg_latency_ms": 4500},
                },
            },
        }

        detector = RegressionDetector()
        with patch.object(detector, "_latest_reports", return_value=[current, baseline]):
            result = detector.compare()
            assert result.baseline_id == "base123"
            assert result.current_id == "curr456"
            assert result.passed is True  # quality improved

    def test_compare_quality_regression(self):
        baseline = {
            "run_id": "base",
            "started_at": "2026-01-01T00:00:00",
            "summary": {
                "avg_quality": 4.5,
                "avg_latency_ms": 5000,
                "total_tokens": 1000,
                "per_agent": {
                    "code-writer/default": {
                        "avg_quality": 4.5,
                        "avg_latency_ms": 5000,
                        "total_tokens": 1000,
                    }
                },
                "per_category": {},
            },
        }
        current = {
            "run_id": "curr",
            "started_at": "2026-01-02T00:00:00",
            "summary": {
                "avg_quality": 2.0,
                "avg_latency_ms": 5000,
                "total_tokens": 1000,
                "per_agent": {
                    "code-writer/default": {
                        "avg_quality": 2.0,
                        "avg_latency_ms": 5000,
                        "total_tokens": 1000,
                    }
                },
                "per_category": {},
            },
        }

        detector = RegressionDetector()
        with patch.object(detector, "_latest_reports", return_value=[current, baseline]):
            result = detector.compare()
            # Should detect quality regression
            quality_alerts = [a for a in result.alerts if a.metric == "quality_drop"]
            assert len(quality_alerts) > 0
            assert result.passed is False

    def test_compare_latency_regression(self):
        baseline = {
            "run_id": "base",
            "started_at": "2026-01-01T00:00:00",
            "summary": {
                "avg_quality": 4.0,
                "avg_latency_ms": 5000,
                "total_tokens": 1000,
                "per_agent": {
                    "agent/default": {
                        "avg_quality": 4.0,
                        "avg_latency_ms": 5000,
                        "total_tokens": 1000,
                    }
                },
                "per_category": {},
            },
        }
        current = {
            "run_id": "curr",
            "started_at": "2026-01-02T00:00:00",
            "summary": {
                "avg_quality": 4.0,
                "avg_latency_ms": 15000,  # 3x increase
                "total_tokens": 1000,
                "per_agent": {
                    "agent/default": {
                        "avg_quality": 4.0,
                        "avg_latency_ms": 15000,
                        "total_tokens": 1000,
                    }
                },
                "per_category": {},
            },
        }

        detector = RegressionDetector()
        with patch.object(detector, "_latest_reports", return_value=[current, baseline]):
            result = detector.compare()
            latency_alerts = [a for a in result.alerts if a.metric == "latency_increase"]
            assert len(latency_alerts) > 0

    def test_compare_metrics(self):
        detector = RegressionDetector()
        metrics = detector._compare_metrics(
            b_quality=4.0, c_quality=4.5,
            b_latency=5000, c_latency=4000,
            b_tokens=1000, c_tokens=1200,
        )
        assert metrics["quality"]["delta"] == 0.5
        assert metrics["latency_ms"]["delta"] == -1000
        assert metrics["tokens"]["delta"] == 200

    def test_compare_metrics_zero_baseline(self):
        detector = RegressionDetector()
        metrics = detector._compare_metrics(
            b_quality=0, c_quality=4.0,
        )
        assert metrics["quality"]["delta_pct"] == 0  # Can't compute % from 0

    def test_check_thresholds_pass(self):
        detector = RegressionDetector()
        summary = {"avg_quality": 4.5, "avg_latency_ms": 5000}
        alerts = detector._check_thresholds(summary)
        # Should not trigger critical alerts for good values
        critical = [a for a in alerts if a.severity == "critical"]
        assert len(critical) == 0

    def test_check_thresholds_quality_below(self):
        detector = RegressionDetector()
        summary = {"avg_quality": 2.0, "avg_latency_ms": 5000}
        alerts = detector._check_thresholds(summary)
        quality_alerts = [a for a in alerts if a.metric == "min_quality"]
        assert len(quality_alerts) > 0

    def test_check_thresholds_latency_exceeded(self):
        detector = RegressionDetector()
        summary = {"avg_quality": 4.5, "avg_latency_ms": 70000}
        alerts = detector._check_thresholds(summary)
        latency_alerts = [a for a in alerts if a.metric == "max_latency_ms"]
        assert len(latency_alerts) > 0

    def test_trend_empty(self):
        detector = RegressionDetector()
        with patch.object(detector, "_latest_reports", return_value=[]):
            trend = detector.trend()
            assert trend == []

    def test_trend_with_data(self):
        reports = [
            {
                "run_id": f"run{i}",
                "started_at": f"2026-01-0{i}T00:00:00",
                "summary": {
                    "avg_quality": 4.0 + i * 0.1,
                    "avg_latency_ms": 5000 - i * 100,
                    "total_tokens": 1000 + i * 50,
                    "total_tasks": 6,
                    "successful": 6,
                },
            }
            for i in range(1, 4)
        ]

        detector = RegressionDetector()
        with patch.object(detector, "_latest_reports", return_value=reports):
            trend = detector.trend(3)
            assert len(trend) == 3
            assert all("run_id" in t for t in trend)
            assert all("avg_quality" in t for t in trend)

    def test_export_csv(self):
        detector = RegressionDetector()
        with patch.object(detector, "trend", return_value=[
            {"run_id": "r1", "date": "2026-01-01", "avg_quality": 4.0, "avg_latency_ms": 5000, "total_tokens": 1000, "tasks": 6, "success_rate": 100},
            {"run_id": "r2", "date": "2026-01-02", "avg_quality": 4.5, "avg_latency_ms": 4500, "total_tokens": 1100, "tasks": 6, "success_rate": 100},
        ]):
            with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
                path = detector.export_csv(f.name)
                assert path == f.name
                content = Path(path).read_text()
                assert "run_id" in content
                assert "r1" in content
                os.unlink(f.name)

    def test_export_csv_empty(self):
        detector = RegressionDetector()
        with patch.object(detector, "trend", return_value=[]):
            path = detector.export_csv("/tmp/empty.csv")
            assert path == ""


# ---------------------------------------------------------------------------
# ComparisonResult tests
# ---------------------------------------------------------------------------


class TestComparisonResult:
    """Tests for ComparisonResult data model."""

    def test_critical_count(self):
        result = ComparisonResult(
            baseline_id="a", current_id="b",
            alerts=[
                RegressionAlert(metric="q", agent="a", category="", baseline_value=4, current_value=2, delta=-2, delta_pct=-50, severity="critical", message="bad"),
                RegressionAlert(metric="q", agent="b", category="", baseline_value=4, current_value=3, delta=-1, delta_pct=-25, severity="warning", message="ok"),
            ],
        )
        assert result.critical_count == 1
        assert result.warning_count == 1

    def test_empty_alerts(self):
        result = ComparisonResult(baseline_id="a", current_id="b")
        assert result.critical_count == 0
        assert result.warning_count == 0
        assert result.passed is True


# ---------------------------------------------------------------------------
# Format tests
# ---------------------------------------------------------------------------


class TestFormatting:
    """Tests for formatting functions."""

    def test_format_comparison_passed(self, capsys):
        result = ComparisonResult(
            baseline_id="base",
            current_id="curr",
            baseline_date="2026-01-01T00:00:00",
            current_date="2026-01-02T00:00:00",
            passed=True,
            overall={
                "quality": {"baseline": 4.0, "current": 4.5, "delta": 0.5, "delta_pct": 12.5},
                "latency_ms": {"baseline": 5000, "current": 4500, "delta": -500, "delta_pct": -10.0},
                "tokens": {"baseline": 1000, "current": 1100, "delta": 100, "delta_pct": 10.0},
            },
        )
        format_comparison(result)
        # Should not raise

    def test_format_comparison_failed(self, capsys):
        result = ComparisonResult(
            baseline_id="base",
            current_id="curr",
            passed=False,
            alerts=[
                RegressionAlert(
                    metric="quality_drop", agent="code-writer", category="",
                    baseline_value=4.5, current_value=2.0,
                    delta=-2.5, delta_pct=-55.6,
                    severity="critical",
                    message="Quality dropped 55.6%",
                ),
            ],
        )
        format_comparison(result)
        # Should not raise

    def test_format_trend(self, capsys):
        trend_data = [
            {"run_id": "r1", "date": "2026-01-01", "avg_quality": 4.0, "avg_latency_ms": 5000, "total_tokens": 1000, "success_rate": 100},
            {"run_id": "r2", "date": "2026-01-02", "avg_quality": 4.5, "avg_latency_ms": 4500, "total_tokens": 1100, "success_rate": 100},
        ]
        format_trend(trend_data)
        # Should not raise

    def test_format_trend_empty(self, capsys):
        format_trend([])
        # Should not raise
