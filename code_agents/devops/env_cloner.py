"""Env Cloner — clone environment configs, templatize, generate ephemeral setups."""

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.devops.env_cloner")


@dataclass
class EnvVariable:
    """A single environment variable with metadata."""
    key: str = ""
    value: str = ""
    is_secret: bool = False
    source_file: str = ""
    category: str = ""  # database, api, feature, infra, other


@dataclass
class EnvTemplate:
    """A templatized environment configuration."""
    name: str = ""
    variables: list[EnvVariable] = field(default_factory=list)
    template_content: str = ""
    required_secrets: list[str] = field(default_factory=list)
    optional_overrides: list[str] = field(default_factory=list)


@dataclass
class EphemeralEnvSetup:
    """Generated setup for an ephemeral environment."""
    name: str = ""
    env_file_content: str = ""
    docker_compose_override: str = ""
    setup_script: str = ""
    teardown_script: str = ""
    ttl_hours: int = 24


@dataclass
class CloneReport:
    """Report from environment cloning operation."""
    source_env: str = ""
    templates: list[EnvTemplate] = field(default_factory=list)
    ephemeral_setup: Optional[EphemeralEnvSetup] = None
    variables_found: int = 0
    secrets_detected: int = 0
    categories: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


SECRET_PATTERNS = [
    re.compile(r"(password|secret|token|key|credential|api_key|apikey|auth)", re.IGNORECASE),
]

CATEGORY_PATTERNS = {
    "database": re.compile(r"(db|database|postgres|mysql|mongo|redis|sql)", re.IGNORECASE),
    "api": re.compile(r"(api|endpoint|url|uri|host|port|base_url)", re.IGNORECASE),
    "feature": re.compile(r"(feature|flag|toggle|enable|disable)", re.IGNORECASE),
    "infra": re.compile(r"(aws|gcp|azure|s3|bucket|region|cluster|k8s|kube)", re.IGNORECASE),
    "auth": re.compile(r"(auth|oauth|jwt|saml|sso|ldap)", re.IGNORECASE),
}


