"""Log-to-Code Mapper — reconstruct execution paths from production logs."""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.observability.log_to_code")


@dataclass
class LogEntry:
    """A single parsed log line."""
    timestamp: str = ""
    level: str = "INFO"
    logger_name: str = ""
    message: str = ""
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    variables: dict = field(default_factory=dict)
    thread: str = "main"


@dataclass
class ExecutionStep:
    """A step in the reconstructed execution path."""
    order: int = 0
    file_path: str = ""
    function_name: str = ""
    line_number: int = 0
    log_message: str = ""
    variables: dict = field(default_factory=dict)
    duration_ms: Optional[float] = None


@dataclass
class ExecutionPath:
    """Full reconstructed execution path."""
    request_id: str = ""
    steps: list[ExecutionStep] = field(default_factory=list)
    total_duration_ms: float = 0.0
    entry_point: str = ""
    exit_point: str = ""
    errors: list[str] = field(default_factory=list)
    variable_timeline: dict = field(default_factory=dict)


@dataclass
class LogToCodeReport:
    """Complete report from log analysis."""
    paths: list[ExecutionPath] = field(default_factory=list)
    unmapped_lines: list[str] = field(default_factory=list)
    source_files_referenced: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# Common log patterns
LOG_PATTERNS = [
    # Python logging: 2024-01-01 12:00:00,000 - module - INFO - message
    re.compile(
        r"(?P<timestamp>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}[,.]?\d*)\s*"
        r"[-–]\s*(?P<logger>\S+)\s*[-–]\s*(?P<level>\w+)\s*[-–]\s*(?P<message>.*)"
    ),
    # Java/Spring: 2024-01-01 12:00:00.000 INFO [thread] class - message
    re.compile(
        r"(?P<timestamp>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+)\s+"
        r"(?P<level>\w+)\s+\[(?P<thread>[^\]]+)\]\s+(?P<logger>\S+)\s*[-–]\s*(?P<message>.*)"
    ),
    # Generic: [LEVEL] message
    re.compile(
        r"\[(?P<level>DEBUG|INFO|WARN(?:ING)?|ERROR|FATAL)\]\s*(?P<message>.*)"
    ),
]

# Variable extraction patterns
VAR_PATTERNS = [
    re.compile(r"(\w+)\s*=\s*['\"]?([^'\";\s,]+)['\"]?"),
    re.compile(r"(\w+):\s*(\S+)"),
]


