"""Performance Profiler Agent — cProfile-based profiling with optimization suggestions.

Runs a Python command under cProfile, parses hotspots, and generates
pattern-based optimization suggestions.
"""

from __future__ import annotations

import logging
import os
import pstats
import subprocess
import tempfile
from dataclasses import dataclass, field
from io import StringIO
from typing import Optional

logger = logging.getLogger("code_agents.observability.profiler")


@dataclass
class HotSpot:
    """A single performance hotspot identified by the profiler."""

    function: str
    file: str
    line: int
    total_time: float
    calls: int
    per_call: float


@dataclass
class Optimization:
    """An optimization suggestion for a hotspot."""

    function: str
    file: str
    suggestion: str
    estimated_impact: str
    code_fix: str = ""


@dataclass
class ProfileResult:
    """Complete profiling result with hotspots and suggestions."""

    hotspots: list[HotSpot]
    optimizations: list[Optimization]
    total_time: float
    command: str
    summary: str = ""


# ---------------------------------------------------------------------------
# Pattern matchers for optimization suggestions
# ---------------------------------------------------------------------------

_IO_KEYWORDS = frozenset([
    "read", "write", "open", "send", "recv", "connect", "execute",
    "query", "fetch", "request", "urlopen", "get", "post", "put",
])

_DB_KEYWORDS = frozenset([
    "execute", "query", "cursor", "fetchone", "fetchall", "fetchmany",
    "commit", "rollback", "select", "insert", "update", "delete",
])

_JSON_KEYWORDS = frozenset(["loads", "dumps", "load", "dump", "encode", "decode"])

_STRING_KEYWORDS = frozenset(["join", "concat", "format", "replace"])


def _is_io_function(name: str) -> bool:
    """Check if a function name suggests I/O work."""
    lower = name.lower()
    return any(kw in lower for kw in _IO_KEYWORDS)


def _is_db_function(name: str) -> bool:
    """Check if a function name suggests database work."""
    lower = name.lower()
    return any(kw in lower for kw in _DB_KEYWORDS)


def _is_json_function(name: str) -> bool:
    """Check if a function name suggests JSON serialization."""
    lower = name.lower()
    return any(kw in lower for kw in _JSON_KEYWORDS)


