"""Data Privacy Scanner — detect PII exposure, consent gaps, and regulation violations.

Scans codebase for personal data in logs, unencrypted PII storage, missing
consent tracking, absent data deletion endpoints, cross-border data transfer,
and Indian ID patterns (Aadhaar/PAN) per DPDP Act.

SECURITY: This scanner MUST NOT log or store actual PII found.
Only file:line references are recorded in findings.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.security.privacy_scanner")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class PrivacyFinding:
    file: str
    line: int
    data_type: str  # "email", "phone", "name", "address", "pan", "aadhaar"
    issue: str
    severity: str  # critical | high | medium | low
    regulation: str  # "GDPR", "DPDP", "PCI", "ALL"


@dataclass
class PrivacyReport:
    findings: list[PrivacyFinding]
    regulation: str
    files_scanned: int
    score: int  # 0-100 (higher = more compliant)
    summary: str


# ---------------------------------------------------------------------------
# Compiled patterns — we NEVER capture actual values, just detect presence.
# ---------------------------------------------------------------------------

# PII in log/print statements
_LOG_STATEMENT = re.compile(
    r"(?:logger\.\w+|logging\.\w+|print|console\.log|console\.info"
    r"|console\.warn|console\.error|System\.out|log\.\w+)\s*\(",
    re.IGNORECASE,
)

_EMAIL_VAR = re.compile(
    r"\b(?:email|e_?mail|user_?email|customer_?email|mail_?address)\b",
    re.IGNORECASE,
)
_PHONE_VAR = re.compile(
    r"\b(?:phone|mobile|cell|phone_?number|mobile_?number|contact_?number|msisdn)\b",
    re.IGNORECASE,
)
_NAME_VAR = re.compile(
    r"\b(?:full_?name|first_?name|last_?name|user_?name|customer_?name"
    r"|person_?name|real_?name|display_?name)\b",
    re.IGNORECASE,
)
_ADDRESS_VAR = re.compile(
    r"\b(?:address|street|postal|zip_?code|city|state|pincode|pin_?code"
    r"|mailing_?address|home_?address|billing_?address)\b",
    re.IGNORECASE,
)

_PII_VARS = {
    "email": _EMAIL_VAR,
    "phone": _PHONE_VAR,
    "name": _NAME_VAR,
    "address": _ADDRESS_VAR,
}

# Aadhaar pattern (12-digit number, may have spaces)
_AADHAAR_VAR = re.compile(
    r"\b(?:aadhaar|aadhar|uidai|uid_?number|aadhaar_?number|aadhaar_?no)\b",
    re.IGNORECASE,
)
_AADHAAR_PATTERN = re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")

# PAN pattern (ABCDE1234F)
_PAN_VAR = re.compile(
    r"\b(?:pan_?number|pan_?no|pan_?card|income_?tax_?id)\b",
    re.IGNORECASE,
)
_PAN_PATTERN = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")

# Encryption / hashing indicators
_ENCRYPTION_PATTERN = re.compile(
    r"(?:encrypt|decrypt|cipher|aes|rsa|hash|sha256|sha512|bcrypt|argon2|scrypt"
    r"|fernet|kms|vault\.read|vault\.write|crypto\.subtle)",
    re.IGNORECASE,
)

# Database / storage patterns
_STORAGE_PATTERN = re.compile(
    r"(?:\.save\(|\.insert|\.create\(|\.update\(|\.put_?item|\.set\(|INSERT\s+INTO"
    r"|UPDATE\s+\w+\s+SET|\.store\(|\.write\(|redis\.set|cache\.set)",
    re.IGNORECASE,
)

# Consent tracking patterns
_CONSENT_PATTERN = re.compile(
    r"(?:consent|gdpr_?consent|user_?consent|data_?consent|opt_?in|opt_?out"
    r"|privacy_?consent|terms_?accepted|cookie_?consent|consent_?flag)",
    re.IGNORECASE,
)

# Data deletion patterns
_DELETE_ENDPOINT = re.compile(
    r"""(?:@\s*(?:app|router)\s*\.\s*delete\s*\(\s*[\"'][^\"']*(?:user|account|profile|data|personal)[^\"']*[\"']"""
    r"""|def\s+delete_?user|def\s+erase_?data|def\s+forget_?me"""
    r"""|def\s+right_?to_?erasure|def\s+purge_?user|def\s+anonymize)""",
    re.IGNORECASE,
)

# External URL patterns (cross-border)
_EXTERNAL_URL = re.compile(
    r"""(?:https?://[a-zA-Z0-9._-]+\.(?:com|io|net|org|eu|us|uk|de|cn|in|jp)"""
    r"""|requests\.(?:post|put|patch)\s*\(\s*[\"']https?://"""
    r"""|fetch\s*\(\s*[\"']https?://"""
    r"""|http\.post|http\.put|axios\.post|axios\.put)""",
    re.IGNORECASE,
)

# File extensions to scan
_SCAN_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".java", ".rb", ".kt"}

# Directories to skip
_SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv", "env",
    ".tox", ".mypy_cache", ".pytest_cache", "dist", "build", ".next",
    "vendor", "target", ".gradle",
}

