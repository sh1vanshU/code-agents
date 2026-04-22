"""API Rate Limit Auditor — find endpoints missing rate limiting.

Scans codebase for HTTP endpoints (FastAPI, Flask, Django) and checks whether
rate limiting decorators/middleware are applied.  Auth and payment endpoints
without limits are flagged as critical.

SECURITY: Only file:line references are stored — no request payloads or tokens.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.security.rate_limit_audit")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class RateLimitFinding:
    file: str
    line: int
    endpoint: str
    issue: str
    severity: str  # critical | high | medium | low
    suggestion: str


@dataclass
class RateLimitReport:
    findings: list[RateLimitFinding]
    total_endpoints: int
    protected_endpoints: int
    unprotected_endpoints: int
    summary: str
    score: int  # 0-100


# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

# HTTP endpoint decorators
_FASTAPI_ROUTE = re.compile(
    r"""@\s*(?:app|router|api)\s*\.\s*"""
    r"""(get|post|put|patch|delete|head|options)\s*\(\s*[\"']([^\"']+)[\"']""",
    re.IGNORECASE,
)

_FLASK_ROUTE = re.compile(
    r"""@\s*(?:app|bp|blueprint)\s*\.\s*route\s*\(\s*[\"']([^\"']+)[\"']"""
    r"""(?:.*methods\s*=\s*\[([^\]]+)\])?""",
    re.IGNORECASE,
)

_DJANGO_URL = re.compile(
    r"""(?:path|re_path|url)\s*\(\s*[\"']([^\"']+)[\"']""",
    re.IGNORECASE,
)

# Rate limit decorators / middleware
_RATE_LIMIT_PATTERNS = [
    re.compile(r"@\s*(?:rate_?limit|throttle|limiter|slowapi)", re.IGNORECASE),
    re.compile(r"RateLimiter|Throttle|SlowAPI|RateLimit", re.IGNORECASE),
    re.compile(r"(?:from|import)\s+(?:slowapi|ratelimit|django_ratelimit|flask_limiter)", re.IGNORECASE),
    re.compile(r"x-ratelimit|retry-after|429", re.IGNORECASE),
]

# Auth-related endpoint paths
_AUTH_PATH_PATTERN = re.compile(
    r"(?:/login|/register|/signup|/sign-up|/signin|/sign-in|/password|/reset-password"
    r"|/forgot-password|/auth/token|/oauth|/verify-otp|/send-otp|/api-key)",
    re.IGNORECASE,
)

# Payment-related endpoint paths
_PAYMENT_PATH_PATTERN = re.compile(
    r"(?:/pay|/charge|/payment|/checkout|/refund|/transfer|/withdraw"
    r"|/deposit|/transaction|/settle|/disburse|/payout)",
    re.IGNORECASE,
)

# Upload endpoints
_UPLOAD_PATH_PATTERN = re.compile(
    r"(?:/upload|/import|/bulk|/batch)",
    re.IGNORECASE,
)

# File extensions to scan
_SCAN_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".java", ".rb"}

# Directories to skip
_SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv", "env",
    ".tox", ".mypy_cache", ".pytest_cache", "dist", "build", ".next",
    "vendor", "target", ".gradle",
}


# ---------------------------------------------------------------------------
# Auditor
# ---------------------------------------------------------------------------


