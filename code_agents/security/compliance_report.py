"""Compliance Report Generator — PCI-DSS, SOC2, GDPR compliance reports.

Aggregates results from security scanner, privacy scanner, rate limit auditor,
and other analysis tools to produce compliance reports mapped to standard
control frameworks.

SECURITY: Only file:line references are stored — no actual secrets or PII.
"""

from __future__ import annotations

import json as _json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.security.compliance_report")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ComplianceControl:
    id: str
    name: str
    status: str  # "pass", "fail", "partial", "not_applicable"
    evidence: list[str]
    notes: str = ""


@dataclass
class ComplianceReport:
    standard: str
    date: str
    score: float  # 0-100
    controls: list[ComplianceControl]
    summary: str = ""


# ---------------------------------------------------------------------------
# Control definitions
# ---------------------------------------------------------------------------

PCI_CONTROLS = {
    "PCI-1": "Install and maintain network security controls",
    "PCI-2": "Apply secure configurations to all system components",
    "PCI-3": "Protect stored account data",
    "PCI-4": "Protect cardholder data with strong cryptography during transmission",
    "PCI-5": "Protect all systems against malware",
    "PCI-6": "Develop and maintain secure systems and software",
    "PCI-7": "Restrict access to system components by business need-to-know",
    "PCI-8": "Identify users and authenticate access to system components",
    "PCI-9": "Restrict physical access to cardholder data",
    "PCI-10": "Log and monitor all access to system components and cardholder data",
    "PCI-11": "Test security of systems and networks regularly",
    "PCI-12": "Support information security with organizational policies",
}

SOC2_CONTROLS = {
    "CC1": "Control environment",
    "CC2": "Communication and information",
    "CC3": "Risk assessment",
    "CC4": "Monitoring activities",
    "CC5": "Control activities",
    "CC6": "Logical and physical access controls",
    "CC7": "System operations",
    "CC8": "Change management",
    "CC9": "Risk mitigation",
    "A1": "Availability — system uptime and recovery",
    "PI1": "Processing integrity — accurate and complete processing",
    "C1": "Confidentiality — protection of confidential information",
    "P1": "Privacy — personal information collection and use",
}

GDPR_CONTROLS = {
    "GDPR-5": "Principles of processing (lawfulness, fairness, transparency)",
    "GDPR-6": "Lawfulness of processing (legal basis / consent)",
    "GDPR-13": "Information to be provided (transparency / privacy notice)",
    "GDPR-15": "Right of access by the data subject",
    "GDPR-17": "Right to erasure (right to be forgotten)",
    "GDPR-20": "Right to data portability",
    "GDPR-25": "Data protection by design and by default",
    "GDPR-30": "Records of processing activities",
    "GDPR-32": "Security of processing",
    "GDPR-33": "Notification of breach to supervisory authority",
    "GDPR-35": "Data protection impact assessment",
    "GDPR-44": "Cross-border transfer restrictions",
}

# File extensions to scan
_SCAN_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".java", ".rb", ".kt"}

# Directories to skip
_SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", "venv", "env",
    ".tox", ".mypy_cache", ".pytest_cache", "dist", "build", ".next",
    "vendor", "target", ".gradle",
}

# ---------------------------------------------------------------------------
# Patterns used for control checks
# ---------------------------------------------------------------------------

_TLS_PATTERN = re.compile(
    r"(?:https://|ssl|tls|verify_?ssl|cert|certificate|ssl_?context"
    r"|SECURE_SSL_REDIRECT|HTTPS_ONLY|force_?https)",
    re.IGNORECASE,
)

_ENCRYPTION_PATTERN = re.compile(
    r"(?:encrypt|decrypt|cipher|aes|rsa|sha256|sha512|bcrypt|argon2|scrypt"
    r"|fernet|kms|vault\.read|vault\.write|crypto\.subtle|hashlib)",
    re.IGNORECASE,
)

_AUTH_PATTERN = re.compile(
    r"(?:authenticate|authorization|jwt|oauth|token|session|login|password"
    r"|credential|api_?key|bearer|permissions|role_?based|rbac|acl)",
    re.IGNORECASE,
)

_LOGGING_PATTERN = re.compile(
    r"(?:logger\.\w+|logging\.\w+|audit_?log|access_?log|security_?log"
    r"|event_?log|log\.info|log\.warn|log\.error)",
    re.IGNORECASE,
)

