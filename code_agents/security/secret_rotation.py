"""Secret Rotation Tracker — detect stale secrets and generate rotation runbooks.

Scans for secret/credential references in config files and environment
variables, checks how long since they were last changed (via git blame),
and generates rotation runbooks for stale secrets.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("code_agents.security.secret_rotation")

_SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".tox", "venv", ".venv",
    "dist", "build", ".eggs", "vendor", "third_party", ".mypy_cache",
    ".pytest_cache", "htmlcov", "site-packages",
}

_CONFIG_FILES = {
    ".env", ".env.example", ".env.local", ".env.production", ".env.staging",
    ".env.development", "config.yaml", "config.yml", "config.json",
    "settings.yaml", "settings.yml", "settings.json", "docker-compose.yml",
    "docker-compose.yaml", "application.properties", "application.yml",
    "appsettings.json", "secrets.yaml", "secrets.yml",
}

_CONFIG_EXTENSIONS = {
    ".env", ".yaml", ".yml", ".json", ".toml", ".ini", ".cfg",
    ".properties", ".conf",
}

# ---------------------------------------------------------------------------
# Secret detection patterns
# ---------------------------------------------------------------------------

_SECRET_KEY_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|apikey)\s*[=:]"),
    re.compile(r"(?i)(secret[_-]?key|secretkey)\s*[=:]"),
    re.compile(r"(?i)(access[_-]?key|accesskey)\s*[=:]"),
    re.compile(r"(?i)(auth[_-]?token|authtoken)\s*[=:]"),
    re.compile(r"(?i)(password|passwd|pwd)\s*[=:]"),
    re.compile(r"(?i)(private[_-]?key|privatekey)\s*[=:]"),
    re.compile(r"(?i)(client[_-]?secret|clientsecret)\s*[=:]"),
    re.compile(r"(?i)(db[_-]?password|database[_-]?password)\s*[=:]"),
    re.compile(r"(?i)(encryption[_-]?key|encryptionkey)\s*[=:]"),
    re.compile(r"(?i)(jwt[_-]?secret|jwtsecret)\s*[=:]"),
    re.compile(r"(?i)(signing[_-]?key|signingkey)\s*[=:]"),
    re.compile(r"(?i)(webhook[_-]?secret|webhooksecret)\s*[=:]"),
    re.compile(r"(?i)(oauth[_-]?secret|oauthsecret)\s*[=:]"),
    re.compile(r"(?i)(smtp[_-]?password|smtppassword)\s*[=:]"),
    re.compile(r"(?i)(redis[_-]?password|redispassword)\s*[=:]"),
    re.compile(r"(?i)(mongo[_-]?password|mongopassword)\s*[=:]"),
    re.compile(r"(?i)(aws[_-]?secret|awssecret)\s*[=:]"),
    re.compile(r"(?i)(gcp[_-]?key|gcpkey)\s*[=:]"),
    re.compile(r"(?i)(azure[_-]?key|azurekey)\s*[=:]"),
    re.compile(r"(?i)(slack[_-]?token|slacktoken)\s*[=:]"),
    re.compile(r"(?i)(github[_-]?token|githubtoken)\s*[=:]"),
    re.compile(r"(?i)(stripe[_-]?key|stripekey)\s*[=:]"),
    re.compile(r"(?i)(sendgrid[_-]?key|sendgridkey)\s*[=:]"),
    re.compile(r"(?i)(twilio[_-]?token|twiliotoken)\s*[=:]"),
    re.compile(r"(?i)(certificate[_-]?password|certpassword)\s*[=:]"),
    re.compile(r"(?i)(keystore[_-]?password|keystorepassword)\s*[=:]"),
]

_ENV_VAR_PATTERN = re.compile(
    r"(?i)\b(\w*(?:KEY|SECRET|TOKEN|PASSWORD|PASSWD|PWD|CREDENTIAL|AUTH)\w*)\s*[=:]"
)

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SecretRef:
    """A reference to a secret in configuration."""
    file: str
    line: int
    key_name: str
    age_days: int = -1  # -1 = unknown
    last_changed: str = ""  # ISO date or empty


@dataclass
class RotationReport:
    """Report of secret rotation status."""
    secrets: list[SecretRef] = field(default_factory=list)
    stale: list[SecretRef] = field(default_factory=list)
    fresh: list[SecretRef] = field(default_factory=list)
    unknown: list[SecretRef] = field(default_factory=list)
    max_age_days: int = 90
    runbook: str = ""

    @property
    def total(self) -> int:
        return len(self.secrets)


class SecretRotationTracker:
    """Track secret rotation status across the codebase."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        self._is_git = (Path(cwd) / ".git").is_dir()
        logger.info("SecretRotationTracker initialized for %s", cwd)

    def scan(self, max_age: int = 90) -> RotationReport:
        """Scan for secrets and check their rotation age."""
        refs = self._find_secret_refs()
        logger.info("Found %d secret references", len(refs))

        # Check ages via git
        for ref in refs:
            ref.age_days = self._check_age(ref)

        report = RotationReport(secrets=refs, max_age_days=max_age)

        for ref in refs:
            if ref.age_days < 0:
                report.unknown.append(ref)
            elif ref.age_days > max_age:
                report.stale.append(ref)
            else:
                report.fresh.append(ref)

        report.runbook = self._generate_runbook(report.stale)
        logger.info(
            "Rotation report: %d total, %d stale, %d fresh, %d unknown",
            report.total, len(report.stale), len(report.fresh), len(report.unknown),
        )
        return report

    def _find_secret_refs(self) -> list[SecretRef]:
        """Find environment variables and config keys that look like secrets."""
        refs: list[SecretRef] = []
        seen: set[tuple[str, str]] = set()

        root = Path(self.cwd)
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
            for fname in files:
                fpath = Path(dirpath) / fname
                if fname in _CONFIG_FILES or fpath.suffix in _CONFIG_EXTENSIONS:
                    try:
                        content = fpath.read_text(encoding="utf-8", errors="ignore")
                    except OSError:
                        continue
                    rel = str(fpath.relative_to(self.cwd))
                    self._extract_refs(rel, content, refs, seen)

        return refs

    def _extract_refs(
        self,
        rel_path: str,
        content: str,
        refs: list[SecretRef],
        seen: set[tuple[str, str]],
    ) -> None:
        """Extract secret references from file content."""
        lines = content.split("\n")
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("//"):
                continue

            # Check known secret patterns
            for pat in _SECRET_KEY_PATTERNS:
                if pat.search(stripped):
                    key_match = re.match(r"([A-Za-z_][A-Za-z0-9_.-]*)", stripped)
                    key_name = key_match.group(1) if key_match else stripped[:40]
                    ident = (rel_path, key_name)
                    if ident not in seen:
                        seen.add(ident)
                        refs.append(SecretRef(file=rel_path, line=i, key_name=key_name))
                    break

            # Check env var pattern
            m = _ENV_VAR_PATTERN.search(stripped)
            if m:
                key_name = m.group(1)
                ident = (rel_path, key_name)
                if ident not in seen:
                    seen.add(ident)
                    refs.append(SecretRef(file=rel_path, line=i, key_name=key_name))

    def _check_age(self, secret_ref: SecretRef) -> int:
        """Check days since last git change to the secret's config line."""
        if not self._is_git:
            return -1

        fpath = Path(self.cwd) / secret_ref.file
        if not fpath.exists():
            return -1

        try:
            result = subprocess.run(
                [
                    "git", "log", "-1", "--format=%at",
                    f"-L{secret_ref.line},{secret_ref.line}:{secret_ref.file}",
                ],
                capture_output=True, text=True, cwd=self.cwd, timeout=15,
            )
            if result.returncode != 0 or not result.stdout.strip():
                # Fallback: blame
                result = subprocess.run(
                    ["git", "blame", "-p", f"-L{secret_ref.line},{secret_ref.line}", str(fpath)],
                    capture_output=True, text=True, cwd=self.cwd, timeout=15,
                )
                if result.returncode != 0:
                    return -1
                for bl in result.stdout.split("\n"):
                    if bl.startswith("author-time "):
                        try:
                            ts = int(bl.split(" ", 1)[1])
                            days = (int(time.time()) - ts) // 86400
                            return max(0, days)
                        except ValueError:
                            return -1
                return -1

            ts = int(result.stdout.strip().split("\n")[0])
            days = (int(time.time()) - ts) // 86400
            return max(0, days)
        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
            return -1

    def _generate_runbook(self, stale: list[SecretRef]) -> str:
        """Generate a rotation runbook for stale secrets."""
        if not stale:
            return "No stale secrets — all secrets are within rotation policy."

        parts = [
            "SECRET ROTATION RUNBOOK",
            "=" * 50,
            "",
            f"Secrets requiring rotation: {len(stale)}",
            "",
        ]

        for i, ref in enumerate(stale, 1):
            parts.append(f"  {i}. {ref.key_name}")
            parts.append(f"     File: {ref.file}:{ref.line}")
            parts.append(f"     Age: {ref.age_days} days")
            parts.append(f"     Action:")
            parts.append(f"       a. Generate new value in your secrets manager")
            parts.append(f"       b. Update {ref.file} with the new reference")
            parts.append(f"       c. Deploy to staging, verify functionality")
            parts.append(f"       d. Deploy to production")
            parts.append(f"       e. Revoke the old secret after grace period")
            parts.append("")

        parts.extend([
            "GENERAL ROTATION STEPS:",
            "  1. Identify all services using the secret",
            "  2. Generate a new secret value",
            "  3. Update secret in vault/secrets manager",
            "  4. Rolling deploy services with new secret",
            "  5. Verify no errors in logs for 30 minutes",
            "  6. Revoke old secret value",
            "  7. Update rotation timestamp in tracker",
        ])

        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def format_rotation_report(report: RotationReport) -> str:
    """Format a human-readable rotation report."""
    parts = [
        f"  Secret Rotation Report (max age: {report.max_age_days} days)",
        f"  Total secrets found: {report.total}",
        f"    Fresh (< {report.max_age_days}d): {len(report.fresh)}",
        f"    Stale (>= {report.max_age_days}d): {len(report.stale)}",
        f"    Unknown age: {len(report.unknown)}",
        "",
    ]

    if report.stale:
        parts.append("  STALE SECRETS (require rotation):")
        for ref in sorted(report.stale, key=lambda r: -r.age_days):
            parts.append(f"    [!] {ref.key_name} — {ref.age_days}d old ({ref.file}:{ref.line})")
        parts.append("")

    if report.unknown:
        parts.append("  UNKNOWN AGE (not in git or untracked):")
        for ref in report.unknown:
            parts.append(f"    [?] {ref.key_name} ({ref.file}:{ref.line})")
        parts.append("")

    if report.fresh:
        parts.append("  FRESH SECRETS:")
        for ref in sorted(report.fresh, key=lambda r: -r.age_days):
            parts.append(f"    [ok] {ref.key_name} — {ref.age_days}d old ({ref.file}:{ref.line})")
        parts.append("")

    if report.runbook:
        parts.append("  " + "-" * 50)
        parts.append("")
        for line in report.runbook.split("\n"):
            parts.append(f"  {line}")

    return "\n".join(parts)


def rotation_report_to_json(report: RotationReport) -> dict:
    """Convert report to JSON-serializable dict."""
    def _ref_dict(r: SecretRef) -> dict:
        return {
            "file": r.file, "line": r.line,
            "key_name": r.key_name, "age_days": r.age_days,
        }

    return {
        "max_age_days": report.max_age_days,
        "total": report.total,
        "stale_count": len(report.stale),
        "fresh_count": len(report.fresh),
        "unknown_count": len(report.unknown),
        "stale": [_ref_dict(r) for r in report.stale],
        "fresh": [_ref_dict(r) for r in report.fresh],
        "unknown": [_ref_dict(r) for r in report.unknown],
        "runbook": report.runbook,
    }
