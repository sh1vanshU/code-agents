"""Feature Flag Manager — find and manage feature flags in codebase."""

import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.analysis.feature_flags")


@dataclass
class FeatureFlag:
    """A detected feature flag."""

    name: str
    file: str
    line: int
    flag_type: str = ""  # boolean, string, enum
    default_value: str = ""
    env_values: dict = field(default_factory=dict)  # env -> value
    references: list[dict] = field(default_factory=list)  # other files referencing this flag
    stale: bool = False  # defined but never checked in code
    last_modified: str = ""


@dataclass
class FlagReport:
    """Aggregated scan results."""

    total_flags: int = 0
    flags: list[FeatureFlag] = field(default_factory=list)
    stale_flags: list[FeatureFlag] = field(default_factory=list)
    env_matrix: dict = field(default_factory=dict)  # flag_name -> {env -> value}


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

class FeatureFlagScanner:
    """Scans a codebase for feature flags across languages and config formats."""

    _FLAG_PATTERNS = [
        "FEATURE_", "ENABLE_", "_ENABLED", "_FLAG",
        "FF_", "TOGGLE_", "_TOGGLE", "USE_", "_ACTIVE",
    ]

    def __init__(self, cwd: str, exclude_dirs: Optional[list[str]] = None):
        self.cwd = cwd
        self.exclude_dirs = exclude_dirs or [
            ".git", "node_modules", "__pycache__", ".venv", "venv",
            "build", "dist", "target", ".tox", ".mypy_cache",
        ]

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def scan(self) -> FlagReport:
        """Scan for all feature flags and return a consolidated report."""
        logger.info("Scanning for feature flags in %s", self.cwd)
        report = FlagReport()

        # Collect from various sources
        flags: list[FeatureFlag] = []
        flags.extend(self._scan_env_flags())
        flags.extend(self._scan_java_flags())
        flags.extend(self._scan_config_flags())
        flags.extend(self._scan_code_flags())

        # Deduplicate by name (merge references)
        seen: dict[str, FeatureFlag] = {}
        for flag in flags:
            if flag.name not in seen:
                seen[flag.name] = flag
            else:
                seen[flag.name].references.extend(flag.references)
                # Merge env_values
                seen[flag.name].env_values.update(flag.env_values)

        report.flags = list(seen.values())
        report.total_flags = len(report.flags)

        # Find cross-file references
        self._find_references(report.flags)

        # Detect stale flags
        self._detect_stale(report)

        # Build env matrix
        for flag in report.flags:
            if flag.env_values:
                report.env_matrix[flag.name] = flag.env_values

        logger.info("Found %d flags (%d stale)", report.total_flags, len(report.stale_flags))
        return report

    # ------------------------------------------------------------------
    # File helpers
    # ------------------------------------------------------------------

    def _get_files(self, extensions: list[str]) -> list[str]:
        """Walk cwd and collect files matching any of the given extensions."""
        files = []
        for root, dirs, filenames in os.walk(self.cwd):
            dirs[:] = [d for d in dirs if d not in self.exclude_dirs]
            for f in filenames:
                if any(f.endswith(ext) for ext in extensions):
                    files.append(os.path.join(root, f))
        return files

    def _is_flag_name(self, name: str) -> bool:
        """Return True if name matches common feature-flag naming patterns."""
        upper = name.upper()
        return any(p in upper for p in self._FLAG_PATTERNS)

    # ------------------------------------------------------------------
    # Source scanners
    # ------------------------------------------------------------------

    def _scan_env_flags(self) -> list[FeatureFlag]:
        """Scan .env* files for feature-flag variables."""
        flags: list[FeatureFlag] = []
        env_files: list[str] = []

        for root, dirs, filenames in os.walk(self.cwd):
            dirs[:] = [d for d in dirs if d not in self.exclude_dirs]
            for f in filenames:
                if f.startswith(".env"):
                    env_files.append(os.path.join(root, f))

        flag_names: dict[str, FeatureFlag] = {}

        for filepath in env_files:
            try:
                rel = os.path.relpath(filepath, self.cwd)
                env_name = Path(filepath).name.replace(".env.", "").replace(".env", "default")

                with open(filepath) as fh:
                    for i, line in enumerate(fh, 1):
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip().strip("'\"")

                        if self._is_flag_name(key):
                            if key not in flag_names:
                                flag_names[key] = FeatureFlag(
                                    name=key, file=rel, line=i,
                                    flag_type="boolean" if val.lower() in ("true", "false", "0", "1") else "string",
                                    default_value=val,
                                )
                            flag_names[key].env_values[env_name] = val
            except Exception:
                logger.debug("Could not read %s", filepath, exc_info=True)

        return list(flag_names.values())

    def _scan_java_flags(self) -> list[FeatureFlag]:
        """Scan Java @Value / @ConditionalOnProperty annotations."""
        flags: list[FeatureFlag] = []
        for filepath in self._get_files([".java"]):
            try:
                with open(filepath) as fh:
                    content = fh.read()
                rel = os.path.relpath(filepath, self.cwd)

                # @Value("${feature.enabled:false}")
                for match in re.finditer(r'@Value\s*\(\s*"\$\{([^}]+)\}"\s*\)', content):
                    prop = match.group(1)
                    if any(kw in prop.lower() for kw in ["feature", "enable", "toggle", "flag", "active"]):
                        name = prop.split(":")[0]
                        default = prop.split(":")[-1] if ":" in prop else ""
                        line_num = content[:match.start()].count("\n") + 1
                        flags.append(FeatureFlag(
                            name=name, file=rel, line=line_num,
                            flag_type="boolean" if default.lower() in ("true", "false") else "string",
                            default_value=default,
                        ))

                # @ConditionalOnProperty
                for match in re.finditer(
                    r'@ConditionalOnProperty\s*\([^)]*name\s*=\s*"([^"]+)"', content
                ):
                    name = match.group(1)
                    line_num = content[:match.start()].count("\n") + 1
                    flags.append(FeatureFlag(name=name, file=rel, line=line_num, flag_type="boolean"))
            except Exception:
                logger.debug("Could not scan Java file %s", filepath, exc_info=True)

        return flags

    def _scan_config_flags(self) -> list[FeatureFlag]:
        """Scan YAML / properties files for feature flag keys."""
        flags: list[FeatureFlag] = []
        for filepath in self._get_files([".yml", ".yaml", ".properties"]):
            try:
                with open(filepath) as fh:
                    content = fh.read()
                rel = os.path.relpath(filepath, self.cwd)

                for i, line in enumerate(content.split("\n"), 1):
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#"):
                        continue
                    if any(kw in stripped.lower() for kw in ["feature", "enable", "toggle", "flag"]):
                        if "=" in stripped or ":" in stripped:
                            sep = "=" if "=" in stripped else ":"
                            key = stripped.split(sep)[0].strip()
                            val = stripped.split(sep, 1)[1].strip() if sep in stripped else ""
                            if key and not key.startswith("#"):
                                flags.append(FeatureFlag(
                                    name=key, file=rel, line=i,
                                    default_value=val,
                                    flag_type="boolean" if val.strip().lower() in ("true", "false") else "string",
                                ))
            except Exception:
                logger.debug("Could not scan config %s", filepath, exc_info=True)

        return flags

    def _scan_code_flags(self) -> list[FeatureFlag]:
        """Scan Python / JS / TS for os.getenv / process.env feature-flag lookups."""
        flags: list[FeatureFlag] = []
        for filepath in self._get_files([".py", ".js", ".ts"]):
            try:
                with open(filepath) as fh:
                    content = fh.read()
                rel = os.path.relpath(filepath, self.cwd)

                for match in re.finditer(
                    r'(?:os\.getenv|os\.environ\.get|os\.environ\[|process\.env\.?)'
                    r'[\s\(\["\']*(FEATURE_\w+|ENABLE_\w+|FF_\w+)',
                    content,
                ):
                    name = match.group(1)
                    line_num = content[:match.start()].count("\n") + 1
                    flags.append(FeatureFlag(name=name, file=rel, line=line_num))
            except Exception:
                logger.debug("Could not scan code file %s", filepath, exc_info=True)

        return flags

    # ------------------------------------------------------------------
    # Cross-reference and staleness
    # ------------------------------------------------------------------

    def _find_references(self, flags: list[FeatureFlag]):
        """Use grep to find all files referencing each flag name."""
        for flag in flags:
            try:
                result = subprocess.run(
                    [
                        "grep", "-rl", flag.name,
                        "--include=*.py", "--include=*.java",
                        "--include=*.js", "--include=*.ts",
                        "--include=*.yml", "--include=*.yaml",
                        "--include=*.properties", ".",
                    ],
                    capture_output=True, text=True, timeout=10, cwd=self.cwd,
                )
                if result.returncode == 0:
                    refs = [
                        f.strip().lstrip("./")
                        for f in result.stdout.strip().split("\n")
                        if f.strip()
                    ]
                    flag.references = [{"file": r} for r in refs if r != flag.file]
            except Exception:
                logger.debug("grep failed for %s", flag.name, exc_info=True)

    def _detect_stale(self, report: FlagReport):
        """Flag is stale if defined in config but not referenced in any code file."""
        code_extensions = {
            ".py", ".java", ".js", ".ts", ".jsx", ".tsx", ".kt", ".scala", ".go",
        }
        for flag in report.flags:
            code_refs = [
                r for r in flag.references
                if Path(r.get("file", "")).suffix in code_extensions
            ]
            config_suffixes = (".env", ".yml", ".yaml", ".properties")
            if not code_refs and any(flag.file.endswith(s) for s in config_suffixes):
                flag.stale = True
                report.stale_flags.append(flag)


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_flag_report(report: FlagReport) -> str:
    """Format flag report for terminal display."""
    lines: list[str] = []
    lines.append(f"  Feature Flags ({report.total_flags} found)")
    lines.append(f"  {'=' * 50}")

    # Active (non-stale) flags
    active = [f for f in report.flags if not f.stale]
    if active:
        lines.append("")
        lines.append("  Active Flags:")
        for flag in active:
            refs = len(flag.references)
            envs = ", ".join(f"{k}={v}" for k, v in flag.env_values.items()) if flag.env_values else ""
            lines.append(f"    * {flag.name}")
            lines.append(f"      File: {flag.file}:{flag.line} | Refs: {refs} | Default: {flag.default_value}")
            if envs:
                lines.append(f"      Envs: {envs}")

    # Stale flags
    if report.stale_flags:
        lines.append("")
        lines.append(f"  Stale Flags ({len(report.stale_flags)}) — defined but not referenced in code:")
        for flag in report.stale_flags:
            lines.append(f"    x {flag.name} ({flag.file}:{flag.line})")

    # Env matrix
    if report.env_matrix:
        lines.append("")
        lines.append("  Environment Matrix:")
        envs_set: set[str] = set()
        for vals in report.env_matrix.values():
            envs_set.update(vals.keys())
        env_list = sorted(envs_set)

        header = f"    {'Flag':<35} " + " ".join(f"{e:>10}" for e in env_list)
        lines.append(header)
        lines.append(f"    {'-' * len(header)}")

        for flag_name, vals in report.env_matrix.items():
            row = f"    {flag_name:<35} "
            for env in env_list:
                val = vals.get(env, "-")
                row += f" {val:>10}"
            lines.append(row)

    return "\n".join(lines)
