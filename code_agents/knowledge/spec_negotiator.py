"""Spec Negotiator — generate alternative specs with cost/risk/UX tradeoffs."""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.knowledge.spec_negotiator")


@dataclass
class SpecAlternative:
    """A single specification alternative."""
    name: str = ""
    approach: str = ""
    description: str = ""
    estimated_effort_days: float = 0.0
    risk_level: str = "medium"  # low, medium, high
    risk_factors: list[str] = field(default_factory=list)
    ux_impact: str = "neutral"  # positive, neutral, negative
    ux_notes: list[str] = field(default_factory=list)
    technical_debt: str = "low"  # low, medium, high
    dependencies: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    tradeoffs: list[str] = field(default_factory=list)


@dataclass
class AmbiguityFlag:
    """A detected ambiguity in the requirement."""
    text: str = ""
    ambiguity_type: str = ""  # scope, behavior, priority, constraint
    question: str = ""
    options: list[str] = field(default_factory=list)


@dataclass
class NegotiationReport:
    """Complete spec negotiation output."""
    original_requirement: str = ""
    ambiguities: list[AmbiguityFlag] = field(default_factory=list)
    alternatives: list[SpecAlternative] = field(default_factory=list)
    recommendation: str = ""
    comparison_matrix: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


AMBIGUITY_MARKERS = [
    (re.compile(r"\b(should|could|might|may|possibly|optionally)\b", re.IGNORECASE), "scope",
     "Uncertain scope — is this required or optional?"),
    (re.compile(r"\b(fast|quick|performant|scalable|efficient)\b", re.IGNORECASE), "constraint",
     "Non-quantified quality attribute — define measurable threshold"),
    (re.compile(r"\b(user-friendly|intuitive|clean|modern|nice)\b", re.IGNORECASE), "behavior",
     "Subjective UX term — specify concrete behavior"),
    (re.compile(r"\b(etc\.?|and so on|among others|similar)\b", re.IGNORECASE), "scope",
     "Open-ended scope — enumerate all items explicitly"),
    (re.compile(r"\b(appropriate|suitable|reasonable|proper)\b", re.IGNORECASE), "behavior",
     "Vague qualifier — define specific criteria"),
    (re.compile(r"\b(handle|support|manage)\b", re.IGNORECASE), "behavior",
     "Generic verb — specify exact behavior for each case"),
]


