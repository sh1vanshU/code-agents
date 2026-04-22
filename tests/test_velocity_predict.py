"""Tests for the sprint velocity predictor."""

from __future__ import annotations

import math
import pytest
from unittest.mock import patch

from code_agents.domain.velocity_predict import VelocityPredictor, VelocityReport


class TestVelocityReport:
    def test_summary(self):
        report = VelocityReport(
            avg_velocity=10.5, predicted_capacity=21,
            committed=25, overcommit=True, trend="stable",
        )
        assert "OVERCOMMITTED" in report.summary()
        assert "10.5" in report.summary()

    def test_summary_ok(self):
        report = VelocityReport(
            avg_velocity=10.0, predicted_capacity=20,
            committed=15, overcommit=False, trend="increasing",
        )
        assert "OK" in report.summary()


class TestEstimateComplexity:
    def test_zero_files(self):
        assert VelocityPredictor._estimate_complexity(0) == 0.5

    def test_one_file(self):
        result = VelocityPredictor._estimate_complexity(1)
        assert result == 1.0

    def test_many_files(self):
        result = VelocityPredictor._estimate_complexity(16)
        assert result > 3.0

    def test_monotonically_increasing(self):
        prev = 0
        for n in [1, 2, 4, 8, 16]:
            curr = VelocityPredictor._estimate_complexity(n)
            assert curr > prev
            prev = curr


class TestWeightedPrediction:
    def test_empty(self):
        assert VelocityPredictor._weighted_prediction([]) == 0.0

    def test_single_value(self):
        assert VelocityPredictor._weighted_prediction([10.0]) == 10.0

    def test_recent_weighted_higher(self):
        # Recent value (20) should pull the average up
        result = VelocityPredictor._weighted_prediction([10.0, 10.0, 10.0, 20.0])
        assert result > 10.0

    def test_constant_values(self):
        result = VelocityPredictor._weighted_prediction([5.0, 5.0, 5.0])
        assert abs(result - 5.0) < 0.01


class TestDetectTrend:
    def test_increasing(self):
        velocities = [5.0, 5.0, 5.0, 10.0, 10.0, 10.0]
        assert VelocityPredictor._detect_trend(velocities) == "increasing"

    def test_decreasing(self):
        velocities = [10.0, 10.0, 10.0, 5.0, 5.0, 5.0]
        assert VelocityPredictor._detect_trend(velocities) == "decreasing"

    def test_stable(self):
        velocities = [10.0, 10.0, 10.0, 10.0, 10.0, 10.0]
        assert VelocityPredictor._detect_trend(velocities) == "stable"

    def test_insufficient_data(self):
        assert VelocityPredictor._detect_trend([5.0, 6.0]) == "insufficient_data"


class TestCalculateConfidence:
    def test_empty(self):
        assert VelocityPredictor._calculate_confidence([]) == 0.0

    def test_single_value(self):
        conf = VelocityPredictor._calculate_confidence([10.0])
        assert 0.0 < conf < 1.0

    def test_consistent_data_higher_confidence(self):
        consistent = VelocityPredictor._calculate_confidence([10.0] * 12)
        inconsistent = VelocityPredictor._calculate_confidence([1.0, 20.0, 3.0, 18.0, 2.0, 19.0])
        assert consistent > inconsistent

    def test_more_data_higher_confidence(self):
        less_data = VelocityPredictor._calculate_confidence([10.0, 10.0])
        more_data = VelocityPredictor._calculate_confidence([10.0] * 12)
        assert more_data >= less_data


class TestParseGitLog:
    def test_parse_empty(self):
        predictor = VelocityPredictor(cwd="/fake")
        result = predictor._parse_git_log("")
        assert result == []

    def test_parse_single_commit(self):
        predictor = VelocityPredictor(cwd="/fake")
        output = "abc123|2026-01-15T10:00:00+00:00|Fix bug\n 2 files changed, 10 insertions(+), 5 deletions(-)\n"
        result = predictor._parse_git_log(output)
        assert len(result) >= 1
        assert result[0]["commits"] == 1
        assert result[0]["velocity"] > 0

    def test_parse_multiple_weeks(self):
        predictor = VelocityPredictor(cwd="/fake")
        output = (
            "abc123|2026-01-01T10:00:00+00:00|Commit 1\n 1 files changed, 5 insertions(+)\n"
            "def456|2026-01-15T10:00:00+00:00|Commit 2\n 3 files changed, 20 insertions(+), 10 deletions(-)\n"
        )
        result = predictor._parse_git_log(output)
        assert len(result) >= 1


class TestPredict:
    @patch.object(VelocityPredictor, "_get_historical")
    def test_predict_basic(self, mock_hist):
        mock_hist.return_value = [
            {"week": "2026-W01", "commits": 5, "velocity": 10.0, "avg_complexity": 2.0},
            {"week": "2026-W02", "commits": 6, "velocity": 12.0, "avg_complexity": 2.0},
            {"week": "2026-W03", "commits": 5, "velocity": 11.0, "avg_complexity": 2.2},
        ]
        predictor = VelocityPredictor(cwd="/fake")
        report = predictor.predict(committed_points=20)
        assert report.avg_velocity > 0
        assert report.predicted_capacity > 0
        assert isinstance(report.overcommit, bool)

    @patch.object(VelocityPredictor, "_get_historical")
    def test_predict_overcommit(self, mock_hist):
        mock_hist.return_value = [
            {"week": f"2026-W{i:02d}", "commits": 3, "velocity": 5.0, "avg_complexity": 1.5}
            for i in range(1, 7)
        ]
        predictor = VelocityPredictor(cwd="/fake")
        report = predictor.predict(committed_points=999)
        assert report.overcommit is True

    @patch.object(VelocityPredictor, "_get_historical")
    def test_predict_no_history(self, mock_hist):
        mock_hist.return_value = []
        predictor = VelocityPredictor(cwd="/fake")
        report = predictor.predict()
        assert report.avg_velocity == 0.0
        assert report.predicted_capacity == 0
        assert report.trend == "unknown"
