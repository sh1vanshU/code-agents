"""Log Analyzer — paste logs, get correlated timeline with root cause analysis.

Parses structured (JSON) and unstructured log lines. Groups by correlation ID,
builds timeline, identifies error chains and root cause.

Usage:
    from code_agents.observability.log_analyzer import LogAnalyzer
    analyzer = LogAnalyzer()
    result = analyzer.analyze(log_text)
    print(format_log_analysis(result))
"""

from __future__ import annotations

import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.observability.log_analyzer")


@dataclass
class LogEntry:
    """A parsed log line."""
    timestamp: str = ""
    level: str = ""  # DEBUG, INFO, WARN, ERROR, FATAL
    service: str = ""
    message: str = ""
    correlation_id: str = ""
    raw: str = ""
    line_number: int = 0
    extra: dict = field(default_factory=dict)


@dataclass
class LogAnalysisConfig:
    cwd: str = "."
    max_entries: int = 1000


@dataclass
class LogTimeline:
    """A correlated group of log entries."""
    correlation_id: str
    entries: list[LogEntry] = field(default_factory=list)
    services: list[str] = field(default_factory=list)
    has_error: bool = False
    duration_ms: float = 0.0


@dataclass
class LogAnalysisResult:
    """Result of analyzing logs."""
    total_lines: int = 0
    parsed_lines: int = 0
    error_count: int = 0
    warn_count: int = 0
    services_seen: list[str] = field(default_factory=list)
    timelines: list[LogTimeline] = field(default_factory=list)
    errors: list[LogEntry] = field(default_factory=list)
    root_cause: Optional[LogEntry] = None
    summary: str = ""
    level_distribution: dict[str, int] = field(default_factory=dict)


