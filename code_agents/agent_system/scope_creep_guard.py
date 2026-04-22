"""Scope Creep Guard — monitor coding session against ticket scope, warn on drift."""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.agent_system.scope_creep_guard")


@dataclass
class ScopeItem:
    """A single item in the defined scope."""
    description: str = ""
    file_patterns: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    required: bool = True


@dataclass
class ScopeViolation:
    """A detected scope drift event."""
    file_path: str = ""
    action: str = ""
    reason: str = ""
    severity: str = "info"  # info, warning, critical
    timestamp: float = 0.0
    distance_from_scope: float = 0.0


@dataclass
class ScopeReport:
    """Complete scope analysis report."""
    ticket_description: str = ""
    scope_items: list[ScopeItem] = field(default_factory=list)
    violations: list[ScopeViolation] = field(default_factory=list)
    in_scope_files: list[str] = field(default_factory=list)
    out_of_scope_files: list[str] = field(default_factory=list)
    drift_score: float = 0.0  # 0.0 = on track, 1.0 = fully drifted
    progress_pct: float = 0.0
    warnings: list[str] = field(default_factory=list)


class ScopeCreepGuard:
    """Monitors coding activity against defined ticket scope."""

    def __init__(self):
        self.scope_items: list[ScopeItem] = []

    def analyze(self, ticket: dict,
                changed_files: list[str],
                file_contents: Optional[dict[str, str]] = None) -> ScopeReport:
        """Analyze changes against ticket scope."""
        description = ticket.get("description", ticket.get("title", ""))
        logger.info("Checking scope for: %s", description[:60])

        file_contents = file_contents or {}

        # Extract scope from ticket
        self.scope_items = self._extract_scope(ticket)

        # Classify files
        in_scope = []
        out_scope = []
        violations = []

        for fpath in changed_files:
            if self._is_in_scope(fpath, description):
                in_scope.append(fpath)
            else:
                out_scope.append(fpath)
                violations.append(ScopeViolation(
                    file_path=fpath,
                    action="modified",
                    reason=f"File not related to scope: {description[:40]}",
                    severity="warning" if not self._is_test_or_config(fpath) else "info",
                    distance_from_scope=self._compute_distance(fpath, description),
                ))

        total = len(changed_files)
        drift = len(out_scope) / total if total else 0.0
        progress = self._estimate_progress(in_scope, self.scope_items)

        report = ScopeReport(
            ticket_description=description,
            scope_items=self.scope_items,
            violations=violations,
            in_scope_files=in_scope,
            out_of_scope_files=out_scope,
            drift_score=round(drift, 2),
            progress_pct=round(progress, 1),
            warnings=self._generate_warnings(drift, violations),
        )
        logger.info("Scope: %.0f%% drift, %.0f%% progress, %d violations",
                     drift * 100, progress, len(violations))
        return report

    def _extract_scope(self, ticket: dict) -> list[ScopeItem]:
        """Extract scope items from ticket."""
        items = []
        desc = ticket.get("description", "")
        title = ticket.get("title", "")
        labels = ticket.get("labels", [])
        components = ticket.get("components", [])

        # Extract keywords
        text = f"{title} {desc}"
        words = set(re.findall(r"\b\w{4,}\b", text.lower()))
        tech_words = [w for w in words if w not in (
            "should", "could", "would", "this", "that", "with", "from", "have",
            "been", "will", "when", "what", "they", "need", "make",
        )]

        items.append(ScopeItem(
            description=title,
            keywords=tech_words[:15],
        ))

        for comp in components:
            items.append(ScopeItem(
                description=f"Component: {comp}",
                file_patterns=[f"*{comp.lower()}*"],
                keywords=[comp.lower()],
            ))
        return items

    def _is_in_scope(self, fpath: str, description: str) -> bool:
        """Check if a file is in scope."""
        fpath_lower = fpath.lower()
        for item in self.scope_items:
            for kw in item.keywords:
                if kw in fpath_lower:
                    return True
            for pattern in item.file_patterns:
                clean = pattern.replace("*", "")
                if clean and clean in fpath_lower:
                    return True
        # Test files for in-scope files count as in-scope
        if self._is_test_or_config(fpath):
            return True
        return False

    def _is_test_or_config(self, fpath: str) -> bool:
        """Check if file is a test or config file."""
        name = fpath.split("/")[-1].lower()
        return (name.startswith("test_") or name.endswith("_test.py")
                or name in ("conftest.py", ".env", "config.yaml", "setup.cfg"))

    def _compute_distance(self, fpath: str, description: str) -> float:
        """Compute how far a file is from the scope (0=close, 1=far)."""
        fpath_words = set(re.findall(r"\w+", fpath.lower()))
        desc_words = set(re.findall(r"\w{3,}", description.lower()))
        if not desc_words:
            return 0.5
        overlap = fpath_words & desc_words
        return 1.0 - (len(overlap) / max(len(desc_words), 1))

    def _estimate_progress(self, in_scope: list[str], items: list[ScopeItem]) -> float:
        """Estimate task progress based on scope coverage."""
        if not items:
            return 0.0
        covered = 0
        for item in items:
            for fpath in in_scope:
                if any(kw in fpath.lower() for kw in item.keywords):
                    covered += 1
                    break
        return (covered / len(items)) * 100

    def _generate_warnings(self, drift: float, violations: list[ScopeViolation]) -> list[str]:
        """Generate warnings."""
        warnings = []
        if drift > 0.3:
            warnings.append(f"Scope drift at {drift:.0%} — over 30% of changes are out of scope")
        critical = [v for v in violations if v.severity == "critical"]
        if critical:
            warnings.append(f"{len(critical)} critical scope violations detected")
        if drift > 0.5:
            warnings.append("Consider splitting this into multiple PRs")
        return warnings


def format_report(report: ScopeReport) -> str:
    """Format scope report."""
    lines = [
        "# Scope Creep Guard",
        f"Ticket: {report.ticket_description[:80]}",
        f"Drift: {report.drift_score:.0%} | Progress: {report.progress_pct:.0f}%",
        f"In scope: {len(report.in_scope_files)} | Out: {len(report.out_of_scope_files)}",
        "",
    ]
    if report.violations:
        lines.append("## Violations")
        for v in report.violations:
            lines.append(f"  [{v.severity}] {v.file_path} — {v.reason}")
    for w in report.warnings:
        lines.append(f"  ! {w}")
    return "\n".join(lines)
