"""API design checker — validate response consistency, pagination, versioning, errors.

Inspects FastAPI/Flask route handlers and OpenAPI specs for adherence to
API design best practices including consistent error formats, pagination
patterns, and versioning strategies.
"""

from __future__ import annotations

import ast
import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("code_agents.api.api_design_checker")

SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "dist", "build", ".tox", ".mypy_cache", ".pytest_cache",
}

# Common API frameworks route decorators
ROUTE_PATTERNS = [
    re.compile(r"@(app|router)\.(get|post|put|patch|delete|options|head)\("),
    re.compile(r'@(app|router)\.route\(\s*["\']'),
    re.compile(r"@(api_view|action)\("),
]

# Error response format patterns
ERROR_FORMAT_KEYS = {"error", "message", "detail", "code", "status"}

# Pagination parameter names
PAGINATION_PARAMS = {"page", "per_page", "limit", "offset", "cursor", "after", "before"}


@dataclass
class APIFinding:
    """A single API design finding."""

    file: str = ""
    line: int = 0
    endpoint: str = ""
    category: str = ""  # response | pagination | versioning | error_format
    severity: str = "warning"
    message: str = ""
    suggestion: str = ""


@dataclass
class EndpointMeta:
    """Metadata about a discovered API endpoint."""

    file: str = ""
    line: int = 0
    method: str = ""
    path: str = ""
    function_name: str = ""
    has_response_model: bool = False
    has_status_code: bool = False
    has_pagination: bool = False
    has_error_handler: bool = False


@dataclass
class APIDesignResult:
    """Result of API design check."""

    endpoints_found: int = 0
    findings: list[APIFinding] = field(default_factory=list)
    endpoints: list[EndpointMeta] = field(default_factory=list)
    consistency_score: float = 0.0  # 0-100
    summary: dict[str, int] = field(default_factory=dict)


