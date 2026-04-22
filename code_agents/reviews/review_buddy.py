"""Code Review Buddy — pre-push code review against conventions and security."""

from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.reviews.review_buddy")


@dataclass
class ReviewFinding:
    file: str
    line: int
    category: str  # convention, security, performance, missing-test, style, complexity
    severity: str  # critical, warning, info
    message: str
    suggestion: str = ""
    auto_fixable: bool = False


@dataclass
class ReviewScore:
    total_findings: int = 0
    score: float = 100.0
    grade: str = "A"
    by_severity: dict = field(default_factory=dict)
    by_category: dict = field(default_factory=dict)


@dataclass
class ReviewBuddyReport:
    files_reviewed: int = 0
    findings: list[ReviewFinding] = field(default_factory=list)
    score: ReviewScore = field(default_factory=ReviewScore)
    conventions_checked: list[str] = field(default_factory=list)
    fixes_applied: int = 0


# Security patterns to flag
_SECURITY_CHECKS = [
    (r"eval\s*\(", "security", "critical", "eval() is dangerous — use ast.literal_eval() or safer alternatives"),
    (r"exec\s*\(", "security", "critical", "exec() can run arbitrary code — avoid in production"),
    (r"os\.system\s*\(", "security", "critical", "os.system() is vulnerable to injection — use subprocess.run()"),
    (r"subprocess\.call\s*\(.*shell\s*=\s*True", "security", "critical", "shell=True is vulnerable to injection"),
    (r"pickle\.loads?\s*\(", "security", "warning", "pickle can execute arbitrary code on untrusted data"),
    (r"yaml\.load\s*\((?!.*Loader)", "security", "warning", "yaml.load() without Loader is unsafe — use safe_load()"),
    (r"password\s*=\s*['\"][^'\"]+['\"]", "security", "critical", "Hardcoded password detected"),
    (r"api_key\s*=\s*['\"][^'\"]+['\"]", "security", "critical", "Hardcoded API key detected"),
    (r"token\s*=\s*['\"][A-Za-z0-9]{20,}['\"]", "security", "warning", "Possible hardcoded token"),
    (r"SELECT\s+.*\s+FROM\s+.*%s", "security", "critical", "SQL injection risk — use parameterized queries"),
    (r"\.format\(.*request\.", "security", "warning", "String formatting with request data — XSS/injection risk"),
]

# Code quality patterns
_QUALITY_CHECKS = [
    (r"except\s*:", "style", "warning", "Bare except catches all exceptions — specify the exception type"),
    (r"# TODO|# FIXME|# HACK|# XXX", "style", "info", "TODO/FIXME comment found"),
    (r"print\s*\(", "style", "info", "print() found — consider using logging"),
    (r"import \*", "style", "warning", "Wildcard import — import specific names"),
    (r"\.sleep\s*\(\s*\d{2,}", "performance", "warning", "Long sleep detected — consider async/event-based approach"),
    (r"for .+ in .+:\s*\n\s+for .+ in .+:", "complexity", "info", "Nested loop — consider refactoring"),
]

_CODE_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".java", ".rb", ".rs"}
_TEST_PATTERNS = {"test_", "_test.", ".test.", "spec.", "_spec.", "__tests__"}