# Regulation → applicable checks
_REGULATION_CHECKS = {
    "gdpr": {"pii_logs", "pii_storage", "consent", "deletion", "cross_border"},
    "dpdp": {"pii_logs", "pii_storage", "consent", "deletion", "aadhaar_pan"},
    "pci": {"pii_logs", "pii_storage", "aadhaar_pan"},
    "all": {"pii_logs", "pii_storage", "consent", "deletion", "cross_border", "aadhaar_pan"},
}


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


class PrivacyScanner:
    """Scan codebase for data privacy violations."""

    def __init__(self, cwd: str, regulation: str = "all") -> None:
        self.cwd = cwd
        self.regulation = regulation.lower()
        self._files: list[Path] = []

    def scan(self) -> PrivacyReport:
        """Run full privacy scan and return report."""
        logger.info("Starting privacy scan (%s) on %s", self.regulation, self.cwd)
        self._files = self._collect_files()
        checks = _REGULATION_CHECKS.get(self.regulation, _REGULATION_CHECKS["all"])

        findings: list[PrivacyFinding] = []

        for fpath in self._files:
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
                lines = content.splitlines()
                rel = str(fpath.relative_to(self.cwd))
            except (OSError, UnicodeDecodeError):
                continue

            if "pii_logs" in checks:
                findings.extend(self._check_pii_in_logs(rel, lines))
            if "pii_storage" in checks:
                findings.extend(self._check_pii_storage(rel, lines))
            if "aadhaar_pan" in checks:
                findings.extend(self._check_aadhaar_pan(rel, lines))
            if "cross_border" in checks:
                findings.extend(self._check_cross_border(rel, lines))

        if "consent" in checks:
            findings.extend(self._check_consent_tracking())
        if "deletion" in checks:
            findings.extend(self._check_data_deletion())

        # Deduplicate
        seen: set[tuple[str, int, str]] = set()
        unique: list[PrivacyFinding] = []
        for f in findings:
            key = (f.file, f.line, f.data_type)
            if key not in seen:
                seen.add(key)
                unique.append(f)

        issue_count = len(unique)
        max_score = max(len(self._files) * 2, 1)
        score = max(0, 100 - int((issue_count / max_score) * 100))

        regulation_label = self.regulation.upper()
        summary = (
            f"Scanned {len(self._files)} files for {regulation_label} compliance. "
            f"Found {issue_count} finding(s). Score: {score}/100."
        )
        logger.info(summary)

        return PrivacyReport(
            findings=unique,
            regulation=regulation_label,
            files_scanned=len(self._files),
            score=score,
            summary=summary,
        )

    # ------------------------------------------------------------------
    # File collection
    # ------------------------------------------------------------------

    def _collect_files(self) -> list[Path]:
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
    # Check: PII in log statements
    # ------------------------------------------------------------------

    def _check_pii_in_logs(self, rel_path: str, lines: list[str]) -> list[PrivacyFinding]:
        findings: list[PrivacyFinding] = []
        for idx, line in enumerate(lines, start=1):
            if not _LOG_STATEMENT.search(line):
                continue
            for pii_type, pattern in _PII_VARS.items():
                if pattern.search(line):
                    findings.append(PrivacyFinding(
                        file=rel_path,
                        line=idx,
                        data_type=pii_type,
                        issue=f"PII ({pii_type}) found in log statement",
                        severity="high",
                        regulation=self._regulation_for_pii(pii_type),
                    ))
        return findings

    # ------------------------------------------------------------------
    # Check: PII stored without encryption
    # ------------------------------------------------------------------

    def _check_pii_storage(self, rel_path: str, lines: list[str]) -> list[PrivacyFinding]:
        findings: list[PrivacyFinding] = []
        full_text = "\n".join(lines)
        has_encryption = bool(_ENCRYPTION_PATTERN.search(full_text))

        for idx, line in enumerate(lines, start=1):
            if not _STORAGE_PATTERN.search(line):
                continue
            for pii_type, pattern in _PII_VARS.items():
                if pattern.search(line) and not has_encryption:
                    findings.append(PrivacyFinding(
                        file=rel_path,
                        line=idx,
                        data_type=pii_type,
                        issue=f"PII ({pii_type}) stored without apparent encryption",
                        severity="high",
                        regulation=self._regulation_for_pii(pii_type),
                    ))
        return findings

    # ------------------------------------------------------------------
    # Check: consent tracking
    # ------------------------------------------------------------------

    def _check_consent_tracking(self) -> list[PrivacyFinding]:
        findings: list[PrivacyFinding] = []
        has_consent = False
        has_user_data_collection = False
        user_data_file = ""
        user_data_line = 0

        for fpath in self._files:
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
                lines = content.splitlines()
                rel = str(fpath.relative_to(self.cwd))
            except (OSError, UnicodeDecodeError):
                continue

            if _CONSENT_PATTERN.search(content):
                has_consent = True

            for idx, line in enumerate(lines, start=1):
                if _STORAGE_PATTERN.search(line):
                    for pii_type, pattern in _PII_VARS.items():
                        if pattern.search(line):
                            has_user_data_collection = True
                            if not user_data_file:
                                user_data_file = rel
                                user_data_line = idx
                            break

        if has_user_data_collection and not has_consent:
            findings.append(PrivacyFinding(
                file=user_data_file or "<project>",
                line=user_data_line,
                data_type="consent",
                issue="User data collected without consent tracking mechanism",
                severity="high",
                regulation="GDPR",
            ))
        return findings

    # ------------------------------------------------------------------
    # Check: data deletion endpoint (right to erasure)
    # ------------------------------------------------------------------

    def _check_data_deletion(self) -> list[PrivacyFinding]:
        findings: list[PrivacyFinding] = []
        has_delete = False
        has_user_model = False
        user_model_file = ""
        user_model_line = 0

        user_model_pattern = re.compile(
            r"(?:class\s+User|class\s+Customer|class\s+Account|class\s+Profile"
            r"|model\s+User|model\s+Customer|CREATE\s+TABLE\s+users)",
            re.IGNORECASE,
        )

        for fpath in self._files:
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
                lines = content.splitlines()
                rel = str(fpath.relative_to(self.cwd))
            except (OSError, UnicodeDecodeError):
                continue

            if _DELETE_ENDPOINT.search(content):
                has_delete = True

            for idx, line in enumerate(lines, start=1):
                if user_model_pattern.search(line):
                    has_user_model = True
                    if not user_model_file:
                        user_model_file = rel
                        user_model_line = idx
                    break

        if has_user_model and not has_delete:
            findings.append(PrivacyFinding(
                file=user_model_file or "<project>",
                line=user_model_line,
                data_type="deletion",
                issue="User data model found but no data deletion endpoint (right to erasure)",
                severity="high",
                regulation="GDPR",
            ))
        return findings

    # ------------------------------------------------------------------
    # Check: cross-border data transfer
    # ------------------------------------------------------------------

    def _check_cross_border(self, rel_path: str, lines: list[str]) -> list[PrivacyFinding]:
        findings: list[PrivacyFinding] = []
        for idx, line in enumerate(lines, start=1):
            if _EXTERNAL_URL.search(line):
                for pii_type, pattern in _PII_VARS.items():
                    # Check surrounding context (5 lines)
                    start = max(0, idx - 6)
                    end = min(len(lines), idx + 4)
                    context = "\n".join(lines[start:end])
                    if pattern.search(context):
                        findings.append(PrivacyFinding(
                            file=rel_path,
                            line=idx,
                            data_type=pii_type,
                            issue=f"PII ({pii_type}) may be sent to external service — cross-border risk",
                            severity="medium",
                            regulation="GDPR",
                        ))
                        break  # one finding per line
        return findings

    # ------------------------------------------------------------------
    # Check: Aadhaar / PAN patterns (DPDP Act)
    # ------------------------------------------------------------------

    def _check_aadhaar_pan(self, rel_path: str, lines: list[str]) -> list[PrivacyFinding]:
        findings: list[PrivacyFinding] = []
        for idx, line in enumerate(lines, start=1):
            # Aadhaar variable in logs
            if _LOG_STATEMENT.search(line) and _AADHAAR_VAR.search(line):
                findings.append(PrivacyFinding(
                    file=rel_path,
                    line=idx,
                    data_type="aadhaar",
                    issue="Aadhaar number logged — DPDP Act violation",
                    severity="critical",
                    regulation="DPDP",
                ))
            # PAN variable in logs
            if _LOG_STATEMENT.search(line) and _PAN_VAR.search(line):
                findings.append(PrivacyFinding(
                    file=rel_path,
                    line=idx,
                    data_type="pan",
                    issue="PAN number logged — DPDP Act violation",
                    severity="critical",
                    regulation="DPDP",
                ))
            # Aadhaar stored without encryption
            if _STORAGE_PATTERN.search(line) and _AADHAAR_VAR.search(line):
                # Check if encryption is in nearby context
                start = max(0, idx - 11)
                end = min(len(lines), idx + 5)
                context = "\n".join(lines[start:end])
                if not _ENCRYPTION_PATTERN.search(context):
                    findings.append(PrivacyFinding(
                        file=rel_path,
                        line=idx,
                        data_type="aadhaar",
                        issue="Aadhaar number stored without encryption",
                        severity="critical",
                        regulation="DPDP",
                    ))
            # PAN stored without encryption
            if _STORAGE_PATTERN.search(line) and _PAN_VAR.search(line):
                start = max(0, idx - 11)
                end = min(len(lines), idx + 5)
                context = "\n".join(lines[start:end])
                if not _ENCRYPTION_PATTERN.search(context):
                    findings.append(PrivacyFinding(
                        file=rel_path,
                        line=idx,
                        data_type="pan",
                        issue="PAN number stored without encryption",
                        severity="critical",
                        regulation="DPDP",
                    ))
        return findings

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _regulation_for_pii(pii_type: str) -> str:
        if pii_type in ("aadhaar", "pan"):
            return "DPDP"
        return "GDPR"


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

