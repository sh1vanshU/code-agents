"""Breaking Change Precog — monitor upstream deps for breaking changes before release."""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.domain.breaking_change_precog")


@dataclass
class Dependency:
    """An upstream dependency being monitored."""
    name: str = ""
    current_version: str = ""
    latest_version: str = ""
    repo_url: str = ""
    pinned: bool = False


@dataclass
class BreakingChange:
    """A detected or predicted breaking change."""
    dependency: str = ""
    version: str = ""
    change_type: str = ""  # api_removal, signature_change, behavior_change, deprecation
    description: str = ""
    impact_level: str = "medium"  # low, medium, high, critical
    affected_files: list[str] = field(default_factory=list)
    migration_steps: list[str] = field(default_factory=list)
    confidence: float = 0.0


@dataclass
class PrecogReport:
    """Complete breaking change prediction report."""
    dependencies_checked: int = 0
    breaking_changes: list[BreakingChange] = field(default_factory=list)
    deprecation_warnings: list[str] = field(default_factory=list)
    safe_updates: list[str] = field(default_factory=list)
    risk_score: float = 0.0  # 0-100
    recommendations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


SEMVER_PATTERN = re.compile(r"(\d+)\.(\d+)\.(\d+)")

BREAKING_INDICATORS = [
    re.compile(r"\bBREAKING\s*CHANGE\b", re.IGNORECASE),
    re.compile(r"\bremoved?\b.*\bAPI\b", re.IGNORECASE),
    re.compile(r"\bdeprecated?\b", re.IGNORECASE),
    re.compile(r"\brename[sd]?\b.*\bfunction\b", re.IGNORECASE),
    re.compile(r"\bchanged?\b.*\bsignature\b", re.IGNORECASE),
    re.compile(r"\bincompatible\b", re.IGNORECASE),
]

DEPRECATION_INDICATORS = [
    re.compile(r"\bdeprecated?\b", re.IGNORECASE),
    re.compile(r"\bwill\s+be\s+removed\b", re.IGNORECASE),
    re.compile(r"\buse\s+\w+\s+instead\b", re.IGNORECASE),
]


