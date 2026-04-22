"""Payment Retry Strategy Analyzer — scan codebase for retry anti-patterns.

Pure regex-based scanning. Detects retry loops, decorator-based retries,
and HTTP client retry configs. Flags missing backoff, unbounded retries,
non-retriable error handling, and absent circuit breakers.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("code_agents.domain.retry_analyzer")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class RetryPattern:
    """A detected retry pattern in source code."""
    file: str
    line: int
    strategy: str  # "fixed", "exponential", "none", "custom"
    max_retries: int
    backoff: str  # e.g. "2s fixed", "exponential 2x", "none"
    has_jitter: bool
    has_circuit_breaker: bool


@dataclass
class RetryFinding:
    """An issue found in a retry pattern."""
    file: str
    line: int
    issue: str
    severity: str  # "critical", "warning", "info"
    recommendation: str


# ---------------------------------------------------------------------------
# Regex patterns for detection
# ---------------------------------------------------------------------------

# Decorator-based retries (tenacity, backoff, retrying, custom)
_RE_RETRY_DECORATOR = re.compile(
    r"@(?:retry|retrying|backoff\.on_exception|backoff\.on_predicate|"
    r"tenacity\.retry|with_retries|auto_retry)",
    re.IGNORECASE,
)

# While-loop retries: while ... retry/attempt/tries
_RE_WHILE_RETRY = re.compile(
    r"while\s+.*(?:retr|attempt|tries|try_count|retry_count|num_retries)",
    re.IGNORECASE,
)

# For-loop retries: for i in range(max_retries)
_RE_FOR_RETRY = re.compile(
    r"for\s+\w+\s+in\s+range\s*\(\s*(?:max_retr|MAX_RETR|num_retr|RETR|retries|attempts)",
    re.IGNORECASE,
)

# max_retries / retry config assignments
_RE_MAX_RETRIES = re.compile(
    r"(?:max_retries|MAX_RETRIES|retry_count|RETRY_COUNT|max_attempts|MAX_ATTEMPTS|retries)"
    r"\s*[=:]\s*(\d+)",
)

# Backoff patterns
_RE_EXPONENTIAL_BACKOFF = re.compile(
    r"(?:exponential|expo|exp_backoff|ExponentialBackoff|wait_exponential|"
    r"backoff\.expo|2\s*\*\*\s*(?:attempt|retry|tries|i|n)|"
    r"pow\s*\(\s*2|math\.pow\s*\(\s*2)",
    re.IGNORECASE,
)

_RE_FIXED_BACKOFF = re.compile(
    r"(?:sleep|delay|wait|time\.sleep)\s*\(\s*(\d+(?:\.\d+)?)\s*\)",
    re.IGNORECASE,
)

_RE_JITTER = re.compile(
    r"(?:jitter|random|randint|uniform|randrange|wait_random)",
    re.IGNORECASE,
)

# Circuit breaker patterns
_RE_CIRCUIT_BREAKER = re.compile(
    r"(?:circuit.?breaker|CircuitBreaker|circuit_breaker|pybreaker|"
    r"circuitbreaker|breaker\.call|@circuit|resilience4j\.circuitbreaker|"
    r"CircuitBreakerPolicy|half.?open|OPEN_STATE|HALF_OPEN)",
    re.IGNORECASE,
)

# Non-retriable HTTP status codes
_RE_NON_RETRIABLE_CATCH = re.compile(
    r"(?:status_code|status|response\.status|statusCode|http_status)"
    r"\s*(?:==|!=|>=|<=|in)\s*.*(?:4\d{2}|400|401|403|404|422)",
    re.IGNORECASE,
)

_RE_RETRY_ON_4XX = re.compile(
    r"(?:retry|retries|again).*(?:4\d{2}|400|401|403|404|422)"
    r"|(?:4\d{2}|400|401|403|404|422).*(?:retry|retries|again)",
    re.IGNORECASE | re.DOTALL,
)

# Payment-related file/content patterns
_RE_PAYMENT_INDICATOR = re.compile(
    r"(?:payment|pay|checkout|charge|refund|settlement|disbursement|"
    r"transaction|txn|billing|invoice|subscription|wallet|transfer|"
    r"payout|acquirer|gateway|merchant|order)",
    re.IGNORECASE,
)

# JavaScript/TypeScript retry patterns (axios-retry, got, etc.)
_RE_JS_RETRY = re.compile(
    r"(?:axiosRetry|axios-retry|retryDelay|retryCondition|"
    r"retry\s*:\s*\{|retries\s*:\s*\d+|maxRetries\s*:\s*\d+|"
    r"got\.retry|fetchRetry|retry-axios)",
    re.IGNORECASE,
)

# File extensions to scan
_SCAN_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go",
    ".rb", ".rs", ".kt", ".scala", ".cs",
}

# Directories to skip
_SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "vendor", "dist", "build", ".tox", ".mypy_cache",
    ".pytest_cache", "env", ".env", "site-packages",
}


# ---------------------------------------------------------------------------
# Analyzer
# ---------------------------------------------------------------------------

class RetryAnalyzer:
    """Scans a codebase for retry patterns and anti-patterns."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        logger.debug("RetryAnalyzer initialized for %s", cwd)

    def analyze(self) -> list[RetryFinding]:
        """Run full analysis: find patterns, check each for issues."""
        patterns = self._find_retry_patterns()
        logger.info("Found %d retry patterns in %s", len(patterns), self.cwd)

        findings: list[RetryFinding] = []
        for p in patterns:
            findings.extend(self._check_backoff(p))
            findings.extend(self._check_non_retriable(p))
            findings.extend(self._check_circuit_breaker(p))
            findings.extend(self._check_unbounded(p))
        return findings

    # ------------------------------------------------------------------
    # Pattern detection
    # ------------------------------------------------------------------

    def _find_retry_patterns(self) -> list[RetryPattern]:
        """Walk source files and extract retry patterns."""
        patterns: list[RetryPattern] = []
        root = Path(self.cwd)

        for dirpath, dirnames, filenames in os.walk(root):
            # Prune skip dirs in-place
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]

            for fname in filenames:
                ext = os.path.splitext(fname)[1].lower()
                if ext not in _SCAN_EXTENSIONS:
                    continue

                fpath = os.path.join(dirpath, fname)
                rel = os.path.relpath(fpath, self.cwd)

                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as fh:
                        lines = fh.readlines()
                except OSError:
                    continue

                patterns.extend(self._extract_patterns(rel, lines))

        return patterns

    def _extract_patterns(self, rel_path: str, lines: list[str]) -> list[RetryPattern]:
        """Extract retry patterns from file lines."""
        results: list[RetryPattern] = []
        content = "".join(lines)

        for i, line in enumerate(lines, start=1):
            matched = False

            # Decorator-based retry
            if _RE_RETRY_DECORATOR.search(line):
                matched = True

            # While-loop retry
            if _RE_WHILE_RETRY.search(line):
                matched = True

            # For-loop retry
            if _RE_FOR_RETRY.search(line):
                matched = True

            # JS/TS retry config
            if _RE_JS_RETRY.search(line):
                matched = True

            if not matched:
                continue

            # Determine context: look at surrounding ~30 lines
            ctx_start = max(0, i - 5)
            ctx_end = min(len(lines), i + 30)
            context = "".join(lines[ctx_start:ctx_end])

            strategy = self._detect_strategy(context)
            max_retries = self._detect_max_retries(context)
            backoff = self._detect_backoff_desc(context, strategy)
            has_jitter = bool(_RE_JITTER.search(context))
            has_cb = bool(_RE_CIRCUIT_BREAKER.search(content))

            results.append(RetryPattern(
                file=rel_path,
                line=i,
                strategy=strategy,
                max_retries=max_retries,
                backoff=backoff,
                has_jitter=has_jitter,
                has_circuit_breaker=has_cb,
            ))

        return results

    def _detect_strategy(self, context: str) -> str:
        """Classify the retry strategy from surrounding code."""
        if _RE_EXPONENTIAL_BACKOFF.search(context):
            return "exponential"
        if _RE_FIXED_BACKOFF.search(context):
            return "fixed"
        # Check if there's any delay at all
        if re.search(r"(?:sleep|delay|wait|backoff)", context, re.IGNORECASE):
            return "custom"
        return "none"

    def _detect_max_retries(self, context: str) -> int:
        """Extract max retry count, or -1 for unbounded."""
        m = _RE_MAX_RETRIES.search(context)
        if m:
            try:
                return int(m.group(1))
            except (ValueError, IndexError):
                return -1
        # If we see a while True with retry, it's unbounded
        if re.search(r"while\s+True", context):
            return -1
        return -1

    def _detect_backoff_desc(self, context: str, strategy: str) -> str:
        """Generate a human-readable backoff description."""
        if strategy == "exponential":
            m = _RE_FIXED_BACKOFF.search(context)
            base = m.group(1) if m else "2"
            return f"exponential base={base}s"
        if strategy == "fixed":
            m = _RE_FIXED_BACKOFF.search(context)
            if m:
                return f"{m.group(1)}s fixed"
            return "fixed (unknown interval)"
        if strategy == "custom":
            return "custom backoff"
        return "none"

    # ------------------------------------------------------------------
    # Checks
    # ------------------------------------------------------------------

    def _check_backoff(self, p: RetryPattern) -> list[RetryFinding]:
        """Check for missing or inadequate backoff."""
        findings: list[RetryFinding] = []

        if p.strategy == "none":
            findings.append(RetryFinding(
                file=p.file,
                line=p.line,
                issue="Retry with no backoff — tight loop can overwhelm downstream services",
                severity="warning",
                recommendation=(
                    "Add exponential backoff with jitter. Example: "
                    "time.sleep(base_delay * (2 ** attempt) + random.uniform(0, 1))"
                ),
            ))
        elif p.strategy == "fixed" and not p.has_jitter:
            findings.append(RetryFinding(
                file=p.file,
                line=p.line,
                issue="Fixed-delay retry without jitter — thundering herd risk",
                severity="info",
                recommendation=(
                    "Add random jitter to spread retries: "
                    "delay + random.uniform(0, delay * 0.5)"
                ),
            ))

        return findings

    def _check_non_retriable(self, p: RetryPattern) -> list[RetryFinding]:
        """Check if retrying on non-retriable errors (4xx)."""
        findings: list[RetryFinding] = []

        # Read the file context around the retry
        fpath = os.path.join(self.cwd, p.file)
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as fh:
                lines = fh.readlines()
        except OSError:
            return findings

        ctx_start = max(0, p.line - 5)
        ctx_end = min(len(lines), p.line + 30)
        context = "".join(lines[ctx_start:ctx_end])

        if _RE_RETRY_ON_4XX.search(context):
            findings.append(RetryFinding(
                file=p.file,
                line=p.line,
                issue="Retrying on 4xx status codes — these are client errors and not transient",
                severity="critical",
                recommendation=(
                    "Only retry on 5xx, timeout, and connection errors. "
                    "4xx errors (400, 401, 403, 404) indicate request problems "
                    "that won't resolve on retry."
                ),
            ))

        return findings

    def _check_circuit_breaker(self, p: RetryPattern) -> list[RetryFinding]:
        """Check for missing circuit breaker on payment endpoints."""
        findings: list[RetryFinding] = []

        if p.has_circuit_breaker:
            return findings

        # Check if this file is payment-related
        is_payment = bool(_RE_PAYMENT_INDICATOR.search(p.file))
        if not is_payment:
            fpath = os.path.join(self.cwd, p.file)
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as fh:
                    content = fh.read(8192)  # First 8KB is enough
                is_payment = bool(_RE_PAYMENT_INDICATOR.search(content))
            except OSError:
                pass

        if is_payment:
            findings.append(RetryFinding(
                file=p.file,
                line=p.line,
                issue="Payment-related retry without circuit breaker — cascading failure risk",
                severity="warning",
                recommendation=(
                    "Add a circuit breaker (e.g. pybreaker, resilience4j) to prevent "
                    "cascading failures when a downstream payment service is degraded. "
                    "Open the breaker after N consecutive failures."
                ),
            ))

        return findings

    def _check_unbounded(self, p: RetryPattern) -> list[RetryFinding]:
        """Check for unbounded or excessive retries."""
        findings: list[RetryFinding] = []

        if p.max_retries == -1:
            findings.append(RetryFinding(
                file=p.file,
                line=p.line,
                issue="Unbounded retries — no max_retries limit detected",
                severity="critical",
                recommendation=(
                    "Always set a max_retries limit. For payment operations, "
                    "3-5 retries is typical. For non-critical operations, "
                    "up to 10 may be acceptable."
                ),
            ))
        elif p.max_retries > 10:
            findings.append(RetryFinding(
                file=p.file,
                line=p.line,
                issue=f"Excessive retries (max_retries={p.max_retries}) — increases latency and load",
                severity="critical",
                recommendation=(
                    "Reduce max_retries to 3-5 for payment operations. "
                    "With exponential backoff, 5 retries already spans ~30s. "
                    "Consider failing fast and using a dead-letter queue instead."
                ),
            ))

        return findings


# ---------------------------------------------------------------------------
# Report formatter
# ---------------------------------------------------------------------------

def format_retry_report(findings: list[RetryFinding]) -> str:
    """Format findings into a human-readable terminal report."""
    if not findings:
        return "  No retry issues found."

    severity_icons = {
        "critical": "[CRITICAL]",
        "warning": "[WARNING]",
        "info": "[INFO]",
    }
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    sorted_findings = sorted(findings, key=lambda f: severity_order.get(f.severity, 3))

    lines: list[str] = []
    lines.append(f"  Found {len(sorted_findings)} retry issue(s):\n")

    for i, f in enumerate(sorted_findings, 1):
        icon = severity_icons.get(f.severity, "[?]")
        lines.append(f"  {i}. {icon} {f.file}:{f.line}")
        lines.append(f"     Issue: {f.issue}")
        lines.append(f"     Fix:   {f.recommendation}")
        lines.append("")

    # Summary
    crit = sum(1 for f in sorted_findings if f.severity == "critical")
    warn = sum(1 for f in sorted_findings if f.severity == "warning")
    info = sum(1 for f in sorted_findings if f.severity == "info")
    lines.append(f"  Summary: {crit} critical, {warn} warnings, {info} info")

    return "\n".join(lines)
