"""Enhanced OWASP Checker — line-level findings with auto-fix suggestions.

Extends the basic OWASP scanner with precise line-level attribution,
severity scoring, and concrete auto-fix code snippets for each finding.

Usage:
    from code_agents.security.owasp_checker import OWASPChecker, OWASPCheckerConfig
    checker = OWASPChecker(OWASPCheckerConfig(cwd="/path/to/repo"))
    result = checker.analyze()
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.security.owasp_checker")

# ---------------------------------------------------------------------------
# OWASP Top 10 (2021) categories
# ---------------------------------------------------------------------------

OWASP_CATEGORIES = {
    "A01": "Broken Access Control",
    "A02": "Cryptographic Failures",
    "A03": "Injection",
    "A04": "Insecure Design",
    "A05": "Security Misconfiguration",
    "A06": "Vulnerable Components",
    "A07": "Authentication Failures",
    "A08": "Software Integrity Failures",
    "A09": "Logging Failures",
    "A10": "SSRF",
}

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class OWASPCheckerConfig:
    cwd: str = "."
    max_files: int = 500
    categories: list[str] = field(default_factory=lambda: list(OWASP_CATEGORIES.keys()))


@dataclass
class OWASPFinding:
    """A single OWASP finding with auto-fix."""
    file: str
    line: int
    category: str  # A01-A10
    category_name: str
    severity: str  # critical | high | medium | low
    description: str
    code_snippet: str = ""
    fix_suggestion: str = ""
    fix_code: str = ""
    confidence: str = "high"  # high | medium | low


@dataclass
class OWASPCheckerReport:
    """Full OWASP checker result."""
    files_scanned: int = 0
    total_findings: int = 0
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    findings: list[OWASPFinding] = field(default_factory=list)
    category_breakdown: dict[str, int] = field(default_factory=dict)
    summary: str = ""


# ---------------------------------------------------------------------------
# Detection rules: (category, regex, severity, description, fix_suggestion, fix_code)
# ---------------------------------------------------------------------------

OWASP_RULES: list[dict] = [
    # A01 — Broken Access Control
    {
        "category": "A01",
        "pattern": re.compile(r"@app\.route.*methods.*(?:DELETE|PUT|PATCH).*\n(?:(?!@login_required|@require_auth).)"),
        "severity": "high",
        "description": "Destructive endpoint without access control decorator",
        "fix_suggestion": "Add authentication/authorization decorator",
        "fix_code": "@login_required\n@require_permissions('admin')",
    },
    {
        "category": "A01",
        "pattern": re.compile(r"(?:CORS|cors)\s*\(\s*\*|allow_origins\s*=\s*\[?\s*['\"]?\*"),
        "severity": "medium",
        "description": "Wildcard CORS allows any origin",
        "fix_suggestion": "Restrict CORS to specific origins",
        "fix_code": 'allow_origins=["https://yourdomain.com"]',
    },
    # A02 — Cryptographic Failures
    {
        "category": "A02",
        "pattern": re.compile(r"(?:md5|sha1)\s*\(", re.IGNORECASE),
        "severity": "high",
        "description": "Weak hash algorithm (MD5/SHA1)",
        "fix_suggestion": "Use SHA-256 or bcrypt for passwords",
        "fix_code": "import hashlib\nhashlib.sha256(data).hexdigest()",
    },
    {
        "category": "A02",
        "pattern": re.compile(r"(?:DES|RC4|Blowfish)\b", re.IGNORECASE),
        "severity": "high",
        "description": "Weak encryption algorithm",
        "fix_suggestion": "Use AES-256-GCM",
        "fix_code": "from cryptography.fernet import Fernet",
    },
    # A03 — Injection
    {
        "category": "A03",
        "pattern": re.compile(r'(?:execute|query)\s*\(\s*f["\']|(?:execute|query)\s*\(\s*["\'].*%\s'),
        "severity": "critical",
        "description": "SQL injection via string interpolation",
        "fix_suggestion": "Use parameterised queries",
        "fix_code": 'cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))',
    },
    {
        "category": "A03",
        "pattern": re.compile(r"os\.system\s*\(\s*f['\"]|subprocess\.\w+\s*\(\s*f['\"]"),
        "severity": "critical",
        "description": "OS command injection via string interpolation",
        "fix_suggestion": "Use subprocess with list args, shlex.quote",
        "fix_code": "subprocess.run([cmd, arg1, arg2], check=True)",
    },
    {
        "category": "A03",
        "pattern": re.compile(r"eval\s*\(\s*(?:request|input|params|req\.)"),
        "severity": "critical",
        "description": "Code injection via eval on user input",
        "fix_suggestion": "Never eval user input; use ast.literal_eval for data",
        "fix_code": "import ast\nresult = ast.literal_eval(user_input)",
    },
    # A05 — Security Misconfiguration
    {
        "category": "A05",
        "pattern": re.compile(r"DEBUG\s*=\s*True", re.IGNORECASE),
        "severity": "medium",
        "description": "Debug mode enabled (may leak stack traces)",
        "fix_suggestion": "Disable debug in production",
        "fix_code": "DEBUG = os.getenv('DEBUG', 'false').lower() == 'true'",
    },
    {
        "category": "A05",
        "pattern": re.compile(r"(?:verify\s*=\s*False|VERIFY_SSL\s*=\s*False)", re.IGNORECASE),
        "severity": "high",
        "description": "SSL verification disabled",
        "fix_suggestion": "Enable SSL verification",
        "fix_code": "verify=True  # or provide CA bundle path",
    },
    # A07 — Authentication Failures
    {
        "category": "A07",
        "pattern": re.compile(r"(?:password|secret)\s*==\s*['\"]", re.IGNORECASE),
        "severity": "critical",
        "description": "Hardcoded password comparison",
        "fix_suggestion": "Use constant-time comparison with hashed passwords",
        "fix_code": "import hmac\nhmac.compare_digest(stored_hash, computed_hash)",
    },
    # A09 — Logging Failures
    {
        "category": "A09",
        "pattern": re.compile(r"(?:except|catch)\s*(?:\w+\s*)?:\s*\n\s*pass"),
        "severity": "medium",
        "description": "Silent exception swallowing (no logging)",
        "fix_suggestion": "Log the exception",
        "fix_code": "except Exception as exc:\n    logger.exception('Unexpected error: %s', exc)",
    },
    # A10 — SSRF
    {
        "category": "A10",
        "pattern": re.compile(r"requests\.(?:get|post|put|delete)\s*\(\s*(?:request\.|params\.|user_)"),
        "severity": "high",
        "description": "SSRF via user-controlled URL",
        "fix_suggestion": "Validate/allowlist URLs before fetching",
        "fix_code": "if not is_allowed_url(url):\n    raise ValueError('URL not in allowlist')",
    },
]


# ---------------------------------------------------------------------------
# OWASPChecker
# ---------------------------------------------------------------------------


class OWASPChecker:
    """Enhanced OWASP Top 10 checker with auto-fix suggestions."""

    def __init__(self, config: Optional[OWASPCheckerConfig] = None):
        self.config = config or OWASPCheckerConfig()

    def analyze(self) -> OWASPCheckerReport:
        """Run OWASP analysis with line-level findings."""
        logger.info("Starting OWASP analysis in %s", self.config.cwd)
        report = OWASPCheckerReport()
        root = Path(self.config.cwd)
        active_rules = [
            r for r in OWASP_RULES if r["category"] in self.config.categories
        ]

        count = 0
        for ext in ("*.py", "*.js", "*.ts", "*.java", "*.go"):
            for fpath in root.rglob(ext):
                if count >= self.config.max_files:
                    break
                count += 1
                if any(p.startswith(".") or p in ("node_modules", "__pycache__") for p in fpath.parts):
                    continue
                rel = str(fpath.relative_to(root))
                try:
                    lines = fpath.read_text(errors="replace").splitlines()
                except Exception:
                    continue
                for idx, line in enumerate(lines, 1):
                    for rule in active_rules:
                        if rule["pattern"].search(line):
                            cat = rule["category"]
                            report.findings.append(OWASPFinding(
                                file=rel,
                                line=idx,
                                category=cat,
                                category_name=OWASP_CATEGORIES.get(cat, "Unknown"),
                                severity=rule["severity"],
                                description=rule["description"],
                                code_snippet=line.strip(),
                                fix_suggestion=rule["fix_suggestion"],
                                fix_code=rule["fix_code"],
                            ))

        report.files_scanned = count
        report.total_findings = len(report.findings)
        report.critical_count = sum(1 for f in report.findings if f.severity == "critical")
        report.high_count = sum(1 for f in report.findings if f.severity == "high")
        report.medium_count = sum(1 for f in report.findings if f.severity == "medium")
        report.low_count = sum(1 for f in report.findings if f.severity == "low")

        # Category breakdown
        for f in report.findings:
            key = f"{f.category} {f.category_name}"
            report.category_breakdown[key] = report.category_breakdown.get(key, 0) + 1

        report.summary = (
            f"Scanned {report.files_scanned} files, {report.total_findings} OWASP findings "
            f"({report.critical_count} critical, {report.high_count} high, "
            f"{report.medium_count} medium, {report.low_count} low)."
        )
        logger.info("OWASP analysis complete: %s", report.summary)
        return report


def format_owasp_report(report: OWASPCheckerReport) -> str:
    """Render OWASP report with fix suggestions."""
    lines = ["=== OWASP Checker Report ===", ""]
    lines.append(f"Files scanned:  {report.files_scanned}")
    lines.append(f"Findings:       {report.total_findings}")
    lines.append("")

    if report.category_breakdown:
        lines.append("Category breakdown:")
        for cat, cnt in sorted(report.category_breakdown.items()):
            lines.append(f"  {cat}: {cnt}")
        lines.append("")

    for f in report.findings:
        sev = f.severity.upper()
        lines.append(f"  [{sev}] {f.category} {f.file}:{f.line}")
        lines.append(f"    {f.description}")
        lines.append(f"    Code: {f.code_snippet}")
        lines.append(f"    Fix:  {f.fix_suggestion}")
        if f.fix_code:
            for fc_line in f.fix_code.splitlines():
                lines.append(f"          {fc_line}")
        lines.append("")

    lines.append(report.summary)
    return "\n".join(lines)
