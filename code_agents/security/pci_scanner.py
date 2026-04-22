"""PCI-DSS Compliance Scanner for payment gateway code.

Scans codebase for PCI-DSS violations: PAN in logs, weak encryption, missing
tokenization, card data in errors, transport security, key management, and
access control issues.

SECURITY: This scanner MUST NOT log or store actual card numbers found.
Only file:line references are recorded in findings.
"""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.security.pci_scanner")

# ---------------------------------------------------------------------------
# PCI-DSS Rules
# ---------------------------------------------------------------------------

PCI_RULES = {
    "PCI-3.4": "Render PAN unreadable anywhere it is stored",
    "PCI-4.1": "Use strong cryptography for transmission",
    "PCI-6.5.1": "Injection flaws (SQL, OS, LDAP)",
    "PCI-6.5.3": "Insecure cryptographic storage",
    "PCI-6.5.7": "Cross-site scripting (XSS)",
    "PCI-6.5.10": "Broken authentication",
    "PCI-8.2.1": "Strong cryptography for credential storage",
}

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class PCIFinding:
    file: str
    line: int
    rule_id: str
    severity: str  # critical | high | medium | low
    description: str
    remediation: str
    code_snippet: str = ""


@dataclass
class PCIReport:
    findings: list[PCIFinding]
    score: int  # 0-100
    passed_rules: list[str]
    failed_rules: list[str]
    summary: str
    scan_time: float


# ---------------------------------------------------------------------------
# Patterns (compiled once)
# ---------------------------------------------------------------------------

# Card number regex — matches 13-19 digit patterns with optional separators.
# Covers Visa (4xxx), Mastercard (5xxx), Discover (6xxx), Amex (3xxx).
# IMPORTANT: We never capture or store matched values — only detect presence.
_PAN_PATTERN = re.compile(
    r"\b[3-6]\d{3}[\s\-]?\d{4}[\s\-]?\d{4}[\s\-]?\d{1,7}\b"
)

# Variable names that suggest card data
_CARD_VAR_PATTERN = re.compile(
    r"\b(card_?number|card_?no|pan|card_?num|credit_?card|cc_?number|"
    r"card_?digits|primary_?account|cardholder)\b",
    re.IGNORECASE,
)

# Logging / print statements
_LOG_STATEMENT = re.compile(
    r"(logger\.(info|debug|warning|error|critical|exception)|"
    r"logging\.(info|debug|warning|error|critical)|"
    r"print\s*\()",
)

# Weak crypto algorithms
_WEAK_HASH = re.compile(
    r"(hashlib\.md5|hashlib\.sha1|MD5\s*\(|SHA1\s*\(|"
    r"Crypto\.Hash\.MD5|Crypto\.Hash\.SHA(?:1)?(?!\d))",
    re.IGNORECASE,
)

_WEAK_CIPHER = re.compile(
    r"(DES\.new|DES3\.new|Cipher\s*\(\s*DES|ARC4|RC4|Blowfish|"
    r"AES\.MODE_ECB|MODE_ECB|algorithms\.TripleDES|algorithms\.Blowfish)",
    re.IGNORECASE,
)

_SMALL_KEY = re.compile(r"key_size\s*=\s*(\d+)")

# Transport security
_HTTP_URL = re.compile(r"""(["'])http://[^"']+/(?:pay|card|checkout|transaction|billing|order)[^"']*\1""", re.IGNORECASE)
_VERIFY_FALSE = re.compile(r"verify\s*=\s*False")
_SSL_DISABLE = re.compile(
    r"(CERT_NONE|check_hostname\s*=\s*False|ssl_verify\s*=\s*False|"
    r"InsecureRequestWarning|urllib3\.disable_warnings)",
)

