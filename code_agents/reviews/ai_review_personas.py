"""AI Review Personas — multiple code review perspectives with distinct personalities."""

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("code_agents.reviews.ai_review_personas")


@dataclass
class ReviewComment:
    """A single review comment from a persona."""
    file_path: str = ""
    line_number: int = 0
    severity: str = "info"  # info, warning, error, critical
    category: str = ""
    message: str = ""
    suggestion: str = ""
    persona: str = ""


@dataclass
class PersonaReport:
    """Review report from a single persona."""
    persona_name: str = ""
    persona_focus: str = ""
    comments: list[ReviewComment] = field(default_factory=list)
    score: int = 0  # 1-10
    summary: str = ""
    approve: bool = True


@dataclass
class MultiPersonaReport:
    """Combined report from all review personas."""
    persona_reports: list[PersonaReport] = field(default_factory=list)
    consensus_score: float = 0.0
    consensus_approve: bool = True
    critical_issues: list[ReviewComment] = field(default_factory=list)
    total_comments: int = 0
    files_reviewed: int = 0


# Built-in personas with their focus areas and patterns
PERSONA_CONFIGS = {
    "security_hawk": {
        "name": "Security Hawk",
        "focus": "Security vulnerabilities, injection, auth, data exposure",
        "patterns": [
            (re.compile(r"eval\s*\("), "critical", "Use of eval() — potential code injection"),
            (re.compile(r"exec\s*\("), "critical", "Use of exec() — potential code injection"),
            (re.compile(r"subprocess\.\w+\(.*shell\s*=\s*True"), "critical", "Shell=True in subprocess — command injection risk"),
            (re.compile(r"(password|secret|token|api_key)\s*=\s*['\"][^'\"]+['\"]"), "error", "Hardcoded credential detected"),
            (re.compile(r"\.format\(.*request"), "warning", "String formatting with request data — potential injection"),
            (re.compile(r"pickle\.loads?\("), "warning", "Pickle deserialization — potential RCE"),
            (re.compile(r"# ?TODO.*secur", re.IGNORECASE), "warning", "Unresolved security TODO"),
        ],
    },
    "perf_pedant": {
        "name": "Performance Pedant",
        "focus": "Performance issues, N+1 queries, memory leaks, complexity",
        "patterns": [
            (re.compile(r"for\s+\w+\s+in\s+.*\.all\(\)"), "warning", "Iterating .all() — potential N+1 query"),
            (re.compile(r"time\.sleep\("), "warning", "Blocking sleep in code path"),
            (re.compile(r"\+\s*=\s*.*\+"), "info", "String concatenation in loop — use join()"),
            (re.compile(r"import\s+\*"), "warning", "Wildcard import — loads unnecessary modules"),
            (re.compile(r"\.readlines\(\)"), "info", "readlines() loads entire file — consider iterating"),
            (re.compile(r"sorted\(.*sorted\("), "warning", "Nested sorts — O(n log n) squared"),
            (re.compile(r"global\s+\w+"), "warning", "Global variable — potential memory leak and contention"),
        ],
    },
    "readability_purist": {
        "name": "Readability Purist",
        "focus": "Code clarity, naming, documentation, structure",
        "patterns": [
            (re.compile(r"def\s+\w{1,2}\("), "warning", "Function name too short — use descriptive names"),
            (re.compile(r"except\s*:"), "warning", "Bare except — catch specific exceptions"),
            (re.compile(r"except\s+Exception\s*:"), "info", "Broad exception catch — be more specific"),
            (re.compile(r"#\s*(?:hack|fixme|xxx)", re.IGNORECASE), "warning", "Code smell marker found"),
            (re.compile(r"def\s+\w+\([^)]{100,}\)"), "info", "Too many parameters — consider a config object"),
            (re.compile(r"if\s+.*\s+and\s+.*\s+and\s+.*\s+and"), "info", "Complex condition — extract to named boolean"),
            (re.compile(r"class\s+\w+:.*\n(?:\s*\n)*\s*def"), "info", "Class missing docstring"),
        ],
    },
    "reliability_guard": {
        "name": "Reliability Guard",
        "focus": "Error handling, resilience, edge cases, testing",
        "patterns": [
            (re.compile(r"except.*:\s*pass"), "error", "Silent exception swallowing — log or handle"),
            (re.compile(r"except.*:\s*\.\.\.\s*$"), "error", "Exception ignored with ellipsis"),
            (re.compile(r"assert\s+"), "warning", "Assert in production code — use proper validation"),
            (re.compile(r"TODO|FIXME|HACK", re.IGNORECASE), "info", "Unresolved TODO/FIXME/HACK"),
            (re.compile(r"\.get\(\s*['\"].*['\"]\s*\)(?!\s*(?:or|if|is))"), "info", "Dict.get() without default — may return None"),
            (re.compile(r"open\(.*\)(?!.*with)"), "warning", "File open without context manager"),
        ],
    },
}


