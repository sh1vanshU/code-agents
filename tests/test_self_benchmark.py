"""Tests for the Self-Benchmarking module."""

from __future__ import annotations

import json
import os
from unittest.mock import patch

import pytest

from code_agents.testing.self_benchmark import (
    BenchmarkReport,
    SelfBenchmark,
    TaskScore,
    format_report_rich,
    format_trend_rich,
    _progress_bar,
)


class TestTaskScore:
    """Test TaskScore dataclass."""

    def test_to_dict(self):
        ts = TaskScore(task_name="review", score=0.8, duration_ms=50)
        d = ts.to_dict()
        assert d["task"] == "review"
        assert d["score"] == 0.8
        assert d["percentage"] == 80.0

    def test_zero_max(self):
        ts = TaskScore(task_name="x", score=0.0, max_score=0.0)
        d = ts.to_dict()
        assert d["percentage"] == 0


class TestBenchmarkReport:
    """Test BenchmarkReport dataclass."""

    def test_empty_report(self):
        report = BenchmarkReport()
        assert report.total_score == 0.0
        assert report.max_possible == 0.0
        assert report.percentage == 0.0

    def test_report_with_tasks(self):
        report = BenchmarkReport(tasks=[
            TaskScore(task_name="review", score=0.8),
            TaskScore(task_name="test", score=0.6),
        ])
        assert report.total_score == pytest.approx(1.4)
        assert report.max_possible == 2.0
        assert report.percentage == 70.0

    def test_to_dict(self):
        report = BenchmarkReport(tasks=[
            TaskScore(task_name="review", score=1.0),
        ])
        d = report.to_dict()
        assert "tasks" in d
        assert "overall_score" in d
        assert d["overall_score"] == 100.0

    def test_summary(self):
        report = BenchmarkReport(tasks=[
            TaskScore(task_name="review", score=0.8, details="Found 3 issues"),
        ])
        s = report.summary()
        assert "review" in s
        assert "80" in s


class TestSelfBenchmark:
    """Test SelfBenchmark task runner."""

    @pytest.fixture
    def bench(self, tmp_path):
        return SelfBenchmark(cwd=str(tmp_path))

    def test_run_all_tasks(self, bench):
        report = bench.run()
        assert len(report.tasks) == 3
        task_names = {t.task_name for t in report.tasks}
        assert task_names == {"review", "test", "bug"}

    def test_run_specific_tasks(self, bench):
        report = bench.run(tasks=["review"])
        assert len(report.tasks) == 1
        assert report.tasks[0].task_name == "review"

    def test_run_unknown_task(self, bench):
        report = bench.run(tasks=["nonexistent"])
        assert len(report.tasks) == 0

    def test_task_code_review(self, bench):
        score = bench._task_code_review()
        assert score.task_name == "review"
        assert 0.0 <= score.score <= 1.0
        assert score.score > 0  # Should find at least some issues
        assert score.duration_ms >= 0

    def test_task_test_generation(self, bench):
        score = bench._task_test_generation()
        assert score.task_name == "test"
        assert 0.0 <= score.score <= 1.0
        assert score.score > 0

    def test_task_bug_detection(self, bench):
        score = bench._task_bug_detection()
        assert score.task_name == "bug"
        assert 0.0 <= score.score <= 1.0
        assert score.score > 0

    def test_score_output_exact_match(self, bench):
        assert bench._score_output({"a", "b"}, {"a", "b"}) == 1.0

    def test_score_output_partial(self, bench):
        assert bench._score_output({"a", "b", "c"}, {"a"}) == pytest.approx(1 / 3)

    def test_score_output_empty(self, bench):
        assert bench._score_output(set(), set()) == 1.0
        assert bench._score_output({"a"}, set()) == 0.0

    def test_save_result(self, bench, tmp_path):
        report = bench.run(tasks=["review"])
        with patch("code_agents.testing.self_benchmark.BENCHMARKS_DIR", str(tmp_path / "bench")):
            filepath = bench.save_result(report)
            assert os.path.isfile(filepath)
            with open(filepath) as f:
                data = json.load(f)
            assert "tasks" in data

    def test_trend_empty(self, bench):
        with patch("code_agents.testing.self_benchmark.BENCHMARKS_DIR", "/nonexistent/path"):
            result = bench.trend()
            assert result == []

    def test_trend_with_data(self, bench, tmp_path):
        bench_dir = tmp_path / "bench"
        bench_dir.mkdir()
        (bench_dir / "bench_20250101_120000.json").write_text(
            json.dumps({"timestamp": "2025-01-01T12:00:00", "overall_score": 75.0, "tasks": []})
        )
        with patch("code_agents.testing.self_benchmark.BENCHMARKS_DIR", str(bench_dir)):
            result = bench.trend()
            assert len(result) == 1
            assert result[0]["overall_score"] == 75.0


class TestProgressBar:
    """Test progress bar helper."""

    def test_full(self):
        bar = _progress_bar(100)
        assert "#" * 20 in bar

    def test_empty(self):
        bar = _progress_bar(0)
        assert "-" * 20 in bar

    def test_half(self):
        bar = _progress_bar(50)
        assert "#" * 10 in bar


class TestFormatting:
    """Test rich formatting functions."""

    def test_format_report_rich(self):
        report = BenchmarkReport(tasks=[
            TaskScore(task_name="review", score=0.8, details="Found 3 issues", duration_ms=50),
        ])
        output = format_report_rich(report)
        assert "Self-Benchmark" in output
        assert "review" in output

    def test_format_trend_rich_empty(self):
        output = format_trend_rich([])
        assert "No benchmark history" in output

    def test_format_trend_rich_with_data(self):
        data = [
            {"timestamp": "2025-01-01T12:00:00", "overall_score": 75.0},
            {"timestamp": "2025-01-02T12:00:00", "overall_score": 82.0},
        ]
        output = format_trend_rich(data)
        assert "Benchmark Trend" in output
        assert "2 runs" in output
