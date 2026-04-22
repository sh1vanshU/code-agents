"""Deadlock Detector — static analysis for concurrency hazards.

Finds: race conditions, lock ordering issues, unsafe shared state access,
missing synchronization in async/threaded code.

Usage:
    from code_agents.observability.deadlock_detector import DeadlockDetector
    detector = DeadlockDetector(DeadlockDetectorConfig(cwd="/path/to/repo"))
    result = detector.scan()
    print(format_deadlock_report(result))
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.observability.deadlock_detector")


@dataclass
class DeadlockDetectorConfig:
    cwd: str = "."
    max_files: int = 500


@dataclass
class ConcurrencyFinding:
    """A potential concurrency hazard."""
    file: str
    line: int
    pattern: str  # "race_condition", "lock_ordering", "shared_state", "missing_sync", "async_hazard"
    severity: str  # "high", "medium", "low"
    description: str
    code: str = ""
    suggestion: str = ""


@dataclass
class DeadlockReport:
    """Result of scanning for concurrency hazards."""
    files_scanned: int = 0
    findings: list[ConcurrencyFinding] = field(default_factory=list)
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    thread_usage: bool = False
    async_usage: bool = False
    multiprocessing_usage: bool = False
    summary: str = ""


CONCURRENCY_PATTERNS = [
    {
        "name": "shared_mutable_global",
        "pattern": re.compile(r"^(\w+)\s*(?::\s*(?:list|dict|set))?\s*=\s*(?:\[\]|\{\}|set\(\))"),
        "context_file": re.compile(r"(?:threading|multiprocessing|asyncio|concurrent)"),
        "severity": "high",
        "description": "Module-level mutable state in a concurrent context — potential race condition",
        "suggestion": "Use threading.Lock, queue.Queue, or thread-local storage",
    },
    {
        "name": "lock_in_async",
        "pattern": re.compile(r"threading\.(?:Lock|RLock|Semaphore)\(\)"),
        "context_func": re.compile(r"async\s+def"),
        "severity": "high",
        "description": "threading.Lock used in async code — will block the event loop",
        "suggestion": "Use asyncio.Lock instead of threading.Lock in async functions",
    },
    {
        "name": "bare_thread_start",
        "pattern": re.compile(r"(?:Thread|Process)\(.*\)\.start\(\)"),
        "severity": "medium",
        "description": "Thread/Process started without join() — potential resource leak or race",
        "suggestion": "Store the thread reference and call .join() or use concurrent.futures",
    },
    {
        "name": "missing_async_await",
        "pattern": re.compile(r"(?<!await\s)(?:asyncio\.\w+|aiohttp\.\w+|httpx\.AsyncClient)\("),
        "context_func": re.compile(r"async\s+def"),
        "severity": "medium",
        "description": "Async call potentially missing await — coroutine never executed",
        "suggestion": "Add 'await' before the async call",
    },
    {
        "name": "time_sleep_in_async",
        "pattern": re.compile(r"time\.sleep\("),
        "context_func": re.compile(r"async\s+def"),
        "severity": "high",
        "description": "time.sleep() in async function blocks the event loop",
        "suggestion": "Use 'await asyncio.sleep()' instead of 'time.sleep()'",
    },
    {
        "name": "global_keyword_in_thread",
        "pattern": re.compile(r"^\s+global\s+\w+"),
        "context_file": re.compile(r"(?:threading|Thread|concurrent)"),
        "severity": "medium",
        "description": "Global variable modification in threaded context — race condition risk",
        "suggestion": "Use threading.Lock to protect global state, or redesign to avoid globals",
    },
    {
        "name": "nested_locks",
        "pattern": re.compile(r"\.acquire\("),
        "severity": "medium",
        "description": "Manual lock acquisition — potential deadlock if locks acquired in different orders",
        "suggestion": "Use context manager ('with lock:') and ensure consistent lock ordering",
    },
    {
        "name": "fire_and_forget_task",
        "pattern": re.compile(r"asyncio\.(?:create_task|ensure_future)\("),
        "severity": "low",
        "description": "Task created without storing reference — exceptions may be silently lost",
        "suggestion": "Store task reference and handle exceptions, or use asyncio.TaskGroup",
    },
]


class DeadlockDetector:
    """Detect concurrency hazards via static analysis."""

    def __init__(self, config: DeadlockDetectorConfig):
        self.config = config

    def scan(self) -> DeadlockReport:
        """Scan codebase for concurrency hazards."""
        logger.info("Scanning for concurrency hazards in %s", self.config.cwd)

        from code_agents.analysis._ast_helpers import scan_python_files

        report = DeadlockReport()
        files = scan_python_files(self.config.cwd)[:self.config.max_files]
        report.files_scanned = len(files)

        for fpath in files:
            self._scan_file(fpath, report)

        report.high_count = sum(1 for f in report.findings if f.severity == "high")
        report.medium_count = sum(1 for f in report.findings if f.severity == "medium")
        report.low_count = sum(1 for f in report.findings if f.severity == "low")
        report.summary = (
            f"{len(report.findings)} hazards: {report.high_count} high, "
            f"{report.medium_count} medium, {report.low_count} low | "
            f"threads={'yes' if report.thread_usage else 'no'} "
            f"async={'yes' if report.async_usage else 'no'}"
        )

        return report

    def _scan_file(self, fpath: str, report: DeadlockReport):
        """Scan a single file."""
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
                lines = content.splitlines()
        except OSError:
            return

        rel_path = os.path.relpath(fpath, self.config.cwd)

        # Detect concurrency usage
        if re.search(r"import\s+threading|from\s+threading", content):
            report.thread_usage = True
        if re.search(r"import\s+asyncio|async\s+def", content):
            report.async_usage = True
        if re.search(r"import\s+multiprocessing|from\s+multiprocessing", content):
            report.multiprocessing_usage = True

        for pattern_def in CONCURRENCY_PATTERNS:
            # Check file-level context requirement
            if "context_file" in pattern_def:
                if not pattern_def["context_file"].search(content):
                    continue

            for i, line in enumerate(lines, 1):
                if pattern_def["pattern"].search(line):
                    # Check function-level context
                    if "context_func" in pattern_def:
                        func_context = "\n".join(lines[max(0, i-10):i])
                        if not pattern_def["context_func"].search(func_context):
                            continue

                    report.findings.append(ConcurrencyFinding(
                        file=rel_path,
                        line=i,
                        pattern=pattern_def["name"],
                        severity=pattern_def["severity"],
                        description=pattern_def["description"],
                        code=line.strip()[:120],
                        suggestion=pattern_def["suggestion"],
                    ))


def format_deadlock_report(report: DeadlockReport) -> str:
    """Format deadlock report for terminal output."""
    lines = []
    lines.append(f"{'=' * 60}")
    lines.append(f"  Concurrency Hazard Scanner")
    lines.append(f"{'=' * 60}")
    lines.append(f"  {report.summary} ({report.files_scanned} files scanned)")

    if not report.findings:
        lines.append("\n  No concurrency hazards found.")
        return "\n".join(lines)

    for sev in ("high", "medium", "low"):
        findings = [f for f in report.findings if f.severity == sev]
        if findings:
            icon = {"high": "X", "medium": "!", "low": "~"}[sev]
            lines.append(f"\n  [{sev.upper()}] ({len(findings)})")
            for f in findings[:15]:
                lines.append(f"    {icon} {f.file}:{f.line} [{f.pattern}]")
                lines.append(f"      {f.description}")
                lines.append(f"      Fix: {f.suggestion}")

    lines.append("")
    return "\n".join(lines)
