"""Performance Profiling with Proof — benchmark commands and prove optimizations.

Run a command N times, collect timing stats, then compare before/after to
statistically prove an optimization actually works.
"""

from __future__ import annotations

import logging
import math
import os
import subprocess
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger("code_agents.testing.perf_proof")


@dataclass
class TimingStats:
    """Statistical summary of timing measurements."""

    times: list[float]
    mean: float = 0.0
    median: float = 0.0
    std_dev: float = 0.0
    min_time: float = 0.0
    max_time: float = 0.0

    def __post_init__(self):
        if self.times:
            self.mean = sum(self.times) / len(self.times)
            sorted_t = sorted(self.times)
            n = len(sorted_t)
            self.median = sorted_t[n // 2] if n % 2 else (sorted_t[n // 2 - 1] + sorted_t[n // 2]) / 2
            self.min_time = sorted_t[0]
            self.max_time = sorted_t[-1]
            if n > 1:
                variance = sum((t - self.mean) ** 2 for t in self.times) / (n - 1)
                self.std_dev = math.sqrt(variance)

    def to_dict(self) -> dict:
        return {
            "times": self.times,
            "mean": round(self.mean, 4),
            "median": round(self.median, 4),
            "std_dev": round(self.std_dev, 4),
            "min": round(self.min_time, 4),
            "max": round(self.max_time, 4),
            "iterations": len(self.times),
        }


@dataclass
class BenchmarkResult:
    """Result of a single benchmark run."""

    command: str
    iterations: int
    stats: TimingStats
    exit_codes: list[int] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "command": self.command,
            "iterations": self.iterations,
            "stats": self.stats.to_dict(),
            "exit_codes": self.exit_codes,
            "all_passed": all(c == 0 for c in self.exit_codes),
            "error": self.error,
        }

    def summary(self) -> str:
        if self.error:
            return f"Benchmark failed: {self.error}"
        s = self.stats
        return (
            f"Command: {self.command}\n"
            f"Iterations: {self.iterations}\n"
            f"Mean: {s.mean:.4f}s | Median: {s.median:.4f}s | StdDev: {s.std_dev:.4f}s\n"
            f"Min: {s.min_time:.4f}s | Max: {s.max_time:.4f}s\n"
            f"All passed: {all(c == 0 for c in self.exit_codes)}"
        )


@dataclass
class ProofResult:
    """Result of a before/after optimization proof."""

    command: str
    before: TimingStats
    after: TimingStats
    comparison: dict = field(default_factory=dict)
    proof_text: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "command": self.command,
            "before": self.before.to_dict(),
            "after": self.after.to_dict(),
            "comparison": self.comparison,
            "proof_text": self.proof_text,
            "error": self.error,
        }


