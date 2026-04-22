"""Concurrency Advisor — recommend async vs threaded vs multiprocess.

Analyzes code patterns and workload characteristics to suggest the
optimal concurrency model for each module / function.

Usage:
    from code_agents.observability.concurrency_advisor import ConcurrencyAdvisor, ConcurrencyAdvisorConfig
    advisor = ConcurrencyAdvisor(ConcurrencyAdvisorConfig(cwd="/path/to/repo"))
    result = advisor.analyze()
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.observability.concurrency_advisor")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ConcurrencyAdvisorConfig:
    cwd: str = "."
    max_files: int = 500


@dataclass
class WorkloadSignal:
    """A detected workload characteristic."""
    file: str
    line: int
    signal_type: str  # "io_bound", "cpu_bound", "network", "disk", "mixed"
    pattern: str
    code: str = ""


@dataclass
class ConcurrencyRecommendation:
    """A concurrency model recommendation for a file/module."""
    file: str
    model: str  # "asyncio", "threading", "multiprocessing", "sequential"
    confidence: str = "high"
    rationale: str = ""
    signals: list[str] = field(default_factory=list)
    migration_hint: str = ""


@dataclass
class ConcurrencyReport:
    """Full concurrency analysis result."""
    files_scanned: int = 0
    signals_found: int = 0
    recommendations: list[ConcurrencyRecommendation] = field(default_factory=list)
    signals: list[WorkloadSignal] = field(default_factory=list)
    async_candidates: int = 0
    thread_candidates: int = 0
    multiprocess_candidates: int = 0
    summary: str = ""


# ---------------------------------------------------------------------------
# Signal detection patterns
# ---------------------------------------------------------------------------

IO_PATTERNS = [
    ("network", re.compile(r"requests\.(get|post|put|delete|patch)\s*\("), "HTTP request (I/O bound)"),
    ("network", re.compile(r"httpx\.\w+|aiohttp\.\w+"), "HTTP client usage"),
    ("network", re.compile(r"(?:urlopen|urllib\.request)"), "URL fetch (I/O bound)"),
    ("disk", re.compile(r"(?:open|read_file|write_file|Path\([^)]*\)\.(?:read|write))"), "File I/O"),
    ("disk", re.compile(r"(?:shutil|os\.(?:listdir|walk|scandir))"), "Filesystem operation"),
    ("io_bound", re.compile(r"(?:cursor\.execute|\.query|\.fetch|\.commit)"), "Database I/O"),
    ("io_bound", re.compile(r"(?:redis\.|memcache|cache\.get|cache\.set)"), "Cache I/O"),
    ("io_bound", re.compile(r"time\.sleep\s*\("), "Blocking sleep"),
    ("io_bound", re.compile(r"socket\.\w+"), "Socket I/O"),
]

CPU_PATTERNS = [
    ("cpu_bound", re.compile(r"(?:numpy|np)\.\w+"), "NumPy computation"),
    ("cpu_bound", re.compile(r"(?:pandas|pd)\.(?:DataFrame|read_csv|merge)"), "Pandas data processing"),
    ("cpu_bound", re.compile(r"(?:hashlib|bcrypt|scrypt|argon2)\.\w+"), "Cryptographic computation"),
    ("cpu_bound", re.compile(r"for\s+\w+\s+in\s+range\s*\(\s*\d{4,}"), "Large loop iteration"),
    ("cpu_bound", re.compile(r"(?:sklearn|torch|tensorflow|tf)\.\w+"), "ML computation"),
    ("cpu_bound", re.compile(r"(?:json\.loads|json\.dumps)\s*\("), "JSON serialization"),
]

EXISTING_CONCURRENCY = [
    ("asyncio", re.compile(r"(?:async\s+def|await\s+|asyncio\.)"), "Already uses async"),
    ("threading", re.compile(r"(?:threading\.Thread|ThreadPoolExecutor|concurrent\.futures)"), "Already uses threads"),
    ("multiprocessing", re.compile(r"(?:multiprocessing\.|ProcessPoolExecutor)"), "Already uses multiprocessing"),
]


# ---------------------------------------------------------------------------
# ConcurrencyAdvisor
# ---------------------------------------------------------------------------


class ConcurrencyAdvisor:
    """Analyze code patterns and recommend concurrency models."""

    def __init__(self, config: Optional[ConcurrencyAdvisorConfig] = None):
        self.config = config or ConcurrencyAdvisorConfig()

    def analyze(self) -> ConcurrencyReport:
        """Run concurrency analysis."""
        logger.info("Starting concurrency analysis in %s", self.config.cwd)
        report = ConcurrencyReport()
        root = Path(self.config.cwd)

        # Collect per-file signals
        file_signals: dict[str, list[WorkloadSignal]] = {}
        count = 0
        for fpath in root.rglob("*.py"):
            if count >= self.config.max_files:
                break
            count += 1
            if any(p.startswith(".") or p in ("node_modules", "__pycache__", ".venv") for p in fpath.parts):
                continue
            rel = str(fpath.relative_to(root))
            try:
                lines = fpath.read_text(errors="replace").splitlines()
            except Exception:
                continue
            signals: list[WorkloadSignal] = []
            for idx, line in enumerate(lines, 1):
                for sig_type, pattern, desc in IO_PATTERNS + CPU_PATTERNS:
                    if pattern.search(line):
                        ws = WorkloadSignal(
                            file=rel, line=idx,
                            signal_type=sig_type, pattern=desc,
                            code=line.strip(),
                        )
                        signals.append(ws)
                        report.signals.append(ws)
            if signals:
                file_signals[rel] = signals

        report.files_scanned = count
        report.signals_found = len(report.signals)

        # Generate recommendations per file
        for rel, signals in file_signals.items():
            rec = self._recommend(rel, signals)
            report.recommendations.append(rec)
            if rec.model == "asyncio":
                report.async_candidates += 1
            elif rec.model == "threading":
                report.thread_candidates += 1
            elif rec.model == "multiprocessing":
                report.multiprocess_candidates += 1

        report.summary = (
            f"Scanned {report.files_scanned} files, {report.signals_found} signals. "
            f"Recommendations: {report.async_candidates} async, "
            f"{report.thread_candidates} threaded, "
            f"{report.multiprocess_candidates} multiprocess."
        )
        logger.info("Concurrency analysis complete: %s", report.summary)
        return report

    def _recommend(self, file: str, signals: list[WorkloadSignal]) -> ConcurrencyRecommendation:
        """Determine best concurrency model for a file."""
        io_count = sum(1 for s in signals if s.signal_type in ("io_bound", "network", "disk"))
        cpu_count = sum(1 for s in signals if s.signal_type == "cpu_bound")
        signal_names = list({s.pattern for s in signals})

        if cpu_count > io_count and cpu_count >= 3:
            return ConcurrencyRecommendation(
                file=file, model="multiprocessing", confidence="high",
                rationale="Predominantly CPU-bound work benefits from multi-process parallelism.",
                signals=signal_names,
                migration_hint="Use ProcessPoolExecutor or multiprocessing.Pool for CPU tasks.",
            )
        elif io_count >= 3:
            return ConcurrencyRecommendation(
                file=file, model="asyncio", confidence="high",
                rationale="Multiple I/O operations benefit from async concurrency.",
                signals=signal_names,
                migration_hint="Convert to async def, use aiohttp/httpx for HTTP, aiofiles for disk.",
            )
        elif io_count > 0:
            return ConcurrencyRecommendation(
                file=file, model="threading", confidence="medium",
                rationale="Light I/O work can use threading without full async migration.",
                signals=signal_names,
                migration_hint="Use ThreadPoolExecutor for concurrent I/O calls.",
            )
        else:
            return ConcurrencyRecommendation(
                file=file, model="sequential", confidence="medium",
                rationale="No strong concurrency signals; sequential is simplest.",
                signals=signal_names,
            )


def format_concurrency_report(report: ConcurrencyReport) -> str:
    """Render concurrency report."""
    lines = ["=== Concurrency Advisor Report ===", ""]
    lines.append(f"Files scanned:         {report.files_scanned}")
    lines.append(f"Signals found:         {report.signals_found}")
    lines.append(f"Async candidates:      {report.async_candidates}")
    lines.append(f"Thread candidates:     {report.thread_candidates}")
    lines.append(f"Multiprocess cands:    {report.multiprocess_candidates}")
    lines.append("")

    for rec in report.recommendations:
        lines.append(f"  {rec.file} -> {rec.model} ({rec.confidence})")
        lines.append(f"    {rec.rationale}")
        if rec.migration_hint:
            lines.append(f"    Hint: {rec.migration_hint}")
    lines.append("")
    lines.append(report.summary)
    return "\n".join(lines)
