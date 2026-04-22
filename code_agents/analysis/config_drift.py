"""Config Drift Detector — compares configs across environments."""

import logging
import os
import re
import json
try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.analysis.config_drift")

@dataclass
class ConfigDiff:
    env_a: str
    env_b: str
    only_in_a: list[dict] = field(default_factory=list)  # key, value
    only_in_b: list[dict] = field(default_factory=list)  # key, value
    different_values: list[dict] = field(default_factory=list)  # key, value_a, value_b
    same_values: int = 0

@dataclass
class DriftReport:
    environments: list[str]
    diffs: list[ConfigDiff] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)  # potential issues


class ConfigDriftDetector:
    """Detects configuration drift between environments."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        self.configs: dict[str, dict] = {}  # env_name -> {key: value}

    def load_configs(self) -> dict[str, dict]:
        """Auto-detect and load config files for all environments."""
        logger.info("Loading configs from %s", self.cwd)

        # Strategy 1: Spring profiles (application-{env}.yml / .properties)
        self._load_spring_profiles()

        # Strategy 2: .env files (.env.dev, .env.staging, .env.prod)
        self._load_env_files()

        # Strategy 3: Config directories (config/dev/, config/staging/, config/prod/)
        self._load_config_dirs()

        # Strategy 4: Kubernetes ConfigMaps
        self._load_k8s_configs()

        logger.info("Loaded configs for %d environments: %s", len(self.configs), list(self.configs.keys()))
        return self.configs

    def _load_spring_profiles(self):
        """Load Spring application-{env}.yml/.properties files."""
        patterns = [
            "src/main/resources",
            "config",
        ]
        for base_dir in patterns:
            full_base = os.path.join(self.cwd, base_dir)
            if not os.path.isdir(full_base):
                continue
            for f in os.listdir(full_base):
                match = re.match(r'application-(\w+)\.(yml|yaml|properties)$', f)
                if match:
                    env_name = match.group(1)
                    ext = match.group(2)
                    fpath = os.path.join(full_base, f)
                    try:
                        if ext in ('yml', 'yaml'):
                            self.configs[env_name] = self._flatten_yaml(fpath)
                        else:
                            self.configs[env_name] = self._parse_properties(fpath)
                        logger.debug("Loaded spring profile: %s from %s", env_name, fpath)
                    except Exception as e:
                        logger.warning("Could not parse %s: %s", fpath, e)

    def _load_env_files(self):
        """Load .env.{env} files."""
        if not os.path.isdir(self.cwd):
            return
        for f in os.listdir(self.cwd):
            match = re.match(r'\.env\.(\w+)$', f)
            if match:
                env_name = match.group(1)
                if env_name in ('example', 'template', 'sample', 'code-agents'):
                    continue
                fpath = os.path.join(self.cwd, f)
                self.configs[env_name] = self._parse_env_file(fpath)
                logger.debug("Loaded env file: %s from %s", env_name, fpath)

    def _load_config_dirs(self):
        """Load from config/{env}/ directories."""
        config_dir = os.path.join(self.cwd, "config")
        if not os.path.isdir(config_dir):
            return
        known_envs = ('dev', 'development', 'staging', 'stage', 'prod', 'production', 'qa', 'uat', 'local')
        for env_dir in os.listdir(config_dir):
            env_path = os.path.join(config_dir, env_dir)
            if os.path.isdir(env_path) and env_dir in known_envs:
                merged = {}
                for f in os.listdir(env_path):
                    fpath = os.path.join(env_path, f)
                    if f.endswith(('.yml', '.yaml')):
                        merged.update(self._flatten_yaml(fpath))
                    elif f.endswith('.properties'):
                        merged.update(self._parse_properties(fpath))
                    elif f.endswith('.json'):
                        try:
                            with open(fpath) as fp:
                                merged.update(self._flatten_dict(json.load(fp)))
                        except Exception as e:
                            logger.warning("Config parse error in %s: %s", fpath, e)
                    elif f.endswith('.env') or f.startswith('.env'):
                        merged.update(self._parse_env_file(fpath))
                if merged:
                    self.configs[env_dir] = merged
                    logger.debug("Loaded config dir: %s with %d keys", env_dir, len(merged))

    def _load_k8s_configs(self):
        """Load Kubernetes ConfigMap/Secret YAML files."""
        if yaml is None:
            return
        k8s_dirs = ['k8s', 'kubernetes', 'deploy', 'deployments', 'manifests']
        for d in k8s_dirs:
            dir_path = os.path.join(self.cwd, d)
            if not os.path.isdir(dir_path):
                continue
            for root, _, files in os.walk(dir_path):
                for f in files:
                    if f.endswith(('.yml', '.yaml')):
                        fpath = os.path.join(root, f)
                        try:
                            with open(fpath) as fp:
                                docs = list(yaml.safe_load_all(fp))
                            for doc in docs:
                                if not isinstance(doc, dict):
                                    continue
                                kind = doc.get("kind", "")
                                if kind in ("ConfigMap", "Secret"):
                                    name = doc.get("metadata", {}).get("name", "")
                                    data = doc.get("data", {})
                                    env = self._guess_env_from_name(name)
                                    if env and data:
                                        self.configs.setdefault(env, {}).update(
                                            {f"{name}.{k}": v for k, v in data.items()}
                                        )
                                        logger.debug("Loaded k8s %s: %s (%d keys)", kind, name, len(data))
                        except Exception as e:
                            logger.warning("Config parse error in %s: %s", fpath, e)

    def _guess_env_from_name(self, name: str) -> Optional[str]:
        """Guess environment from resource name."""
        name_lower = name.lower()
        for env in ['prod', 'production', 'staging', 'stage', 'dev', 'development', 'qa', 'uat']:
            if env in name_lower:
                return env
        return None

    def _flatten_yaml(self, path: str) -> dict:
        """Parse YAML and flatten to dot-notation keys."""
        if yaml is None:
            logger.warning("PyYAML not installed — cannot parse %s", path)
            return {}
        with open(path) as f:
            data = yaml.safe_load(f) or {}
        return self._flatten_dict(data)

    def _flatten_dict(self, d: dict, prefix: str = "") -> dict:
        """Flatten nested dict to dot-notation."""
        result = {}
        for k, v in d.items():
            key = f"{prefix}.{k}" if prefix else str(k)
            if isinstance(v, dict):
                result.update(self._flatten_dict(v, key))
            else:
                result[key] = str(v) if v is not None else ""
        return result

    def _parse_properties(self, path: str) -> dict:
        """Parse Java .properties file."""
        result = {}
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#') or line.startswith('!'):
                    continue
                if '=' in line:
                    key, _, value = line.partition('=')
                    result[key.strip()] = value.strip()
                elif ':' in line:
                    key, _, value = line.partition(':')
                    result[key.strip()] = value.strip()
        return result

    def _parse_env_file(self, path: str) -> dict:
        """Parse .env file."""
        result = {}
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, _, value = line.partition('=')
                    value = value.strip().strip('"').strip("'")
                    result[key.strip()] = value
        return result

    def compare(self, env_a: str, env_b: str) -> ConfigDiff:
        """Compare two environments."""
        a = self.configs.get(env_a, {})
        b = self.configs.get(env_b, {})

        diff = ConfigDiff(env_a=env_a, env_b=env_b)

        all_keys = set(a.keys()) | set(b.keys())
        for key in sorted(all_keys):
            if key in a and key not in b:
                diff.only_in_a.append({"key": key, "value": self._mask_sensitive(key, a[key])})
            elif key in b and key not in a:
                diff.only_in_b.append({"key": key, "value": self._mask_sensitive(key, b[key])})
            elif a[key] != b[key]:
                diff.different_values.append({
                    "key": key,
                    "value_a": self._mask_sensitive(key, a[key]),
                    "value_b": self._mask_sensitive(key, b[key]),
                })
            else:
                diff.same_values += 1

        return diff

    def compare_all(self) -> DriftReport:
        """Compare all environment pairs."""
        envs = sorted(self.configs.keys())
        report = DriftReport(environments=envs)

        for i in range(len(envs)):
            for j in range(i + 1, len(envs)):
                diff = self.compare(envs[i], envs[j])
                report.diffs.append(diff)

        # Generate warnings
        for diff in report.diffs:
            if diff.only_in_a:
                report.warnings.append(f"{len(diff.only_in_a)} keys only in {diff.env_a} (missing from {diff.env_b})")
            if diff.only_in_b:
                report.warnings.append(f"{len(diff.only_in_b)} keys only in {diff.env_b} (missing from {diff.env_a})")
            # Check for potential secrets with same value across envs
            for item in diff.different_values:
                if any(w in item["key"].lower() for w in ("password", "secret", "token", "key", "credential")):
                    if item["value_a"] == item["value_b"]:
                        report.warnings.append(f"Same secret value for '{item['key']}' across {diff.env_a}/{diff.env_b}")

        return report

    def _mask_sensitive(self, key: str, value: str) -> str:
        """Mask sensitive values."""
        sensitive_words = ('password', 'secret', 'token', 'key', 'credential', 'auth', 'api_key')
        if any(w in key.lower() for w in sensitive_words):
            if len(value) > 4:
                return value[:3] + "***"
            return "***"
        return value


def format_drift_report(report: DriftReport) -> str:
    """Format report for terminal display."""
    lines = []
    lines.append("  Config Drift Report")
    lines.append(f"  Environments: {', '.join(report.environments)}")
    lines.append(f"  {'=' * 50}")

    for diff in report.diffs:
        lines.append(f"\n  {diff.env_a} vs {diff.env_b}:")
        lines.append(f"  {'─' * 40}")
        lines.append(f"    Same: {diff.same_values} | Different: {len(diff.different_values)} | Only {diff.env_a}: {len(diff.only_in_a)} | Only {diff.env_b}: {len(diff.only_in_b)}")

        if diff.different_values:
            lines.append(f"\n    Different Values:")
            for item in diff.different_values[:15]:
                lines.append(f"      {item['key']}:")
                lines.append(f"        {diff.env_a}: {item['value_a']}")
                lines.append(f"        {diff.env_b}: {item['value_b']}")
            if len(diff.different_values) > 15:
                lines.append(f"      ... and {len(diff.different_values) - 15} more")

        if diff.only_in_a:
            lines.append(f"\n    Only in {diff.env_a} ({len(diff.only_in_a)}):")
            for item in diff.only_in_a[:10]:
                lines.append(f"      + {item['key']} = {item['value']}")
            if len(diff.only_in_a) > 10:
                lines.append(f"      ... and {len(diff.only_in_a) - 10} more")

        if diff.only_in_b:
            lines.append(f"\n    Only in {diff.env_b} ({len(diff.only_in_b)}):")
            for item in diff.only_in_b[:10]:
                lines.append(f"      + {item['key']} = {item['value']}")
            if len(diff.only_in_b) > 10:
                lines.append(f"      ... and {len(diff.only_in_b) - 10} more")

    if report.warnings:
        lines.append(f"\n  Warnings:")
        for w in report.warnings:
            lines.append(f"    ! {w}")

    return "\n".join(lines)
