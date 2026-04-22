"""Design Document Generator — structured decision documents.

Generates design docs with context, options, tradeoffs, decision rationale,
and implementation plan from a problem statement.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.knowledge.design_doc")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class Option:
    """A design option/alternative."""

    name: str
    description: str
    pros: list[str] = field(default_factory=list)
    cons: list[str] = field(default_factory=list)
    effort: str = "medium"  # "low" | "medium" | "high"
    risk: str = "low"  # "low" | "medium" | "high"
    recommended: bool = False


@dataclass
class DesignDoc:
    """A generated design document."""

    title: str
    author: str = ""
    date: str = ""
    status: str = "draft"  # "draft" | "review" | "accepted" | "rejected"
    context: str = ""
    problem_statement: str = ""
    goals: list[str] = field(default_factory=list)
    non_goals: list[str] = field(default_factory=list)
    options: list[Option] = field(default_factory=list)
    decision: str = ""
    implementation_plan: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)

    def to_markdown(self) -> str:
        """Render as markdown document."""
        lines = [
            f"# {self.title}",
            "",
            f"**Author:** {self.author}  ",
            f"**Date:** {self.date}  ",
            f"**Status:** {self.status}",
            "",
            "## Context",
            self.context,
            "",
            "## Problem Statement",
            self.problem_statement,
            "",
        ]

        if self.goals:
            lines.append("## Goals")
            for g in self.goals:
                lines.append(f"- {g}")
            lines.append("")

        if self.non_goals:
            lines.append("## Non-Goals")
            for ng in self.non_goals:
                lines.append(f"- {ng}")
            lines.append("")

        if self.options:
            lines.append("## Options Considered")
            for i, opt in enumerate(self.options, 1):
                rec = " (Recommended)" if opt.recommended else ""
                lines.append(f"\n### Option {i}: {opt.name}{rec}")
                lines.append(opt.description)
                lines.append(f"\n**Effort:** {opt.effort} | **Risk:** {opt.risk}")
                if opt.pros:
                    lines.append("\n**Pros:**")
                    for p in opt.pros:
                        lines.append(f"- {p}")
                if opt.cons:
                    lines.append("\n**Cons:**")
                    for c in opt.cons:
                        lines.append(f"- {c}")
            lines.append("")

        if self.decision:
            lines.append("## Decision")
            lines.append(self.decision)
            lines.append("")

        if self.implementation_plan:
            lines.append("## Implementation Plan")
            for i, step in enumerate(self.implementation_plan, 1):
                lines.append(f"{i}. {step}")
            lines.append("")

        if self.risks:
            lines.append("## Risks & Mitigations")
            for r in self.risks:
                lines.append(f"- {r}")
            lines.append("")

        if self.open_questions:
            lines.append("## Open Questions")
            for q in self.open_questions:
                lines.append(f"- {q}")
            lines.append("")

        if self.references:
            lines.append("## References")
            for ref in self.references:
                lines.append(f"- {ref}")
            lines.append("")

        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


class DesignDocGenerator:
    """Generate design documents from problem descriptions and codebase context."""

    def __init__(self, cwd: Optional[str] = None):
        self.cwd = cwd or os.getcwd()

    # ── Public API ────────────────────────────────────────────────────────

    def generate(
        self,
        title: str,
        problem: str,
        options: Optional[list[dict]] = None,
        goals: Optional[list[str]] = None,
        non_goals: Optional[list[str]] = None,
    ) -> DesignDoc:
        """Generate a design document.

        Args:
            title: Document title
            problem: Problem statement / description
            options: List of option dicts with name, description, pros, cons
            goals: List of goals
            non_goals: List of non-goals
        """
        author = self._get_git_author()
        date = datetime.now().strftime("%Y-%m-%d")
        context = self._gather_context(problem)

        doc = DesignDoc(
            title=title,
            author=author,
            date=date,
            status="draft",
            context=context,
            problem_statement=problem,
            goals=goals or self._infer_goals(problem),
            non_goals=non_goals or [],
        )

        if options:
            doc.options = [self._build_option(o) for o in options]
        else:
            doc.options = self._suggest_options(problem)

        doc.decision = self._generate_decision(doc.options)
        doc.implementation_plan = self._generate_plan(doc.options, problem)
        doc.risks = self._identify_risks(doc.options, problem)
        doc.open_questions = self._generate_questions(problem, doc.options)

        logger.info("Generated design doc: %s with %d options", title, len(doc.options))
        return doc

    def save(self, doc: DesignDoc, output_dir: Optional[str] = None) -> str:
        """Save design doc to file."""
        out = output_dir or os.path.join(self.cwd, "docs", "design")
        os.makedirs(out, exist_ok=True)
        slug = re.sub(r"[^a-z0-9]+", "-", doc.title.lower()).strip("-")
        path = os.path.join(out, f"{doc.date}-{slug}.md")
        Path(path).write_text(doc.to_markdown(), encoding="utf-8")
        logger.info("Saved design doc to %s", path)
        return path

    # ── Context gathering ─────────────────────────────────────────────────

    def _get_git_author(self) -> str:
        """Get current git user name."""
        try:
            proc = subprocess.run(
                ["git", "config", "user.name"],
                capture_output=True, text=True, cwd=self.cwd, timeout=5,
            )
            return proc.stdout.strip() if proc.returncode == 0 else "Unknown"
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return "Unknown"

    def _gather_context(self, problem: str) -> str:
        """Gather project context relevant to the problem."""
        parts = []
        # Check project type
        indicators = {
            "package.json": "Node.js project",
            "pyproject.toml": "Python project (Poetry)",
            "go.mod": "Go project",
            "Cargo.toml": "Rust project",
            "pom.xml": "Java project (Maven)",
            "build.gradle": "Java project (Gradle)",
        }
        for fname, desc in indicators.items():
            if os.path.isfile(os.path.join(self.cwd, fname)):
                parts.append(f"Project type: {desc}")
                break

        # Get recent activity
        try:
            proc = subprocess.run(
                ["git", "log", "--oneline", "-10"],
                capture_output=True, text=True, cwd=self.cwd, timeout=5,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                parts.append(f"Recent commits:\n{proc.stdout.strip()}")
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return "\n\n".join(parts) if parts else "No additional context gathered."

    # ── Inference helpers ─────────────────────────────────────────────────

    def _infer_goals(self, problem: str) -> list[str]:
        """Infer goals from the problem statement."""
        goals = []
        problem_lower = problem.lower()
        if "performance" in problem_lower or "slow" in problem_lower:
            goals.append("Improve performance to meet latency/throughput targets")
        if "scale" in problem_lower or "scaling" in problem_lower:
            goals.append("Enable horizontal scaling for increased load")
        if "security" in problem_lower or "vulnerab" in problem_lower:
            goals.append("Address security concerns and meet compliance requirements")
        if "maintain" in problem_lower or "technical debt" in problem_lower:
            goals.append("Improve maintainability and reduce technical debt")
        if "migrat" in problem_lower:
            goals.append("Complete migration with minimal downtime and data integrity")
        if not goals:
            goals.append("Solve the stated problem with minimal disruption")
            goals.append("Maintain backward compatibility where possible")
        return goals

    def _suggest_options(self, problem: str) -> list[Option]:
        """Suggest generic options when none are provided."""
        return [
            Option(
                name="Incremental improvement",
                description="Make targeted changes to existing code to address the problem.",
                pros=["Low risk", "Quick to implement", "Minimal disruption"],
                cons=["May not fully solve the problem", "Technical debt may remain"],
                effort="low", risk="low",
            ),
            Option(
                name="Full redesign",
                description="Redesign the affected component from scratch with the problem in mind.",
                pros=["Clean solution", "Addresses root cause", "Better long-term"],
                cons=["Higher effort", "More risk", "Longer timeline"],
                effort="high", risk="medium",
            ),
            Option(
                name="Third-party solution",
                description="Adopt an existing library or service that solves this problem.",
                pros=["Battle-tested", "Community support", "Faster to deploy"],
                cons=["New dependency", "Less control", "Potential vendor lock-in"],
                effort="medium", risk="medium",
            ),
        ]

    def _build_option(self, opt_dict: dict) -> Option:
        """Build an Option from a dict."""
        return Option(
            name=opt_dict.get("name", "Unnamed"),
            description=opt_dict.get("description", ""),
            pros=opt_dict.get("pros", []),
            cons=opt_dict.get("cons", []),
            effort=opt_dict.get("effort", "medium"),
            risk=opt_dict.get("risk", "low"),
            recommended=opt_dict.get("recommended", False),
        )

    def _generate_decision(self, options: list[Option]) -> str:
        """Generate a decision summary."""
        recommended = [o for o in options if o.recommended]
        if recommended:
            return f"Proceed with **{recommended[0].name}** based on the tradeoff analysis above."
        return "Decision pending — review options with the team and update this document."

    def _generate_plan(self, options: list[Option], problem: str) -> list[str]:
        """Generate implementation plan steps."""
        return [
            "Review and finalize the design document with stakeholders",
            "Create implementation tickets/issues",
            "Implement changes behind a feature flag (if applicable)",
            "Write/update tests for the new behavior",
            "Deploy to staging and validate",
            "Gradual rollout to production with monitoring",
            "Update documentation and runbooks",
        ]

    def _identify_risks(self, options: list[Option], problem: str) -> list[str]:
        """Identify risks across options."""
        risks = []
        high_risk = [o for o in options if o.risk == "high"]
        if high_risk:
            risks.append(f"High-risk options identified: {', '.join(o.name for o in high_risk)}")
        problem_lower = problem.lower()
        if "data" in problem_lower:
            risks.append("Data integrity risk — ensure migrations are reversible")
        if "api" in problem_lower:
            risks.append("API compatibility risk — version or deprecate, do not break")
        risks.append("Timeline risk — scope creep during implementation")
        return risks

    def _generate_questions(self, problem: str, options: list[Option]) -> list[str]:
        """Generate open questions for discussion."""
        questions = [
            "What is the acceptable timeline for this change?",
            "Are there any compliance or regulatory requirements to consider?",
        ]
        if any(o.effort == "high" for o in options):
            questions.append("Do we have the team capacity for the high-effort option?")
        return questions
