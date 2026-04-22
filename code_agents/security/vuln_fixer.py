"""Vulnerability Fixer — parse CVE alerts, find affected code, suggest fixes.

Reads CVE advisories (from JSON or structured text), correlates them with
installed dependencies, locates usage in the codebase, and generates
prioritised fix suggestions including dependency upgrade commands.

Usage:
    from code_agents.security.vuln_fixer import VulnFixer, VulnFixerConfig
    fixer = VulnFixer(VulnFixerConfig(cwd="/path/to/repo"))
    result = fixer.analyze()
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.security.vuln_fixer")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

CVE_PATTERN = re.compile(r"CVE-\d{4}-\d{4,}")


@dataclass
class VulnFixerConfig:
    cwd: str = "."
    max_files: int = 500
    severity_threshold: str = "medium"  # low | medium | high | critical
    include_transitive: bool = True


@dataclass
class CVEAlert:
    """A single CVE advisory."""
    cve_id: str
    package: str
    affected_versions: str = ""
    fixed_version: str = ""
    severity: str = "medium"
    description: str = ""
    cwe: str = ""


@dataclass
class AffectedLocation:
    """A code location that imports / uses the vulnerable package."""
    file: str
    line: int
    code: str = ""
    usage_type: str = ""  # "import", "call", "config"


@dataclass
class FixSuggestion:
    """Suggested fix for a CVE."""
    cve_id: str
    package: str
    current_version: str = ""
    target_version: str = ""
    upgrade_command: str = ""
    code_changes: list[str] = field(default_factory=list)
    breaking_risk: str = "low"  # low | medium | high


@dataclass
class VulnFixerReport:
    """Full vulnerability analysis result."""
    cves_parsed: int = 0
    affected_packages: int = 0
    locations_found: int = 0
    alerts: list[CVEAlert] = field(default_factory=list)
    locations: list[AffectedLocation] = field(default_factory=list)
    suggestions: list[FixSuggestion] = field(default_factory=list)
    summary: str = ""


# ---------------------------------------------------------------------------
# Severity ordering
# ---------------------------------------------------------------------------

SEVERITY_ORDER = {"critical": 4, "high": 3, "medium": 2, "low": 1}

# ---------------------------------------------------------------------------
# Dependency file parsers
# ---------------------------------------------------------------------------

REQUIREMENTS_RE = re.compile(r"^([A-Za-z0-9_-]+)\s*([=<>!~]+.+)?$")
PACKAGE_JSON_DEP_RE = re.compile(r'"([^"]+)":\s*"([^"]*)"')


def _parse_requirements(path: Path) -> dict[str, str]:
    """Parse requirements.txt into {package: version}."""
    deps: dict[str, str] = {}
    if not path.exists():
        return deps
    for raw_line in path.read_text(errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        m = REQUIREMENTS_RE.match(line)
        if m:
            deps[m.group(1).lower()] = (m.group(2) or "").strip()
    return deps


def _parse_package_json(path: Path) -> dict[str, str]:
    """Parse package.json dependencies."""
    deps: dict[str, str] = {}
    if not path.exists():
        return deps
    try:
        import json as _json
        data = _json.loads(path.read_text(errors="replace"))
        for section in ("dependencies", "devDependencies"):
            for pkg, ver in data.get(section, {}).items():
                deps[pkg.lower()] = ver
    except Exception:
        logger.debug("Failed to parse %s", path)
    return deps


def _parse_pyproject(path: Path) -> dict[str, str]:
    """Parse pyproject.toml [tool.poetry.dependencies]."""
    deps: dict[str, str] = {}
    if not path.exists():
        return deps
    try:
        content = path.read_text(errors="replace")
        in_deps = False
        for line in content.splitlines():
            if "[tool.poetry.dependencies]" in line:
                in_deps = True
                continue
            if in_deps:
                if line.startswith("["):
                    break
                m = re.match(r'^(\w[\w-]*)\s*=\s*["\']?([^"\']+)', line)
                if m:
                    deps[m.group(1).lower()] = m.group(2).strip()
    except Exception:
        logger.debug("Failed to parse %s", path)
    return deps


# ---------------------------------------------------------------------------
# VulnFixer
# ---------------------------------------------------------------------------


class VulnFixer:
    """Parse CVE alerts, find affected code, and suggest fixes."""

    def __init__(self, config: Optional[VulnFixerConfig] = None):
        self.config = config or VulnFixerConfig()
        self._deps: dict[str, str] = {}

    # -- public API ---------------------------------------------------------

    def analyze(
        self,
        alerts: Optional[list[CVEAlert]] = None,
        advisory_text: str = "",
    ) -> VulnFixerReport:
        """Run full vulnerability analysis.

        Args:
            alerts: Pre-parsed CVE alerts.
            advisory_text: Raw text containing CVE references.
        """
        logger.info("Starting vulnerability analysis in %s", self.config.cwd)
        report = VulnFixerReport()

        # Step 1 — gather alerts
        cve_alerts = list(alerts or [])
        if advisory_text:
            cve_alerts.extend(self._parse_advisory_text(advisory_text))
        report.alerts = cve_alerts
        report.cves_parsed = len(cve_alerts)
        logger.info("Parsed %d CVE alerts", report.cves_parsed)

        if not cve_alerts:
            report.summary = "No CVE alerts to process."
            return report

        # Step 2 — load project dependencies
        self._deps = self._load_dependencies()

        # Step 3 — find affected locations for each alert
        affected_pkgs: set[str] = set()
        threshold = SEVERITY_ORDER.get(self.config.severity_threshold, 2)
        for alert in cve_alerts:
            sev = SEVERITY_ORDER.get(alert.severity, 2)
            if sev < threshold:
                continue
            locs = self._find_usage(alert.package)
            report.locations.extend(locs)
            if locs or alert.package.lower() in self._deps:
                affected_pkgs.add(alert.package)
                report.suggestions.append(self._build_suggestion(alert))

        report.affected_packages = len(affected_pkgs)
        report.locations_found = len(report.locations)

        # Step 4 — sort suggestions by severity
        report.suggestions.sort(
            key=lambda s: SEVERITY_ORDER.get(
                next((a.severity for a in cve_alerts if a.cve_id == s.cve_id), "low"), 1
            ),
            reverse=True,
        )

        report.summary = (
            f"{report.cves_parsed} CVEs analysed, {report.affected_packages} affected "
            f"packages, {report.locations_found} code locations, "
            f"{len(report.suggestions)} fix suggestions."
        )
        logger.info("Vulnerability analysis complete: %s", report.summary)
        return report

    # -- internal helpers ---------------------------------------------------

    def _parse_advisory_text(self, text: str) -> list[CVEAlert]:
        """Extract CVE IDs from free-text advisories."""
        alerts: list[CVEAlert] = []
        seen: set[str] = set()
        for m in CVE_PATTERN.finditer(text):
            cve_id = m.group(0)
            if cve_id not in seen:
                seen.add(cve_id)
                alerts.append(CVEAlert(cve_id=cve_id, package="unknown"))
        return alerts

    def _load_dependencies(self) -> dict[str, str]:
        """Load dependencies from project files."""
        root = Path(self.config.cwd)
        deps: dict[str, str] = {}
        deps.update(_parse_requirements(root / "requirements.txt"))
        deps.update(_parse_package_json(root / "package.json"))
        deps.update(_parse_pyproject(root / "pyproject.toml"))
        logger.debug("Loaded %d dependencies", len(deps))
        return deps

    def _find_usage(self, package: str) -> list[AffectedLocation]:
        """Scan source files for imports/usage of the given package."""
        root = Path(self.config.cwd)
        locations: list[AffectedLocation] = []
        pkg_lower = package.lower().replace("-", "_")
        import_re = re.compile(
            rf"(?:import\s+{re.escape(pkg_lower)}|from\s+{re.escape(pkg_lower)}\s+import|"
            rf"require\(['\"]({re.escape(package)})['\"])",
            re.IGNORECASE,
        )
        count = 0
        for ext in ("*.py", "*.js", "*.ts", "*.java"):
            for fpath in root.rglob(ext):
                if count >= self.config.max_files:
                    break
                count += 1
                rel = str(fpath.relative_to(root))
                if any(part.startswith(".") or part == "node_modules" for part in fpath.parts):
                    continue
                try:
                    lines = fpath.read_text(errors="replace").splitlines()
                except Exception:
                    continue
                for idx, line in enumerate(lines, 1):
                    if import_re.search(line):
                        locations.append(AffectedLocation(
                            file=rel, line=idx, code=line.strip(), usage_type="import",
                        ))
        return locations

    def _build_suggestion(self, alert: CVEAlert) -> FixSuggestion:
        """Build a fix suggestion for a CVE alert."""
        current = self._deps.get(alert.package.lower(), "unknown")
        target = alert.fixed_version or "latest"
        pkg = alert.package

        # Determine upgrade command based on project type
        root = Path(self.config.cwd)
        if (root / "pyproject.toml").exists():
            cmd = f"poetry add {pkg}@{target}"
        elif (root / "requirements.txt").exists():
            cmd = f"pip install {pkg}>={target}"
        elif (root / "package.json").exists():
            cmd = f"npm install {pkg}@{target}"
        else:
            cmd = f"# upgrade {pkg} to {target}"

        changes: list[str] = []
        if alert.cwe:
            changes.append(f"Address {alert.cwe}: review usages for safe alternatives")
        if current != "unknown" and target != "latest":
            changes.append(f"Bump {pkg} from {current} to {target}")

        return FixSuggestion(
            cve_id=alert.cve_id,
            package=pkg,
            current_version=current,
            target_version=target,
            upgrade_command=cmd,
            code_changes=changes,
            breaking_risk="medium" if target == "latest" else "low",
        )


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def format_vuln_report(report: VulnFixerReport) -> str:
    """Render a human-readable vulnerability report."""
    lines = ["=== Vulnerability Fixer Report ===", ""]
    if not report.alerts:
        lines.append("No CVE alerts found.")
        return "\n".join(lines)

    lines.append(f"CVEs analysed:       {report.cves_parsed}")
    lines.append(f"Affected packages:   {report.affected_packages}")
    lines.append(f"Code locations:      {report.locations_found}")
    lines.append(f"Fix suggestions:     {len(report.suggestions)}")
    lines.append("")

    for sug in report.suggestions:
        lines.append(f"  [{sug.cve_id}] {sug.package}")
        lines.append(f"    Current: {sug.current_version}  ->  Target: {sug.target_version}")
        lines.append(f"    Command: {sug.upgrade_command}")
        lines.append(f"    Breaking risk: {sug.breaking_risk}")
        for ch in sug.code_changes:
            lines.append(f"    - {ch}")
        lines.append("")

    lines.append(report.summary)
    return "\n".join(lines)
