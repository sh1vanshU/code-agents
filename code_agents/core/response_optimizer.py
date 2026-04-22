"""Response Optimizer — analyze API responses for over-fetching, N+1, pagination gaps.

Scans API endpoint handlers and identifies: excessive data in responses,
missing pagination for list endpoints, N+1 serialization patterns,
unnecessary nested data, and missing field selection.

Usage:
    from code_agents.core.response_optimizer import ResponseOptimizer
    optimizer = ResponseOptimizer(ResponseOptimizerConfig(cwd="/path/to/repo"))
    result = optimizer.scan()
    print(format_response_report(result))
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.core.response_optimizer")


@dataclass
class ResponseOptimizerConfig:
    cwd: str = "."
    max_files: int = 200


@dataclass
class ResponseFinding:
    file: str
    line: int
    endpoint: str = ""
    finding_type: str = ""  # "over_fetching", "missing_pagination", "n_plus_1", "large_response", "no_field_selection"
    severity: str = "medium"
    description: str = ""
    suggestion: str = ""


@dataclass
class ResponseOptimizeResult:
    files_scanned: int = 0
    endpoints_found: int = 0
    findings: list[ResponseFinding] = field(default_factory=list)
    summary: str = ""


class ResponseOptimizer:
    """Scan API endpoints for response optimization opportunities."""

    def __init__(self, config: ResponseOptimizerConfig):
        self.config = config

    def scan(self) -> ResponseOptimizeResult:
        logger.info("Scanning API responses for optimization in %s", self.config.cwd)
        result = ResponseOptimizeResult()

        from code_agents.tools._pattern_matchers import grep_codebase
        # Find all route handlers
        matches = grep_codebase(self.config.cwd, r"@(?:router|app)\.(get|post|put|delete)", max_results=self.config.max_files)
        result.endpoints_found = len(matches)

        seen_files = set()
        for match in matches:
            seen_files.add(match.file)
            self._analyze_endpoint(match.file, match.line, match.content, result)

        result.files_scanned = len(seen_files)
        result.summary = f"{result.endpoints_found} endpoints, {len(result.findings)} optimization opportunities"
        return result

    def _analyze_endpoint(self, file: str, line: int, content: str, result: ResponseOptimizeResult):
        full_path = os.path.join(self.config.cwd, file)
        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
        except OSError:
            return

        # Get the handler body (next 30 lines after decorator)
        handler_body = "".join(lines[line - 1:line + 30])

        # Check for list endpoints without pagination
        if re.search(r"\.get\(.*[\"']/[\"']", content):
            if not re.search(r"(limit|offset|page|skip|cursor|pagination)", handler_body, re.IGNORECASE):
                result.findings.append(ResponseFinding(
                    file=file, line=line, endpoint=content.strip(),
                    finding_type="missing_pagination", severity="high",
                    description="List endpoint without pagination parameters",
                    suggestion="Add limit/offset or cursor-based pagination to prevent returning unbounded results",
                ))

        # Check for returning all fields (no response_model or select)
        if "return " in handler_body and "response_model" not in content:
            if not re.search(r"(model_dump|dict\(|schema|fields=|exclude=|include=)", handler_body):
                result.findings.append(ResponseFinding(
                    file=file, line=line, endpoint=content.strip(),
                    finding_type="no_field_selection", severity="medium",
                    description="Endpoint returns data without explicit field selection",
                    suggestion="Use response_model or explicit field selection to avoid over-fetching",
                ))

        # Check for N+1 patterns (loop with DB calls)
        if re.search(r"for\s+\w+\s+in.*:.*\n.*(?:query|find|get|fetch|select|execute)", handler_body, re.DOTALL):
            result.findings.append(ResponseFinding(
                file=file, line=line, endpoint=content.strip(),
                finding_type="n_plus_1", severity="high",
                description="Possible N+1 query pattern in endpoint handler",
                suggestion="Use batch/bulk query, eager loading, or dataloader pattern",
            ))


def format_response_report(result: ResponseOptimizeResult) -> str:
    lines = [f"{'=' * 60}", f"  API Response Optimizer", f"{'=' * 60}"]
    lines.append(f"  {result.summary}")
    if not result.findings:
        lines.append("\n  No optimization opportunities found.")
    else:
        for sev in ("high", "medium", "low"):
            findings = [f for f in result.findings if f.severity == sev]
            if findings:
                lines.append(f"\n  [{sev.upper()}] ({len(findings)})")
                for f in findings[:10]:
                    lines.append(f"    {f.file}:{f.line} [{f.finding_type}]")
                    lines.append(f"      {f.description}")
                    lines.append(f"      Fix: {f.suggestion}")
    lines.append("")
    return "\n".join(lines)