class PerfProver:
    """Benchmark commands and statistically prove optimizations."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        logger.debug("PerfProver initialized for %s", cwd)

    def benchmark(self, command: str, iterations: int = 3) -> BenchmarkResult:
        """Benchmark a command by running it N times and collecting timing stats.

        Args:
            command: Shell command to benchmark.
            iterations: Number of times to run (default 3).

        Returns:
            BenchmarkResult with timing statistics.
        """
        if iterations < 1:
            iterations = 1
        if iterations > 100:
            iterations = 100

        logger.info("Benchmarking '%s' (%d iterations)", command, iterations)

        times = self._run_timed(command, iterations)
        if isinstance(times, str):
            # Error string
            return BenchmarkResult(
                command=command, iterations=iterations,
                stats=TimingStats(times=[]),
                error=times,
            )

        timings, exit_codes = times
        stats = TimingStats(times=timings)

        result = BenchmarkResult(
            command=command,
            iterations=iterations,
            stats=stats,
            exit_codes=exit_codes,
        )
        logger.info("Benchmark complete: mean=%.4fs, median=%.4fs", stats.mean, stats.median)
        return result

    def prove_optimization(
        self,
        command: str,
        optimization_fn: Callable[[], None],
        iterations: int = 3,
    ) -> ProofResult:
        """Prove an optimization by benchmarking before/after.

        Args:
            command: Shell command to benchmark.
            optimization_fn: Callable that applies the optimization.
            iterations: Number of iterations for each benchmark.

        Returns:
            ProofResult with statistical comparison.
        """
        logger.info("Starting optimization proof for '%s'", command)

        # Before
        before_result = self._run_timed(command, iterations)
        if isinstance(before_result, str):
            return ProofResult(
                command=command,
                before=TimingStats(times=[]),
                after=TimingStats(times=[]),
                error=f"Before benchmark failed: {before_result}",
            )
        before_times, _ = before_result
        before_stats = TimingStats(times=before_times)

        # Apply optimization
        try:
            optimization_fn()
        except Exception as exc:
            return ProofResult(
                command=command,
                before=before_stats,
                after=TimingStats(times=[]),
                error=f"Optimization function failed: {exc}",
            )

        # After
        after_result = self._run_timed(command, iterations)
        if isinstance(after_result, str):
            return ProofResult(
                command=command,
                before=before_stats,
                after=TimingStats(times=[]),
                error=f"After benchmark failed: {after_result}",
            )
        after_times, _ = after_result
        after_stats = TimingStats(times=after_times)

        # Statistical comparison
        comparison = self._statistical_comparison(before_times, after_times)
        proof_text = self._format_proof(before_stats, after_stats, comparison)

        result = ProofResult(
            command=command,
            before=before_stats,
            after=after_stats,
            comparison=comparison,
            proof_text=proof_text,
        )
        logger.info("Proof complete: speedup=%.2fx", comparison.get("speedup", 0))
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_timed(
        self, command: str, iterations: int
    ) -> tuple[list[float], list[int]] | str:
        """Run a command N times and collect wall-clock times.

        Returns (timings, exit_codes) or an error string.
        """
        timings: list[float] = []
        exit_codes: list[int] = []

        for i in range(iterations):
            try:
                start = time.perf_counter()
                result = subprocess.run(
                    command, shell=True,
                    capture_output=True, text=True,
                    cwd=self.cwd, timeout=300,
                )
                elapsed = time.perf_counter() - start
                timings.append(elapsed)
                exit_codes.append(result.returncode)
                logger.debug("Iteration %d/%d: %.4fs (exit=%d)", i + 1, iterations, elapsed, result.returncode)
            except subprocess.TimeoutExpired:
                return f"Command timed out (>300s) on iteration {i + 1}"
            except OSError as exc:
                return f"OS error on iteration {i + 1}: {exc}"

        return timings, exit_codes

    def _statistical_comparison(self, before: list[float], after: list[float]) -> dict:
        """Compare two sets of timing measurements.

        Returns dict with mean_diff, speedup, percent_change, and a simple
        p-value proxy using the overlap of confidence intervals.
        """
        if not before or not after:
            return {"error": "insufficient data"}

        before_stats = TimingStats(times=before)
        after_stats = TimingStats(times=after)

        mean_diff = before_stats.mean - after_stats.mean
        speedup = before_stats.mean / after_stats.mean if after_stats.mean > 0 else float("inf")
        pct_change = (mean_diff / before_stats.mean * 100) if before_stats.mean > 0 else 0.0

        # Simple p-value proxy: non-overlapping means +/- 1 std dev => likely significant
        # This is a heuristic, not a real statistical test
        before_upper = before_stats.mean + before_stats.std_dev
        after_lower = after_stats.mean - after_stats.std_dev
        before_lower = before_stats.mean - before_stats.std_dev
        after_upper = after_stats.mean + after_stats.std_dev

        if before_lower > after_upper:
            confidence = "high"
        elif before_stats.mean > after_stats.mean + after_stats.std_dev:
            confidence = "medium"
        elif mean_diff > 0:
            confidence = "low"
        else:
            confidence = "none (no improvement)"

        # Welch's t-test approximation for p-value proxy
        n_b, n_a = len(before), len(after)
        if before_stats.std_dev > 0 or after_stats.std_dev > 0:
            se = math.sqrt(
                (before_stats.std_dev ** 2 / n_b) + (after_stats.std_dev ** 2 / n_a)
            ) if n_b > 0 and n_a > 0 else 0
            t_stat = mean_diff / se if se > 0 else 0
        else:
            t_stat = float("inf") if mean_diff > 0 else 0

        return {
            "mean_diff": round(mean_diff, 4),
            "speedup": round(speedup, 2),
            "percent_change": round(pct_change, 2),
            "confidence": confidence,
            "t_statistic": round(t_stat, 3),
            "before_mean": round(before_stats.mean, 4),
            "after_mean": round(after_stats.mean, 4),
        }

    def _format_proof(
        self, before: TimingStats, after: TimingStats, comparison: dict
    ) -> str:
        """Format a human-readable proof of optimization."""
        lines: list[str] = []
        lines.append("Performance Proof")
        lines.append("=" * 50)
        lines.append("")
        lines.append("Before optimization:")
        lines.append(f"  Mean: {before.mean:.4f}s | Median: {before.median:.4f}s | StdDev: {before.std_dev:.4f}s")
        lines.append(f"  Range: {before.min_time:.4f}s — {before.max_time:.4f}s ({len(before.times)} runs)")
        lines.append("")
        lines.append("After optimization:")
        lines.append(f"  Mean: {after.mean:.4f}s | Median: {after.median:.4f}s | StdDev: {after.std_dev:.4f}s")
        lines.append(f"  Range: {after.min_time:.4f}s — {after.max_time:.4f}s ({len(after.times)} runs)")
        lines.append("")
        lines.append("Comparison:")

        speedup = comparison.get("speedup", 0)
        pct = comparison.get("percent_change", 0)
        conf = comparison.get("confidence", "unknown")

        if speedup > 1:
            lines.append(f"  Speedup:  {speedup:.2f}x faster")
            lines.append(f"  Change:   {pct:.1f}% improvement")
        elif speedup < 1:
            lines.append(f"  Slowdown: {1/speedup:.2f}x slower")
            lines.append(f"  Change:   {abs(pct):.1f}% regression")
        else:
            lines.append("  No measurable change")

        lines.append(f"  Confidence: {conf}")
        lines.append("")

        if speedup >= 1.5 and conf in ("high", "medium"):
            lines.append("VERDICT: Optimization PROVEN effective.")
        elif speedup >= 1.1:
            lines.append("VERDICT: Marginal improvement, more iterations recommended.")
        elif speedup < 1.0:
            lines.append("VERDICT: REGRESSION detected — optimization is harmful.")
        else:
            lines.append("VERDICT: No significant difference detected.")

        return "\n".join(lines)


def format_benchmark_rich(result: BenchmarkResult) -> str:
    """Format a benchmark result with terminal colors."""
    lines: list[str] = []
    lines.append(f"\n  \033[1mPerformance Benchmark\033[0m")
    lines.append(f"  Command: {result.command}")
    lines.append(f"  Iterations: {result.iterations}")
    lines.append("")

    if result.error:
        lines.append(f"  \033[31mError: {result.error}\033[0m")
        return "\n".join(lines)

    s = result.stats
    lines.append(f"  \033[36mTiming\033[0m")
    lines.append(f"    Mean:   {s.mean:.4f}s")
    lines.append(f"    Median: {s.median:.4f}s")
    lines.append(f"    StdDev: {s.std_dev:.4f}s")
    lines.append(f"    Min:    {s.min_time:.4f}s")
    lines.append(f"    Max:    {s.max_time:.4f}s")
    lines.append("")

    passed = all(c == 0 for c in result.exit_codes)
    status = "\033[32mAll passed\033[0m" if passed else "\033[31mSome failed\033[0m"
    lines.append(f"  Exit codes: {result.exit_codes} — {status}")
    lines.append("")
    return "\n".join(lines)
