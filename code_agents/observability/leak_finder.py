"""Leak Finder — detect memory leak patterns via static analysis.

Scans for: unclosed resources, growing caches without eviction,
event listener accumulation, circular references, missing context managers.

Usage:
    from code_agents.observability.leak_finder import LeakFinder
    finder = LeakFinder(LeakFinderConfig(cwd="/path/to/repo"))
    result = finder.scan()
    print(format_leak_report(result))
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.observability.leak_finder")


@dataclass
class LeakFinderConfig:
    cwd: str = "."
    max_files: int = 500


@dataclass
class LeakFinding:
    """A potential memory leak pattern."""
    file: str
    line: int
    pattern: str  # "unclosed_resource", "growing_cache", "listener_leak", "circular_ref", "missing_context_manager"
    severity: str  # "high", "medium", "low"
    description: str
    code: str = ""
    suggestion: str = ""


@dataclass
class LeakReport:
    """Result of scanning for leak patterns."""
    files_scanned: int = 0
    findings: list[LeakFinding] = field(default_factory=list)
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    summary: str = ""


# Patterns that suggest potential leaks
LEAK_PATTERNS = [
    {
        "name": "unclosed_resource",
        "pattern": re.compile(r"(?:open|connect|socket|urlopen|Session|Engine|create_engine)\s*\("),
        "anti_pattern": re.compile(r"(?:with\s+|\.close\(\)|__exit__|contextmanager|@contextlib)"),
        "severity": "high",
        "description": "Resource opened without explicit close or context manager",
        "suggestion": "Use 'with' statement or ensure .close() is called in a finally block",
    },
    {
        "name": "growing_cache",
        "pattern": re.compile(r"(\w+)\s*\[.*\]\s*=|(\w+)\.append\(|(\w+)\.add\(|(\w+)\.update\("),
        "context": re.compile(r"(cache|buffer|queue|pool|registry|_store|_map|_dict|_list|_set|_buffer)"),
        "severity": "medium",
        "description": "Collection grows without size limits or eviction",
        "suggestion": "Add maxlen (collections.deque), LRU eviction, or periodic cleanup",
    },
    {
        "name": "listener_leak",
        "pattern": re.compile(r"(?:addEventListener|\.on\(|\.connect\(|\.subscribe\(|signal\.connect|\.register\()"),
        "anti_pattern": re.compile(r"(?:removeEventListener|\.off\(|\.disconnect\(|\.unsubscribe\(|\.unregister\()"),
        "severity": "medium",
        "description": "Event listener/callback registered without corresponding removal",
        "suggestion": "Add cleanup in __del__, close(), or use weak references",
    },
    {
        "name": "missing_context_manager",
        "pattern": re.compile(r"(\w+)\s*=\s*(?:open|connect|socket|urlopen|Session|Engine)\s*\("),
        "anti_pattern": re.compile(r"^with\s+"),
        "severity": "high",
        "description": "Resource assigned to variable without 'with' statement",
        "suggestion": "Wrap in 'with' statement to ensure automatic cleanup",
    },
    {
        "name": "global_mutable",
        "pattern": re.compile(r"^(\w+)\s*(?::\s*(?:list|dict|set|List|Dict|Set))?\s*=\s*(?:\[\]|\{\}|set\(\)|dict\(\)|list\(\))"),
        "severity": "low",
        "description": "Module-level mutable collection that may grow unbounded",
        "suggestion": "Consider using WeakValueDictionary, LRU cache, or periodic cleanup",
    },
]


class LeakFinder:
    """Scan for memory leak patterns."""

    def __init__(self, config: LeakFinderConfig):
        self.config = config

    def scan(self) -> LeakReport:
        """Scan the codebase for leak patterns."""
        logger.info("Scanning for memory leak patterns in %s", self.config.cwd)

        from code_agents.analysis._ast_helpers import scan_python_files

        report = LeakReport()
        files = scan_python_files(self.config.cwd)[:self.config.max_files]
        report.files_scanned = len(files)

        for fpath in files:
            self._scan_file(fpath, report)

        report.high_count = sum(1 for f in report.findings if f.severity == "high")
        report.medium_count = sum(1 for f in report.findings if f.severity == "medium")
        report.low_count = sum(1 for f in report.findings if f.severity == "low")
        report.summary = f"{len(report.findings)} potential leaks: {report.high_count} high, {report.medium_count} medium, {report.low_count} low"

        return report

    def _scan_file(self, fpath: str, report: LeakReport):
        """Scan a single file for leak patterns."""
        try:
            with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except OSError:
            return

        rel_path = os.path.relpath(fpath, self.config.cwd)
        full_content = "".join(lines)

        for pattern_def in LEAK_PATTERNS:
            for i, line in enumerate(lines, 1):
                if pattern_def["pattern"].search(line):
                    # Check anti-pattern (should NOT be present)
                    if "anti_pattern" in pattern_def:
                        if pattern_def["anti_pattern"].search(line):
                            continue
                        # Check surrounding lines for context manager
                        context_start = max(0, i - 3)
                        context = "".join(lines[context_start:i])
                        if pattern_def["anti_pattern"].search(context):
                            continue

                    # Check context requirement
                    if "context" in pattern_def:
                        if not pattern_def["context"].search(line):
                            continue

                    report.findings.append(LeakFinding(
                        file=rel_path,
                        line=i,
                        pattern=pattern_def["name"],
                        severity=pattern_def["severity"],
                        description=pattern_def["description"],
                        code=line.strip()[:120],
                        suggestion=pattern_def["suggestion"],
                    ))


def format_leak_report(report: LeakReport) -> str:
    """Format leak report for terminal output."""
    lines = []
    lines.append(f"{'=' * 60}")
    lines.append(f"  Memory Leak Pattern Scanner")
    lines.append(f"{'=' * 60}")
    lines.append(f"  {report.summary} ({report.files_scanned} files scanned)")

    if not report.findings:
        lines.append("\n  No potential leaks found.")
        return "\n".join(lines)

    # Group by severity
    for sev in ("high", "medium", "low"):
        findings = [f for f in report.findings if f.severity == sev]
        if findings:
            icon = {"high": "X", "medium": "!", "low": "~"}[sev]
            lines.append(f"\n  [{sev.upper()}] ({len(findings)})")
            for f in findings[:15]:
                lines.append(f"    {icon} {f.file}:{f.line} [{f.pattern}]")
                lines.append(f"      {f.code}")
                lines.append(f"      Fix: {f.suggestion}")

    lines.append("")
    return "\n".join(lines)
