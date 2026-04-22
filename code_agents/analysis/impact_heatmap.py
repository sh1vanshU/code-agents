"""Impact Heatmap — visual risk map combining change frequency, bugs, coupling, ownership."""

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.analysis.impact_heatmap")


@dataclass
class FileRiskProfile:
    """Risk profile for a single file."""
    file_path: str = ""
    change_frequency: int = 0  # commits touching this file
    bug_density: float = 0.0  # bugs per 100 LOC
    coupling_score: float = 0.0  # 0-1, how coupled to other files
    ownership_score: float = 0.0  # 0-1, 1=single owner, 0=many owners
    complexity: float = 0.0
    lines_of_code: int = 0
    risk_score: float = 0.0  # composite 0-100
    risk_level: str = "low"  # low, medium, high, critical
    contributing_factors: list[str] = field(default_factory=list)


@dataclass
class HeatmapReport:
    """Complete risk heatmap."""
    files: list[FileRiskProfile] = field(default_factory=list)
    hotspots: list[FileRiskProfile] = field(default_factory=list)  # top risk files
    total_files: int = 0
    avg_risk: float = 0.0
    risk_distribution: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


class ImpactHeatmap:
    """Generates a risk heatmap combining multiple signals."""

    def __init__(self, cwd: str):
        self.cwd = cwd

    def analyze(self, file_stats: list[dict],
                git_log: Optional[list[dict]] = None,
                bug_data: Optional[dict] = None) -> HeatmapReport:
        """Generate risk heatmap from combined signals."""
        logger.info("Generating heatmap for %d files", len(file_stats))

        git_log = git_log or []
        bug_data = bug_data or {}

        # Build change frequency from git log
        change_freq = self._compute_change_frequency(git_log)
        ownership = self._compute_ownership(git_log)
        coupling = self._compute_coupling(git_log)

        profiles = []
        for stat in file_stats:
            fpath = stat.get("file_path", stat.get("path", ""))
            loc = stat.get("lines_of_code", stat.get("loc", 0))
            complexity = stat.get("complexity", 0)

            bugs = bug_data.get(fpath, 0)
            bug_dens = (bugs / loc * 100) if loc > 0 else 0.0

            profile = FileRiskProfile(
                file_path=fpath,
                change_frequency=change_freq.get(fpath, 0),
                bug_density=round(bug_dens, 2),
                coupling_score=coupling.get(fpath, 0.0),
                ownership_score=ownership.get(fpath, 1.0),
                complexity=complexity,
                lines_of_code=loc,
            )
            profile.risk_score = self._compute_risk_score(profile)
            profile.risk_level = self._classify_risk(profile.risk_score)
            profile.contributing_factors = self._get_factors(profile)
            profiles.append(profile)

        profiles.sort(key=lambda p: -p.risk_score)
        hotspots = [p for p in profiles if p.risk_level in ("high", "critical")]

        distribution = {"low": 0, "medium": 0, "high": 0, "critical": 0}
        for p in profiles:
            distribution[p.risk_level] = distribution.get(p.risk_level, 0) + 1

        avg = sum(p.risk_score for p in profiles) / len(profiles) if profiles else 0.0

        report = HeatmapReport(
            files=profiles,
            hotspots=hotspots[:20],
            total_files=len(profiles),
            avg_risk=round(avg, 1),
            risk_distribution=distribution,
            warnings=self._generate_warnings(profiles, hotspots),
        )
        logger.info("Heatmap: %d files, avg risk %.1f, %d hotspots", len(profiles), avg, len(hotspots))
        return report

    def _compute_change_frequency(self, git_log: list[dict]) -> dict[str, int]:
        """Compute change frequency per file from git log."""
        freq: dict[str, int] = {}
        for entry in git_log:
            for fpath in entry.get("files", []):
                freq[fpath] = freq.get(fpath, 0) + 1
        return freq

    def _compute_ownership(self, git_log: list[dict]) -> dict[str, float]:
        """Compute ownership score (1=single owner, lower=diffuse)."""
        file_authors: dict[str, set] = {}
        for entry in git_log:
            author = entry.get("author", "")
            for fpath in entry.get("files", []):
                file_authors.setdefault(fpath, set()).add(author)

        ownership = {}
        for fpath, authors in file_authors.items():
            # Single author = 1.0, many authors = lower
            ownership[fpath] = 1.0 / len(authors) if authors else 1.0
        return ownership

    def _compute_coupling(self, git_log: list[dict]) -> dict[str, float]:
        """Compute coupling: files frequently changed together."""
        coupling: dict[str, float] = {}
        for entry in git_log:
            files = entry.get("files", [])
            for fpath in files:
                # More co-changed files = higher coupling
                coupling[fpath] = coupling.get(fpath, 0) + len(files) - 1

        # Normalize to 0-1
        if coupling:
            max_c = max(coupling.values()) or 1
            coupling = {k: min(v / max_c, 1.0) for k, v in coupling.items()}
        return coupling

    def _compute_risk_score(self, profile: FileRiskProfile) -> float:
        """Compute composite risk score 0-100."""
        score = 0.0
        # Change frequency contribution (0-30)
        score += min(30, profile.change_frequency * 3)
        # Bug density contribution (0-25)
        score += min(25, profile.bug_density * 5)
        # Coupling contribution (0-20)
        score += profile.coupling_score * 20
        # Ownership diffusion (0-15)
        score += (1 - profile.ownership_score) * 15
        # Complexity contribution (0-10)
        score += min(10, profile.complexity * 0.5)
        return round(min(100, score), 1)

    def _classify_risk(self, score: float) -> str:
        """Classify risk level from score."""
        if score >= 75:
            return "critical"
        if score >= 50:
            return "high"
        if score >= 25:
            return "medium"
        return "low"

    def _get_factors(self, profile: FileRiskProfile) -> list[str]:
        """Get contributing risk factors."""
        factors = []
        if profile.change_frequency > 5:
            factors.append(f"High change frequency ({profile.change_frequency} commits)")
        if profile.bug_density > 1.0:
            factors.append(f"High bug density ({profile.bug_density:.1f}/100 LOC)")
        if profile.coupling_score > 0.5:
            factors.append(f"High coupling ({profile.coupling_score:.2f})")
        if profile.ownership_score < 0.3:
            factors.append("Diffuse ownership")
        return factors

    def _generate_warnings(self, profiles: list[FileRiskProfile],
                           hotspots: list[FileRiskProfile]) -> list[str]:
        """Generate warnings."""
        warnings = []
        if len(hotspots) > len(profiles) * 0.2:
            warnings.append("More than 20% of files are hotspots — consider broad refactoring")
        critical = [p for p in profiles if p.risk_level == "critical"]
        if critical:
            warnings.append(f"{len(critical)} critical files need immediate attention")
        return warnings


def format_report(report: HeatmapReport) -> str:
    """Format heatmap report."""
    lines = [
        "# Impact Heatmap",
        f"Files: {report.total_files} | Avg Risk: {report.avg_risk} | Hotspots: {len(report.hotspots)}",
        f"Distribution: {report.risk_distribution}",
        "",
    ]
    for p in report.hotspots[:15]:
        lines.append(f"  [{p.risk_level}] {p.file_path} — score {p.risk_score}")
        for f in p.contributing_factors:
            lines.append(f"    - {f}")
    return "\n".join(lines)