# Key management
_HARDCODED_KEY = re.compile(
    r"""(?:(?:encryption|secret|api|aes|private)_?key|SECRET_KEY|AES_KEY)\s*=\s*["'][A-Za-z0-9+/=]{16,}["']""",
    re.IGNORECASE,
)
_WEAK_KDF = re.compile(
    r"(hashlib\.(md5|sha1|sha256)\s*\(\s*(?:password|secret|key|credential))",
    re.IGNORECASE,
)

# Access control — payment endpoints without auth
_PAYMENT_ENDPOINT = re.compile(
    r"""@(?:app|router|api)\.(get|post|put|patch|delete)\s*\(\s*["']/[^"']*(?:pay|card|checkout|transaction|billing|refund)[^"']*["']""",
    re.IGNORECASE,
)
_AUTH_DECORATOR = re.compile(
    r"@(?:requires?_auth|login_required|authenticated|Depends\s*\(\s*(?:get_current_user|verify_token|auth)|"
    r"permission_required|jwt_required|token_required)",
    re.IGNORECASE,
)
_RATE_LIMIT_DECORATOR = re.compile(
    r"@(?:rate_limit|limiter\.limit|throttle|RateLimit)",
    re.IGNORECASE,
)

# Error / exception patterns with card vars
_EXCEPTION_WITH_CARD = re.compile(
    r"(?:raise\s+\w+(?:Error|Exception)\s*\(|"
    r"(?:HttpResponse|JSONResponse|jsonify|Response)\s*\(|"
    r"return\s+.*(?:error|message|detail)\s*[=:])"
    r"[^);\n]*\b(?:card_?number|pan|card_?no|cc_?number|card_?digits)\b",
    re.IGNORECASE,
)

# DB column patterns suggesting raw PAN storage
_DB_COLUMN_RAW_PAN = re.compile(
    r"""(?:Column|Field|CharField|TextField|column)\s*\(\s*["'](?:card_?number|pan|card_?no|cc_?number)["']""",
    re.IGNORECASE,
)

# Tokenisation suffix check (positive — means it's tokenised)
_TOKEN_SUFFIX = re.compile(r"_token(?:ized)?$|_masked$|_hash(?:ed)?$", re.IGNORECASE)

# Source file extensions to scan
_SOURCE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go",
    ".rb", ".php", ".cs", ".kt", ".scala", ".rs",
}

# Directories to skip
_SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".tox", ".venv", "venv",
    "env", ".mypy_cache", ".pytest_cache", "dist", "build",
    ".eggs", "*.egg-info",
}


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


