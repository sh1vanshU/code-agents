"""Tests for velocity_anomaly.py — team slowdown detection."""

import pytest

from code_agents.domain.velocity_anomaly import (
    VelocityAnomalyDetector,
    VelocityReport,
    Anomaly,
    format_report,
)


@pytest.fixture
def detector():
    return VelocityAnomalyDetector(threshold_pct=25.0)


SAMPLE_METRICS = [
    {"period": "Sprint 1", "commits": 50, "prs_merged": 10, "bugs_filed": 3,
     "ci_failures": 2, "incidents": 0, "story_points_completed": 30,
     "avg_pr_time_hours": 4},
    {"period": "Sprint 2", "commits": 48, "prs_merged": 9, "bugs_filed": 4,
     "ci_failures": 3, "incidents": 1, "story_points_completed": 28,
     "avg_pr_time_hours": 5},
    {"period": "Sprint 3", "commits": 20, "prs_merged": 4, "bugs_filed": 10,
     "ci_failures": 8, "incidents": 3, "story_points_completed": 15,
     "avg_pr_time_hours": 12},
]


class TestTrend:
    def test_declining_trend(self, detector):
        sprints = [detector._parse_metrics(m) for m in SAMPLE_METRICS]
        trend = detector._compute_trend(sprints)
        assert trend == "declining"

    def test_stable_trend(self, detector):
        stable = [{"period": f"S{i}", "story_points_completed": 30} for i in range(3)]
        sprints = [detector._parse_metrics(m) for m in stable]
        trend = detector._compute_trend(sprints)
        assert trend == "stable"


class TestDetectAnomalies:
    def test_detects_commit_drop(self, detector):
        sprints = [detector._parse_metrics(m) for m in SAMPLE_METRICS]
        values = [s.commits for s in sprints]
        anomalies = detector._detect_anomalies("commits", sprints, values)
        assert len(anomalies) >= 1

    def test_detects_bug_spike(self, detector):
        sprints = [detector._parse_metrics(m) for m in SAMPLE_METRICS]
        values = [s.bugs_filed for s in sprints]
        anomalies = detector._detect_anomalies("bugs_filed", sprints, values)
        assert len(anomalies) >= 1


class TestAnalyze:
    def test_full_analysis(self, detector):
        report = detector.analyze(SAMPLE_METRICS)
        assert isinstance(report, VelocityReport)
        assert report.periods_analyzed == 3
        assert len(report.anomalies) >= 1

    def test_health_score(self, detector):
        report = detector.analyze(SAMPLE_METRICS)
        assert 0 <= report.health_score <= 100

    def test_too_few_periods(self, detector):
        report = detector.analyze([SAMPLE_METRICS[0]])
        assert "Need at least" in report.warnings[0]

    def test_format_report(self, detector):
        report = detector.analyze(SAMPLE_METRICS)
        text = format_report(report)
        assert "Velocity" in text
