"""Environment Differ — diff env vars, configs, and versions between environments.

Compares local vs staging vs prod configs to find mismatches,
missing variables, and suspicious values.

Usage:
    from code_agents.devops.env_differ import EnvDiffer
    differ = EnvDiffer()
    result = differ.diff_files("local.env", "staging.env")
    print(format_env_diff(result))
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.devops.env_differ")


@dataclass
class EnvDiffConfig:
    cwd: str = "."
    mask_secrets: bool = True


@dataclass
class EnvDiffEntry:
    """A single diff entry between environments."""
    key: str
    left_value: str = ""
    right_value: str = ""
    diff_type: str = ""  # "missing_left", "missing_right", "different", "same"
    is_secret: bool = False
    severity: str = "info"  # "info", "warning", "critical"


@dataclass
class EnvDiffResult:
    """Result of comparing two environments."""
    left_name: str = ""
    right_name: str = ""
    total_keys: int = 0
    missing_left: int = 0
    missing_right: int = 0
    different: int = 0
    same: int = 0
    entries: list[EnvDiffEntry] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    summary: str = ""


SECRET_PATTERNS = re.compile(
    r"(password|secret|token|key|credential|auth|api_key|apikey|private|cert)",
    re.IGNORECASE,
)

CRITICAL_KEYS = frozenset({
    "DATABASE_URL", "DB_HOST", "DB_PORT", "DB_NAME",
    "REDIS_URL", "REDIS_HOST",
    "API_KEY", "SECRET_KEY", "JWT_SECRET",
    "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
})


class EnvDiffer:
    """Compare environment configurations."""

    def __init__(self, config: Optional[EnvDiffConfig] = None):
        self.config = config or EnvDiffConfig()

    def diff_files(self, left_path: str, right_path: str) -> EnvDiffResult:
        """Diff two .env files."""
        left_name = os.path.basename(left_path)
        right_name = os.path.basename(right_path)

        left_vars = self._parse_env_file(left_path)
        right_vars = self._parse_env_file(right_path)

        return self._compare(left_vars, right_vars, left_name, right_name)

    def diff_dicts(self, left: dict, right: dict, left_name: str = "left", right_name: str = "right") -> EnvDiffResult:
        """Diff two environment variable dicts."""
        return self._compare(left, right, left_name, right_name)

    def _parse_env_file(self, path: str) -> dict[str, str]:
        """Parse a .env file into a dict."""
        full_path = os.path.join(self.config.cwd, path) if not os.path.isabs(path) else path
        result: dict[str, str] = {}
        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, _, value = line.partition("=")
                        key = key.strip()
                        value = value.strip().strip("'\"")
                        result[key] = value
        except OSError:
            logger.warning("Could not read env file: %s", path)
        return result

    def _compare(self, left: dict, right: dict, left_name: str, right_name: str) -> EnvDiffResult:
        """Compare two env dicts."""
        result = EnvDiffResult(left_name=left_name, right_name=right_name)
        all_keys = sorted(set(left.keys()) | set(right.keys()))
        result.total_keys = len(all_keys)

        for key in all_keys:
            in_left = key in left
            in_right = key in right
            is_secret = bool(SECRET_PATTERNS.search(key))

            entry = EnvDiffEntry(key=key, is_secret=is_secret)

            if in_left and in_right:
                lv = left[key]
                rv = right[key]
                if self.config.mask_secrets and is_secret:
                    entry.left_value = "***"
                    entry.right_value = "***" if lv != rv else "***"
                else:
                    entry.left_value = lv
                    entry.right_value = rv

                if lv == rv:
                    entry.diff_type = "same"
                    result.same += 1
                else:
                    entry.diff_type = "different"
                    result.different += 1
                    entry.severity = "critical" if key.upper() in CRITICAL_KEYS else "warning"
            elif in_left and not in_right:
                entry.diff_type = "missing_right"
                entry.left_value = "***" if (self.config.mask_secrets and is_secret) else left[key]
                result.missing_right += 1
                entry.severity = "warning"
            else:
                entry.diff_type = "missing_left"
                entry.right_value = "***" if (self.config.mask_secrets and is_secret) else right[key]
                result.missing_left += 1
                entry.severity = "warning"

            result.entries.append(entry)

        # Warnings
        if result.different > 0:
            result.warnings.append(f"{result.different} keys have different values")
        if result.missing_left > 0:
            result.warnings.append(f"{result.missing_left} keys missing from {left_name}")
        if result.missing_right > 0:
            result.warnings.append(f"{result.missing_right} keys missing from {right_name}")

        # Suspicious patterns
        for entry in result.entries:
            if entry.diff_type == "same" and entry.key.upper() in CRITICAL_KEYS:
                result.warnings.append(f"{entry.key} is identical across environments — possibly using dev defaults in prod")

        result.summary = f"{result.total_keys} keys: {result.same} same, {result.different} different, {result.missing_left + result.missing_right} missing"
        return result


def format_env_diff(result: EnvDiffResult) -> str:
    """Format env diff for terminal output."""
    lines = []
    lines.append(f"{'=' * 60}")
    lines.append(f"  Env Diff: {result.left_name} vs {result.right_name}")
    lines.append(f"{'=' * 60}")
    lines.append(f"  {result.summary}")

    if result.warnings:
        lines.append(f"\n  Warnings:")
        for w in result.warnings:
            lines.append(f"    ! {w}")

    # Show differences
    diffs = [e for e in result.entries if e.diff_type != "same"]
    if diffs:
        lines.append(f"\n  Differences ({len(diffs)}):")
        for entry in diffs:
            icon = {"different": "~", "missing_left": "<", "missing_right": ">"}[entry.diff_type]
            sev = {"info": " ", "warning": "!", "critical": "X"}[entry.severity]
            secret = " [SECRET]" if entry.is_secret else ""
            if entry.diff_type == "different":
                lines.append(f"    {sev} {icon} {entry.key}{secret}")
                lines.append(f"        {result.left_name}: {entry.left_value}")
                lines.append(f"        {result.right_name}: {entry.right_value}")
            elif entry.diff_type == "missing_right":
                lines.append(f"    {sev} {icon} {entry.key}{secret}  (only in {result.left_name})")
            else:
                lines.append(f"    {sev} {icon} {entry.key}{secret}  (only in {result.right_name})")

    lines.append("")
    return "\n".join(lines)