_INPUT_VALIDATION_PATTERN = re.compile(
    r"(?:validate|sanitize|escape|parameterize|prepared_?statement|bind_?param"
    r"|@validator|@validates|Schema\(|Pydantic|marshmallow|joi\.|zod\.)",
    re.IGNORECASE,
)

_RATE_LIMIT_PATTERN = re.compile(
    r"(?:rate_?limit|throttle|limiter|slowapi|RateLimiter)",
    re.IGNORECASE,
)

_SECRETS_PATTERN = re.compile(
    r"(?:\.env|secret|password|api_?key|token|credential)",
    re.IGNORECASE,
)

_MONITORING_PATTERN = re.compile(
    r"(?:prometheus|grafana|datadog|newrelic|sentry|cloudwatch|healthcheck"
    r"|health_?check|uptime|alertmanager|pagerduty|opsgenie)",
    re.IGNORECASE,
)

_PRIVACY_NOTICE_PATTERN = re.compile(
    r"(?:privacy_?policy|privacy_?notice|cookie_?policy|terms_?of_?service"
    r"|data_?processing_?agreement|dpa|privacy_?statement)",
    re.IGNORECASE,
)

_CONSENT_PATTERN = re.compile(
    r"(?:consent|gdpr_?consent|user_?consent|opt_?in|opt_?out|cookie_?consent"
    r"|consent_?flag|consent_?form|consent_?modal)",
    re.IGNORECASE,
)

_DELETE_ENDPOINT = re.compile(
    r"""(?:@\s*(?:app|router)\s*\.\s*delete\s*\(\s*[\"'][^\"']*(?:user|account|profile|data|personal)[^\"']*[\"']"""
    r"""|def\s+delete_?user|def\s+erase_?data|def\s+forget_?me"""
    r"""|def\s+right_?to_?erasure|def\s+purge_?user|def\s+anonymize)""",
    re.IGNORECASE,
)

_EXPORT_DATA_PATTERN = re.compile(
    r"(?:export_?data|download_?data|data_?export|data_?portability|data_?dump"
    r"|get_?my_?data|user_?data_?export)",
    re.IGNORECASE,
)

_BREACH_NOTIFY_PATTERN = re.compile(
    r"(?:breach_?notif|incident_?report|security_?incident|alert_?admin"
    r"|notify_?admin|escalat|security_?alert)",
    re.IGNORECASE,
)

_DPIA_PATTERN = re.compile(
    r"(?:impact_?assessment|dpia|privacy_?impact|risk_?assessment"
    r"|data_?classification|data_?inventory)",
    re.IGNORECASE,
)