class APIDesignChecker:
    """Check API design quality and consistency."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        logger.debug("APIDesignChecker initialized for %s", cwd)

    def check(
        self,
        categories: list[str] | None = None,
    ) -> APIDesignResult:
        """Run API design checks.

        Args:
            categories: Which checks to run. Default: all.
                Options: response, pagination, versioning, error_format

        Returns:
            APIDesignResult with findings and scores.
        """
        if categories is None:
            categories = ["response", "pagination", "versioning", "error_format"]

        result = APIDesignResult()
        files = self._collect_api_files()
        logger.info("Checking %d API files", len(files))

        for fpath in files:
            try:
                content = Path(fpath).read_text(errors="replace")
            except OSError:
                continue

            rel = os.path.relpath(fpath, self.cwd)
            endpoints = self._extract_endpoints(content, rel)
            result.endpoints.extend(endpoints)

            for ep in endpoints:
                if "response" in categories:
                    result.findings.extend(self._check_response_consistency(content, ep))
                if "pagination" in categories:
                    result.findings.extend(self._check_pagination(content, ep))
                if "error_format" in categories:
                    result.findings.extend(self._check_error_format(content, ep))

        if "versioning" in categories:
            result.findings.extend(self._check_versioning(result.endpoints))

        result.endpoints_found = len(result.endpoints)

        # Calculate consistency score
        if result.endpoints_found > 0:
            issue_ratio = len(result.findings) / result.endpoints_found
            result.consistency_score = round(max(0, 100 - issue_ratio * 20), 1)

        result.summary = {
            "endpoints_found": result.endpoints_found,
            "total_findings": len(result.findings),
            "consistency_score": result.consistency_score,
        }
        logger.info(
            "API check complete: %d endpoints, %d findings, score=%.1f",
            result.endpoints_found, len(result.findings), result.consistency_score,
        )
        return result

    def _collect_api_files(self) -> list[str]:
        """Collect files likely containing API routes."""
        files: list[str] = []
        for root, dirs, fnames in os.walk(self.cwd):
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
            for fname in fnames:
                if not fname.endswith(".py"):
                    continue
                fpath = os.path.join(root, fname)
                # Quick check for route patterns
                try:
                    head = Path(fpath).read_text(errors="replace")[:5000]
                except OSError:
                    continue
                if any(p.search(head) for p in ROUTE_PATTERNS):
                    files.append(fpath)
        return files

    def _extract_endpoints(self, content: str, rel_path: str) -> list[EndpointMeta]:
        """Extract endpoint metadata from source."""
        endpoints: list[EndpointMeta] = []
        lines = content.splitlines()

        for i, line in enumerate(lines):
            for pattern in ROUTE_PATTERNS:
                match = pattern.search(line)
                if not match:
                    continue

                method = match.group(2) if match.lastindex and match.lastindex >= 2 else "unknown"
                # Extract path from decorator
                path_match = re.search(r'["\']([^"\']+)["\']', line)
                path = path_match.group(1) if path_match else "/"

                # Find function name on next line(s)
                func_name = ""
                for j in range(i + 1, min(i + 5, len(lines))):
                    func_match = re.match(r"\s*(?:async\s+)?def\s+(\w+)", lines[j])
                    if func_match:
                        func_name = func_match.group(1)
                        break

                has_model = "response_model" in line
                has_status = "status_code" in line

                # Check surrounding context for pagination/error handling
                context = "\n".join(lines[max(0, i - 2):min(len(lines), i + 30)])
                has_pagination = any(p in context.lower() for p in PAGINATION_PARAMS)
                has_error = "HTTPException" in context or "raise" in context

                endpoints.append(EndpointMeta(
                    file=rel_path, line=i + 1, method=method.upper(),
                    path=path, function_name=func_name,
                    has_response_model=has_model, has_status_code=has_status,
                    has_pagination=has_pagination, has_error_handler=has_error,
                ))
        return endpoints

    def _check_response_consistency(
        self, content: str, ep: EndpointMeta,
    ) -> list[APIFinding]:
        """Check response model consistency."""
        findings: list[APIFinding] = []

        if not ep.has_response_model and ep.method in ("GET", "POST"):
            findings.append(APIFinding(
                file=ep.file, line=ep.line, endpoint=f"{ep.method} {ep.path}",
                category="response", severity="warning",
                message=f"No response_model on {ep.method} {ep.path}",
                suggestion="Add response_model for type safety and documentation",
            ))

        if not ep.has_status_code and ep.method == "POST":
            findings.append(APIFinding(
                file=ep.file, line=ep.line, endpoint=f"{ep.method} {ep.path}",
                category="response", severity="info",
                message=f"No explicit status_code on POST {ep.path}",
                suggestion="Add status_code=201 for resource creation endpoints",
            ))

        return findings

    def _check_pagination(
        self, content: str, ep: EndpointMeta,
    ) -> list[APIFinding]:
        """Check pagination patterns for list endpoints."""
        findings: list[APIFinding] = []

        # Only check GET endpoints that likely return lists
        if ep.method != "GET":
            return findings

        is_list_ep = any(kw in ep.path for kw in ("list", "/s", "all")) or ep.path.endswith("s")
        if is_list_ep and not ep.has_pagination:
            findings.append(APIFinding(
                file=ep.file, line=ep.line, endpoint=f"GET {ep.path}",
                category="pagination", severity="warning",
                message=f"List endpoint GET {ep.path} has no pagination parameters",
                suggestion="Add limit/offset or cursor-based pagination",
            ))

        return findings

    def _check_error_format(
        self, content: str, ep: EndpointMeta,
    ) -> list[APIFinding]:
        """Check error response format consistency."""
        findings: list[APIFinding] = []

        if not ep.has_error_handler:
            findings.append(APIFinding(
                file=ep.file, line=ep.line, endpoint=f"{ep.method} {ep.path}",
                category="error_format", severity="info",
                message=f"No error handling in {ep.function_name}",
                suggestion="Add try/except with HTTPException for consistent errors",
            ))

        return findings

    def _check_versioning(self, endpoints: list[EndpointMeta]) -> list[APIFinding]:
        """Check API versioning strategy."""
        findings: list[APIFinding] = []

        paths = [ep.path for ep in endpoints]
        has_versioned = any(re.match(r"/v\d+/", p) for p in paths)
        has_unversioned = any(not re.match(r"/v\d+/", p) for p in paths)

        if has_versioned and has_unversioned:
            findings.append(APIFinding(
                category="versioning", severity="warning",
                message="Mixed versioned and unversioned API paths",
                suggestion="Consistently use URL versioning (e.g., /v1/) for all endpoints",
            ))

        return findings


def check_api_design(
    cwd: str,
    categories: list[str] | None = None,
) -> dict:
    """Convenience function to check API design.

    Returns:
        Dict with findings, endpoints, and consistency score.
    """
    checker = APIDesignChecker(cwd)
    result = checker.check(categories=categories)
    return {
        "endpoints_found": result.endpoints_found,
        "consistency_score": result.consistency_score,
        "findings": [
            {"file": f.file, "line": f.line, "endpoint": f.endpoint,
             "category": f.category, "severity": f.severity, "message": f.message}
            for f in result.findings
        ],
        "summary": result.summary,
    }