class RateLimitAuditor:
    """Audit codebase for missing rate limiting on HTTP endpoints."""

    def __init__(self, cwd: str) -> None:
        self.cwd = cwd
        self._files: list[Path] = []

    def audit(self) -> RateLimitReport:
        """Run full audit and return report."""
        logger.info("Starting rate limit audit on %s", self.cwd)
        self._files = self._collect_files()
        endpoints = self._find_endpoints()
        logger.info("Found %d endpoints across %d files", len(endpoints), len(self._files))

        findings: list[RateLimitFinding] = []
        # Run specific checks first so critical findings take precedence in dedup
        findings.extend(self._check_auth_endpoints(endpoints))
        findings.extend(self._check_payment_endpoints(endpoints))
        findings.extend(self._check_rate_limits(endpoints))
        findings.extend(self._check_consistency(endpoints))

        # Deduplicate by (file, line, endpoint, severity) — keep distinct severity levels
        seen: set[tuple[str, int, str, str]] = set()
        unique: list[RateLimitFinding] = []
        for f in findings:
            key = (f.file, f.line, f.endpoint, f.severity)
            if key not in seen:
                seen.add(key)
                unique.append(f)

        protected = sum(1 for ep in endpoints if ep.get("has_rate_limit"))
        unprotected = len(endpoints) - protected
        score = 100 if len(endpoints) == 0 else int((protected / len(endpoints)) * 100)

        summary = (
            f"Scanned {len(self._files)} files, found {len(endpoints)} endpoints. "
            f"{protected} protected, {unprotected} unprotected. "
            f"Score: {score}/100. {len(unique)} finding(s)."
        )
        logger.info(summary)

        return RateLimitReport(
            findings=unique,
            total_endpoints=len(endpoints),
            protected_endpoints=protected,
            unprotected_endpoints=unprotected,
            summary=summary,
            score=score,
        )

    # ------------------------------------------------------------------
    # File collection
    # ------------------------------------------------------------------

    def _collect_files(self) -> list[Path]:
        """Collect scannable source files."""
        result: list[Path] = []
        root = Path(self.cwd)
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            for fname in filenames:
                p = Path(dirpath) / fname
                if p.suffix in _SCAN_EXTENSIONS:
                    result.append(p)
        return result

    # ------------------------------------------------------------------
    # Endpoint discovery
    # ------------------------------------------------------------------

    def _find_endpoints(self) -> list[dict]:
        """Discover all HTTP endpoints in scanned files."""
        endpoints: list[dict] = []
        for fpath in self._files:
            try:
                lines = fpath.read_text(encoding="utf-8", errors="replace").splitlines()
            except (OSError, UnicodeDecodeError):
                continue

            rel = str(fpath.relative_to(self.cwd))
            file_text = "\n".join(lines)
            has_limiter_import = any(p.search(file_text) for p in _RATE_LIMIT_PATTERNS)

            for idx, line in enumerate(lines, start=1):
                ep = self._parse_endpoint(line, idx, rel, lines, has_limiter_import)
                if ep:
                    endpoints.append(ep)
        return endpoints

    def _parse_endpoint(
        self,
        line: str,
        lineno: int,
        rel_path: str,
        all_lines: list[str],
        has_limiter_import: bool,
    ) -> Optional[dict]:
        """Parse a single line for an endpoint definition."""
        # FastAPI / Starlette
        m = _FASTAPI_ROUTE.search(line)
        if m:
            method, path = m.group(1).upper(), m.group(2)
            has_rl = self._has_rate_limit_nearby(all_lines, lineno, has_limiter_import)
            return {
                "file": rel_path, "line": lineno, "method": method,
                "path": path, "framework": "fastapi", "has_rate_limit": has_rl,
            }

        # Flask
        m = _FLASK_ROUTE.search(line)
        if m:
            path = m.group(1)
            methods = m.group(2) if m.group(2) else "GET"
            has_rl = self._has_rate_limit_nearby(all_lines, lineno, has_limiter_import)
            return {
                "file": rel_path, "line": lineno, "method": methods,
                "path": path, "framework": "flask", "has_rate_limit": has_rl,
            }

        # Django URL conf
        m = _DJANGO_URL.search(line)
        if m:
            path = m.group(1)
            has_rl = self._has_rate_limit_nearby(all_lines, lineno, has_limiter_import)
            return {
                "file": rel_path, "line": lineno, "method": "ALL",
                "path": path, "framework": "django", "has_rate_limit": has_rl,
            }

        return None

    def _has_rate_limit_nearby(
        self, lines: list[str], lineno: int, has_limiter_import: bool
    ) -> bool:
        """Check if a rate limit decorator exists in the decorator stack for this endpoint."""
        decorator_patterns = [
            re.compile(r"@\s*(?:rate_?limit|throttle|limiter\.\w+)", re.IGNORECASE),
            re.compile(r"RateLimiter|Throttle\(", re.IGNORECASE),
        ]
        # Collect the decorator stack: walk down from decorator line to find
        # all decorators until we hit a def/class/blank or non-decorator line.
        # Then walk up from the decorator to find stacked decorators above.
        collected: list[str] = [lines[lineno - 1]]  # current line (0-indexed)

        # Walk down to find more decorators or the function def
        for i in range(lineno, min(len(lines), lineno + 5)):
            line = lines[i].strip()
            if line.startswith("@") or line.startswith("def ") or line.startswith("async def "):
                collected.append(lines[i])
            elif not line:
                continue
            else:
                break

        # Walk up to find stacked decorators above the route decorator
        for i in range(lineno - 2, max(-1, lineno - 6), -1):
            line = lines[i].strip()
            if line.startswith("@"):
                collected.append(lines[i])
            elif not line:
                continue
            else:
                break  # hit a non-decorator line (e.g., previous function body)

        context = "\n".join(collected)
        for pat in decorator_patterns:
            if pat.search(context):
                return True
        return False

    # ------------------------------------------------------------------
    # Checks
    # ------------------------------------------------------------------

    def _check_rate_limits(self, endpoints: list[dict]) -> list[RateLimitFinding]:
        """Flag endpoints without any rate limiting."""
        findings: list[RateLimitFinding] = []
        for ep in endpoints:
            if not ep["has_rate_limit"]:
                findings.append(RateLimitFinding(
                    file=ep["file"],
                    line=ep["line"],
                    endpoint=f"{ep['method']} {ep['path']}",
                    issue="Endpoint has no rate limiting",
                    severity="medium",
                    suggestion="Add @rate_limit or throttle middleware to prevent abuse",
                ))
        return findings

    def _check_auth_endpoints(self, endpoints: list[dict] | None = None) -> list[RateLimitFinding]:
        """Flag auth endpoints (login/register/password) without rate limits."""
        if endpoints is None:
            endpoints = self._find_endpoints()
        findings: list[RateLimitFinding] = []
        for ep in endpoints:
            if _AUTH_PATH_PATTERN.search(ep["path"]) and not ep["has_rate_limit"]:
                findings.append(RateLimitFinding(
                    file=ep["file"],
                    line=ep["line"],
                    endpoint=f"{ep['method']} {ep['path']}",
                    issue="Authentication endpoint without rate limiting — brute force risk",
                    severity="critical",
                    suggestion="Add strict rate limiting (e.g., 5 req/min) to prevent credential stuffing",
                ))
        return findings

    def _check_payment_endpoints(self, endpoints: list[dict] | None = None) -> list[RateLimitFinding]:
        """Flag payment endpoints without rate limits."""
        if endpoints is None:
            endpoints = self._find_endpoints()
        findings: list[RateLimitFinding] = []
        for ep in endpoints:
            if _PAYMENT_PATH_PATTERN.search(ep["path"]) and not ep["has_rate_limit"]:
                findings.append(RateLimitFinding(
                    file=ep["file"],
                    line=ep["line"],
                    endpoint=f"{ep['method']} {ep['path']}",
                    issue="Payment endpoint without rate limiting — financial abuse risk",
                    severity="critical",
                    suggestion="Add rate limiting and idempotency checks to prevent duplicate charges",
                ))
        return findings

    def _check_consistency(self, endpoints: list[dict] | None = None) -> list[RateLimitFinding]:
        """Flag groups of similar endpoints with inconsistent rate limiting."""
        if endpoints is None:
            endpoints = self._find_endpoints()
        findings: list[RateLimitFinding] = []

        # Group endpoints by path prefix (first two segments)
        groups: dict[str, list[dict]] = {}
        for ep in endpoints:
            parts = ep["path"].strip("/").split("/")
            prefix = "/" + "/".join(parts[:2]) if len(parts) >= 2 else ep["path"]
            groups.setdefault(prefix, []).append(ep)

        for prefix, eps in groups.items():
            if len(eps) < 2:
                continue
            protected = [e for e in eps if e["has_rate_limit"]]
            unprotected = [e for e in eps if not e["has_rate_limit"]]
            if protected and unprotected:
                for ep in unprotected:
                    findings.append(RateLimitFinding(
                        file=ep["file"],
                        line=ep["line"],
                        endpoint=f"{ep['method']} {ep['path']}",
                        issue=f"Inconsistent rate limiting under {prefix} — some endpoints protected, some not",
                        severity="warning",
                        suggestion="Apply consistent rate limiting across all endpoints in the same group",
                    ))
        return findings


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

