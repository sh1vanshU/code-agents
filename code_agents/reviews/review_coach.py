"""Review Coach — senior engineer code review with mentoring tone.

Provides thoughtful code review focusing on design, naming, patterns,
tradeoffs, and growth opportunities. Uses a constructive, educational
approach rather than gatekeeping.

Usage:
    from code_agents.reviews.review_coach import ReviewCoach, ReviewCoachConfig
    coach = ReviewCoach(ReviewCoachConfig(cwd="/path/to/repo"))
    result = coach.review(diff="...")
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.reviews.review_coach")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ReviewCoachConfig:
    cwd: str = "."
    focus_areas: list[str] = field(default_factory=lambda: [
        "design", "naming", "patterns", "tradeoffs", "readability",
    ])
    mentoring_level: str = "mid"  # "junior", "mid", "senior"


@dataclass
class CoachFinding:
    """A single review finding with educational context."""
    file: str
    line: int
    category: str  # "design", "naming", "patterns", "tradeoffs", "readability", "error_handling"
    severity: str  # "suggestion", "improvement", "concern"
    title: str
    explanation: str
    why_it_matters: str = ""
    code_before: str = ""
    code_after: str = ""
    learning_reference: str = ""


@dataclass
class ReviewCoachReport:
    """Full coaching review result."""
    files_reviewed: int = 0
    total_findings: int = 0
    findings: list[CoachFinding] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    growth_areas: list[str] = field(default_factory=list)
    overall_assessment: str = ""
    summary: str = ""


# ---------------------------------------------------------------------------
# Review rules — category, pattern, finding generator
# ---------------------------------------------------------------------------

NAMING_ISSUES = [
    (re.compile(r"def\s+([a-z])(\s*\()"), "single_char_func",
     "Single-character function name reduces readability",
     "Use descriptive names that reveal intent: process_payment() instead of p()"),
    (re.compile(r"\b([a-z])\s*=\s*"), "single_char_var",
     "Single-character variable (outside loops/comprehensions)",
     "Descriptive names make code self-documenting. 'customer_count' > 'c'"),
    (re.compile(r"def\s+(do_|handle_|process_|manage_)\w+"), "vague_verb",
     "Vague function name prefix (do_, handle_, process_)",
     "Be specific: 'validate_payment_amount' instead of 'process_payment'"),
]

DESIGN_ISSUES = [
    (re.compile(r"def\s+\w+\([^)]{100,}\)"), "too_many_params",
     "Function has many parameters — consider a config object",
     "Group related parameters into a dataclass. This improves testability and reduces coupling."),
    (re.compile(r"if\s+.+(?:\s+and\s+.+){3,}"), "complex_condition",
     "Complex boolean condition — extract to named method",
     "Extract conditions like is_eligible_for_discount(). Named booleans are self-documenting."),
    (re.compile(r"(?:class\s+\w+)(?:.*\n){80,}(?=class|\Z)"), "god_class",
     "Large class may have too many responsibilities",
     "Consider Single Responsibility: split into focused classes. See SOLID principles."),
]

PATTERN_ISSUES = [
    (re.compile(r"if\s+isinstance\s*\(\s*\w+\s*,\s*\w+\s*\)(?:.*elif\s+isinstance){2,}"), "type_switch",
     "Type-checking cascade — consider polymorphism or visitor pattern",
     "Replace isinstance chains with polymorphic dispatch or a strategy pattern."),
    (re.compile(r"(?:try:.*\n\s*.*\n\s*except\s+Exception)"), "broad_except",
     "Catching broad Exception — be specific about expected errors",
     "Catch specific exceptions (ValueError, KeyError) for better error handling."),
    (re.compile(r"global\s+\w+"), "global_state",
     "Global mutable state makes code hard to test and reason about",
     "Use dependency injection or module-level constants instead of global mutable state."),
]

TRADEOFF_ISSUES = [
    (re.compile(r"# TODO|# FIXME|# HACK|# XXX", re.IGNORECASE), "tech_debt_marker",
     "Technical debt marker — consider addressing or tracking",
     "Convert TODOs to tickets. Untracked TODOs accumulate and get forgotten."),
    (re.compile(r"time\.sleep\s*\(\s*\d+\s*\)"), "sleep_in_code",
     "Hard-coded sleep — consider event-driven approach or configurable delay",
     "Sleeps hide race conditions. Use events, callbacks, or configurable timeouts."),
]

ERROR_HANDLING_ISSUES = [
    (re.compile(r"except\s*(?:\w+\s*)?:\s*$"), "swallowed_exception",
     "Bare except clause — ensure exception is logged, not silently swallowed",
     "At minimum, log the exception. Silent failures make debugging extremely difficult."),
    (re.compile(r"except\s+Exception\s*:"), "broad_except_clause",
     "Catching broad Exception — be specific about expected errors",
     "Catch specific exceptions (ValueError, KeyError) for better error handling."),
]

ALL_RULES = [
    ("naming", NAMING_ISSUES),
    ("design", DESIGN_ISSUES),
    ("patterns", PATTERN_ISSUES),
    ("tradeoffs", TRADEOFF_ISSUES),
    ("error_handling", ERROR_HANDLING_ISSUES),
]


# ---------------------------------------------------------------------------
# ReviewCoach
# ---------------------------------------------------------------------------


class ReviewCoach:
    """Senior engineer code review with mentoring tone."""

    def __init__(self, config: Optional[ReviewCoachConfig] = None):
        self.config = config or ReviewCoachConfig()

    def review(self, diff: str = "", files: Optional[list[str]] = None) -> ReviewCoachReport:
        """Review code from diff text or file list."""
        logger.info("Starting coaching review in %s", self.config.cwd)
        report = ReviewCoachReport()

        if diff:
            self._review_diff(diff, report)
        elif files:
            for f in files:
                self._review_file(f, report)
        else:
            self._review_directory(report)

        self._assess(report)
        report.total_findings = len(report.findings)
        report.summary = (
            f"Reviewed {report.files_reviewed} files, "
            f"{report.total_findings} findings. "
            f"Strengths: {len(report.strengths)}, Growth areas: {len(report.growth_areas)}."
        )
        logger.info("Coaching review complete: %s", report.summary)
        return report

    def _review_diff(self, diff: str, report: ReviewCoachReport) -> None:
        """Review a unified diff."""
        current_file = ""
        for line_no, line in enumerate(diff.splitlines(), 1):
            if line.startswith("+++ b/"):
                current_file = line[6:]
                report.files_reviewed += 1
                continue
            if line.startswith("+") and not line.startswith("+++"):
                code = line[1:]
                self._check_line(current_file, line_no, code, report)

    def _review_file(self, filepath: str, report: ReviewCoachReport) -> None:
        """Review a single file."""
        root = Path(self.config.cwd)
        fpath = root / filepath
        if not fpath.exists():
            return
        report.files_reviewed += 1
        try:
            lines = fpath.read_text(errors="replace").splitlines()
        except Exception:
            return
        for idx, line in enumerate(lines, 1):
            self._check_line(filepath, idx, line, report)

    def _review_directory(self, report: ReviewCoachReport) -> None:
        """Review all Python files in cwd."""
        root = Path(self.config.cwd)
        count = 0
        for fpath in root.rglob("*.py"):
            if count >= 200:
                break
            if any(p.startswith(".") or p in ("node_modules", "__pycache__", ".venv") for p in fpath.parts):
                continue
            count += 1
            rel = str(fpath.relative_to(root))
            self._review_file(rel, report)

    def _check_line(self, file: str, line: int, code: str, report: ReviewCoachReport) -> None:
        """Check a single line against all rules."""
        for category, rules in ALL_RULES:
            if category not in self.config.focus_areas and category != "error_handling":
                continue
            for pattern, rule_id, title, explanation in rules:
                if pattern.search(code):
                    report.findings.append(CoachFinding(
                        file=file, line=line,
                        category=category, severity="suggestion",
                        title=title,
                        explanation=explanation,
                        code_before=code.strip(),
                    ))

    def _assess(self, report: ReviewCoachReport) -> None:
        """Generate overall assessment, strengths, and growth areas."""
        cats = {f.category for f in report.findings}
        all_cats = {"design", "naming", "patterns", "tradeoffs", "error_handling", "readability"}
        clean = all_cats - cats

        for c in clean:
            report.strengths.append(f"No {c} issues detected")
        for c in cats:
            count = sum(1 for f in report.findings if f.category == c)
            report.growth_areas.append(f"{c}: {count} suggestions")

        if len(report.findings) == 0:
            report.overall_assessment = "Clean code with no significant issues. Great work!"
        elif len(report.findings) <= 3:
            report.overall_assessment = "Good code overall with minor improvement opportunities."
        else:
            report.overall_assessment = "Several areas for improvement identified. Focus on the highest-impact items first."


def format_coach_report(report: ReviewCoachReport) -> str:
    """Render coaching review report."""
    lines = ["=== Review Coach Report ===", ""]
    lines.append(f"Files reviewed:  {report.files_reviewed}")
    lines.append(f"Findings:        {report.total_findings}")
    lines.append("")

    if report.strengths:
        lines.append("Strengths:")
        for s in report.strengths:
            lines.append(f"  + {s}")
        lines.append("")

    if report.growth_areas:
        lines.append("Growth areas:")
        for g in report.growth_areas:
            lines.append(f"  - {g}")
        lines.append("")

    for f in report.findings:
        lines.append(f"  [{f.category.upper()}] {f.file}:{f.line}")
        lines.append(f"    {f.title}")
        lines.append(f"    {f.explanation}")
        if f.code_before:
            lines.append(f"    Code: {f.code_before}")
        lines.append("")

    lines.append(f"Assessment: {report.overall_assessment}")
    lines.append("")
    lines.append(report.summary)
    return "\n".join(lines)