class LogAnalyzer:
    """Analyze and correlate log entries."""

    def __init__(self, config: Optional[LogAnalysisConfig] = None):
        self.config = config or LogAnalysisConfig()

    def analyze(self, log_text: str) -> LogAnalysisResult:
        """Analyze log text."""
        logger.info("Analyzing logs (%d chars)", len(log_text))
        result = LogAnalysisResult()

        lines = log_text.strip().splitlines()
        result.total_lines = len(lines)

        entries: list[LogEntry] = []
        for i, line in enumerate(lines[:self.config.max_entries], 1):
            entry = self._parse_line(line, i)
            if entry:
                entries.append(entry)

        result.parsed_lines = len(entries)

        # Count levels
        for entry in entries:
            result.level_distribution[entry.level] = result.level_distribution.get(entry.level, 0) + 1

        result.error_count = result.level_distribution.get("ERROR", 0) + result.level_distribution.get("FATAL", 0)
        result.warn_count = result.level_distribution.get("WARN", 0) + result.level_distribution.get("WARNING", 0)

        # Collect services
        services = set()
        for entry in entries:
            if entry.service:
                services.add(entry.service)
        result.services_seen = sorted(services)

        # Group by correlation ID
        correlated: dict[str, list[LogEntry]] = defaultdict(list)
        uncorrelated: list[LogEntry] = []
        for entry in entries:
            if entry.correlation_id:
                correlated[entry.correlation_id].append(entry)
            else:
                uncorrelated.append(entry)

        for cid, group in correlated.items():
            timeline = LogTimeline(
                correlation_id=cid,
                entries=group,
                services=sorted(set(e.service for e in group if e.service)),
                has_error=any(e.level in ("ERROR", "FATAL") for e in group),
            )
            result.timelines.append(timeline)

        # Collect errors
        result.errors = [e for e in entries if e.level in ("ERROR", "FATAL")]

        # Identify root cause (first error)
        if result.errors:
            result.root_cause = result.errors[0]

        # Build summary
        result.summary = self._build_summary(result)

        return result

    def _parse_line(self, line: str, line_number: int) -> Optional[LogEntry]:
        """Parse a single log line (JSON or plain text)."""
        line = line.strip()
        if not line:
            return None

        # Try JSON first
        if line.startswith("{"):
            try:
                data = json.loads(line)
                return LogEntry(
                    timestamp=str(data.get("timestamp", data.get("time", data.get("@timestamp", "")))),
                    level=str(data.get("level", data.get("severity", data.get("log.level", "INFO")))).upper(),
                    service=str(data.get("service", data.get("service.name", data.get("logger", "")))),
                    message=str(data.get("message", data.get("msg", data.get("log", "")))),
                    correlation_id=str(data.get("correlation_id", data.get("trace_id", data.get("request_id", data.get("x-request-id", ""))))),
                    raw=line,
                    line_number=line_number,
                    extra={k: v for k, v in data.items() if k not in ("timestamp", "time", "level", "severity", "service", "message", "msg")},
                )
            except json.JSONDecodeError:
                pass

        # Try common log formats
        # Format: 2024-01-15 10:30:00 [ERROR] service - message
        patterns = [
            re.compile(r"^(\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2}[.\d]*)\s*\[?(\w+)\]?\s*(?:(\w[\w.-]*)\s*[-|:]?\s*)?(.*)"),
            re.compile(r"^(\w{3}\s+\d+\s+\d{2}:\d{2}:\d{2})\s+(\w+)\s+(\w+)\s+(.*)"),
            re.compile(r"^(\d{2}:\d{2}:\d{2}[.\d]*)\s*(\w+)\s+(.*)"),
        ]

        for pattern in patterns:
            match = pattern.match(line)
            if match:
                groups = match.groups()
                entry = LogEntry(raw=line, line_number=line_number)
                entry.timestamp = groups[0] if len(groups) > 0 else ""
                level = groups[1].upper() if len(groups) > 1 else "INFO"
                if level in ("DEBUG", "INFO", "WARN", "WARNING", "ERROR", "FATAL", "CRITICAL", "TRACE"):
                    entry.level = level
                else:
                    entry.level = "INFO"
                    entry.service = groups[1] if len(groups) > 1 else ""
                entry.message = groups[-1] if groups else line
                if len(groups) > 3:
                    entry.service = groups[2]

                # Extract correlation IDs from message
                cid_match = re.search(r"(?:correlation[_-]?id|trace[_-]?id|request[_-]?id)[=: ]+([a-f0-9-]{8,})", line, re.IGNORECASE)
                if cid_match:
                    entry.correlation_id = cid_match.group(1)

                return entry

        # Fallback: treat as INFO message
        return LogEntry(
            message=line, raw=line, level="INFO", line_number=line_number,
        )

    def _build_summary(self, result: LogAnalysisResult) -> str:
        parts = [f"{result.parsed_lines} lines parsed"]
        if result.error_count:
            parts.append(f"{result.error_count} errors")
        if result.warn_count:
            parts.append(f"{result.warn_count} warnings")
        if result.services_seen:
            parts.append(f"{len(result.services_seen)} services")
        if result.timelines:
            parts.append(f"{len(result.timelines)} correlated flows")
        if result.root_cause:
            parts.append(f"root cause: {result.root_cause.message[:60]}")
        return " | ".join(parts)


def format_log_analysis(result: LogAnalysisResult) -> str:
    """Format log analysis for terminal output."""
    lines = []
    lines.append(f"{'=' * 60}")
    lines.append(f"  Log Analysis")
    lines.append(f"{'=' * 60}")
    lines.append(f"  {result.summary}")
    lines.append(f"  Levels: {result.level_distribution}")

    if result.root_cause:
        lines.append(f"\n  ROOT CAUSE (line {result.root_cause.line_number}):")
        lines.append(f"    [{result.root_cause.level}] {result.root_cause.message[:120]}")

    if result.errors:
        lines.append(f"\n  Errors ({len(result.errors)}):")
        for err in result.errors[:10]:
            svc = f"[{err.service}] " if err.service else ""
            lines.append(f"    L{err.line_number}: {svc}{err.message[:100]}")

    if result.timelines:
        lines.append(f"\n  Correlated Flows ({len(result.timelines)}):")
        for tl in result.timelines[:5]:
            err_marker = " [HAS ERRORS]" if tl.has_error else ""
            lines.append(f"    {tl.correlation_id}: {len(tl.entries)} entries, services={tl.services}{err_marker}")

    lines.append("")
    return "\n".join(lines)