class ReviewBuddy:
    """Pre-push code review checking conventions, security, and test coverage."""

    def __init__(self, cwd: str = ".", staged_only: bool = True, auto_fix: bool = False):
        self.cwd = os.path.abspath(cwd)
        self.staged_only = staged_only
        self.auto_fix = auto_fix

    def check(self) -> ReviewBuddyReport:
        """Run all checks on changed files."""
        changed_files = self._get_changed_files()
        code_files = [f for f in changed_files if Path(f).suffix in _CODE_EXTENSIONS]

        findings: list[ReviewFinding] = []
        conventions = []

        for f in code_files:
            full_path = os.path.join(self.cwd, f)
            if not os.path.exists(full_path):
                continue
            try:
                content = Path(full_path).read_text(errors="replace")
            except OSError:
                continue

            findings.extend(self._check_security(f, content))
            findings.extend(self._check_quality(f, content))
            findings.extend(self._check_file_conventions(f, content))

        # Check for missing tests
        findings.extend(self._check_missing_tests(changed_files))

        # Check for large files
        findings.extend(self._check_large_changes(code_files))

        conventions = ["security", "code-quality", "test-coverage", "file-size"]

        score = self._calculate_score(findings)
        fixes = 0
        if self.auto_fix:
            fixes = self._apply_fixes(findings)

        return ReviewBuddyReport(
            files_reviewed=len(code_files),
            findings=findings,
            score=score,
            conventions_checked=conventions,
            fixes_applied=fixes,
        )

    def _run_git(self, *args: str) -> str:
        try:
            result = subprocess.run(
                ["git"] + list(args),
                cwd=self.cwd, capture_output=True, text=True, timeout=30,
            )
            return result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return ""

    def _get_changed_files(self) -> list[str]:
        """Get changed files (staged or all unstaged)."""
        if self.staged_only:
            output = self._run_git("diff", "--cached", "--name-only")
        else:
            output = self._run_git("diff", "--name-only", "HEAD")
        if not output:
            # Fallback: unstaged changes
            output = self._run_git("diff", "--name-only")
        return [f for f in output.split("\n") if f.strip()] if output else []

    def _check_security(self, filepath: str, content: str) -> list[ReviewFinding]:
        """Check for security issues."""
        findings = []
        for line_num, line in enumerate(content.split("\n"), 1):
            for pattern, category, severity, message in _SECURITY_CHECKS:
                if re.search(pattern, line, re.IGNORECASE):
                    findings.append(ReviewFinding(
                        file=filepath, line=line_num,
                        category=category, severity=severity,
                        message=message,
                    ))
        return findings

    def _check_quality(self, filepath: str, content: str) -> list[ReviewFinding]:
        """Check for code quality issues."""
        findings = []
        for line_num, line in enumerate(content.split("\n"), 1):
            for pattern, category, severity, message in _QUALITY_CHECKS:
                if re.search(pattern, line, re.IGNORECASE):
                    findings.append(ReviewFinding(
                        file=filepath, line=line_num,
                        category=category, severity=severity,
                        message=message,
                    ))
        return findings

    def _check_file_conventions(self, filepath: str, content: str) -> list[ReviewFinding]:
        """Check file-level conventions."""
        findings = []
        lines = content.split("\n")

        # Check for very long lines
        for i, line in enumerate(lines, 1):
            if len(line) > 200:
                findings.append(ReviewFinding(
                    file=filepath, line=i,
                    category="style", severity="info",
                    message=f"Line is {len(line)} chars — consider wrapping",
                ))

        # Check for missing docstring (Python)
        if filepath.endswith(".py"):
            has_docstring = any('"""' in line or "'''" in line for line in lines[:10])
            if not has_docstring and len(lines) > 20:
                findings.append(ReviewFinding(
                    file=filepath, line=1,
                    category="convention", severity="info",
                    message="Module docstring missing",
                ))

        return findings

    def _check_missing_tests(self, changed_files: list[str]) -> list[ReviewFinding]:
        """Check if changed source files have corresponding tests."""
        findings = []
        source_files = [
            f for f in changed_files
            if Path(f).suffix in _CODE_EXTENSIONS
            and not any(p in f for p in _TEST_PATTERNS)
        ]

        for sf in source_files:
            stem = Path(sf).stem
            test_name = f"test_{stem}"
            # Check if test file exists in repo
            test_exists = False
            for test_dir in ["tests", "test", "spec", "."]:
                for ext in [".py", ".js", ".ts"]:
                    candidate = os.path.join(self.cwd, test_dir, f"{test_name}{ext}")
                    if os.path.exists(candidate):
                        test_exists = True
                        break
                if test_exists:
                    break

            if not test_exists:
                findings.append(ReviewFinding(
                    file=sf, line=0,
                    category="missing-test", severity="warning",
                    message=f"No test file found for {sf}",
                    suggestion=f"Create tests/{test_name}.py",
                ))

        return findings

    def _check_large_changes(self, files: list[str]) -> list[ReviewFinding]:
        """Flag files with large diffs."""
        findings = []
        for f in files:
            diff = self._run_git("diff", "--cached" if self.staged_only else "HEAD", "--", f)
            if not diff:
                continue
            added = sum(1 for line in diff.split("\n") if line.startswith("+") and not line.startswith("+++"))
            if added > 300:
                findings.append(ReviewFinding(
                    file=f, line=0,
                    category="complexity", severity="warning",
                    message=f"Large change: {added} lines added — consider splitting",
                ))
        return findings

    def _calculate_score(self, findings: list[ReviewFinding]) -> ReviewScore:
        """Calculate review score from findings."""
        if not findings:
            return ReviewScore(total_findings=0, score=100.0, grade="A")

        by_severity: dict[str, int] = {}
        by_category: dict[str, int] = {}
        for f in findings:
            by_severity[f.severity] = by_severity.get(f.severity, 0) + 1
            by_category[f.category] = by_category.get(f.category, 0) + 1

        # Scoring: critical=-20, warning=-5, info=-1
        penalty = (
            by_severity.get("critical", 0) * 20
            + by_severity.get("warning", 0) * 5
            + by_severity.get("info", 0) * 1
        )
        score = max(0.0, 100.0 - penalty)

        if score >= 90:
            grade = "A"
        elif score >= 75:
            grade = "B"
        elif score >= 60:
            grade = "C"
        elif score >= 40:
            grade = "D"
        else:
            grade = "F"

        return ReviewScore(
            total_findings=len(findings),
            score=round(score, 1),
            grade=grade,
            by_severity=by_severity,
            by_category=by_category,
        )

    def _apply_fixes(self, findings: list[ReviewFinding]) -> int:
        """Apply auto-fixable findings. Returns count of fixes applied."""
        fixed = 0
        # Group fixable findings by file
        fixable = [f for f in findings if f.auto_fixable and f.suggestion]
        for finding in fixable:
            logger.info("Auto-fix not yet implemented for: %s", finding.message)
        return fixed


