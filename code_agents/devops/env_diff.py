"""Environment Diff Checker — compare .env files across environments.

Parses .env.dev, .env.staging, .env.prod etc. and shows differences,
missing keys, and flags secret-bearing keys that differ.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.devops.env_diff")

# Patterns that indicate a key holds a secret value
_SECRET_PATTERNS = re.compile(
    r"(PASSWORD|TOKEN|SECRET|KEY|API_KEY|APIKEY|AUTH|CREDENTIAL|PRIVATE|"
    r"ENCRYPTION|SIGNING|ACCESS_KEY|JWT|HMAC|SALT|HASH)",
    re.IGNORECASE,
)


@dataclass
class EnvDiffResult:
    """Result of comparing two environment configurations."""

    env_a: str
    env_b: str
    missing_in_b: list[str] = field(default_factory=list)
    missing_in_a: list[str] = field(default_factory=list)
    different_values: list[dict] = field(default_factory=list)
    secrets_differ: list[str] = field(default_factory=list)

    @property
    def has_differences(self) -> bool:
        return bool(self.missing_in_a or self.missing_in_b or self.different_values)

    @property
    def total_diffs(self) -> int:
        return len(self.missing_in_a) + len(self.missing_in_b) + len(self.different_values)

    def summary(self) -> str:
        """One-line summary of differences."""
        parts = []
        if self.missing_in_b:
            parts.append(f"{len(self.missing_in_b)} missing in {self.env_b}")
        if self.missing_in_a:
            parts.append(f"{len(self.missing_in_a)} missing in {self.env_a}")
        if self.different_values:
            parts.append(f"{len(self.different_values)} values differ")
        if self.secrets_differ:
            parts.append(f"{len(self.secrets_differ)} secrets differ")
        return "; ".join(parts) if parts else "No differences"


class EnvDiffChecker:
    """Compare environment configuration files for discrepancies."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        logger.debug("EnvDiffChecker initialized, cwd=%s", cwd)

    def compare(self, env_a: str, env_b: str) -> EnvDiffResult:
        """Compare two environment configs.

        Args:
            env_a: Name of the first environment (e.g. 'dev', 'staging').
                   Resolves to .env.dev, .env.staging, etc.
            env_b: Name of the second environment.

        Returns:
            EnvDiffResult with all differences catalogued.
        """
        logger.info("Comparing environments: %s vs %s", env_a, env_b)

        data_a = self._load_env(env_a)
        data_b = self._load_env(env_b)

        keys_a = set(data_a.keys())
        keys_b = set(data_b.keys())

        missing_in_b = sorted(keys_a - keys_b)
        missing_in_a = sorted(keys_b - keys_a)

        common_keys = keys_a & keys_b
        different_values: list[dict] = []
        secrets_differ: list[str] = []

        for key in sorted(common_keys):
            val_a = data_a[key]
            val_b = data_b[key]
            if val_a != val_b:
                is_secret = self._is_secret_key(key)
                entry = {
                    "key": key,
                    "value_a": "***" if is_secret else val_a,
                    "value_b": "***" if is_secret else val_b,
                    "is_secret": is_secret,
                }
                different_values.append(entry)
                if is_secret:
                    secrets_differ.append(key)

        result = EnvDiffResult(
            env_a=env_a,
            env_b=env_b,
            missing_in_b=missing_in_b,
            missing_in_a=missing_in_a,
            different_values=different_values,
            secrets_differ=secrets_differ,
        )
        logger.info(
            "Diff result: %d missing_in_b, %d missing_in_a, %d different, %d secrets",
            len(missing_in_b),
            len(missing_in_a),
            len(different_values),
            len(secrets_differ),
        )
        return result

    def _load_env(self, env_name: str) -> dict[str, str]:
        """Load and parse an environment file.

        Searches for files in order:
        1. .env.<name>  (e.g. .env.dev)
        2. .env.<name>.local
        3. env/<name>.env
        4. config/<name>.env

        Args:
            env_name: Environment name (dev, staging, prod, etc.).

        Returns:
            Dictionary of key-value pairs from the env file.
        """
        candidates = [
            Path(self.cwd) / f".env.{env_name}",
            Path(self.cwd) / f".env.{env_name}.local",
            Path(self.cwd) / "env" / f"{env_name}.env",
            Path(self.cwd) / "config" / f"{env_name}.env",
            Path(self.cwd) / f".env-{env_name}",
        ]

        for candidate in candidates:
            if candidate.exists():
                logger.debug("Loading env '%s' from %s", env_name, candidate)
                return self._parse_env_file(candidate)

        logger.warning("No env file found for '%s' in %s", env_name, self.cwd)
        return {}

    @staticmethod
    def _parse_env_file(path: Path) -> dict[str, str]:
        """Parse a .env file into key-value pairs.

        Handles:
        - KEY=VALUE
        - KEY="VALUE" (strips quotes)
        - KEY='VALUE' (strips quotes)
        - Comments (#)
        - Empty lines
        - export KEY=VALUE
        """
        result: dict[str, str] = {}
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
        except OSError as exc:
            logger.warning("Cannot read %s: %s", path, exc)
            return result

        for line_num, line in enumerate(content.splitlines(), 1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # Strip optional 'export ' prefix
            if line.startswith("export "):
                line = line[7:].strip()

            if "=" not in line:
                continue

            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()

            # Strip surrounding quotes
            if len(value) >= 2:
                if (value.startswith('"') and value.endswith('"')) or (
                    value.startswith("'") and value.endswith("'")
                ):
                    value = value[1:-1]

            # Strip inline comments (only if not inside quotes)
            if " #" in value:
                value = value.split(" #")[0].strip()

            if key:
                result[key] = value

        logger.debug("Parsed %d keys from %s", len(result), path)
        return result

    @staticmethod
    def _is_secret_key(key: str) -> bool:
        """Check if a key name suggests it holds a secret value.

        Args:
            key: The environment variable name.

        Returns:
            True if the key matches secret patterns.
        """
        return bool(_SECRET_PATTERNS.search(key))

    def list_environments(self) -> list[str]:
        """Discover available environment files in the project.

        Returns:
            List of environment names found (e.g. ['dev', 'staging', 'prod']).
        """
        envs: set[str] = set()
        cwd = Path(self.cwd)

        # .env.<name> pattern
        for path in cwd.glob(".env.*"):
            name = path.name.replace(".env.", "").replace(".local", "")
            if name and not name.startswith("."):
                envs.add(name)

        # .env-<name> pattern
        for path in cwd.glob(".env-*"):
            name = path.name.replace(".env-", "")
            if name:
                envs.add(name)

        # env/<name>.env pattern
        env_dir = cwd / "env"
        if env_dir.is_dir():
            for path in env_dir.glob("*.env"):
                envs.add(path.stem)

        # config/<name>.env pattern
        config_dir = cwd / "config"
        if config_dir.is_dir():
            for path in config_dir.glob("*.env"):
                envs.add(path.stem)

        result = sorted(envs)
        logger.debug("Found environments: %s", result)
        return result