class BreakingChangePrecog:
    """Monitors upstream dependencies for breaking changes."""

    def __init__(self, cwd: str):
        self.cwd = cwd

    def analyze(self, dependencies: list[dict],
                changelogs: Optional[dict[str, str]] = None,
                usage_map: Optional[dict[str, list[str]]] = None) -> PrecogReport:
        """Analyze dependencies for breaking changes."""
        logger.info("Checking %d dependencies for breaking changes", len(dependencies))
        changelogs = changelogs or {}
        usage_map = usage_map or {}

        deps = [self._parse_dep(d) for d in dependencies]
        breaking = []
        deprecations = []
        safe = []

        for dep in deps:
            # Check version bump type
            bump = self._version_bump_type(dep.current_version, dep.latest_version)

            # Check changelog for breaking indicators
            changelog = changelogs.get(dep.name, "")
            changes = self._analyze_changelog(dep, changelog, usage_map.get(dep.name, []))

            if changes:
                breaking.extend(changes)
            elif bump == "major":
                breaking.append(BreakingChange(
                    dependency=dep.name,
                    version=dep.latest_version,
                    change_type="behavior_change",
                    description=f"Major version bump {dep.current_version} -> {dep.latest_version}",
                    impact_level="high",
                    confidence=0.6,
                ))
            elif bump == "minor":
                # Check for deprecations
                dep_warnings = self._check_deprecations(changelog)
                deprecations.extend(dep_warnings)
                safe.append(f"{dep.name}: {dep.current_version} -> {dep.latest_version} (minor)")
            else:
                safe.append(f"{dep.name}: up to date")

        risk = self._compute_risk(breaking, deps)

        report = PrecogReport(
            dependencies_checked=len(deps),
            breaking_changes=sorted(breaking, key=lambda b: -b.confidence),
            deprecation_warnings=deprecations,
            safe_updates=safe,
            risk_score=round(risk, 1),
            recommendations=self._generate_recommendations(breaking, deprecations),
            warnings=self._generate_warnings(breaking),
        )
        logger.info("Precog: %d breaking, %d deprecations, risk=%.0f",
                     len(breaking), len(deprecations), risk)
        return report

    def _parse_dep(self, raw: dict) -> Dependency:
        return Dependency(
            name=raw.get("name", ""),
            current_version=raw.get("current", raw.get("current_version", "")),
            latest_version=raw.get("latest", raw.get("latest_version", "")),
            repo_url=raw.get("url", raw.get("repo_url", "")),
            pinned=raw.get("pinned", False),
        )

    def _version_bump_type(self, current: str, latest: str) -> str:
        """Determine version bump type."""
        c = SEMVER_PATTERN.search(current)
        l = SEMVER_PATTERN.search(latest)
        if not c or not l:
            return "unknown"
        cmaj, cmin, cpatch = int(c.group(1)), int(c.group(2)), int(c.group(3))
        lmaj, lmin, lpatch = int(l.group(1)), int(l.group(2)), int(l.group(3))
        if lmaj > cmaj:
            return "major"
        if lmin > cmin:
            return "minor"
        if lpatch > cpatch:
            return "patch"
        return "none"

    def _analyze_changelog(self, dep: Dependency, changelog: str,
                           used_apis: list[str]) -> list[BreakingChange]:
        """Analyze changelog for breaking changes affecting us."""
        changes = []
        if not changelog:
            return changes

        for indicator in BREAKING_INDICATORS:
            for m in indicator.finditer(changelog):
                context = changelog[max(0, m.start() - 50):m.end() + 100].strip()
                # Check if any used APIs are mentioned
                affected = [api for api in used_apis if api.lower() in context.lower()]
                if affected or not used_apis:
                    changes.append(BreakingChange(
                        dependency=dep.name,
                        version=dep.latest_version,
                        change_type=self._classify_change(context),
                        description=context[:120],
                        impact_level="high" if affected else "medium",
                        affected_files=[],
                        confidence=0.8 if affected else 0.5,
                    ))
        return changes

    def _classify_change(self, context: str) -> str:
        ctx_lower = context.lower()
        if "remove" in ctx_lower:
            return "api_removal"
        if "signature" in ctx_lower or "parameter" in ctx_lower:
            return "signature_change"
        if "deprecat" in ctx_lower:
            return "deprecation"
        return "behavior_change"

    def _check_deprecations(self, changelog: str) -> list[str]:
        warnings = []
        for pattern in DEPRECATION_INDICATORS:
            for m in pattern.finditer(changelog):
                context = changelog[max(0, m.start() - 20):m.end() + 60].strip()
                warnings.append(context[:100])
        return warnings

    def _compute_risk(self, breaking: list[BreakingChange], deps: list[Dependency]) -> float:
        if not deps:
            return 0
        score = 0.0
        for bc in breaking:
            if bc.impact_level == "critical":
                score += 25
            elif bc.impact_level == "high":
                score += 15
            elif bc.impact_level == "medium":
                score += 8
            else:
                score += 3
        return min(100, score)

    def _generate_recommendations(self, breaking: list[BreakingChange],
                                  deprecations: list[str]) -> list[str]:
        recs = []
        if breaking:
            recs.append(f"Address {len(breaking)} breaking changes before upgrading")
        if deprecations:
            recs.append(f"Plan migration for {len(deprecations)} deprecation warnings")
        if not breaking and not deprecations:
            recs.append("All clear — safe to update dependencies")
        return recs

    def _generate_warnings(self, breaking: list[BreakingChange]) -> list[str]:
        warnings = []
        critical = [b for b in breaking if b.impact_level == "critical"]
        if critical:
            warnings.append(f"{len(critical)} critical breaking changes — do not upgrade without migration plan")
        return warnings


def format_report(report: PrecogReport) -> str:
    lines = [
        "# Breaking Change Precog",
        f"Deps: {report.dependencies_checked} | Breaking: {len(report.breaking_changes)} | Risk: {report.risk_score:.0f}",
        "",
    ]
    for bc in report.breaking_changes:
        lines.append(f"  [{bc.impact_level}] {bc.dependency} {bc.version}: {bc.description[:80]}")
    return "\n".join(lines)