class LogToCodeMapper:
    """Reconstructs execution paths from production logs mapped to source code."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        self.source_map: dict[str, list[dict]] = {}  # logger_name -> [{file, line, func}]
        self.log_entries: list[LogEntry] = []

    def analyze(self, log_content: str, source_files: Optional[list[str]] = None) -> LogToCodeReport:
        """Main entry point: analyze logs and reconstruct execution paths."""
        logger.info("Analyzing %d bytes of log content", len(log_content))

        # Step 1: Build source map from project files
        if source_files:
            self._build_source_map(source_files)

        # Step 2: Parse log lines
        self.log_entries = self._parse_logs(log_content)
        logger.info("Parsed %d log entries", len(self.log_entries))

        # Step 3: Group by request/correlation ID
        groups = self._group_by_request(self.log_entries)
        logger.info("Found %d request groups", len(groups))

        # Step 4: Reconstruct execution paths
        paths = []
        unmapped = []
        for req_id, entries in groups.items():
            path = self._reconstruct_path(req_id, entries)
            paths.append(path)

        # Step 5: Identify unmapped lines
        for entry in self.log_entries:
            if not entry.file_path and entry.logger_name not in self.source_map:
                unmapped.append(entry.message)

        # Step 6: Collect referenced source files
        referenced = set()
        for path in paths:
            for step in path.steps:
                if step.file_path:
                    referenced.add(step.file_path)

        report = LogToCodeReport(
            paths=paths,
            unmapped_lines=unmapped[:100],
            source_files_referenced=sorted(referenced),
            warnings=self._generate_warnings(paths),
        )
        logger.info(
            "Report: %d paths, %d unmapped lines, %d source files",
            len(report.paths), len(report.unmapped_lines),
            len(report.source_files_referenced),
        )
        return report

    def _parse_logs(self, content: str) -> list[LogEntry]:
        """Parse raw log content into structured entries."""
        entries = []
        for line in content.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            entry = self._parse_line(line)
            if entry:
                entries.append(entry)
        return entries

    def _parse_line(self, line: str) -> Optional[LogEntry]:
        """Parse a single log line."""
        for pattern in LOG_PATTERNS:
            m = pattern.match(line)
            if m:
                groups = m.groupdict()
                entry = LogEntry(
                    timestamp=groups.get("timestamp", ""),
                    level=groups.get("level", "INFO"),
                    logger_name=groups.get("logger", ""),
                    message=groups.get("message", line),
                    thread=groups.get("thread", "main"),
                )
                entry.variables = self._extract_variables(entry.message)
                self._resolve_source(entry)
                return entry
        # Fallback: treat as unstructured
        return LogEntry(message=line, variables=self._extract_variables(line))

    def _extract_variables(self, message: str) -> dict:
        """Extract variable assignments from log message."""
        variables = {}
        for pattern in VAR_PATTERNS:
            for m in pattern.finditer(message):
                key, value = m.group(1), m.group(2)
                if len(key) > 1 and not key.isupper():
                    variables[key] = value
        return variables

    def _build_source_map(self, source_files: list[str]):
        """Build mapping from logger names to source file locations."""
        logger.debug("Building source map from %d files", len(source_files))
        for fpath in source_files:
            try:
                module_name = self._file_to_module(fpath)
                if module_name:
                    self.source_map[module_name] = [{"file": fpath, "line": 0, "func": ""}]
            except Exception:
                continue

    def _file_to_module(self, fpath: str) -> str:
        """Convert file path to Python module name."""
        path = fpath.replace(self.cwd, "").lstrip("/").replace("/", ".").replace(".py", "")
        return path

    def _resolve_source(self, entry: LogEntry):
        """Try to resolve a log entry to source file location."""
        if entry.logger_name in self.source_map:
            info = self.source_map[entry.logger_name][0]
            entry.file_path = info["file"]
            entry.line_number = info.get("line")

    def _group_by_request(self, entries: list[LogEntry]) -> dict[str, list[LogEntry]]:
        """Group log entries by request/correlation ID."""
        groups: dict[str, list[LogEntry]] = {}
        request_id_pattern = re.compile(
            r"(?:request_id|req_id|correlation_id|trace_id)[=:\s]+([a-zA-Z0-9_-]+)"
        )
        default_group: list[LogEntry] = []
        for entry in entries:
            rid = None
            m = request_id_pattern.search(entry.message)
            if m:
                rid = m.group(1)
            if not rid:
                rid = entry.variables.get("request_id") or entry.variables.get("trace_id")
            if rid:
                groups.setdefault(rid, []).append(entry)
            else:
                default_group.append(entry)
        if default_group and not groups:
            groups["default"] = default_group
        elif default_group:
            groups["untagged"] = default_group
        return groups

    def _reconstruct_path(self, request_id: str, entries: list[LogEntry]) -> ExecutionPath:
        """Reconstruct execution path from grouped log entries."""
        steps = []
        variable_timeline: dict[str, list] = {}
        for i, entry in enumerate(entries):
            step = ExecutionStep(
                order=i,
                file_path=entry.file_path or "",
                function_name=entry.logger_name.split(".")[-1] if entry.logger_name else "",
                line_number=entry.line_number or 0,
                log_message=entry.message,
                variables=entry.variables,
            )
            steps.append(step)
            for k, v in entry.variables.items():
                variable_timeline.setdefault(k, []).append(
                    {"step": i, "value": v, "timestamp": entry.timestamp}
                )

        errors = [e.message for e in entries if e.level in ("ERROR", "FATAL")]
        path = ExecutionPath(
            request_id=request_id,
            steps=steps,
            entry_point=steps[0].file_path if steps else "",
            exit_point=steps[-1].file_path if steps else "",
            errors=errors,
            variable_timeline=variable_timeline,
        )
        return path

    def _generate_warnings(self, paths: list[ExecutionPath]) -> list[str]:
        """Generate warnings about potential issues."""
        warnings = []
        for path in paths:
            if path.errors:
                warnings.append(
                    f"Request {path.request_id}: {len(path.errors)} error(s) detected"
                )
            if len(path.steps) > 50:
                warnings.append(
                    f"Request {path.request_id}: unusually long path ({len(path.steps)} steps)"
                )
            # Check for variable mutations
            for var, timeline in path.variable_timeline.items():
                values = [t["value"] for t in timeline]
                if len(set(values)) > 1:
                    warnings.append(
                        f"Request {path.request_id}: variable '{var}' mutated across execution"
                    )
        return warnings


def format_report(report: LogToCodeReport) -> str:
    """Format a LogToCodeReport as human-readable text."""
    lines = ["# Log-to-Code Execution Report", ""]
    for path in report.paths:
        lines.append(f"## Request: {path.request_id}")
        lines.append(f"Steps: {len(path.steps)} | Errors: {len(path.errors)}")
        lines.append("")
        for step in path.steps[:20]:
            loc = f"{step.file_path}:{step.line_number}" if step.file_path else "(unmapped)"
            lines.append(f"  {step.order}. [{loc}] {step.log_message[:80]}")
            if step.variables:
                vars_str = ", ".join(f"{k}={v}" for k, v in step.variables.items())
                lines.append(f"     vars: {vars_str}")
        lines.append("")
    if report.unmapped_lines:
        lines.append(f"## Unmapped Lines: {len(report.unmapped_lines)}")
        for ul in report.unmapped_lines[:10]:
            lines.append(f"  - {ul[:100]}")
    if report.warnings:
        lines.append("")
        lines.append("## Warnings")
        for w in report.warnings:
            lines.append(f"  - {w}")
    return "\n".join(lines)
