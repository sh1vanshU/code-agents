"""Decision Fatigue Reducer — auto-apply repetitive micro-decisions, surface novel ones."""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.agent_system.decision_fatigue_reducer")


@dataclass
class Decision:
    """A decision point encountered during development."""
    id: str = ""
    category: str = ""  # naming, formatting, import_order, error_handling, pattern_choice
    description: str = ""
    options: list[str] = field(default_factory=list)
    auto_resolved: bool = False
    chosen_option: str = ""
    confidence: float = 0.0
    is_novel: bool = False
    context: str = ""


@dataclass
class DecisionPattern:
    """A learned decision pattern from history."""
    category: str = ""
    pattern: str = ""
    chosen: str = ""
    frequency: int = 0
    confidence: float = 0.0


@dataclass
class FatigueReport:
    """Complete decision fatigue analysis."""
    total_decisions: int = 0
    auto_resolved: int = 0
    novel_decisions: list[Decision] = field(default_factory=list)
    auto_decisions: list[Decision] = field(default_factory=list)
    learned_patterns: list[DecisionPattern] = field(default_factory=list)
    fatigue_score: float = 0.0  # 0=low fatigue, 1=high fatigue
    savings_pct: float = 0.0
    warnings: list[str] = field(default_factory=list)


# Known micro-decision categories and auto-resolution rules
AUTO_RULES = {
    "naming": {
        "snake_case_funcs": re.compile(r"def\s+([a-z_]\w*)"),
        "PascalCase_classes": re.compile(r"class\s+([A-Z]\w*)"),
    },
    "import_order": {
        "stdlib_first": True,
        "third_party_second": True,
        "local_last": True,
    },
    "error_handling": {
        "specific_exceptions": True,
        "log_before_raise": True,
    },
    "formatting": {
        "trailing_comma": True,
        "double_quotes": True,
    },
}