class SpecNegotiator:
    """Analyzes ambiguous requirements and generates alternative specs."""

    def __init__(self, project_context: Optional[str] = None):
        self.project_context = project_context or ""

    def analyze(self, requirement: str,
                constraints: Optional[dict] = None) -> NegotiationReport:
        """Analyze a requirement and produce alternative specs."""
        logger.info("Analyzing requirement (%d chars)", len(requirement))
        constraints = constraints or {}

        # Step 1: Detect ambiguities
        ambiguities = self._detect_ambiguities(requirement)
        logger.info("Found %d ambiguities", len(ambiguities))

        # Step 2: Generate alternatives
        alternatives = self._generate_alternatives(requirement, ambiguities, constraints)

        # Step 3: Build comparison matrix
        matrix = self._build_comparison_matrix(alternatives)

        # Step 4: Generate recommendation
        recommendation = self._recommend(alternatives)

        report = NegotiationReport(
            original_requirement=requirement,
            ambiguities=ambiguities,
            alternatives=alternatives,
            recommendation=recommendation,
            comparison_matrix=matrix,
            warnings=self._generate_warnings(ambiguities),
        )
        logger.info("Generated %d alternatives", len(alternatives))
        return report

    def _detect_ambiguities(self, requirement: str) -> list[AmbiguityFlag]:
        """Detect ambiguous parts of the requirement."""
        flags = []
        for pattern, amb_type, question in AMBIGUITY_MARKERS:
            for m in pattern.finditer(requirement):
                context = requirement[max(0, m.start() - 30):m.end() + 30].strip()
                flags.append(AmbiguityFlag(
                    text=context,
                    ambiguity_type=amb_type,
                    question=question,
                    options=[],
                ))
        return flags

    def _generate_alternatives(self, requirement: str,
                               ambiguities: list[AmbiguityFlag],
                               constraints: dict) -> list[SpecAlternative]:
        """Generate three alternative specs: minimal, balanced, comprehensive."""
        max_days = constraints.get("max_days", 30)
        team_size = constraints.get("team_size", 2)

        minimal = SpecAlternative(
            name="Minimal Viable",
            approach="minimal",
            description=f"Smallest scope that addresses core need: {requirement[:80]}",
            estimated_effort_days=round(max_days * 0.3, 1),
            risk_level="low",
            risk_factors=["May not satisfy all stakeholders", "Limited flexibility"],
            ux_impact="neutral",
            ux_notes=["Basic but functional UX"],
            technical_debt="low",
            acceptance_criteria=self._derive_criteria(requirement, "minimal"),
            tradeoffs=[
                "Fastest delivery",
                "Lowest risk",
                "May need follow-up iteration",
                "Limited feature set",
            ],
        )

        balanced = SpecAlternative(
            name="Balanced",
            approach="balanced",
            description=f"Balanced scope with key features: {requirement[:80]}",
            estimated_effort_days=round(max_days * 0.6, 1),
            risk_level="medium",
            risk_factors=["Moderate complexity", "Some integration risk"],
            ux_impact="positive",
            ux_notes=["Good UX covering main use cases"],
            technical_debt="medium",
            acceptance_criteria=self._derive_criteria(requirement, "balanced"),
            tradeoffs=[
                "Good balance of scope and time",
                "Covers 80% of use cases",
                "Some technical debt accepted",
                "Reasonable delivery timeline",
            ],
        )

        comprehensive = SpecAlternative(
            name="Comprehensive",
            approach="comprehensive",
            description=f"Full scope with all edge cases: {requirement[:80]}",
            estimated_effort_days=round(max_days * 1.0, 1),
            risk_level="high",
            risk_factors=["Scope creep risk", "Complex integration", "Timeline pressure"],
            ux_impact="positive",
            ux_notes=["Polished UX with edge case handling"],
            technical_debt="low",
            acceptance_criteria=self._derive_criteria(requirement, "comprehensive"),
            tradeoffs=[
                "Complete feature set",
                "Higher initial investment",
                "Lower future maintenance",
                "Longest delivery timeline",
            ],
        )

        return [minimal, balanced, comprehensive]

    def _derive_criteria(self, requirement: str, level: str) -> list[str]:
        """Derive acceptance criteria from requirement at given level."""
        base_criteria = [f"Core functionality: {requirement[:60]}"]
        if level == "minimal":
            base_criteria.append("Basic input validation")
            base_criteria.append("Happy path works end-to-end")
        elif level == "balanced":
            base_criteria.extend([
                "Input validation with error messages",
                "Happy path and common error paths handled",
                "Basic logging and monitoring",
            ])
        else:
            base_criteria.extend([
                "Comprehensive input validation",
                "All error paths handled with recovery",
                "Full logging, monitoring, and alerting",
                "Performance within defined SLAs",
                "Documentation and runbook",
            ])
        return base_criteria

    def _build_comparison_matrix(self, alternatives: list[SpecAlternative]) -> dict:
        """Build a comparison matrix for alternatives."""
        matrix = {}
        for alt in alternatives:
            matrix[alt.name] = {
                "effort_days": alt.estimated_effort_days,
                "risk": alt.risk_level,
                "ux_impact": alt.ux_impact,
                "tech_debt": alt.technical_debt,
                "criteria_count": len(alt.acceptance_criteria),
            }
        return matrix

    def _recommend(self, alternatives: list[SpecAlternative]) -> str:
        """Generate recommendation."""
        if len(alternatives) >= 2:
            return (
                f"Recommended: '{alternatives[1].name}' — "
                f"best balance of delivery time ({alternatives[1].estimated_effort_days}d) "
                f"and feature coverage. Start with this and iterate."
            )
        return "Insufficient data for recommendation."

    def _generate_warnings(self, ambiguities: list[AmbiguityFlag]) -> list[str]:
        """Generate warnings about the requirement."""
        warnings = []
        scope_ambs = [a for a in ambiguities if a.ambiguity_type == "scope"]
        if len(scope_ambs) > 3:
            warnings.append(f"High scope ambiguity ({len(scope_ambs)} markers) — clarify before starting")
        constraint_ambs = [a for a in ambiguities if a.ambiguity_type == "constraint"]
        if constraint_ambs:
            warnings.append("Non-quantified constraints — define measurable thresholds")
        return warnings


def format_report(report: NegotiationReport) -> str:
    """Format negotiation report as text."""
    lines = [
        "# Spec Negotiation Report",
        f"\nOriginal: {report.original_requirement[:100]}",
        f"\nAmbiguities: {len(report.ambiguities)}",
    ]
    for a in report.ambiguities:
        lines.append(f"  - [{a.ambiguity_type}] {a.question}")
    lines.append("")
    for alt in report.alternatives:
        lines.append(f"## {alt.name} ({alt.estimated_effort_days}d, {alt.risk_level} risk)")
        lines.append(f"  {alt.description}")
        for t in alt.tradeoffs:
            lines.append(f"  - {t}")
    if report.recommendation:
        lines.append(f"\n## Recommendation\n{report.recommendation}")
    return "\n".join(lines)
