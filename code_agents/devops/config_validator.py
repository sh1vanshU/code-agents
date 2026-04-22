"""Config File Validator — validate YAML, JSON, TOML, .env files in a project."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("code_agents.devops.config_validator")

# ── Common known keys for typo detection ─────────────────────────────────────
_KNOWN_ENV_KEYS = {
    "DATABASE_URL", "REDIS_URL", "SECRET_KEY", "API_KEY", "DEBUG", "PORT", "HOST",
    "LOG_LEVEL", "NODE_ENV", "PYTHONPATH", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
    "AWS_REGION", "SENTRY_DSN", "CORS_ORIGINS", "ALLOWED_HOSTS",
    "CODE_AGENTS_BACKEND", "CODE_AGENTS_MODEL", "CODE_AGENTS_AUTO_RUN",
    "CODE_AGENTS_DRY_RUN", "CODE_AGENTS_MAX_LOOPS", "CODE_AGENTS_CONTEXT_WINDOW",
    "CURSOR_API_KEY", "ANTHROPIC_API_KEY", "TARGET_REPO_PATH",
}


@dataclass
class ConfigFinding:
    """A single validation finding."""

    file: str
    line: int
    issue: str
    severity: str  # "error" | "warning" | "info"
    suggestion: str


class ConfigValidator:
    """Validate config files in a project directory."""

    def __init__(self, cwd: str):
        self.cwd = cwd

    # ── Public API ───────────────────────────────────────────────────────

    def validate(self) -> list[ConfigFinding]:
        """Scan for config files and validate each one."""
        findings: list[ConfigFinding] = []
        scanned = 0

        for root, _dirs, files in os.walk(self.cwd):
            # Skip hidden dirs and common large dirs
            rel_root = os.path.relpath(root, self.cwd)
            if any(
                part.startswith(".")
                or part in ("node_modules", "__pycache__", "venv", ".venv", "dist", "build")
                for part in Path(rel_root).parts
            ):
                continue

            for fname in files:
                full = os.path.join(root, fname)
                rel = os.path.relpath(full, self.cwd)

                if fname.endswith((".yaml", ".yml")):
                    findings.extend(self._validate_yaml(rel))
                    scanned += 1
                elif fname.endswith(".json") and not fname.startswith("package-lock"):
                    findings.extend(self._validate_json(rel))
                    scanned += 1
                elif fname.endswith(".toml"):
                    findings.extend(self._validate_toml(rel))
                    scanned += 1
                elif fname.startswith(".env") or fname.endswith(".env"):
                    findings.extend(self._validate_env(rel))
                    scanned += 1

            if scanned > 500:
                break  # safety cap

        logger.info("Validated %d config files, found %d issues", scanned, len(findings))
        return findings

    # ── YAML validation ──────────────────────────────────────────────────

    def _validate_yaml(self, path: str) -> list[ConfigFinding]:
        findings: list[ConfigFinding] = []
        full = os.path.join(self.cwd, path)
        try:
            with open(full, "r") as f:
                content = f.read()
        except OSError as e:
            findings.append(ConfigFinding(file=path, line=0, issue=f"Cannot read: {e}", severity="error", suggestion="Check file permissions"))
            return findings

        # Check for common YAML pitfalls (before parse, since tabs cause parse failure)
        for i, line in enumerate(content.splitlines(), 1):
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                # Tab indentation (YAML uses spaces)
                if line.startswith("\t"):
                    findings.append(ConfigFinding(file=path, line=i, issue="Tab indentation (YAML requires spaces)", severity="error", suggestion="Replace tabs with spaces"))
                # Trailing whitespace on value lines
                if ": " in stripped and stripped.endswith(" "):
                    findings.append(ConfigFinding(file=path, line=i, issue="Trailing whitespace after value", severity="info", suggestion="Remove trailing whitespace"))

        # Syntax check
        try:
            import yaml  # noqa: PLC0415

            docs = list(yaml.safe_load_all(content))
            if not docs or all(d is None for d in docs):
                findings.append(ConfigFinding(file=path, line=1, issue="YAML file is empty or all null documents", severity="warning", suggestion="Ensure file has valid content"))
        except ImportError:
            pass
        except yaml.YAMLError as e:
            line_num = getattr(e, "problem_mark", None)
            ln = (line_num.line + 1) if line_num else 1
            findings.append(ConfigFinding(file=path, line=ln, issue=f"YAML syntax error: {e}", severity="error", suggestion="Fix YAML syntax"))

        return findings

    # ── JSON validation ──────────────────────────────────────────────────

    def _validate_json(self, path: str) -> list[ConfigFinding]:
        findings: list[ConfigFinding] = []
        full = os.path.join(self.cwd, path)
        try:
            with open(full, "r") as f:
                content = f.read()
        except OSError as e:
            findings.append(ConfigFinding(file=path, line=0, issue=f"Cannot read: {e}", severity="error", suggestion="Check file permissions"))
            return findings

        if not content.strip():
            findings.append(ConfigFinding(file=path, line=1, issue="JSON file is empty", severity="warning", suggestion="Add valid JSON content or remove file"))
            return findings

        try:
            data = json.loads(content)
        except json.JSONDecodeError as e:
            findings.append(ConfigFinding(file=path, line=e.lineno, issue=f"JSON syntax error: {e.msg}", severity="error", suggestion="Fix JSON syntax"))
            return findings

        # Check for common issues
        if isinstance(data, dict):
            for key, value in data.items():
                if value is None:
                    findings.append(ConfigFinding(file=path, line=1, issue=f"Key '{key}' has null value", severity="info", suggestion=f"Set a value for '{key}' or remove it"))
                if isinstance(value, str) and value == "":
                    findings.append(ConfigFinding(file=path, line=1, issue=f"Key '{key}' has empty string value", severity="info", suggestion=f"Set a meaningful value for '{key}'"))

        # Trailing comma detection (common mistake, not valid JSON — already caught by decoder)
        for i, line in enumerate(content.splitlines(), 1):
            stripped = line.rstrip()
            if stripped.endswith(",}") or stripped.endswith(",]"):
                findings.append(ConfigFinding(file=path, line=i, issue="Trailing comma before closing bracket", severity="error", suggestion="Remove the trailing comma"))

        return findings

    # ── TOML validation ──────────────────────────────────────────────────

    def _validate_toml(self, path: str) -> list[ConfigFinding]:
        findings: list[ConfigFinding] = []
        full = os.path.join(self.cwd, path)
        try:
            with open(full, "r") as f:
                content = f.read()
        except OSError as e:
            findings.append(ConfigFinding(file=path, line=0, issue=f"Cannot read: {e}", severity="error", suggestion="Check file permissions"))
            return findings

        if not content.strip():
            findings.append(ConfigFinding(file=path, line=1, issue="TOML file is empty", severity="warning", suggestion="Add valid TOML content"))
            return findings

        # Try tomllib (3.11+) or tomli
        try:
            try:
                import tomllib  # noqa: PLC0415
            except ImportError:
                import tomli as tomllib  # noqa: PLC0415

            tomllib.loads(content)
        except ImportError:
            # No TOML parser available — do basic checks
            for i, line in enumerate(content.splitlines(), 1):
                stripped = line.strip()
                if "=" in stripped and not stripped.startswith("#") and not stripped.startswith("["):
                    key, _, value = stripped.partition("=")
                    value = value.strip()
                    if not value:
                        findings.append(ConfigFinding(file=path, line=i, issue=f"Key '{key.strip()}' has no value", severity="warning", suggestion="Provide a value or remove the key"))
        except Exception as e:  # noqa: BLE001
            findings.append(ConfigFinding(file=path, line=1, issue=f"TOML parse error: {e}", severity="error", suggestion="Fix TOML syntax"))

        return findings

    # ── .env validation ──────────────────────────────────────────────────

    def _validate_env(self, path: str) -> list[ConfigFinding]:
        findings: list[ConfigFinding] = []
        full = os.path.join(self.cwd, path)
        try:
            with open(full, "r") as f:
                lines = f.readlines()
        except OSError as e:
            findings.append(ConfigFinding(file=path, line=0, issue=f"Cannot read: {e}", severity="error", suggestion="Check file permissions"))
            return findings

        keys_seen: list[str] = []
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue

            if "=" not in stripped:
                findings.append(ConfigFinding(file=path, line=i, issue="Line has no '=' separator", severity="warning", suggestion="Use KEY=VALUE format"))
                continue

            key, _, value = stripped.partition("=")
            key = key.strip()
            value = value.strip()

            # Empty value
            if not value or value in ('""', "''"):
                findings.append(ConfigFinding(file=path, line=i, issue=f"'{key}' has empty value", severity="warning", suggestion=f"Set a value for {key} or add a comment explaining why it is empty"))

            # Duplicate key
            if key in keys_seen:
                findings.append(ConfigFinding(file=path, line=i, issue=f"Duplicate key '{key}'", severity="warning", suggestion="Remove the duplicate — only the last value will be used"))
            keys_seen.append(key)

            # Typo detection against known keys
            typo_suggestions = self._check_typos([key], _KNOWN_ENV_KEYS)
            for suggestion in typo_suggestions:
                findings.append(ConfigFinding(file=path, line=i, issue=f"Possible typo: '{key}'", severity="info", suggestion=suggestion))

        return findings

    # ── Typo detection ───────────────────────────────────────────────────

    def _check_typos(self, keys: list[str], known_keys: set[str]) -> list[str]:
        """Check if any key is a likely typo of a known key using Levenshtein distance."""
        suggestions: list[str] = []
        for key in keys:
            if key in known_keys:
                continue
            for known in known_keys:
                dist = _levenshtein(key.upper(), known.upper())
                if 0 < dist <= 2 and len(key) > 3:
                    suggestions.append(f"Did you mean '{known}'?")
                    break
        return suggestions


def _levenshtein(s: str, t: str) -> int:
    """Compute Levenshtein edit distance between two strings."""
    if len(s) < len(t):
        return _levenshtein(t, s)
    if len(t) == 0:
        return len(s)
    prev = list(range(len(t) + 1))
    for i, sc in enumerate(s):
        curr = [i + 1]
        for j, tc in enumerate(t):
            cost = 0 if sc == tc else 1
            curr.append(min(curr[j] + 1, prev[j + 1] + 1, prev[j] + cost))
        prev = curr
    return prev[len(t)]


# ── Formatting helpers ───────────────────────────────────────────────────────


def format_config_report(findings: list[ConfigFinding]) -> str:
    """Return a human-readable validation report."""
    if not findings:
        return "  All config files are valid — no issues found."

    sev_icon = {"error": "!", "warning": "~", "info": "."}
    lines: list[str] = ["", "  Config Validation Report", "  " + "-" * 50]

    by_file: dict[str, list[ConfigFinding]] = {}
    for f in findings:
        by_file.setdefault(f.file, []).append(f)

    for filepath, file_findings in sorted(by_file.items()):
        lines.append(f"  {filepath}")
        for ff in file_findings:
            icon = sev_icon.get(ff.severity, "?")
            lines.append(f"    [{icon}] L{ff.line}: {ff.issue}")
            if ff.suggestion:
                lines.append(f"         -> {ff.suggestion}")
        lines.append("")

    errors = sum(1 for f in findings if f.severity == "error")
    warnings = sum(1 for f in findings if f.severity == "warning")
    infos = sum(1 for f in findings if f.severity == "info")
    lines.append(f"  Summary: {errors} errors, {warnings} warnings, {infos} info")
    lines.append("")
    return "\n".join(lines)