class DecisionFatigueReducer:
    """Reduces decision fatigue by auto-resolving repetitive choices."""

    def __init__(self):
        self.history: list[DecisionPattern] = []

    def analyze(self, code_context: dict[str, str],
                decision_history: Optional[list[dict]] = None,
                pending_decisions: Optional[list[dict]] = None) -> FatigueReport:
        """Analyze decisions and auto-resolve where possible."""
        logger.info("Analyzing decisions: %d files, %d pending",
                     len(code_context), len(pending_decisions or []))

        # Load history
        if decision_history:
            self.history = self._load_history(decision_history)

        # Detect decisions in code
        detected = self._detect_decisions(code_context)

        # Add pending decisions
        if pending_decisions:
            detected.extend(self._parse_pending(pending_decisions))

        # Auto-resolve what we can
        for decision in detected:
            self._try_auto_resolve(decision)

        auto = [d for d in detected if d.auto_resolved]
        novel = [d for d in detected if d.is_novel]
        total = len(detected)

        report = FatigueReport(
            total_decisions=total,
            auto_resolved=len(auto),
            novel_decisions=novel,
            auto_decisions=auto,
            learned_patterns=self.history,
            fatigue_score=self._compute_fatigue(novel, total),
            savings_pct=(len(auto) / total * 100) if total else 0,
            warnings=self._generate_warnings(novel, detected),
        )
        logger.info("Fatigue: %d/%d auto-resolved, %d novel", len(auto), total, len(novel))
        return report

    def _load_history(self, raw: list[dict]) -> list[DecisionPattern]:
        """Load decision history."""
        patterns = []
        for item in raw:
            patterns.append(DecisionPattern(
                category=item.get("category", ""),
                pattern=item.get("pattern", ""),
                chosen=item.get("chosen", ""),
                frequency=item.get("frequency", 1),
                confidence=float(item.get("confidence", 0.5)),
            ))
        return patterns

    def _detect_decisions(self, code: dict[str, str]) -> list[Decision]:
        """Detect decision points in code."""
        decisions = []
        idx = 0
        for fpath, content in code.items():
            # Naming decisions
            for m in re.finditer(r"def\s+(\w+)", content):
                name = m.group(1)
                if not name.islower() and not name.startswith("_"):
                    idx += 1
                    decisions.append(Decision(
                        id=f"d_{idx}",
                        category="naming",
                        description=f"Function naming: {name}",
                        options=["snake_case", "keep_current"],
                        context=fpath,
                    ))

            # Error handling decisions
            for m in re.finditer(r"except\s*:", content):
                line = content[:m.start()].count("\n") + 1
                idx += 1
                decisions.append(Decision(
                    id=f"d_{idx}",
                    category="error_handling",
                    description=f"Bare except at {fpath}:{line}",
                    options=["catch_specific", "keep_bare"],
                    context=fpath,
                ))

            # Import order decisions
            imports = re.findall(r"^(?:import|from)\s+\S+", content, re.MULTILINE)
            if len(imports) > 3:
                idx += 1
                decisions.append(Decision(
                    id=f"d_{idx}",
                    category="import_order",
                    description=f"Import ordering in {fpath}",
                    options=["isort_standard", "keep_current"],
                    context=fpath,
                ))
        return decisions

    def _parse_pending(self, pending: list[dict]) -> list[Decision]:
        """Parse pending decision dicts."""
        decisions = []
        for p in pending:
            decisions.append(Decision(
                id=p.get("id", ""),
                category=p.get("category", "other"),
                description=p.get("description", ""),
                options=p.get("options", []),
                context=p.get("context", ""),
            ))
        return decisions

    def _try_auto_resolve(self, decision: Decision):
        """Try to auto-resolve a decision using rules and history."""
        # Check history first
        for pattern in self.history:
            if pattern.category == decision.category and pattern.confidence > 0.7:
                decision.auto_resolved = True
                decision.chosen_option = pattern.chosen
                decision.confidence = pattern.confidence
                return

        # Check built-in rules
        if decision.category in AUTO_RULES:
            if decision.category == "naming":
                decision.auto_resolved = True
                decision.chosen_option = "snake_case"
                decision.confidence = 0.9
                return
            elif decision.category == "error_handling":
                decision.auto_resolved = True
                decision.chosen_option = "catch_specific"
                decision.confidence = 0.85
                return
            elif decision.category == "import_order":
                decision.auto_resolved = True
                decision.chosen_option = "isort_standard"
                decision.confidence = 0.95
                return

        # Novel decision — needs human input
        decision.is_novel = True
        decision.confidence = 0.0

    def _compute_fatigue(self, novel: list[Decision], total: int) -> float:
        """Compute fatigue score."""
        if total == 0:
            return 0.0
        return min(1.0, len(novel) / max(total, 1))

    def _generate_warnings(self, novel: list[Decision],
                           all_decisions: list[Decision]) -> list[str]:
        """Generate warnings."""
        warnings = []
        if len(novel) > 10:
            warnings.append(f"High decision load: {len(novel)} novel decisions need attention")
        categories = set(d.category for d in novel)
        if len(categories) > 3:
            warnings.append("Decisions span many categories — consider establishing conventions")
        return warnings


def format_report(report: FatigueReport) -> str:
    """Format fatigue report."""
    lines = [
        "# Decision Fatigue Report",
        f"Decisions: {report.total_decisions} | Auto: {report.auto_resolved} | Novel: {len(report.novel_decisions)}",
        f"Savings: {report.savings_pct:.0f}% | Fatigue: {report.fatigue_score:.0%}",
        "",
    ]
    if report.novel_decisions:
        lines.append("## Needs Your Decision")
        for d in report.novel_decisions[:10]:
            lines.append(f"  [{d.category}] {d.description}")
            if d.options:
                lines.append(f"    Options: {', '.join(d.options)}")
    return "\n".join(lines)