_SEVERITY_ICON = {
    "critical": "\u2620\ufe0f ",
    "high": "\u26a0\ufe0f ",
    "medium": "\u26ab",
    "low": "\u2139\ufe0f ",
    "warning": "\u26a0\ufe0f ",
}


def format_rate_limit_report(report: RateLimitReport) -> str:
    """Format report as terminal-friendly text."""
    lines: list[str] = []
    lines.append("\n  Rate Limit Audit Report")
    lines.append("  " + "=" * 50)
    lines.append(f"  Total endpoints:     {report.total_endpoints}")
    lines.append(f"  Protected:           {report.protected_endpoints}")
    lines.append(f"  Unprotected:         {report.unprotected_endpoints}")
    lines.append(f"  Score:               {report.score}/100")
    lines.append("")

    if not report.findings:
        lines.append("  No findings — all endpoints are rate limited.")
        return "\n".join(lines)

    severity_order = {"critical": 0, "high": 1, "medium": 2, "warning": 3, "low": 4}
    sorted_findings = sorted(report.findings, key=lambda f: severity_order.get(f.severity, 5))

    for f in sorted_findings:
        icon = _SEVERITY_ICON.get(f.severity, "")
        lines.append(f"  {icon} [{f.severity.upper()}] {f.endpoint}")
        lines.append(f"     File: {f.file}:{f.line}")
        lines.append(f"     Issue: {f.issue}")
        lines.append(f"     Fix: {f.suggestion}")
        lines.append("")

    return "\n".join(lines)


def rate_limit_report_to_json(report: RateLimitReport) -> dict:
    """Convert report to JSON-serializable dict."""
    return {
        "total_endpoints": report.total_endpoints,
        "protected_endpoints": report.protected_endpoints,
        "unprotected_endpoints": report.unprotected_endpoints,
        "score": report.score,
        "summary": report.summary,
        "findings": [
            {
                "file": f.file,
                "line": f.line,
                "endpoint": f.endpoint,
                "issue": f.issue,
                "severity": f.severity,
                "suggestion": f.suggestion,
            }
            for f in report.findings
        ],
    }
