"""Idempotency Key Auditor — scans payment API endpoints for idempotency patterns.

Verifies that payment-related POST/PUT/PATCH endpoints properly handle
idempotency keys, use atomic DB operations, are retry-safe, and prevent
double charges. Supports Python (FastAPI/Flask), Java (Spring), and
Node.js (Express) codebases.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.domain.idempotency_audit")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class IdempotencyFinding:
    file: str
    line: int
    endpoint: str
    issue: str
    severity: str  # "critical", "warning", "info"
    suggestion: str


@dataclass
class _EndpointInfo:
    file: str
    line: int
    method: str  # POST, PUT, PATCH
    path: str
    func_body: str
    func_name: str = ""


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

PAYMENT_KEYWORDS = re.compile(
    r"/(pay|charge|refund|capture|authorize|transfer|order|checkout|settlement|disburse|payout)",
    re.IGNORECASE,
)

# Endpoint decorators / route definitions across frameworks
_ENDPOINT_PATTERNS: list[re.Pattern] = [
    # FastAPI / Flask decorators
    re.compile(
        r"""@(?:app|router|api|bp|blueprint)\.(post|put|patch)\(\s*["']([^"']+)["']""",
        re.IGNORECASE,
    ),
    # Spring annotations
    re.compile(
        r"""@(Post|Put|Patch)Mapping\(\s*(?:value\s*=\s*)?["']([^"']+)["']""",
        re.IGNORECASE,
    ),
    # Express.js (must not be preceded by @ which would be a decorator)
    re.compile(
        r"""(?<!@)(?:app|router)\.(post|put|patch)\(\s*["']([^"']+)["']""",
        re.IGNORECASE,
    ),
]

# Idempotency key indicators
_IDEMPOTENCY_HEADERS = re.compile(
    r"""(X-Idempotency-Key|Idempotency-Key|x-idempotency-key|idempotency.key)""",
    re.IGNORECASE,
)
_IDEMPOTENCY_PARAMS = re.compile(
    r"""(idempotency_key|idempotent_key|request_id|idempotencyKey|idempotentKey|requestId)""",
)

# Atomic / transaction patterns
_ATOMIC_PATTERNS = re.compile(
    r"""(transaction\.atomic|@transaction\.atomic|with\s+transaction\.atomic"""
    r"""|BEGIN\b|COMMIT\b|session\.begin|@Transactional|\.atomic\("""
    r"""|SAVEPOINT\b|@atomic|acquire_lock|with_lock|advisory_lock)""",
    re.IGNORECASE,
)

# Retry-unsafe patterns
_UNSAFE_INCREMENT = re.compile(r"""\b\w+\s*[\+\-]=\s*\d+""")
_INSERT_NO_CONFLICT = re.compile(
    r"""INSERT\s+INTO\b(?!.*(?:ON\s+CONFLICT|ON\s+DUPLICATE\s+KEY|IF\s+NOT\s+EXISTS))""",
    re.IGNORECASE | re.DOTALL,
)
_EXTERNAL_CALL_NO_KEY = re.compile(
    r"""(requests\.(post|put|patch)|httpx\.(post|put|patch)|fetch\(|axios\.(post|put|patch)|HttpClient|RestTemplate)""",
    re.IGNORECASE,
)

# Double-charge prevention
_STATUS_CHECK = re.compile(
    r"""(\.status\s*==|\.status\s*!=|\.state\s*==|\.state\s*!="""
    r"""|status\s*===?\s*["']|order_status|payment_status|txn_status"""
    r"""|OrderStatus\.|PaymentStatus\.|TransactionStatus\.)""",
    re.IGNORECASE,
)
_OPTIMISTIC_LOCK = re.compile(
    r"""(version\s*=|@Version|optimistic.lock|lock_version|__version__|row_version|etag)""",
    re.IGNORECASE,
)

# Source file extensions by framework
_SOURCE_EXTENSIONS = {
    ".py", ".java", ".js", ".ts", ".jsx", ".tsx", ".kt", ".go",
}


# ---------------------------------------------------------------------------
# Auditor
# ---------------------------------------------------------------------------

class IdempotencyAuditor:
    """Scans payment API endpoints and transaction handlers for idempotency patterns."""

    def __init__(self, cwd: str) -> None:
        self.cwd = cwd
        self._files_scanned = 0
        self._endpoints_found = 0
        logger.debug("IdempotencyAuditor initialized for %s", cwd)

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def audit(self) -> list[IdempotencyFinding]:
        """Run the full idempotency audit.

        1. Find all POST/PUT/PATCH endpoints (payment-related)
        2. Check each for idempotency key handling
        3. Check for atomic DB operations
        4. Check for retry safety
        5. Check for double-charge prevention
        """
        findings: list[IdempotencyFinding] = []

        endpoints = self._find_payment_endpoints()
        self._endpoints_found = len(endpoints)
        logger.info(
            "Found %d payment endpoint(s) across %d file(s)",
            len(endpoints),
            self._files_scanned,
        )

        for ep in endpoints:
            findings.extend(self._check_idempotency_key(ep.file, ep.func_body, ep.path, ep.line))
            findings.extend(self._check_atomic_operations(ep.file, ep.func_body, ep.path, ep.line))
            findings.extend(self._check_retry_safety(ep.file, ep.func_body, ep.path, ep.line))
            findings.extend(self._check_double_charge_prevention(ep.file, ep.func_body, ep.path, ep.line))

        # Sort by severity: critical first, then warning, then info
        severity_order = {"critical": 0, "warning": 1, "info": 2}
        findings.sort(key=lambda f: (severity_order.get(f.severity, 3), f.file, f.line))

        logger.info("Audit complete: %d finding(s)", len(findings))
        return findings

    # ------------------------------------------------------------------
    # Endpoint discovery
    # ------------------------------------------------------------------

    def _find_payment_endpoints(self) -> list[_EndpointInfo]:
        """Scan for POST/PUT/PATCH endpoints that are payment-related."""
        endpoints: list[_EndpointInfo] = []
        root = Path(self.cwd)

        for dirpath, dirnames, filenames in os.walk(root):
            # Skip hidden dirs, node_modules, venvs, __pycache__
            dirnames[:] = [
                d for d in dirnames
                if not d.startswith(".")
                and d not in ("node_modules", "__pycache__", "venv", ".venv", "dist", "build", "target")
            ]

            for fname in filenames:
                ext = os.path.splitext(fname)[1]
                if ext not in _SOURCE_EXTENSIONS:
                    continue

                fpath = os.path.join(dirpath, fname)
                try:
                    content = Path(fpath).read_text(encoding="utf-8", errors="ignore")
                except (OSError, UnicodeDecodeError):
                    continue

                self._files_scanned += 1
                lines = content.split("\n")

                for pattern in _ENDPOINT_PATTERNS:
                    for match in pattern.finditer(content):
                        method = match.group(1).upper()
                        path = match.group(2)

                        if not PAYMENT_KEYWORDS.search(path):
                            continue

                        # Find line number
                        line_num = content[:match.start()].count("\n") + 1

                        # Extract function body (next 80 lines from match)
                        start_idx = max(0, line_num - 1)
                        end_idx = min(len(lines), start_idx + 80)
                        func_body = "\n".join(lines[start_idx:end_idx])

                        rel_path = os.path.relpath(fpath, self.cwd)

                        endpoints.append(_EndpointInfo(
                            file=rel_path,
                            line=line_num,
                            method=method,
                            path=path,
                            func_body=func_body,
                        ))

        return endpoints

    # ------------------------------------------------------------------
    # Check: idempotency key
    # ------------------------------------------------------------------

    def _check_idempotency_key(
        self, file: str, func_body: str, endpoint: str, line: int
    ) -> list[IdempotencyFinding]:
        """Check if function accepts/validates an idempotency key."""
        findings: list[IdempotencyFinding] = []

        has_header = bool(_IDEMPOTENCY_HEADERS.search(func_body))
        has_param = bool(_IDEMPOTENCY_PARAMS.search(func_body))

        if not has_header and not has_param:
            findings.append(IdempotencyFinding(
                file=file,
                line=line,
                endpoint=endpoint,
                issue="No idempotency key handling found",
                severity="critical",
                suggestion=(
                    "Accept an idempotency key via header (X-Idempotency-Key) or "
                    "parameter (idempotency_key). Store the key with the response "
                    "and return cached response on duplicate requests."
                ),
            ))
        elif has_header or has_param:
            # Key is present — info-level acknowledgement
            findings.append(IdempotencyFinding(
                file=file,
                line=line,
                endpoint=endpoint,
                issue="Idempotency key parameter/header detected",
                severity="info",
                suggestion="Ensure the key is validated, stored, and checked before processing.",
            ))

        return findings

    # ------------------------------------------------------------------
    # Check: atomic operations
    # ------------------------------------------------------------------

    def _check_atomic_operations(
        self, file: str, func_body: str, endpoint: str, line: int
    ) -> list[IdempotencyFinding]:
        """Check for DB transaction / atomicity patterns."""
        findings: list[IdempotencyFinding] = []

        has_atomic = bool(_ATOMIC_PATTERNS.search(func_body))

        if not has_atomic:
            findings.append(IdempotencyFinding(
                file=file,
                line=line,
                endpoint=endpoint,
                issue="No atomic/transaction wrapper around state changes",
                severity="warning",
                suggestion=(
                    "Wrap payment state mutations in a database transaction "
                    "(e.g., @transaction.atomic, session.begin(), BEGIN/COMMIT) "
                    "to prevent partial writes on failure."
                ),
            ))

        return findings

    # ------------------------------------------------------------------
    # Check: retry safety
    # ------------------------------------------------------------------

    def _check_retry_safety(
        self, file: str, func_body: str, endpoint: str, line: int
    ) -> list[IdempotencyFinding]:
        """Check for patterns that are unsafe to retry."""
        findings: list[IdempotencyFinding] = []

        # Check for increment without check-and-set
        if _UNSAFE_INCREMENT.search(func_body):
            findings.append(IdempotencyFinding(
                file=file,
                line=line,
                endpoint=endpoint,
                issue="Counter increment without check-and-set may cause double-counting on retry",
                severity="warning",
                suggestion=(
                    "Use compare-and-swap or conditional update: "
                    "UPDATE ... SET counter = counter + 1 WHERE counter = <expected_value> "
                    "or use the idempotency key to deduplicate."
                ),
            ))

        # Check for INSERT without ON CONFLICT
        if _INSERT_NO_CONFLICT.search(func_body):
            findings.append(IdempotencyFinding(
                file=file,
                line=line,
                endpoint=endpoint,
                issue="INSERT without ON CONFLICT / IF NOT EXISTS may create duplicates on retry",
                severity="warning",
                suggestion=(
                    "Use INSERT ... ON CONFLICT DO NOTHING/UPDATE or "
                    "INSERT ... IF NOT EXISTS to make inserts idempotent."
                ),
            ))

        # Check for external API calls without forwarding idempotency key
        ext_calls = _EXTERNAL_CALL_NO_KEY.findall(func_body)
        if ext_calls:
            has_key_forward = bool(_IDEMPOTENCY_HEADERS.search(func_body)) or bool(_IDEMPOTENCY_PARAMS.search(func_body))
            if not has_key_forward:
                findings.append(IdempotencyFinding(
                    file=file,
                    line=line,
                    endpoint=endpoint,
                    issue="External API call without idempotency key forwarding",
                    severity="warning",
                    suggestion=(
                        "Forward the idempotency key to downstream API calls "
                        "to ensure end-to-end idempotency."
                    ),
                ))

        return findings

    # ------------------------------------------------------------------
    # Check: double-charge prevention
    # ------------------------------------------------------------------

    def _check_double_charge_prevention(
        self, file: str, func_body: str, endpoint: str, line: int
    ) -> list[IdempotencyFinding]:
        """Check for duplicate charge prevention mechanisms."""
        findings: list[IdempotencyFinding] = []

        has_status_check = bool(_STATUS_CHECK.search(func_body))
        has_optimistic_lock = bool(_OPTIMISTIC_LOCK.search(func_body))

        if not has_status_check and not has_optimistic_lock:
            findings.append(IdempotencyFinding(
                file=file,
                line=line,
                endpoint=endpoint,
                issue="No double-charge prevention detected (missing status check or optimistic lock)",
                severity="critical",
                suggestion=(
                    "Check order/payment status before charging "
                    "(e.g., if order.status == 'PENDING') and/or use optimistic locking "
                    "(version field) to prevent concurrent duplicate charges."
                ),
            ))
        elif has_status_check and has_optimistic_lock:
            findings.append(IdempotencyFinding(
                file=file,
                line=line,
                endpoint=endpoint,
                issue="Status check and optimistic locking both present",
                severity="info",
                suggestion="Good — both status guard and optimistic lock detected.",
            ))

        return findings


# ---------------------------------------------------------------------------
# Report formatter
# ---------------------------------------------------------------------------

def format_idempotency_report(findings: list[IdempotencyFinding]) -> str:
    """Format findings for terminal output, grouped by severity with remediation."""
    if not findings:
        return "  No idempotency issues found. All payment endpoints look good."

    lines: list[str] = []

    # Group by severity
    by_severity: dict[str, list[IdempotencyFinding]] = {
        "critical": [],
        "warning": [],
        "info": [],
    }
    for f in findings:
        by_severity.setdefault(f.severity, []).append(f)

    severity_labels = {
        "critical": "CRITICAL",
        "warning": "WARNING",
        "info": "INFO",
    }
    severity_icons = {
        "critical": "[!]",
        "warning": "[~]",
        "info": "[i]",
    }

    total = len(findings)
    crit_count = len(by_severity["critical"])
    warn_count = len(by_severity["warning"])
    info_count = len(by_severity["info"])

    lines.append(f"  Idempotency Audit: {total} finding(s)")
    lines.append(f"  Critical: {crit_count}  Warning: {warn_count}  Info: {info_count}")
    lines.append("")

    for sev in ("critical", "warning", "info"):
        items = by_severity.get(sev, [])
        if not items:
            continue

        label = severity_labels[sev]
        icon = severity_icons[sev]
        lines.append(f"  --- {label} ({len(items)}) ---")

        for f in items:
            lines.append(f"  {icon} {f.file}:{f.line}  {f.endpoint}")
            lines.append(f"      Issue: {f.issue}")
            lines.append(f"      Fix:   {f.suggestion}")
            lines.append("")

    return "\n".join(lines)
