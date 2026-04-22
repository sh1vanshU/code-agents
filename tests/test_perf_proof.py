"""Tests for the Performance Profiling with Proof module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from code_agents.testing.perf_proof import (
    BenchmarkResult,
    PerfProver,
    ProofResult,
    TimingStats,
    format_benchmark_rich,
)


class TestTimingStats:
    """Test TimingStats calculations."""

    def test_empty(self):
        s = TimingStats(times=[])
        assert s.mean == 0.0
        assert s.median == 0.0
        assert s.std_dev == 0.0

    def test_single_value(self):
        s = TimingStats(times=[1.5])
        assert s.mean == 1.5
        assert s.median == 1.5
        assert s.min_time == 1.5
        assert s.max_time == 1.5
        assert s.std_dev == 0.0

    def test_multiple_values(self):
        s = TimingStats(times=[1.0, 2.0, 3.0])
        assert s.mean == 2.0
        assert s.median == 2.0
        assert s.min_time == 1.0
        assert s.max_time == 3.0
        assert s.std_dev > 0

    def test_even_count_median(self):
        s = TimingStats(times=[1.0, 2.0, 3.0, 4.0])
        assert s.median == 2.5  # Average of 2.0 and 3.0

    def test_to_dict(self):
        s = TimingStats(times=[1.0, 2.0])
        d = s.to_dict()
        assert "mean" in d
        assert "median" in d
        assert "std_dev" in d
        assert d["iterations"] == 2


class TestBenchmarkResult:
    """Test BenchmarkResult dataclass."""

    def test_to_dict(self):
        r = BenchmarkResult(
            command="echo test", iterations=3,
            stats=TimingStats(times=[0.1, 0.2, 0.15]),
            exit_codes=[0, 0, 0],
        )
        d = r.to_dict()
        assert d["command"] == "echo test"
        assert d["all_passed"] is True
        assert d["iterations"] == 3

    def test_summary_with_error(self):
        r = BenchmarkResult(
            command="fail", iterations=1,
            stats=TimingStats(times=[]),
            error="Command timed out",
        )
        s = r.summary()
        assert "failed" in s.lower() or "timed out" in s.lower()

    def test_summary_success(self):
        r = BenchmarkResult(
            command="echo ok", iterations=3,
            stats=TimingStats(times=[0.1, 0.2, 0.15]),
            exit_codes=[0, 0, 0],
        )
        s = r.summary()
        assert "echo ok" in s
        assert "Mean" in s


class TestPerfProver:
    """Test PerfProver methods."""

    @pytest.fixture
    def prover(self, tmp_path):
        return PerfProver(cwd=str(tmp_path))

    @patch("code_agents.testing.perf_proof.subprocess.run")
    def test_benchmark_success(self, mock_run, prover):
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        result = prover.benchmark("echo test", iterations=2)
        assert result.error == ""
        assert len(result.stats.times) == 2
        assert all(c == 0 for c in result.exit_codes)

    @patch("code_agents.testing.perf_proof.subprocess.run")
    def test_benchmark_command_fails(self, mock_run, prover):
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="error")
        result = prover.benchmark("false", iterations=2)
        assert len(result.stats.times) == 2
        assert all(c == 1 for c in result.exit_codes)

    @patch("code_agents.testing.perf_proof.subprocess.run")
    def test_benchmark_timeout(self, mock_run, prover):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 300)
        result = prover.benchmark("sleep 999", iterations=1)
        assert "timed out" in result.error.lower()

    def test_benchmark_clamps_iterations(self, prover):
        with patch("code_agents.testing.perf_proof.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            # Negative iterations -> clamped to 1
            result = prover.benchmark("echo", iterations=-5)
            assert result.iterations == 1

    def test_statistical_comparison_faster(self, prover):
        before = [2.0, 2.1, 1.9]
        after = [1.0, 1.1, 0.9]
        comp = prover._statistical_comparison(before, after)
        assert comp["speedup"] > 1
        assert comp["percent_change"] > 0

    def test_statistical_comparison_slower(self, prover):
        before = [1.0, 1.1, 0.9]
        after = [2.0, 2.1, 1.9]
        comp = prover._statistical_comparison(before, after)
        assert comp["speedup"] < 1

    def test_statistical_comparison_empty(self, prover):
        comp = prover._statistical_comparison([], [1.0])
        assert "error" in comp

    def test_format_proof_faster(self, prover):
        before = TimingStats(times=[2.0, 2.1, 1.9])
        after = TimingStats(times=[1.0, 1.1, 0.9])
        comp = {"speedup": 2.0, "percent_change": 50.0, "confidence": "high"}
        text = prover._format_proof(before, after, comp)
        assert "faster" in text.lower()
        assert "PROVEN" in text

    def test_format_proof_regression(self, prover):
        before = TimingStats(times=[1.0])
        after = TimingStats(times=[2.0])
        comp = {"speedup": 0.5, "percent_change": -50.0, "confidence": "none"}
        text = prover._format_proof(before, after, comp)
        assert "REGRESSION" in text

    @patch("code_agents.testing.perf_proof.subprocess.run")
    def test_prove_optimization(self, mock_run, prover):
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
        result = prover.prove_optimization(
            "echo test",
            optimization_fn=lambda: None,
            iterations=2,
        )
        assert result.error == ""
        assert len(result.before.times) == 2
        assert len(result.after.times) == 2
        assert result.proof_text != ""


class TestFormatBenchmarkRich:
    """Test rich formatting of benchmark results."""

    def test_format_success(self):
        r = BenchmarkResult(
            command="echo ok", iterations=3,
            stats=TimingStats(times=[0.1, 0.2, 0.15]),
            exit_codes=[0, 0, 0],
        )
        output = format_benchmark_rich(r)
        assert "echo ok" in output
        assert "Mean" in output

    def test_format_error(self):
        r = BenchmarkResult(
            command="fail", iterations=1,
            stats=TimingStats(times=[]),
            error="Timeout",
        )
        output = format_benchmark_rich(r)
        assert "Timeout" in output