class ProfilerAgent:
    """Profile a Python command and produce optimization suggestions."""

    def __init__(self, cwd: str, command: str) -> None:
        self.cwd = cwd
        self.command = command
        logger.info("ProfilerAgent initialized: cwd=%s command=%s", cwd, command)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> ProfileResult:
        """Run the full profiling pipeline.

        1. Execute command under cProfile
        2. Parse stats into HotSpot list
        3. Generate optimization suggestions
        4. Build summary
        """
        logger.info("Starting profile run for: %s", self.command)
        stats_path = self._run_with_cprofile()
        if stats_path is None:
            logger.warning("cProfile run produced no stats file")
            return ProfileResult(
                hotspots=[],
                optimizations=[],
                total_time=0.0,
                command=self.command,
                summary="Profiling failed — no stats produced.",
            )

        hotspots = self._parse_stats(stats_path)
        optimizations = self._generate_optimizations(hotspots)
        total_time = sum(h.total_time for h in hotspots) if hotspots else 0.0

        # Cleanup temp file
        try:
            os.unlink(stats_path)
        except OSError:
            pass

        summary = self._build_summary(hotspots, optimizations, total_time)
        result = ProfileResult(
            hotspots=hotspots,
            optimizations=optimizations,
            total_time=total_time,
            command=self.command,
            summary=summary,
        )
        logger.info("Profile complete: %d hotspots, %d optimizations", len(hotspots), len(optimizations))
        return result

    # ------------------------------------------------------------------
    # Internal: run command under cProfile
    # ------------------------------------------------------------------

    def _run_with_cprofile(self) -> Optional[str]:
        """Run the command under cProfile and return the stats file path."""
        fd, stats_path = tempfile.mkstemp(suffix=".prof", prefix="code_agents_")
        os.close(fd)

        cmd_parts = [
            "python", "-m", "cProfile", "-o", stats_path,
        ] + self.command.split()

        logger.debug("Running: %s", cmd_parts)
        try:
            result = subprocess.run(
                cmd_parts,
                cwd=self.cwd,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if result.returncode != 0:
                logger.warning(
                    "Command exited with code %d: %s",
                    result.returncode,
                    result.stderr[:500] if result.stderr else "(no stderr)",
                )
            # Stats file may still have data even on non-zero exit
            if os.path.exists(stats_path) and os.path.getsize(stats_path) > 0:
                return stats_path
            logger.warning("Stats file is empty or missing")
            return None
        except subprocess.TimeoutExpired:
            logger.error("Command timed out after 300s")
            return None
        except FileNotFoundError:
            logger.error("python not found in PATH")
            return None

    # ------------------------------------------------------------------
    # Internal: parse pstats into HotSpot list
    # ------------------------------------------------------------------

    def _parse_stats(self, stats_path: str, top: int = 20) -> list[HotSpot]:
        """Read pstats file and return top N hotspots sorted by cumulative time."""
        try:
            stats = pstats.Stats(stats_path, stream=StringIO())
        except Exception as exc:
            logger.error("Failed to read stats file %s: %s", stats_path, exc)
            return []

        stats.sort_stats("cumulative")

        hotspots: list[HotSpot] = []
        # stats.stats is dict[(filename, line, func_name)] -> (cc, nc, tt, ct, callers)
        for (filename, line, func_name), (_, num_calls, total_time, cum_time, _) in stats.stats.items():
            # Skip builtins and stdlib internals
            if filename.startswith("<") or "/lib/python" in filename:
                continue
            per_call = cum_time / num_calls if num_calls > 0 else 0.0
            hotspots.append(HotSpot(
                function=func_name,
                file=filename,
                line=line,
                total_time=cum_time,
                calls=num_calls,
                per_call=per_call,
            ))

        # Sort by cumulative time descending
        hotspots.sort(key=lambda h: h.total_time, reverse=True)
        return hotspots[:top]

    # ------------------------------------------------------------------
    # Internal: generate optimization suggestions
    # ------------------------------------------------------------------

    def _generate_optimizations(self, hotspots: list[HotSpot]) -> list[Optimization]:
        """Generate pattern-based optimization suggestions for hotspots."""
        optimizations: list[Optimization] = []

        for hs in hotspots:
            opts = self._analyze_hotspot(hs)
            optimizations.extend(opts)

        return optimizations

    def _analyze_hotspot(self, hs: HotSpot) -> list[Optimization]:
        """Analyze a single hotspot and return applicable optimizations."""
        results: list[Optimization] = []

        # Pattern: Repeated function calls -> cache/memoize
        if hs.calls > 100 and hs.per_call < 0.001:
            results.append(Optimization(
                function=hs.function,
                file=hs.file,
                suggestion="High call count with low per-call time — consider caching or memoization with @functools.lru_cache",
                estimated_impact=f"~{hs.calls} calls could be reduced to 1 with caching",
                code_fix="@functools.lru_cache(maxsize=128)",
            ))

        # Pattern: High per-call time in I/O functions -> async/batch
        if _is_io_function(hs.function) and hs.per_call > 0.01:
            results.append(Optimization(
                function=hs.function,
                file=hs.file,
                suggestion="Slow I/O function — consider async I/O or batching requests",
                estimated_impact=f"est. {int(hs.total_time / hs.per_call * 0.6):.0f}x fewer round trips with batching",
                code_fix="# Use asyncio.gather() or batch API calls",
            ))

        # Pattern: N+1 database queries
        if _is_db_function(hs.function) and hs.calls > 10:
            results.append(Optimization(
                function=hs.function,
                file=hs.file,
                suggestion=f"Possible N+1 query pattern — {hs.calls} DB calls detected. Use batch/bulk queries or JOIN",
                estimated_impact=f"est. {int(hs.calls * 0.8)} fewer queries (~{hs.total_time * 0.6:.2f}s saved)",
                code_fix="# Use SELECT ... WHERE id IN (...) instead of per-item queries",
            ))

        # Pattern: JSON serialization overhead
        if _is_json_function(hs.function) and hs.total_time > 0.1:
            results.append(Optimization(
                function=hs.function,
                file=hs.file,
                suggestion="JSON serialization overhead — consider orjson/ujson for faster parsing",
                estimated_impact=f"est. 2-5x speedup on {hs.total_time:.2f}s of JSON work",
                code_fix="import orjson  # pip install orjson — 3-10x faster than stdlib json",
            ))

        # Pattern: String operations with high call count
        if hs.function in ("join", "format", "replace", "encode", "decode") and hs.calls > 500:
            results.append(Optimization(
                function=hs.function,
                file=hs.file,
                suggestion="Heavy string operations — use str.join() for concatenation, avoid repeated format calls",
                estimated_impact=f"est. 30-50% speedup on string ops ({hs.calls} calls)",
                code_fix="# Use ''.join(items) instead of += in loops",
            ))

        # Pattern: Generic high-time function
        if not results and hs.total_time > 0.5:
            results.append(Optimization(
                function=hs.function,
                file=hs.file,
                suggestion=f"Hotspot consuming {hs.total_time:.2f}s — review for optimization opportunities",
                estimated_impact="varies — profile sub-calls for more detail",
            ))

        return results

    # ------------------------------------------------------------------
    # Internal: build summary
    # ------------------------------------------------------------------

    def _build_summary(
        self,
        hotspots: list[HotSpot],
        optimizations: list[Optimization],
        total_time: float,
    ) -> str:
        """Build a human-readable summary."""
        if not hotspots:
            return "No hotspots detected — profiling may have failed or the command was too fast."
        top3 = ", ".join(h.function for h in hotspots[:3])
        return (
            f"Profiled in {total_time:.2f}s. "
            f"Top hotspots: {top3}. "
            f"{len(optimizations)} optimization(s) suggested."
        )


# ---------------------------------------------------------------------------
# Terminal formatting
# ---------------------------------------------------------------------------

def format_profile_result(result: ProfileResult, top: int = 20) -> str:
    """Format a ProfileResult as a rich terminal table."""
    lines: list[str] = []

    # Header
    cmd_display = result.command if len(result.command) < 50 else result.command[:47] + "..."
    header = f" Profile: {cmd_display} ({result.total_time:.2f}s) "
    width = max(70, len(header) + 4)
    lines.append(f"\u256d\u2500{header}{'─' * (width - len(header) - 3)}\u256e")

    if not result.hotspots:
        lines.append(f"\u2502 {'No hotspots detected.':<{width - 3}}\u2502")
        lines.append(f"\u2570{'─' * (width - 1)}\u256f")
        return "\n".join(lines)

    # Table header
    hdr = f"  {'Function':<30} {'Time':>8} {'Calls':>8} {'Impact':<12}"
    lines.append(f"\u2502{hdr:<{width - 2}}\u2502")
    lines.append(f"\u2502{'─' * (width - 2)}\u2502")

    # Hotspot rows
    max_time = max(h.total_time for h in result.hotspots) if result.hotspots else 1.0
    for hs in result.hotspots[:top]:
        func_display = hs.function[:28] if len(hs.function) > 28 else hs.function
        bar_len = int((hs.total_time / max_time) * 8) if max_time > 0 else 0
        bar = "\u2588" * bar_len + "\u2591" * (8 - bar_len)
        row = f"  {func_display:<30} {hs.total_time:>7.3f}s {hs.calls:>8} {bar}"
        lines.append(f"\u2502{row:<{width - 2}}\u2502")

    lines.append(f"\u2570{'─' * (width - 1)}\u256f")

    # Optimizations
    if result.optimizations:
        lines.append("")
        lines.append("Optimizations:")
        for opt in result.optimizations:
            lines.append(f"  * {opt.function}: {opt.suggestion} ({opt.estimated_impact})")
            if opt.code_fix:
                lines.append(f"    Fix: {opt.code_fix}")

    # Summary
    if result.summary:
        lines.append("")
        lines.append(result.summary)

    return "\n".join(lines)


def format_profile_json(result: ProfileResult) -> dict:
    """Format a ProfileResult as a JSON-serializable dict."""
    return {
        "command": result.command,
        "total_time": result.total_time,
        "summary": result.summary,
        "hotspots": [
            {
                "function": h.function,
                "file": h.file,
                "line": h.line,
                "total_time": h.total_time,
                "calls": h.calls,
                "per_call": h.per_call,
            }
            for h in result.hotspots
        ],
        "optimizations": [
            {
                "function": o.function,
                "file": o.file,
                "suggestion": o.suggestion,
                "estimated_impact": o.estimated_impact,
                "code_fix": o.code_fix,
            }
            for o in result.optimizations
        ],
    }
