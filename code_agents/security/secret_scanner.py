"""Secret Scanner — detect exposed secrets in code, configs, and git history.

Scans source files, environment configs, and (optionally) git commit diffs
for accidentally committed secrets: AWS keys, API tokens, passwords,
private keys, etc.

SECURITY: This scanner MUST NOT log or store actual secret values.
Only file:line references and masked previews are recorded.

Usage:
    from code_agents.security.secret_scanner import SecretScanner, SecretScannerConfig
    scanner = SecretScanner(SecretScannerConfig(cwd="/path/to/repo"))
    result = scanner.scan()
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.security.secret_scanner")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SecretScannerConfig:
    cwd: str = "."
    max_files: int = 1000
    scan_git_history: bool = False
    git_depth: int = 50
    scan_env_files: bool = True


@dataclass
class SecretFinding:
    """A detected secret exposure."""
    file: str
    line: int
    secret_type: str  # "aws_key", "api_token", "password", "private_key", etc.
    severity: str = "critical"
    masked_preview: str = ""  # first 4 chars + "***"
    description: str = ""
    remediation: str = ""
    in_git_history: bool = False
    commit_sha: str = ""


@dataclass
class SecretScanReport:
    """Full secret scanning result."""
    files_scanned: int = 0
    secrets_found: int = 0
    critical_count: int = 0
    high_count: int = 0
    findings: list[SecretFinding] = field(default_factory=list)
    scanned_git_history: bool = False
    git_commits_scanned: int = 0
    summary: str = ""


# ---------------------------------------------------------------------------
# Secret patterns — regex + metadata
# ---------------------------------------------------------------------------

SECRET_PATTERNS: list[dict] = [
    {
        "name": "aws_access_key",
        "pattern": re.compile(r"(?:AKIA)[A-Z0-9]{16}"),
        "severity": "critical",
        "description": "AWS Access Key ID",
        "remediation": "Rotate key in AWS IAM console, use environment variables or IAM roles.",
    },
    {
        "name": "aws_secret_key",
        "pattern": re.compile(r"(?:aws_secret_access_key|AWS_SECRET)\s*[:=]\s*['\"]?([A-Za-z0-9/+=]{40})"),
        "severity": "critical",
        "description": "AWS Secret Access Key",
        "remediation": "Rotate in AWS IAM, store in secrets manager.",
    },
    {
        "name": "generic_api_key",
        "pattern": re.compile(r"(?:api[_-]?key|apikey)\s*[:=]\s*['\"]([A-Za-z0-9_\-]{20,})['\"]", re.IGNORECASE),
        "severity": "high",
        "description": "Generic API key",
        "remediation": "Rotate the API key and use environment variables.",
    },
    {
        "name": "generic_token",
        "pattern": re.compile(r"(?:token|bearer)\s*[:=]\s*['\"]([A-Za-z0-9_\-.]{20,})['\"]", re.IGNORECASE),
        "severity": "high",
        "description": "Generic access token",
        "remediation": "Rotate the token and use a secrets manager.",
    },
    {
        "name": "password_assignment",
        "pattern": re.compile(r"(?:password|passwd|pwd)\s*[:=]\s*['\"]([^'\"]{8,})['\"]", re.IGNORECASE),
        "severity": "critical",
        "description": "Hardcoded password",
        "remediation": "Remove hardcoded password, use environment variable or vault.",
    },
    {
        "name": "private_key",
        "pattern": re.compile(r"-----BEGIN (?:RSA |EC |DSA )?PRIVATE KEY-----"),
        "severity": "critical",
        "description": "Private key file content",
        "remediation": "Remove private key from source, store securely outside repo.",
    },
    {
        "name": "github_token",
        "pattern": re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,}"),
        "severity": "critical",
        "description": "GitHub personal access token",
        "remediation": "Revoke token in GitHub settings, generate new one.",
    },
    {
        "name": "slack_token",
        "pattern": re.compile(r"xox[baprs]-[A-Za-z0-9-]{10,}"),
        "severity": "high",
        "description": "Slack token",
        "remediation": "Revoke in Slack admin, rotate credentials.",
    },
    {
        "name": "jwt_token",
        "pattern": re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+"),
        "severity": "high",
        "description": "JWT token",
        "remediation": "Invalidate the token, check if refresh token is also exposed.",
    },
    {
        "name": "connection_string",
        "pattern": re.compile(r"(?:mysql|postgres|mongodb|redis)://[^\s'\"]{10,}", re.IGNORECASE),
        "severity": "critical",
        "description": "Database connection string with credentials",
        "remediation": "Use environment variables for connection strings.",
    },
]

# Files/dirs to always skip
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", ".tox", "dist", "build"}
SKIP_EXTENSIONS = {".pyc", ".pyo", ".whl", ".tar", ".gz", ".zip", ".jar", ".png", ".jpg", ".ico"}

# Env-like file patterns
ENV_FILE_PATTERNS = {"*.env", ".env.*", "*.env.local", "config.env", ".env.code-agents"}


def _mask_secret(value: str) -> str:
    """Mask a secret, keeping first 4 chars."""
    if len(value) <= 4:
        return "****"
    return value[:4] + "****"


# ---------------------------------------------------------------------------
# SecretScanner
# ---------------------------------------------------------------------------


class SecretScanner:
    """Scan codebase for exposed secrets."""

    def __init__(self, config: Optional[SecretScannerConfig] = None):
        self.config = config or SecretScannerConfig()

    def scan(self) -> SecretScanReport:
        """Run full secret scan."""
        logger.info("Starting secret scan in %s", self.config.cwd)
        report = SecretScanReport()
        root = Path(self.config.cwd)

        # Scan source files
        findings = self._scan_files(root)
        report.findings.extend(findings)
        report.files_scanned = self._last_files_scanned

        # Scan git history if requested
        if self.config.scan_git_history:
            git_findings, commits = self._scan_git_history(root)
            report.findings.extend(git_findings)
            report.scanned_git_history = True
            report.git_commits_scanned = commits

        # Tally
        report.secrets_found = len(report.findings)
        report.critical_count = sum(1 for f in report.findings if f.severity == "critical")
        report.high_count = sum(1 for f in report.findings if f.severity == "high")

        report.summary = (
            f"Scanned {report.files_scanned} files, found {report.secrets_found} secrets "
            f"({report.critical_count} critical, {report.high_count} high)."
        )
        logger.info("Secret scan complete: %s", report.summary)
        return report

    # -- internal -----------------------------------------------------------

    _last_files_scanned: int = 0

    def _scan_files(self, root: Path) -> list[SecretFinding]:
        """Scan all text files for secret patterns."""
        findings: list[SecretFinding] = []
        count = 0
        for fpath in root.rglob("*"):
            if count >= self.config.max_files:
                break
            if not fpath.is_file():
                continue
            if any(skip in fpath.parts for skip in SKIP_DIRS):
                continue
            if fpath.suffix in SKIP_EXTENSIONS:
                continue
            count += 1
            rel = str(fpath.relative_to(root))
            try:
                content = fpath.read_text(errors="replace")
            except Exception:
                continue
            for line_no, line in enumerate(content.splitlines(), 1):
                # Skip comments that are obviously documentation
                stripped = line.strip()
                if stripped.startswith("#") and "example" in stripped.lower():
                    continue
                for sp in SECRET_PATTERNS:
                    m = sp["pattern"].search(line)
                    if m:
                        matched = m.group(1) if m.lastindex and m.lastindex >= 1 else m.group(0)
                        findings.append(SecretFinding(
                            file=rel,
                            line=line_no,
                            secret_type=sp["name"],
                            severity=sp["severity"],
                            masked_preview=_mask_secret(matched),
                            description=sp["description"],
                            remediation=sp["remediation"],
                        ))
        self._last_files_scanned = count
        return findings

    def _scan_git_history(self, root: Path) -> tuple[list[SecretFinding], int]:
        """Scan recent git diffs for leaked secrets."""
        findings: list[SecretFinding] = []
        commits_scanned = 0
        try:
            import subprocess
            result = subprocess.run(
                ["git", "log", f"-{self.config.git_depth}", "--format=%H", "--diff-filter=A"],
                cwd=str(root), capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                return findings, 0

            shas = result.stdout.strip().splitlines()
            for sha in shas[:self.config.git_depth]:
                commits_scanned += 1
                diff_result = subprocess.run(
                    ["git", "diff", f"{sha}~1", sha, "--no-color"],
                    cwd=str(root), capture_output=True, text=True, timeout=15,
                )
                if diff_result.returncode != 0:
                    continue
                for line in diff_result.stdout.splitlines():
                    if not line.startswith("+"):
                        continue
                    for sp in SECRET_PATTERNS:
                        m = sp["pattern"].search(line)
                        if m:
                            matched = m.group(1) if m.lastindex and m.lastindex >= 1 else m.group(0)
                            findings.append(SecretFinding(
                                file=f"git:{sha[:8]}",
                                line=0,
                                secret_type=sp["name"],
                                severity=sp["severity"],
                                masked_preview=_mask_secret(matched),
                                description=sp["description"],
                                remediation=sp["remediation"],
                                in_git_history=True,
                                commit_sha=sha[:8],
                            ))
        except Exception as exc:
            logger.warning("Git history scan failed: %s", exc)
        return findings, commits_scanned


def format_secret_report(report: SecretScanReport) -> str:
    """Render a human-readable secret scan report."""
    lines = ["=== Secret Scanner Report ===", ""]
    lines.append(f"Files scanned:   {report.files_scanned}")
    lines.append(f"Secrets found:   {report.secrets_found}")
    lines.append(f"  Critical:      {report.critical_count}")
    lines.append(f"  High:          {report.high_count}")
    if report.scanned_git_history:
        lines.append(f"Git commits:     {report.git_commits_scanned}")
    lines.append("")

    for f in report.findings:
        src = f"git:{f.commit_sha}" if f.in_git_history else f"{f.file}:{f.line}"
        lines.append(f"  [{f.severity.upper()}] {f.secret_type} in {src}")
        lines.append(f"    Preview: {f.masked_preview}")
        lines.append(f"    Fix: {f.remediation}")
    lines.append("")
    lines.append(report.summary)
    return "\n".join(lines)
