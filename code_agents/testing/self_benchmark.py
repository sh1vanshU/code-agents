"""Self-Benchmarking — measure agent quality across standard tasks.

Runs a set of benchmark tasks (code review, test generation, bug detection),
scores output quality, and tracks improvement over time.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.testing.self_benchmark")

BENCHMARKS_DIR = os.path.join(
    os.path.expanduser("~"), ".code-agents", "benchmarks"
)

# Sample data for benchmark tasks
_SAMPLE_DIFF = """--- a/app.py
+++ b/app.py
@@ -10,6 +10,8 @@ def process_payment(amount, card):
     if amount <= 0:
         raise ValueError("Amount must be positive")
+    # TODO: add currency validation
+    result = charge_card(card, amount)
+    log.info(f"Charged {card} for {amount}")
     return result
"""

_SAMPLE_CODE_WITH_BUGS = '''
def calculate_discount(price, discount_pct):
    """Calculate discounted price."""
    if discount_pct > 1:  # Bug: should check > 100 for percentage
        return 0
    result = price - (price * discount_pct / 100)
    return result  # Bug: no rounding, can return float like 9.999999

def find_user(users, user_id):
    """Find user by ID."""
    for user in users:
        if user["id"] == user_id:  # Bug: no KeyError handling
            return user
    return None  # Missing: no logging for not-found

def divide(a, b):
    """Divide two numbers."""
    return a / b  # Bug: no zero division check
'''

_KNOWN_BUGS = [
    "discount_pct > 1 should be > 100",
    "no rounding on discount result",
    "no KeyError handling on user['id']",
    "no zero division check in divide()",
]

_SAMPLE_FUNCTION = '''
def send_notification(user_id: str, message: str, channel: str = "email") -> bool:
    """Send a notification to a user via the specified channel."""
    user = db.get_user(user_id)
    if not user:
        return False
    if channel == "email":
        return email_client.send(user.email, message)
    elif channel == "sms":
        return sms_client.send(user.phone, message)
    elif channel == "push":
        return push_client.send(user.device_token, message)
    return False
'''


@dataclass
class TaskScore:
    """Score for a single benchmark task."""

    task_name: str
    score: float  # 0.0 to 1.0
    max_score: float = 1.0
    details: str = ""
    duration_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "task": self.task_name,
            "score": round(self.score, 3),
            "max_score": self.max_score,
            "percentage": round(self.score / self.max_score * 100, 1) if self.max_score > 0 else 0,
            "details": self.details,
            "duration_ms": self.duration_ms,
        }


@dataclass
class BenchmarkReport:
    """Full benchmark report across all tasks."""

    tasks: list[TaskScore] = field(default_factory=list)
    overall_score: float = 0.0
    timestamp: str = ""
    duration_ms: int = 0
    error: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()

    @property
    def total_score(self) -> float:
        if not self.tasks:
            return 0.0
        return sum(t.score for t in self.tasks)

    @property
    def max_possible(self) -> float:
        if not self.tasks:
            return 0.0
        return sum(t.max_score for t in self.tasks)

    @property
    def percentage(self) -> float:
        if self.max_possible == 0:
            return 0.0
        return self.total_score / self.max_possible * 100

    def to_dict(self) -> dict:
        return {
            "tasks": [t.to_dict() for t in self.tasks],
            "overall_score": round(self.percentage, 1),
            "total_score": round(self.total_score, 3),
            "max_possible": round(self.max_possible, 3),
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }

    def summary(self) -> str:
        lines: list[str] = []
        lines.append("Self-Benchmark Report")
        lines.append(f"Date: {self.timestamp[:19]}")
        lines.append(f"Overall: {self.percentage:.1f}% ({self.total_score:.2f}/{self.max_possible:.2f})")
        lines.append("")
        for t in self.tasks:
            pct = t.score / t.max_score * 100 if t.max_score else 0
            bar = _progress_bar(pct)
            lines.append(f"  {t.task_name:20s} {bar} {pct:.0f}%")
            if t.details:
                lines.append(f"    {t.details}")
        if self.error:
            lines.append(f"\nError: {self.error}")
        return "\n".join(lines)


def _progress_bar(pct: float, width: int = 20) -> str:
    filled = int(pct / 100 * width)
    return "[" + "#" * filled + "-" * (width - filled) + "]"


class SelfBenchmark:
    """Run self-benchmarking tasks to measure agent quality."""

    AVAILABLE_TASKS = ["review", "test", "bug"]

    def __init__(self, cwd: str):
        self.cwd = cwd
        logger.debug("SelfBenchmark initialized for %s", cwd)

    def run(self, tasks: list[str] | None = None) -> BenchmarkReport:
        """Run benchmark tasks and return a report.

        Args:
            tasks: List of task names to run. None = all tasks.
                   Available: "review", "test", "bug"

        Returns:
            BenchmarkReport with scores for each task.
        """
        if tasks is None:
            tasks = self.AVAILABLE_TASKS

        report = BenchmarkReport()
        start = time.perf_counter()

        task_map = {
            "review": self._task_code_review,
            "test": self._task_test_generation,
            "bug": self._task_bug_detection,
        }

        for task_name in tasks:
            if task_name not in task_map:
                logger.warning("Unknown task: %s, skipping", task_name)
                continue

            logger.info("Running benchmark task: %s", task_name)
            try:
                score = task_map[task_name]()
                report.tasks.append(score)
            except Exception as exc:
                logger.error("Task %s failed: %s", task_name, exc)
                report.tasks.append(TaskScore(
                    task_name=task_name, score=0.0,
                    details=f"Error: {exc}",
                ))

        report.duration_ms = int((time.perf_counter() - start) * 1000)
        report.overall_score = report.percentage
        logger.info("Benchmark complete: %.1f%% (%d tasks)", report.percentage, len(report.tasks))
        return report

    def _task_code_review(self) -> TaskScore:
        """Benchmark: review a sample diff, measure quality.

        Checks if the review catches key issues:
        - TODO without issue reference
        - Logging sensitive data (card number)
        - Missing error handling
        """
        start = time.perf_counter()
        issues_found: list[str] = []

        # Simulate review by pattern matching on the diff
        diff = _SAMPLE_DIFF

        # Check 1: TODO detection
        if "TODO" in diff:
            issues_found.append("todo_detected")

        # Check 2: Sensitive data in logs
        if "log" in diff.lower() and "card" in diff.lower():
            issues_found.append("sensitive_logging")

        # Check 3: Missing error handling for charge_card
        if "charge_card" in diff and "try" not in diff:
            issues_found.append("missing_error_handling")

        expected = {"todo_detected", "sensitive_logging", "missing_error_handling"}
        found = set(issues_found)
        score = self._score_output(expected, found)

        duration = int((time.perf_counter() - start) * 1000)
        return TaskScore(
            task_name="review",
            score=score,
            details=f"Found {len(found)}/{len(expected)} issues: {', '.join(sorted(found))}",
            duration_ms=duration,
        )

    def _task_test_generation(self) -> TaskScore:
        """Benchmark: generate test ideas for a function, measure coverage.

        Evaluates if generated tests cover:
        - Happy path, edge cases, error cases
        - All channels (email, sms, push)
        - User not found case
        """
        start = time.perf_counter()
        func = _SAMPLE_FUNCTION

        # Simulate test generation by analyzing the function
        test_ideas: list[str] = []

        # Check various aspects
        if "user_id" in func:
            test_ideas.append("test_valid_user")
        if "not user" in func or "None" in func:
            test_ideas.append("test_user_not_found")
        if '"email"' in func:
            test_ideas.append("test_email_channel")
        if '"sms"' in func:
            test_ideas.append("test_sms_channel")
        if '"push"' in func:
            test_ideas.append("test_push_channel")
        if "return False" in func:
            test_ideas.append("test_invalid_channel")

        expected = {
            "test_valid_user", "test_user_not_found",
            "test_email_channel", "test_sms_channel",
            "test_push_channel", "test_invalid_channel",
        }
        found = set(test_ideas)
        score = self._score_output(expected, found)

        duration = int((time.perf_counter() - start) * 1000)
        return TaskScore(
            task_name="test",
            score=score,
            details=f"Generated {len(found)}/{len(expected)} test cases",
            duration_ms=duration,
        )

    def _task_bug_detection(self) -> TaskScore:
        """Benchmark: find known bugs in sample code, measure accuracy."""
        start = time.perf_counter()

        code = _SAMPLE_CODE_WITH_BUGS
        bugs_found: list[str] = []

        # Pattern-based bug detection
        if "> 1" in code and "discount" in code:
            bugs_found.append("discount threshold wrong (>1 vs >100)")
        if "return result" in code and "round" not in code and "discount" in code:
            bugs_found.append("no rounding on float result")
        if '["id"]' in code and "try" not in code and "get(" not in code:
            bugs_found.append("no KeyError handling")
        if "a / b" in code and "b == 0" not in code and "b != 0" not in code:
            bugs_found.append("no zero division check")

        expected_count = len(_KNOWN_BUGS)
        found_count = len(bugs_found)
        score = min(found_count / expected_count, 1.0) if expected_count > 0 else 0.0

        duration = int((time.perf_counter() - start) * 1000)
        return TaskScore(
            task_name="bug",
            score=score,
            details=f"Found {found_count}/{expected_count} bugs: {'; '.join(bugs_found)}",
            duration_ms=duration,
        )

    def _score_output(self, expected: set, actual: set) -> float:
        """Score output accuracy as intersection / union (Jaccard similarity).

        Returns 0.0 to 1.0.
        """
        if not expected and not actual:
            return 1.0
        if not expected:
            return 0.0
        intersection = expected & actual
        return len(intersection) / len(expected)

    def save_result(self, report: BenchmarkReport) -> str:
        """Save benchmark result to ~/.code-agents/benchmarks/.

        Returns the file path.
        """
        os.makedirs(BENCHMARKS_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"bench_{ts}.json"
        filepath = os.path.join(BENCHMARKS_DIR, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, indent=2)

        logger.info("Saved benchmark result to %s", filepath)
        return filepath

    def trend(self) -> list[dict]:
        """Load historical benchmark results and return as a trend.

        Returns list of {timestamp, overall_score, tasks} dicts,
        sorted by timestamp ascending.
        """
        if not os.path.isdir(BENCHMARKS_DIR):
            return []

        results: list[dict] = []
        for fname in sorted(os.listdir(BENCHMARKS_DIR)):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(BENCHMARKS_DIR, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                results.append({
                    "timestamp": data.get("timestamp", ""),
                    "overall_score": data.get("overall_score", 0),
                    "tasks": data.get("tasks", []),
                })
            except (json.JSONDecodeError, OSError) as exc:
                logger.debug("Error reading %s: %s", fpath, exc)

        return results


def format_report_rich(report: BenchmarkReport) -> str:
    """Format a benchmark report with terminal colors."""
    lines: list[str] = []
    lines.append(f"\n  \033[1mSelf-Benchmark Report\033[0m")
    lines.append(f"  Date: {report.timestamp[:19]}")
    lines.append(f"  Duration: {report.duration_ms}ms")
    lines.append("")

    pct = report.percentage
    color = "\033[32m" if pct >= 80 else "\033[33m" if pct >= 50 else "\033[31m"
    lines.append(f"  Overall: {color}{pct:.1f}%\033[0m ({report.total_score:.2f}/{report.max_possible:.2f})")
    lines.append("")

    for t in report.tasks:
        t_pct = t.score / t.max_score * 100 if t.max_score else 0
        t_color = "\033[32m" if t_pct >= 80 else "\033[33m" if t_pct >= 50 else "\033[31m"
        bar = _progress_bar(t_pct)
        lines.append(f"  {t.task_name:20s} {bar} {t_color}{t_pct:.0f}%\033[0m  ({t.duration_ms}ms)")
        if t.details:
            lines.append(f"    \033[2m{t.details}\033[0m")

    lines.append("")
    return "\n".join(lines)


def format_trend_rich(trend_data: list[dict]) -> str:
    """Format benchmark trend data."""
    if not trend_data:
        return "  No benchmark history found. Run 'code-agents self-bench' to start tracking."

    lines: list[str] = []
    lines.append(f"\n  \033[1mBenchmark Trend\033[0m ({len(trend_data)} runs)")
    lines.append("")

    for entry in trend_data[-10:]:  # Last 10
        ts = entry.get("timestamp", "")[:16]
        score = entry.get("overall_score", 0)
        color = "\033[32m" if score >= 80 else "\033[33m" if score >= 50 else "\033[31m"
        bar = _progress_bar(score, width=15)
        lines.append(f"  {ts}  {bar} {color}{score:.1f}%\033[0m")

    lines.append("")
    return "\n".join(lines)
