"""Tests for benchmark — agent benchmarking with quality scoring."""

import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from code_agents.testing.benchmark import (
    DEFAULT_TASKS,
    BenchmarkReport,
    BenchmarkResult,
    BenchmarkRunner,
    _build_judge_prompt,
)


# ---------------------------------------------------------------------------
# Data model tests
# ---------------------------------------------------------------------------


class TestBenchmarkResult:
    """Tests for BenchmarkResult dataclass."""

    def test_defaults(self):
        r = BenchmarkResult(task_id="t1", task_name="Test", category="gen", agent="code-writer", backend="cursor", model="auto")
        assert r.task_id == "t1"
        assert r.quality_score == 0
        assert r.error == ""
        assert r.latency_ms == 0

    def test_with_values(self):
        r = BenchmarkResult(
            task_id="t2", task_name="Review", category="review",
            agent="code-reviewer", backend="claude", model="sonnet",
            response="looks good", latency_ms=1500, quality_score=4,
        )
        assert r.quality_score == 4
        assert r.latency_ms == 1500


class TestBenchmarkReport:
    """Tests for BenchmarkReport dataclass."""

    def test_defaults(self):
        r = BenchmarkReport()
        assert r.results == []
        assert r.summary == {}

    def test_with_results(self):
        results = [
            BenchmarkResult(task_id="t1", task_name="T1", category="gen", agent="a", backend="b", model="m", quality_score=4, latency_ms=100),
        ]
        r = BenchmarkReport(run_id="r1", results=results)
        assert len(r.results) == 1


# ---------------------------------------------------------------------------
# Default tasks
# ---------------------------------------------------------------------------


class TestDefaultTasks:
    """Tests for built-in benchmark tasks."""

    def test_tasks_not_empty(self):
        assert len(DEFAULT_TASKS) > 0

    def test_task_structure(self):
        for task in DEFAULT_TASKS:
            assert "id" in task
            assert "name" in task
            assert "category" in task
            assert "prompt" in task
            assert "judge_criteria" in task

    def test_task_ids_unique(self):
        ids = [t["id"] for t in DEFAULT_TASKS]
        assert len(ids) == len(set(ids))

    def test_categories_valid(self):
        valid = {"generation", "review", "explanation", "refactoring", "debugging"}
        for task in DEFAULT_TASKS:
            assert task["category"] in valid


# ---------------------------------------------------------------------------
# Judge prompt
# ---------------------------------------------------------------------------


class TestJudgePrompt:
    """Tests for judge prompt building."""

    def test_build_judge_prompt(self):
        task = DEFAULT_TASKS[0]
        response = "def fizzbuzz(n): pass"
        prompt = _build_judge_prompt(task, response)
        assert "1-5" in prompt
        assert task["prompt"] in prompt
        assert response in prompt
        assert task["judge_criteria"] in prompt

    def test_judge_prompt_contains_scoring(self):
        prompt = _build_judge_prompt(DEFAULT_TASKS[0], "test")
        assert "Excellent" in prompt
        assert "Wrong" in prompt


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------