class PCIComplianceScanner:
    """Scans a codebase for PCI-DSS compliance violations."""

    def __init__(self, cwd: str) -> None:
        self.cwd = os.path.abspath(cwd)
        self._files: list[Path] = []
        self._file_cache: dict[str, list[str]] = {}
        logger.debug("PCIComplianceScanner initialised for %s", self.cwd)

    # -- public API ----------------------------------------------------------

    def scan(self) -> PCIReport:
        """Run all PCI checks and return a report."""
        t0 = time.monotonic()
        self._files = self._collect_files()
        logger.info("Scanning %d source files in %s", len(self._files), self.cwd)

        findings: list[PCIFinding] = []
        findings.extend(self._check_pan_in_logs())
        findings.extend(self._check_encryption())
        findings.extend(self._check_tokenization())
        findings.extend(self._check_error_messages())
        findings.extend(self._check_transport_security())
        findings.extend(self._check_key_management())
        findings.extend(self._check_access_control())

        elapsed = time.monotonic() - t0

        # Determine which rules passed / failed
        failed_ids = sorted({f.rule_id for f in findings})
        passed_ids = sorted(set(PCI_RULES.keys()) - set(failed_ids))

        score = self._calculate_score(findings)
        summary = self._build_summary(findings, score, elapsed)

        report = PCIReport(
            findings=findings,
            score=score,
            passed_rules=passed_ids,
            failed_rules=failed_ids,
            summary=summary,
            scan_time=elapsed,
        )
        logger.info("PCI scan complete: score=%d, findings=%d, time=%.2fs",
                     score, len(findings), elapsed)
        return report

    # -- file collection -----------------------------------------------------

    def _collect_files(self) -> list[Path]:
        """Walk cwd and collect source files, skipping irrelevant dirs."""
        collected: list[Path] = []
        root = Path(self.cwd)
        for dirpath, dirnames, filenames in os.walk(root):
            # Prune skipped directories in-place
            dirnames[:] = [
                d for d in dirnames
                if d not in _SKIP_DIRS and not d.endswith(".egg-info")
            ]
            for fname in filenames:
                p = Path(dirpath) / fname
                if p.suffix in _SOURCE_EXTENSIONS:
                    collected.append(p)
        return collected

    def _read_lines(self, path: Path) -> list[str]:
        """Read file lines with caching.  Returns empty list on read errors."""
        key = str(path)
        if key not in self._file_cache:
            try:
                self._file_cache[key] = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                logger.warning("Could not read %s", key)
                self._file_cache[key] = []
        return self._file_cache[key]

    def _rel(self, path: Path) -> str:
        """Return path relative to cwd for display."""
        try:
            return str(path.relative_to(self.cwd))
        except ValueError:
            return str(path)

    @staticmethod
    def _safe_snippet(line: str, max_len: int = 120) -> str:
        """Return a sanitised snippet — strip card-like numbers to avoid leaking PAN."""
        sanitised = _PAN_PATTERN.sub("[REDACTED_PAN]", line)
        sanitised = sanitised.strip()
        if len(sanitised) > max_len:
            sanitised = sanitised[:max_len] + "..."
        return sanitised

    # -- PCI-3.4  PAN in logs / print ----------------------------------------

    def _check_pan_in_logs(self) -> list[PCIFinding]:
        """Detect card numbers logged or printed in plaintext."""
        findings: list[PCIFinding] = []
        for path in self._files:
            lines = self._read_lines(path)
            for idx, line in enumerate(lines, start=1):
                # Check for log/print statements that reference card variables
                if _LOG_STATEMENT.search(line) and _CARD_VAR_PATTERN.search(line):
                    findings.append(PCIFinding(
                        file=self._rel(path),
                        line=idx,
                        rule_id="PCI-3.4",
                        severity="critical",
                        description="Card variable referenced in log/print statement",
                        remediation="Remove card data from logs or mask it: card[-4:].rjust(len(card), '*')",
                        code_snippet=self._safe_snippet(line),
                    ))
                # Check for literal PAN patterns in log/print
                elif _LOG_STATEMENT.search(line) and _PAN_PATTERN.search(line):
                    findings.append(PCIFinding(
                        file=self._rel(path),
                        line=idx,
                        rule_id="PCI-3.4",
                        severity="critical",
                        description="Possible card number literal in log/print statement",
                        remediation="Never log full card numbers. Use masking: ****-****-****-1234",
                        code_snippet=self._safe_snippet(line),
                    ))
                # Card variable in f-string / format / % string (even outside log)
                elif _CARD_VAR_PATTERN.search(line) and re.search(r'(f["\']|\.format\(|%\s*\()', line):
                    if _LOG_STATEMENT.search(line) or re.search(r"print\s*\(", line):
                        findings.append(PCIFinding(
                            file=self._rel(path),
                            line=idx,
                            rule_id="PCI-3.4",
                            severity="critical",
                            description="Card variable interpolated in string used in log/print",
                            remediation="Mask card data before string interpolation",
                            code_snippet=self._safe_snippet(line),
                        ))
        return findings

    # -- PCI-6.5.3 / PCI-8.2.1  Weak encryption ----------------------------

    def _check_encryption(self) -> list[PCIFinding]:
        """Detect weak cryptographic algorithms."""
        findings: list[PCIFinding] = []
        for path in self._files:
            lines = self._read_lines(path)
            for idx, line in enumerate(lines, start=1):
                # Weak hash
                m = _WEAK_HASH.search(line)
                if m:
                    # Check context — if used for password/card/credential
                    context_lines = lines[max(0, idx - 4):idx + 2]
                    context_text = " ".join(context_lines)
                    if re.search(r"(password|card|credential|pan|secret|token|auth)", context_text, re.IGNORECASE):
                        findings.append(PCIFinding(
                            file=self._rel(path),
                            line=idx,
                            rule_id="PCI-8.2.1",
                            severity="critical",
                            description=f"Weak hash algorithm ({m.group().strip()}) used for sensitive data",
                            remediation="Use bcrypt, scrypt, or PBKDF2 for passwords; AES-256 for card data",
                            code_snippet=self._safe_snippet(line),
                        ))
                    else:
                        findings.append(PCIFinding(
                            file=self._rel(path),
                            line=idx,
                            rule_id="PCI-6.5.3",
                            severity="high",
                            description=f"Weak hash algorithm ({m.group().strip()}) detected",
                            remediation="Replace MD5/SHA1 with SHA-256+ or use bcrypt/scrypt for credentials",
                            code_snippet=self._safe_snippet(line),
                        ))

                # Weak cipher
                m = _WEAK_CIPHER.search(line)
                if m:
                    findings.append(PCIFinding(
                        file=self._rel(path),
                        line=idx,
                        rule_id="PCI-6.5.3",
                        severity="critical",
                        description=f"Weak cipher or mode ({m.group().strip()}) detected",
                        remediation="Use AES-256-GCM or AES-256-CBC with HMAC. Never use ECB mode, DES, or RC4.",
                        code_snippet=self._safe_snippet(line),
                    ))

                # Small key size
                km = _SMALL_KEY.search(line)
                if km:
                    key_bits = int(km.group(1))
                    if key_bits < 128:
                        findings.append(PCIFinding(
                            file=self._rel(path),
                            line=idx,
                            rule_id="PCI-6.5.3",
                            severity="high",
                            description=f"Key size {key_bits} bits is below the 128-bit minimum",
                            remediation="Use a minimum key size of 128 bits (256 recommended)",
                            code_snippet=self._safe_snippet(line),
                        ))
        return findings

    # -- PCI-3.4  Tokenization / raw PAN storage ----------------------------

    def _check_tokenization(self) -> list[PCIFinding]:
        """Detect raw PAN storage without tokenization or masking."""
        findings: list[PCIFinding] = []
        for path in self._files:
            lines = self._read_lines(path)
            for idx, line in enumerate(lines, start=1):
                # DB columns named card_number / pan without _token suffix
                if _DB_COLUMN_RAW_PAN.search(line):
                    findings.append(PCIFinding(
                        file=self._rel(path),
                        line=idx,
                        rule_id="PCI-3.4",
                        severity="critical",
                        description="Database column stores raw PAN without tokenization",
                        remediation="Use a tokenized column name (e.g. card_number_token) and store only tokens/masked values",
                        code_snippet=self._safe_snippet(line),
                    ))

                # Variable assignment of full PAN (16-digit string literal)
                if re.search(r"""(?:card_?number|pan|card_?no)\s*=\s*["']\d{13,19}["']""", line, re.IGNORECASE):
                    findings.append(PCIFinding(
                        file=self._rel(path),
                        line=idx,
                        rule_id="PCI-3.4",
                        severity="critical",
                        description="Full PAN assigned as string literal",
                        remediation="Never store full PAN. Use tokenization service or mask: ****-****-****-1234",
                        code_snippet=self._safe_snippet(line),
                    ))

        return findings

    # -- PCI-3.4  Card data in error messages --------------------------------

    def _check_error_messages(self) -> list[PCIFinding]:
        """Detect card details in error/exception messages."""
        findings: list[PCIFinding] = []
        for path in self._files:
            lines = self._read_lines(path)
            for idx, line in enumerate(lines, start=1):
                if _EXCEPTION_WITH_CARD.search(line):
                    findings.append(PCIFinding(
                        file=self._rel(path),
                        line=idx,
                        rule_id="PCI-3.4",
                        severity="high",
                        description="Card variable referenced in error/exception message",
                        remediation="Never include card data in error responses. Use masked values or reference IDs.",
                        code_snippet=self._safe_snippet(line),
                    ))
                # Also check plain raise/return with card vars in format strings
                elif re.search(r"raise\s+\w+", line) and _CARD_VAR_PATTERN.search(line):
                    if re.search(r'(f["\']|\.format\(|%\s)', line):
                        findings.append(PCIFinding(
                            file=self._rel(path),
                            line=idx,
                            rule_id="PCI-3.4",
                            severity="high",
                            description="Card variable interpolated in exception message",
                            remediation="Remove card data from exception messages. Log masked reference instead.",
                            code_snippet=self._safe_snippet(line),
                        ))
        return findings

    # -- PCI-4.1  Transport security -----------------------------------------

    def _check_transport_security(self) -> list[PCIFinding]:
        """Detect insecure transport for payment endpoints."""
        findings: list[PCIFinding] = []
        for path in self._files:
            lines = self._read_lines(path)
            for idx, line in enumerate(lines, start=1):
                # HTTP URLs for payment endpoints
                if _HTTP_URL.search(line):
                    findings.append(PCIFinding(
                        file=self._rel(path),
                        line=idx,
                        rule_id="PCI-4.1",
                        severity="critical",
                        description="Payment endpoint accessed over plain HTTP instead of HTTPS",
                        remediation="Always use https:// for payment-related endpoints",
                        code_snippet=self._safe_snippet(line),
                    ))

                # verify=False
                if _VERIFY_FALSE.search(line):
                    findings.append(PCIFinding(
                        file=self._rel(path),
                        line=idx,
                        rule_id="PCI-4.1",
                        severity="high",
                        description="SSL/TLS certificate verification disabled (verify=False)",
                        remediation="Remove verify=False. Use proper CA certificates.",
                        code_snippet=self._safe_snippet(line),
                    ))

                # SSL disabled patterns
                if _SSL_DISABLE.search(line):
                    findings.append(PCIFinding(
                        file=self._rel(path),
                        line=idx,
                        rule_id="PCI-4.1",
                        severity="high",
                        description="SSL/TLS verification or warnings suppressed",
                        remediation="Do not disable SSL verification or suppress security warnings.",
                        code_snippet=self._safe_snippet(line),
                    ))
        return findings

    # -- PCI-6.5.3 / PCI-8.2.1  Key management ------------------------------

    def _check_key_management(self) -> list[PCIFinding]:
        """Detect hardcoded keys and weak key derivation."""
        findings: list[PCIFinding] = []
        for path in self._files:
            lines = self._read_lines(path)
            for idx, line in enumerate(lines, start=1):
                if _HARDCODED_KEY.search(line):
                    findings.append(PCIFinding(
                        file=self._rel(path),
                        line=idx,
                        rule_id="PCI-6.5.3",
                        severity="critical",
                        description="Hardcoded encryption/secret key detected",
                        remediation="Store keys in a secrets manager (Vault, AWS KMS, etc.). Never commit keys to code.",
                        code_snippet=self._safe_snippet(line),
                    ))

                if _WEAK_KDF.search(line):
                    findings.append(PCIFinding(
                        file=self._rel(path),
                        line=idx,
                        rule_id="PCI-8.2.1",
                        severity="high",
                        description="Weak key derivation — simple hash used for credential/key",
                        remediation="Use PBKDF2, bcrypt, scrypt, or Argon2 for key derivation.",
                        code_snippet=self._safe_snippet(line),
                    ))
        return findings

    # -- PCI-6.5.10  Access control ------------------------------------------

    def _check_access_control(self) -> list[PCIFinding]:
        """Detect payment endpoints without auth or rate limiting."""
        findings: list[PCIFinding] = []
        for path in self._files:
            lines = self._read_lines(path)
            for idx, line in enumerate(lines, start=1):
                if _PAYMENT_ENDPOINT.search(line):
                    # Look backwards for auth decorator (up to 5 lines before)
                    context_before = lines[max(0, idx - 6):idx - 1]
                    has_auth = any(_AUTH_DECORATOR.search(cl) for cl in context_before)
                    has_rate_limit = any(_RATE_LIMIT_DECORATOR.search(cl) for cl in context_before)

                    if not has_auth:
                        findings.append(PCIFinding(
                            file=self._rel(path),
                            line=idx,
                            rule_id="PCI-6.5.10",
                            severity="high",
                            description="Payment endpoint without authentication decorator",
                            remediation="Add authentication (e.g. @requires_auth, Depends(get_current_user)) to all payment endpoints.",
                            code_snippet=self._safe_snippet(line),
                        ))
                    if not has_rate_limit:
                        findings.append(PCIFinding(
                            file=self._rel(path),
                            line=idx,
                            rule_id="PCI-6.5.10",
                            severity="medium",
                            description="Payment endpoint without rate limiting",
                            remediation="Add rate limiting to prevent card testing / brute force attacks.",
                            code_snippet=self._safe_snippet(line),
                        ))
        return findings

    # -- scoring & summary ---------------------------------------------------

    @staticmethod
    def _calculate_score(findings: list[PCIFinding]) -> int:
        """Calculate 0-100 compliance score from findings.

        Deductions:
          - critical: 15 points each (max 60)
          - high:     8 points each  (max 40)
          - medium:   3 points each  (max 20)
          - low:      1 point each   (max 10)
        """
        deductions = 0
        severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for f in findings:
            severity_counts[f.severity] = severity_counts.get(f.severity, 0) + 1

        deductions += min(severity_counts.get("critical", 0) * 15, 60)
        deductions += min(severity_counts.get("high", 0) * 8, 40)
        deductions += min(severity_counts.get("medium", 0) * 3, 20)
        deductions += min(severity_counts.get("low", 0) * 1, 10)

        return max(0, 100 - deductions)

    @staticmethod
    def _build_summary(findings: list[PCIFinding], score: int, elapsed: float) -> str:
        sev = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for f in findings:
            sev[f.severity] = sev.get(f.severity, 0) + 1

        parts = []
        if sev["critical"]:
            parts.append(f"{sev['critical']} critical")
        if sev["high"]:
            parts.append(f"{sev['high']} high")
        if sev["medium"]:
            parts.append(f"{sev['medium']} medium")
        if sev["low"]:
            parts.append(f"{sev['low']} low")

        finding_str = ", ".join(parts) if parts else "no issues"
        return f"Score: {score}/100 | {finding_str} | {len(findings)} total findings | {elapsed:.2f}s"


