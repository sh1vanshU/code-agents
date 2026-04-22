"""Batch Optimizer — find loops with individual ops, suggest batch alternatives.

Scans code for loops that perform individual database queries, API calls,
or I/O operations, and suggests batch/bulk equivalents for better performance.

Usage:
    from code_agents.observability.batch_optimizer import BatchOptimizer, BatchOptimizerConfig
    optimizer = BatchOptimizer(BatchOptimizerConfig(cwd="/path/to/repo"))
    result = optimizer.analyze()
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.observability.batch_optimizer")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class BatchOptimizerConfig:
    cwd: str = "."
    max_files: int = 500
    min_severity: str = "medium"  # low | medium | high


@dataclass
class LoopOperation:
    """An individual operation inside a loop."""
    file: str
    loop_line: int
    op_line: int
    op_type: str  # "db_query", "api_call", "file_io", "cache_op"
    code: str = ""
    loop_code: str = ""


@dataclass
class BatchSuggestion:
    """Suggested batch/bulk alternative."""
    file: str
    line: int
    op_type: str
    severity: str = "high"
    original_pattern: str = ""
    batch_alternative: str = ""
    estimated_speedup: str = ""
    implementation: str = ""


@dataclass
class BatchOptimizerReport:
    """Full batch optimization analysis."""
    files_scanned: int = 0
    loop_ops_found: int = 0
    suggestions: list[BatchSuggestion] = field(default_factory=list)
    operations: list[LoopOperation] = field(default_factory=list)
    estimated_total_speedup: str = ""
    summary: str = ""


# ---------------------------------------------------------------------------
# Detection patterns
# ---------------------------------------------------------------------------

LOOP_STARTS = re.compile(r"^\s*(for\s+\w+\s+in\s+|while\s+|\.forEach\s*\(|\.map\s*\(|\.each\s*\()")

INDIVIDUAL_OPS = [
    ("db_query", re.compile(r"\.(?:get|filter|find_one|execute|query|fetch_one|save|create|update|delete)\s*\("),
     "Individual DB query in loop"),
    ("db_query", re.compile(r"(?:INSERT|SELECT|UPDATE|DELETE)\s+", re.IGNORECASE),
     "Raw SQL in loop"),
    ("api_call", re.compile(r"requests\.(?:get|post|put|delete|patch)\s*\("),
     "HTTP request in loop"),
    ("api_call", re.compile(r"(?:httpx|aiohttp)\.\w+\.(?:get|post|put|delete)\s*\("),
     "Async HTTP request in loop"),
    ("file_io", re.compile(r"(?:open\s*\(|\.read_text\(|\.write_text\(|\.read_bytes\()"),
     "File I/O in loop"),
    ("cache_op", re.compile(r"(?:redis\.(?:get|set|delete)|cache\.(?:get|set|delete))\s*\("),
     "Cache operation in loop"),
]

# Batch alternatives per op type
BATCH_ALTERNATIVES = {
    "db_query": {
        "alternative": "Use bulk_create / bulk_update / select_in / executemany",
        "speedup": "10-100x for large datasets",
        "python": (
            "# Instead of:\n"
            "# for item in items:\n"
            "#     Model.objects.create(**item)\n\n"
            "# Use bulk:\n"
            "Model.objects.bulk_create([Model(**item) for item in items])\n\n"
            "# Or for queries:\n"
            "results = Model.objects.filter(id__in=ids)"
        ),
    },
    "api_call": {
        "alternative": "Use batch API endpoint or asyncio.gather for concurrent calls",
        "speedup": "5-50x with concurrency or batch endpoints",
        "python": (
            "# Instead of sequential:\n"
            "# for url in urls:\n"
            "#     requests.get(url)\n\n"
            "# Use concurrent:\n"
            "import asyncio, aiohttp\n"
            "async def fetch_all(urls):\n"
            "    async with aiohttp.ClientSession() as session:\n"
            "        tasks = [session.get(url) for url in urls]\n"
            "        return await asyncio.gather(*tasks)"
        ),
    },
    "file_io": {
        "alternative": "Batch reads into single pass or use memory-mapped I/O",
        "speedup": "2-10x for many small files",
        "python": (
            "# Instead of:\n"
            "# for path in paths:\n"
            "#     content = open(path).read()\n\n"
            "# Use concurrent:\n"
            "from concurrent.futures import ThreadPoolExecutor\n"
            "with ThreadPoolExecutor() as pool:\n"
            "    contents = list(pool.map(Path.read_text, paths))"
        ),
    },
    "cache_op": {
        "alternative": "Use mget/mset or pipeline for batch cache operations",
        "speedup": "5-20x with pipeline/mget",
        "python": (
            "# Instead of:\n"
            "# for key in keys:\n"
            "#     redis.get(key)\n\n"
            "# Use pipeline:\n"
            "pipe = redis.pipeline()\n"
            "for key in keys:\n"
            "    pipe.get(key)\n"
            "results = pipe.execute()"
        ),
    },
}


# ---------------------------------------------------------------------------
# BatchOptimizer
# ---------------------------------------------------------------------------


class BatchOptimizer:
    """Find loops with individual operations and suggest batch alternatives."""

    def __init__(self, config: Optional[BatchOptimizerConfig] = None):
        self.config = config or BatchOptimizerConfig()

    def analyze(self) -> BatchOptimizerReport:
        """Run batch optimization analysis."""
        logger.info("Starting batch optimization analysis in %s", self.config.cwd)
        report = BatchOptimizerReport()
        root = Path(self.config.cwd)

        count = 0
        for ext in ("*.py", "*.js", "*.ts"):
            for fpath in root.rglob(ext):
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
                self._scan_file(rel, lines, report)

        report.files_scanned = count
        report.loop_ops_found = len(report.operations)

        # Generate suggestions
        for op in report.operations:
            alt = BATCH_ALTERNATIVES.get(op.op_type, {})
            report.suggestions.append(BatchSuggestion(
                file=op.file,
                line=op.loop_line,
                op_type=op.op_type,
                severity="high" if op.op_type in ("db_query", "api_call") else "medium",
                original_pattern=op.code,
                batch_alternative=alt.get("alternative", "Consider batching"),
                estimated_speedup=alt.get("speedup", "2-5x"),
                implementation=alt.get("python", ""),
            ))

        if report.suggestions:
            high = sum(1 for s in report.suggestions if s.severity == "high")
            report.estimated_total_speedup = f"{high} high-impact optimizations"

        report.summary = (
            f"Scanned {report.files_scanned} files, found {report.loop_ops_found} "
            f"loop operations, generated {len(report.suggestions)} batch suggestions."
        )
        logger.info("Batch optimization complete: %s", report.summary)
        return report

    def _scan_file(self, rel: str, lines: list[str], report: BatchOptimizerReport) -> None:
        """Scan a file for loops containing individual operations."""
        in_loop = False
        loop_line = 0
        loop_indent = 0
        loop_code = ""

        for idx, line in enumerate(lines, 1):
            stripped = line.lstrip()
            indent = len(line) - len(stripped)

            # Detect loop start
            if LOOP_STARTS.match(line):
                in_loop = True
                loop_line = idx
                loop_indent = indent
                loop_code = stripped
                continue

            # Check if still inside loop body
            if in_loop:
                if stripped and indent <= loop_indent and not stripped.startswith(("#", "//")):
                    in_loop = False
                    continue

                # Check for individual operations
                for op_type, pattern, desc in INDIVIDUAL_OPS:
                    if pattern.search(line):
                        report.operations.append(LoopOperation(
                            file=rel, loop_line=loop_line, op_line=idx,
                            op_type=op_type, code=stripped, loop_code=loop_code,
                        ))


def format_batch_report(report: BatchOptimizerReport) -> str:
    """Render batch optimization report."""
    lines = ["=== Batch Optimizer Report ===", ""]
    lines.append(f"Files scanned:    {report.files_scanned}")
    lines.append(f"Loop operations:  {report.loop_ops_found}")
    lines.append(f"Suggestions:      {len(report.suggestions)}")
    if report.estimated_total_speedup:
        lines.append(f"Impact:           {report.estimated_total_speedup}")
    lines.append("")

    for s in report.suggestions:
        lines.append(f"  [{s.severity.upper()}] {s.file}:{s.line} ({s.op_type})")
        lines.append(f"    Pattern: {s.original_pattern}")
        lines.append(f"    Alternative: {s.batch_alternative}")
        lines.append(f"    Speedup: {s.estimated_speedup}")
        lines.append("")

    lines.append(report.summary)
    return "\n".join(lines)