class AIReviewPersonas:
    """Runs code review from multiple AI persona perspectives."""

    def __init__(self, personas: Optional[list[str]] = None):
        self.active_personas = personas or list(PERSONA_CONFIGS.keys())

    def analyze(self, file_contents: dict[str, str]) -> MultiPersonaReport:
        """Run multi-persona code review."""
        logger.info(
            "Running %d review personas on %d files",
            len(self.active_personas), len(file_contents),
        )

        persona_reports = []
        all_critical = []

        for persona_key in self.active_personas:
            config = PERSONA_CONFIGS.get(persona_key)
            if not config:
                logger.warning("Unknown persona: %s", persona_key)
                continue

            report = self._run_persona(persona_key, config, file_contents)
            persona_reports.append(report)

            for comment in report.comments:
                if comment.severity == "critical":
                    all_critical.append(comment)

        total_comments = sum(len(r.comments) for r in persona_reports)
        scores = [r.score for r in persona_reports if r.score > 0]
        consensus_score = sum(scores) / len(scores) if scores else 0.0
        consensus_approve = all(r.approve for r in persona_reports)

        report = MultiPersonaReport(
            persona_reports=persona_reports,
            consensus_score=round(consensus_score, 1),
            consensus_approve=consensus_approve,
            critical_issues=all_critical,
            total_comments=total_comments,
            files_reviewed=len(file_contents),
        )
        logger.info(
            "Review complete: %d comments, score %.1f, approve=%s",
            total_comments, consensus_score, consensus_approve,
        )
        return report

    def _run_persona(self, key: str, config: dict,
                     file_contents: dict[str, str]) -> PersonaReport:
        """Run a single persona's review."""
        comments = []
        for fpath, content in file_contents.items():
            lines = content.splitlines()
            for pattern, severity, message in config["patterns"]:
                for m in pattern.finditer(content):
                    line_num = content[:m.start()].count("\n") + 1
                    comments.append(ReviewComment(
                        file_path=fpath,
                        line_number=line_num,
                        severity=severity,
                        category=config["focus"].split(",")[0].strip(),
                        message=message,
                        suggestion=self._generate_suggestion(key, message),
                        persona=config["name"],
                    ))

        # Score: start at 10, deduct for issues
        score = 10
        for c in comments:
            if c.severity == "critical":
                score -= 3
            elif c.severity == "error":
                score -= 2
            elif c.severity == "warning":
                score -= 1
            else:
                score -= 0.3
        score = max(1, int(score))

        approve = not any(c.severity in ("critical", "error") for c in comments)

        return PersonaReport(
            persona_name=config["name"],
            persona_focus=config["focus"],
            comments=comments,
            score=score,
            summary=f"{config['name']}: {len(comments)} issues found",
            approve=approve,
        )

    def _generate_suggestion(self, persona: str, message: str) -> str:
        """Generate a fix suggestion based on the issue."""
        suggestions = {
            "eval()": "Use ast.literal_eval() for safe evaluation",
            "exec()": "Refactor to avoid dynamic code execution",
            "Shell=True": "Use shell=False with list arguments",
            "Hardcoded credential": "Move to environment variable or secrets manager",
            "N+1": "Use select_related/prefetch_related or batch query",
            "sleep": "Use async sleep or event-based waiting",
            "Wildcard import": "Import specific names needed",
            "too short": "Use descriptive names that convey intent",
            "Bare except": "Catch specific exception types",
            "Silent exception": "Log the exception or handle appropriately",
        }
        for key, suggestion in suggestions.items():
            if key.lower() in message.lower():
                return suggestion
        return "Review and address this issue"


def format_report(report: MultiPersonaReport) -> str:
    """Format multi-persona report."""
    lines = [
        "# Multi-Persona Code Review",
        f"Score: {report.consensus_score}/10 | Approve: {report.consensus_approve}",
        f"Files: {report.files_reviewed} | Comments: {report.total_comments}",
        "",
    ]
    for pr in report.persona_reports:
        lines.append(f"## {pr.persona_name} ({pr.score}/10)")
        lines.append(f"Focus: {pr.persona_focus}")
        for c in pr.comments[:10]:
            lines.append(f"  [{c.severity}] {c.file_path}:{c.line_number} - {c.message}")
        lines.append("")
    return "\n".join(lines)