class TestBenchmarkRunner:
    """Tests for BenchmarkRunner."""

    def test_init_defaults(self):
        runner = BenchmarkRunner()
        assert runner.agents == ["code-writer"]
        assert runner.models == []
        assert runner.tasks == DEFAULT_TASKS
        assert runner.judge is True

    def test_init_custom(self):
        runner = BenchmarkRunner(
            agents=["code-reviewer", "security"],
            models=["sonnet", "opus"],
            tasks=[DEFAULT_TASKS[0]],
            judge=False,
        )
        assert runner.agents == ["code-reviewer", "security"]
        assert runner.models == ["sonnet", "opus"]
        assert len(runner.tasks) == 1
        assert runner.judge is False

    def test_summarize_empty(self):
        runner = BenchmarkRunner()
        assert runner._summarize([]) == {}

    def test_summarize_valid(self):
        runner = BenchmarkRunner()
        results = [
            BenchmarkResult(task_id="t1", task_name="T1", category="gen", agent="a", backend="b", model="m", quality_score=4, latency_ms=100, input_tokens=50, output_tokens=100),
            BenchmarkResult(task_id="t2", task_name="T2", category="review", agent="a", backend="b", model="m", quality_score=3, latency_ms=200, input_tokens=60, output_tokens=80),
        ]
        s = runner._summarize(results)
        assert s["total_tasks"] == 2
        assert s["successful"] == 2
        assert s["failed"] == 0
        assert s["avg_latency_ms"] == 150
        assert s["avg_quality"] == 3.5
        assert s["total_tokens"] == 290
        assert "per_agent" in s
        assert "per_category" in s

    def test_summarize_with_errors(self):
        runner = BenchmarkRunner()
        results = [
            BenchmarkResult(task_id="t1", task_name="T1", category="gen", agent="a", backend="b", model="m", quality_score=5, latency_ms=100, input_tokens=50, output_tokens=100),
            BenchmarkResult(task_id="t2", task_name="T2", category="gen", agent="a", backend="b", model="m", error="timeout"),
        ]
        s = runner._summarize(results)
        assert s["successful"] == 1
        assert s["failed"] == 1
        assert s["avg_quality"] == 5.0

    def test_summarize_per_agent(self):
        runner = BenchmarkRunner()
        results = [
            BenchmarkResult(task_id="t1", task_name="T1", category="gen", agent="writer", backend="b", model="m1", quality_score=5, latency_ms=100, input_tokens=10, output_tokens=10),
            BenchmarkResult(task_id="t2", task_name="T2", category="gen", agent="reviewer", backend="b", model="m2", quality_score=3, latency_ms=200, input_tokens=20, output_tokens=20),
        ]
        s = runner._summarize(results)
        assert "writer/m1" in s["per_agent"]
        assert "reviewer/m2" in s["per_agent"]
        assert s["per_agent"]["writer/m1"]["avg_quality"] == 5.0
        assert s["per_agent"]["reviewer/m2"]["avg_quality"] == 3.0

    def test_summarize_per_category(self):
        runner = BenchmarkRunner()
        results = [
            BenchmarkResult(task_id="t1", task_name="T1", category="generation", agent="a", backend="b", model="m", quality_score=4, latency_ms=100),
            BenchmarkResult(task_id="t2", task_name="T2", category="generation", agent="a", backend="b", model="m", quality_score=5, latency_ms=150),
            BenchmarkResult(task_id="t3", task_name="T3", category="review", agent="a", backend="b", model="m", quality_score=3, latency_ms=200),
        ]
        s = runner._summarize(results)
        assert s["per_category"]["generation"]["avg_quality"] == 4.5
        assert s["per_category"]["review"]["avg_quality"] == 3.0


class TestBenchmarkPersistence:
    """Tests for saving/loading benchmark reports."""

    def test_save_and_load(self, tmp_path):
        with patch("code_agents.testing.benchmark.BENCHMARKS_DIR", tmp_path):
            runner = BenchmarkRunner()
            report = BenchmarkReport(
                run_id="test123",
                started_at="2026-01-01T00:00:00",
                finished_at="2026-01-01T00:01:00",
                summary={"total_tasks": 1},
                results=[
                    BenchmarkResult(task_id="t1", task_name="T1", category="gen", agent="a", backend="b", model="m"),
                ],
            )
            path = runner.save_report(report)
            assert path.exists()

            loaded = BenchmarkRunner.load_report(path)
            assert loaded["run_id"] == "test123"
            assert len(loaded["results"]) == 1

    def test_list_reports(self, tmp_path):
        with patch("code_agents.testing.benchmark.BENCHMARKS_DIR", tmp_path):
            runner = BenchmarkRunner()
            for i in range(3):
                report = BenchmarkReport(run_id=f"run{i}", summary={"avg_quality": i})
                runner.save_report(report)

            reports = BenchmarkRunner.list_reports()
            assert len(reports) == 3

    def test_list_reports_empty(self, tmp_path):
        with patch("code_agents.testing.benchmark.BENCHMARKS_DIR", tmp_path / "nonexistent"):
            reports = BenchmarkRunner.list_reports()
            assert reports == []


class TestBenchmarkPrint:
    """Tests for print_report (coverage for both rich and fallback)."""

    def test_print_report_fallback(self, capsys):
        with patch.dict("sys.modules", {"rich": None, "rich.console": None, "rich.table": None, "rich.panel": None}):
            report = BenchmarkReport(
                run_id="test",
                summary={"total_tasks": 1, "successful": 1, "avg_quality": 4, "avg_latency_ms": 100},
                results=[
                    BenchmarkResult(task_id="t1", task_name="FizzBuzz", category="gen", agent="writer", backend="b", model="m", quality_score=4, latency_ms=100),
                ],
            )
            BenchmarkRunner.print_report(report)
            out = capsys.readouterr().out
            assert "test" in out or "FizzBuzz" in out
