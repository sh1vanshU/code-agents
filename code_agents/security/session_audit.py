"""Session Management Auditor — find session/auth security issues in code.

Scans for:
  - JWT/session tokens without expiry
  - Cookies missing httponly, secure, samesite flags
  - Session fixation (no regeneration after login)
  - Missing logout/session invalidation endpoints
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.security.session_audit")

_CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rb",
    ".cs", ".php", ".kt", ".scala",
}

_SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".tox", "venv", ".venv",
    "dist", "build", ".eggs", "vendor", "third_party", ".mypy_cache",
    ".pytest_cache", "htmlcov", "site-packages",
}

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SessionFinding:
    """A session management security finding."""
    file: str
    line: int
    category: str  # "token_expiry", "cookie_flags", "session_fixation", "logout"
    severity: str  # "critical", "high", "medium", "low"
    message: str
    code_snippet: str = ""


@dataclass
class SessionAuditReport:
    """Full session audit report."""
    findings: list[SessionFinding] = field(default_factory=list)
    files_scanned: int = 0

    @property
    def by_category(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for f in self.findings:
            counts[f.category] = counts.get(f.category, 0) + 1
        return counts

    @property
    def by_severity(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for f in self.findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        return counts


# ---------------------------------------------------------------------------
# Detection patterns
# ---------------------------------------------------------------------------

# JWT creation without expiry
_JWT_CREATE_PATTERNS = [
    re.compile(r"""jwt\.encode\s*\("""),
    re.compile(r"""jwt\.sign\s*\("""),
    re.compile(r"""JWT\.create\s*\("""),
    re.compile(r"""Jwts\.builder\s*\("""),
    re.compile(r"""jose\.jwt\.encode\s*\("""),
    re.compile(r"""create_access_token\s*\("""),
    re.compile(r"""create_refresh_token\s*\("""),
    re.compile(r"""generate_token\s*\("""),
    re.compile(r"""sign_token\s*\("""),
]

_EXPIRY_KEYWORDS = [
    "exp", "expires", "expiry", "expires_in", "expiresIn",
    "expires_delta", "expiration", "ttl", "max_age", "maxAge",
    "setExpiration", "expire_seconds",
]

# Cookie patterns
_COOKIE_SET_PATTERNS = [
    re.compile(r"""\.set_cookie\s*\("""),
    re.compile(r"""\.cookie\s*\("""),
    re.compile(r"""Set-Cookie\s*:"""),
    re.compile(r"""res\.cookie\s*\("""),
    re.compile(r"""response\.set_cookie\s*\("""),
    re.compile(r"""cookie\.New\s*\("""),
    re.compile(r"""Cookie\s*\("""),
    re.compile(r"""setCookie\s*\("""),
    re.compile(r"""addCookie\s*\("""),
]

_COOKIE_SECURE_FLAGS = {
    "httponly": re.compile(r"""(?i)httponly\s*[=:]\s*(?:True|true|1)"""),
    "secure": re.compile(r"""(?i)(?<![a-z])secure\s*[=:]\s*(?:True|true|1)"""),
    "samesite": re.compile(r"""(?i)samesite\s*[=:]\s*['"]?(Strict|Lax|None)"""),
}

# Session fixation patterns
_LOGIN_PATTERNS = [
    re.compile(r"""(?:login|authenticate|sign_in|signin|do_login)\s*\(""", re.IGNORECASE),
    re.compile(r"""@(?:post|POST)\s*\(\s*['"]/(?:login|auth|signin)['"]"""),
    re.compile(r"""(?:router|app)\.post\s*\(\s*['"]/(?:login|auth|signin)['"]"""),
]

_SESSION_REGEN_PATTERNS = [
    re.compile(r"""session\.regenerate"""),
    re.compile(r"""session\.cycle_id"""),
    re.compile(r"""session\.clear"""),
    re.compile(r"""request\.session\.flush"""),
    re.compile(r"""session\.invalidate"""),
    re.compile(r"""changeSessionId"""),
    re.compile(r"""new_session"""),
    re.compile(r"""rotate_session"""),
    re.compile(r"""session\.create"""),
]

# Logout patterns
_LOGOUT_PATTERNS = [
    re.compile(r"""(?:logout|log_out|sign_out|signout)\s*\(""", re.IGNORECASE),
    re.compile(r"""['"]/(?:logout|signout|log-out|sign-out)['"]"""),
    re.compile(r"""session\.destroy"""),
    re.compile(r"""session\.delete"""),
    re.compile(r"""blacklist.*token""", re.IGNORECASE),
    re.compile(r"""revoke.*token""", re.IGNORECASE),
    re.compile(r"""invalidate.*session""", re.IGNORECASE),
    re.compile(r"""token.*blacklist""", re.IGNORECASE),
]


class SessionAuditor:
    """Audit session management patterns for security issues."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        logger.info("SessionAuditor initialized for %s", cwd)

    def audit(self) -> SessionAuditReport:
        """Run the full session audit."""
        report = SessionAuditReport()
        files = self._collect_files(Path(self.cwd))
        report.files_scanned = len(files)
        logger.info("Auditing session management in %d files", len(files))

        has_login = False
        has_logout = False
        has_session_regen = False

        for fpath in files:
            try:
                content = fpath.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            rel = str(fpath.relative_to(self.cwd))
            lines = content.split("\n")

            report.findings.extend(self._check_token_expiry(rel, lines))
            report.findings.extend(self._check_secure_cookies(rel, lines))

            login_findings = self._check_session_fixation(rel, lines, content)
            report.findings.extend(login_findings)

            # Track global patterns
            for pat in _LOGIN_PATTERNS:
                if pat.search(content):
                    has_login = True
            for pat in _LOGOUT_PATTERNS:
                if pat.search(content):
                    has_logout = True
            for pat in _SESSION_REGEN_PATTERNS:
                if pat.search(content):
                    has_session_regen = True

        # Check for missing logout
        logout_findings = self._check_logout(has_login, has_logout)
        report.findings.extend(logout_findings)

        logger.info(
            "Session audit complete: %d findings in %d files",
            len(report.findings), report.files_scanned,
        )
        return report

    def _check_token_expiry(self, rel_path: str, lines: list[str]) -> list[SessionFinding]:
        """Check for JWT/token creation without expiry."""
        findings: list[SessionFinding] = []

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//"):
                continue

            for pat in _JWT_CREATE_PATTERNS:
                if not pat.search(stripped):
                    continue

                # Look in surrounding context for expiry keywords
                context_start = max(0, i - 3)
                context_end = min(len(lines), i + 10)
                context = "\n".join(lines[context_start:context_end])

                has_expiry = any(
                    kw in context for kw in _EXPIRY_KEYWORDS
                )

                if not has_expiry:
                    findings.append(SessionFinding(
                        file=rel_path,
                        line=i + 1,
                        category="token_expiry",
                        severity="critical",
                        message="JWT/token created without expiry — tokens never expire",
                        code_snippet=stripped[:100],
                    ))
                break

        return findings

    def _check_secure_cookies(self, rel_path: str, lines: list[str]) -> list[SessionFinding]:
        """Check for cookies missing security flags."""
        findings: list[SessionFinding] = []

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("//"):
                continue

            is_cookie = False
            for pat in _COOKIE_SET_PATTERNS:
                if pat.search(stripped):
                    is_cookie = True
                    break

            if not is_cookie:
                continue

            # Check surrounding context for security flags
            context_start = max(0, i - 1)
            context_end = min(len(lines), i + 8)
            context = "\n".join(lines[context_start:context_end])

            missing: list[str] = []
            for flag_name, flag_pat in _COOKIE_SECURE_FLAGS.items():
                if not flag_pat.search(context):
                    missing.append(flag_name)

            if missing:
                findings.append(SessionFinding(
                    file=rel_path,
                    line=i + 1,
                    category="cookie_flags",
                    severity="high" if "httponly" in missing or "secure" in missing else "medium",
                    message=f"Cookie missing flags: {', '.join(missing)}",
                    code_snippet=stripped[:100],
                ))

        return findings

    def _check_session_fixation(
        self, rel_path: str, lines: list[str], content: str,
    ) -> list[SessionFinding]:
        """Check for login handlers without session regeneration."""
        findings: list[SessionFinding] = []

        for i, line in enumerate(lines):
            stripped = line.strip()
            is_login = False
            for pat in _LOGIN_PATTERNS:
                if pat.search(stripped):
                    is_login = True
                    break

            if not is_login:
                continue

            # Look in the function body for session regeneration
            func_end = min(len(lines), i + 40)
            func_body = "\n".join(lines[i:func_end])

            has_regen = any(
                pat.search(func_body) for pat in _SESSION_REGEN_PATTERNS
            )

            if not has_regen:
                findings.append(SessionFinding(
                    file=rel_path,
                    line=i + 1,
                    category="session_fixation",
                    severity="high",
                    message="Login handler without session regeneration — session fixation risk",
                    code_snippet=stripped[:100],
                ))

        return findings

    def _check_logout(self, has_login: bool, has_logout: bool) -> list[SessionFinding]:
        """Check if the codebase has login but no logout mechanism."""
        findings: list[SessionFinding] = []

        if has_login and not has_logout:
            findings.append(SessionFinding(
                file="(project-wide)",
                line=0,
                category="logout",
                severity="high",
                message="Login detected but no logout/session invalidation endpoint found",
            ))

        return findings

    # ----- helpers -----

    def _collect_files(self, target: Path) -> list[Path]:
        """Collect source code files."""
        files: list[Path] = []
        for root, dirs, fnames in os.walk(target):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
            for fn in fnames:
                if Path(fn).suffix in _CODE_EXTENSIONS:
                    files.append(Path(root) / fn)
        return sorted(files)


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def format_session_report(report: SessionAuditReport) -> str:
    """Format a human-readable session audit report."""
    if not report.findings:
        return "  No session management issues found!"

    parts = [
        f"  Session Management Audit: {len(report.findings)} findings",
        f"  Files scanned: {report.files_scanned}",
        "",
    ]

    category_labels = {
        "token_expiry": "Missing Token Expiry",
        "cookie_flags": "Insecure Cookies",
        "session_fixation": "Session Fixation Risk",
        "logout": "Missing Logout",
    }

    for cat, count in sorted(report.by_category.items()):
        parts.append(f"    {category_labels.get(cat, cat)}: {count}")
    parts.append("")

    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    sorted_findings = sorted(
        report.findings,
        key=lambda f: (severity_order.get(f.severity, 9), f.file, f.line),
    )

    for f in sorted_findings:
        sev_icon = {
            "critical": "[!!]", "high": "[!]", "medium": "[~]", "low": "[-]",
        }.get(f.severity, "[ ]")
        loc = f"{f.file}:{f.line}" if f.line > 0 else f.file
        parts.append(f"  {sev_icon} [{f.severity.upper()}] {loc}")
        parts.append(f"      {f.message}")
        if f.code_snippet:
            parts.append(f"      > {f.code_snippet}")
        parts.append("")

    return "\n".join(parts)


def session_report_to_json(report: SessionAuditReport) -> dict:
    """Convert report to JSON-serializable dict."""
    return {
        "files_scanned": report.files_scanned,
        "total_findings": len(report.findings),
        "by_category": report.by_category,
        "by_severity": report.by_severity,
        "findings": [
            {
                "file": f.file,
                "line": f.line,
                "category": f.category,
                "severity": f.severity,
                "message": f.message,
                "code_snippet": f.code_snippet,
            }
            for f in report.findings
        ],
    }
