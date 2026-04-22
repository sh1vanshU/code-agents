"""Per-repo configurable review checklist with pattern-based scoring.

Evaluates diffs against a list of checklist items (security, quality, testing)
and scores them 0-100. Loads custom rules from .code-agents/review-checklist.yaml.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger("code_agents.reviews.review_checklist")


@dataclass
class ChecklistItem:
    """A single review checklist item."""

    name: str
    description: str
    category: str  # security, quality, testing, style
    weight: float = 1.0  # importance multiplier
    passed: bool = True
    pattern: str = ""  # regex pattern to match against diff (bad patterns)
    file_pattern: str = ""  # glob to match against changed files


@dataclass
class ChecklistResult:
    """Result of running a review checklist."""

    items: list[ChecklistItem] = field(default_factory=list)
    score: float = 100.0  # 0-100
    passed_count: int = 0
    failed_count: int = 0

    @property
    def total(self) -> int:
        return self.passed_count + self.failed_count


# ---------------------------------------------------------------------------
# Default checklist items — built-in rules
# ---------------------------------------------------------------------------

DEFAULT_CHECKLIST: list[dict] = [
    {
        "name": "no_hardcoded_secrets",
        "description": "No hardcoded API keys, passwords, or tokens in diff",
        "category": "security",
        "weight": 3.0,
        "pattern": r"""(?i)(api[_-]?key|password|secret|token|credential)\s*[=:]\s*["'][^"']{8,}["']""",
    },
    {
        "name": "no_sql_injection",
        "description": "No raw string interpolation in SQL queries",
        "category": "security",
        "weight": 2.5,
        "pattern": r"""(?:execute|cursor\.execute|query)\s*\(\s*f?["'].*\{.*\}""",
    },
    {
        "name": "no_eval",
        "description": "No use of eval() or exec() on dynamic input",
        "category": "security",
        "weight": 2.0,
        "pattern": r"""\beval\s*\(|\bexec\s*\(""",
    },
    {
        "name": "error_handling",
        "description": "No bare except clauses that swallow errors silently",
        "category": "quality",
        "weight": 1.5,
        "pattern": r"""except\s*:\s*\n\s*(pass|\.\.\.)\s*$""",
    },
    {
        "name": "no_print_debug",
        "description": "No print() statements used for debugging (use logger)",
        "category": "quality",
        "weight": 1.0,
        "pattern": r"""^\+.*\bprint\s*\(""",
    },
    {
        "name": "tests_included",
        "description": "Changes include corresponding test files",
        "category": "testing",
        "weight": 1.5,
        "file_pattern": "test_*",
    },
]


class ReviewChecklist:
    """Evaluate code diffs against a configurable review checklist."""

    def __init__(self, repo_path: str = "."):
        self.repo_path = repo_path
        self._items: list[dict] = list(DEFAULT_CHECKLIST)
        self._load_custom_checklist()

    def _load_custom_checklist(self) -> None:
        """Load custom checklist from .code-agents/review-checklist.yaml if exists."""
        custom_path = Path(self.repo_path) / ".code-agents" / "review-checklist.yaml"
        if not custom_path.exists():
            return
        try:
            import yaml

            data = yaml.safe_load(custom_path.read_text())
            if isinstance(data, dict) and "checklist" in data:
                items = data["checklist"]
                if isinstance(items, list):
                    self._items = items
                    logger.info("Loaded %d custom checklist items from %s", len(items), custom_path)
        except Exception as exc:
            logger.warning("Failed to load custom checklist: %s", exc)

    def evaluate(self, diff: str, changed_files: list[str] | None = None) -> ChecklistResult:
        """Evaluate a diff against all checklist items.

        Args:
            diff: unified diff text (e.g. from git diff)
            changed_files: list of changed file paths

        Returns:
            ChecklistResult with item-level pass/fail and overall score.
        """
        changed_files = changed_files or []
        result_items: list[ChecklistItem] = []
        total_weight = 0.0
        passed_weight = 0.0

        for item_def in self._items:
            item = ChecklistItem(
                name=item_def.get("name", "unknown"),
                description=item_def.get("description", ""),
                category=item_def.get("category", "other"),
                weight=float(item_def.get("weight", 1.0)),
                pattern=item_def.get("pattern", ""),
                file_pattern=item_def.get("file_pattern", ""),
            )
            total_weight += item.weight

            # Check pattern against diff
            if item.pattern:
                try:
                    if re.search(item.pattern, diff, re.MULTILINE):
                        item.passed = False
                    else:
                        item.passed = True
                except re.error:
                    logger.warning("Invalid regex for %s: %s", item.name, item.pattern)
                    item.passed = True
            # Check file_pattern against changed files
            elif item.file_pattern:
                item.passed = self._check_file_pattern(item.file_pattern, changed_files)
            else:
                item.passed = True

            if item.passed:
                passed_weight += item.weight

            result_items.append(item)

        passed_count = sum(1 for i in result_items if i.passed)
        failed_count = sum(1 for i in result_items if not i.passed)
        score = (passed_weight / total_weight * 100) if total_weight > 0 else 100.0

        return ChecklistResult(
            items=result_items,
            score=round(score, 1),
            passed_count=passed_count,
            failed_count=failed_count,
        )

    @staticmethod
    def _check_file_pattern(pattern: str, changed_files: list[str]) -> bool:
        """Check if changed files match a file pattern requirement.

        For 'tests_included', we check if any test file is in the changed files.
        """
        import fnmatch

        for f in changed_files:
            basename = os.path.basename(f)
            if fnmatch.fnmatch(basename, pattern):
                return True
        return False


def format_checklist(result: ChecklistResult) -> str:
    """Format checklist result for terminal display."""
    lines = []
    lines.append("  ╔══ REVIEW CHECKLIST ══╗")
    lines.append(f"  ║ Score: {result.score:.0f}/100  ({result.passed_count} passed, {result.failed_count} failed)")
    lines.append("  ╚═══════════════════════╝")

    # Group by category
    categories: dict[str, list[ChecklistItem]] = {}
    for item in result.items:
        categories.setdefault(item.category, []).append(item)

    for category, items in sorted(categories.items()):
        lines.append(f"\n  [{category.upper()}]")
        for item in items:
            icon = "PASS" if item.passed else "FAIL"
            marker = f"[{icon}]"
            lines.append(f"    {marker} {item.name}: {item.description}")

    return "\n".join(lines)