# ---------------------------------------------------------------------------
# Report Formatter
# ---------------------------------------------------------------------------

_SEVERITY_COLORS = {
    "critical": "\033[91m",  # red
    "high": "\033[93m",      # yellow
    "medium": "\033[94m",    # blue
    "low": "\033[90m",       # gray
}
_SEVERITY_ICONS = {
    "critical": "!!",
    "high": "! ",
    "medium": "* ",
    "low": "- ",
}
_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"


def format_pci_report(report: PCIReport, *, use_color: bool = True) -> str:
    """Format a PCIReport for terminal display with coloured severity and score bar.

    Output layout:
        +-- PCI-DSS Compliance Scan ----------------------+
        | Score: 72/100 ########..                        |
        | Critical: 2  High: 3  Medium: 5  Low: 1        |
        +-------------------------------------------------+
        | !! PCI-3.4 CRITICAL                             |
        |   src/payment.py:45                             |
        |   Card number logged in plaintext               |
        |   Fix: Use masking -- card[-4:].rjust(16,'*')   |
        +-------------------------------------------------+
    """
    lines: list[str] = []
    W = 60  # box width

    def _c(color: str, text: str) -> str:
        return f"{color}{text}{_RESET}" if use_color else text

    # Header
    title = " PCI-DSS Compliance Scan "
    border = "+" + "-" * (W - 2) + "+"
    title_line = "+" + "-" * ((W - 2 - len(title)) // 2) + title + "-" * ((W - 2 - len(title) + 1) // 2) + "+"
    lines.append(title_line)

    # Score bar
    filled = report.score * 20 // 100
    bar = "#" * filled + "." * (20 - filled)
    score_color = "\033[92m" if report.score >= 80 else ("\033[93m" if report.score >= 50 else "\033[91m")
    score_str = f"Score: {_c(score_color, f'{report.score}/100')} [{bar}]"
    lines.append(f"| {score_str}")

    # Severity summary
    sev = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for f in report.findings:
        sev[f.severity] = sev.get(f.severity, 0) + 1

    sev_parts = []
    for s in ("critical", "high", "medium", "low"):
        label = s.capitalize()
        count = sev[s]
        col = _SEVERITY_COLORS.get(s, "")
        sev_parts.append(f"{_c(col, label)}: {count}")
    lines.append(f"| {' '.join(sev_parts)}")
    lines.append(f"| Scan time: {report.scan_time:.2f}s | Files scanned: {len(set(f.file for f in report.findings)) or 'all'}")
    lines.append(border)

    # Passed rules
    if report.passed_rules:
        lines.append(f"| {_c(_BOLD, 'Passed rules:')}")
        for r in report.passed_rules:
            desc = PCI_RULES.get(r, "")
            lines.append(f"|   {_c(chr(27) + '[92m', 'OK')} {r} — {desc}")
        lines.append("|")

    # Failed rules
    if report.failed_rules:
        lines.append(f"| {_c(_BOLD, 'Failed rules:')}")
        for r in report.failed_rules:
            desc = PCI_RULES.get(r, "")
            lines.append(f"|   {_c(chr(27) + '[91m', 'FAIL')} {r} — {desc}")
        lines.append(border)

    # Findings (grouped by severity)
    if report.findings:
        for severity in ("critical", "high", "medium", "low"):
            group = [f for f in report.findings if f.severity == severity]
            if not group:
                continue
            icon = _SEVERITY_ICONS.get(severity, "  ")
            col = _SEVERITY_COLORS.get(severity, "")
            lines.append(f"| {_c(col, f'{icon}{severity.upper()}')} ({len(group)} finding{'s' if len(group) != 1 else ''})")
            lines.append("|")
            for f in group:
                lines.append(f"|   {_c(_BOLD, f.rule_id)} {f.file}:{f.line}")
                lines.append(f"|     {f.description}")
                if f.code_snippet:
                    lines.append(f"|     {_c(_DIM, f.code_snippet)}")
                lines.append(f"|     Fix: {f.remediation}")
                lines.append("|")
            lines.append(border)
    else:
        lines.append(f"| {_c(chr(27) + '[92m', 'No PCI-DSS violations found.')}")
        lines.append(border)

    lines.append("")
    return "\n".join(lines)


def pci_report_to_json(report: PCIReport) -> dict:
    """Convert a PCIReport to a JSON-serializable dict."""
    return {
        "score": report.score,
        "summary": report.summary,
        "scan_time": round(report.scan_time, 3),
        "passed_rules": report.passed_rules,
        "failed_rules": report.failed_rules,
        "findings": [
            {
                "file": f.file,
                "line": f.line,
                "rule_id": f.rule_id,
                "severity": f.severity,
                "description": f.description,
                "remediation": f.remediation,
                "code_snippet": f.code_snippet,
            }
            for f in report.findings
        ],
    }