_SEVERITY_ICON = {
    "critical": "\u2620\ufe0f ",
    "high": "\u26a0\ufe0f ",
    "medium": "\u26ab",
    "low": "\u2139\ufe0f ",
}


def format_privacy_report(report: PrivacyReport) -> str:
    """Format report as terminal-friendly text."""
    lines: list[str] = []
    lines.append(f"\n  Privacy Scan Report ({report.regulation})")
    lines.append("  " + "=" * 50)
    lines.append(f"  Files scanned:  {report.files_scanned}")
    lines.append(f"  Findings:       {len(report.findings)}")
    lines.append(f"  Score:          {report.score}/100")
    lines.append("")

    if not report.findings:
        lines.append("  No privacy findings — looking good!")
        return "\n".join(lines)

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    sorted_findings = sorted(report.findings, key=lambda f: severity_order.get(f.severity, 5))

    for f in sorted_findings:
        icon = _SEVERITY_ICON.get(f.severity, "")
        lines.append(f"  {icon} [{f.severity.upper()}] {f.data_type} — {f.regulation}")
        lines.append(f"     File: {f.file}:{f.line}")
        lines.append(f"     Issue: {f.issue}")
        lines.append("")

    return "\n".join(lines)


def privacy_report_to_json(report: PrivacyReport) -> dict:
    """Convert report to JSON-serializable dict."""
    return {
        "regulation": report.regulation,
        "files_scanned": report.files_scanned,
        "score": report.score,
        "summary": report.summary,
        "findings": [
            {
                "file": f.file,
                "line": f.line,
                "data_type": f.data_type,
                "issue": f.issue,
                "severity": f.severity,
                "regulation": f.regulation,
            }
            for f in report.findings
        ],
    }