def format_review(report: ReviewBuddyReport) -> str:
    """Format review report for display."""
    s = report.score
    grade_color = {"A": "🟢", "B": "🟡", "C": "🟠", "D": "🔴", "F": "💀"}.get(s.grade, "⚪")

    lines = [
        "## Code Review Buddy",
        "",
        f"**Score:** {grade_color} {s.score}/100 (Grade: {s.grade})",
        f"**Files Reviewed:** {report.files_reviewed}",
        f"**Findings:** {s.total_findings}",
        "",
    ]

    if s.by_severity:
        sev_parts = []
        for sev in ["critical", "warning", "info"]:
            count = s.by_severity.get(sev, 0)
            if count:
                icon = {"critical": "🔴", "warning": "🟡", "info": "ℹ️"}.get(sev, "")
                sev_parts.append(f"{icon} {count} {sev}")
        if sev_parts:
            lines.append("  ".join(sev_parts))
            lines.append("")

    # Group findings by category
    if report.findings:
        by_cat: dict[str, list[ReviewFinding]] = {}
        for f in report.findings:
            by_cat.setdefault(f.category, []).append(f)

        for cat, items in sorted(by_cat.items()):
            lines.append(f"### {cat.replace('-', ' ').title()}")
            lines.append("")
            for f in items[:10]:  # Limit per category
                icon = {"critical": "🔴", "warning": "🟡", "info": "ℹ️"}.get(f.severity, "⚪")
                loc = f"{f.file}:{f.line}" if f.line else f.file
                lines.append(f"- {icon} `{loc}` — {f.message}")
                if f.suggestion:
                    lines.append(f"  Suggestion: {f.suggestion}")
            if len(items) > 10:
                lines.append(f"  ... and {len(items) - 10} more")
            lines.append("")

    if report.fixes_applied:
        lines.append(f"**Auto-fixed:** {report.fixes_applied} issue(s)")

    return "\n".join(lines)
