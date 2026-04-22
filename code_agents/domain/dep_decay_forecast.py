"""Dependency decay forecast — predict dependency risk, CVE likelihood, alternatives.

Analyzes project dependencies for staleness, maintenance health, known
vulnerabilities, and suggests safer alternatives when risk is high.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("code_agents.domain.dep_decay_forecast")

# Risk weight factors
STALENESS_WEIGHT = 0.3
MAINTENANCE_WEIGHT = 0.25
CVE_WEIGHT = 0.3
POPULARITY_WEIGHT = 0.15


@dataclass
class DependencyRisk:
    """Risk assessment for a single dependency."""

    name: str = ""
    current_version: str = ""
    latest_version: str = ""
    staleness_days: int = 0
    maintenance_score: float = 0.0  # 0-1, higher = healthier
    cve_count: int = 0
    cve_severity_max: str = "none"  # none | low | medium | high | critical
    risk_score: float = 0.0  # 0-100, higher = riskier
    risk_level: str = "low"  # low | medium | high | critical
    alternatives: list[str] = field(default_factory=list)
    recommendation: str = ""


@dataclass
class DecayForecast:
    """Predicted decay trajectory for a dependency."""

    name: str = ""
    months_to_critical: int = 0
    decay_rate: float = 0.0  # score increase per month
    predicted_risk_6mo: float = 0.0
    predicted_risk_12mo: float = 0.0


@dataclass
class DepDecayResult:
    """Result of dependency decay analysis."""

    dependencies_analyzed: int = 0
    risks: list[DependencyRisk] = field(default_factory=list)
    forecasts: list[DecayForecast] = field(default_factory=list)
    overall_health: float = 0.0  # 0-100
    critical_count: int = 0
    high_count: int = 0
    summary: dict[str, int] = field(default_factory=dict)


class DepDecayForecaster:
    """Forecast dependency decay and risk."""

    def __init__(self, cwd: str):
        self.cwd = cwd
        logger.debug("DepDecayForecaster initialized for %s", cwd)

    def analyze(
        self,
        dep_file: str | None = None,
        include_dev: bool = False,
    ) -> DepDecayResult:
        """Analyze dependency decay and forecast risk.

        Args:
            dep_file: Path to dependency file. Auto-detected if None.
            include_dev: Include dev dependencies.

        Returns:
            DepDecayResult with risks and forecasts.
        """
        result = DepDecayResult()

        # Find and parse dependency file
        if dep_file is None:
            dep_file = self._auto_detect_dep_file()
        if dep_file is None:
            logger.warning("No dependency file found in %s", self.cwd)
            return result

        logger.info("Analyzing dependencies from %s", dep_file)
        deps = self._parse_dependencies(dep_file, include_dev)
        result.dependencies_analyzed = len(deps)

        # Assess each dependency
        for name, version in deps.items():
            risk = self._assess_risk(name, version)
            result.risks.append(risk)

            # Forecast decay
            forecast = self._forecast_decay(risk)
            result.forecasts.append(forecast)

        # Calculate overall health
        if result.risks:
            avg_risk = sum(r.risk_score for r in result.risks) / len(result.risks)
            result.overall_health = round(max(0, 100 - avg_risk), 1)
        else:
            result.overall_health = 100.0

        result.critical_count = sum(1 for r in result.risks if r.risk_level == "critical")
        result.high_count = sum(1 for r in result.risks if r.risk_level == "high")

        result.summary = {
            "dependencies_analyzed": result.dependencies_analyzed,
            "critical": result.critical_count,
            "high": result.high_count,
            "medium": sum(1 for r in result.risks if r.risk_level == "medium"),
            "low": sum(1 for r in result.risks if r.risk_level == "low"),
            "overall_health": result.overall_health,
        }
        logger.info(
            "Decay analysis: %d deps, health=%.1f, %d critical",
            len(deps), result.overall_health, result.critical_count,
        )
        return result

    def _auto_detect_dep_file(self) -> str | None:
        """Auto-detect dependency file."""
        candidates = [
            "pyproject.toml", "requirements.txt", "requirements.in",
            "Pipfile", "setup.py", "setup.cfg",
            "package.json", "package-lock.json",
            "Cargo.toml", "go.mod", "pom.xml",
            "Gemfile", "composer.json",
        ]
        for name in candidates:
            path = os.path.join(self.cwd, name)
            if os.path.isfile(path):
                return path
        return None

    def _parse_dependencies(
        self, dep_file: str, include_dev: bool,
    ) -> dict[str, str]:
        """Parse dependencies from a dependency file."""
        fpath = Path(dep_file)
        deps: dict[str, str] = {}

        try:
            content = fpath.read_text(errors="replace")
        except OSError:
            return deps

        fname = fpath.name

        if fname == "pyproject.toml":
            deps.update(self._parse_pyproject(content, include_dev))
        elif fname in ("requirements.txt", "requirements.in"):
            deps.update(self._parse_requirements(content))
        elif fname == "package.json":
            deps.update(self._parse_package_json(content, include_dev))
        elif fname == "go.mod":
            deps.update(self._parse_go_mod(content))

        return deps

    def _parse_pyproject(self, content: str, include_dev: bool) -> dict[str, str]:
        """Parse pyproject.toml dependencies."""
        deps: dict[str, str] = {}
        in_deps = False
        in_dev_deps = False

        for line in content.splitlines():
            stripped = line.strip()
            if stripped == "[tool.poetry.dependencies]":
                in_deps = True
                in_dev_deps = False
                continue
            elif stripped == "[tool.poetry.group.dev.dependencies]":
                in_deps = False
                in_dev_deps = True
                continue
            elif stripped.startswith("["):
                in_deps = False
                in_dev_deps = False
                continue

            if in_deps or (in_dev_deps and include_dev):
                match = re.match(r'(\S+)\s*=\s*["\']?([^"\']+)', stripped)
                if match and match.group(1) != "python":
                    deps[match.group(1)] = match.group(2).strip('"\'{}')

        return deps

    def _parse_requirements(self, content: str) -> dict[str, str]:
        """Parse requirements.txt."""
        deps: dict[str, str] = {}
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            match = re.match(r"([a-zA-Z0-9_.-]+)\s*([><=!~]+\s*[\d.]+)?", line)
            if match:
                deps[match.group(1)] = (match.group(2) or "").strip()
        return deps

    def _parse_package_json(self, content: str, include_dev: bool) -> dict[str, str]:
        """Parse package.json dependencies."""
        deps: dict[str, str] = {}
        try:
            import json  # lazy import
            data = json.loads(content)
            for name, version in data.get("dependencies", {}).items():
                deps[name] = version
            if include_dev:
                for name, version in data.get("devDependencies", {}).items():
                    deps[name] = version
        except (ImportError, ValueError):
            pass
        return deps

    def _parse_go_mod(self, content: str) -> dict[str, str]:
        """Parse go.mod dependencies."""
        deps: dict[str, str] = {}
        for match in re.finditer(r"^\s+(\S+)\s+(v[\d.]+)", content, re.MULTILINE):
            deps[match.group(1)] = match.group(2)
        return deps

    def _assess_risk(self, name: str, version: str) -> DependencyRisk:
        """Assess risk for a single dependency."""
        risk = DependencyRisk(name=name, current_version=version)

        # Heuristic-based risk assessment (no network calls)
        # Staleness heuristic from version pattern
        risk.staleness_days = self._estimate_staleness(version)

        # Maintenance score heuristic
        risk.maintenance_score = self._estimate_maintenance(name)

        # CVE heuristic based on known risky packages
        risk.cve_count, risk.cve_severity_max = self._estimate_cve_risk(name, version)

        # Calculate composite risk score
        staleness_risk = min(100, risk.staleness_days / 10)
        maintenance_risk = (1 - risk.maintenance_score) * 100
        cve_risk = min(100, risk.cve_count * 30)

        risk.risk_score = round(
            staleness_risk * STALENESS_WEIGHT
            + maintenance_risk * MAINTENANCE_WEIGHT
            + cve_risk * CVE_WEIGHT
            + (100 - risk.maintenance_score * 100) * POPULARITY_WEIGHT,
            1,
        )

        # Classify risk level
        if risk.risk_score >= 70 or risk.cve_severity_max == "critical":
            risk.risk_level = "critical"
        elif risk.risk_score >= 50 or risk.cve_severity_max == "high":
            risk.risk_level = "high"
        elif risk.risk_score >= 30:
            risk.risk_level = "medium"
        else:
            risk.risk_level = "low"

        # Suggest alternatives for high-risk deps
        risk.alternatives = self._suggest_alternatives(name)
        risk.recommendation = self._make_recommendation(risk)

        return risk

    def _estimate_staleness(self, version: str) -> int:
        """Estimate staleness in days from version pattern."""
        # Rough heuristic: older minor versions = more stale
        match = re.search(r"(\d+)\.(\d+)", version)
        if match:
            major, minor = int(match.group(1)), int(match.group(2))
            if major == 0:
                return 180  # Pre-1.0 often stale
            return max(0, (10 - minor) * 30)  # Rough estimate
        return 90  # Default

    def _estimate_maintenance(self, name: str) -> float:
        """Estimate maintenance health from package name heuristics."""
        well_maintained = {
            "fastapi", "pydantic", "sqlalchemy", "requests", "flask",
            "django", "pytest", "numpy", "pandas", "react", "express",
            "typescript", "eslint", "prettier",
        }
        if name.lower() in well_maintained:
            return 0.9
        # Packages with common prefixes tend to be maintained
        if any(name.lower().startswith(p) for p in ("python-", "py", "django-", "flask-")):
            return 0.6
        return 0.5

    def _estimate_cve_risk(self, name: str, version: str) -> tuple[int, str]:
        """Estimate CVE risk (heuristic, no network)."""
        # Known historically vulnerable packages
        risky = {
            "urllib3": (2, "high"),
            "pillow": (3, "high"),
            "django": (1, "medium"),
            "flask": (1, "low"),
            "requests": (1, "medium"),
            "lodash": (2, "high"),
            "express": (1, "medium"),
        }
        name_lower = name.lower()
        if name_lower in risky:
            return risky[name_lower]
        return 0, "none"

    def _suggest_alternatives(self, name: str) -> list[str]:
        """Suggest alternative packages."""
        alternatives = {
            "requests": ["httpx", "aiohttp"],
            "urllib3": ["httpx"],
            "flask": ["fastapi", "starlette"],
            "moment": ["dayjs", "date-fns"],
            "lodash": ["ramda", "native ES6"],
            "express": ["fastify", "koa"],
        }
        return alternatives.get(name.lower(), [])

    def _make_recommendation(self, risk: DependencyRisk) -> str:
        """Generate recommendation for a dependency."""
        if risk.risk_level == "critical":
            if risk.alternatives:
                return f"Migrate to {risk.alternatives[0]} or upgrade immediately"
            return "Upgrade immediately — critical risk"
        if risk.risk_level == "high":
            return "Schedule upgrade within next sprint"
        if risk.risk_level == "medium":
            return "Monitor and plan upgrade"
        return "No action needed"

    def _forecast_decay(self, risk: DependencyRisk) -> DecayForecast:
        """Forecast risk trajectory."""
        # Estimated monthly risk increase
        decay_rate = 2.0  # base
        if risk.maintenance_score < 0.5:
            decay_rate += 3.0
        if risk.cve_count > 0:
            decay_rate += 2.0

        current = risk.risk_score
        months_to_critical = max(1, int((70 - current) / decay_rate)) if current < 70 else 0

        return DecayForecast(
            name=risk.name,
            months_to_critical=months_to_critical,
            decay_rate=round(decay_rate, 1),
            predicted_risk_6mo=round(min(100, current + decay_rate * 6), 1),
            predicted_risk_12mo=round(min(100, current + decay_rate * 12), 1),
        )


def forecast_dep_decay(
    cwd: str,
    dep_file: str | None = None,
    include_dev: bool = False,
) -> dict:
    """Convenience function for dependency decay forecast.

    Returns:
        Dict with risks, forecasts, and overall health.
    """
    forecaster = DepDecayForecaster(cwd)
    result = forecaster.analyze(dep_file=dep_file, include_dev=include_dev)
    return {
        "overall_health": result.overall_health,
        "risks": [
            {"name": r.name, "version": r.current_version, "risk_score": r.risk_score,
             "risk_level": r.risk_level, "cve_count": r.cve_count,
             "recommendation": r.recommendation, "alternatives": r.alternatives}
            for r in result.risks
        ],
        "forecasts": [
            {"name": f.name, "months_to_critical": f.months_to_critical,
             "predicted_risk_6mo": f.predicted_risk_6mo,
             "predicted_risk_12mo": f.predicted_risk_12mo}
            for f in result.forecasts
        ],
        "summary": result.summary,
    }