class EnvCloner:
    """Clones, templatizes, and generates ephemeral environment configurations."""

    def __init__(self, cwd: str):
        self.cwd = cwd

    def analyze(self, source_env: str = "production",
                target_name: str = "ephemeral",
                ttl_hours: int = 24) -> CloneReport:
        """Main entry: extract env configs, templatize, generate ephemeral setup."""
        logger.info("Cloning environment from %s in %s", source_env, self.cwd)

        # Step 1: Extract variables from all env sources
        variables = self._extract_variables()
        logger.info("Found %d environment variables", len(variables))

        # Step 2: Categorize and detect secrets
        for var in variables:
            var.category = self._categorize(var.key)
            var.is_secret = self._is_secret(var.key, var.value)

        # Step 3: Generate template
        template = self._generate_template(source_env, variables)

        # Step 4: Generate ephemeral setup
        ephemeral = self._generate_ephemeral(target_name, template, ttl_hours)

        categories: dict[str, int] = {}
        secrets_count = 0
        for var in variables:
            categories[var.category] = categories.get(var.category, 0) + 1
            if var.is_secret:
                secrets_count += 1

        report = CloneReport(
            source_env=source_env,
            templates=[template],
            ephemeral_setup=ephemeral,
            variables_found=len(variables),
            secrets_detected=secrets_count,
            categories=categories,
            warnings=self._generate_warnings(variables),
        )
        logger.info("Clone report: %d vars, %d secrets", len(variables), secrets_count)
        return report

    def _extract_variables(self) -> list[EnvVariable]:
        """Extract environment variables from all config sources."""
        variables = []
        cwd = Path(self.cwd)

        # .env files
        for env_file in cwd.glob(".env*"):
            if env_file.is_file() and env_file.stat().st_size < 100_000:
                try:
                    variables.extend(self._parse_env_file(str(env_file)))
                except Exception as exc:
                    logger.warning("Failed to parse %s: %s", env_file, exc)

        # docker-compose.yml environment sections
        compose_files = list(cwd.glob("docker-compose*.yml")) + list(cwd.glob("docker-compose*.yaml"))
        for cf in compose_files:
            variables.extend(self._parse_compose_env(str(cf)))

        return variables

    def _parse_env_file(self, fpath: str) -> list[EnvVariable]:
        """Parse a .env file into variables."""
        variables = []
        with open(fpath) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip("'\"")
                    variables.append(EnvVariable(
                        key=key, value=value, source_file=fpath,
                    ))
        return variables

    def _parse_compose_env(self, fpath: str) -> list[EnvVariable]:
        """Extract environment variables from docker-compose file."""
        variables = []
        try:
            with open(fpath) as f:
                content = f.read()
            env_pattern = re.compile(r"^\s+-\s+(\w+)=(.+)$", re.MULTILINE)
            for m in env_pattern.finditer(content):
                variables.append(EnvVariable(
                    key=m.group(1), value=m.group(2).strip(),
                    source_file=fpath,
                ))
        except Exception as exc:
            logger.warning("Failed to parse compose %s: %s", fpath, exc)
        return variables

    def _categorize(self, key: str) -> str:
        """Categorize a variable by its key name."""
        for category, pattern in CATEGORY_PATTERNS.items():
            if pattern.search(key):
                return category
        return "other"

    def _is_secret(self, key: str, value: str) -> bool:
        """Detect if a variable is likely a secret."""
        for pattern in SECRET_PATTERNS:
            if pattern.search(key):
                return True
        if len(value) > 20 and re.match(r"^[A-Za-z0-9+/=_-]+$", value):
            return True
        return False

    def _generate_template(self, env_name: str, variables: list[EnvVariable]) -> EnvTemplate:
        """Generate a template from extracted variables."""
        lines = [f"# Environment template generated from {env_name}", ""]
        required_secrets = []
        optional_overrides = []

        for var in variables:
            if var.is_secret:
                lines.append(f"{var.key}=${{{{ {var.key} }}}}")
                required_secrets.append(var.key)
            else:
                lines.append(f"{var.key}={var.value}")
                optional_overrides.append(var.key)

        return EnvTemplate(
            name=env_name,
            variables=variables,
            template_content="\n".join(lines),
            required_secrets=required_secrets,
            optional_overrides=optional_overrides,
        )

    def _generate_ephemeral(self, name: str, template: EnvTemplate,
                            ttl_hours: int) -> EphemeralEnvSetup:
        """Generate an ephemeral environment setup."""
        env_content = template.template_content.replace(
            "# Environment template", f"# Ephemeral environment: {name}"
        )

        setup_script = f"""#!/bin/bash
# Setup ephemeral environment: {name}
# TTL: {ttl_hours} hours
set -euo pipefail

echo "Creating ephemeral environment: {name}"
cp .env.template .env.{name}

# Replace secret placeholders
for secret in {' '.join(template.required_secrets[:5])}; do
    read -sp "Enter $secret: " value
    sed -i "s|\\${{{{ $secret }}}}|$value|g" .env.{name}
done

echo "Environment {name} ready. TTL: {ttl_hours}h"
"""

        teardown_script = f"""#!/bin/bash
# Teardown ephemeral environment: {name}
set -euo pipefail
echo "Tearing down ephemeral environment: {name}"
rm -f .env.{name}
echo "Done."
"""

        return EphemeralEnvSetup(
            name=name,
            env_file_content=env_content,
            setup_script=setup_script,
            teardown_script=teardown_script,
            ttl_hours=ttl_hours,
        )

    def _generate_warnings(self, variables: list[EnvVariable]) -> list[str]:
        """Generate warnings about the environment config."""
        warnings = []
        secret_vars = [v for v in variables if v.is_secret]
        if secret_vars:
            warnings.append(f"{len(secret_vars)} secrets detected — use vault/secrets manager")
        dupes = {}
        for v in variables:
            dupes.setdefault(v.key, []).append(v.source_file)
        for key, sources in dupes.items():
            if len(sources) > 1:
                warnings.append(f"Duplicate key '{key}' in: {', '.join(sources)}")
        return warnings


def format_report(report: CloneReport) -> str:
    """Format clone report as text."""
    lines = [
        "# Environment Clone Report",
        f"Source: {report.source_env}",
        f"Variables: {report.variables_found} | Secrets: {report.secrets_detected}",
        "",
    ]
    if report.categories:
        lines.append("## Categories")
        for cat, count in sorted(report.categories.items()):
            lines.append(f"  {cat}: {count}")
    if report.warnings:
        lines.append("\n## Warnings")
        for w in report.warnings:
            lines.append(f"  - {w}")
    return "\n".join(lines)