_CROSS_BORDER_PATTERN = re.compile(
    r"(?:transfer|cross.?border|international|gdpr.?transfer|standard.?contractual"
    r"|adequacy|binding.?corporate|schrems)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


class ComplianceReportGenerator:
    """Generate compliance reports against PCI, SOC2, or GDPR standards."""

    def __init__(self, cwd: str) -> None:
        self.cwd = cwd
        self._file_contents: dict[str, str] = {}  # rel_path -> content
        self._all_text = ""

    def generate(self, standard: str = "pci") -> ComplianceReport:
        """Generate compliance report for the given standard."""
        standard = standard.lower()
        logger.info("Generating %s compliance report for %s", standard.upper(), self.cwd)

        self._load_files()

        if standard == "pci":
            controls = self._pci_controls()
        elif standard == "soc2":
            controls = self._soc2_controls()
        elif standard == "gdpr":
            controls = self._gdpr_controls()
        else:
            raise ValueError(f"Unknown standard: {standard}. Supported: pci, soc2, gdpr")

        passed = sum(1 for c in controls if c.status == "pass")
        partial = sum(1 for c in controls if c.status == "partial")
        total = sum(1 for c in controls if c.status != "not_applicable")
        score = round(((passed + partial * 0.5) / max(total, 1)) * 100, 1)

        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        summary = (
            f"{standard.upper()} Compliance Report — {date_str}\n"
            f"Score: {score}/100 | "
            f"Pass: {passed} | Partial: {partial} | "
            f"Fail: {sum(1 for c in controls if c.status == 'fail')} | "
            f"N/A: {sum(1 for c in controls if c.status == 'not_applicable')}"
        )

        return ComplianceReport(
            standard=standard.upper(),
            date=date_str,
            score=score,
            controls=controls,
            summary=summary,
        )

    # ------------------------------------------------------------------
    # File loading
    # ------------------------------------------------------------------

    def _load_files(self) -> None:
        """Load all source files into memory for scanning."""
        self._file_contents = {}
        root = Path(self.cwd)
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            for fname in filenames:
                p = Path(dirpath) / fname
                if p.suffix in _SCAN_EXTENSIONS:
                    try:
                        content = p.read_text(encoding="utf-8", errors="replace")
                        rel = str(p.relative_to(root))
                        self._file_contents[rel] = content
                    except (OSError, UnicodeDecodeError):
                        continue
        self._all_text = "\n".join(self._file_contents.values())

    def _search(self, pattern: re.Pattern) -> list[str]:
        """Return list of files matching a pattern."""
        return [f for f, c in self._file_contents.items() if pattern.search(c)]

    def _has(self, pattern: re.Pattern) -> bool:
        """Check if any file matches a pattern."""
        return bool(pattern.search(self._all_text))

    # ------------------------------------------------------------------
    # PCI-DSS controls
    # ------------------------------------------------------------------

    def _pci_controls(self) -> list[ComplianceControl]:
        controls: list[ComplianceControl] = []

        # PCI-1: Network security
        tls_files = self._search(_TLS_PATTERN)
        controls.append(ComplianceControl(
            id="PCI-1", name=PCI_CONTROLS["PCI-1"],
            status="pass" if tls_files else "fail",
            evidence=tls_files[:5] or ["No TLS/SSL configuration found"],
            notes="TLS/SSL configuration detected" if tls_files else "No network security controls found",
        ))

        # PCI-2: Secure configuration
        env_files = [f for f in self._file_contents if ".env" in f or "config" in f.lower()]
        hardcoded_secrets = self._search(re.compile(
            r"""(?:password|secret|api_key|token)\s*=\s*[\"'][^\"']{8,}[\"']""", re.IGNORECASE
        ))
        if hardcoded_secrets:
            status = "fail"
            evidence = [f"{f} (hardcoded secret)" for f in hardcoded_secrets[:5]]
        elif env_files:
            status = "pass"
            evidence = env_files[:5]
        else:
            status = "partial"
            evidence = ["No config files detected"]
        controls.append(ComplianceControl(
            id="PCI-2", name=PCI_CONTROLS["PCI-2"],
            status=status, evidence=evidence,
        ))

        # PCI-3: Protect stored account data
        enc_files = self._search(_ENCRYPTION_PATTERN)
        controls.append(ComplianceControl(
            id="PCI-3", name=PCI_CONTROLS["PCI-3"],
            status="pass" if enc_files else "fail",
            evidence=enc_files[:5] or ["No encryption detected for stored data"],
        ))

        # PCI-4: Cryptography during transmission
        controls.append(ComplianceControl(
            id="PCI-4", name=PCI_CONTROLS["PCI-4"],
            status="pass" if tls_files else "fail",
            evidence=tls_files[:5] or ["No transport encryption detected"],
        ))

        # PCI-5: Malware protection (not directly code-detectable)
        controls.append(ComplianceControl(
            id="PCI-5", name=PCI_CONTROLS["PCI-5"],
            status="not_applicable",
            evidence=["Infrastructure concern — not detectable from source code"],
        ))

        # PCI-6: Secure software development
        validation_files = self._search(_INPUT_VALIDATION_PATTERN)
        controls.append(ComplianceControl(
            id="PCI-6", name=PCI_CONTROLS["PCI-6"],
            status="pass" if validation_files else "fail",
            evidence=validation_files[:5] or ["No input validation detected"],
        ))

        # PCI-7: Restrict access by need-to-know
        auth_files = self._search(_AUTH_PATTERN)
        controls.append(ComplianceControl(
            id="PCI-7", name=PCI_CONTROLS["PCI-7"],
            status="pass" if auth_files else "fail",
            evidence=auth_files[:5] or ["No access control mechanisms found"],
        ))

        # PCI-8: Authentication
        controls.append(ComplianceControl(
            id="PCI-8", name=PCI_CONTROLS["PCI-8"],
            status="pass" if auth_files else "fail",
            evidence=auth_files[:5] or ["No authentication mechanisms found"],
        ))

        # PCI-9: Physical access (not code-detectable)
        controls.append(ComplianceControl(
            id="PCI-9", name=PCI_CONTROLS["PCI-9"],
            status="not_applicable",
            evidence=["Physical security — not detectable from source code"],
        ))

        # PCI-10: Logging and monitoring
        log_files = self._search(_LOGGING_PATTERN)
        controls.append(ComplianceControl(
            id="PCI-10", name=PCI_CONTROLS["PCI-10"],
            status="pass" if log_files else "fail",
            evidence=log_files[:5] or ["No logging/monitoring detected"],
        ))

        # PCI-11: Test security regularly
        test_files = [f for f in self._file_contents if "test" in f.lower()]
        security_tests = [f for f in test_files if "secur" in f.lower()]
        if security_tests:
            status = "pass"
            evidence = security_tests[:5]
        elif test_files:
            status = "partial"
            evidence = test_files[:5] + ["No dedicated security tests found"]
        else:
            status = "fail"
            evidence = ["No test files found"]
        controls.append(ComplianceControl(
            id="PCI-11", name=PCI_CONTROLS["PCI-11"],
            status=status, evidence=evidence,
        ))

        # PCI-12: Organizational policies (not code-detectable)
        policy_files = [f for f in self._file_contents
                        if any(w in f.lower() for w in ("security", "policy", "compliance", "contributing"))]
        controls.append(ComplianceControl(
            id="PCI-12", name=PCI_CONTROLS["PCI-12"],
            status="pass" if policy_files else "not_applicable",
            evidence=policy_files[:5] or ["No policy documents detected in source"],
        ))

        return controls

    # ------------------------------------------------------------------
    # SOC2 controls
    # ------------------------------------------------------------------

    def _soc2_controls(self) -> list[ComplianceControl]:
        controls: list[ComplianceControl] = []

        # CC1: Control environment (org governance — partial from code)
        readme_files = [f for f in self._file_contents if "readme" in f.lower() or "contributing" in f.lower()]
        controls.append(ComplianceControl(
            id="CC1", name=SOC2_CONTROLS["CC1"],
            status="partial" if readme_files else "fail",
            evidence=readme_files[:3] or ["No governance/contributing docs found"],
        ))

        # CC2: Communication
        doc_files = [f for f in self._file_contents if any(
            w in f.lower() for w in ("doc", "readme", "changelog", "wiki")
        )]
        controls.append(ComplianceControl(
            id="CC2", name=SOC2_CONTROLS["CC2"],
            status="pass" if doc_files else "fail",
            evidence=doc_files[:5] or ["No documentation found"],
        ))

        # CC3: Risk assessment
        controls.append(ComplianceControl(
            id="CC3", name=SOC2_CONTROLS["CC3"],
            status="partial" if self._has(_INPUT_VALIDATION_PATTERN) else "fail",
            evidence=self._search(_INPUT_VALIDATION_PATTERN)[:3] or ["No risk controls found"],
        ))

        # CC4: Monitoring
        mon_files = self._search(_MONITORING_PATTERN)
        log_files = self._search(_LOGGING_PATTERN)
        combined = list(set(mon_files + log_files))
        controls.append(ComplianceControl(
            id="CC4", name=SOC2_CONTROLS["CC4"],
            status="pass" if mon_files else ("partial" if log_files else "fail"),
            evidence=combined[:5] or ["No monitoring detected"],
        ))

        # CC5: Control activities
        auth_files = self._search(_AUTH_PATTERN)
        controls.append(ComplianceControl(
            id="CC5", name=SOC2_CONTROLS["CC5"],
            status="pass" if auth_files else "fail",
            evidence=auth_files[:5] or ["No control activities detected"],
        ))

        # CC6: Access controls
        controls.append(ComplianceControl(
            id="CC6", name=SOC2_CONTROLS["CC6"],
            status="pass" if auth_files else "fail",
            evidence=auth_files[:5] or ["No access controls found"],
        ))

        # CC7: System operations
        controls.append(ComplianceControl(
            id="CC7", name=SOC2_CONTROLS["CC7"],
            status="pass" if log_files else "fail",
            evidence=log_files[:5] or ["No operational logging found"],
        ))

        # CC8: Change management
        git_ci_files = [f for f in self._file_contents
                        if any(w in f.lower() for w in (".github", "ci", "pipeline", "jenkins", "gitlab-ci"))]
        controls.append(ComplianceControl(
            id="CC8", name=SOC2_CONTROLS["CC8"],
            status="pass" if git_ci_files else "partial",
            evidence=git_ci_files[:5] or ["No CI/CD pipeline config detected"],
            notes="Git-based change management assumed",
        ))

        # CC9: Risk mitigation
        rl_files = self._search(_RATE_LIMIT_PATTERN)
        enc_files = self._search(_ENCRYPTION_PATTERN)
        combined_risk = list(set(rl_files + enc_files))
        controls.append(ComplianceControl(
            id="CC9", name=SOC2_CONTROLS["CC9"],
            status="pass" if combined_risk else "fail",
            evidence=combined_risk[:5] or ["No risk mitigation controls found"],
        ))

        # A1: Availability
        health_files = self._search(_MONITORING_PATTERN)
        controls.append(ComplianceControl(
            id="A1", name=SOC2_CONTROLS["A1"],
            status="pass" if health_files else "fail",
            evidence=health_files[:5] or ["No availability monitoring found"],
        ))

        # PI1: Processing integrity
        validation_files = self._search(_INPUT_VALIDATION_PATTERN)
        controls.append(ComplianceControl(
            id="PI1", name=SOC2_CONTROLS["PI1"],
            status="pass" if validation_files else "fail",
            evidence=validation_files[:5] or ["No input validation found"],
        ))

        # C1: Confidentiality
        enc_files = self._search(_ENCRYPTION_PATTERN)
        controls.append(ComplianceControl(
            id="C1", name=SOC2_CONTROLS["C1"],
            status="pass" if enc_files else "fail",
            evidence=enc_files[:5] or ["No encryption mechanisms found"],
        ))

        # P1: Privacy
        consent_files = self._search(_CONSENT_PATTERN)
        privacy_files = self._search(_PRIVACY_NOTICE_PATTERN)
        combined_privacy = list(set(consent_files + privacy_files))
        controls.append(ComplianceControl(
            id="P1", name=SOC2_CONTROLS["P1"],
            status="pass" if combined_privacy else "fail",
            evidence=combined_privacy[:5] or ["No privacy controls found"],
        ))

        return controls

    # ------------------------------------------------------------------
    # GDPR controls
    # ------------------------------------------------------------------

    def _gdpr_controls(self) -> list[ComplianceControl]:
        controls: list[ComplianceControl] = []

        # GDPR-5: Principles of processing
        privacy_files = self._search(_PRIVACY_NOTICE_PATTERN)
        controls.append(ComplianceControl(
            id="GDPR-5", name=GDPR_CONTROLS["GDPR-5"],
            status="pass" if privacy_files else "fail",
            evidence=privacy_files[:5] or ["No privacy notice / policy found"],
        ))

        # GDPR-6: Lawfulness — consent
        consent_files = self._search(_CONSENT_PATTERN)
        controls.append(ComplianceControl(
            id="GDPR-6", name=GDPR_CONTROLS["GDPR-6"],
            status="pass" if consent_files else "fail",
            evidence=consent_files[:5] or ["No consent mechanism found"],
        ))

        # GDPR-13: Transparency
        controls.append(ComplianceControl(
            id="GDPR-13", name=GDPR_CONTROLS["GDPR-13"],
            status="pass" if privacy_files else "fail",
            evidence=privacy_files[:5] or ["No transparency / privacy notice found"],
        ))

        # GDPR-15: Right of access
        export_files = self._search(_EXPORT_DATA_PATTERN)
        controls.append(ComplianceControl(
            id="GDPR-15", name=GDPR_CONTROLS["GDPR-15"],
            status="pass" if export_files else "fail",
            evidence=export_files[:5] or ["No data access / export endpoint found"],
        ))

        # GDPR-17: Right to erasure
        delete_files = self._search(_DELETE_ENDPOINT)
        controls.append(ComplianceControl(
            id="GDPR-17", name=GDPR_CONTROLS["GDPR-17"],
            status="pass" if delete_files else "fail",
            evidence=delete_files[:5] or ["No data deletion endpoint found"],
        ))

        # GDPR-20: Data portability
        controls.append(ComplianceControl(
            id="GDPR-20", name=GDPR_CONTROLS["GDPR-20"],
            status="pass" if export_files else "fail",
            evidence=export_files[:5] or ["No data portability / export feature found"],
        ))

        # GDPR-25: Data protection by design
        enc_files = self._search(_ENCRYPTION_PATTERN)
        val_files = self._search(_INPUT_VALIDATION_PATTERN)
        combined = list(set(enc_files + val_files))
        status = "pass" if enc_files and val_files else ("partial" if combined else "fail")
        controls.append(ComplianceControl(
            id="GDPR-25", name=GDPR_CONTROLS["GDPR-25"],
            status=status,
            evidence=combined[:5] or ["No data protection by design mechanisms found"],
        ))

        # GDPR-30: Records of processing
        log_files = self._search(_LOGGING_PATTERN)
        controls.append(ComplianceControl(
            id="GDPR-30", name=GDPR_CONTROLS["GDPR-30"],
            status="pass" if log_files else "fail",
            evidence=log_files[:5] or ["No processing records / audit logging found"],
        ))

        # GDPR-32: Security of processing
        controls.append(ComplianceControl(
            id="GDPR-32", name=GDPR_CONTROLS["GDPR-32"],
            status="pass" if enc_files else "fail",
            evidence=enc_files[:5] or ["No encryption / security mechanisms found"],
        ))

        # GDPR-33: Breach notification
        breach_files = self._search(_BREACH_NOTIFY_PATTERN)
        controls.append(ComplianceControl(
            id="GDPR-33", name=GDPR_CONTROLS["GDPR-33"],
            status="pass" if breach_files else "fail",
            evidence=breach_files[:5] or ["No breach notification mechanism found"],
        ))

        # GDPR-35: Data protection impact assessment
        dpia_files = self._search(_DPIA_PATTERN)
        controls.append(ComplianceControl(
            id="GDPR-35", name=GDPR_CONTROLS["GDPR-35"],
            status="pass" if dpia_files else "fail",
            evidence=dpia_files[:5] or ["No DPIA / impact assessment found"],
        ))

        # GDPR-44: Cross-border transfers
        transfer_files = self._search(_CROSS_BORDER_PATTERN)
        controls.append(ComplianceControl(
            id="GDPR-44", name=GDPR_CONTROLS["GDPR-44"],
            status="pass" if not transfer_files else "partial",
            evidence=transfer_files[:5] or ["No cross-border transfer mechanisms detected"],
            notes="No cross-border transfer code found — may be compliant by default" if not transfer_files else "",
        ))

        return controls

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    def format_markdown(self, report: ComplianceReport) -> str:
        """Format report as Markdown."""
        lines: list[str] = []
        lines.append(f"# {report.standard} Compliance Report")
        lines.append(f"\n**Date:** {report.date}")
        lines.append(f"**Score:** {report.score}/100\n")

        status_icon = {"pass": "PASS", "fail": "FAIL", "partial": "PARTIAL", "not_applicable": "N/A"}

        lines.append("| Control | Name | Status | Notes |")
        lines.append("|---------|------|--------|-------|")
        for c in report.controls:
            icon = status_icon.get(c.status, c.status)
            notes = c.notes or ("; ".join(c.evidence[:2]))
            lines.append(f"| {c.id} | {c.name} | {icon} | {notes} |")

        lines.append(f"\n## Summary\n\n{report.summary}")
        return "\n".join(lines)

    def format_terminal(self, report: ComplianceReport) -> str:
        """Format report for terminal display."""
        lines: list[str] = []
        lines.append(f"\n  {report.standard} Compliance Report")
        lines.append("  " + "=" * 55)
        lines.append(f"  Date:   {report.date}")
        lines.append(f"  Score:  {report.score}/100")
        lines.append("")

        status_label = {
            "pass": "  PASS  ",
            "fail": "  FAIL  ",
            "partial": "PARTIAL ",
            "not_applicable": "  N/A   ",
        }

        for c in report.controls:
            label = status_label.get(c.status, c.status)
            lines.append(f"  [{label}] {c.id}: {c.name}")
            if c.evidence and c.status != "not_applicable":
                for ev in c.evidence[:3]:
                    lines.append(f"             - {ev}")
            if c.notes:
                lines.append(f"             Note: {c.notes}")

        lines.append("")
        lines.append(f"  {report.summary}")
        return "\n".join(lines)

    def format_json(self, report: ComplianceReport) -> str:
        """Format report as JSON string."""
        return _json.dumps(compliance_report_to_json(report), indent=2)


# ---------------------------------------------------------------------------
# JSON helper
# ---------------------------------------------------------------------------


def compliance_report_to_json(report: ComplianceReport) -> dict:
    """Convert report to JSON-serializable dict."""
    return {
        "standard": report.standard,
        "date": report.date,
        "score": report.score,
        "summary": report.summary,
        "controls": [
            {
                "id": c.id,
                "name": c.name,
                "status": c.status,
                "evidence": c.evidence,
                "notes": c.notes,
            }
            for c in report.controls
        ],
    }
